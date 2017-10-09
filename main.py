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
    '/', 'chickencoopauto.controllers.CoopGetStatus',
    '/login', 'chickencoopauto.controllers.Login',
    '/WaterHeater/(manual|auto)', 'chickencoopauto.controllers.WaterHeaterSetMode',
    '/WaterHeater/(on|off)', 'chickencoopauto.controllers.WaterHeaterSetOnOff',
    '/Light/(manual|auto)', 'chickencoopauto.controllers.LightSetMode',
    '/Light/(on|off)', 'chickencoopauto.controllers.LightSetOnOff',
    '/Door/(manual|auto)', 'chickencoopauto.controllers.DoorSetMode',
    '/Door/(open|close)', 'chickencoopauto.controllers.DoorOpenClose',
    '/Fan/(manual|auto)', 'chickencoopauto.controllers.FanSetMode',
    '/Fan/(on|off)', 'chickencoopauto.controllers.FanSetOnOff',
)

if __name__ == '__main__':
    coop = Coop()
    coop.initialize_sensors_relays()

    app = web.application(urls, globals())

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
