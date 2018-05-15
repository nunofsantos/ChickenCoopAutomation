import logging
from logging.handlers import RotatingFileHandler
import thread

import web

from chickencoopauto.coop import Coop


log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

log_filehandler = RotatingFileHandler('/var/log/chickencoop/coop.log', maxBytes=1024**2, backupCount=100)
log_filehandler.setFormatter(log_formatter)
log_filehandler.setLevel(logging.WARN)

log_consolehandler = logging.StreamHandler()
log_consolehandler.setFormatter(log_formatter)
log_consolehandler.setLevel(logging.DEBUG)

logger = logging.getLogger('chickencoopauto')
logger.addHandler(log_filehandler)
logger.addHandler(log_consolehandler)
logger.setLevel(logging.DEBUG)

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
    '/Heater/(manual|auto)', 'chickencoopauto.controllers.HeaterSetMode',
    '/Heater/(on|off)', 'chickencoopauto.controllers.HeaterSetOnOff',
    '/reboot', 'chickencoopauto.controllers.Reboot',
)

if __name__ == '__main__':
    coop = Coop()
    coop.initialize_sensors_relays()

    app = web.application(urls, globals())

    try:
        coop.start()
        thread.start_new_thread(app.run(), ())
        while coop.isAlive():
            coop.join(5)
    finally:
        coop.shutdown()
