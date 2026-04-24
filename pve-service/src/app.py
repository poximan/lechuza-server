from fastapi import FastAPI, HTTPException
from typing import Dict, Any

from . import config as cfg
from .collector import PveCollector
from .history import update_history, load_history_for_dashboard
from .mqtt_pub import publish_snapshot
from .poller import Poller
from .repository import SnapshotRepository
from .utils import timebox


app = FastAPI(title="pve-service", version="1.1.0")

_collector = PveCollector()
_repository = SnapshotRepository()
_STALE_SECONDS = cfg.PVE_POLL_INTERVAL_SECONDS * 2


def _handle_snapshot(snapshot: Dict[str, Any]) -> None:
    _repository.store(snapshot)
    update_history(
        snapshot,
        poll_seconds=cfg.PVE_POLL_INTERVAL_SECONDS,
        hours=cfg.PVE_HISTORY_HOURS,
    )


_poller = Poller(
    interval_seconds=cfg.PVE_POLL_INTERVAL_SECONDS,
    collect_fn=_collector.collect,
    on_snapshot=_handle_snapshot,
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
    return {"status": "up"}


@app.get("/api/pve/state")
def get_state() -> Dict[str, Any]:
    snapshot = _repository.read()
    if not snapshot:
        raise HTTPException(status_code=503, detail="Sin datos disponibles")
    age = _repository.age_seconds()
    if age is None or age > _STALE_SECONDS:
        raise HTTPException(status_code=503, detail="Estado desactualizado")
    return snapshot


@app.get("/api/pve/history")
def get_history() -> Dict[str, Any]:
    vms, meta = load_history_for_dashboard()
    return {"vms": vms, "meta": meta}
