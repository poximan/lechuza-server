import os

def _req(name: str) -> str:
    v = os.getenv(name)
    if v is None or not v.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return v.strip()

def _parse_ids(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]

def _req_bool(name: str) -> bool:
    return _req(name).lower() in {"1", "true", "yes", "on"}

PVE_BASE_URL = _req("PVE_BASE_URL")
PVE_API_TOKEN = _req("PVE_API_TOKEN")
PVE_NODE_NAME = _req("PVE_NODE_NAME")
PVE_VHOST_IDS = _parse_ids(_req("PVE_VHOST_IDS"))
PVE_HTTP_TIMEOUT_SECONDS = int(_req("PVE_HTTP_TIMEOUT_SECONDS"))
PVE_VERIFY_SSL = _req_bool("PVE_VERIFY_SSL")
_ca_bundle = os.getenv("PVE_CA_BUNDLE")
if _ca_bundle:
    if not os.path.exists(_ca_bundle):
        raise EnvironmentError(f"PVE_CA_BUNDLE apunta a un archivo inexistente: {_ca_bundle}")
    PVE_CA_BUNDLE = _ca_bundle
else:
    PVE_CA_BUNDLE = None
PVE_POLL_INTERVAL_SECONDS = int(_req("PVE_POLL_INTERVAL_SECONDS"))
PVE_HISTORY_HOURS = int(_req("PVE_HISTORY_HOURS"))
PVE_MQTT_PUBLISH_FACTOR = int(_req("PVE_MQTT_PUBLISH_FACTOR"))

# MQTT publication for Panelito
MQTT_TOPIC_PROXMOX_ESTADO = _req("MQTT_TOPIC_PROXMOX_ESTADO")
MQTT_QOS_STATE = int(_req("MQTT_PUBLISH_QOS_STATE"))
MQTT_RETAIN_STATE = _req_bool("MQTT_PUBLISH_RETAIN_STATE")

# Filenames for persistence
DATA_DIR = _req("PVE_DATA_DIR")
STATE_FILE = _req("PVE_STATE_FILE")
HISTORY_FILE = _req("PVE_HISTORY_FILE")
