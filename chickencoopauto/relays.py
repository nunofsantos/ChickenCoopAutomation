import logging
from time import sleep

import RPi.GPIO as GPIO
from transitions import Machine

from notifications import Notification


log = logging.getLogger(__name__)


class Relay(Machine):
    def __init__(self, coop, channel, name, port, initial_state):
        self.coop = coop
        self.name = name
        self.channel = channel
        self.port = port
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(port, GPIO.OUT, initial=(initial_state == 'on'))

        self.transition_states = [
            'on',
            'off',
        ]
        self.transition_initial = initial_state
        self.transition_transitions = [
            {
                'trigger': 'turn_on',
                'source': 'off',
                'dest': 'on',
                'after': self.notify_on
            },
            {
                'trigger': 'turn_off',
                'source': 'on',
                'dest': 'off',
                'after': self.notify_off
            },
        ]

        super(Relay, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions,
            after_state_change=self.set_relay,
            send_event=True
        )

    def set_relay(self, event):
        GPIO.output(self.port, self.state == 'on')

    def reset(self):
        self.set_state(self.transition_initial)
        self.set_relay(None)

    def notify_on(self, event):
        pass

    def notify_off(self, event):
        pass


class SingleRelayOperatedObject(Machine):
    def __init__(self, coop, name, relay):
        self.coop = coop
        self.name = name
        self.relay = relay

        self.transition_states = [
            'auto',
            'auto-on',
            'auto-off',
            'manual',
            'manual-on',
            'manual-off',
        ]
        self.transition_initial = 'auto-off'
        self.transition_transitions = [
            {
                'trigger': 'set_auto',
                'source': [
                    'manual',
                    'manual-on',
                    'manual-off',
                ],
                'dest': 'auto',
                'after': self.notify_auto
            },
            {
                'trigger': 'check',
                'source': 'auto',
                'dest': 'auto-on',
                'conditions': self.is_on,
            },
            {
                'trigger': 'check',
                'source': 'auto',
                'dest': 'auto-off',
                'conditions': self.is_off,
            },
            {
                'trigger': 'check',
                'source': 'auto-off',
                'dest': 'auto-on',
                'conditions': [self.is_off, self.is_auto_go_on],
                'before': self.turn_on,
            },
            {
                'trigger': 'check',
                'source': 'auto-on',
                'dest': 'auto-off',
                'conditions': [self.is_on, self.is_auto_go_off],
                'before': self.turn_off,
            },
            {
                'trigger': 'set_manual',
                'source': [
                    'auto',
                    'auto-on',
                    'auto-off',
                ],
                'dest': 'manual',
                'after': self.notify_manual
            },
            {
                'trigger': 'check',
                'source': ['manual', 'manual-off'],
                'dest': 'manual-on',
                'conditions': self.is_on,
            },
            {
                'trigger': 'check',
                'source': ['manual', 'manual-on'],
                'dest': 'manual-off',
                'conditions': self.is_off,
            },
        ]
        super(SingleRelayOperatedObject, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions,
            send_event=True
        )

    def is_auto_go_on(self, event=None):
        # must be implemented in subclass
        pass

    def is_auto_go_off(self, event=None):
        # must be implemented in subclass
        pass

    def is_on(self, event=None):
        return self.relay.state == 'on'

    def is_off(self, event=None):
        return self.relay.state == 'off'

    def is_auto_mode(self):
        return 'auto' in self.state

    def is_manual_mode(self):
        return 'manual' in self.state

    def notify_auto(self, event=None):
        self.coop.notifier_callback(
            Notification('INFO',
                         '{name} is back to automatic mode',
                         name=self.name)
        )

    def notify_manual(self, event):
        self.coop.notifier_callback(
            Notification('MANUAL',
                         '{name} is in manual mode',
                         name=self.name)
        )

    def turn_on(self, event=None):
        self.relay.turn_on()
        extra_info = ''
        if event and 'temp' in event.kwargs:
            temp = event.kwargs.get('temp')
            extra_info = ' (temp={:.1f})'.format(temp) if temp else '???'
        self.coop.notifier_callback(
            Notification('INFO',
                         '{name} turned on{auto}{extra_info}',
                         name=self.name,
                         auto=('' if self.is_manual_mode() else ' automatically'),
                         extra_info=extra_info)
        )

    def turn_off(self, event=None):
        self.relay.turn_off()
        extra_info = ''
        if event and 'temp' in event.kwargs:
            temp = event.kwargs.get('temp')
            extra_info = ' (temp={:.1f})'.format(temp) if temp else '???'
        self.coop.notifier_callback(
            Notification('INFO',
                         '{name} turned off{auto}{extra_info}',
                         name=self.name,
                         auto=('' if self.is_manual_mode() else ' automatically'),
                         extra_info=extra_info)
        )

    def status(self):
        if 'manual' in self.state:
            return 'MANUAL'
        else:
            return 'OK'


