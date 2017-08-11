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

    def __init__(self, notification_type, severity, message, clears=(), single=True, auto_clear=False):
        self.type = notification_type
        self.severity = severity
        self.message = message
        self.clears = clears
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
            for clear in notification.clears:
                self._clear_notification_type(clear)
            self.coop.notifier_callback(notification=notification, message=notification.message.format(**kwargs))
            if not notification.auto_clear:
                self.notification_sent[notification.type] = notification.severity

    def _clear_notification_type(self, notification_type):
        if notification_type not in self.types:
            log.error('Invalid notification type "{}"'.format(notification_type))
        else:
            self.notification_sent.pop(notification_type, None)

    def clear_notification(self, notification):
        self._clear_notification_type(notification.type)

    @property
    def status(self):
        _status = []
        for severity in self.notification_sent.values():
            _status.append(severity)
        return _status
