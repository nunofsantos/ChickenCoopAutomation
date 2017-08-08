import logging

from chickencoopauto.coop import Coop
from chickencoopauto.utils import DummyThread


logging.basicConfig()
log = logging.getLogger('main')
log.setLevel(logging.DEBUG)
logging.getLogger('chickencoopauto').setLevel(logging.DEBUG)


if __name__ == '__main__':
    coop = Coop()
    dummy = DummyThread()
    dummy.daemon = True
    try:
        coop.start()
        dummy.start()
        while coop.isAlive():
            coop.join(5)
    except (Exception, KeyboardInterrupt):
        coop.shutdown()
