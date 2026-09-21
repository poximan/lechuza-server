import json
import os


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise EnvironmentError(f"Falta variable obligatoria: {name}")
    return value


def positive_integer(name: str) -> int:
    value = int(required(name))
    if value < 1:
        raise EnvironmentError(f"{name} debe ser mayor que cero")
    return value


MODBUS_TRANSPORT_BASE_URL = required("MODBUS_TRANSPORT_BASE_URL")
MODBUS_TRANSPORT_API_KEY = required("MODBUS_TRANSPORT_API_KEY")
MODBUS_TRANSPORT_TIMEOUT_SECONDS = positive_integer(
    "MODBUS_TRANSPORT_TIMEOUT_SECONDS"
)
POLL_INTERVAL_SECONDS = positive_integer("JANITZA_POLL_INTERVAL_SECONDS")
DATA_DIR = os.path.abspath(required("JANITZA_DATA_DIR"))
STATE_FILE = os.path.join(DATA_DIR, "janitza-state.json")
ANALYZERS = json.loads(required("JANITZA_ANALYZERS_JSON"))

if not isinstance(ANALYZERS, list) or not ANALYZERS:
    raise EnvironmentError("JANITZA_ANALYZERS_JSON debe ser una lista no vacia")

analyzer_ids: set[int] = set()
for item in ANALYZERS:
    if (
        not isinstance(item, dict)
        or type(item.get("id")) is not int
        or not 1 <= item["id"] <= 247
        or not str(item.get("name", "")).strip()
    ):
        raise EnvironmentError("Cada analizador Janitza requiere id Modbus y name")
    if item["id"] in analyzer_ids:
        raise EnvironmentError(f"ID Janitza duplicado: {item['id']}")
    analyzer_ids.add(item["id"])
