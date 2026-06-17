from __future__ import annotations

from dataclasses import dataclass

from logosaurio import Logosaurio, logger
from src.services.state_store import ObserverStateStore
from src.services.generator_state import GeneratorStateCache
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.services.orchestrator import ModbusOrchestrator
from src import config


@dataclass
class ApplicationContext:
    logger: Logosaurio
    state_store: ObserverStateStore
    generator_cache: GeneratorStateCache
    publisher: ModbusMqttPublisher
    orchestrator: ModbusOrchestrator


def create_context() -> ApplicationContext:
    state_store = ObserverStateStore(config.OBS_STATE_FILE)
    generator_cache = GeneratorStateCache()
    publisher = ModbusMqttPublisher(logger)
    orchestrator = ModbusOrchestrator(logger, publisher, state_store, generator_cache)
    return ApplicationContext(
        logger=logger,
        state_store=state_store,
        generator_cache=generator_cache,
        publisher=publisher,
        orchestrator=orchestrator,
    )
