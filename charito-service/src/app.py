import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException

from config import load_service_config_from_json
from broadcast import broadcast_whitelist
from poller import CharitoPoller
from state import StateStore


def _req(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


def _req_int(name: str) -> int:
    return int(_req(name))


def _req_float(name: str) -> float:
    return float(_req(name))


DATA_DIR = Path(_req("CHARITO_DATA_DIR"))
STATE_FILE = Path(_req("CHARITO_STATE_FILE"))
TARGETS_JSON = _req("CHARITO_TARGETS_JSON")
service_cfg = load_service_config_from_json(TARGETS_JSON)
POLL_INTERVAL = _req_int("CHARITO_POLL_INTERVAL_SECONDS")
HTTP_TIMEOUT = _req_float("CHARITO_HTTP_TIMEOUT_SECONDS")

app = FastAPI(title="charito-service", version="2.0.0")

os.makedirs(DATA_DIR, exist_ok=True)
state_store = StateStore(Path(STATE_FILE))
targets = service_cfg.instances

poller = CharitoPoller(
    targets=targets,
    state=state_store,
    poll_interval=POLL_INTERVAL,
    request_timeout=HTTP_TIMEOUT,
)


@app.on_event("startup")
def startup_event() -> None:
    try:
        broadcast_whitelist(targets)
    except Exception:
        pass
    poller.start()


@app.on_event("shutdown")
def shutdown_event() -> None:
    poller.stop()


@app.get("/health")
def health() -> dict:
    return {"status": "up", "targets": len(targets)}


@app.get("/api/charito/instances")
def list_instances(since: Optional[str] = None) -> dict:
    return state_store.build_index(since)


@app.get("/api/charito/instances/{instance_id}")
def get_instance(instance_id: str) -> dict:
    data = state_store.build_state([instance_id]).get("items", [])
    if not data:
        raise HTTPException(status_code=404, detail="instance not found")
    return data[0]


@app.get("/api/charito/state")
def full_state(ids: Optional[str] = None) -> dict:
    subset = None
    if ids:
        subset = [part.strip() for part in ids.split(",") if part.strip()]
    return state_store.build_state(subset)
