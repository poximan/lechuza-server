from dataclasses import dataclass
import threading
from typing import Any

from logosaurio import Logosaurio, logger
from modbus_transport_client import ModbusTcpReadOnlyDriver

from src import config
from src.services.relay_monitoring import RelayMonitoringService
from src.services.state_store import ObserverStateStore


@dataclass
class ApplicationContext:
    logger: Logosaurio
    state_store: ObserverStateStore
    orchestrator: Any


class MicomOrchestrator:
    def __init__(
        self,
        monitor: RelayMonitoringService,
        driver: ModbusTcpReadOnlyDriver,
        application_logger: Logosaurio,
    ) -> None:
        self.monitor = monitor
        self.driver = driver
        self.logger = application_logger
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._supervise,
            name="micom-monitor",
            daemon=True,
        )

    def _supervise(self):
        while not self.stop_event.is_set():
            try:
                self.monitor.start_monitoring_loop(self.stop_event, lambda: None)
                if not self.stop_event.is_set():
                    raise RuntimeError("El observador MiCOM finalizo inesperadamente")
            except Exception as exc:
                self.logger.log(
                    f"Observador MiCOM reiniciado tras {type(exc).__name__}: {exc}",
                    origin="MICOM/SUPERVISOR",
                )
                self.stop_event.wait(5)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=10)
        self.driver.shutdown()

    def health_snapshot(self):
        running = self.thread.is_alive()
        return {
            "ready": running,
            "workers": {"micom-monitor": {"running": running}},
        }

    def relay_query_snapshot(self, relay_id):
        return self.monitor.query_diagnostics.get_query_snapshot(relay_id)

    def relay_current_calculation_snapshot(self, relay_id):
        return self.monitor.metadata.get_current_calculation_snapshot(relay_id)

    def relay_observer_runtime_snapshot(self):
        return self.monitor.get_observer_runtime_snapshot()

    def relay_clock_on_demand(self, relay_id):
        return self.monitor.metadata.read_clock_on_demand(relay_id)


def create_context() -> ApplicationContext:
    store = ObserverStateStore(config.OBS_STATE_FILE)
    driver = ModbusTcpReadOnlyDriver(
        config.MODBUS_TRANSPORT_BASE_URL,
        "mw-exemys",
        "micom-collector",
        config.MODBUS_TRANSPORT_API_KEY,
        config.MODBUS_TRANSPORT_TIMEOUT_SECONDS,
        logger,
    )
    monitor = RelayMonitoringService(
        driver,
        config.RELAY_INTERVAL_SECONDS,
        logger,
        store,
    )
    return ApplicationContext(
        logger,
        store,
        MicomOrchestrator(monitor, driver, logger),
    )
