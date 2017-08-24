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
    '/', 'chickencoopauto.controllers.coop_get_status',
    '/WaterHeater/(manual|auto)', 'chickencoopauto.controllers.water_heater_set_mode',
    '/WaterHeater/(on|off)', 'chickencoopauto.controllers.water_heater_set_on_off',
    '/Light/(manual|auto)', 'chickencoopauto.controllers.light_set_mode',
    '/Light/(on|off)', 'chickencoopauto.controllers.light_set_on_off',
    '/Door/(manual|auto)', 'chickencoopauto.controllers.door_set_mode',
    '/Door/(open|close)', 'chickencoopauto.controllers.door_open_close',
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
