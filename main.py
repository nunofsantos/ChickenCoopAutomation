import logging
import thread

import web

from chickencoopauto.coop import Coop
# from chickencoopauto.utils import DummyThread


logging.basicConfig()
log = logging.getLogger('main')
log.setLevel(logging.DEBUG)
logging.getLogger('chickencoopauto').setLevel(logging.DEBUG)

urls = (
    '/', 'Coop'
)

app = web.application(urls, globals())

if __name__ == '__main__':
    coop = Coop()
    coop.initialize_sensors_relays()

    # dummy = DummyThread()
    # dummy.daemon = True

    try:
        coop.start()
        # dummy.start()
        thread.start_new_thread(app.run(), ())
        while coop.isAlive():
            coop.join(5)
    finally:
        coop.shutdown()
