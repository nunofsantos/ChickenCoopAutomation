import logging

import RPi.GPIO as GPIO


log = logging.getLogger(__name__)


class RGBLED(object):
    colors = {
        'red': (1,0,0),
        'green': (0, 1, 0),
        'blue': (0, 0, 1),
        'white': (1, 1, 1),
        'off': (0, 0, 0),
    }

    def __init__(self, coop, name, ports, initial_state):
        self.coop = coop
        self.name = name
        self.ports = ports
        self._initial_state = initial_state
        self._state = initial_state
        GPIO.setmode(GPIO.BCM)
        for i in range(0, len(self.ports)):
            GPIO.setup(ports[i], GPIO.OUT,initial=self.colors[initial_state][i])

    def on(self, color):
        if color not in self.colors:
            log.error('Invalid color "{}" for {}'.format(color, self.name))
            self.off()
        else:
            for i in range(0, len(self.ports)):
                GPIO.output(self.ports[i], self.colors[color][i])
                self._state = color
                log.info('{} set to {}'.format(self.name, color))

    def off(self):
        self.on('off')

    def reset(self):
        self.on(self._initial_state)

    @property
    def state(self):
        return self._state
