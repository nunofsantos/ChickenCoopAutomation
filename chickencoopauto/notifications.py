from datetime import datetime
import logging

log = logging.getLogger(__name__)


class Notification(object):
    INFO = 1
    WARN = 5
    MANUAL = 10
    ERROR = 15

    severity_levels = {
        'INFO': INFO,
        'WARN': WARN,
        'MANUAL': MANUAL,
        'ERROR': ERROR,
    }

    def __init__(self, severity, message, clears=(), single=True, auto_clear=False):
        self.severity = severity
        self.message = message
        self.clears = clears
        self.single = single
        self.auto_clear = auto_clear
        self.timestamp = datetime.now()

    def type(self):
        return self.__class__

    @classmethod
    def severity_text(cls, severity):
        for text, number in cls.severity_levels.items():
            if number == severity:
                return text


class SwitchSensorFailedWaitNotification(Notification):
    def __init__(self, name, state):
        super(SwitchSensorFailedWaitNotification, self).__init__(
            Notification.ERROR,
            '{name} FAILED to wait to {state}'.format(name=name, state=state),
            auto_clear=True
        )


class WaterSensorLevelLowNotification(Notification):
    def __init__(self, name):
        super(WaterSensorLevelLowNotification, self).__init__(
            Notification.WARN,
            'Water level below {name} level'.format(name=name)
        )


class WaterSensorInvalidNotification(Notification):
    def __init__(self):
        super(WaterSensorInvalidNotification, self).__init__(
            Notification.ERROR,
            'Water level sensors are in invalid state!'
        )


class AmbientTempHighNotification(Notification):
    def __init__(self, temp, maxi):
        super(AmbientTempHighNotification, self).__init__(
            Notification.WARN,
            'Ambient temperature {temp:.1f} is higher than {maxi:.1f} maximum!'.format(temp=temp, maxi=maxi),
            clears=(AmbientTempLowNotification, )
        )


class AmbientTempLowNotification(Notification):
    def __init__(self, temp, mini):
        super(AmbientTempLowNotification, self).__init__(
            Notification.WARN,
            'Ambient temperature {temp:.1f} is lower than {mini:.1f} minimum!'.format(temp=temp, mini=mini),
            clears=(AmbientTempHighNotification, )
        )


class AmbientHumiHighNotification(Notification):
    def __init__(self, humi, maxi):
        super(AmbientHumiHighNotification, self).__init__(
            Notification.WARN,
            'Ambient humidity {humi:.1f} is higher than {maxi:.1f} maximum!'.format(humi=humi, maxi=maxi),
            clears=(AmbientHumiLowNotification, )
        )


class AmbientHumiLowNotification(Notification):
    def __init__(self, humi, mini):
        super(AmbientHumiLowNotification, self).__init__(
            Notification.WARN,
            'Ambient humidity {humi:.1f} is lower than {mini:.1f} minimum!'.format(humi=humi, mini=mini),
            clears=(AmbientHumiHighNotification, )
        )


class ManualModeNotification(Notification):
    def __init__(self, name):
        super(ManualModeNotification, self).__init__(
            Notification.MANUAL,
            '{name} set to MANUAL mode'.format(name=name),
            clears=(AutomaticModeNotification, )
        )


class AutomaticModeNotification(Notification):
    def __init__(self, name):
        super(AutomaticModeNotification, self).__init__(
            Notification.INFO,
            '{name} set to automatic mode'.format(name=name),
            clears=(ManualModeNotification, ),
            auto_clear=True
        )


class WaterHeaterOnNotification(Notification):
    def __init__(self, temp, mini):
        super(WaterHeaterOnNotification, self).__init__(
            Notification.INFO,
            'Water temp {temp:.1f} is below {mini:.1f} minimum, turning on heater!'.format(temp=temp, mini=mini),
            clears=(WaterHeaterOffNotification, )
        )


