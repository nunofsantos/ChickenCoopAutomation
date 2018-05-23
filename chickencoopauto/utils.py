import logging
from threading import Event, Thread


log = logging.getLogger(__name__)


class Singleton(object):
    __instance = None

    def __new__(cls):
        if Singleton.__instance is None:
            Singleton.__instance = object.__new__(cls)
        return Singleton.__instance


class StoppableThread(Thread):
    def __init__(self):
        super(StoppableThread, self).__init__()
        self._stop_event = Event()

    def stop(self):
        self._stop_event.set()

    def is_stopping(self):
        return self._stop_event.is_set()


def format_temp(temp):
    return u'{:.1f} \N{DEGREE SIGN}F'.format(temp) if isinstance(temp, float) else '???'


def format_humi(humi):
    return '{:.1f} %'.format(humi) if isinstance(humi, float) else '???'
