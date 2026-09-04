import os

from src.persistencia.configuracion_base_datos import DATABASE_DIR


def _env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _req(name: str, *aliases: str) -> str:
    value = _env(name, *aliases)
    if value is None or not str(value).strip():
        raise EnvironmentError(f"Falta variable obligatoria: {name}")
    return value


def _req_int(name: str, *aliases: str) -> int:
    raw = _req(name, *aliases)
    try:
        return int(raw)
    except ValueError as exc:
        raise EnvironmentError(
            f"{name} debe ser un entero; recibido={raw!r}"
        ) from exc


def _req_int_range(name: str, minimum: int, maximum: int, *aliases: str) -> int:
    value = _req_int(name, *aliases)
    if value < minimum or value > maximum:
        raise EnvironmentError(
            f"{name} fuera de rango: esperado={minimum}..{maximum}, recibido={value}"
        )
    return value


def _req_positive_int(name: str, *aliases: str) -> int:
    return _req_int_range(name, 1, 2_147_483_647, *aliases)


def _req_bool(name: str, *aliases: str) -> bool:
    raw = _req(name, *aliases)
    normalized = raw.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise EnvironmentError(
        f"{name} debe ser booleano; recibido={raw!r}"
    )


# ------------------ Conexiones Modbus ------------------
MW_EXEMYS = {
    "name": "mw-exemys",
    "host": _req("MODBUS_COLLECTOR_MW_EXEMYS_MB_HOST"),
    "port": _req_int_range("MODBUS_COLLECTOR_MW_EXEMYS_MB_PORT", 1, 65535),
    "unit_id": _req_int_range("MODBUS_COLLECTOR_MW_EXEMYS_MB_ID", 0, 255),
    "register_count": _req_int_range("MODBUS_COLLECTOR_MW_EXEMYS_MB_COUNT", 16, 125),
    "interval_seconds": _req_positive_int("MODBUS_COLLECTOR_MW_EXEMYS_MB_INTERVAL_SECONDS"),
    "timeout_seconds": _req_positive_int("MODBUS_COLLECTOR_MW_EXEMYS_MB_TIMEOUT_SECONDS"),
}

MODBUS_READ_ATTEMPTS = _req_int_range(
    "MODBUS_COLLECTOR_MB_READ_ATTEMPTS",
    3,
    3,
)
RELAY_TIMEOUT_SECONDS = _req_positive_int(
    "MODBUS_COLLECTOR_RELAY_MB_TIMEOUT_SECONDS"
)
GENERATOR_TIMEOUT_SECONDS = _req_positive_int(
    "MODBUS_COLLECTOR_GE_MB_TIMEOUT_SECONDS"
)

EDIF_ESTIVARIZ_GE = {
    "name": "edif-estivariz",
    "grd_id": _req_positive_int("EDIF_ESTIVARIZ_GE_GRD_ID"),
    "register_offset": _req_positive_int("EDIF_ESTIVARIZ_GE_REGISTER_OFFSET"),
    "line_bit_index": _req_int_range("EDIF_ESTIVARIZ_GE_LINE_BIT_INDEX", 0, 15),
    "generator_bit_index": _req_int_range("EDIF_ESTIVARIZ_GE_GENERATOR_BIT_INDEX", 0, 15),
    "topic": _req("EDIF_ESTIVARIZ_GE_TOPIC"),
}

EDIF_FONTANA_GE = {
    "name": "edif-fontana",
    "host": _req("MODBUS_COLLECTOR_EDIF_FONTANA_MB_HOST"),
    "port": _req_int_range("MODBUS_COLLECTOR_EDIF_FONTANA_MB_PORT", 1, 65535),
    "unit_id": _req_int_range("MODBUS_COLLECTOR_EDIF_FONTANA_MB_ID", 0, 255),
    "register_offset": _req_int_range("EDIF_FONTANA_GE_REGISTER_OFFSET", 0, 65535),
    "register_count": _req_int_range("EDIF_FONTANA_GE_REGISTER_COUNT", 1, 125),
    "line_bit_index": _req_int_range("EDIF_FONTANA_GE_LINE_BIT_INDEX", 0, 15),
    "generator_bit_index": _req_int_range("EDIF_FONTANA_GE_GENERATOR_BIT_INDEX", 0, 15),
    "interval_seconds": _req_positive_int("EDIF_FONTANA_GE_INTERVAL_SECONDS"),
    "topic": _req("EDIF_FONTANA_GE_TOPIC"),
}

# ------------------ Rutas de datos ------------------
HISTORY_PAGE_SIZE = _req_positive_int("MODBUS_HISTORY_PAGE_SIZE")
OBS_STATE_FILE = os.path.join(DATABASE_DIR, "modbus-collector-state.json")
GRD_FAILURE_THRESHOLD = _req_positive_int("MODBUS_COLLECTOR_GRD_FAILURE_THRESHOLD")
RELAY_LATEST_FAULT_ADDRESS = _req_int_range("MODBUS_RELAY_LATEST_FAULT_ADDRESS", 0, 65535)
RELAY_FAULT_REGISTER_COUNT = _req_int_range("MODBUS_RELAY_FAULT_REGISTER_COUNT", 15, 15)
ALARM_INTERNAL_API_KEY = _req("ALARM_INTERNAL_API_KEY")
ALARM_OUTBOX_FILE = os.path.join(DATABASE_DIR, "alarm-events.json")
GLOBAL_RED_THRESHOLD = float(_req("GLOBAL_THRESHOLD_ROJO"))
if not 0 <= GLOBAL_RED_THRESHOLD <= 100:
    raise EnvironmentError("GLOBAL_THRESHOLD_ROJO debe estar entre 0 y 100")

# ------------------ MQTT ------------------
MQTT_BROKER_HOST = _req("MQTT_BROKER_HOST")
MQTT_BROKER_PORT = _req_int_range("MQTT_BROKER_PORT", 1, 65535)
MQTT_BROKER_USERNAME = _req("MQTT_BROKER_USERNAME")
MQTT_BROKER_PASSWORD = _req("MQTT_BROKER_PASSWORD")
MQTT_BROKER_USE_TLS = _req_bool("MQTT_BROKER_USE_TLS")
MQTT_TLS_INSECURE = _req_bool("MQTT_TLS_INSECURE")
MQTT_KEEPALIVE = _req_positive_int("MQTT_BROKER_KEEPALIVE")
MQTT_RECONNECT_DELAY_MIN = _req_positive_int("MQTT_RECONNECT_DELAY_MIN")
MQTT_RECONNECT_DELAY_MAX = _req_positive_int("MQTT_RECONNECT_DELAY_MAX")
MQTT_PUBLISH_TIMEOUT_SECONDS = _req_positive_int("MQTT_PUBLISH_TIMEOUT_SECONDS")
if MQTT_RECONNECT_DELAY_MAX < MQTT_RECONNECT_DELAY_MIN:
    raise EnvironmentError(
        "MQTT_RECONNECT_DELAY_MAX no puede ser menor que MQTT_RECONNECT_DELAY_MIN"
    )

MQTT_TOPIC_GRADO = _req("MQTT_TOPIC_GRADO")
MQTT_TOPIC_GRDS = _req("MQTT_TOPIC_GRDS")

MQTT_PUBLISH_QOS_STATE = _req_int_range("MQTT_PUBLISH_QOS_STATE", 0, 2)
MQTT_PUBLISH_RETAIN_STATE = _req_bool("MQTT_PUBLISH_RETAIN_STATE")
