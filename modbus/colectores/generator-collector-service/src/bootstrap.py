from dataclasses import dataclass
import threading
from typing import Any

from logosaurio import Logosaurio, logger
from modbus_transport_client import ModbusTcpReadOnlyDriver

from src import config
from src.modbus.server_ge_estivariz import EdifEstivarizGeneratorClient
from src.modbus.server_ge_fontana import EdifFontanaGeneratorClient
from src.services.alarm_generator import GeneratorAlarmGenerator
from src.services.generator_state import GeneratorStateCache
from src.services.mqtt_publisher import GeneratorMqttPublisher


@dataclass
class ApplicationContext:
    logger: Logosaurio
    generator_cache: GeneratorStateCache
    publisher: GeneratorMqttPublisher
    orchestrator: Any
    alarm_generator: GeneratorAlarmGenerator


class GeneratorOrchestrator:
    def __init__(self, workers, drivers, application_logger):
        self.stop_event = threading.Event()
        self.workers = workers
        self.drivers = drivers
        self.logger = application_logger
        self.threads = [
            threading.Thread(
                target=self._supervise,
                args=(name, worker),
                name=name,
                daemon=True,
            )
            for name, worker in workers.items()
        ]

    def _supervise(self, name, worker):
        while not self.stop_event.is_set():
            try:
                worker(self.stop_event, lambda: None)
                if not self.stop_event.is_set():
                    raise RuntimeError("El observador finalizo inesperadamente")
            except Exception as exc:
                self.logger.log(
                    f"{name} reiniciado tras {type(exc).__name__}: {exc}",
                    origin="GE/SUPERVISOR",
                )
                self.stop_event.wait(5)

    def start(self):
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=10)
        for driver in self.drivers:
            driver.shutdown()

    def health_snapshot(self):
        return {
            "ready": all(thread.is_alive() for thread in self.threads),
            "workers": {
                thread.name: {"running": thread.is_alive()}
                for thread in self.threads
            },
        }


def create_context(alarms: GeneratorAlarmGenerator) -> ApplicationContext:
    cache = GeneratorStateCache(config.STATE_FILE)
    publisher = GeneratorMqttPublisher(logger)
    estivariz_driver = ModbusTcpReadOnlyDriver(
        config.MODBUS_TRANSPORT_BASE_URL,
        "mw-exemys",
        "generator-estivariz",
        config.MODBUS_TRANSPORT_API_KEY,
        config.MODBUS_TRANSPORT_TIMEOUT_SECONDS,
        logger,
    )
    fontana_driver = ModbusTcpReadOnlyDriver(
        config.MODBUS_TRANSPORT_BASE_URL,
        "edif-fontana",
        "generator-fontana",
        config.MODBUS_TRANSPORT_API_KEY,
        config.MODBUS_TRANSPORT_TIMEOUT_SECONDS,
        logger,
    )
    estivariz = EdifEstivarizGeneratorClient(
        estivariz_driver,
        int(config.MW_EXEMYS["unit_id"]),
        int(config.MW_EXEMYS["interval_seconds"]),
        logger,
        publisher,
        cache,
        alarms,
    )
    fontana_config = config.EDIF_FONTANA_GE
    fontana = EdifFontanaGeneratorClient(
        fontana_driver,
        int(fontana_config["unit_id"]),
        int(fontana_config["register_offset"]),
        int(fontana_config["register_count"]),
        int(fontana_config["line_bit_index"]),
        int(fontana_config["generator_bit_index"]),
        int(fontana_config["interval_seconds"]),
        logger,
        publisher,
        cache,
        str(fontana_config["topic"]),
        str(fontana_config["name"]),
        alarms,
    )
    orchestrator = GeneratorOrchestrator(
        {
            "ge-estivariz-monitor": estivariz.start_monitoring_loop,
            "ge-fontana-monitor": fontana.start_monitoring_loop,
        },
        [estivariz_driver, fontana_driver],
        logger,
    )
    return ApplicationContext(logger, cache, publisher, orchestrator, alarms)
