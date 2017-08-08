import logging

import Adafruit_DHT as DHT
import RPi.GPIO as GPIO
from w1thermsensor import W1ThermSensor

from notifications import Notification, NotifierMixin


log = logging.getLogger(__name__)


class Sensor(NotifierMixin):
    notifications = []

    def __init__(self, coop, name):
        super(Sensor, self).__init__(self.notifications)
        self.coop = coop
        self.name = name

    def check(self, **kwargs):
        pass


class SwitchSensor(Sensor):
    notification_switch_sensor_failed_wait = Notification(
        'switch sensor failed wait',
        Notification.ERROR,
        '{name} FAILED to wait to {state}',
        auto_clear=True
    )

    def __init__(self, coop, name, port, timeout=30000):
        self.notifications.extend([
            self.notification_switch_sensor_failed_wait,
        ])
        super(SwitchSensor, self).__init__(coop, name)
        self.port = port
        self.timeout = timeout
        GPIO.setmode(GPIO.BCM)
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
            self.send_notification(self.notification_switch_sensor_failed_wait,
                                   name=self.name, state='OPEN' if state else 'CLOSE')
            return False
        log.info('Done!')
        self.check()
        return True


class WaterLevelSensor(SwitchSensor):
    notification_water_level_low = Notification(
        'water level low',
        Notification.WARN,
        'Water level below {name} level'
    )

    def __init__(self, coop, name, port):
        self.notifications = [
            self.notification_water_level_low
        ]
        super(WaterLevelSensor, self).__init__(coop, name, port)

    def check(self):
        state = super(WaterLevelSensor, self).check()
        if not state:
            self.send_notification(self.notification_water_level_low, name=self.name)
        else:
            self.clear_notification(self.notification_water_level_low)
        return state


class AmbientTempHumiSensor(Sensor):
    notification_ambient_temp_high = Notification(
        'ambient temp high',
        Notification.WARN,
        'Ambient temperature {temp:.1f} is higher than {max:.1f} maximum!'
    )
    notification_ambient_temp_low = Notification(
        'ambient temp low',
        Notification.WARN,
        'Ambient temperature {temp:.1f} is lower than {min:.1f} minimum!'
    )
    notification_ambient_humi_high = Notification(
        'ambient humi high',
        Notification.WARN,
        'Ambient humidity {humi:.1f} is higher than {max:.1f} maximum!'
    )
    notification_ambient_humi_low = Notification(
        'ambient humi low',
        Notification.WARN,
        'Ambient humidity {humi:.1f} is lower than {min:.1f} minimum!'
    )

    def __init__(self, coop, name, sensor, port, alert_temp, alert_humi):
        self.notifications = [
            self.notification_ambient_temp_high,
            self.notification_ambient_temp_low,
            self.notification_ambient_humi_high,
            self.notification_ambient_humi_low,
        ]
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
            self.clear_notification(self.notification_ambient_temp_high)
            self.send_notification(self.notification_ambient_temp_low, temp=temp, min=self.alert_temp[0])
        elif temp > self.alert_temp[1]:
            self.clear_notification(self.notification_ambient_temp_low)
            self.send_notification(self.notification_ambient_temp_high, temp=temp, max=self.alert_temp[1])
        else:
            self.clear_notification(self.notification_ambient_temp_high)
            self.clear_notification(self.notification_ambient_temp_low)

    def check_alert_humi(self, humi):
        if humi < self.alert_humi[0]:
            self.clear_notification(self.notification_ambient_humi_high)
            self.send_notification(self.notification_ambient_humi_low, humi=humi, min=self.alert_humi[0])
        elif humi > self.alert_humi[1]:
            self.clear_notification(self.notification_ambient_humi_low)
            self.send_notification(self.notification_ambient_humi_high, humi=humi, max=self.alert_humi[1])
        else:
            self.clear_notification(self.notification_ambient_humi_high)
            self.clear_notification(self.notification_ambient_humi_low)

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
