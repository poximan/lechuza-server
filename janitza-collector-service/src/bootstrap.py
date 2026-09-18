from dataclasses import dataclass

from logosaurio import logger
from modbus_transport_client import ModbusTcpReadOnlyDriver

from src import config
from src.services.collector import JanitzaCollector
from src.services.state_store import JanitzaStateStore


@dataclass
class ApplicationContext:
    collector: JanitzaCollector


def create_context() -> ApplicationContext:
    driver = ModbusTcpReadOnlyDriver(
        config.MODBUS_TRANSPORT_BASE_URL,
        "mw-exemys",
        "janitza-collector",
        config.MODBUS_TRANSPORT_API_KEY,
        config.MODBUS_TRANSPORT_TIMEOUT_SECONDS,
        logger,
    )
    collector = JanitzaCollector(
        driver,
        config.ANALYZERS,
        config.POLL_INTERVAL_SECONDS,
        JanitzaStateStore(config.STATE_FILE),
    )
    return ApplicationContext(collector=collector)