class WaterHeater(SingleRelayOperatedObject):
    def __init__(self, coop, name, relay, temp_range):
        self.temp_range = temp_range
        self.temp = None
        super(WaterHeater, self).__init__(
            coop,
            name,
            relay
        )

    def is_auto_go_on(self, event=None):
        temp = event.kwargs.get('temp', None)
        water_empty = event.kwargs.get('water_empty', None)
        return (not water_empty and
                temp is not None and
                temp < self.temp_range[0])

    def is_auto_go_off(self, event=None):
        temp = event.kwargs.get('temp', None)
        water_empty = event.kwargs.get('water_empty', None)
        return (water_empty or
                temp is None or
                temp > self.temp_range[1])

    def set_temp_range(self, temp_range):
        self.temp_range = temp_range


class Heater(SingleRelayOperatedObject):
    def __init__(self, coop, name, relay, temp_range):
        self.temp_range = temp_range
        self.temp = None
        super(Heater, self).__init__(
            coop,
            name,
            relay
        )

    def is_auto_go_on(self, event=None):
        temp = event.kwargs.get('temp', None)
        return (temp is not None and
                temp < self.temp_range[0])

    def is_auto_go_off(self, event=None):
        temp = event.kwargs.get('temp', None)
        return (temp is None or
                temp > self.temp_range[1])

    def set_temp_range(self, temp_range):
        self.temp_range = temp_range


class Fan(SingleRelayOperatedObject):
    def __init__(self, coop, name, relay, temp_range):
        self.temp_range = temp_range
        self.temp = None
        super(Fan, self).__init__(
            coop,
            name,
            relay
        )

    def is_auto_go_on(self, event=None):
        temp = event.kwargs.get('temp', None)
        return (temp is not None and
                temp > self.temp_range[1])

    def is_auto_go_off(self, event=None):
        temp = event.kwargs.get('temp', None)
        return (temp is None or
                temp < self.temp_range[0])

    def set_temp_range(self, temp_range):
        self.temp_range = temp_range


class Light(SingleRelayOperatedObject):
    def __init__(self, coop, name, relay):
        super(Light, self).__init__(
            coop,
            name,
            relay
        )

    def is_auto_go_on(self, event=None):
        sunrise_sunset = event.kwargs.get('sunrise_sunset', None)
        # return sunrise_sunset is not None and sunrise_sunset.go_night()
        return False

    def is_auto_go_off(self, event=None):
        sunrise_sunset = event.kwargs.get('sunrise_sunset', None)
        # return sunrise_sunset is not None and sunrise_sunset.go_day()
        return True


class MultiRelayOperatedObject(Machine):
    def __init__(self, coop, name, relays,
                 t_states=None, t_initial=None, t_transitions=None):
        self.coop = coop
        self.name = name
        self.relays = relays
        self.transition_states = t_states
        self.transition_initial = t_initial
        self.transition_transitions = t_transitions
        super(MultiRelayOperatedObject, self).__init__(
            self,
            name=name,
            states=self.transition_states,
            initial=self.transition_initial,
            transitions=self.transition_transitions,
            send_event=True
        )

    def is_auto_mode(self):
        return 'auto' in self.state

    def is_manual_mode(self):
        return 'manual' in self.state

    def notify_auto(self, event):
        self.coop.notifier_callback(
            Notification('INFO',
                         '{name} is back to automatic mode',
                         name=self.name)
        )

    def notify_manual(self, event):
        self.coop.notifier_callback(
            Notification('MANUAL',
                         '{name} is on manual mode',
                         name=self.name)
        )

    def turn_on(self, relay_num):
        self.relays[relay_num].turn_on()

    def turn_off(self, relay_num):
        self.relays[relay_num].turn_off()

    def status(self):
        pass


