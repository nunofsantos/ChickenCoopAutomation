# -*- coding: utf-8 -*-
from base64 import decodestring
from re import sub
from subprocess import call

from arrow import now
from plotly.offline import plot
from plotly.graph_objs import Data, Figure, Layout, Scatter
from transitions.core import EventData
from web.db import database
import web

from coop import Coop
from notifications import Notification
from utils import format_humi, format_temp, get_db


render = web.template.render('templates')


def get_username_password(auth):
    if not auth:
        return ('', '')
    auth = sub('^Basic ', '', auth)
    username, password = decodestring(auth).split(':')
    return (username, password)


def validate_user(ctx, notify=False):
    if not ctx.env.get('HTTP_AUTHORIZATION'):
        return False
    username, password = get_username_password(ctx.env.get('HTTP_AUTHORIZATION'))
    coop = Coop()
    if username == coop.config['Authentication']['USERNAME'] and password == coop.config['Authentication']['PASSWORD']:
        return True
    else:
        if notify:
            coop.notifier_callback(
                Notification('WARN',
                             'Failed login attempt: username={username}, password={password}, ip={ip}',
                             username=username,
                             password=password,
                             ip=ctx['ip'])
            )
        return False


class AuthenticatedUser(object):
    def GET(self, *args, **kwargs):
        if not validate_user(web.ctx):
            raise web.seeother('/login')


class Login(object):
    def GET(self):
        if validate_user(web.ctx, notify=True):
            raise web.seeother('/')
        else:
            web.header('WWW-Authenticate', 'Basic realm="Authentication"')
            web.ctx.status = '401 Unauthorized'


class HeartbeatStatus(object):
    def GET(self):
        coop = Coop()
        coop.check()
        return render.heartbeat(
            coop.status,
            coop.rebooting
        )


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
            coop.sunset_sunrise_sensor.sunrise_display(display_extra=False),
            coop.sunset_sunrise_sensor.sunset_display(display_extra=False),
            coop.ambient_temp_humi_sensor.state,
            coop.ambient_temp_humi_sensor.status(),
            format_temp(coop.ambient_temp_humi_sensor.temp),
            format_humi(coop.ambient_temp_humi_sensor.humi),
            format_temp(coop.water_temp_sensor.temp),
            coop.water_temp_sensor.get_state_for_display(),
            coop.water_temp_sensor.status(),
            format_temp(coop.water_heater.temp_range[0]),
            format_temp(coop.water_heater.temp_range[1]),
            coop.water_heater.state,
            coop.water_heater.status(),
            coop.water_heater_relay.state,
            coop.door_dual_sensor.state,
            coop.sunset_sunrise_sensor.sunrise_display(include_extra=True, display_extra=True, include_day=False),
            coop.sunset_sunrise_sensor.sunset_display(include_extra=True, display_extra=True, include_day=False),
            coop.door.state,
            coop.door.status(),
            coop.water_level_dual_sensor.state,
            coop.water_level_dual_sensor.status(),
            coop.light.state,
            coop.light.status(),
            format_temp(coop.fan.temp_range[0]),
            format_temp(coop.fan.temp_range[1]),
            coop.fan.state,
            coop.fan.status(),
            format_temp(coop.heater.temp_range[0]),
            format_temp(coop.heater.temp_range[1]),
            coop.heater.state,
            coop.heater.status(),
            coop.heater_relay.state,
        )


def _single_relay_operated_object_set_mode(obj, mode, **kwargs):
    if mode not in ('auto', 'manual'):
        raise web.seeother('/')
    obj.set_state(mode)
    obj.check(**kwargs)
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


class HeaterSetMode(AuthenticatedUser):
    def GET(self, mode):
        super(HeaterSetMode, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_mode(coop.heater, mode)


class HeaterSetOnOff(AuthenticatedUser):
    def GET(self, state):
        super(HeaterSetOnOff, self).GET()
        coop = Coop()
        _single_relay_operated_object_set_on_off(coop.heater, state)


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
        _single_relay_operated_object_set_mode(coop.door, mode, switches=coop.door_dual_sensor)


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
        coop.stop()
        coop.join()
        coop.shutdown()
        call(['/usr/bin/sudo', '/sbin/shutdown', '-r', 'now'])
        raise web.seeother('/')


class TempHumiGraph(AuthenticatedUser):
    def GET(self):
        super(TempHumiGraph, self).GET()
        get_data = web.input(range_days='7', action='read')
        range_days = get_data.range_days
        coop = Coop()
        db = get_db(coop)
        data = Data([
            scatter_graph_timeseries(db, 'AMBIENT_TEMP', 'Air Temperature', 'red', range_days=range_days),
            scatter_graph_timeseries(db, 'WATER_TEMP', 'Water Temperature', 'blue', range_days=range_days),
            scatter_graph_timeseries(db, 'AMBIENT_HUMI', 'Humidity', 'green', width=1, yaxis2=True, range_days=range_days),
        ])
        min_x = min(min(data[0].x), min(data[1].x), min(data[2].x))
        max_x = max(max(data[0].x), max(data[1].x), max(data[2].x))
        temp_min = coop.config['Water']['HEATER_TEMP_RANGE'][1]
        temp_max = coop.config['AmbientTempHumi']['TEMP_FAN']
        layout = Layout(
            title='Temperature & Humidity',
            xaxis={
                'title':'Date',
            },
            yaxis={
                'title':'Temperature (F)',
            },
            yaxis2={
                'title': 'Humidity (%)',
                'type': 'linear',
                'range': [0, 100],
                'fixedrange': True,
                'overlaying': 'y',
                'side': 'right',
                'showgrid': False,
            },
            shapes=[
                {
                    'type': 'line',
                    'x0': min_x,
                    'y0': temp_max,
                    'x1': max_x,
                    'y1': temp_max,
                    'line': {
                        'color': 'red',
                        'width': 1,
                        'dash': 'dot',
                    },
                },
                {
                    'type': 'line',
                    'x0': min_x,
                    'y0': temp_min,
                    'x1': max_x,
                    'y1': temp_min,
                    'line': {
                        'color': 'blue',
                        'width': 1,
                        'dash': 'dot',
                    },
                },
            ]
        )
        figure = Figure(data=data, layout=layout)
        graph = plot(figure, auto_open=False, output_type='div')

        return render.temp_humi_graph(coop.status, graph, range_days)


def scatter_graph_timeseries(db, log_type, name, color, width=3, yaxis2=False, range_days=7):
    query = db.select(
        'coop_log',
        what='log_value, (created AT TIME ZONE \'UTC\') AT TIME ZONE \'US/Eastern\' as created_local',
        where='log_type = \'{}\' and created > now() - interval \'{} day\''.format(log_type, range_days),
        order='created asc'
    )
    x, y = zip(*[(i['created_local'], i['log_value']) for i in query])
    return Scatter(
        x=x,
        y=y,
        marker={
            'color': color,
            'symbol': 104,
            'size': '10',
        },
        mode='lines',
        name=name,
        line={
            'width': width,
        },
        yaxis='y2' if yaxis2 else 'y',
    )
