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

# pip3 install paho-mqtt

import paho.mqtt.client as mqtt
import logging


class MQTT_publisher:

    def __init__(self, broker='127.0.0.1', port=1883):
        """
        Creates an instance of the MQTT class.

        :param broker: MQTT broker hostname or ip address, default is localhost
        :type broker: string
        :param port: MQTT broker port. Default is 1883.
        :type port: int
        """
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Initializing MQTT publisher")
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
        """ Establish connection to MQTT broker """
        self.logger.info("Connecting to MQTT broker")
        try:
            self._client.connect_async(self.mqtt_broker, self.mqtt_port, keepalive=60)
        except Exception as e:
            self.logger.critical("Error connecting to MQTT broker: {}".format(e))
            exit(1)

    def loop_start(self):
        """ Starts the MQTT event loop """
        self._client.loop_start()

    def loop_stop(self):
        """ Stops the MQTT event loop """
        self._client.loop_stop()

    def disconnect(self):
        """ Disconnects from MQTT broker """
        self._client.disconnect()

    def publish(self, value):
        """ Publishes (sends) a value to the MQTT broker for subscribers to consume """
        self.logger.debug("Sending value '{}' to MQTT broker".format(value))
        (result, mid) = self._client.publish(self.mqtt_topic, value, 0, retain=True)
        if result == mqtt.MQTT_ERR_SUCCESS:
            self.logger.info("Message ID {}, '{}' successfully sent to MQTT broker".format(mid, value))
        elif result == mqtt.MQTT_ERR_NO_CONN:
            self.logger.warning("Message ID '{}' could not be sent, no connection".format(mid))
        else:
            self.logger.warning("Message ID '{}' could not be sent, unknown error".format(mid))

    def on_connect(self, client, userdata, flags, rc):
        """ MQTT Connected callback, does no do anything really usefull right now """
        self.logger.info("Connected to MQTT broker")
        self._is_connected = True

    def on_disconnect(self, client, userdata, flags):
        """ MQTT Disconnected callback, does no do anything really usefull right now """
        self.logger.info("Disconnected from MQTT broker")
        self._is_connected = False
