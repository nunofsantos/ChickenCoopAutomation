import logging

import RPi.GPIO as GPIO


log = logging.getLogger(__name__)


class Relay(object):
    def __init__(self, coop, channel, port, initial_state):
        self.coop = coop
        self.channel = channel
        self.port = port
        self._initial_state = initial_state
        self._state = initial_state
        GPIO.setup(port, GPIO.OUT, initial=initial_state)

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


class RelayOperatedObject(object):
    def __init__(self, coop, name, relays, sunset_sunrise, manual_mode=False):
        self.coop = coop
        self.name = name
        self.relays = []
        if isinstance(relays, list):
            self.relays .extend(relays)
        elif isinstance(relays, Relay):
            self.relays.append(relays)
        self.sunset_sunrise = sunset_sunrise
        self.manual_mode = manual_mode

    @property
    def state(self):
        return [r.state for r in self.relays]

    def check(self, **kwargs):
        if self.sunset_sunrise:
            now = self.sunset_sunrise.refresh()
            log.debug('{} time is {}'.format(self.name, now.to('US/Eastern').format('HH:mm:ss')))

    def _set_mode(self, manual_mode=False):
        if manual_mode == self.manual_mode:
            return
        if manual_mode:
            self.set_manual_mode()
        else:
            self.set_auto_mode()

    def set_manual_mode(self):
        self.manual_mode = True
        log.info('{} set to MANUAL mode'.format(self.name))

    def set_auto_mode(self):
        self.manual_mode = False
        log.info('{} set to AUTOMATIC mode'.format(self.name))

    def on(self, relay_num=0, manual_mode=True):
        self._set_mode(manual_mode)
        self.relays[relay_num].on()

    def off(self, relay_num=0, manual_mode=True):
        self._set_mode(manual_mode)
        self.relays[relay_num].off()


class WaterHeater(RelayOperatedObject):
    def __init__(self, coop, name, relay, temp_range, manual_mode=False):
        super(WaterHeater, self).__init__(coop, name, relay, None, manual_mode)
        self.temp_range = temp_range

    def check(self, temp):
        if temp < self.temp_range[0] and not self.is_heating():
            self.on(manual_mode=False)
            log.warning('ACTION: Water temp {:.1f} is below {:.1f} minimum,'
                        ' turning on heater!'.format(temp, self.temp_range[0]))
        elif temp > self.temp_range[1] and self.is_heating():
            self.off(manual_mode=False)
            log.warning('ACTION: Water temp {:.1f} is above {:.1f} maximum,'
                        ' turning off heater!'.format(temp, self.temp_range[1]))
        else:
            log.info('Water heater is {}'.format('ON' if self.is_heating() else 'OFF'))

    def is_heating(self):
        return self.state[0] == self.coop.ON

    def set_temp_range(self, temp_range):
        self.temp_range = temp_range


class Light(RelayOperatedObject):
    def __init__(self, coop, name, relay, sunset_sunrise, manual_mode=False):
        super(Light, self).__init__(coop, name, relay, sunset_sunrise, manual_mode)

    def check(self):
        super(Light, self).check()


class Door(RelayOperatedObject):
    def __init__(self, coop, name, relays, sunset_sunrise, door_open_sensor, door_closed_sensor, manual_mode=False):
        super(Door, self).__init__(coop, name, relays, sunset_sunrise, manual_mode)
        self.open_sensor = door_open_sensor
        self.closed_sensor = door_closed_sensor
        self.CLOSED = self.coop.OFF
        self.OPEN = self.coop.ON

    @property
    def state(self):
        open_sensor_state = self.open_sensor.check()
        closed_sensor_state = self.closed_sensor.check()
        if open_sensor_state and not closed_sensor_state:
            return self.OPEN
        elif closed_sensor_state and not open_sensor_state:
            return self.CLOSED
        else:
            log.error('Door sensor in invalid state!')
            self.set_manual_mode()
            return None

    def check(self):
        super(Door, self).check()
        is_day = self.sunset_sunrise.is_day()
        current_state = self.state
        if current_state == self.CLOSED and is_day:
            if self.manual_mode:
                log.warning('Door is in MANUAL mode, and is closed during the day!')
            else:
                log.info('Door was closed, opening after sunrise')
                self.open(manual_mode=False)
        elif current_state == self.OPEN and not is_day:
            if self.manual_mode:
                log.warning('Door is in MANUAL mode, and is open during the night!')
            else:
                log.info('Door was open, closing after sunset')
                self.close(manual_mode=False)
        elif current_state is not None:
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
                log.error('Door FAILED to open!')
                self.set_manual_mode()
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
                log.error('Door FAILED to close!')
                self.set_manual_mode()
        else:
            log.warning('Door is already closed')
