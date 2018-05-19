import logging


log = logging.getLogger(__name__)


class Singleton(object):
    __instance = None

    def __new__(cls):
        if Singleton.__instance is None:
            Singleton.__instance = object.__new__(cls)
        return Singleton.__instance


def format_temp(temp):
    return u'{:.1f} \N{DEGREE SIGN}F'.format(temp) if isinstance(temp, float) else '???'

def format_humi(humi):
    return '{:.1f} %'.format(humi) if isinstance(humi, float) else '???'
