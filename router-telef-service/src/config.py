import os


def _req(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


def _req_int(name: str) -> int:
    return int(_req(name))


def _req_float(name: str) -> float:
    return float(_req(name))


def _req_bool(name: str) -> bool:
    return _req(name).lower() in {"1", "true", "yes", "on"}


TARGET_IP = _req("TARGET_IP")
TARGET_PORT = _req_int("TARGET_PORT")
PROBE_INTERVAL_SECONDS = _req_int("PROBE_INTERVAL_SECONDS")

CHECK_HOST_BASE_URL = _req("CHECK_HOST_BASE_URL")
CHECK_HOST_MAX_NODES = _req_int("CHECK_HOST_MAX_NODES")
CHECK_HOST_SUCCESS_LATENCY_SECONDS = _req_float("CHECK_HOST_SUCCESS_LATENCY_SECONDS")
CHECK_HOST_RESULT_TIMEOUT_SECONDS = _req_float("CHECK_HOST_RESULT_TIMEOUT_SECONDS")
CHECK_HOST_POLL_INTERVAL_SECONDS = _req_float("CHECK_HOST_POLL_INTERVAL_SECONDS")
CHECK_HOST_REQUEST_TIMEOUT_SECONDS = _req_float("CHECK_HOST_REQUEST_TIMEOUT_SECONDS")

STATUS_TOPIC = _req("MQTT_TOPIC_MODEM_CONEXION")
MQTT_QOS = _req_int("MQTT_PUBLISH_QOS_STATE")
MQTT_RETAIN = _req_bool("MQTT_PUBLISH_RETAIN_STATE")
MQTT_CLIENT_ID = _req("MQTT_ROUTER_CLIENT_ID")

MQTT_BROKER_HOST = _req("MQTT_BROKER_HOST")
MQTT_BROKER_PORT = _req_int("MQTT_BROKER_PORT")
MQTT_BROKER_USERNAME = _req("MQTT_BROKER_USERNAME")
MQTT_BROKER_PASSWORD = _req("MQTT_BROKER_PASSWORD")
MQTT_BROKER_KEEPALIVE = _req_int("MQTT_BROKER_KEEPALIVE")
MQTT_RECONNECT_DELAY_MIN = _req_int("MQTT_RECONNECT_DELAY_MIN")
MQTT_RECONNECT_DELAY_MAX = _req_int("MQTT_RECONNECT_DELAY_MAX")
MQTT_BROKER_USE_TLS = _req_bool("MQTT_BROKER_USE_TLS")
MQTT_TLS_INSECURE = _req_bool("MQTT_TLS_INSECURE")

MQTT_BROKER_CA_CERT = os.getenv("MQTT_BROKER_CA_CERT")
MQTT_CLIENT_CERTFILE = os.getenv("MQTT_CLIENT_CERTFILE")
MQTT_CLIENT_KEYFILE = os.getenv("MQTT_CLIENT_KEYFILE")
