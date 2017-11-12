#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
#  Copyright 2017- Serge Wagener                     serge@wagener.family
#########################################################################
#  This software is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Thi software is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this software  If not, see <http://www.gnu.org/licenses/>.
#########################################################################

# pip3 install paho-mqtt pyserial

"""
This software runs on a Raspberry Pi (old v1 is ok). It connects to the FTLABS RD200M Radon sensor
via serial port and to an MQTT broker via TCP. Measured values received vir serial port are simply forwarded
to an MQTT Topic for all subscribers to consume.
"""

import logging
import time
import RPi.GPIO as GPIO

from mqtt import MQTT_publisher
from rd200m import RD200M


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)-8s %(module)-15s %(threadName)-20s %(message)s -- %(filename)s:%(funcName)s:%(lineno)d', datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(__name__)
    logger.debug("Starting RADON measurement")

    shng = MQTT_publisher(broker='192.168.2.1', port=1883)
    shng.connect()
    shng.loop_start()

    rd200m = RD200M()
    rd200m.open()
    rd200m.start_reception(callback=lambda value: shng.publish(value))
    # rd200m.reset()

    time.sleep(1)
    rd200m.force_read()

    while True:
        try:
            time.sleep(.25)
        except KeyboardInterrupt:
            logger.info("ctrl-c detected, shutting down")
            break
        except Exception:
            raise
            break

    logger.debug("Stopping")
    rd200m.close()
    shng.loop_stop()
    shng.disconnect()


if __name__ == "__main__":
    main()
