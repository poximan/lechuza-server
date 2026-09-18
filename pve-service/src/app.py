import threading
from typing import Dict, Any

from fastapi import FastAPI, HTTPException

from . import config as cfg
from .collector import PveCollector
from .history import update_history, load_history_for_dashboard
from .mqtt_pub import publish_snapshot
from .poller import Poller
from .repository import SnapshotRepository
from .alarm_source import PveAlarmSource
from alarm_generator import create_alarm_generator_router


app = FastAPI(title="pve-service", version="1.1.0")

_collector = PveCollector()
_repository = SnapshotRepository()
_alarm_source = PveAlarmSource()
_STALE_SECONDS = cfg.PVE_POLL_INTERVAL_SECONDS * 2
_availability_lock = threading.RLock()
_last_collection_error: Dict[str, Any] | None = None


def _handle_snapshot(snapshot: Dict[str, Any]) -> None:
    global _last_collection_error
    _repository.store(snapshot)
    update_history(
        snapshot,
        poll_seconds=cfg.PVE_POLL_INTERVAL_SECONDS,
        hours=cfg.PVE_HISTORY_HOURS,
    )
    _alarm_source.observe(snapshot)
    with _availability_lock:
        _last_collection_error = None


def _handle_collection_failure(failure: Dict[str, Any]) -> None:
    global _last_collection_error
    _alarm_source.observe(failure)
    with _availability_lock:
        _last_collection_error = dict(failure)


_poller = Poller(
    interval_seconds=cfg.PVE_POLL_INTERVAL_SECONDS,
    collect_fn=_collector.collect,
    on_snapshot=_handle_snapshot,
    on_failure=_handle_collection_failure,
    publish_fn=publish_snapshot,
    publish_every=cfg.PVE_MQTT_PUBLISH_FACTOR,
)


@app.on_event("startup")
def _startup() -> None:
    _poller.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    _poller.stop()


@app.get("/health")
def health() -> Dict[str, str]:
    if not _poller.is_alive():
        raise HTTPException(status_code=503, detail="Recolector PVE detenido")
    return {"status": "up"}


@app.get("/api/pve/state")
def get_state() -> Dict[str, Any]:
    snapshot = _repository.read()
    if not snapshot:
        raise HTTPException(status_code=503, detail="Sin datos disponibles")
    age = _repository.age_seconds()
    with _availability_lock:
        failure = dict(_last_collection_error) if _last_collection_error else None
    snapshot["data_age_seconds"] = age
    snapshot["stale"] = age is None or age > _STALE_SECONDS
    snapshot["source_status"] = "offline" if failure else "online"
    snapshot["source_error"] = failure.get("error") if failure else None
    return snapshot


@app.get("/api/pve/history")
def get_history() -> Dict[str, Any]:
    vms, meta = load_history_for_dashboard()
    return {"vms": vms, "meta": meta}


app.include_router(
    create_alarm_generator_router(
        _alarm_source.outbox,
        cfg.ALARM_INTERNAL_API_KEY,
    )
)
