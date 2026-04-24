import threading

from src import config
from logosaurio import Logosaurio
from src.modbus.modbus_driver import ModbusTcpDriver
from src.modbus.server_ge_emar import GeEmarClient
from src.modbus.server_mb_middleware import GrdMiddlewareClient
from src.modbus.server_mb_reles import ProtectionRelayClient
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.services.ge_emar_state import GeEmarStateCache
from src.services.state_store import ObserverStateStore


class ModbusOrchestrator:
    """
    Arranca y coordina los hilos de monitoreo de GRDs y relÃ©s.
    """

    def __init__(
        self,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
        observer_store: ObserverStateStore,
        ge_state_cache: GeEmarStateCache,
    ):
        self.logger = logger
        self.mqtt_publisher = mqtt_publisher
        self.observer_store = observer_store
        self.ge_state_cache = ge_state_cache
        self._threads: list[threading.Thread] = []
        self._driver: ModbusTcpDriver | None = None

    def start(self) -> None:
        self.logger.log("Instanciando driver Modbus...", origin="MW/START")
        self._driver = ModbusTcpDriver(
            host=config.MB_HOST,
            port=config.MB_PORT,
            timeout=10,
            logger=self.logger,
        )

        grd_client = GrdMiddlewareClient(
            modbus_driver=self._driver,
            default_unit_id=config.MB_ID,
            register_count=config.MB_COUNT,
            refresh_interval=config.MB_INTERVAL_SECONDS,
            logger=self.logger,
            mqtt_publisher=self.mqtt_publisher,
        )
        relay_client = ProtectionRelayClient(
            modbus_driver=self._driver,
            refresh_interval=config.MB_INTERVAL_SECONDS,
            logger=self.logger,
            observer_store=self.observer_store,
        )
        ge_client = GeEmarClient(
            modbus_driver=self._driver,
            default_unit_id=config.MB_ID,
            refresh_interval=config.MB_INTERVAL_SECONDS,
            logger=self.logger,
            mqtt_publisher=self.mqtt_publisher,
            state_cache=self.ge_state_cache,
        )

        grd_thread = threading.Thread(target=grd_client.start_observer_loop, name="grd-monitor", daemon=True)
        rele_thread = threading.Thread(target=relay_client.start_monitoring_loop, name="rele-monitor", daemon=True)
        ge_thread = threading.Thread(target=ge_client.start_monitoring_loop, name="ge-mar-monitor", daemon=True)
        grd_thread.start()
        rele_thread.start()
        ge_thread.start()
        self._threads.extend([grd_thread, rele_thread, ge_thread])
        self.logger.log("Orquestador Modbus iniciado.", origin="MW/START")
