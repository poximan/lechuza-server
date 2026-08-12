from __future__ import annotations

from dataclasses import dataclass

from logosaurio import Logosaurio, logger
from src.control.latest_state_registry import LatestStateRegistry
from src.persistencia.dao.dao_estado_grd import grd_state_dao
from src.persistencia.dao.dao_grd import grd_dao
from src.services.state_store import ObserverStateStore
from src.services.generator_state import GeneratorStateCache
from src.services.grd_service import GrdService
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.services.orchestrator import ModbusOrchestrator
from src import config


@dataclass
class ApplicationContext:
    logger: Logosaurio
    state_store: ObserverStateStore
    generator_cache: GeneratorStateCache
    grd_state_registry: LatestStateRegistry
    grd_service: GrdService
    publisher: ModbusMqttPublisher
    orchestrator: ModbusOrchestrator


def create_context() -> ApplicationContext:
    state_store = ObserverStateStore(config.OBS_STATE_FILE)
    generator_cache = GeneratorStateCache()
    grd_state_registry = LatestStateRegistry(grd_state_dao.get_current_states())
    grd_service = GrdService(grd_dao, grd_state_dao, grd_state_registry)
    publisher = ModbusMqttPublisher(logger)
    orchestrator = ModbusOrchestrator(
        logger,
        publisher,
        state_store,
        generator_cache,
        grd_state_registry,
        grd_service,
    )
    return ApplicationContext(
        logger=logger,
        state_store=state_store,
        generator_cache=generator_cache,
        grd_state_registry=grd_state_registry,
        grd_service=grd_service,
        publisher=publisher,
        orchestrator=orchestrator,
    )
