from __future__ import annotations

import threading
from typing import Any

import requests
from timeauthority import get_time_authority

from . import config, db


_AUTH = get_time_authority()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_STATUS_LOCK = threading.Lock()
_STATUS: dict[str, Any] = {
    "state": "starting", "last_success_at": None, "last_error": None,
}


def _headers() -> dict[str, str]:
    return {"X-API-Key": config.SOURCE_API_KEY}


def _get_json(url: str, params=None) -> dict:
    response = requests.get(
        url, headers=_headers(), params=params,
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Respuesta JSON invalida de {url}")
    return payload


def sync_once() -> None:
    cursor = db.get_alarm_cursor()
    while True:
        alarms = _get_json(
            f"{config.PANELEXEMYS_BASE_URL}/internal/alarms",
            {"after_event_id": cursor, "event_limit": 1000},
        )
        db.ingest_alarm_snapshot(alarms)
        cursor = int(alarms.get("last_event_id") or cursor)
        if not alarms.get("has_more"):
            break
    dispatches = _get_json(
        f"{config.MENSAGELO_BASE_URL}/internal/dispatches",
        {"limit": 5000},
    ).get("dispatches")
    if not isinstance(dispatches, list):
        raise ValueError("Contrato invalido de mensagelo")
    db.ingest_dispatches(dispatches)


def _run() -> None:
    while not _STOP.is_set():
        try:
            sync_once()
        except Exception as exc:
            with _STATUS_LOCK:
                _STATUS.update(state="degraded", last_error=f"{type(exc).__name__}: {exc}")
        else:
            with _STATUS_LOCK:
                _STATUS.update(state="ok", last_success_at=_AUTH.utc_iso(), last_error=None)
        _STOP.wait(config.POLL_INTERVAL_SECONDS)


def start() -> None:
    global _THREAD
    if _THREAD is None or not _THREAD.is_alive():
        _STOP.clear()
        _THREAD = threading.Thread(target=_run, name="alarmero-sync", daemon=True)
        _THREAD.start()


def stop() -> None:
    _STOP.set()
    if _THREAD is not None:
        _THREAD.join(timeout=2)


def status() -> dict:
    with _STATUS_LOCK:
        return dict(_STATUS)
