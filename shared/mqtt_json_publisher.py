from __future__ import annotations

import json
import ssl
import threading
from typing import Any

import certifi
import paho.mqtt.client as mqtt


class MqttJsonPublisher:
    """Conexion MQTT reutilizable; los dominios definen sus propios topics."""

    def __init__(
        self,
        logger: Any,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        keepalive: int,
        reconnect_delay_min: int,
        reconnect_delay_max: int,
        publish_timeout_seconds: int,
        use_tls: bool,
        tls_insecure: bool,
    ) -> None:
        self.log = logger
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.reconnect_delay_min = reconnect_delay_min
        self.reconnect_delay_max = reconnect_delay_max
        self.publish_timeout_seconds = publish_timeout_seconds
        self.use_tls = use_tls
        self.tls_insecure = tls_insecure
        self._lock = threading.RLock()
        self._client: mqtt.Client | None = None
        self._connected = False
        self._connect()

    def _connect(self) -> None:
        with self._lock:
            if self._client is not None:
                return
            client = mqtt.Client(clean_session=True)
            client.username_pw_set(self.username, self.password)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.reconnect_delay_set(
                min_delay=self.reconnect_delay_min,
                max_delay=self.reconnect_delay_max,
            )
            if self.use_tls:
                context = ssl.create_default_context(cafile=certifi.where())
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                if self.tls_insecure:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                client.tls_set_context(context)
            try:
                client.connect_async(self.host, self.port, keepalive=self.keepalive)
                client.loop_start()
            except Exception as exc:
                self.log.log(f"Error iniciando conexion MQTT: {exc}", origin="MQTT")
                return
            self._client = client

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties=None):
        self._connected = reason_code == mqtt.CONNACK_ACCEPTED
        message = (
            "MQTT publisher conectado."
            if self._connected
            else f"MQTT no pudo conectar (rc={reason_code})."
        )
        self.log.log(message, origin="MQTT")

    def _on_disconnect(self, _client, _userdata, *args):
        reason_code = args[0] if len(args) == 1 else args[1] if len(args) > 1 else "desconocido"
        self._connected = False
        self.log.log(f"MQTT desconectado (rc={reason_code}).", origin="MQTT")

    def publish_json(self, topic: str, payload: Any, qos: int, retain: bool) -> bool:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        with self._lock:
            if self._client is None:
                self._connect()
            client = self._client
            connected = self._connected
        if not client or not connected:
            self.log.log(f"MQTT no conectado para {topic}.", origin="MQTT")
            return False
        try:
            info = client.publish(topic, payload=body, qos=qos, retain=retain)
            info.wait_for_publish(timeout=self.publish_timeout_seconds)
            if info.rc != mqtt.MQTT_ERR_SUCCESS or not info.is_published():
                raise RuntimeError(f"MQTT no confirmo publicacion (rc={info.rc})")
            return True
        except Exception as exc:
            self.log.log(f"Error publicando en {topic}: {exc}", origin="MQTT")
            with self._lock:
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception:
                    pass
                self._client = None
                self._connected = False
            return False

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
