from __future__ import annotations

import threading
from typing import Any

import requests
from timeauthority import get_time_authority

from . import config, db
from .frequency_service import FrequencyService


_TIME = get_time_authority()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_SOURCE_SESSION = requests.Session()
_MENSAGELO_SESSION = requests.Session()
_CATALOG_ETAGS: dict[str, str] = {}
_ACKNOWLEDGED_CURSORS: dict[str, int] = {}
_STATUS_LOCK = threading.Lock()
_STATUS: dict[str, Any] = {
    "state": "starting",
    "last_success_at": None,
    "last_error": None,
}


def _source_headers() -> dict[str, str]:
    return {"X-API-Key": config.ALARM_INTERNAL_API_KEY}


def _mensagelo_headers(dispatch_id: str | None = None) -> dict[str, str]:
    headers = {"X-API-Key": config.MENSAGELO_API_KEY}
    if dispatch_id is not None:
        headers["Idempotency-Key"] = dispatch_id
    return headers


def _get_json(
    session: requests.Session,
    url: str,
    *,
    headers: dict[str, str],
    params=None,
) -> dict[str, Any]:
    response = session.get(
        url,
        headers=headers,
        params=params,
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Respuesta JSON invalida de {url}")
    return payload


def _sync_catalog(source: config.AlarmSource, frequency: FrequencyService) -> None:
    headers = _source_headers()
    known_etag = _CATALOG_ETAGS.get(source.source_id)
    if known_etag is not None:
        headers["If-None-Match"] = known_etag
    response = _SOURCE_SESSION.get(
        f"{source.base_url}/api/v1/alarms/catalog",
        headers=headers,
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    if response.status_code == 304:
        return
    response.raise_for_status()
    catalog = response.json()
    if not isinstance(catalog, dict):
        raise ValueError(f"Catalogo invalido de {source.source_id}")
    if catalog.get("source_id") != source.source_id:
        raise ValueError(
            f"Identidad invalida para fuente {source.source_id}: {catalog.get('source_id')}"
        )
    alarms = catalog.get("alarms")
    if not isinstance(alarms, list):
        raise ValueError(f"Catalogo invalido de {source.source_id}")
    alarm_keys = [
        alarm.get("alarm_key")
        for alarm in alarms
        if isinstance(alarm, dict)
    ]
    if len(alarm_keys) != len(alarms) or len(set(alarm_keys)) != len(alarm_keys):
        raise ValueError(
            f"Catalogo con claves invalidas o repetidas de {source.source_id}"
        )
    db.ingest_catalog(source.source_id, alarms)
    frequency.update_catalog(source.source_id, alarms)
    etag = response.headers.get("ETag")
    if etag:
        _CATALOG_ETAGS[source.source_id] = etag


def _sync_source(source: config.AlarmSource, frequency: FrequencyService) -> None:
    _sync_catalog(source, frequency)

    cursor = db.get_source_cursor(source.source_id)
    while True:
        response = _get_json(
            _SOURCE_SESSION,
            f"{source.base_url}/api/v1/alarms/events",
            headers=_source_headers(),
            params={"after_event_id": cursor, "limit": 1000},
        )
        if response.get("source_id") != source.source_id:
            raise ValueError(f"Eventos con identidad invalida de {source.source_id}")
        events = response.get("events")
        if not isinstance(events, list):
            raise ValueError(f"Eventos invalidos de {source.source_id}")
        has_more = response.get("has_more")
        if not isinstance(has_more, bool):
            raise ValueError(f"Paginacion invalida de {source.source_id}")
        cursor, qualifications, observations = db.ingest_events(source.source_id, events)
        frequency.record_observations(observations)
        frequency.record_qualifications(qualifications)
        if cursor > _ACKNOWLEDGED_CURSORS.get(source.source_id, 0):
            acknowledgement = _SOURCE_SESSION.post(
                f"{source.base_url}/api/v1/alarms/events/ack",
                headers=_source_headers(),
                json={"through_event_id": cursor},
                timeout=config.HTTP_TIMEOUT_SECONDS,
            )
            acknowledgement.raise_for_status()
            _ACKNOWLEDGED_CURSORS[source.source_id] = cursor
        if not has_more:
            break
    frequency.record_observations(db.initialize_catalog_baselines(source.source_id))


def _dispatch_pending() -> None:
    for item in db.pending_dispatches():
        dispatch_id = str(item["dispatch_id"])
        try:
            response = _MENSAGELO_SESSION.post(
                f"{config.MENSAGELO_BASE_URL}/send_async",
                headers=_mensagelo_headers(dispatch_id),
                json={
                    "recipients": item["recipients"],
                    "subject": item["subject"],
                    "body": item["body"],
                    "message_type": "alarm_event",
                },
                timeout=config.HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except Exception as exc:
            db.mark_dispatch_error(
                dispatch_id,
                f"{type(exc).__name__}: {exc}",
                _TIME.utc_iso(),
            )
        else:
            db.mark_dispatch_accepted(dispatch_id, _TIME.utc_iso())


def _sync_dispatch_results() -> None:
    response = _get_json(
        _MENSAGELO_SESSION,
        f"{config.MENSAGELO_BASE_URL}/internal/dispatches",
        headers=_mensagelo_headers(),
        params={"limit": 5000},
    )
    dispatches = response.get("dispatches")
    if not isinstance(dispatches, list):
        raise ValueError("Contrato invalido de despachos Mensagelo")
    db.ingest_dispatches(dispatches)


def sync_once(frequency: FrequencyService) -> None:
    frequency.refresh_if_new_day()
    failures = []
    synchronized_sources = set()
    configured_sources = {source.source_id for source in config.ALARM_SOURCES}
    db.reconcile_configured_sources(configured_sources)
    frequency.retain_sources(configured_sources)
    for source in config.ALARM_SOURCES:
        try:
            _sync_source(source, frequency)
            synchronized_sources.add(source.source_id)
        except Exception as exc:
            failures.append(f"{source.source_id}: {type(exc).__name__}: {exc}")

    frequency.record_qualifications(
        db.process_due_transitions(_TIME.utc_iso(), list(config.ALARM_RECIPIENTS), synchronized_sources)
    )
    _dispatch_pending()
    try:
        _sync_dispatch_results()
    except Exception as exc:
        failures.append(f"mensagelo: {type(exc).__name__}: {exc}")
    if failures:
        raise RuntimeError("; ".join(failures))


def _run(frequency: FrequencyService) -> None:
    while not _STOP.is_set():
        try:
            sync_once(frequency)
        except Exception as exc:
            with _STATUS_LOCK:
                _STATUS.update(
                    state="degraded",
                    last_error=f"{type(exc).__name__}: {exc}",
                )
        else:
            with _STATUS_LOCK:
                _STATUS.update(
                    state="ok",
                    last_success_at=_TIME.utc_iso(),
                    last_error=None,
                )
        _STOP.wait(config.POLL_INTERVAL_SECONDS)
    _SOURCE_SESSION.close()
    _MENSAGELO_SESSION.close()


def start(frequency: FrequencyService) -> None:
    global _THREAD
    if _THREAD is None or not _THREAD.is_alive():
        _STOP.clear()
        _THREAD = threading.Thread(target=_run, args=(frequency,), name="alarmero-sync", daemon=True)
        _THREAD.start()


def stop() -> None:
    _STOP.set()
    if _THREAD is not None:
        _THREAD.join(timeout=2)


def status() -> dict[str, Any]:
    with _STATUS_LOCK:
        return dict(_STATUS)
