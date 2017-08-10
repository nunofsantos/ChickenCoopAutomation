import logging

import RPi.GPIO as GPIO

from notifications import Notification, NotifierMixin


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
        GPIO.setup(port, GPIO.OUT,initial=initial_state)

    @property
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
    notification_manual_mode = Notification(
        'manual mode',
        Notification.MANUAL,
        '{name} set to MANUAL mode'
    )
    notification_auto_mode = Notification(
        'automatic mode',
        Notification.INFO,
        '{name} set to automatic mode',
        auto_clear=True
    )
    notifications = []

    def __init__(self, coop, name, relays, sunset_sunrise, manual_mode=False):
        self.notifications.extend([
            self.notification_manual_mode,
            self.notification_auto_mode,
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

    @property
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
        self.send_notification(self.notification_manual_mode, name=self.name)

    def set_auto_mode(self):
        self.manual_mode = False
        self.clear_notification(self.notification_manual_mode)
        self.send_notification(self.notification_auto_mode, name=self.name)

    def on(self, relay_num=0, manual_mode=True):
        self._set_mode(manual_mode)
        self.relays[relay_num].on()

    def off(self, relay_num=0, manual_mode=True):
        self._set_mode(manual_mode)
        self.relays[relay_num].off()


class WaterHeater(RelayOperatedObject):
    notification_water_heater_on = Notification(
        'water heater on',
        Notification.INFO,
        'Water temp {temp:.1f} is below {min:.1f} minimum, turning on heater!'
    )
    notification_water_heater_off = Notification(
        'water heater off',
        Notification.INFO,
        'Water temp {temp:.1f} is above {max:.1f} maximum, turning off heater.',
        auto_clear=True
    )
    notification_water_heater_off_empty_invalid = Notification(
        'water heater off empty invalid',
        Notification.INFO,
        'Water tank is empty or in invalid state, turning off heater.',
        auto_clear=True
    )

    def __init__(self, coop, name, relay, temp_range, manual_mode=False):
        self.notifications = [
            self.notification_water_heater_on,
            self.notification_water_heater_off,
            self.notification_water_heater_off_empty_invalid
        ]
        super(WaterHeater, self).__init__(coop, name, relay, None, manual_mode)
        self.temp_range = temp_range
        self.temp = None

    def check(self, temp):
        super(WaterHeater, self).check()
        self.temp = temp
        if self.coop.water_level_dual_sensor.check() in (self.coop.water_level_dual_sensor.FULL,
                                                         self.coop.water_level_dual_sensor.HALF):
            if temp < self.temp_range[0] and not self.is_heating():
                self.on(manual_mode=False)
            elif temp > self.temp_range[1] and self.is_heating():
                self.off(manual_mode=False)
            else:
                if self.manual_mode:
                    self.set_auto_mode()
                    self.clear_notification(self.notification_water_heater_off_empty_invalid)
                log.info('Water heater is {}'.format('ON' if self.is_heating() else 'OFF'))
        else:
            # water level is empty or sensors are in invalid state
            if self.is_heating():
                self.send_notification(self.notification_water_heater_off_empty_invalid)
                self.off(manual_mode=True)
            else:
                log.info('Water heater is {}'.format('ON' if self.is_heating() else 'OFF'))

    def is_heating(self):
        return self.state[0] == self.coop.ON

    def on(self, relay_num=0, manual_mode=True):
        super(WaterHeater, self).on(relay_num=relay_num, manual_mode=manual_mode)
        self.clear_notification(self.notification_water_heater_off)
        self.send_notification(self.notification_water_heater_on, temp=self.temp, min=self.temp_range[0])

    def off(self, relay_num=0, manual_mode=True):
        super(WaterHeater, self).off(relay_num=relay_num, manual_mode=manual_mode)
        self.clear_notification(self.notification_water_heater_on)
        if not manual_mode:
            self.send_notification(self.notification_water_heater_off, temp=self.temp, max=self.temp_range[1])

    def set_temp_range(self, temp_range):
        self.temp_range = temp_range


class Light(RelayOperatedObject):
    notification_light_on = Notification(
        'light on',
        Notification.INFO,
        'Turning ON light'
    )
    notification_light_off = Notification(
        'light off',
        Notification.INFO,
        'Turning OFF light',
        auto_clear=True
    )

    def __init__(self, coop, name, relay, sunset_sunrise, manual_mode=False):
        self.notifications = [
            self.notification_light_on,
            self.notification_light_off
        ]
        super(Light, self).__init__(coop, name, relay, sunset_sunrise, manual_mode)

    def check(self):
        super(Light, self).check()

    def on(self, relay_num=0, manual_mode=True):
        super(Light, self).on(relay_num=relay_num, manual_mode=manual_mode)
        self.clear_notification(self.notification_light_off)
        self.send_notification(self.notification_light_on)

    def off(self, relay_num=0, manual_mode=True):
        super(Light, self).on(relay_num=relay_num, manual_mode=manual_mode)
        self.clear_notification(self.notification_light_on)
        self.send_notification(self.notification_light_off)


class Door(RelayOperatedObject):
    notification_door_opening_sunrise = Notification(
        'door opening',
        Notification.INFO,
        'Door was closed, opening after sunrise',
        auto_clear=True
    )
    notification_door_closing_sunset = Notification(
        'door closing',
        Notification.INFO,
        'Door was open, closing after sunset',
        auto_clear=True
    )
    notification_door_sensor_invalid_state = Notification(
        'door sensor invalid',
        Notification.ERROR,
        'Door sensors are in invalid state!'
    )
    notification_door_manual_mode_closed_day = Notification(
        'door manual mode closed day',
        Notification.WARN,
        'Door is in MANUAL mode, and is closed during the day!'
    )
    notification_door_manual_mode_open_night = Notification(
        'door manual mode open night',
        Notification.WARN,
        'Door is in MANUAL mode, and is open during the night!'
    )
    notification_door_failed_open = Notification(
        'door failed open',
        Notification.ERROR,
        'Door FAILED to open'
    )
    notification_door_failed_close = Notification(
        'door failed close',
        Notification.ERROR,
        'Door FAILED to close'
    )

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
            self.notification_door_opening_sunrise,
            self.notification_door_closing_sunset,
            self.notification_door_sensor_invalid_state,
            self.notification_door_manual_mode_closed_day,
            self.notification_door_manual_mode_open_night,
            self.notification_door_failed_open,
            self.notification_door_failed_close,
        ]
        super(Door, self).__init__(coop, name, relays, sunset_sunrise, manual_mode)
        self.open_sensor = door_open_sensor
        self.closed_sensor = door_closed_sensor

    @property
    def state(self):
        open_sensor_state = self.open_sensor.check()
        closed_sensor_state = self.closed_sensor.check()
        if open_sensor_state and not closed_sensor_state:
            self.clear_notification(self.notification_door_sensor_invalid_state)
            self.clear_notification(self.notification_door_failed_open)
            return self.OPEN
        elif closed_sensor_state and not open_sensor_state:
            self.clear_notification(self.notification_door_sensor_invalid_state)
            self.clear_notification(self.notification_door_failed_close)
            return self.CLOSED
        else:
            self.send_notification(self.notification_door_sensor_invalid_state)
            self.set_manual_mode()
            return self.INVALID

    def check(self):
        super(Door, self).check()
        is_day = self.sunset_sunrise.is_day()
        current_state = self.state
        if current_state == self.CLOSED and is_day:
            if self.manual_mode:
                self.send_notification(self.notification_door_manual_mode_closed_day)
            else:
                self.send_notification(self.notification_door_opening_sunrise)
                self.open(manual_mode=False)
        elif current_state == self.OPEN and not is_day:
            if self.manual_mode:
                self.send_notification(self.notification_door_manual_mode_open_night)
            else:
                self.send_notification(self.notification_door_closing_sunset)
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
                self.send_notification(self.notification_door_failed_open)
                self.set_manual_mode()
            else:
                self.clear_notification(self.notification_door_failed_open)
                self.clear_notification(self.notification_door_manual_mode_closed_day)
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
                self.send_notification(self.notification_door_failed_close)
                self.set_manual_mode()
            else:
                self.clear_notification(self.notification_door_failed_close)
                self.clear_notification(self.notification_door_manual_mode_open_night)
        else:
            log.warning('Door is already closed')

    def set_auto_mode(self):
        super(Door, self).set_auto_mode()
        self.clear_notification(self.notification_door_manual_mode_closed_day)
        self.clear_notification(self.notification_door_manual_mode_open_night)
        self.clear_notification(self.notification_door_failed_close)
        self.clear_notification(self.notification_door_failed_open)

    def set_manual_mode(self):
        super(Door, self).set_manual_mode()
        self.clear_notification(self.notification_door_manual_mode_closed_day)
        self.clear_notification(self.notification_door_manual_mode_open_night)
