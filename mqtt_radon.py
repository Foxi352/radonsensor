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
|  *** ATTENTION: This is early work in progress ***
|  *** DO NOT USE IN PRODUCTION until you know what you are doing ***
|
This software runs on a Raspberry Pi (old v1 is ok). It connects to the FTLABS RD200M Radon sensor
via serial port and to an MQTT broker via TCP. Measured values received vir serial port are simply forwarded
to an MQTT Topic for all subscribers to consume.
"""


import binascii
import logging
import paho.mqtt.client as mqtt
import serial
import threading
import time
import RPi.GPIO as GPIO


class MQTT_publisher:

    def __init__(self, broker='127.0.0.1', port=1883):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing MQTT publisher")
        self.mqtt_broker = broker
        self.mqtt_port = port
        self.mqtt_topic = 'sensor/radon/value'
        self.mqtt_deviceid = 'radon_01'
        self.mqtt_devicename = 'Raden Sensor 1'

        self._is_connected = False
        self._on_message = None

        self._client = mqtt.Client(client_id=self.mqtt_deviceid, clean_session=True)
        self._client.on_connect = self.on_connect
        self._client.on_disconnect = self.on_disconnect

    def connect(self):
        self.logger.debug("Connecting to MQTT broker")
        try:
            self._client.connect_async(self.mqtt_broker, self.mqtt_port, keepalive=60)
        except Exception as e:
            self.logger.critical("Error connecting to MQTT broker: {}".format(e))
            exit(1)

    def loop_start(self):
        self._client.loop_start()

    def loop_stop(self):
        self._client.loop_stop()

    def disconnect(self):
        self._client.disconnect()

    def publish(self, value):
        self.logger.debug("Sending value '{}' to MQTT broker".format(value))
        (result, mid) = self._client.publish(self.mqtt_topic, value, 0, retain=True)
        if result == mqtt.MQTT_ERR_SUCCESS:
            self.logger.info("Message ID {}, '{}' successfully sent to MQTT broker".format(mid, value))
        elif result == mqtt.MQTT_ERR_NO_CONN:
            self.logger.warning("Message ID '{}' could not be sent, no connection".format(mid))
        else:
            self.logger.warning("Message ID '{}' could not be sent, unknown error".format(mid))

    def on_connect(self, client, userdata, flags, rc):
        self.logger.info("Connected to MQTT broker")
        self._is_connected = True

    def on_disconnect(self, client, userdata, flags):
        self.logger.info("Disconnected from MQTT broker")
        self._is_connected = False


class RD200M:

    cmd_RESULT_QUERY = 0x01     # Request all data
    cmd_RESET = 0xA0            # RD200M reset
    cmd_SET_PERIOD = 0xA1       # Set data transfer period
    cmd_RESULT_RETURN = 0x10    # Read all data (receive only)

    status = {0x00: 'Measurement between power on and 200s',
              0x01: 'Measurement between 200s and 1h',
              0x10: 'WARNING: Measurement within 30m and count > 10',
              0x02: 'Measurement after 1h',
              0xE0: 'Detected vibrations, measurement maybe unreliable'}

    def __init__(self, port='/dev/ttyAMA0', baudrate=19200, period=10):
        """
        Creates an instance of the RD200M class.

        :param port: Serial port to use. Defaults to the Raspberry Pi onboard UART
        :type port: string
        :param baudrate: Baudrate (bit/s) for serial port communication. Defaults to 19200 for RD200M
        :type baudrate: int
        :param period: Time interval in minutes for the RD200M to send measurements automatically
        :type period: int
        """
        self.logger = logging.getLogger(__name__)
        self.port = port
        self.baudrate = baudrate
        self.period = period

        self._callback = None

        self.__timeout = None
        self.__serial = serial.Serial()
        self.__receive_thread = None

    def open(self):
        """
        Opens the serial port specified in the constructor.

        :return: Returns true on succes or false if unable to open serial port
        :rtype: bool
        """
        self.__serial.baudrate = self.baudrate
        self.__serial.port = self.port
        self.__serial.open()
        if self.__serial.is_open:
            self.logger.info("Serial port '{}' opened with {} bit/s".format(self.port, self.baudrate))
        else:
            self.logger.critical("Unable to open port '{}'".format(self.port))
            return False
        return True

    def reset(self, period=None):
        """
        Reset the RD200M by setting the desired measurement send period and a reset command

        :param period: Time interval in minutes for the RD200M to send measurements automatically
        :type period: int
        """
        self.__serial.baudrate = self.baudrate
        if period:
            self.period = period
        self.logger.info("Resetting RD200M and setting measurement period to {} minutes".format(self.period))
        self._send_cmd(self.cmd_SET_PERIOD, self.period)
        time.sleep(1)
        self._send_cmd(self.cmd_RESET)
        time.sleep(1)

    def force_read(self):
        """ Force the RD200M to send the actual values """
        self._send_cmd(self.cmd_RESULT_QUERY)

    def start_reception(self, callback=None):
        """
        Starts the serial reception thread. Values collected will be sent to the callback function if set.

        :param callback: Callback function / method to call when a measurement value is received
        :type callback: lambda

        :return: Returns always true for now
        :rtype: bool
        """
        self.__serial.baudrate = self.baudrate
        self._callback = callback
        self.logger.info("Starting reception thread")
        self._running = True
        self.__receive_thread = threading.Thread(target=self.__receive_thread_worker, name='RD200M receiver')
        self.__receive_thread.start()
        return True

    def close(self):
        """
        Closes the serial port and cancels reading in progress.

        :return: Returns always true for now
        :rtype: bool
        """
        self._running = False
        if self.__serial.is_open:
            self.__serial.close()
            self.logger.debug("Serial port '{}' closed".format(self.port))
        else:
            self.logger.debug("Cannot close serial port '{}' because it is not open".format(self.port))
        if self.__receive_thread and self.__receive_thread.isAlive():
            self.__receive_thread.join()
        return True

    def _send_cmd(self, cmd, data=None):
        """
        Sends a command to the RD200M with optional parameters

        :param cmd: Command to send. See cmd_* constants in this class.
        :type cmd: int
        :param data: Optional data to send with the command (such as period time)
        :type data: int

        :return: Returns true if command has been sucessfully bufered for sending or false on any error
        :rtype: bool
        """
        cmdarray = bytearray([0x02, cmd])
        if data:
            if isinstance(data, int):
                size = (data.bit_length() + 7) // 8
                checksum = 0xFF - (cmd + size + data)
                cmdarray.extend([size, data, checksum])
            else:
                self.logger.warning("Data must be of type integer, ignoring '{}'".format(data))
                return False
        else:
            size = 0
            checksum = 0xFF - (cmd + size)
            cmdarray.extend([size, checksum])
        self.logger.debug("Sending command '{}'".format(binascii.hexlify(cmdarray).decode()))
        self.__serial.write(cmdarray)
        return True

    def _process_measurement_data(self, data):
        """
        Processes an incoming (already checksum tested) data packet and sends processed value to the
        callback defined in start_reception()

        :param data: 4 bytes data received from RD200M.
        :type data: bytes

        :return: Returns always true for now
        :rtype: bool
        """
        if len(data) != 4:
            self.logger.warning("Received data '{}' has not exactly 4 bytes, cannot decode measurement".format(binascii.hexlify(data).decode()))
            return False
        status = data[0]
        minutes = data[1]
        integer = data[2]
        decimal = data[3]
        radon = float(str(integer) + "." + str(decimal)) * 37  # * 37 converts pCi/L to bq/m3
        self.logger.info("Radon is {} bq/m3, {}".format(radon, self.status[status]))
        self._callback and self._callback(radon)
        return True

    def __receive_thread_worker(self):
        """ Received serial communication from RD200M. Controlls checksum and sends packets to _process_measurement() if valid. """
        self.logger.debug("Receive thread started")
        while self._running:
            response = self.__serial.read(size=8)
            if len(response) == 8:
                self.logger.debug("Received '{}'".format(binascii.hexlify(response).decode()))
                cmd = response[1]
                size = response[2]
                data = response[3:3 + size]
                checksum = int.from_bytes(response[-1:], byteorder='big')
                data_sum = 0
                for ch in data:
                    data_sum += ch
                calculated_checksum = 0xFF - (cmd + size + data_sum)
                if checksum == calculated_checksum:
                    if cmd == self.cmd_RESULT_RETURN:
                        self._process_measurement_data(data)
                    else:
                        self.logger.warning("Received unknown command '{'}".format(cmd))
                else:
                    self.logger.warning("Checksum error, ignoring received data '{}'".format(binascii.hexlify(response).decode()))
        self.logger.debug("Receive thread stopped")


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
            traceback.print_exc(file=sys.stdout)
            break

    logger.debug("Stopping")
    rd200m.close()
    shng.loop_stop()
    shng.disconnect()


if __name__ == "__main__":
    main()
