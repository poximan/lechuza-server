import json

from typing import Any, Optional
import config

class MqttTopicPublisher:
    """
    Publicador simple reutilizable.
    Usa como default los parÃ¡metros de publicaciones de 'estado' definidos en config:

      - MQTT_PUBLISH_QOS_STATE

      - MQTT_PUBLISH_RETAIN_STATE

    Se pueden sobreescribir por llamada.

    """
    def __init__(self, logger, manager):
        self.log = logger
        self._origen = "OBS/PUB"
        self._manager = manager
        self._qos_state = int(config.MQTT_PUBLISH_QOS_STATE)
        self._retain_state = bool(config.MQTT_PUBLISH_RETAIN_STATE)

    def _ensure_started(self) -> bool:
        if self._manager.is_connected():

            return True

        ok = self._manager.start()

        if not ok:

            self.log.log("No se pudo establecer conexion MQTT via manager.", origin=self._origen)

        return ok

    def publish(self, topic: str, payload: Any,
                qos: Optional[int] = None, retain: Optional[bool] = None):
        if not self._ensure_started():
            self.log.log(f"No se pudo conectar para publicar en '{topic}'.", origin=self._origen)
            return
        q = self._qos_state if qos is None else int(qos)
        r = self._retain_state if retain is None else bool(retain)
        try:
            data = payload if isinstance(payload, str) else str(payload)
            self._manager.publish(topic, data, qos=q, retain=r)
        except Exception as e:
            self.log.log(f"Error publicando en '{topic}': {e}", origin=self._origen)

    def publish_json(self, topic: str, obj: dict,
                     qos: Optional[int] = None, retain: Optional[bool] = None):
        self.publish(topic, json.dumps(obj, ensure_ascii=False), qos=qos, retain=retain)


