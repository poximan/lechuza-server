import json
from typing import Any

import config
from src.utils import timebox

_manager = None  # instancia de MqttClientManager


def set_manager(manager) -> None:
    global _manager
    _manager = manager


def _safe_publish(topic: str, payload: Any, qos: int, retain: bool) -> None:
    if _manager is None:
        return
    try:
        _manager.publish(topic, payload, qos=qos, retain=retain)
    except Exception:
        pass


def publish_email_state(payload: dict) -> None:
    """
    Publica el estado agregado del servidor de correo (retain).
    payload: {"smtp":"conectado","ping_local":"conectado","ping_remoto":"desconectado","ts":"..."}
    """
    _safe_publish(
        config.MQTT_TOPIC_EMAIL_ESTADO,
        json.dumps(payload, ensure_ascii=False),
        qos=config.MQTT_PUBLISH_QOS_STATE,
        retain=config.MQTT_PUBLISH_RETAIN_STATE,
    )


def publish_proxmox_state(payload: dict) -> None:
    """
    Publica el snapshot de estado de Proxmox (retain).
    payload: {"ts":"...","status":"online|offline","node":"...","vms":[...],"missing":[...],"error":str|None}
    """
    _safe_publish(
        config.MQTT_TOPIC_PROXMOX_ESTADO,
        json.dumps(payload, ensure_ascii=False),
        qos=config.MQTT_PUBLISH_QOS_STATE,
        retain=config.MQTT_PUBLISH_RETAIN_STATE,
    )


def publish_email_event(subject: str, ok: bool) -> None:
    """
    Evento de envio de email/alarma (no retain).
    payload: {"type":"email","subject":"...","ok":true|false,"ts":"..."}
    """
    obj = {
        "type": "email",
        "subject": subject,
        "ok": bool(ok),
        "ts": timebox.utc_iso(),
    }
    _safe_publish(
        config.MQTT_TOPIC_EMAIL_EVENT,
        json.dumps(obj, ensure_ascii=False),
        qos=config.MQTT_PUBLISH_QOS_EVENT,
        retain=config.MQTT_PUBLISH_RETAIN_EVENT,
    )
