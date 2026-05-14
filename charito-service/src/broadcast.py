import json
import os
import threading
import ssl
import certifi

import paho.mqtt.client as mqtt

MQTT_STATE_TOPIC = None

_lock = threading.RLock()
_client: mqtt.Client | None = None
_last_state_payload: str | None = None


def broadcast_state(snapshot: dict) -> None:
    if not isinstance(snapshot, dict):
        raise TypeError("El snapshot charito debe ser un objeto JSON")
    items = snapshot.get("items")
    if not isinstance(items, list):
        raise ValueError("El snapshot charito debe contener una lista 'items'")
    if not items:
        return

    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    global _last_state_payload
    if _last_state_payload == body:
        return
    _publish_once(body)
    _last_state_payload = body


def _publish_once(body: str) -> None:
    client = _get_client()
    topic = _state_topic()
    info = client.publish(topic, payload=body, qos=1, retain=True)
    info.wait_for_publish()


def close_mqtt() -> None:
    global _client
    with _lock:
        client = _client
        _client = None
    if client is None:
        return
    client.loop_stop()
    client.disconnect()


def _get_client() -> mqtt.Client:
    global _client
    with _lock:
        if _client is not None and _client.is_connected():
            return _client
        client = mqtt.Client(clean_session=True)
        host = _require("MQTT_BROKER_HOST")
        port = int(_require("MQTT_BROKER_PORT"))
        username = _require("MQTT_BROKER_USERNAME")
        password = _require("MQTT_BROKER_PASSWORD")
        use_tls = _truthy(_require("MQTT_BROKER_USE_TLS"))
        insecure = _truthy(_require("MQTT_TLS_INSECURE"))
        keepalive = int(_require("MQTT_BROKER_KEEPALIVE"))
        client.username_pw_set(username, password)
        if use_tls:
            context = ssl.create_default_context(cafile=certifi.where())
            try:
                context.minimum_version = ssl.TLSVersion.TLSv1_2
            except AttributeError:
                context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            if insecure:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            client.tls_set_context(context)
        client.connect(host, port, keepalive=keepalive)
        client.loop_start()
        _client = client
        return client


def _state_topic() -> str:
    global MQTT_STATE_TOPIC
    if MQTT_STATE_TOPIC is None:
        MQTT_STATE_TOPIC = _require("CHARITO_MQTT_STATE_TOPIC")
    return MQTT_STATE_TOPIC


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable obligatoria: {name}")
    return value.strip()


def _truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}
