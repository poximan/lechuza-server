import json
import os
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


def _required_int(name: str) -> int:
    return int(_required(name))


@dataclass(frozen=True)
class AlarmSource:
    source_id: str
    base_url: str


def _parse_sources(raw: str) -> tuple[AlarmSource, ...]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EnvironmentError("ALARMERO_SOURCES_JSON no contiene JSON valido") from exc
    if not isinstance(parsed, list) or not parsed:
        raise EnvironmentError("ALARMERO_SOURCES_JSON debe ser una lista no vacia")
    sources = []
    for item in parsed:
        if not isinstance(item, dict):
            raise EnvironmentError("Cada fuente de alarma debe ser un objeto")
        source_id = str(item.get("id") or "").strip()
        base_url = str(item.get("baseUrl") or "").strip().rstrip("/")
        if not source_id or not base_url:
            raise EnvironmentError("Cada fuente requiere id y baseUrl")
        sources.append(AlarmSource(source_id, base_url))
    if len({source.source_id for source in sources}) != len(sources):
        raise EnvironmentError("ALARMERO_SOURCES_JSON repite identificadores")
    return tuple(sources)


def _parse_recipients(raw: str) -> tuple[str, str]:
    recipients = tuple(item.strip() for item in raw.split(",") if item.strip())
    if len(recipients) != 2 or len(set(recipients)) != 2:
        raise EnvironmentError("ALARM_RECIPIENTS debe declarar dos destinatarios distintos")
    return recipients


SERVICE_HOST = _required("SERVICE_HOST")
SERVICE_PORT = _required_int("SERVICE_PORT")
DATABASE_DIR = Path(_required("DATABASE_DIR"))
DATABASE_NAME = _required("DATABASE_NAME")
if Path(DATABASE_NAME).name != DATABASE_NAME:
    raise EnvironmentError("DATABASE_NAME debe contener solo el nombre del archivo")
DATABASE_PATH = DATABASE_DIR / DATABASE_NAME
ALARM_SOURCES = _parse_sources(_required("ALARMERO_SOURCES_JSON"))
ALARM_INTERNAL_API_KEY = _required("ALARM_INTERNAL_API_KEY")
MENSAGELO_BASE_URL = _required("MENSAGELO_BASE_URL").rstrip("/")
MENSAGELO_API_KEY = _required("MENSAGELO_API_KEY")
ALARM_RECIPIENTS = _parse_recipients(_required("ALARM_RECIPIENTS"))
ALARM_SUBJECT_PREFIX = _required("ALARM_SUBJECT_PREFIX")
HTTP_TIMEOUT_SECONDS = _required_int("HTTP_TIMEOUT_SECONDS")
POLL_INTERVAL_SECONDS = _required_int("POLL_INTERVAL_SECONDS")

if HTTP_TIMEOUT_SECONDS < 1:
    raise EnvironmentError("HTTP_TIMEOUT_SECONDS debe ser mayor que cero")
if POLL_INTERVAL_SECONDS < 1:
    raise EnvironmentError("POLL_INTERVAL_SECONDS debe ser mayor que cero")
