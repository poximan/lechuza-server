import json
import os
import threading
import time
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

from . import config as cfg
from .logger import logger


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


_MQTT_HOST = _require("MQTT_BROKER_HOST")
_MQTT_PORT = int(_require("MQTT_BROKER_PORT"))
_MQTT_USERNAME = _require("MQTT_BROKER_USERNAME")
_MQTT_PASSWORD = _require("MQTT_BROKER_PASSWORD")
_MQTT_KEEPALIVE = int(_require("MQTT_BROKER_KEEPALIVE"))
_USE_TLS = _require("MQTT_BROKER_USE_TLS").lower() in {"1", "true", "yes", "on"}
_TLS_INSECURE = _require("MQTT_TLS_INSECURE").lower() in {"1", "true", "yes", "on"}

_CLIENT_LOCK = threading.RLock()
_CLIENT: Optional[mqtt.Client] = None


def _build_client() -> mqtt.Client:
    client = mqtt.Client(client_id="pve-service", clean_session=True)
    client.username_pw_set(_MQTT_USERNAME, _MQTT_PASSWORD)
    if _USE_TLS:
        client.tls_set()
        client.tls_insecure_set(_TLS_INSECURE)
    client.connect(_MQTT_HOST, _MQTT_PORT, keepalive=_MQTT_KEEPALIVE)
    client.loop_start()
    return client


def _get_client_locked() -> mqtt.Client:
    global _CLIENT
    if _CLIENT is not None and _CLIENT.is_connected():
        return _CLIENT
    _CLIENT = _build_client()
    return _CLIENT


def _reset_client_locked() -> None:
    global _CLIENT
    if _CLIENT is None:
        return
    try:
        _CLIENT.loop_stop()
    except Exception:
        pass
    try:
        _CLIENT.disconnect()
    except Exception:
        pass
    _CLIENT = None


def publish_snapshot(snapshot: Dict[str, Any]) -> None:
    payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    attempts = 0
    delay = 1.0
    while attempts < 5:
        attempts += 1
        with _CLIENT_LOCK:
            client = _get_client_locked()
        try:
            info = client.publish(
                cfg.MQTT_TOPIC_PROXMOX_ESTADO,
                payload=payload,
                qos=cfg.MQTT_QOS_STATE,
                retain=cfg.MQTT_RETAIN_STATE,
            )
            info.wait_for_publish()
            if info.is_published():
                return
            raise RuntimeError("MQTT publish no confirmado")
        except Exception as exc:
            logger.log(f"MQTT publish fallo (intento {attempts}): {exc}", "PVE/MQTT")
            with _CLIENT_LOCK:
                _reset_client_locked()
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError("MQTT publish excedio reintentos")
