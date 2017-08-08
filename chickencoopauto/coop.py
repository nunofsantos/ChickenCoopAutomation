import ConfigParser
import logging
from threading import Thread
from time import sleep

import Adafruit_DHT as DHT
import RPi.GPIO as GPIO

import relays
import sensors
import utils


log = logging.getLogger(__name__)


class Coop(Thread):
    def __init__(self):
        super(Coop, self).__init__()
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        self.config = self._read_config()
        self.ON = self.config['Main']['ON']
        self.OFF = self.config['Main']['OFF']
        self._create_objects()

    @staticmethod
    def _read_config():
        parser = ConfigParser.ConfigParser()
        parser.read('config.ini')

        main_options = {
            'ON': parser.getboolean('Main', 'ON'),
            'OFF': parser.getboolean('Main', 'OFF'),
            'CHECK_DELAY': parser.getint('Main', 'CHECK_DELAY'),
            'LAT': parser.getfloat('Main', 'LAT'),
            'LON': parser.getfloat('Main', 'LON'),
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

        config = {
            'Main': main_options,
            'AmbientTempHumi': ambient_options,
            'Light': light_options,
            'Water': water_options,
            'Door': door_options,
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

        self.relay_module = {
            1: relays.Relay(self, 1, self.config['Water']['HEATER_PORT'], self.OFF),
            2: relays.Relay(self, 2, self.config['Light']['PORT'], self.OFF),
            3: relays.Relay(self, 3, self.config['Door']['PORT_1'], self.OFF),
            4: relays.Relay(self, 4, self.config['Door']['PORT_2'], self.OFF),
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
        self.water_level_sensor_top = sensors.WaterLevelSensor(
            self,
            'Water Level Sensor Top',
            self.config['Water']['SENSOR_LEVEL_TOP_PORT']
        )
        self.water_level_sensor_bottom = sensors.WaterLevelSensor(
            self,
            'Water Level Sensor Bottom',
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
            # ambient temperature
            self.ambient_temp_humi_sensor.check()

            # water temperature
            self.water_temp_sensor.check()

            # water level
            self.water_level_sensor_top.check()
            self.water_level_sensor_bottom.check()

            # light
            self.light.check()

            #############################
            # door switches
            # self.door_open_sensor.check()
            # self.door_closed_sensor.check()
            #############################

            # door
            self.door.check()

            sleep(self.config['Main']['CHECK_DELAY'])

    def shutdown(self):
        log.info('Resetting relays...')
        for relay in self.relay_module.values():
            relay.reset()
        GPIO.cleanup()
