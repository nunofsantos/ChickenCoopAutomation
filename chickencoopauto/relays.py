import logging

import RPi.GPIO as GPIO

from notifications import (
    NotifierMixin,
    ManualModeNotification,
    AutomaticModeNotification,
    WaterHeaterOnNotification,
    WaterHeaterOffNotification,
    WaterHeaterOffEmptyInvalidNotification,
    LightOnNotification,
    LightOffNotification,
    DoorOpeningSunriseNotification,
    DoorClosingSunsetNotification,
    DoorSensorInvalidStateNotification,
    DoorClosedDayNotification,
    DoorOpenNightNotification,
    DoorFailedOpenNotification,
    DoorFailedCloseNotification,
)

log = logging.getLogger(__name__)


class Relay(object):
    def __init__(self, coop, channel, name, port, initial_state):
        self.coop = coop
        self.channel = channel
        self.name = name
        self.port = port
        self._initial_state = initial_state
        self._state = initial_state
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(port, GPIO.OUT, initial=initial_state)

    def state(self):
        return self._state

    def _set(self, state):
        GPIO.output(self.port, state)
        self._state = state

    def on(self):
        self._set(self.coop.ON)

    def off(self):
        self._set(self.coop.OFF)

    def reset(self):
        self._set(self._initial_state)


class RelayOperatedObject(NotifierMixin):
    notifications = []

    def __init__(self, coop, name, relays, sunset_sunrise, manual_mode=False):
        self.notifications.extend([
            ManualModeNotification,
            AutomaticModeNotification,
        ])
        super(RelayOperatedObject, self).__init__(self.notifications)
        self.coop = coop
        self.name = name
        self.relays = []
        if isinstance(relays, list):
            self.relays.extend(relays)
        elif isinstance(relays, Relay):
            self.relays.append(relays)
        self.sunset_sunrise = sunset_sunrise
        self.manual_mode = manual_mode
        self.coop.notifier_manager.register_notifier(self)

    def state(self):
        return [r.state for r in self.relays]

    def check(self, **kwargs):
        if self.sunset_sunrise:
            now = self.sunset_sunrise.refresh()
            log.debug('{} time is {}'.format(self.name, now.to('US/Eastern').format('HH:mm:ss')))
        state = []
        for r in self.relays:
            log.debug('{} is {}'.format(r.name, 'ON' if r.state == self.coop.ON else 'OFF'))
            state.append(r.state)
        return state

    def _set_mode(self, manual_mode=False):
        if manual_mode == self.manual_mode:
            return
        if manual_mode:
            self.set_manual_mode()
        else:
            self.set_auto_mode()

    def set_manual_mode(self):
        self.manual_mode = True
        self.send_notification(ManualModeNotification(name=self.name))

    def set_auto_mode(self):
        self.manual_mode = False
        self.send_notification(AutomaticModeNotification(name=self.name))

    def on(self, relay_num=0, manual_mode=True):
        self._set_mode(manual_mode)
        self.relays[relay_num].on()

    def off(self, relay_num=0, manual_mode=True):
        self._set_mode(manual_mode)
        self.relays[relay_num].off()


class WaterHeater(RelayOperatedObject):
    def __init__(self, coop, name, relay, temp_range, manual_mode=False):
        self.notifications = [
            WaterHeaterOnNotification,
            WaterHeaterOffNotification,
            WaterHeaterOffEmptyInvalidNotification,
        ]
        super(WaterHeater, self).__init__(coop, name, relay, None, manual_mode)
        self.temp_range = temp_range
        self.temp = None

    def check(self, temp):
        super(WaterHeater, self).check()
        self.temp = temp
        water_level_dual_sensor_state = self.coop.water_level_dual_sensor.check()
        if  water_level_dual_sensor_state == self.coop.water_level_dual_sensor.FULL or \
            water_level_dual_sensor_state == self.coop.water_level_dual_sensor.HALF:
            if temp < self.temp_range[0] and not self.is_heating():
                self.on(manual_mode=False)
            elif temp > self.temp_range[1] and self.is_heating():
                self.off(manual_mode=False)
            else:
                if self.manual_mode:
                    self.set_auto_mode()
                    self.clear_notification(WaterHeaterOffEmptyInvalidNotification)
                log.info('Water heater is {}'.format('ON' if self.is_heating() else 'OFF'))
        else:
            # water level is empty or sensors are in invalid state
            if self.is_heating():
                self.send_notification(WaterHeaterOffEmptyInvalidNotification())
                self.off(manual_mode=True)
            else:
                log.info('Water heater is {}'.format('ON' if self.is_heating() else 'OFF'))
        return self.state()[0]

    def is_heating(self):
        return self.state()[0] == self.coop.ON

    def on(self, relay_num=0, manual_mode=True):
        super(WaterHeater, self).on(relay_num=relay_num, manual_mode=manual_mode)
        self.send_notification(WaterHeaterOnNotification(temp=self.temp, mini=self.temp_range[0]))

    def off(self, relay_num=0, manual_mode=True):
        super(WaterHeater, self).off(relay_num=relay_num, manual_mode=manual_mode)
        if not manual_mode:
            self.send_notification(WaterHeaterOffNotification(temp=self.temp, maxi=self.temp_range[1]))

    def set_temp_range(self, temp_range):
        self.temp_range = temp_range


