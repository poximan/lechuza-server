import os


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable obligatoria: {name}")
    return value.strip()


DATABASE_DIR = os.path.abspath(_required("MODBUS_COLLECTOR_DATA_DIR"))
DATABASE_NAME = _required("MODBUS_COLLECTOR_DATABASE_NAME")
if os.path.basename(DATABASE_NAME) != DATABASE_NAME or DATABASE_NAME in {".", ".."}:
    raise EnvironmentError(
        "MODBUS_COLLECTOR_DATABASE_NAME debe contener solo el nombre del archivo"
    )
DATABASE_FILE = os.path.join(DATABASE_DIR, DATABASE_NAME)
