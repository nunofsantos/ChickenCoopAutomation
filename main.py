import logging
from time import sleep


from chickencoopauto.coop import Coop


logging.basicConfig()
log = logging.getLogger('main')
log.setLevel(logging.DEBUG)
logging.getLogger('chickencoopauto').setLevel(logging.DEBUG)


def main():
    coop = Coop()
    # sunset_sunrise.set_is_day(True)

    try:
        count = 1
        while True:
            log.debug('===== {} ====='.format(count))
            #######################
            # if count == 3:
            #     sunset_sunrise.set_extra_min_sunset(0)
            #     sunset_sunrise.set_is_day(False)
            # elif count == 6:
            #     door.set_manual_mode()
            #     sunset_sunrise.set_extra_min_sunset(2000)
            #     sunset_sunrise.set_is_day(True)
            # elif count == 9:
            #     door.set_auto_mode()
            #######################

            # ambient temperature
            coop.ambient_temp_humi_sensor.check()

            # water temperature
            coop.water_temp_sensor.check()

            # water level
            coop.water_level_sensor_top.check()
            coop.water_level_sensor_bottom.check()

            # light
            coop.light.check()

            #############################
            # door switches
            # coop.door_open_sensor.check()
            # coop.door_closed_sensor.check()
            #############################

            # door
            coop.door.check()

            sleep(5)
            count += 1
    finally:
        log.info('Resetting relays...')
        coop.shutdown()


if __name__ == '__main__':
    main()
