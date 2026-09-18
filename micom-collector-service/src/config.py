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
RELAY_INTERVAL_SECONDS = positive_integer("MICOM_POLL_INTERVAL_SECONDS")
DATA_DIR = os.path.abspath(required("MICOM_DATA_DIR"))
OBS_STATE_FILE = os.path.join(DATA_DIR, "micom-state.json")
