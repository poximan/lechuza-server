import asyncio
from timeauthority import get_time_authority

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .logger import logger
from .mqtt_publisher import MqttPublisher
from .tcp_probe import TcpProbe
from .alarm_source import ModemAlarmSource
from .connectivity_client import GrdConnectivityClient
from .state_store import ConnectionStateStore
from alarm_generator import create_alarm_generator_router

app = FastAPI(title="modem-link-monitor", version="1.0.0")
time_provider = get_time_authority()
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
    failure_confirmation=config.CHECK_HOST_FAILURE_CONFIRMATION_SECONDS,
    result_timeout=config.CHECK_HOST_RESULT_TIMEOUT_SECONDS,
    poll_interval=config.CHECK_HOST_POLL_INTERVAL_SECONDS,
    request_timeout=config.CHECK_HOST_REQUEST_TIMEOUT_SECONDS,
)
_connectivity_client = GrdConnectivityClient(
    config.GRD_COLLECTOR_API_BASE,
    config.GRD_SUMMARY_TIMEOUT_SECONDS,
)
_publisher: MqttPublisher | None = None
_monitor_task: asyncio.Task | None = None
_alarm_source = ModemAlarmSource()
class ConnectionState:
    def __init__(self, ip: str, port: int) -> None:
        self._lock = asyncio.Lock()
        self._store = ConnectionStateStore(config.STATE_FILE, ip, port)
        self._state = self._store.load()

    @staticmethod
    def _iso_now() -> str:
        return time_provider.utc_iso()

    async def set_state(self, result: dict) -> None:
        async with self._lock:
            self._state["state"] = result["state"]
            self._state["nodes"] = result["nodes"]
            self._state["request_id"] = result.get("request_id")
            self._state["error"] = result.get("error")
            self._state["ts"] = self._iso_now()
            self._store.save(self._state)

    async def snapshot(self) -> dict:
        async with self._lock:
            return dict(self._state)


_state = ConnectionState(config.TARGET_IP, config.TARGET_PORT)
_last_published = None


async def _monitor_loop():
    global _last_published
    while True:
        try:
            result = await asyncio.to_thread(_probe.check, config.TARGET_IP, config.TARGET_PORT)
            state = result["state"]
            if state not in {"abierto", "cerrado", "desconocido"}:
                raise ValueError(f"Estado TCP fuera de contrato: {state}")
            connectivity_percentage = None
            if state == "abierto":
                try:
                    connectivity_percentage = await asyncio.to_thread(
                        _connectivity_client.percentage
                    )
                except Exception as exc:
                    logger.warning(
                        "No se pudo confirmar conectividad GRD; se conserva la alarma: %s",
                        exc,
                        origin="ROUTER-TELEF/GRD",
                    )
            await _state.set_state(result)
            snapshot = await _state.snapshot()
            _alarm_source.observe(state, connectivity_percentage, str(snapshot["ts"]))
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
    logger.info("Iniciando modem-link-monitor para %s:%s", config.TARGET_IP, config.TARGET_PORT, origin="ROUTER-TELEF")
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
    logger.info("modem-link-monitor finalizado", origin="ROUTER-TELEF")


@app.get("/status")
async def get_status():
    return await _state.snapshot()


app.include_router(
    create_alarm_generator_router(
        _alarm_source.outbox,
        config.ALARM_INTERNAL_API_KEY,
    )
)
