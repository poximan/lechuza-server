from dataclasses import dataclass
import threading
from typing import Any

from logosaurio import Logosaurio, logger
from modbus_transport_client import ModbusTcpReadOnlyDriver
from src import config
from src.control.latest_state_registry import LatestStateRegistry
from src.persistencia.dao.dao_estado_grd import grd_state_dao
from src.persistencia.dao.dao_grd import grd_dao
from src.services.alarm_generator import GrdAlarmGenerator
from src.services.grd_service import GrdService
from src.services.mqtt_publisher import GrdMqttPublisher
from src.modbus.server_mb_middleware import GrdMiddlewareClient


@dataclass
class ApplicationContext:
    logger: Logosaurio
    grd_service: GrdService
    publisher: GrdMqttPublisher
    orchestrator: Any
    alarm_generator: GrdAlarmGenerator


class GrdOrchestrator:
    def __init__(
        self,
        worker: GrdMiddlewareClient,
        driver: ModbusTcpReadOnlyDriver,
        application_logger: Logosaurio,
    ) -> None:
        self.worker = worker
        self.driver = driver
        self.logger = application_logger
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="grd-monitor", daemon=True)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.worker.start_observer_loop(self.stop_event, lambda: None)
                if not self.stop_event.is_set():
                    raise RuntimeError("El observador GRD finalizo inesperadamente")
            except Exception as exc:
                self.logger.log(
                    f"Observador GRD reiniciado tras {type(exc).__name__}: {exc}",
                    origin="GRD/SUPERVISOR",
                )
                self.stop_event.wait(5)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=10)
        self.driver.shutdown()

    def health_snapshot(self) -> dict[str, Any]:
        running = self.thread.is_alive()
        return {
            "ready": running,
            "workers": {"grd-monitor": {"running": running}},
        }


def create_context(alarm_generator: GrdAlarmGenerator) -> ApplicationContext:
    registry = LatestStateRegistry(grd_state_dao.get_current_states())
    service = GrdService(grd_dao, grd_state_dao, registry)
    publisher = GrdMqttPublisher(logger)
    driver = ModbusTcpReadOnlyDriver(
        config.MODBUS_TRANSPORT_BASE_URL,
        "mw-exemys",
        "grd-collector",
        config.MODBUS_TRANSPORT_API_KEY,
        config.MODBUS_TRANSPORT_TIMEOUT_SECONDS,
        logger,
    )
    worker = GrdMiddlewareClient(
        driver,
        int(config.MW_EXEMYS["unit_id"]),
        int(config.MW_EXEMYS["register_stride"]),
        int(config.MW_EXEMYS["interval_seconds"]),
        logger,
        publisher,
        registry,
        service,
        alarm_generator,
    )
    orchestrator = GrdOrchestrator(worker, driver, logger)
    return ApplicationContext(
        logger,
        service,
        publisher,
        orchestrator,
        alarm_generator,
    )
