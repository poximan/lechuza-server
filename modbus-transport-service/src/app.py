from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from timeauthority import get_time_authority

from .config import (
    API_KEY,
    QUEUE_MAXSIZE,
    WAIT_TIMEOUT_SECONDS,
    load_endpoint_configs,
)
from .contracts import ConnectRequest, ReadRequest
from .endpoint_worker import EndpointWorker


_TIME = get_time_authority()
workers = {
    config.name: EndpointWorker(config, QUEUE_MAXSIZE)
    for config in load_endpoint_configs()
}
app = FastAPI(title="modbus-transport-service", version="1.1.0")


def authorize(value: str | None) -> None:
    if value != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.on_event("startup")
def startup() -> None:
    for worker in workers.values():
        worker.start()


@app.on_event("shutdown")
def shutdown() -> None:
    for worker in workers.values():
        worker.stop()


@app.post("/internal/v1/read")
def read(
    request: ReadRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> dict:
    authorize(x_api_key)
    worker = workers.get(request.endpoint)
    if worker is None:
        raise HTTPException(status_code=404, detail="endpoint Modbus desconocido")
    return worker.submit_read(request, WAIT_TIMEOUT_SECONDS)


@app.post("/internal/v1/endpoints/{endpoint}/connect")
def connect(
    endpoint: str,
    request: ConnectRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> dict:
    authorize(x_api_key)
    worker = workers.get(endpoint)
    if worker is None:
        raise HTTPException(status_code=404, detail="endpoint Modbus desconocido")
    result = worker.submit_connect(request.caller, WAIT_TIMEOUT_SECONDS)
    return {
        "endpoint": endpoint,
        "caller": request.caller,
        "connected": bool(result.get("connected")),
    }


@app.get("/internal/v1/modbus/channels")
def channels() -> dict:
    return {
        "version": 1,
        "sampled_at": _TIME.utc_iso(),
        "channels": [worker.diagnostics() for worker in workers.values()],
    }


@app.get("/health")
def health() -> dict:
    running = all(worker.thread.is_alive() for worker in workers.values())
    if not running:
        raise HTTPException(status_code=503, detail="worker Modbus detenido")
    return {"status": "up"}
