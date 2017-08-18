
class Notification(object):
    severity_levels = {
        'ERROR': 30,
        'WARN': 20,
        'MANUAL': 10,
        'INFO': 0
    }

    def __init__(self, severity, message, **kwargs):
        self.severity = severity
        self.message = message.format(**kwargs)
