import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .logger import logger
from .mqtt_publisher import MqttPublisher
from .tcp_probe import TcpProbe

app = FastAPI(title="router-telef-service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"]
)

_probe = TcpProbe(
    base_url=config.CHECK_HOST_BASE_URL,
    max_nodes=config.CHECK_HOST_MAX_NODES,
    success_latency=config.CHECK_HOST_SUCCESS_LATENCY_SECONDS,
    result_timeout=config.CHECK_HOST_RESULT_TIMEOUT_SECONDS,
    poll_interval=config.CHECK_HOST_POLL_INTERVAL_SECONDS,
    request_timeout=config.CHECK_HOST_REQUEST_TIMEOUT_SECONDS,
)
_publisher: MqttPublisher | None = None
_monitor_task: asyncio.Task | None = None
class ConnectionState:
    def __init__(self, ip: str, port: int) -> None:
        self._lock = asyncio.Lock()
        self._state = {"ip": ip, "port": port, "state": "desconocido", "ts": self._iso_now()}

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    async def set_state(self, state: str) -> None:
        async with self._lock:
            self._state["state"] = state
            self._state["ts"] = self._iso_now()

    async def snapshot(self) -> dict:
        async with self._lock:
            return dict(self._state)


_state = ConnectionState(config.TARGET_IP, config.TARGET_PORT)
_last_published = None


async def _monitor_loop():
    global _last_published
    while True:
        try:
            state = await asyncio.to_thread(_probe.check, config.TARGET_IP, config.TARGET_PORT)
            if state not in {"abierto", "cerrado", "desconocido"}:
                state = "desconocido"
            await _state.set_state(state)
            if _publisher and state != _last_published:
                published = _publisher.publish_state(state)
                if published:
                    _last_published = state
                else:
                    logger.warning("No se pudo publicar estado %s, se reintentara tras el siguiente ciclo", state, origin="ROUTER-TELEF")
                    _publisher.publish_offline()
        except Exception as exc:
            logger.exception("Error en monitor TCP: %s", exc, origin="ROUTER-TELEF")
        await asyncio.sleep(config.PROBE_INTERVAL_SECONDS)


@app.on_event("startup")
async def on_startup():
    global _publisher, _monitor_task
    logger.info("Iniciando router-telef-service para %s:%s", config.TARGET_IP, config.TARGET_PORT, origin="ROUTER-TELEF")
    _publisher = MqttPublisher()
    _monitor_task = asyncio.create_task(_monitor_loop())


@app.on_event("shutdown")
async def on_shutdown():
    global _publisher, _monitor_task
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None
    if _publisher:
        _publisher.stop()
        _publisher = None
    logger.info("router-telef-service finalizado", origin="ROUTER-TELEF")


@app.get("/status")
async def get_status():
    return await _state.snapshot()
