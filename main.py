import logging
from logging.handlers import RotatingFileHandler
import signal
import sys
import thread

from web import application

from chickencoopauto.coop import Coop


log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

log_filehandler = RotatingFileHandler('/var/log/chickencoop/coop.log', maxBytes=1024**2, backupCount=100)
log_filehandler.setFormatter(log_formatter)
log_filehandler.setLevel(logging.DEBUG)

log_consolehandler = logging.StreamHandler()
log_consolehandler.setFormatter(log_formatter)
log_consolehandler.setLevel(logging.DEBUG)

logging.getLogger('web').setLevel(logging.ERROR)

log = logging.getLogger('chickencoopauto')
log.addHandler(log_filehandler)
log.addHandler(log_consolehandler)
log.setLevel(logging.DEBUG)

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
    '/status', 'chickencoopauto.controllers.HeartbeatStatus',
    '/TempHumiGraph', 'chickencoopauto.controllers.TempHumiGraph',
)


def sigterm_handler(_, __):
    log.info('SIGTERM, shutting down')
    coop = Coop()
    coop.shutdown()
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, sigterm_handler)
    coop = Coop()
    coop.initialize_sensors_relays()

    app = application(urls, globals())

    try:
        coop.start()
        thread.start_new_thread(app.run(), ())
        while coop.isAlive():
            coop.join(60)
    finally:
        coop.shutdown()
