from __future__ import unicode_literals
import json
import logging

import arrow
import Adafruit_DHT as DHT  # noqa: N814
import requests
from requests.exceptions import RequestException
import RPi.GPIO as GPIO
from w1thermsensor import W1ThermSensor

from transitions.extensions import GraphMachine as Machine

from notifications import Notification


log = logging.getLogger(__name__)


class Sensor(Machine):
    def __init__(self, *args, **kwargs):
        self.last = None
        self.name = kwargs.pop('name')
        super(Sensor, self).__init__(*args, **kwargs)

    def read_sensor(self):
        pass

    def read_and_check(self):
        self.read_sensor()
        self.check()


class TempSensor(Sensor):
    def __init__(self, coop, name, sensor, port, temp_range):
        self.name = name
        self.coop = coop
        self.temp_error_low = temp_range[0]
        self.temp_low = temp_range[1]
        self.temp_high = temp_range[2]
        self.temp_error_high = temp_range[3]
        self.temp = None
        self.sensor = sensor
        self.port = port

        self.transition_states = [
            'temp_ok',
            'temp_low',
            'temp_high',
            'temp_error_low',
            'temp_error_high',
            'temp_invalid',
        ]
        self.transition_initial = 'temp_invalid'
        self.transition_transitions = [
            {
                'trigger': 'check',
                'source': [
                    'temp_ok',
                    'temp_low',
                    'temp_error_low',
                    'temp_invalid',
                ],
                'dest': 'temp_high',
                'conditions': self.go_temp_high,
                'after': self.notify_temp_high
            },
            {
                'trigger': 'check',
                'source': 'temp_error_high',
                'dest': 'temp_high',
                'conditions': self.go_temp_high,
            },
            {
                'trigger': 'check',
                'source': [
                    'temp_ok',
                    'temp_high',
                    'temp_error_high',
                    'temp_invalid',
                ],
                'dest': 'temp_low',
                'conditions': self.go_temp_low,
                'after': self.notify_temp_low
            },
            {
                'trigger': 'check',
                'source': 'temp_error_low',
                'dest': 'temp_low',
                'conditions': self.go_temp_low,
            },
            {
                'trigger': 'check',
                'source': [
                    'temp_low',
                    'temp_high',
                    'temp_error_low',
                    'temp_error_high',
                    'temp_invalid',
                ],
                'dest': 'temp_ok',
                'conditions': self.go_temp_ok
            },
            {
                'trigger': 'check',
                'source': [
                    'temp_ok',
                    'temp_low',
                    'temp_high',
                    'temp_error_low',
                    'temp_invalid',
                ],
                'dest': 'temp_error_high',
                'conditions': self.go_temp_error_high,
                'after': self.notify_temp_error_high
            },
            {
                'trigger': 'check',
                'source': [
                    'temp_ok',
                    'temp_low',
                    'temp_high',
                    'temp_error_high',
                    'temp_invalid',
                ],
                'dest': 'temp_error_low',
                'conditions': self.go_temp_error_low,
                'after': self.notify_temp_error_low
            },
            {
                'trigger': 'check',
                'source': '*',
                'dest': 'temp_invalid',
                'conditions': self.go_temp_invalid
            },
        ]

        super(TempSensor, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions
        )

    def go_temp_ok(self):
        return self.temp and self.temp_low <= self.temp <= self.temp_high

    def go_temp_invalid(self):
        return self.temp is None

    def go_temp_low(self):
        return self.temp and self.temp_error_low <= self.temp < self.temp_low

    def go_temp_high(self):
        return self.temp and self.temp_error_high >= self.temp > self.temp_high

    def go_temp_error_low(self):
        return self.temp and self.temp < self.temp_error_low

    def go_temp_error_high(self):
        return self.temp and self.temp > self.temp_error_high

    def notify_temp_high(self):
        self.coop.notifier_callback(
            Notification('WARN',
                         '{name} - temperature {temp:.1f} is above {maxi:.1f} maximum',
                         name=self.name,
                         temp=self.temp,
                         maxi=self.temp_high)
        )

    def notify_temp_low(self):
        self.coop.notifier_callback(
            Notification('WARN',
                         '{name} - temperature {temp:.1f} is below {mini:.1f} minimum',
                         name=self.name,
                         temp=self.temp,
                         mini=self.temp_low)
        )

    def notify_temp_error_high(self):
        self.coop.notifier_callback(
            Notification('ERROR',
                         '{name} - temperature {temp:.1f} is above {maxi:.1f} maximum',
                         name=self.name,
                         temp=self.temp,
                         maxi=self.temp_error_high)
        )

    def notify_temp_error_low(self):
        self.coop.notifier_callback(
            Notification('ERROR',
                         '{name} - temperature {temp:.1f} is below {mini:.1f} minimum',
                         name=self.name,
                         temp=self.temp,
                         mini=self.temp_error_low)
        )

    def status(self):
        error = False
        warn = False
        manual = False

        if self.state in ['temp_low', 'temp_high', 'temp_invalid']:
            warn = True
        if 'error' in self.state:
            error = True

        if error:
            return 'ERROR'
        elif warn:
            return 'WARN'
        elif manual:
            return 'MANUAL'
        else:
            return 'OK'


