# -*- coding: utf-8 -*-
from base64 import decodestring
from re import sub

from arrow import now
from transitions.core import EventData
import web

from chickencoopauto.coop import Coop


render = web.template.render('templates')


class AuthenticatedUser(object):
    def GET(self):
        if not web.ctx.env.get('HTTP_AUTHORIZATION'):
            raise web.seeother('/login')

class Login(object):
    def GET(self):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        auth_required = False
        if auth is None:
            auth_required = True
        else:
            auth = sub('^Basic ', '', auth)
            username, password = decodestring(auth).split(':')
            coop = Coop()
            if username == coop.config['Authentication']['USERNAME'] \
               and password == coop.config['Authentication']['PASSWORD']:
                raise web.seeother('/')
            else:
                auth_required = True
        if auth_required:
            web.header('WWW-Authenticate', 'Basic realm="Authentication"')
            web.ctx.status = '401 Unauthorized'
            return


class CoopGetStatus(AuthenticatedUser):
    def GET(self):
        super(CoopGetStatus, self).GET()
        coop = Coop()
        # coop.sunset_sunrise_sensor.get_graph().draw('static/day-night.png', prog='dot')
        # coop.ambient_temp_humi_sensor.get_graph().draw('static/ambient-temp.png', prog='dot')
        # coop.water_temp_sensor.get_graph().draw('static/water-temp.png', prog='dot')
        # coop.water_heater.get_graph().draw('static/water-heater-mode.png', prog='dot')
        # coop.water_heater_relay.get_graph().draw('static/water-heater.png', prog='dot')
        # coop.door_dual_sensor.get_graph().draw('static/door-switches.png', prog='dot')
        # coop.door.get_graph().draw('static/door.png', prog='dot')
        # coop.water_level_dual_sensor.get_graph().draw('static/water-level.png', prog='dot')
        coop.check()
        return render.index(
            coop.status,
            now().format('MMMM DD, hh:mm a'),
            coop.sunset_sunrise_sensor.state,
            coop.sunset_sunrise_sensor.status(),
            coop.sunset_sunrise_sensor.get_sunrise().format('MMMM DD, hh:mm a'),
            coop.sunset_sunrise_sensor.get_sunset().format('MMMM DD, hh:mm a'),
            coop.ambient_temp_humi_sensor.state,
            coop.ambient_temp_humi_sensor.status(),
            u'{:.1f} \N{DEGREE SIGN}F'.format(coop.ambient_temp_humi_sensor.temp)
                if isinstance(coop.ambient_temp_humi_sensor.temp, float)
                else '???',
            '{:.1f} %'.format(coop.ambient_temp_humi_sensor.humi)
                if isinstance(coop.ambient_temp_humi_sensor.humi, float)
                else '???',
            u'{:.1f} \N{DEGREE SIGN}F'.format(coop.water_temp_sensor.temp),
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