class Door(MultiRelayOperatedObject):
    def __init__(self, coop, name, relays, manual_mode=False):
        self.transition_states = [
            'auto',
            'auto-open-day',
            'auto-closed-night',
            'manual',
            'manual-open-day',
            'manual-closed-day',
            'manual-open-night',
            'manual-closed-night',
            'manual-invalid'
        ]
        self.transition_initial = 'manual' if manual_mode else 'auto'
        self.transition_transitions = [
            {
                'trigger': 'set_auto',
                'source': [
                    'manual',
                    'manual-open-day',
                    'manual-closed-day',
                    'manual-open-night',
                    'manual-closed-night',
                    'manual-invalid',
                ],
                'dest': 'auto',
                'conditions': self.is_not_invalid,
                'after': self.notify_auto,
            },
            {
                'trigger': 'set_auto',
                'source': [
                    'auto',
                    'auto-open-day',
                    'auto-closed-night'
                ],
                'dest': '=',
                'conditions': self.is_not_invalid,
            },
            {
                'trigger': 'check',
                'source': 'auto',
                'dest': 'auto-open-day',
                'conditions': self.is_day,
                'after': self.open,
            },
            {
                'trigger': 'check',
                'source': 'auto',
                'dest': 'auto-closed-night',
                'conditions': self.is_night,
                'after': self.close,
            },
            {
                'trigger': 'check',
                'source': 'auto-closed-night',
                'dest': 'auto-open-day',
                'conditions': [self.is_day, self.is_closed],
                'after': self.open
            },
            {
                'trigger': 'check',
                'source': 'auto-open-day',
                'dest': 'auto-closed-night',
                'conditions': [self.is_night, self.is_open],
                'after': self.close
            },
            {
                'trigger': 'set_manual',
                'source': [
                    'auto',
                    'auto-open-day',
                    'auto-closed-night',
                ],
                'dest': 'manual',
                'after': self.notify_manual
            },
            {
                'trigger': 'set_manual',
                'source': [
                    'manual',
                    'manual-open-day',
                    'manual-closed-day',
                    'manual-open-night',
                    'manual-closed-night',
                    'manual-invalid',
                ],
                'dest': '=',
            },
            {
                'trigger': 'check',
                'source': [
                    'auto-open-day',
                    'auto-closed-night',
                    'manual',
                    'manual-open-day',
                    'manual-open-night',
                    'manual-closed-night',
                    'manual-invalid',
                ],
                'dest': 'manual-closed-day',
                'conditions': [self.is_day, self.is_closed],
                'after': self.notify_manual_close
            },
            {
                'trigger': 'check',
                'source': [
                    'manual',
                    'manual-open-day',
                    'manual-open-night',
                    'manual-closed-day',
                    'manual-invalid',
                ],
                'dest': 'manual-closed-night',
                'conditions': [self.is_night, self.is_closed],
                'after': self.notify_manual_close
            },
            {
                'trigger': 'check',
                'source': [
                    'manual',
                    'manual-open-night',
                    'manual-closed-day',
                    'manual-closed-night',
                    'manual-invalid',
                ],
                'dest': 'manual-open-day',
                'conditions': [self.is_day, self.is_open],
                'after': self.notify_manual_open
            },
            {
                'trigger': 'check',
                'source': [
                    'auto-open-day',
                    'auto-closed-night',
                    'manual',
                    'manual-open-day',
                    'manual-closed-day',
                    'manual-closed-night',
                    'manual-invalid',
                ],
                'dest': 'manual-open-night',
                'conditions': [self.is_night, self.is_open],
                'after': self.notify_manual_open
            },
            {
                'trigger': 'check',
                'source': [
                    'auto-open-day',
                    'auto-closed-night',
                ],
                'dest': 'manual-invalid',
                'conditions': self.is_invalid,
            },
            {
                'trigger': 'check',
                'source': [
                    'manual',
                    'manual-open-day',
                    'manual-closed-day',
                    'manual-open-night',
                    'manual-closed-night',
                ],
                'dest': 'manual-invalid',
                'conditions': self.is_invalid,
                'after': self.notify_manual_invalid
            },
        ]
        super(Door, self).__init__(
            coop,
            name=name,
            relays=relays,
            t_states=self.transition_states,
            t_initial=self.transition_initial,
            t_transitions=self.transition_transitions
        )

    def open(self, event):
        switches = event.kwargs['switches']
        if switches.state == 'open':
            log.info('{} was already open'.format(self.name))
            return
        self.turn_on(1)
        opened = switches.top_sensor.wait_on()
        self.turn_off(1)
        if not opened:
            switches.top_sensor.failed_to_wait()
            self.coop.notifier_callback(
                Notification('ERROR',
                             '{name} failed to open{at}',
                             name=self.name,
                             at=(' at sunrise' if self.is_auto_mode() else ''))
            )
            self.set_manual()
        else:
            self.coop.notifier_callback(
                Notification('INFO',
                             '{name} opened{at}',
                             name=self.name,
                             at=(' at sunrise' if self.is_auto_mode() else ''))
            )

    def close(self, event):
        switches = event.kwargs['switches']
        if switches.state == 'closed':
            log.info('{} was already closed'.format(self.name))
            return
        self.turn_on(0)
        closed = switches.bottom_sensor.wait_on()
        # delay to compensate for switches sometimes trigerring too soon
        sleep(0.1)
        self.turn_off(0)
        if not closed:
            switches.bottom_sensor.failed_to_wait()
            self.coop.notifier_callback(
                Notification('ERROR',
                             '{name} failed to close{at}',
                             name=self.name,
                             at=(' at sunset' if self.is_auto_mode() else ''))
            )
            self.set_manual()
        else:
            self.coop.notifier_callback(
                Notification('INFO',
                             '{name} closed{at}',
                             name=self.name,
                             at=(' at sunset' if self.is_auto_mode() else ''))
            )

    def is_day(self, event):
        return self.coop.sunset_sunrise_sensor.is_day()

    def is_night(self, event):
        return self.coop.sunset_sunrise_sensor.is_night()

    def is_invalid(self, event):
        return self.coop.door_dual_sensor.is_invalid()

    def is_not_invalid(self, event):
        return not self.is_invalid(event)

    def is_open(self, event):
        return self.coop.door_dual_sensor.is_open()

    def is_closed(self, event):
        return self.coop.door_dual_sensor.is_closed()

    def notify_manual_open(self, event):
        sunrise_sunset = event.kwargs.get('sunrise_sunset')
        self.coop.notifier_callback(
            Notification('WARN',
                         '{name} is in manual mode and is open{at}!',
                         name=self.name,
                         at=(' during the night' if sunrise_sunset and sunrise_sunset.is_night() else ''))
        )

    def notify_manual_close(self, event):
        sunrise_sunset = event.kwargs.get('sunrise_sunset')
        self.coop.notifier_callback(
            Notification('WARN',
                         '{name} is in manual mode and is closed{at}!',
                         name=self.name,
                         at=(' during the day' if sunrise_sunset and sunrise_sunset.is_day() else ''))
        )

    def notify_manual_invalid(self, event):
        self.coop.notifier_callback(
            Notification('WARN',
                         '{name} is in invalid state, set to manual mode',
                         name=self.name)
        )

    def status(self):
        error = False
        warn = False
        manual = False

        if 'manual' in self.state:
            manual = True
        if self.state in ['manual-invalid', 'manual-closed-day', 'manual-open-night']:
            error = True

        if error:
            return 'ERROR'
        elif warn:
            return 'WARN'
        elif manual:
            return 'MANUAL'
        else:
            return 'OK'
