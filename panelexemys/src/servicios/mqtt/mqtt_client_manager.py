import json
import queue
from typing import Callable, List, Tuple, Optional

import config
from .mqtt_driver import MqttDriver
from src.utils import timebox


class MqttClientManager:
    """
    Manager que orquesta el driver MQTT.
    - Suscripciones por defecto 100% tomadas de config (sin hardcode).
    - Expone publish() para UI (broker_view) con QoS/retain que le pida la UI.
    """

    def __init__(self, logger):
        self.log = logger
        self._origen = "OBS/MQTT"

        # Crear driver
        self.driver = MqttDriver(logger=self.log)
        self._status_topic = config.MQTT_SERVICE_STATUS_TOPIC
        self._status_qos = config.MQTT_SERVICE_STATUS_QOS
        self._status_retain = config.MQTT_SERVICE_STATUS_RETAIN

        # Mensajes entrantes: por defecto una cola nueva
        self.msg_queue: "queue.Queue[Tuple[str, str]]" = queue.Queue()
        self._listeners: List[Tuple[str, Callable[[str, str], None]]] = []

        # Suscripciones por defecto (si no se dieron) - TODO desde config
        self.subscriptions = [
            (config.MQTT_TOPIC_GRADO, 0),
            (config.MQTT_TOPIC_GRDS, 0),
            (config.MQTT_TOPIC_MODEM_CONEXION, 0),
        ]

        # Registrar callbacks del driver hacia metodos del manager
        self.driver.register_on_connect(self._on_driver_connect)
        self.driver.register_on_disconnect(self._on_driver_disconnect)
        self.driver.set_on_message(self._on_driver_message)

        # Estado interno
        self._started = False

    # ----------------- Ciclo de vida
    def start(self) -> bool:
        if self._started:
            return True

        ok = self.driver.connect()
        if not ok:
            self.log.log("MQTT Client Manager: No se pudo establecer conexion inicial.", origin=self._origen)
            return False
        self._started = True
        self.log.log("MQTT Client Manager: Conexion establecida correctamente.", origin=self._origen)
        return True

    def stop(self):
        self._publish_status(False, "shutdown")
        self.driver.disconnect()
        self._started = False

    # ----------------- Callbacks encadenados del driver
    def _on_driver_connect(self, client, userdata, flags, rc):
        self.log.log("MQTT Client Manager: on_connect OK. Suscribiendo topicos...", origin=self._origen)
        try:
            for topic, qos in self.subscriptions:
                self.driver.subscribe(topic, qos)
        except TypeError:
            self.log.log("MQTT Client Manager: subscriptions no es iterable en _on_driver_connect.", origin=self._origen)
        self._publish_status(True, "connect")

    def _on_driver_disconnect(self, client, userdata, rc):
        if rc != 0:
            self._publish_status(False, f"connection_lost_rc{rc}")

    def _on_driver_message(self, client, userdata, msg):
        # Decodificar y encolar el mensaje para el resto del sistema
        try:
            payload = msg.payload.decode(errors="replace")
        except Exception:
            payload = str(msg.payload)

        self.log.log(f"Mensaje en {msg.topic}: {payload}", origin=self._origen)

        try:
            self.msg_queue.put_nowait((msg.topic, payload))
        except queue.Full:
            pass

        for prefix, callback in list(self._listeners):
            if msg.topic.startswith(prefix):
                try:
                    callback(msg.topic, payload)
                except Exception as exc:
                    self.log.log(f"MQTT Client Manager: listener error ({prefix}): {exc}", origin=self._origen)

    # ----------------- API hacia el resto del sistema
    def publish(self, topic: str, payload, qos: int = 0, retain: bool = False):
        self.driver.publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, topic: str, qos: int = 0):
        self.subscriptions.append((topic, qos))
        if self.driver.is_connected():
            self.driver.subscribe(topic, qos)

    def get_message(self, timeout: Optional[float] = None):
        try:
            return self.msg_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_connected(self) -> bool:
        return self.driver.is_connected()

    def get_connection_status(self) -> str:
        if self.driver.is_connected():
            return "conectado"
        if self._started:
            return "conectando"
        return "desconectado"

    def set_message_queue(self, q: "queue.Queue[Tuple[str,str]]"):
        if isinstance(q, queue.Queue):
            self.msg_queue = q

    def register_prefix_listener(self, prefix: str, callback: Callable[[str, str], None]) -> None:
        """
        Registra un callback para los mensajes cuyo topic comience con prefix.
        El listener NO consume la cola compartida.
        """
        if not callable(callback):
            raise ValueError("callback debe ser invocable")
        self._listeners.append((prefix, callback))

    def _publish_status(self, online: bool, reason: str) -> None:
        if not self._status_topic:
            return
        payload = {
            "status": "online" if online else "offline",
            "reason": reason,
            "ts": timebox.utc_iso(),
            "source": "panelexemys",
        }
        try:
            self.driver.publish(
                self._status_topic,
                json.dumps(payload, ensure_ascii=False),
                qos=self._status_qos,
                retain=self._status_retain,
            )
        except Exception as exc:
            self.log.log(f"No se pudo publicar estado del servicio: {exc}", origin=self._origen)
