import os


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise EnvironmentError(f"Falta variable obligatoria: {name}")
    return value


def integer(name: str, minimum: int = 0) -> int:
    value = int(required(name))
    if value < minimum:
        raise EnvironmentError(f"{name} debe ser mayor o igual a {minimum}")
    return value


def boolean(name: str) -> bool:
    value = required(name).lower()
    if value not in {"1", "0", "true", "false", "yes", "no", "on", "off"}:
        raise EnvironmentError(f"{name} debe ser booleano")
    return value in {"1", "true", "yes", "on"}


DATA_DIR = os.path.abspath(required("GENERATOR_DATA_DIR"))
STATE_FILE = os.path.join(DATA_DIR, "generator-state.json")
ALARM_OUTBOX_FILE = os.path.join(DATA_DIR, "alarm-events.json")
ALARM_INTERNAL_API_KEY = required("ALARM_INTERNAL_API_KEY")
MODBUS_TRANSPORT_BASE_URL = required("MODBUS_TRANSPORT_BASE_URL")
MODBUS_TRANSPORT_API_KEY = required("MODBUS_TRANSPORT_API_KEY")
MODBUS_TRANSPORT_TIMEOUT_SECONDS = integer(
    "MODBUS_TRANSPORT_TIMEOUT_SECONDS", 1
)
MW_EXEMYS = {
    "unit_id": integer("GENERATOR_ESTIVARIZ_UNIT_ID", 1),
    "register_count": integer("GENERATOR_ESTIVARIZ_REGISTER_COUNT", 1),
    "interval_seconds": integer("GENERATOR_ESTIVARIZ_POLL_INTERVAL_SECONDS", 1),
}
EDIF_ESTIVARIZ_GE = {
    "name": "edif-estivariz",
    "grd_id": integer("EDIF_ESTIVARIZ_GE_GRD_ID", 1),
    "register_offset": integer("EDIF_ESTIVARIZ_GE_REGISTER_OFFSET"),
    "line_bit_index": integer("EDIF_ESTIVARIZ_GE_LINE_BIT_INDEX"),
    "generator_bit_index": integer("EDIF_ESTIVARIZ_GE_GENERATOR_BIT_INDEX"),
    "topic": required("EDIF_ESTIVARIZ_GE_TOPIC"),
}
EDIF_FONTANA_GE = {
    "name": "edif-fontana",
    "unit_id": integer("GENERATOR_FONTANA_UNIT_ID", 1),
    "register_offset": integer("EDIF_FONTANA_GE_REGISTER_OFFSET"),
    "register_count": integer("EDIF_FONTANA_GE_REGISTER_COUNT", 1),
    "line_bit_index": integer("EDIF_FONTANA_GE_LINE_BIT_INDEX"),
    "generator_bit_index": integer("EDIF_FONTANA_GE_GENERATOR_BIT_INDEX"),
    "interval_seconds": integer("EDIF_FONTANA_GE_INTERVAL_SECONDS", 1),
    "topic": required("EDIF_FONTANA_GE_TOPIC"),
}
MQTT_BROKER_HOST = required("MQTT_BROKER_HOST")
MQTT_BROKER_PORT = integer("MQTT_BROKER_PORT", 1)
MQTT_BROKER_USERNAME = required("MQTT_BROKER_USERNAME")
MQTT_BROKER_PASSWORD = required("MQTT_BROKER_PASSWORD")
MQTT_BROKER_USE_TLS = boolean("MQTT_BROKER_USE_TLS")
MQTT_TLS_INSECURE = boolean("MQTT_TLS_INSECURE")
MQTT_KEEPALIVE = integer("MQTT_BROKER_KEEPALIVE", 1)
MQTT_RECONNECT_DELAY_MIN = integer("MQTT_RECONNECT_DELAY_MIN", 1)
MQTT_RECONNECT_DELAY_MAX = integer("MQTT_RECONNECT_DELAY_MAX", 1)
MQTT_PUBLISH_TIMEOUT_SECONDS = integer("MQTT_PUBLISH_TIMEOUT_SECONDS", 1)
MQTT_PUBLISH_QOS_STATE = integer("MQTT_PUBLISH_QOS_STATE")
MQTT_PUBLISH_RETAIN_STATE = boolean("MQTT_PUBLISH_RETAIN_STATE")