class Light(RelayOperatedObject):
    def __init__(self, coop, name, relay, sunset_sunrise, manual_mode=False):
        self.notifications = [
            LightOnNotification,
            LightOffNotification,
        ]
        super(Light, self).__init__(coop, name, relay, sunset_sunrise, manual_mode)

    def check(self):
        super(Light, self).check()

    def on(self, relay_num=0, manual_mode=True):
        super(Light, self).on(relay_num=relay_num, manual_mode=manual_mode)
        self.send_notification(LightOnNotification())

    def off(self, relay_num=0, manual_mode=True):
        super(Light, self).on(relay_num=relay_num, manual_mode=manual_mode)
        self.send_notification(LightOffNotification())


class Door(RelayOperatedObject):
    CLOSED = True
    OPEN = False
    INVALID = None

    states = {
        'CLOSED': CLOSED,
        'OPEN': OPEN,
        'INVALID': INVALID
    }

    def __init__(self, coop, name, relays, sunset_sunrise, door_open_sensor, door_closed_sensor, manual_mode=False):
        self.notifications = [
            DoorOpeningSunriseNotification,
            DoorClosingSunsetNotification,
            DoorSensorInvalidStateNotification,
            DoorClosedDayNotification,
            DoorOpenNightNotification,
            DoorFailedOpenNotification,
            DoorFailedCloseNotification,
        ]
        super(Door, self).__init__(coop, name, relays, sunset_sunrise, manual_mode)
        self.open_sensor = door_open_sensor
        self.closed_sensor = door_closed_sensor

    def state(self):
        open_sensor_state = self.open_sensor.check()
        closed_sensor_state = self.closed_sensor.check()
        if open_sensor_state and not closed_sensor_state:
            self.clear_notification(DoorSensorInvalidStateNotification)
            self.clear_notification(DoorFailedOpenNotification)
            return self.OPEN
        elif closed_sensor_state and not open_sensor_state:
            self.clear_notification(DoorSensorInvalidStateNotification)
            self.clear_notification(DoorFailedCloseNotification)
            return self.CLOSED
        else:
            self.send_notification(DoorSensorInvalidStateNotification())
            self.set_manual_mode()
            return self.INVALID

    def check(self):
        super(Door, self).check()
        is_day = self.sunset_sunrise.is_day()
        current_state = self.state()
        if current_state == self.CLOSED and is_day:
            if self.manual_mode:
                self.send_notification(DoorClosedDayNotification())
            else:
                self.send_notification(DoorOpeningSunriseNotification())
                self.open(manual_mode=False)
        elif current_state == self.OPEN and not is_day:
            if self.manual_mode:
                self.send_notification(DoorOpenNightNotification())
            else:
                self.send_notification(DoorClosingSunsetNotification())
                self.close(manual_mode=False)
        elif current_state is not self.INVALID:
            log.info('Door {}is {} during the {}'.format('is in MANUAL mode, and ' if self.manual_mode else '',
                                                         'CLOSED' if current_state == self.CLOSED else 'OPEN',
                                                         'day' if is_day else 'night'))

    def open(self, manual_mode=True):
        if self.closed_sensor.check():
            super(Door, self).off(0, manual_mode)
            super(Door, self).on(1, manual_mode)
            opening = self.closed_sensor.wait_off()
            if opening:
                opened = self.open_sensor.wait_on()
            else:
                opened = None
            super(Door, self).off(1, manual_mode)
            if not (opening or opened):
                self.send_notification(DoorFailedOpenNotification())
                self.set_manual_mode()
            else:
                self.clear_notification(DoorFailedOpenNotification)
                self.clear_notification(DoorClosedDayNotification)
        else:
            log.warning('Door is already open')

    def close(self, manual_mode=True):
        if self.open_sensor.check():
            super(Door, self).off(1, manual_mode)
            super(Door, self).on(0, manual_mode)
            closing = self.open_sensor.wait_off()
            if closing:
                closed = self.closed_sensor.wait_on()
            else:
                closed = None
            super(Door, self).off(0, manual_mode)
            if not (closing or closed):
                self.send_notification(DoorFailedCloseNotification())
                self.set_manual_mode()
            else:
                self.clear_notification(DoorFailedCloseNotification)
                self.clear_notification(DoorOpenNightNotification)
        else:
            log.warning('Door is already closed')

    def set_auto_mode(self):
        super(Door, self).set_auto_mode()
        self.clear_notification(DoorClosedDayNotification)
        self.clear_notification(DoorOpenNightNotification)
        self.clear_notification(DoorFailedCloseNotification)
        self.clear_notification(DoorFailedOpenNotification)

    def set_manual_mode(self):
        super(Door, self).set_manual_mode()
        self.clear_notification(DoorClosedDayNotification)
        self.clear_notification(DoorOpenNightNotification)
