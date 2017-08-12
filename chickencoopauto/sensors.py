import logging

import Adafruit_DHT as DHT  # noqa: N814
import RPi.GPIO as GPIO
from w1thermsensor import W1ThermSensor

from notifications import (
    NotifierMixin,
    SwitchSensorFailedWaitNotification,
    WaterSensorLevelLowNotification,
    WaterSensorInvalidNotification,
    AmbientTempHighNotification,
    AmbientTempLowNotification,
    AmbientHumiHighNotification,
    AmbientHumiLowNotification
)


log = logging.getLogger(__name__)


class Sensor(NotifierMixin):
    notifications = []

    def __init__(self, coop, name):
        super(Sensor, self).__init__(self.notifications)
        self.coop = coop
        self.name = name
        self.state = None
        self.coop.notifier_manager.register_notifier(self)

    def check(self, **kwargs):
        pass


class SwitchSensor(Sensor):
    def __init__(self, coop, name, port, timeout=30000):
        self.CLOSED = True
        self.OPEN = False
        self.notifications.extend([
            SwitchSensorFailedWaitNotification,
        ])
        super(SwitchSensor, self).__init__(coop, name)
        self.port = port
        self.timeout = timeout
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(port, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def check(self):
        super(SwitchSensor, self).check()
        self.state = GPIO.input(self.port)
        log.info('{} is {}'.format(self.name, 'CLOSED' if self.state else 'OPEN'))
        return self.state

    def wait_on(self):
        return self._wait(detect=GPIO.RISING)

    def wait_off(self):
        return self._wait(detect=GPIO.FALLING)

    def _wait(self, detect=GPIO.RISING):
        self.state = self.check()
        if (self.state == GPIO.HIGH and detect == GPIO.RISING) or (self.state == GPIO.LOW and detect == GPIO.FALLING):
            return False
        log.info('Waiting...')
        result = GPIO.wait_for_edge(self.port, detect, timeout=self.timeout)
        if result is None:
            self.send_notification(SwitchSensorFailedWaitNotification(name=self.name,
                                                                      state='OPEN' if self.state else 'CLOSE'))
            return False
        log.info('Done!')
        self.check()
        return True


class WaterLevelSensor(SwitchSensor):
    def __init__(self, coop, name, port):
        self.notifications = [
            WaterSensorLevelLowNotification
        ]
        super(WaterLevelSensor, self).__init__(coop, name, port)

    def check(self):
        self.state = super(WaterLevelSensor, self).check()
        if self.state == self.OPEN:
            self.send_notification(WaterSensorLevelLowNotification(name=self.name))
        else:
            self.clear_notification(WaterSensorLevelLowNotification)
        return self.state


class HalfEmptyWaterLevelSensors(Sensor):
    FULL = 1.0
    HALF = 0.5
    EMPTY = 0.0
    INVALID = -1.0

    states = {
        'FULL': FULL,
        'HALF': HALF,
        'EMPTY': EMPTY,
        'INVALID': INVALID
    }

    def __init__(self, coop, name, port_half, port_empty):
        self.notifications = [
            WaterSensorLevelLowNotification,
            WaterSensorInvalidNotification
        ]
        super(HalfEmptyWaterLevelSensors, self).__init__(coop, name)
        self.half_sensor = WaterLevelSensor(
            coop,
            'Water Level Sensor Half',
            port_half
        )
        self.empty_sensor = WaterLevelSensor(
            coop,
            'Water Level Sensor Empty',
            port_empty
        )

    def check(self):
        half_state = self.half_sensor.check()
        empty_state = self.empty_sensor.check()

        if half_state and not empty_state:
            self.send_notification(WaterSensorInvalidNotification())
            self.state = self.states['INVALID']
        if not half_state and empty_state:
            self.clear_notification(WaterSensorInvalidNotification)
            self.state = self.states['HALF']
        if not half_state and not empty_state:
            self.send_notification(WaterSensorLevelLowNotification(name=self.name))
            self.state = self.states['EMPTY']
        if half_state and empty_state:
            self.clear_notification(WaterSensorInvalidNotification)
            self.state = self.states['FULL']
        return self.state


class AmbientTempHumiSensor(Sensor):
    def __init__(self, coop, name, sensor, port, alert_temp, alert_humi):
        self.notifications = [
            AmbientTempHighNotification,
            AmbientTempLowNotification,
            AmbientHumiHighNotification,
            AmbientHumiLowNotification,
        ]
        super(AmbientTempHumiSensor, self).__init__(coop, name)
        self.sensor = sensor
        self.port = port
        self.alert_temp = alert_temp
        self.alert_humi = alert_humi
        self.humi = None
        self.temp = None

    def check(self, max_tries=2):
        super(AmbientTempHumiSensor, self).check()
        self.humi, self.temp = DHT.read_retry(self.sensor, self.port, retries=max_tries)
        if self.temp:
            self.temp = float(self.temp) * 1.8 + 32.0
            self.check_alert_temp(self.temp)
        if self.humi:
            self.check_alert_humi(self.humi)
        if self.humi and self.temp:
            log.info('Humi: {:.1f}  Temp: {:.1f}'.format(float(self.humi), float(self.temp)))
        else:
            log.warning('Unable to get ambient humidity and temperature')
        return self.humi, self.temp

    def check_alert_temp(self, temp):
        if temp < self.alert_temp[0]:
            self.send_notification(AmbientTempLowNotification(temp=temp, mini=self.alert_temp[0]))
        elif temp > self.alert_temp[1]:
            self.send_notification(AmbientTempHighNotification(temp=temp, maxi=self.alert_temp[1]))
        else:
            self.clear_notification(AmbientTempHighNotification)
            self.clear_notification(AmbientTempLowNotification)

    def check_alert_humi(self, humi):
        if humi < self.alert_humi[0]:
            self.send_notification(AmbientHumiLowNotification(humi=humi, mini=self.alert_humi[0]))
        elif humi > self.alert_humi[1]:
            self.send_notification(AmbientHumiHighNotification(humi=humi, maxi=self.alert_humi[1]))
        else:
            self.clear_notification(AmbientHumiHighNotification)
            self.clear_notification(AmbientHumiLowNotification)

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
        self.state = self.sensor.get_temperature(W1ThermSensor.DEGREES_F)
        log.info('Water temp: {:.1f}'.format(self.state))
        self.heater.check(self.state)
        return self.state
