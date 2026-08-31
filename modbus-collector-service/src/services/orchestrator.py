import threading
from collections.abc import Callable
from typing import Any

from logosaurio import Logosaurio

from src import config
from src.control.latest_state_registry import LatestStateRegistry
from src.modbus.modbus_driver import ModbusTcpConnectionConfig, ModbusTcpReadOnlyDriver
from src.modbus.server_ge_estivariz import EdifEstivarizGeneratorClient
from src.modbus.server_ge_fontana import EdifFontanaGeneratorClient
from src.modbus.server_mb_middleware import GrdMiddlewareClient
from src.modbus.server_mb_reles import ProtectionRelayClient
from src.services.generator_state import GeneratorStateCache
from src.services.grd_service import GrdService
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.services.state_store import ObserverStateStore
from src.utils import timebox


WorkerTarget = Callable[[threading.Event, Callable[[], None]], None]
WorkerSpec = tuple[WorkerTarget, int]


class ModbusOrchestrator:
    """Coordina, supervisa y detiene los observadores Modbus."""

    RESTART_DELAY_SECONDS = 5

    def __init__(
        self,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
        observer_store: ObserverStateStore,
        generator_state_cache: GeneratorStateCache,
        grd_state_registry: LatestStateRegistry,
        grd_service: GrdService,
    ):
        self.logger = logger
        self.mqtt_publisher = mqtt_publisher
        self.observer_store = observer_store
        self.generator_state_cache = generator_state_cache
        self.grd_state_registry = grd_state_registry
        self.grd_service = grd_service
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._workers: dict[str, dict[str, Any]] = {}
        self._drivers: dict[str, ModbusTcpReadOnlyDriver] = {}
        self._relay_client: ProtectionRelayClient | None = None
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("El orquestador Modbus ya fue iniciado")
            self._started = True

        mw_driver = ModbusTcpReadOnlyDriver.from_config(
            ModbusTcpConnectionConfig(
                name=str(config.MW_EXEMYS["name"]),
                host=str(config.MW_EXEMYS["host"]),
                port=int(config.MW_EXEMYS["port"]),
                timeout=10,
            ),
            self.logger,
        )
        fontana_driver = ModbusTcpReadOnlyDriver.from_config(
            ModbusTcpConnectionConfig(
                name=str(config.EDIF_FONTANA_GE["name"]),
                host=str(config.EDIF_FONTANA_GE["host"]),
                port=int(config.EDIF_FONTANA_GE["port"]),
                timeout=10,
            ),
            self.logger,
        )
        self._drivers = {"mw-exemys": mw_driver, "edif-fontana": fontana_driver}

        mw_interval = int(config.MW_EXEMYS["interval_seconds"])
        fontana_interval = int(config.EDIF_FONTANA_GE["interval_seconds"])
        self._relay_client = ProtectionRelayClient(
            modbus_driver=mw_driver,
            refresh_interval=mw_interval,
            logger=self.logger,
            observer_store=self.observer_store,
        )
        targets: dict[str, WorkerSpec] = {
            "grd-monitor": (
                GrdMiddlewareClient(
                    modbus_driver=mw_driver,
                    default_unit_id=int(config.MW_EXEMYS["unit_id"]),
                    register_count=int(config.MW_EXEMYS["register_count"]),
                    refresh_interval=mw_interval,
                    logger=self.logger,
                    mqtt_publisher=self.mqtt_publisher,
                    state_registry=self.grd_state_registry,
                    grd_service=self.grd_service,
                ).start_observer_loop,
                mw_interval,
            ),
            "rele-monitor": (
                self._relay_client.start_monitoring_loop,
                mw_interval,
            ),
            "ge-estivariz-monitor": (
                EdifEstivarizGeneratorClient(
                    modbus_driver=mw_driver,
                    default_unit_id=int(config.MW_EXEMYS["unit_id"]),
                    refresh_interval=mw_interval,
                    logger=self.logger,
                    mqtt_publisher=self.mqtt_publisher,
                    state_cache=self.generator_state_cache,
                ).start_monitoring_loop,
                mw_interval,
            ),
            "ge-fontana-monitor": (
                EdifFontanaGeneratorClient(
                    modbus_driver=fontana_driver,
                    unit_id=int(config.EDIF_FONTANA_GE["unit_id"]),
                    register_offset=int(config.EDIF_FONTANA_GE["register_offset"]),
                    register_count=int(config.EDIF_FONTANA_GE["register_count"]),
                    line_bit_index=int(config.EDIF_FONTANA_GE["line_bit_index"]),
                    generator_bit_index=int(
                        config.EDIF_FONTANA_GE["generator_bit_index"]
                    ),
                    refresh_interval=fontana_interval,
                    logger=self.logger,
                    mqtt_publisher=self.mqtt_publisher,
                    state_cache=self.generator_state_cache,
                    topic=str(config.EDIF_FONTANA_GE["topic"]),
                    name=str(config.EDIF_FONTANA_GE["name"]),
                ).start_monitoring_loop,
                fontana_interval,
            ),
        }

        for name, (target, interval_seconds) in targets.items():
            with self._lock:
                self._workers[name] = {
                    "running": False,
                    "last_heartbeat": None,
                    "last_heartbeat_monotonic": None,
                    "heartbeat_timeout_seconds": max(60, interval_seconds * 4 + 30),
                    "last_error": None,
                    "restart_count": 0,
                }
            thread = threading.Thread(
                target=self._supervise,
                args=(name, target),
                name=name,
                daemon=True,
            )
            self._threads[name] = thread
            thread.start()
        self.logger.log("Orquestador Modbus iniciado.", origin="MW/START")

    def _supervise(self, name: str, target: WorkerTarget) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                self._workers[name]["running"] = True
            try:
                target(self._stop_event, lambda: self._heartbeat(name))
                if not self._stop_event.is_set():
                    raise RuntimeError("El observador finalizo sin solicitud de apagado")
            except Exception as exc:
                with self._lock:
                    state = self._workers[name]
                    state["running"] = False
                    state["last_error"] = f"{type(exc).__name__}: {exc}"
                    state["restart_count"] = int(state["restart_count"]) + 1
                self.logger.log(
                    f"Observador {name} fallo y sera reiniciado: {type(exc).__name__}: {exc}",
                    origin="MW/SUPERVISOR",
                )
                self._stop_event.wait(self.RESTART_DELAY_SECONDS)
            else:
                break

        with self._lock:
            self._workers[name]["running"] = False

    def _heartbeat(self, name: str) -> None:
        with self._lock:
            state = self._workers[name]
            state["running"] = True
            state["last_heartbeat"] = timebox.utc_iso()
            state["last_heartbeat_monotonic"] = timebox.monotonic()
            state["last_error"] = None

    def health_snapshot(self) -> dict[str, Any]:
        now = timebox.monotonic()
        with self._lock:
            workers = {}
            for name, state in self._workers.items():
                heartbeat_monotonic = state["last_heartbeat_monotonic"]
                heartbeat_age = (
                    None
                    if heartbeat_monotonic is None
                    else max(0.0, now - float(heartbeat_monotonic))
                )
                heartbeat_stale = (
                    heartbeat_age is None
                    or heartbeat_age > float(state["heartbeat_timeout_seconds"])
                )
                workers[name] = {
                    key: value
                    for key, value in state.items()
                    if key != "last_heartbeat_monotonic"
                }
                workers[name].update(
                    {
                        "heartbeat_age_seconds": (
                            round(heartbeat_age, 3) if heartbeat_age is not None else None
                        ),
                        "heartbeat_stale": heartbeat_stale,
                        "thread_alive": bool(
                            self._threads.get(name) and self._threads[name].is_alive()
                        ),
                    }
                )
            started = self._started
        drivers = {name: driver.is_connected() for name, driver in self._drivers.items()}
        mqtt_connected = self.mqtt_publisher.is_connected()
        workers_ready = bool(workers) and all(
            state["running"]
            and state["thread_alive"]
            and state["last_heartbeat"]
            and not state["heartbeat_stale"]
            and state["last_error"] is None
            for state in workers.values()
        )
        dependencies_ready = (
            bool(drivers)
            and all(drivers.values())
            and mqtt_connected
        )
        return {
            "ready": bool(started and workers_ready and dependencies_ready),
            "workers": workers,
            "drivers": drivers,
            "mqtt_connected": mqtt_connected,
        }

    def relay_disturbance_snapshot(self, relay_id: int) -> dict[str, Any]:
        if self._relay_client is None:
            raise RuntimeError("El observador de reles todavia no fue iniciado")
        return self._relay_client.get_disturbance_snapshot(relay_id)

    def relay_current_calculation_snapshot(self, relay_id: int) -> dict[str, Any]:
        if self._relay_client is None:
            raise RuntimeError("El observador de reles todavia no fue iniciado")
        return self._relay_client.get_current_calculation_snapshot(relay_id)

    def relay_query_snapshot(self, relay_id: int) -> list[dict]:
        if self._relay_client is None:
            raise RuntimeError("El observador de reles todavia no fue iniciado")
        return self._relay_client.get_query_snapshot(relay_id)

    def relay_observer_runtime_snapshot(self) -> dict[str, Any]:
        if self._relay_client is None:
            raise RuntimeError("El observador de reles todavia no fue iniciado")
        return self._relay_client.get_observer_runtime_snapshot()

    def stop(self) -> None:
        self._stop_event.set()
        for driver in self._drivers.values():
            driver.shutdown()
        deadline = timebox.monotonic() + 20
        for thread in self._threads.values():
            remaining = max(0.0, deadline - timebox.monotonic())
            if remaining == 0:
                break
            thread.join(timeout=remaining)
        alive = [name for name, thread in self._threads.items() if thread.is_alive()]
        if alive:
            self.logger.log(
                f"Observadores que no terminaron dentro del plazo: {alive}",
                origin="MW/STOP",
            )
        self.logger.log("Orquestador Modbus detenido.", origin="MW/STOP")
