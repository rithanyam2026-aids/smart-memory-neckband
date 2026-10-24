"""
MQTT Receiver and Bridge for Smart Memory Neckband Cloud Backend.
Listens for instantaneous emergency alerts and telemetry updates.
Provides graceful offline fallback when MQTT broker is not running.
"""

from __future__ import annotations
import json
import logging
import threading
from typing import Optional, Callable
from cloud.database import CloudDatabase
from device.config import config

logger = logging.getLogger("MQTTHandler")


class MQTTHandler:
    def __init__(self, db: CloudDatabase, on_alert_callback: Optional[Callable] = None):
        self.db = db
        self.on_alert_callback = on_alert_callback
        self.client = None
        self.is_connected = False
        self._init_client()

    def _init_client(self):
        try:
            import paho.mqtt.client as mqtt

            # Compatibility across paho-mqtt v1 and v2
            if hasattr(mqtt, "CallbackAPIVersion"):
                self.client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=f"cloud_backend_{config.DEVICE_ID}"
                )
            else:
                self.client = mqtt.Client(client_id=f"cloud_backend_{config.DEVICE_ID}")

            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
        except Exception as e:
            logger.warning(f"MQTT client initialization skipped or failed: {e}. Fallback active.")
            self.client = None

    def start_background(self):
        """Start non-blocking MQTT receiver thread."""
        if not self.client:
            return
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()

    def _run_loop(self):
        try:
            self.client.connect(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, 60)
            self.client.loop_forever()
        except Exception as e:
            logger.info(f"MQTT broker offline or unreachable ({config.MQTT_BROKER_HOST}:{config.MQTT_BROKER_PORT}): {e}. Using HTTPS sync fallback.")
            self.is_connected = False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info(f"Connected to MQTT broker with result code {rc}")
        self.is_connected = True
        client.subscribe(config.MQTT_TOPIC_ALERTS)
        client.subscribe(config.MQTT_TOPIC_STATUS)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic = msg.topic
            user_id = payload.get("user_id", "user_01")

            if topic == config.MQTT_TOPIC_ALERTS:
                self.db.insert_alert(user_id, payload)
                if self.on_alert_callback:
                    self.on_alert_callback(payload)
            elif topic == config.MQTT_TOPIC_STATUS:
                self.db.update_device_status(user_id, payload)
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def simulate_receive_alert(self, user_id: str, alert_data: dict):
        """Direct method for test suites and environments without active MQTT brokers."""
        self.db.insert_alert(user_id, alert_data)
        if self.on_alert_callback:
            self.on_alert_callback(alert_data)
