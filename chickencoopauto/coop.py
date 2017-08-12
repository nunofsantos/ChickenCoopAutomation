import ConfigParser
import logging
import os.path
import smtplib
from threading import Thread
from time import sleep

import Adafruit_DHT as DHT  # noqa: N814
import RPi.GPIO as GPIO

import led
import notifications
import relays
import sensors
import utils


log = logging.getLogger(__name__)


class Coop(Thread):
    def __init__(self, config_ini='config.ini'):
        self.notifier_manager = notifications.NotifierManager()
        super(Coop, self).__init__()
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        self.config = self._read_config(config_ini)
        self.ON = self.config['Main']['ON']
        self.OFF = self.config['Main']['OFF']
        self._create_objects()

    @staticmethod
    def _read_config(config_ini):
        if not os.path.isfile(config_ini):
            raise IOError
        parser = ConfigParser.ConfigParser()
        parser.read(config_ini)

        main_options = {
            'ON': parser.getboolean('Main', 'ON'),
            'OFF': parser.getboolean('Main', 'OFF'),
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
                parser.getfloat('AmbientTempHumi', 'TEMP_MIN'),
                parser.getfloat('AmbientTempHumi', 'TEMP_MAX')
            ],
            'HUMI_RANGE': [
                parser.getfloat('AmbientTempHumi', 'HUMI_MIN'),
                parser.getfloat('AmbientTempHumi', 'HUMI_MAX')
            ],
            'SENSOR_PORT': parser.getint('AmbientTempHumi', 'SENSOR_PORT'),
        }

        light_options = {
            'PORT': parser.getint('Light', 'PORT'),
        }

        water_options = {
            'HEATER_PORT': parser.getint('Water', 'HEATER_PORT'),
            'HEATER_TEMP_RANGE': [
                parser.getfloat('Water', 'HEATER_TEMP_ON'),
                parser.getfloat('Water', 'HEATER_TEMP_OFF')
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

        notifications_options = {
            'LOG': parser.getboolean('Notifications', 'LOG'),
            'LOG_THRESHOLD': parser.get('Notifications', 'LOG_THRESHOLD'),
            'EMAIL': parser.getboolean('Notifications', 'EMAIL'),
            'EMAIL_THRESHOLD': parser.get('Notifications', 'EMAIL_THRESHOLD'),
            'EMAIL_FROM': parser.get('Notifications', 'EMAIL_FROM'),
            'EMAIL_PASSWORD': parser.get('Notifications', 'EMAIL_PASSWORD'),
            'EMAILS_TO': parser.get('Notifications', 'EMAILS_TO'),
        }

        config = {
            'Main': main_options,
            'StatusLED': status_led_options,
            'AmbientTempHumi': ambient_options,
            'Light': light_options,
            'Water': water_options,
            'Door': door_options,
            'Notifications': notifications_options,
        }

        return config

    def _create_objects(self):
        self.sunset_sunrise = utils.SunriseSunset(
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
            self.config['AmbientTempHumi']['HUMI_RANGE']
        )

        self.status_led = led.RGBLED(
            self,
            'Status LED',
            (self.config['StatusLED']['PORT_R'],
             self.config['StatusLED']['PORT_G'],
             self.config['StatusLED']['PORT_B']),
            'off'
        )

        self.relay_module = {
            1: relays.Relay(self, 1, 'Water Heater Relay', self.config['Water']['HEATER_PORT'], self.OFF),
            2: relays.Relay(self, 2, 'Light Relay', self.config['Light']['PORT'], self.OFF),
            3: relays.Relay(self, 3, 'Door Relay 1', self.config['Door']['PORT_1'], self.OFF),
            4: relays.Relay(self, 4, 'Door Relay 2', self.config['Door']['PORT_2'], self.OFF),
        }

        self.water_heater_relay = self.relay_module[1]
        self.water_heater = relays.WaterHeater(
            self,
            'Water heater',
            self.water_heater_relay,
            self.config['Water']['HEATER_TEMP_RANGE']
        )
        self.water_temp_sensor = sensors.WaterTempSensor(
            self,
            'Water Temp Sensor',
            self.water_heater)
        self.water_level_dual_sensor = sensors.HalfEmptyWaterLevelSensors(
            self,
            'Water Level Dual Sensor HalfEmpty',
            self.config['Water']['SENSOR_LEVEL_TOP_PORT'],
            self.config['Water']['SENSOR_LEVEL_BOTTOM_PORT']
        )

        self.light_relay = self.relay_module[2]
        self.light = relays.Light(
            self,
            'Light',
            self.light_relay,
            self.sunset_sunrise
        )

        self.door_open_sensor = sensors.SwitchSensor(
            self,
            'Door Open Sensor',
            self.config['Door']['OPEN_SENSOR_PORT'],
            timeout=self.config['Door']['SENSOR_TIMEOUT']
        )
        self.door_closed_sensor = sensors.SwitchSensor(
            self,
            'Door Closed Sensor',
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
            self.door_relays,
            self.sunset_sunrise,
            self.door_open_sensor,
            self.door_closed_sensor,
            manual_mode=False
        )

    def run(self):
        while True:
            self.ambient_temp_humi_sensor.check()
            self.water_temp_sensor.check()
            self.water_level_dual_sensor.check()
            self.light.check()
            self.door.check()
            self.status_led.on(self._convert_status_to_color(self.status()))

            sleep(self.config['Main']['CHECK_FREQUENCY'])

    def shutdown(self):
        log.info('Resetting relays...')
        for relay in self.relay_module.values():
            relay.reset()
        self.status_led.reset()
        GPIO.cleanup()

    def status(self):
        s = self.notifier_manager.status()
        log.info('Coop status: {}'.format(notifications.Notification.severity_text(s)))
        return s

    @staticmethod
    def _convert_status_to_color(status):
        return 'red' if status == notifications.Notification.ERROR else \
               'white' if status == notifications.Notification.MANUAL else \
               'blue' if status == notifications.Notification.WARN else \
               'green'

    def notifier_callback(self, **kwargs):
        severity = kwargs['notification'].severity
        if self.config['Notifications']['LOG']:
            if severity >= notifications.Notification.severity_levels[self.config['Notifications']['LOG_THRESHOLD']]:
                self.log_callback(**kwargs)
        if self.config['Notifications']['EMAIL']:
            if severity >= notifications.Notification.severity_levels[self.config['Notifications']['EMAIL_THRESHOLD']]:
                kwargs['gmail_credentials'] = {
                    'email': self.config['Notifications']['EMAIL_FROM'],
                    'password': self.config['Notifications']['EMAIL_PASSWORD'],
                }
                kwargs['emails_to'] = self.config['Notifications']['EMAILS_TO']
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
    def log_callback(**kwargs):
        notification = kwargs['notification']
        log_message = '[{}] {}: {}'.format(notifications.Notification.severity_text(notification.severity),
                                           notification.type.__name__,
                                           kwargs['message'])
        if notification.severity == notification.INFO:
            log.info(log_message)
        elif notification.severity == notification.WARN:
            log.warning(log_message)
        elif notification.severity == notification.ERROR:
            log.error(log_message)
