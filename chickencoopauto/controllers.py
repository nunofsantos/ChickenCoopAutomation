# -*- coding: utf-8 -*-
from base64 import decodestring
from re import sub
from subprocess import call

from arrow import now
from transitions.core import EventData
import web

from coop import Coop
from notifications import Notification


render = web.template.render('templates')


def get_username_password(auth):
    if not auth:
        return ('', '')
    auth = sub('^Basic ', '', auth)
    username, password = decodestring(auth).split(':')
    return (username, password)

def validate_user(auth, notify=False):
    if not auth:
        return False
    username, password = get_username_password(auth)
    coop = Coop()
    if username == coop.config['Authentication']['USERNAME'] \
       and password == coop.config['Authentication']['PASSWORD']:
        return True
    else:
        if notify:
            coop.notifier_callback(
                Notification('WARN',
                             'Failed login attempt: username={username}, password={password}',
                             username=username,
                             password=password)
            )
        return False


class AuthenticatedUser(object):
    def GET(self, *args, **kwargs):
        if not validate_user(web.ctx.env.get('HTTP_AUTHORIZATION')):
            raise web.seeother('/login')


class Login(object):
    def GET(self):
        if validate_user(web.ctx.env.get('HTTP_AUTHORIZATION'), notify=True):
            raise web.seeother('/')
        else:
            web.header('WWW-Authenticate', 'Basic realm="Authentication"')
            web.ctx.status = '401 Unauthorized'


class CoopGetStatus(AuthenticatedUser):
    def GET(self):
        super(CoopGetStatus, self).GET()
        coop = Coop()
        coop.check()
        return render.index(
            coop.status,
            coop.rebooting,
            now().format('MMMM DD, hh:mm a'),
            coop.sunset_sunrise_sensor.state,
            coop.sunset_sunrise_sensor.status(),
            coop.sunset_sunrise_sensor.sunrise_display(),
            coop.sunset_sunrise_sensor.sunset_display(),
            coop.ambient_temp_humi_sensor.state,
            coop.ambient_temp_humi_sensor.status(),
            u'{:.1f} \N{DEGREE SIGN}F'.format(coop.ambient_temp_humi_sensor.temp)
                if isinstance(coop.ambient_temp_humi_sensor.temp, float)
                else '???',
            '{:.1f} %'.format(coop.ambient_temp_humi_sensor.humi)
                if isinstance(coop.ambient_temp_humi_sensor.humi, float)
                else '???',
            u'{:.1f} \N{DEGREE SIGN}F'.format(coop.water_temp_sensor.temp) if coop.water_temp_sensor.temp else '???',
            coop.water_heater.state,
            coop.max_status_level([coop.water_heater.status(), coop.water_temp_sensor.status()]),
            coop.water_heater_relay.state,
            coop.door_dual_sensor.state,
            coop.door.state,
            coop.door.status(),
            coop.water_level_dual_sensor.state,
            coop.water_level_dual_sensor.status(),
            coop.light.state,
            coop.light.status(),
            coop.fan.state,
            coop.fan.status()
        )


def _single_relay_operated_object_set_mode(obj, mode):
    if mode not in ('auto', 'manual'):
        raise web.seeother('/')
    obj.set_state(mode)
    raise web.seeother('/')


def _single_relay_operated_object_set_on_off(obj, state):
    if state not in ('on', 'off'):
        raise web.seeother('/')
    if state == 'on':
        obj.turn_on()
    else:
        obj.turn_off()
    obj.set_state('manual-{}'.format(state))
    raise web.seeother('/')


class WaterHeaterSetMode(AuthenticatedUser):
    def GET(self, mode):
        super(WaterHeaterSetMode, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_mode(coop.water_heater, mode)


class WaterHeaterSetOnOff(AuthenticatedUser):
    def GET(self, state):
        super(WaterHeaterSetOnOff, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_on_off(coop.water_heater, state)


class FanSetMode(AuthenticatedUser):
    def GET(self, mode):
        super(FanSetMode, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_mode(coop.fan, mode)


class FanSetOnOff(AuthenticatedUser):
    def GET(self, state):
        super(FanSetOnOff, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_on_off(coop.fan, state)


class LightSetMode(AuthenticatedUser):
    def GET(self, mode):
        super(LightSetMode, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_mode(coop.light, mode)


class LightSetOnOff(AuthenticatedUser):
    def GET(self, state):
        super(LightSetOnOff, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_on_off(coop.light, state)


class DoorSetMode(AuthenticatedUser):
    def GET(self, mode):
        super(DoorSetMode, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_mode(coop.door, mode)


class DoorOpenClose(AuthenticatedUser):
    def GET(self, action):
        super(DoorOpenClose, self).GET()
        if action not in ('open', 'close'):
            raise web.seeother('/')
        coop = Coop()
        event = EventData(None, None, None, None, None, {'switches': coop.door_dual_sensor})
        if action == 'open':
            coop.door.open(event)
            state = 'open'
        else:
            coop.door.close(event)
            state = 'closed'
        day_night = coop.sunset_sunrise_sensor.state
        if day_night == 'invalid':
            day_night = 'night'
        coop.door.set_state('manual-{}-{}'.format(state, day_night))
        raise web.seeother('/')


class Reboot(AuthenticatedUser):
    def GET(self):
        super(Reboot, self).GET()
        username, _ = get_username_password(web.ctx.env.get('HTTP_AUTHORIZATION'))
        coop = Coop()
        coop.rebooting = True
        coop.notifier_callback(
            Notification('WARN',
                         'Reboot initiated by user {username}',
                         username=username)
        )
        call(['/usr/bin/sudo', '/sbin/shutdown', '-r', '+1'])
        raise web.seeother('/')
