import os


def _req(name: str) -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        raise EnvironmentError(f"Falta variable obligatoria: {name}")
    return str(value).strip()


def _req_int(name: str) -> int:
    return int(_req(name))


def _req_bool(name: str) -> bool:
    return _req(name).lower() in {"1", "true", "yes", "on"}


# ------------------ Modbus middleware ------------------
MB_HOST = _req("MODBUS_MW_MB_HOST")
MB_PORT = _req_int("MODBUS_MW_MB_PORT")
MB_ID = _req_int("MODBUS_MW_MB_ID")
MB_COUNT = _req_int("MODBUS_MW_MB_COUNT")
MB_INTERVAL_SECONDS = _req_int("MODBUS_MW_MB_INTERVAL_SECONDS")

GE_EMAR = {
    "grd_id": _req_int("GE_EMAR_GRD_ID"),
    "register_offset": _req_int("GE_EMAR_REGISTER_OFFSET"),
    "bit_index": _req_int("GE_EMAR_BIT_INDEX"),
    "topic": _req("GE_EMAR_TOPIC"),
}

GRD_DESCRIPTIONS: dict[int, str] = {
    1: "SS - presuriz doradillo",
    2: "SS - pluvial prefectura",
    3: "SS - presuriz agro",
    4: "SE - CD45 Murchison",
    5: "reserva",
    6: "SS - pluvial lugones",
    7: "reserva",
    8: "SE - et doradillo",
    9: "reserva",
    10: "SE - rec2(O) doradillo",
    11: "SE - rec3(N) doradillo",
    12: "reserva",
    13: "SE - et soc.rural",
    14: "SS - edif estivariz GE",
    15: "SE - et juan XXIII",
    16: "reserva",
    17: "SS - pque pesquero",
}

ESCLAVOS_MB: dict[int, str] = {
    1: "NO APLICA - (SE)et soc.rural - plc",
    2: "NO APLICA - (SE)et doradillo - proteccion (no esta?)",
    3: "(SE)et doradillo - proteccion MiCOM CDA03 33KV",
    4: "NO APLICA - (SE)et doradillo - proteccion MiCOM rele cuba",
    5: "(SE)et doradillo - proteccion MiCOM CDA02 33KV",
    6: "(SE)et doradillo - proteccion MiCOM CDA03 13,2KV",
    7: "NO APLICA - (SS)presuriz doradillo - plc",
    8: "NO APLICA - (SE)et juan XXIII - proteccion janitza umg 96s",
    9: "NO APLICA - (SE)et juan XXIII - proteccion janitza umg 96s",
    10: "NO APLICA - (SE)et juan XXIII - proteccion janitza umg 96s",
    11: "NO APLICA - (SE)et juan XXIII - proteccion MiCOM p12x",
    12: "NO APLICA - (SE)et juan XXIII - proteccion MiCOM p12x",
    13: "NO APLICA - (SE)et juan XXIII - proteccion MiCOM p12x",
    14: "NO APLICA - (SE)et juan XXIII - proteccion MiCOM p12x",
}

# ------------------ Data paths ------------------
DATABASE_DIR = _req("MODBUS_MW_DATA_DIR")
DATABASE_NAME = _req("MODBUS_MW_DATABASE_NAME")
OBS_STATE_FILE = os.path.join(DATABASE_DIR, "modbus-mw-state.json")

# ------------------ MQTT ------------------
MQTT_BROKER_HOST = _req("MQTT_BROKER_HOST")
MQTT_BROKER_PORT = _req_int("MQTT_BROKER_PORT")
MQTT_BROKER_USERNAME = _req("MQTT_BROKER_USERNAME")
MQTT_BROKER_PASSWORD = _req("MQTT_BROKER_PASSWORD")
MQTT_BROKER_USE_TLS = _req_bool("MQTT_BROKER_USE_TLS")
MQTT_TLS_INSECURE = _req_bool("MQTT_TLS_INSECURE")
MQTT_KEEPALIVE = _req_int("MQTT_BROKER_KEEPALIVE")
MQTT_CONNECT_TIMEOUT = _req_int("MQTT_CONNECT_TIMEOUT")
MQTT_RECONNECT_DELAY_MIN = _req_int("MQTT_RECONNECT_DELAY_MIN")
MQTT_RECONNECT_DELAY_MAX = _req_int("MQTT_RECONNECT_DELAY_MAX")

MQTT_TOPIC_MODEM_CONEXION = _req("MQTT_TOPIC_MODEM_CONEXION")
MQTT_TOPIC_GRADO = _req("MQTT_TOPIC_GRADO")
MQTT_TOPIC_GRDS = _req("MQTT_TOPIC_GRDS")
MQTT_TOPIC_EMAIL_ESTADO = _req("MQTT_TOPIC_EMAIL_ESTADO")
MQTT_TOPIC_EMAIL_EVENT = _req("MQTT_TOPIC_EMAIL_EVENT")
MQTT_TOPIC_PROXMOX_ESTADO = _req("MQTT_TOPIC_PROXMOX_ESTADO")

MQTT_PUBLISH_QOS_STATE = _req_int("MQTT_PUBLISH_QOS_STATE")
MQTT_PUBLISH_RETAIN_STATE = _req_bool("MQTT_PUBLISH_RETAIN_STATE")
MQTT_PUBLISH_QOS_EVENT = _req_int("MQTT_PUBLISH_QOS_EVENT")
MQTT_PUBLISH_RETAIN_EVENT = _req_bool("MQTT_PUBLISH_RETAIN_EVENT")

HTTP_POLL_SECONDS = _req_int("MODBUS_HTTP_POLL_SECONDS")
MQTT_REFRESH_FACTOR = _req_int("MODBUS_MQTT_REFRESH_FACTOR")
