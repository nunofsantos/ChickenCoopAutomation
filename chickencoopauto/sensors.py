import logging

import Adafruit_DHT as DHT
import RPi.GPIO as GPIO
from w1thermsensor import W1ThermSensor


log = logging.getLogger(__name__)


class Sensor(object):
    def __init__(self, coop, name):
        self.coop = coop
        self.name = name

    def check(self, **kwargs):
        pass


class SwitchSensor(Sensor):
    def __init__(self, coop, name, port, timeout=30000):
        super(SwitchSensor, self).__init__(coop, name)
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


class WaterLevelSensor(SwitchSensor):
    def __init__(self, coop, name, port):
        super(WaterLevelSensor, self).__init__(coop, name, port)


class AmbientTempHumiSensor(Sensor):
    def __init__(self, coop, name, sensor, port, alert_temp, alert_humi):
        super(AmbientTempHumiSensor, self).__init__(coop, name)
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
    def __init__(self, coop, name, heater):
        super(WaterTempSensor, self).__init__(coop, name)
        self.heater = heater
        self.sensor = W1ThermSensor()  # must go in GPIO4 !!!

    def check(self):
        super(WaterTempSensor, self).check()
        temp = self.sensor.get_temperature(W1ThermSensor.DEGREES_F)
        log.info('Water temp: {:.1f}'.format(temp))
        self.heater.check(temp)
        return temp