class AmbientTempHumiSensor(TempSensor):
    def __init__(self, coop, name, sensor, port, temp_range, humi_range, cache_mins):
        self.name = name
        self.humi_low = humi_range[0]
        self.humi_high = humi_range[1]
        self.humi = None
        self.cache_mins = cache_mins

        super(AmbientTempHumiSensor, self).__init__(coop, name, sensor, port, temp_range)
        self.last = arrow.utcnow()

    def read_sensor(self):
        now = arrow.utcnow()
        humi, temp = DHT.read_retry(self.sensor, self.port, retries=3, delay_seconds=2)
        if temp:
            self.temp = float(temp) * 1.8 + 32.0
            self.last = now
            log.info('Ambient temp: {:.1f}'.format(float(self.temp)))
        elif now > self.last.shift(minutes=self.cache_mins):
            self.temp = None
            self.state = 'temp_invalid'
            log.warning('Unable to get ambient temperature')
        elif self.temp:
            log.debug('Last ambient temperature: {:.1f}'.format(float(self.temp)))
        if humi:
            self.humi = humi
            self.last = now
            log.info('Ambient humidity: {:.1f}%'.format(float(self.humi)))
        elif now > self.last.shift(minutes=self.cache_mins):
            self.humi = None
            # self.state = 'humi_invalid'
            log.warning('Unable to get ambient humidity')
        elif self.humi:
            log.debug('Last ambient humidity: {:.1f}%'.format(float(self.temp)))
        return self.temp


class WaterTempSensor(TempSensor):
    def __init__(self, coop, name, temp_range):
        super(WaterTempSensor, self).__init__(
            coop,
            name,
            W1ThermSensor(),
            4,  # must go in GPIO4 !!!
            temp_range
        )

    def read_sensor(self):
        self.temp = self.sensor.get_temperature(W1ThermSensor.DEGREES_F)
        self.last = arrow.utcnow()
        log.info('Water temp: {:.1f}'.format(float(self.temp)))
        return self.temp


