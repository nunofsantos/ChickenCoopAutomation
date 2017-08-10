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

    def __init__(self, type, severity, message, single=True, auto_clear=False):
        self.type = type
        self.severity = severity
        self.message = message
        self.single = single
        self.auto_clear = auto_clear

    @classmethod
    def severity_text(cls, severity):
        for text, number in cls.severity_levels.items():
            if number == severity:
                return text


class NotifierManager(object):
    def __init__(self):
        self.notifiers = []

    def register_notifier(self, notifier):
        self.notifiers.append(notifier)

    @property
    def detailed_status(self):
        _status = []
        for notifier in self.notifiers:
            _status.extend(notifier.status)
        return _status

    @property
    def status(self):
        _detailed_status = self.detailed_status
        if len(_detailed_status) == 0:
            return Notification.INFO
        else:
            return max(_detailed_status)


class NotifierMixin(object):
    def __init__(self, notifications):
        self.notification_sent = {}
        self.types = [n.type for n in notifications]

    def send_notification(self, notification, **kwargs):
        if notification.type not in self.types:
            log.error('Invalid notification type "{}"'.format(notification.type))
        elif not notification.single or notification.type not in self.notification_sent:
            self._send(notification, notification.message.format(**kwargs))
            if not notification.auto_clear:
                self.notification_sent[notification.type] = notification.severity

    def clear_notification(self, notification):
        if notification.type not in self.types:
            log.error('Invalid notification type "{}"'.format(notification.type))
        else:
            self.notification_sent.pop(notification.type, None)

    def _send(self, notification, message):
        self.coop.notifier_callback(notification=notification, message=message)

    @property
    def status(self):
        _status = []
        for severity in self.notification_sent.values():
            _status.append(severity)
        return _status
