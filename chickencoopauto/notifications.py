import logging


log = logging.getLogger(__name__)


class Notification(object):
    def __init__(self, type, message, single=True, auto_clear=False):
        self.type = type
        self.message = message
        self.single = single
        self.auto_clear = auto_clear

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
                self.notification_sent[notification.type] = True

    def clear_notification(self, notification):
        if notification.type not in self.types:
            log.error('Invalid notification type "{}"'.format(notification.type))
        else:
            self.notification_sent.pop(notification.type, None)

    def _send(self, notification, message):
        log.warning('Notification ({}): {}'.format(notification.type, message))
