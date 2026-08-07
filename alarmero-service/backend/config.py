import os
from pathlib import Path


def _req(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


def _req_int(name: str) -> int:
    return int(_req(name))


SERVICE_HOST = _req("SERVICE_HOST")
SERVICE_PORT = _req_int("SERVICE_PORT")
DATABASE_DIR = Path(_req("DATABASE_DIR"))
DATABASE_NAME = _req("DATABASE_NAME")
DATABASE_PATH = DATABASE_DIR / DATABASE_NAME
PANELEXEMYS_BASE_URL = _req("PANELEXEMYS_BASE_URL").rstrip("/")
MENSAGELO_BASE_URL = _req("MENSAGELO_BASE_URL").rstrip("/")
SOURCE_API_KEY = _req("SOURCE_API_KEY")
HTTP_TIMEOUT_SECONDS = _req_int("HTTP_TIMEOUT_SECONDS")
POLL_INTERVAL_SECONDS = _req_int("POLL_INTERVAL_SECONDS")

if HTTP_TIMEOUT_SECONDS < 1:
    raise EnvironmentError("HTTP_TIMEOUT_SECONDS debe ser mayor que cero")
if POLL_INTERVAL_SECONDS < 1:
    raise EnvironmentError("POLL_INTERVAL_SECONDS debe ser mayor que cero")
