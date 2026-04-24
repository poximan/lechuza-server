import json
import ssl
import threading
import time

import certifi
import paho.mqtt.client as mqtt

from . import config
from .logger import logger


class MqttPublisher:
    def __init__(self) -> None:
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.MQTT_CLIENT_ID)
        self._client.username_pw_set(config.MQTT_BROKER_USERNAME, config.MQTT_BROKER_PASSWORD)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        if config.MQTT_BROKER_USE_TLS:
            context = ssl.create_default_context(cafile=certifi.where())
            try:
                context.minimum_version = ssl.TLSVersion.TLSv1_2
            except AttributeError:
                context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            if config.MQTT_BROKER_CA_CERT:
                context.load_verify_locations(cafile=config.MQTT_BROKER_CA_CERT)
            if config.MQTT_CLIENT_CERTFILE and config.MQTT_CLIENT_KEYFILE:
                context.load_cert_chain(config.MQTT_CLIENT_CERTFILE, config.MQTT_CLIENT_KEYFILE)
            if config.MQTT_TLS_INSECURE:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            self._client.tls_set_context(context)

        self._lock = threading.RLock()
        self._connected = False
        self._connected_event = threading.Event()
        self._stopping = False
        self._reconnect_lock = threading.Lock()
        self._backoff_seconds = 2
        self._client.reconnect_delay_set(
            min_delay=config.MQTT_RECONNECT_DELAY_MIN,
            max_delay=config.MQTT_RECONNECT_DELAY_MAX,
        )
        self._client.loop_start()
        self._connect()

    def _connect(self) -> None:
        try:
            self._client.connect_async(
                config.MQTT_BROKER_HOST,
                config.MQTT_BROKER_PORT,
                keepalive=config.MQTT_BROKER_KEEPALIVE,
            )
        except Exception as exc:
            logger.error("Conexion MQTT fallida: %s", exc, origin="ROUTER-TELEF/MQTT")
            self._schedule_reconnect()

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties=None):
        self._connected = reason_code == mqtt.CONNACK_ACCEPTED

        if self._connected:
            logger.info("MQTT conectado (rc=%s)", reason_code, origin="ROUTER-TELEF/MQTT")
            self._connected_event.set()
            self._backoff_seconds = 2
        else:
            logger.error("MQTT no pudo conectar (rc=%s)", reason_code, origin="ROUTER-TELEF/MQTT")
            self._connected_event.clear()

    def _on_disconnect(self, _client, _userdata, _disconnect_flags, reason_code, _properties=None):
        self._connected = False
        logger.warning("MQTT desconectado (rc=%s)", reason_code, origin="ROUTER-TELEF/MQTT")
        self._connected_event.clear()

        if not self._stopping:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._reconnect_lock.acquire(blocking=False):
            def _reconnect():
                try:
                    time.sleep(self._backoff_seconds)
                    self._connect()
                    self._backoff_seconds = min(self._backoff_seconds * 2, 30)
                finally:
                    self._reconnect_lock.release()

            threading.Thread(target=_reconnect, daemon=True).start()

    def publish_state(self, state: str) -> bool:
        return self._publish(state)

    def publish_offline(self) -> bool:
        return self._publish("desconocido")

    def _publish(self, state: str) -> bool:
        payload = {
            "estado": state,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        data = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            if not self._connected_event.wait(timeout=5):
                logger.error(
                    "No hay conexion MQTT disponible para publicar estado %s",
                    state,
                    origin="ROUTER-TELEF/MQTT",
                )
                self._schedule_reconnect()
                return False
            try:
                result = self._client.publish(
                    config.STATUS_TOPIC,
                    data,
                    qos=config.MQTT_QOS,
                    retain=config.MQTT_RETAIN,
                )
                result.wait_for_publish()
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise RuntimeError(f"publicacion MQTT fallo rc={result.rc}")
                logger.info("Publicado estado %s en %s", state, config.STATUS_TOPIC, origin="ROUTER-TELEF/MQTT")
                return True
            except Exception as exc:
                logger.error("Fallo publicando estado %s: %s", state, exc, origin="ROUTER-TELEF/MQTT")
                self._schedule_reconnect()
                return False

    def stop(self) -> None:
        self._stopping = True
        try:
            self._client.loop_stop()
        finally:
            self._client.disconnect()