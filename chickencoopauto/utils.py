import logging
from threading import Thread
from time import sleep


log = logging.getLogger(__name__)


class Singleton(object):
    __instance = None

    def __new__(cls):
        if Singleton.__instance is None:
            Singleton.__instance = object.__new__(cls)
        return Singleton.__instance


class DummyThread(Thread):
    def run(self):
        while True:
            sleep(20)