class SwitchSensor(Sensor):
    def __init__(self, coop, name, port, timeout=10000):
        self.coop = coop
        self.name = name
        self.port = port
        self.timeout = timeout
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.port, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        self.transition_states = [
            'open',
            'closed',
            'failed to wait'
        ]
        self.transition_initial = 'open'
        self.transition_transitions = [
            {
                'trigger': 'check',
                'source': '*',
                'dest': 'closed',
                'conditions': self.go_closed
            },
            {
                'trigger': 'check',
                'source': '*',
                'dest': 'open',
                'conditions': self.go_open
            },
            {
                'trigger': 'failed_to_wait',
                'source': ['open', 'closed'],
                'dest': 'failed to wait',
                'conditions': self.go_failed_to_wait,
                'after': self.notify_failed_to_wait
            },
        ]

        super(SwitchSensor, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions
        )

    def read_sensor(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.port, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        if GPIO.input(self.port):
            self.state = 'closed'
        else:
            self.state = 'open'
        log.info('{} is {}'.format(self.name, self.state))
        self.last = arrow.utcnow()
        return self.state

    def wait_on(self):
        return self._wait(detect=GPIO.RISING)

    def wait_off(self):
        return self._wait(detect=GPIO.FALLING)

    def _wait(self, detect=GPIO.RISING):
        if (self.is_closed() and detect == GPIO.RISING) or \
           (self.is_open() and detect == GPIO.FALLING):
            return False
        log.debug('Waiting...')
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.port, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        result = GPIO.wait_for_edge(self.port, detect, timeout=self.timeout)
        if result is None:
            self.failed_to_wait()
            return False
        log.debug('Done!')
        return True

    def go_open(self):
        return self.state == 'open'

    def go_closed(self):
        return self.state == 'closed'

    def go_failed_to_wait(self):
        return self.state == 'failed to wait'

    def notify_open(self):
        log.debug('{} is OPEN!'.format(self.name))

    def notify_closed(self):
        log.debug('{} is CLOSED!'.format(self.name))

    def notify_failed_to_wait(self):
        log.warning('{} failed to WAIT!'.format(self.name))


class HalfEmptyWaterLevelsSensor(Sensor):
    def __init__(self, coop, name, port_half, port_empty):
        self.coop = coop
        self.name = name
        self.port_half = port_half
        self.port_empty = port_empty
        self.half_sensor = SwitchSensor(self.coop, '{} Half'.format(name), port_half)
        self.empty_sensor = SwitchSensor(self.coop, '{} Empty'.format(name), port_empty)

        self.transition_states = [
            'full',
            'half',
            'empty',
            'invalid',
        ]
        self.transition_initial = 'full'
        self.transition_transitions = [
            {
                'trigger': 'check',
                'source': ['empty', 'half', 'invalid'],
                'dest': 'full',
                'conditions': self.go_full,
                'after': self.notify_full
            },
            {
                'trigger': 'check',
                'source': ['full', 'empty', 'invalid'],
                'dest': 'half',
                'conditions': self.go_half,
                'after': self.notify_half
            },
            {
                'trigger': 'check',
                'source': ['full', 'half', 'invalid'],
                'dest': 'empty',
                'conditions': self.go_empty,
                'after': self.notify_empty
            },
            {
                'trigger': 'check',
                'source': ['full', 'half', 'empty'],
                'dest': 'invalid',
                'conditions': self.go_invalid,
                'after': self.notify_invalid
            },
        ]

        super(HalfEmptyWaterLevelsSensor, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions
        )

    def read_sensor(self):
        self.half_sensor.read_sensor()
        self.empty_sensor.read_sensor()
        self.last = arrow.utcnow()
        return self.state

    def read_and_check(self):
        self.half_sensor.read_and_check()
        self.empty_sensor.read_and_check()
        self.check()
        return self.state

    def go_full(self):
        if self.is_full():
            return False
        else:
            return self.half_sensor.state == 'closed' and self.empty_sensor.state == 'closed'

    def go_half(self):
        if self.is_half():
            return False
        else:
            return self.half_sensor.state == 'open' and self.empty_sensor.state == 'closed'

    def go_empty(self):
        if self.is_empty():
            return False
        else:
            return self.half_sensor.state == 'open' and self.empty_sensor.state == 'open'

    def go_invalid(self):
        if self.is_invalid():
            return False
        else:
            return self.half_sensor.state == 'closed' and self.empty_sensor.state == 'open'

    def notify_full(self):
        self.coop.notifier_callback(
            Notification('INFO',
                         '{name} - water tank is full',
                         name=self.name)
        )

    def notify_half(self):
        self.coop.notifier_callback(
            Notification('WARN',
                         '{name} - water tank is low',
                         name=self.name)
        )

    def notify_empty(self):
        self.coop.notifier_callback(
            Notification('ERROR',
                         '{name} - water tank is empty',
                         name=self.name)
        )

    def notify_invalid(self):
        self.coop.notifier_callback(
            Notification('ERROR',
                         '{name} - water tank sensors are in invalid state',
                         name=self.name)
        )

    def status(self):
        error = False
        warn = False
        manual = False

        if self.state == 'half':
            warn = True
        elif self.state in ['empty', 'invalid']:
            error = True

        if error:
            return 'ERROR'
        elif warn:
            return 'WARN'
        elif manual:
            return 'MANUAL'
        else:
            return 'OK'


class DoorDualSensor(Sensor):
    def __init__(self, coop, name, port_top, port_bottom, timeout=10000):
        self.coop = coop
        self.name = name
        self.port_top = port_top
        self.port_bottom = port_bottom
        self.top_sensor = SwitchSensor(self.coop, '{} Top'.format(name), port_top, timeout=timeout)
        self.bottom_sensor = SwitchSensor(self.coop, '{} Bottom'.format(name), port_bottom, timeout=timeout)

        self.transition_states = [
            'open',
            'closed',
            'invalid',
        ]
        self.transition_initial = 'closed'
        self.transition_transitions = [
            {
                'trigger': 'failed_wait',
                'source': ['open', 'closed'],
                'dest': 'invalid',
                'after': self.notify_invalid
            },
            {
                'trigger': 'check',
                'source': ['open', 'closed'],
                'dest': 'invalid',
                'conditions': self.go_invalid,
                'after': self.notify_invalid
            },
            {
                'trigger': 'check',
                'source': ['invalid', 'closed'],
                'dest': 'open',
                'conditions': self.go_open,
                'after': self.notify_open
            },
            {
                'trigger': 'check',
                'source': ['invalid', 'open'],
                'dest': 'closed',
                'conditions': self.go_closed,
                'after': self.notify_closed
            },
        ]

        super(DoorDualSensor, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions
        )

    def read_sensor(self):
        self.top_sensor.read_sensor()
        self.bottom_sensor.read_sensor()
        self.last = arrow.utcnow()
        return self.state

    def read_and_check(self):
        self.top_sensor.read_and_check()
        self.bottom_sensor.read_and_check()
        self.check()
        return self.state

    def go_open(self):
        return self.top_sensor.state == 'closed' and self.bottom_sensor.state == 'open'

    def go_closed(self):
        return self.top_sensor.state == 'open' and self.bottom_sensor.state == 'closed'

    def go_invalid(self):
        return self.top_sensor.state == self.bottom_sensor.state

    def notify_open(self):
        # self.coop.notifier_callback(
        #     Notification('INFO',
        #                  '{name} is open',
        #                  name=self.name)
        # )
        log.info('{name} is open'.format(name=self.name))

    def notify_closed(self):
        # self.coop.notifier_callback(
        #     Notification('INFO',
        #                  '{name} is closed',
        #                  name=self.name)
        # )
        log.info('{name} is closed'.format(name=self.name))

    def notify_invalid(self):
        # self.coop.notifier_callback(
        #     Notification('INFO',
        #                  '{name} is in invalid state',
        #                  name=self.name)
        # )
        log.info('{name} is in invalid state'.format(name=self.name))

    def status(self):
        error = False
        warn = False
        manual = False

        if self.state == 'invalid':
            warn = True

        if error:
            return 'ERROR'
        elif warn:
            return 'WARN'
        elif manual:
            return 'MANUAL'
        else:
            return 'OK'


class SunriseSunsetSensor(Sensor):
    def __init__(self, coop, name, lat, lon, extra_min_sunrise=0, extra_min_sunset=0):
        self.coop = coop
        self.name = name
        self.last = None
        self.sunrise = None
        self.sunset = None
        self.lat = lat
        self.lon = lon
        self.extra_min_sunrise = extra_min_sunrise
        self.extra_min_sunset = extra_min_sunset
        # self.count = 0

        self.transition_states = [
            'day',
            'night',
            'invalid',
        ]
        self.transition_initial = 'day'
        self.transition_transitions = [
            {
                'trigger': 'check',
                'source': ['day', 'invalid'],
                'dest': 'night',
                'conditions': self.go_night,
                'after': self.notify_night
            },
            {
                'trigger': 'check',
                'source': ['night', 'invalid'],
                'dest': 'day',
                'conditions': self.go_day,
                'after': self.notify_day
            },
            {
                'trigger': 'check',
                'source': '*',
                'dest': 'invalid',
                'conditions': self.go_invalid,
                'after': self.notify_invalid
            },
        ]

        super(SunriseSunsetSensor, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions
        )

    def read_sensor(self):
        now = arrow.utcnow()

        # self.count += 1
        # print '>>>>>>>>>>>>>>>>>>>>>> COUNT {}'.format(self.count)
        # self.last = now
        # if 3 < self.count < 6:
        #     self.sunrise = now.shift(hours=-6)
        #     self.sunset = now.shift(hours=-3)
        # else:
        #     self.sunrise = now.shift(hours=-3)
        #     self.sunset = now.shift(hours=3)
        # return

        if self.last is None or (now - self.last).days > 1:
            try:
                url = 'https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&date=today&formatted=0'.format(
                    lat=self.lat,
                    lon=self.lon
                )
                response = requests.get(url)
                response.raise_for_status()
                data = json.loads(response.text)
                if data['status'] == 'OK':
                    self.sunrise = arrow.get(data['results']['civil_twilight_begin'])
                    self.sunset = arrow.get(data['results']['civil_twilight_end'])
                    self.last = now
                    log.info('SunriseSunset refreshed at {}. Today is {}, sunrise is at {}, sunset is at {}'.format(
                        self.last.to('US/Eastern').format('MMMM DD, YYYY HH:mm:ss'),
                        now.to('US/Eastern').format('MMMM DD, YYYY'),
                        self.sunrise.to('US/Eastern').format('MMMM DD, YYYY HH:mm:ss'),
                        self.sunset.to('US/Eastern').format('MMMM DD, YYYY HH:mm:ss')))
                else:
                    self.notify_invalid()
                    log.error('SunriseSunset FAILED to refresh at {}'.format(now.to('US/Eastern').format(
                        'MMMM DD, YYYY HH:mm:ss')))
            except (RequestException, ValueError):
                self.notify_invalid()
                log.error('SunriseSunset FAILED to refresh at {}'.format(now.to('US/Eastern').format(
                    'MMMM DD, YYYY HH:mm:ss')))
        return now

    def go_day(self):
        if self.sunset is not None and self.sunrise is not None:
            now = arrow.utcnow()
            if now.to('US/Eastern').day < self.sunrise.to('US/Eastern').day:
                # past sunset, already have sunrise/sunset info for next day
                return False
            else:
                after_sunrise = now > self.sunrise.shift(minutes=self.extra_min_sunrise)
                before_sunset = now < self.sunset.shift(minutes=self.extra_min_sunset)
                return after_sunrise and before_sunset
        else:
            return None

    def go_night(self):
        _go_day = self.go_day()
        if _go_day is None:
            return None
        else:
            return not _go_day

    def go_invalid(self):
        return self.go_day() is None

    def notify_night(self):
        self.coop.notifier_callback(
            Notification('INFO',
                         '{name} - sunset at {sunset}',
                         name=self.name,
                         sunset=self.get_sunset())
        )

    def notify_day(self):
        self.coop.notifier_callback(
            Notification('INFO',
                         '{name} - sunrise at {sunrise}',
                         name=self.name,
                         sunrise=self.get_sunrise())
        )

    def notify_invalid(self):
        self.coop.notifier_callback(
            Notification('WARN',
                         '{name} - unable to get sunrise/sunset data',
                         name=self.name)
        )

    def get_sunrise(self):
        if self.sunrise is not None:
            return self.sunrise.shift(minutes=self.extra_min_sunrise).to('US/Eastern')
        else:
            return None

    def get_sunset(self):
        if self.sunset is not None:
            return self.sunset.shift(minutes=self.extra_min_sunset).to('US/Eastern')
        else:
            return None

    def set_extra_min_sunrise(self, extra_min):
        self.extra_min_sunrise = extra_min

    def set_extra_min_sunset(self, extra_min):
        self.extra_min_sunset = extra_min

    def status(self):
        error = False
        warn = False
        manual = False

        if self.state == 'invalid':
            warn = True

        if error:
            return 'ERROR'
        elif warn:
            return 'WARN'
        elif manual:
            return 'MANUAL'
        else:
            return 'OK'
