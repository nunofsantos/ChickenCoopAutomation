import logging


log = logging.getLogger(__name__)


class Singleton(object):
    __instance = None

    def __new__(cls):
        if Singleton.__instance is None:
            Singleton.__instance = object.__new__(cls)
        return Singleton.__instance
