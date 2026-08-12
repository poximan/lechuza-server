import json
import threading
from typing import Any
import ssl
import certifi

import paho.mqtt.client as mqtt

from src import config
from logosaurio import Logosaurio


class ModbusMqttPublisher:
    """
    Publicador MQTT dedicado para snapshots de GRDs/modem.
    Mantiene una unica instancia de paho-mqtt con reconexion automatica.
    """

    def __init__(self, logger: Logosaurio):
        self.log = logger
        self._lock = threading.RLock()
        self._client: mqtt.Client | None = None
        self._connected = False
        self._connect()

    def _connect(self) -> None:
        with self._lock:
            if self._client is not None:
                return
            client = mqtt.Client(clean_session=True)
            client.username_pw_set(config.MQTT_BROKER_USERNAME, config.MQTT_BROKER_PASSWORD)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.reconnect_delay_set(
                min_delay=config.MQTT_RECONNECT_DELAY_MIN,
                max_delay=config.MQTT_RECONNECT_DELAY_MAX,
            )
            if config.MQTT_BROKER_USE_TLS:
                context = ssl.create_default_context(cafile=certifi.where())
                try:
                    context.minimum_version = ssl.TLSVersion.TLSv1_2
                except AttributeError:
                    context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
                if config.MQTT_TLS_INSECURE:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                client.tls_set_context(context)
            try:
                client.connect_async(
                    config.MQTT_BROKER_HOST,
                    config.MQTT_BROKER_PORT,
                    keepalive=config.MQTT_KEEPALIVE,
                )
                client.loop_start()
            except Exception as exc:
                self.log.log(f"Error iniciando conexion MQTT: {exc}", origin="MW/MQTT")
                return
            self._client = client

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties=None):
        self._connected = (reason_code == mqtt.CONNACK_ACCEPTED)
        if self._connected:
            self.log.log("MQTT publisher conectado.", origin="MW/MQTT")
        else:
            self.log.log(f"MQTT no pudo conectar (rc={reason_code}).", origin="MW/MQTT")

    def _on_disconnect(self, _client, _userdata, *args):
        reason_code = self._extract_disconnect_reason_code(args)
        self._connected = False
        self.log.log(f"MQTT desconectado (rc={reason_code}).", origin="MW/MQTT")

    @staticmethod
    def _extract_disconnect_reason_code(args: tuple) -> Any:
        # paho-mqtt VERSION1 invoca on_disconnect(client, userdata, rc)
        # y VERSION2 usa on_disconnect(client, userdata, disconnect_flags, reason_code, properties).
        if not args:
            return "desconocido"
        if len(args) == 1:
            return args[0]
        return args[1]

    def _publish(self, topic: str, payload: Any, qos: int, retain: bool) -> bool:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        with self._lock:
            if self._client is None:
                self._connect()
            client = self._client
            connected = self._connected

        if not client or not connected:
            self.log.log(
                f"MQTT no conectado; publicacion pendiente para {topic}.",
                origin="MW/MQTT",
            )
            return False
        try:
            info = client.publish(topic, payload=body, qos=qos, retain=retain)
            info.wait_for_publish(timeout=config.MQTT_PUBLISH_TIMEOUT_SECONDS)
            if info.rc != mqtt.MQTT_ERR_SUCCESS or not info.is_published():
                raise RuntimeError(
                    f"MQTT no confirmo publicacion en {config.MQTT_PUBLISH_TIMEOUT_SECONDS}s "
                    f"(rc={info.rc})"
                )
            return True
        except Exception as exc:
            self.log.log(f"Error publicando en {topic}: {exc}", origin="MW/MQTT")
            with self._lock:
                try:
                    client.loop_stop()
                except Exception:
                    pass
                try:
                    client.disconnect()
                except Exception:
                    pass
                self._client = None
                self._connected = False
            return False

    def publish_grado(self, payload: dict) -> bool:
        return self._publish(
            config.MQTT_TOPIC_GRADO,
            payload,
            qos=config.MQTT_PUBLISH_QOS_STATE,
            retain=config.MQTT_PUBLISH_RETAIN_STATE,
        )

    def publish_grds(self, payload: dict) -> bool:
        return self._publish(
            config.MQTT_TOPIC_GRDS,
            payload,
            qos=config.MQTT_PUBLISH_QOS_STATE,
            retain=config.MQTT_PUBLISH_RETAIN_STATE,
        )

    def publish_ge_status(self, topic: str, payload: dict) -> bool:
        return self._publish(
            topic,
            payload,
            qos=config.MQTT_PUBLISH_QOS_STATE,
            retain=config.MQTT_PUBLISH_RETAIN_STATE,
        )

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def close(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
            self._connected = False
        if client is None:
            return
        try:
            client.disconnect()
        finally:
            client.loop_stop()
