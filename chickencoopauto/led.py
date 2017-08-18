import logging

import RPi.GPIO as GPIO
from transitions import Machine


log = logging.getLogger(__name__)


class RGBLED(Machine):
    colors = {
        'red': (1, 0, 0),
        'green': (0, 1, 0),
        'blue': (0, 0, 1),
        'white': (1, 1, 1),
        'off': (0, 0, 0),
    }

    def __init__(self, coop, name, ports):
        # attributes for transitions
        self.coop = coop
        self.name = name
        self.transition_states = self.colors.keys()
        self.transition_initial = 'off'
        self.transition_transitions = [
            {
                'trigger': 'turn_red',
                'source': '*',
                'dest': 'red',
            },
            {
                'trigger': 'turn_green',
                'source': '*',
                'dest': 'green',
            },
            {
                'trigger': 'turn_blue',
                'source': '*',
                'dest': 'blue',
            },
            {
                'trigger': 'turn_white',
                'source': '*',
                'dest': 'white',
            },
            {
                'trigger': 'turn_off',
                'source': '*',
                'dest': 'off',
            },
        ]

        super(RGBLED, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions
        )

        # other attributes
        self.ports = ports

        GPIO.setmode(GPIO.BCM)
        for i in range(0, len(self.ports)):
            GPIO.setup(ports[i], GPIO.OUT, initial=self.colors[self.transition_initial][i])

    def on(self, color):
        if color not in self.colors:
            log.error('Invalid color "{}" for {}'.format(color, self.name))
            self.off()
        else:
            for i in range(0, len(self.ports)):
                GPIO.output(self.ports[i], self.colors[color][i])
            self.set_state(color)
            log.info('{} set to {}'.format(self.name, color))

    def off(self):
        self.on('off')

    def reset(self):
        self.on(self.transition_initial)
