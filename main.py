import arrow
import json
import logging
import requests
from time import sleep

import Adafruit_DHT as DHT
import RPi.GPIO as GPIO
from w1thermsensor import W1ThermSensor

# relays have negative logic
ON = False
OFF = True

logging.basicConfig(format='%(asctime)s %(levelname)-7s %(message)s')
log = logging.getLogger('main')
log.setLevel(logging.DEBUG)


class Sensor(object):
    def __init__(self, name):
        self.name = name

    def check(self, **kwargs):
        pass


class SwitchSensor(Sensor):
    def __init__(self, name, port, timeout=30000):
        super(SwitchSensor, self).__init__(name)
        self.port = port
        self.timeout = timeout
        GPIO.setup(port, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def check(self):
        super(SwitchSensor, self).check()
        state = GPIO.input(self.port)
        log.info('{} is {}'.format(self.name, 'CLOSED' if state else 'OPEN'))
        return state

    def wait_on(self):
        return self._wait(detect=GPIO.RISING)

    def wait_off(self):
        return self._wait(detect=GPIO.FALLING)

    def _wait(self, detect=GPIO.RISING):
        state = self.check()
        if (state == GPIO.HIGH and detect == GPIO.RISING) or (state == GPIO.LOW and detect == GPIO.FALLING):
            return False
        log.info('Waiting...')
        result = GPIO.wait_for_edge(self.port, detect, timeout=self.timeout)
        if result is None:
            log.error('{} FAILED to wait to {}'.format(self.name, 'OPEN' if state else 'CLOSE'))
            return False
        log.info('Done!')
        self.check()
        return True


class AmbientTempHumiSensor(Sensor):
    def __init__(self, sensor, port, alert_temp, alert_humi):
        super(AmbientTempHumiSensor, self).__init__('AmbientTempHumiSensor')
        self.sensor = sensor
        self.port = port
        self.alert_temp = alert_temp
        self.alert_humi = alert_humi

    def check(self, max_tries=2):
        super(AmbientTempHumiSensor, self).check()
        humi, temp = DHT.read_retry(self.sensor, self.port, retries=max_tries)
        if temp:
            temp = float(temp) * 1.8 + 32.0
            self.check_alert_temp(temp)
        if humi:
            self.check_alert_humi(humi)
        if humi and temp:
            log.info('Humi: {:.1f}  Temp: {:.1f}'.format(float(humi), float(temp)))
        else:
            log.warning('Unable to get ambient humidity and temperature')
        return humi, temp

    def check_alert_temp(self, temp):
        if temp < self.alert_temp[0]:
            logging.warning('ALERT: Ambient temperature {:.1f}'
                            ' is lower than {:.1f} minimum!'.format(temp, self.alert_temp[0]))
        elif temp > self.alert_temp[1]:
            log.warning('ALERT: Ambient temperature {:.1f}'
                        ' is higher than {:.1f} maximum!'.format(temp, self.alert_temp[1]))

    def check_alert_humi(self, humi):
        if humi < self.alert_humi[0]:
            log.warning('ALERT: Ambient humidity {:.1f}'
                        ' is lower than {:.1f} minimum!'.format(humi, self.alert_humi[0]))
        elif humi > self.alert_humi[1]:
            log.warning('ALERT: Ambient humidity {:.1f}'
                        ' is higher than {:.1f} maximum!'.format(humi, self.alert_humi[1]))

    def set_alert_temp(self, alert_temp):
        self.alert_temp = alert_temp

    def set_alert_humi(self, alert_humi):
        self.alert_humi = alert_humi


class WaterTempSensor(Sensor):
    def __init__(self, heater):
        super(WaterTempSensor, self).__init__('WaterTempSensor')
        self.heater = heater
        self.sensor = W1ThermSensor()  # must go in GPIO4 !!!

    def check(self):
        super(WaterTempSensor, self).check()
        temp = self.sensor.get_temperature(W1ThermSensor.DEGREES_F)
        log.info('Water temp: {:.1f}'.format(temp))
        self.heater.check(temp)
        return temp


class RelayOperatedObject(object):
    def __init__(self, name, relay, sunset_sunrise, manual_mode=False):
        self.name = name
        self.relay = relay
        self.sunset_sunrise = sunset_sunrise
        self.state = relay.get()
        self.manual_mode = manual_mode

    def check(self, **kwargs):
        if self.sunset_sunrise:
            now = self.sunset_sunrise.refresh()
            log.info('{} time is {}'.format(self.name, now.to('US/Eastern').format('HH:mm:ss')))

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

    def on(self, manual_mode=True):
        self._set_mode(manual_mode)
        self.relay.on()
        self.state = ON

    def off(self, manual_mode=True):
        self._set_mode(manual_mode)
        self.relay.off()
        self.state = OFF


class WaterHeater(RelayOperatedObject):
    def __init__(self, relay, temp_range, manual_mode=False):
        super(WaterHeater, self).__init__('Water heater', relay, None, manual_mode)
        self.temp_range = temp_range

    def check(self, temp):
        if temp < self.temp_range[0] and self.state == OFF:
            self.on(manual_mode=False)
            log.warning('ACTION: Water temp {:.1f} is below {:.1f} minimum,'
                        ' turning on heater!'.format(temp, self.temp_range[0]))
        elif temp > self.temp_range[1] and self.state == ON:
            self.off(manual_mode=False)
            log.warning('ACTION: Water temp {:.1f} is above {:.1f} maximum,'
                        ' turning off heater!'.format(temp, self.temp_range[1]))
        else:
            log.info('Water heater is {}'.format('ON' if self.state == ON else 'OFF'))

    def is_heating(self):
        return self.state == ON

    def set_temp_range(self, temp_range):
        self.temp_range = temp_range


class Light(RelayOperatedObject):
    def __init__(self, relay, sunset_sunrise, manual_mode=False):
        super(Light, self).__init__('Light', relay, sunset_sunrise, manual_mode)

    def check(self):
        super(Light, self).check()


class Door(RelayOperatedObject):
    def __init__(self, relays, sunset_sunrise, door_open_sensor, door_closed_sensor, manual_mode=False):
        super(Door, self).__init__('Door', relays[0], sunset_sunrise, manual_mode)
        self.relay2 = relays[1]
        self.open_sensor = door_open_sensor
        self.closed_sensor = door_closed_sensor
        self.CLOSED = OFF
        self.OPEN = ON

    def get_state(self):
        open_sensor_state = self.open_sensor.check()
        closed_sensor_state = self.closed_sensor.check()
        if open_sensor_state and not closed_sensor_state:
            return self.OPEN
        elif closed_sensor_state and not open_sensor_state:
            return self.CLOSED
        else:
            log.error('Door sensor in invalid state!')
            return None

    def check(self):
        super(Door, self).check()
        is_day = self.sunset_sunrise.is_day()
        current_state = self.get_state()
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
            super(Door, self).off(manual_mode)
            self.relay2.on()
            opening = self.closed_sensor.wait_off()
            if opening:
                opened = self.open_sensor.wait_on()
            else:
                opened = None
            self.relay2.off()
            if not (opening or opened):
                log.error('Door FAILED to open!')
        else:
            log.warning('Door is already open')

    def close(self, manual_mode=True):
        if self.open_sensor.check():
            self.relay2.off()
            super(Door, self).on(manual_mode)
            closing = self.open_sensor.wait_off()
            if closing:
                closed = self.closed_sensor.wait_on()
            else:
                closed = None
            super(Door, self).off(manual_mode)
            if not (closing or closed):
                log.error('Door FAILED to close!')
        else:
            log.warning('Door is already closed')


class Relay(object):
    def __init__(self, channel, port, initial_state):
        self.channel = channel
        self.port = port
        self.initial_state = initial_state
        self.state = initial_state
        GPIO.setup(port, GPIO.OUT, initial=initial_state)

    def get(self):
        return self.state

    def _set(self, state):
        GPIO.output(self.port, state)
        self.state = state

    def on(self):
        self._set(ON)

    def off(self):
        self._set(OFF)

    def reset(self):
        self._set(self.initial_state)


class SunriseSunset(object):
    def __init__(self, lat, lon, extra_min_sunrise=0, extra_min_sunset=0):
        self.lat = lat
        self.lon = lon
        self.extra_min_sunrise = extra_min_sunrise
        self.extra_min_sunset = extra_min_sunset
        self.last = None
        self.sunrise = None
        self.sunset = None
        self.refresh()

    def refresh(self):
        now = arrow.utcnow()
        if not self.last or (now - self.last).days > 0:
            url = 'https://api.sunrise-sunset.org/json?lat={}&lng={}&date=today&formatted=0'.format(self.lat, self.lon)
            response = requests.get(url)
            data = json.loads(response.text)
            if data['status'] == 'OK':
                self.sunrise = arrow.get(data['results']['civil_twilight_begin'])
                self.sunset = arrow.get(data['results']['civil_twilight_end'])
                self.last = now
                log.info('SunriseSunset refreshed at {}. Today is {}, sunrise is at {}, sunset is at {}'.format(
                    self.last.to('US/Eastern').format('MMMM DD, YYYY HH:mm:ss'),
                    now.to('US/Eastern').format('MMMM DD, YYYY'),
                    self.sunrise.to('US/Eastern').format('HH:mm:ss'),
                    self.sunset.to('US/Eastern').format('HH:mm:ss')))
            else:
                log.error('SunriseSunset FAILED to refresh at {}'.format(now.to('US/Eastern').format(
                    'MMMM DD, YYYY HH:mm:ss')))
        return now

    # def set_is_day(self, set):
    #     self.isday = set

    def is_day(self):
        # return self.isday
        now = arrow.utcnow()
        return now.shift(minutes=-self.extra_min_sunrise) > self.sunrise and \
               now.shift(minutes=-self.extra_min_sunset) < self.sunset

    def get_sunrise(self):
        return self.sunrise.to('US/Eastern').format()

    def get_sunset(self):
        return self.sunset.to('US/Eastern').format()

    def set_extra_min_sunrise(self, extra_min):
        self.extra_min_sunrise = extra_min

    def set_extra_min_sunset(self, extra_min):
        self.extra_min_sunset = extra_min


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    LAT = 42.548862
    LON = -71.350557
    sunset_sunrise = SunriseSunset(LAT, LON, extra_min_sunset=2000)

    AMBIENT_TEMP_RANGE = (40.0, 80.0)
    AMBIENT_HUMI_RANGE = (30.0, 80.0)
    AMBIENT_TEMP_HUMI_SENSOR_PORT = 21
    ambient_temp_humi_sensor = AmbientTempHumiSensor(DHT.DHT22, AMBIENT_TEMP_HUMI_SENSOR_PORT,
                                                     AMBIENT_TEMP_RANGE, AMBIENT_HUMI_RANGE)

    WATER_HEATER_PORT = 18
    LIGHT_PORT = 22
    DOOR_PORT_1 = 17
    DOOR_PORT_2 = 27
    RELAY_MODULE = [
        Relay(1, WATER_HEATER_PORT, OFF),
        Relay(2, LIGHT_PORT, OFF),
        Relay(3, DOOR_PORT_1, OFF),
        Relay(4, DOOR_PORT_2, OFF),
    ]
    water_heater_relay = RELAY_MODULE[0]

    WATER_HEATER_TEMP_RANGE = (82.0, 85.0)
    water_heater = WaterHeater(water_heater_relay, WATER_HEATER_TEMP_RANGE)

    water_temp_sensor = WaterTempSensor(water_heater)

    light_relay = RELAY_MODULE[1]
    light = Light(light_relay, sunset_sunrise)

    DOOR_OPEN_SENSOR_PORT = 23
    door_open_sensor = SwitchSensor('DoorOpenSensor', DOOR_OPEN_SENSOR_PORT, timeout=3000)
    DOOR_CLOSED_SENSOR_PORT = 24
    door_closed_sensor = SwitchSensor('DoorClosedSensor', DOOR_CLOSED_SENSOR_PORT, timeout=3000)

    door_relays = (RELAY_MODULE[2], RELAY_MODULE[3])
    door = Door(door_relays, sunset_sunrise, door_open_sensor, door_closed_sensor, manual_mode=False)

    # sunset_sunrise.set_is_day(True)

    try:
        count = 1
        while True:
            log.debug('===== {} ====='.format(count))
            #######################
            # if count == 3:
            #     sunset_sunrise.set_extra_min_sunset(0)
            #     sunset_sunrise.set_is_day(False)
            # elif count == 6:
            #     door.set_manual_mode()
            #     sunset_sunrise.set_extra_min_sunset(2000)
            #     sunset_sunrise.set_is_day(True)
            # elif count == 9:
            #     door.set_auto_mode()
            #######################

            # ambient temperature
            ambient_temp_humi_sensor.check()

            # water temperature
            water_temp_sensor.check()

            # light
            light.check()

            #############################
            # door switches
            # door_open_sensor.check()
            # door_closed_sensor.check()
            #############################

            # door
            door.check()

            sleep(2)
            count += 1
    finally:
        log.info('Resetting relays...')
        for relay in RELAY_MODULE:
            relay.reset()
        GPIO.cleanup()


if __name__ == '__main__':
    main()
