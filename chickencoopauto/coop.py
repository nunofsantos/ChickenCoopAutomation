import ConfigParser
import logging
import smtplib
from threading import Thread
from time import sleep

import Adafruit_DHT as DHT  # noqa: N814
import RPi.GPIO as GPIO
import web

import led
from notifications import Notification
import relays
import sensors
import utils


log = logging.getLogger(__name__)


class Coop(Thread, utils.Singleton):
    def __init__(self):
        self.initialized = False
        Thread.__init__(self)
        utils.Singleton.__init__(self)
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        self.config = self._read_config()
        self.render = web.template.render('templates')

    @staticmethod
    def _read_config():
        parser = ConfigParser.ConfigParser()
        parser.read('config.ini')

        authentication_options = {
            'USERNAME': parser.get('Authentication', 'USERNAME'),
            'PASSWORD': parser.get('Authentication', 'PASSWORD'),
        }

        main_options = {
            'CHECK_FREQUENCY': parser.getint('Main', 'CHECK_FREQUENCY'),
            'LAT': parser.getfloat('Main', 'LAT'),
            'LON': parser.getfloat('Main', 'LON'),
        }

        status_led_options = {
            'PORT_R': parser.getint('StatusLED', 'PORT_R'),
            'PORT_G': parser.getint('StatusLED', 'PORT_G'),
            'PORT_B': parser.getint('StatusLED', 'PORT_B'),
        }

        ambient_options = {
            'TEMP_RANGE': [
                parser.getfloat('AmbientTempHumi', 'TEMP_MIN_ERROR'),
                parser.getfloat('AmbientTempHumi', 'TEMP_MIN'),
                parser.getfloat('AmbientTempHumi', 'TEMP_MAX'),
                parser.getfloat('AmbientTempHumi', 'TEMP_MAX_ERROR'),
            ],
            'HUMI_RANGE': [
                parser.getfloat('AmbientTempHumi', 'HUMI_MIN'),
                parser.getfloat('AmbientTempHumi', 'HUMI_MAX'),
            ],
            'TEMP_HUMI_CACHE': parser.getint('AmbientTempHumi', 'TEMP_HUMI_CACHE'),
            'SENSOR_PORT': parser.getint('AmbientTempHumi', 'SENSOR_PORT'),
            'TEMP_FAN': parser.getfloat('AmbientTempHumi', 'TEMP_FAN'),
            'FAN_PORT': parser.getint('AmbientTempHumi', 'FAN_PORT'),
            'TEMP_HEATER': parser.getfloat('AmbientTempHumi', 'TEMP_HEATER'),
            'HEATER_PORT': parser.getint('AmbientTempHumi', 'HEATER_PORT'),
        }

        light_options = {
            'PORT': parser.getint('Light', 'PORT'),
        }

        water_options = {
            'HEATER_PORT': parser.getint('Water', 'HEATER_PORT'),
            'HEATER_TEMP_RANGE': [
                parser.getfloat('Water', 'HEATER_TEMP_LOW_ERROR'),
                parser.getfloat('Water', 'HEATER_TEMP_ON'),
                parser.getfloat('Water', 'HEATER_TEMP_OFF'),
                parser.getfloat('Water', 'HEATER_TEMP_HIGH_ERROR'),
            ],
            'SENSOR_LEVEL_TOP_PORT': parser.getint('Water', 'SENSOR_LEVEL_TOP_PORT'),
            'SENSOR_LEVEL_BOTTOM_PORT': parser.getint('Water', 'SENSOR_LEVEL_BOTTOM_PORT'),
        }

        door_options = {
            'PORT_1': parser.getint('Door', 'PORT_1'),
            'PORT_2': parser.getint('Door', 'PORT_2'),
            'OPEN_SENSOR_PORT': parser.getint('Door', 'OPEN_SENSOR_PORT'),
            'CLOSED_SENSOR_PORT': parser.getint('Door', 'CLOSED_SENSOR_PORT'),
            'SENSOR_TIMEOUT': parser.getint('Door', 'SENSOR_TIMEOUT'),
            'EXTRA_MIN_SUNRISE': parser.getint('Door', 'EXTRA_MIN_SUNRISE'),
            'EXTRA_MIN_SUNSET': parser.getint('Door', 'EXTRA_MIN_SUNSET'),
        }

        other_options = {
            'UNUSED_PORT_1': parser.getint('Other', 'UNUSED_PORT_1'),
            'UNUSED_PORT_2': parser.getint('Other', 'UNUSED_PORT_2'),
        }

        notifications_options = {
            'LOG': parser.getboolean('Notifications', 'LOG'),
            'LOG_THRESHOLD': parser.get('Notifications', 'LOG_THRESHOLD'),
            'EMAIL': parser.getboolean('Notifications', 'EMAIL'),
            'EMAIL_THRESHOLD': parser.get('Notifications', 'EMAIL_THRESHOLD'),
            'EMAIL_FROM': parser.get('Notifications', 'EMAIL_FROM'),
            'EMAIL_PASSWORD': parser.get('Notifications', 'EMAIL_PASSWORD'),
            'EMAILS_TO': parser.get('Notifications', 'EMAILS_TO'),
            'SMS': parser.getboolean('Notifications', 'SMS'),
            'SMS_THRESHOLD': parser.get('Notifications', 'SMS_THRESHOLD'),
            'SMS_TO': parser.get('Notifications', 'SMS_TO'),
        }

        config = {
            'Authentication': authentication_options,
            'Main': main_options,
            'StatusLED': status_led_options,
            'AmbientTempHumi': ambient_options,
            'Light': light_options,
            'Water': water_options,
            'Door': door_options,
            'Other': other_options,
            'Notifications': notifications_options,
        }

        return config

    def initialize_sensors_relays(self):
        self.sunset_sunrise_sensor = sensors.SunriseSunsetSensor(
            self,
            'Sunrise/Sunset Sensor',
            self.config['Main']['LAT'],
            self.config['Main']['LON'],
            extra_min_sunrise=self.config['Door']['EXTRA_MIN_SUNRISE'],
            extra_min_sunset=self.config['Door']['EXTRA_MIN_SUNSET']
        )

        self.ambient_temp_humi_sensor = sensors.AmbientTempHumiSensor(
            self,
            'Ambient Temp/Humi Sensor',
            DHT.DHT22,
            self.config['AmbientTempHumi']['SENSOR_PORT'],
            self.config['AmbientTempHumi']['TEMP_RANGE'],
            self.config['AmbientTempHumi']['HUMI_RANGE'],
            self.config['AmbientTempHumi']['TEMP_HUMI_CACHE']
        )

        self.status_led = led.RGBLED(
            self,
            'Status LED',
            (self.config['StatusLED']['PORT_R'],
             self.config['StatusLED']['PORT_G'],
             self.config['StatusLED']['PORT_B'])
        )

        self.relay_module = {
            1: relays.Relay(self, 1, 'Water Heater Relay', self.config['Water']['HEATER_PORT'], 'off'),
            2: relays.Relay(self, 2, 'Light Relay', self.config['Light']['PORT'], 'off'),
            3: relays.Relay(self, 3, 'Door Relay 1', self.config['Door']['PORT_1'], 'off'),
            4: relays.Relay(self, 4, 'Door Relay 2', self.config['Door']['PORT_2'], 'off'),
            5: relays.Relay(self, 5, 'Fan Relay', self.config['AmbientTempHumi']['FAN_PORT'], 'off'),
            6: relays.Relay(self, 6, 'Heater Relay', self.config['AmbientTempHumi']['HEATER_PORT'], 'off'),
            7: relays.Relay(self, 7, 'Unused Relay 1', self.config['Other']['UNUSED_PORT_1'], 'off'),
            8: relays.Relay(self, 8, 'Unused Relay 2', self.config['Other']['UNUSED_PORT_2'], 'off'),
        }

        self.water_heater_relay = self.relay_module[1]
        self.water_heater = relays.WaterHeater(
            self,
            'Water heater',
            self.water_heater_relay,
            self.config['Water']['HEATER_TEMP_RANGE'][1:3]
        )

        self.water_temp_sensor = sensors.WaterTempSensor(
            self,
            'Water Temp Sensor',
            self.config['Water']['HEATER_TEMP_RANGE'],
        )

        self.water_level_dual_sensor = sensors.HalfEmptyWaterLevelsSensor(
            self,
            'Water Level Dual Sensor HalfEmpty',
            self.config['Water']['SENSOR_LEVEL_TOP_PORT'],
            self.config['Water']['SENSOR_LEVEL_BOTTOM_PORT']
        )

        self.light_relay = self.relay_module[2]
        self.light = relays.Light(
            self,
            'Light',
            self.light_relay
        )

        self.door_dual_sensor = sensors.DoorDualSensor(
            self,
            'Door Dual Sensor',
            self.config['Door']['OPEN_SENSOR_PORT'],
            self.config['Door']['CLOSED_SENSOR_PORT'],
            timeout=self.config['Door']['SENSOR_TIMEOUT']
        )

        self.door_relays = [
            self.relay_module[3],
            self.relay_module[4]
        ]
        self.door = relays.Door(
            self,
            'Door',
            self.door_relays
        )

        self.fan_relay = self.relay_module[5]
        self.fan = relays.Fan(
            self,
            'Fan',
            self.fan_relay,
            (self.config['AmbientTempHumi']['TEMP_FAN'] - 5.0, self.config['AmbientTempHumi']['TEMP_FAN'])
        )

        self.heater_relay = self.relay_module[6]
        self.heater = relays.Heater(
            self,
            'Heater',
            self.heater_relay,
            (self.config['AmbientTempHumi']['TEMP_HEATER'], self.config['AmbientTempHumi']['TEMP_HEATER'] + 5.0)
        )

        self.rebooting = False
        self.initialized = True

    def check(self):
        self.sunset_sunrise_sensor.read_and_check()
        self.water_temp_sensor.read_and_check()
        self.water_level_dual_sensor.read_and_check()
        water_empty = self.water_level_dual_sensor.state == 'empty' or \
                      self.water_level_dual_sensor.state == 'invalid'
        self.water_heater.check(temp=self.water_temp_sensor.temp, water_empty=water_empty)
        self.door_dual_sensor.read_and_check()
        self.door.check(switches=self.door_dual_sensor,
                        sunrise_sunset=self.sunset_sunrise_sensor)
        self.light.check(sunrise_sunset=self.sunset_sunrise_sensor)
        self.fan.check(temp=self.ambient_temp_humi_sensor.temp)
        self.heater.check(temp=self.ambient_temp_humi_sensor.temp)
        self.status_led.on(self._convert_status_to_color(self.status))

    def run(self):
        if not self.initialized:
            raise Exception('Coop sensors and relays not initialized!')

        while True:
            # this takes a while, so don't do it inside coop.check()
            self.ambient_temp_humi_sensor.read_and_check()
            self.check()
            sleep(self.config['Main']['CHECK_FREQUENCY'])

    def shutdown(self):
        log.info('Resetting relays...')
        for relay in self.relay_module.values():
            relay.reset()
        self.status_led.reset()
        # GPIO.cleanup()

    @staticmethod
    def max_status_level(status_list):
        if 'ERROR' in status_list:
            return 'ERROR'
        elif 'WARN' in status_list:
            return 'WARN'
        elif 'MANUAL' in status_list:
            return 'MANUAL'
        else:
            return 'OK'

    @property
    def status(self):
        components_status = []

        for component in [self.sunset_sunrise_sensor,
                          self.ambient_temp_humi_sensor,
                          self.water_temp_sensor,
                          self.water_level_dual_sensor,
                          self.water_heater,
                          self.door_dual_sensor,
                          self.door,
                          self.light,
                          self.fan]:
            components_status.append(component.status())

        return self.max_status_level(components_status)

    @staticmethod
    def _convert_status_to_color(status):
        return 'red' if status == 'ERROR' else \
               'blue' if status == 'WARN' else \
               'white' if status == 'MANUAL' else \
               'green'

    def notifier_callback(self, notification):
        severity = notification.severity
        if self.config['Notifications']['LOG']:
            if Notification.severity_levels[severity] >= \
                    Notification.severity_levels[self.config['Notifications']['LOG_THRESHOLD']]:
                self.log_callback(notification)
        if self.config['Notifications']['EMAIL']:
            if Notification.severity_levels[severity] >= \
                    Notification.severity_levels[self.config['Notifications']['EMAIL_THRESHOLD']]:
                kwargs = {
                    'gmail_credentials': {
                        'email': self.config['Notifications']['EMAIL_FROM'],
                        'password': self.config['Notifications']['EMAIL_PASSWORD'],
                    },
                    'emails_to': self.config['Notifications']['EMAILS_TO'],
                    'message': notification.message
                }
                self.email_callback(**kwargs)
        if self.config['Notifications']['SMS']:
            if Notification.severity_levels[severity] >= \
                    Notification.severity_levels[self.config['Notifications']['SMS_THRESHOLD']]:
                kwargs = {
                    'gmail_credentials': {
                        'email': self.config['Notifications']['EMAIL_FROM'],
                        'password': self.config['Notifications']['EMAIL_PASSWORD'],
                    },
                    'emails_to': self.config['Notifications']['SMS_TO'],
                    'message': notification.message
                }
                self.email_callback(**kwargs)

    @staticmethod
    def email_callback(**kwargs):
        gmail_credentials = kwargs['gmail_credentials']
        emails_to = kwargs['emails_to']
        gmail = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        gmail.ehlo()
        gmail.login(gmail_credentials['email'], gmail_credentials['password'])
        subject = 'Chicken Coop Alert!'
        body = kwargs['message']
        email_text = '''\
From: {email_from}
To: {to}
Subject: {subject}

{body}
'''.format(email_from=gmail_credentials['email'], to=emails_to, subject=subject, body=body)
        gmail.sendmail(gmail_credentials['email'], emails_to.split(','), email_text)
        gmail.quit()

    @staticmethod
    def log_callback(notification):
        log_message = '{}: {}'.format(notification.severity, notification.message)
        if notification.severity == 'INFO':
            log.info(log_message)
        elif notification.severity == 'WARN':
            log.warning(log_message)
        elif notification.severity == 'ERROR':
            log.error(log_message)
