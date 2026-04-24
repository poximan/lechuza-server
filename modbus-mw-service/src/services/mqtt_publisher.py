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
            client.loop_start()
            try:
                client.connect_async(
                    config.MQTT_BROKER_HOST,
                    config.MQTT_BROKER_PORT,
                    keepalive=config.MQTT_KEEPALIVE,
                )
            except Exception as exc:
                self.log.log(f"Error iniciando conexion MQTT: {exc}", origin="MW/MQTT")
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

    def _publish(self, topic: str, payload: Any, qos: int, retain: bool) -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        with self._lock:
            if self._client is None:
                self._connect()
            client = self._client
            connected = self._connected

        if not client or not connected:
            try:
                if client:
                    client.reconnect()
            except Exception as exc:
                self.log.log(f"MQTT no conectado. Reconexion fallida: {exc}", origin="MW/MQTT")
            return
        try:
            info = client.publish(topic, payload=body, qos=qos, retain=retain)
            info.wait_for_publish()
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT rc={info.rc}")
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

    def publish_grado(self, payload: dict) -> None:
        self._publish(
            config.MQTT_TOPIC_GRADO,
            payload,
            qos=config.MQTT_PUBLISH_QOS_STATE,
            retain=config.MQTT_PUBLISH_RETAIN_STATE,
        )

    def publish_grds(self, payload: dict) -> None:
        self._publish(
            config.MQTT_TOPIC_GRDS,
            payload,
            qos=config.MQTT_PUBLISH_QOS_STATE,
            retain=config.MQTT_PUBLISH_RETAIN_STATE,
        )

    def publish_ge_emar(self, payload: dict) -> None:
        topic = config.GE_EMAR["topic"]
        self._publish(
            topic,
            payload,
            qos=config.MQTT_PUBLISH_QOS_STATE,
            retain=config.MQTT_PUBLISH_RETAIN_STATE,
        )
