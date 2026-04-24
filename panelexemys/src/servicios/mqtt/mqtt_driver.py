import ssl
import threading
from typing import Callable, List, Optional
import paho.mqtt.client as mqtt
import config
import os
import platform
import hashlib
import uuid

class MqttDriver:
    """
    Capa delgada sobre paho-mqtt.
    Mantener cambios al minimo; este modulo expone connect/ disconnect/ publish/ subscribe/ callbacks.
    """

    def __init__(self, logger):
        self.log = logger
        self._origen = "OBS/MQTT"

        client_id = self._compute_client_id()
        clean_session = True  # comportamiento habitual en clientes móviles/edge

        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id, clean_session=clean_session)
        except TypeError:
            self.client = mqtt.Client(client_id=client_id, clean_session=clean_session)

        username = config.MQTT_BROKER_USERNAME
        password = config.MQTT_BROKER_PASSWORD
        if username is not None:
            self.client.username_pw_set(username, password)

        will_topic = config.MQTT_WILL_TOPIC
        will_payload = config.MQTT_WILL_PAYLOAD
        will_qos = config.MQTT_WILL_QOS
        will_retain = config.MQTT_WILL_RETAIN
        if will_topic:
            if will_payload is None or will_qos is None or will_retain is None:
                raise ValueError("Configuracion LWT incompleta: defina payload/qos/retain")
            self.client.will_set(will_topic, payload=will_payload, qos=int(will_qos), retain=bool(will_retain))

        if config.MQTT_BROKER_USE_TLS:
            ca = config.MQTT_BROKER_CA_CERT
            certfile = config.MQTT_CLIENT_CERTFILE
            keyfile = config.MQTT_CLIENT_KEYFILE
            tls_insecure = config.MQTT_TLS_INSECURE
            self.client.tls_set(
                ca_certs=ca,
                certfile=certfile,
                keyfile=keyfile,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
            self.client.tls_insecure_set(tls_insecure)
            self.log.log(f"TLS configurado (insecure={tls_insecure}).", origin=self._origen)

        self.keepalive = int(config.MQTT_BROKER_KEEPALIVE)
        min_delay = int(config.MQTT_RECONNECT_DELAY_MIN)
        max_delay = int(config.MQTT_RECONNECT_DELAY_MAX)
        try:
            self.client.reconnect_delay_set(min_delay=min_delay, max_delay=max_delay)
        except AttributeError:
            pass

        self.client.on_connect = self._on_connect_internal
        self.client.on_disconnect = self._on_disconnect_internal
        self.client.on_message = self._on_message_internal

        self._extra_on_connect: List[Callable] = []
        self._extra_on_disconnect: List[Callable] = []
        self._extra_on_message: Optional[Callable] = None

        self._connected_event = threading.Event()
        self._connected = False
        self._loop_started = False

    @staticmethod
    def _compute_client_id() -> str:
        """Genera un clientId estable por plataforma sin depender de archivos de propiedades.
        Preferencias: /etc/machine-id -> hostname -> MAC -> UUID aleatoria (último recurso).
        """
        candidates: list[str] = []
        # 1) machine-id (Linux)
        try:
            if os.path.exists('/etc/machine-id'):
                with open('/etc/machine-id','r',encoding='utf-8',errors='ignore') as f:
                    mid = f.read().strip()
                    if mid:
                        candidates.append(mid)
        except Exception:
            pass
        # 2) hostname del SO/contenedor
        try:
            hn = platform.node()
            if hn:
                candidates.append(hn)
        except Exception:
            pass
        # 3) MAC del host
        try:
            mac = uuid.getnode()
            if mac and (mac >> 40) % 2 == 0:
                candidates.append(hex(mac))
        except Exception:
            pass
        if not candidates:
            candidates.append(str(uuid.uuid4()))

        h = hashlib.sha256("|".join(candidates).encode('utf-8')).hexdigest()[:12]
        return f"panelexemys-{h}"

    def _on_connect_internal(self, client, userdata, flags, rc, *args):
        if rc == 0:
            self._connected = True
            self._connected_event.set()
            self.log.log("MQTT Driver: on_connect OK (rc=0).", origin=self._origen)
        else:
            self._connected = False
            self.log.log(f"MQTT Driver: on_connect con error (rc={rc}).", origin=self._origen)

        for cb in self._extra_on_connect:
            try:
                cb(client, userdata, flags, rc)
            except Exception as e:
                self.log.log(f"MQTT Driver: error en callback externo on_connect: {e}", origin=self._origen)

    def _on_disconnect_internal(self, client, userdata, rc, *args):
        self._connected = False
        self._connected_event.clear()
        self.log.log(f"MQTT Client Manager: on_disconnect (rc={rc}).", origin=self._origen)

        for cb in self._extra_on_disconnect:
            try:
                cb(client, userdata, rc)
            except Exception as e:
                self.log.log(f"MQTT Driver: error en callback externo on_disconnect: {e}", origin=self._origen)

    def _on_message_internal(self, client, userdata, msg):
        if self._extra_on_message is not None:
            try:
                self._extra_on_message(client, userdata, msg)
                return
            except Exception as e:
                self.log.log(f"MQTT Driver: error en callback externo on_message: {e}", origin=self._origen)
        try:
            payload = msg.payload.decode(errors="replace")
        except Exception:
            payload = str(msg.payload)
        self.log.log(f"MQTT mensaje: {msg.topic} -> {payload}", origin=self._origen)

    def register_on_connect(self, cb: Callable):
        self._extra_on_connect.append(cb)

    def register_on_disconnect(self, cb: Callable):
        self._extra_on_disconnect.append(cb)

    def set_on_message(self, cb: Callable):
        self._extra_on_message = cb

    def connect(self) -> bool:
        host = config.MQTT_BROKER_HOST
        port = int(config.MQTT_BROKER_PORT)
        timeout = int(config.MQTT_CONNECT_TIMEOUT)

        self.log.log(
            f"MQTT Driver: Intentando conectar a {host}:{port} (keepalive={self.keepalive})",
            origin=self._origen,
        )

        try:
            self.client.connect_async(host, port, keepalive=self.keepalive)
        except Exception as e:
            self.log.log(f"MQTT Driver: excepcion en connect_async: {e}", origin=self._origen)
            return False

        if not self._loop_started:
            self.client.loop_start()
            self._loop_started = True

        if self._connected_event.wait(timeout=timeout):
            self.log.log("MQTT Driver: Conexión confirmada por callback dentro del timeout.", origin=self._origen)
            return True

        self.log.log("MQTT Driver: Timeout esperando confirmacion de conexion.", origin=self._origen)
        return False

    def disconnect(self):
        try:
            self.client.disconnect()
        except Exception as e:
            self.log.log(f"MQTT Driver: error en disconnect(): {e}", origin=self._origen)
        finally:
            if self._loop_started:
                self.client.loop_stop()
                self._loop_started = False
            self._connected = False
            self._connected_event.clear()

    def publish(self, topic: str, payload, qos: int = 0, retain: bool = False):
        if not self._connected:
            self.log.log(f"MQTT Driver: publish abortado; cliente desconectado (topic={topic}).", origin=self._origen)
            return
        try:
            res = self.client.publish(topic, payload, qos=qos, retain=retain)
            self.log.log(f"MQTT Driver: publish('{topic}') -> {res.rc}", origin=self._origen)
        except Exception as e:
            self.log.log(f"MQTT Driver: error publicando en '{topic}': {e}", origin=self._origen)

    def subscribe(self, topic: str, qos: int = 0):
        if not self._connected:
            self.log.log(f"MQTT Driver: subscribe abortado; cliente desconectado (topic={topic}).", origin=self._origen)
            return
        try:
            res = self.client.subscribe(topic, qos=qos)
            self.log.log(f"MQTT Client Manager: subscribe('{topic}') -> {res}", origin=self._origen)
        except Exception as e:
            self.log.log(f"MQTT Driver: error al suscribirse a '{topic}': {e}", origin=self._origen)

    def is_connected(self) -> bool:
        return self._connected
