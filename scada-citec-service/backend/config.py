import os
from pathlib import Path


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


BASE_DIR = Path(__file__).resolve().parent
ADAPTER_QUERY_INTERVAL_SECONDS = _req_float("CITEC_ADAPTER_QUERY_INTERVAL_SECONDS")
REFRESH_ON_START = _req_bool("CITEC_REFRESH_ON_START")
SCADA_DAEMON_BASE_URL = _req("SCADA_DAEMON_BASE_URL").rstrip("/")
TAG_REFRESH_INTERVAL_SECONDS = _req_float("CITEC_TAG_REFRESH_INTERVAL_SECONDS")


def _voltage_from_tag(tag: str) -> str:
    tag_lower = (tag or "").lower()
    if "_352_" in tag_lower:
        return "33 kV"
    if "_252_" in tag_lower:
        return "13.2 kV"
    return "13.2 kV"


STATION_LABELS = {
    "ETE": "Estacion Estivariz",
    "EC1": "Estacion Centro",
    "ETSR": "Estacion Sociedad Rural",
    "ETED": "Estacion Doradillo",
}


def station_label_for(prefix: str) -> str:
    if not prefix:
        return "Estacion"
    upper = prefix.upper()
    return STATION_LABELS.get(upper, f"Estacion {upper}")


API_PORT = _req_int("SCADA_CITEC_SERVICE_PORT")

FRONTEND_DIR = BASE_DIR.parent / "frontend"
STATIC_CACHE_SECONDS = _req_int("SCADA_STATIC_CACHE_SECONDS")
