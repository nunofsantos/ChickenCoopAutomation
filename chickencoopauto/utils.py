import arrow
import json
import logging
import requests


log = logging.getLogger(__name__)


class SunriseSunset(object):
    def __init__(self, lat, lon, extra_min_sunrise=0, extra_min_sunset=0):
        self.lat = lat
        self.lon = lon
        self.extra_min_sunrise = extra_min_sunrise
        self.extra_min_sunset = extra_min_sunset
        self.last = None
        self.sunrise = None
        self.sunset = None
        self.refresh()

    def refresh(self):
        now = arrow.utcnow()
        if not self.last or (now - self.last).days > 0:
            url = 'https://api.sunrise-sunset.org/json?lat={}&lng={}&date=today&formatted=0'.format(self.lat, self.lon)
            response = requests.get(url)
            data = json.loads(response.text)
            if data['status'] == 'OK':
                self.sunrise = arrow.get(data['results']['civil_twilight_begin'])
                self.sunset = arrow.get(data['results']['civil_twilight_end'])
                self.last = now
                log.info('SunriseSunset refreshed at {}. Today is {}, sunrise is at {}, sunset is at {}'.format(
                    self.last.to('US/Eastern').format('MMMM DD, YYYY HH:mm:ss'),
                    now.to('US/Eastern').format('MMMM DD, YYYY'),
                    self.sunrise.to('US/Eastern').format('HH:mm:ss'),
                    self.sunset.to('US/Eastern').format('HH:mm:ss')))
            else:
                log.error('SunriseSunset FAILED to refresh at {}'.format(now.to('US/Eastern').format(
                    'MMMM DD, YYYY HH:mm:ss')))
        return now

    # def set_is_day(self, set):
    #     self.isday = set

    def is_day(self):
        # return self.isday
        now = arrow.utcnow()
        return now.shift(minutes=-self.extra_min_sunrise) > self.sunrise and \
               now.shift(minutes=-self.extra_min_sunset) < self.sunset

    def get_sunrise(self):
        return self.sunrise.to('US/Eastern').format()

    def get_sunset(self):
        return self.sunset.to('US/Eastern').format()

    def set_extra_min_sunrise(self, extra_min):
        self.extra_min_sunrise = extra_min

    def set_extra_min_sunset(self, extra_min):
        self.extra_min_sunset = extra_min