class WaterHeaterOffNotification(Notification):
    def __init__(self, temp, maxi):
        super(WaterHeaterOffNotification, self).__init__(
            Notification.INFO,
            'Water temp {temp:.1f} is above {maxi:.1f} maximum, turning off heater.'.format(temp=temp, maxi=maxi),
            clears=(WaterHeaterOnNotification, ),
            auto_clear=True
        )


class WaterHeaterOffEmptyInvalidNotification(Notification):
    def __init__(self):
        super(WaterHeaterOffEmptyInvalidNotification, self).__init__(
            Notification.INFO,
            'Water tank is empty or in invalid state, turning off heater.',
            clears=(WaterHeaterOnNotification, ),
            auto_clear=True
        )


class LightOnNotification(Notification):
    def __init__(self):
        super(LightOnNotification, self).__init__(
            Notification.INFO,
            'Turning ON light',
            clears=(LightOffNotification, )
        )


class LightOffNotification(Notification):
    def __init__(self):
        super(LightOffNotification, self).__init__(
            Notification.INFO,
            'Turning OFF light',
            clears=(LightOnNotification, ),
            auto_clear=True
        )


class DoorOpeningSunriseNotification(Notification):
    def __init__(self):
        super(DoorOpeningSunriseNotification, self).__init__(
            Notification.INFO,
            'Door was closed, opening after sunrise',
            auto_clear=True
        )


class DoorClosingSunsetNotification(Notification):
    def __init__(self):
        super(DoorClosingSunsetNotification, self).__init__(
            Notification.INFO,
            'Door was open, closing after sunset',
            auto_clear=True
        )


class DoorSensorInvalidStateNotification(Notification):
    def __init__(self):
        super(DoorSensorInvalidStateNotification, self).__init__(
            Notification.ERROR,
            'Door sensors are in invalid state!'
        )


class DoorClosedDayNotification(Notification):
    def __init__(self):
        super(DoorClosedDayNotification, self).__init__(
            Notification.WARN,
            'Door is in MANUAL mode, and is closed during the day!'
        )


class DoorOpenNightNotification(Notification):
    def __init__(self):
        super(DoorOpenNightNotification, self).__init__(
            Notification.WARN,
            'Door is in MANUAL mode, and is open during the night!'
        )


class DoorFailedOpenNotification(Notification):
    def __init__(self):
        super(DoorFailedOpenNotification, self).__init__(
            Notification.ERROR,
            'Door FAILED to open'
        )


class DoorFailedCloseNotification(Notification):
    def __init__(self):
        super(DoorFailedCloseNotification, self).__init__(
            Notification.ERROR,
            'Door FAILED to close'
        )


class NotifierManager(object):
    def __init__(self):
        self.notifiers = []

    def register_notifier(self, notifier):
        self.notifiers.append(notifier)

    def detailed_status(self):
        _status = []
        for notifier in self.notifiers:
            s = notifier.status()
            if s is not None:
                _status.extend(s)
        return _status

    def status(self):
        _detailed_status = self.detailed_status()
        if len(_detailed_status) == 0:
            return Notification.INFO
        else:
            return max(_detailed_status)


class NotifierMixin(object):
    def __init__(self, notification_types):
        self.notification_sent = {}
        for t in notification_types:
            self.notification_sent[t] = None

    def send_notification(self, notification, **kwargs):
        if notification.type() not in self.notification_sent.keys():
            log.error('Invalid notification type "{}"'.format(notification.type()))
        elif not notification.single or self.notification_sent[notification.type()] is None:
            for clear in notification.clears:
                self.clear_notification(clear)
            self.coop.notifier_callback(notification=notification, message=notification.message.format(**kwargs))
            if not notification.auto_clear:
                self.notification_sent[notification.type()] = notification

    def clear_notification(self, notification_type):
        if notification_type not in self.notification_sent.keys():
            log.error('Invalid notification type "{}"'.format(notification_type))
        else:
            self.notification_sent[notification_type] = None

    def status(self):
        _status = []
        for notification in self.notification_sent.values():
            if notification is not None:
                _status.append(notification.severity)
        return _status
