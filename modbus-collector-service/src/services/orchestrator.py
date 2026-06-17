import threading

from logosaurio import Logosaurio
from src import config
from src.modbus.modbus_driver import ModbusTcpConnectionConfig, ModbusTcpDriver
from src.modbus.server_ge_estivariz import EdifEstivarizGeneratorClient
from src.modbus.server_ge_fontana import EdifFontanaGeneratorClient
from src.modbus.server_mb_middleware import GrdMiddlewareClient
from src.modbus.server_mb_reles import ProtectionRelayClient
from src.services.generator_state import GeneratorStateCache
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.services.state_store import ObserverStateStore


class ModbusOrchestrator:
    """
    Arranca y coordina los hilos de monitoreo sobre las conexiones Modbus.
    """

    def __init__(
        self,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
        observer_store: ObserverStateStore,
        generator_state_cache: GeneratorStateCache,
    ):
        self.logger = logger
        self.mqtt_publisher = mqtt_publisher
        self.observer_store = observer_store
        self.generator_state_cache = generator_state_cache
        self._threads: list[threading.Thread] = []
        self._drivers: dict[str, ModbusTcpDriver] = {}

    def start(self) -> None:
        self.logger.log("Instanciando conexiones Modbus...", origin="MW/START")
        mw_exemys_driver = ModbusTcpDriver.from_config(
            ModbusTcpConnectionConfig(
                name=str(config.MW_EXEMYS["name"]),
                host=str(config.MW_EXEMYS["host"]),
                port=int(config.MW_EXEMYS["port"]),
                timeout=10,
            ),
            self.logger,
        )
        edif_fontana_driver = ModbusTcpDriver.from_config(
            ModbusTcpConnectionConfig(
                name=str(config.EDIF_FONTANA_GE["name"]),
                host=str(config.EDIF_FONTANA_GE["host"]),
                port=int(config.EDIF_FONTANA_GE["port"]),
                timeout=10,
            ),
            self.logger,
        )
        self._drivers = {
            "mw-exemys": mw_exemys_driver,
            "edif-fontana": edif_fontana_driver,
        }

        grd_client = GrdMiddlewareClient(
            modbus_driver=mw_exemys_driver,
            default_unit_id=int(config.MW_EXEMYS["unit_id"]),
            register_count=int(config.MW_EXEMYS["register_count"]),
            refresh_interval=int(config.MW_EXEMYS["interval_seconds"]),
            logger=self.logger,
            mqtt_publisher=self.mqtt_publisher,
        )
        relay_client = ProtectionRelayClient(
            modbus_driver=mw_exemys_driver,
            refresh_interval=int(config.MW_EXEMYS["interval_seconds"]),
            logger=self.logger,
            observer_store=self.observer_store,
        )
        ge_estivariz_client = EdifEstivarizGeneratorClient(
            modbus_driver=mw_exemys_driver,
            default_unit_id=int(config.MW_EXEMYS["unit_id"]),
            refresh_interval=int(config.MW_EXEMYS["interval_seconds"]),
            logger=self.logger,
            mqtt_publisher=self.mqtt_publisher,
            state_cache=self.generator_state_cache,
        )
        ge_fontana_client = EdifFontanaGeneratorClient(
            modbus_driver=edif_fontana_driver,
            unit_id=int(config.EDIF_FONTANA_GE["unit_id"]),
            register_offset=int(config.EDIF_FONTANA_GE["register_offset"]),
            register_count=int(config.EDIF_FONTANA_GE["register_count"]),
            line_bit_index=int(config.EDIF_FONTANA_GE["line_bit_index"]),
            generator_bit_index=int(config.EDIF_FONTANA_GE["generator_bit_index"]),
            refresh_interval=int(config.EDIF_FONTANA_GE["interval_seconds"]),
            logger=self.logger,
            mqtt_publisher=self.mqtt_publisher,
            state_cache=self.generator_state_cache,
            topic=str(config.EDIF_FONTANA_GE["topic"]),
            name=str(config.EDIF_FONTANA_GE["name"]),
        )

        grd_thread = threading.Thread(target=grd_client.start_observer_loop, name="grd-monitor", daemon=True)
        rele_thread = threading.Thread(target=relay_client.start_monitoring_loop, name="rele-monitor", daemon=True)
        ge_estivariz_thread = threading.Thread(target=ge_estivariz_client.start_monitoring_loop, name="ge-estivariz-monitor", daemon=True)
        ge_fontana_thread = threading.Thread(target=ge_fontana_client.start_monitoring_loop, name="ge-fontana-monitor", daemon=True)

        grd_thread.start()
        rele_thread.start()
        ge_estivariz_thread.start()
        ge_fontana_thread.start()
        self._threads.extend([grd_thread, rele_thread, ge_estivariz_thread, ge_fontana_thread])
        self.logger.log("Orquestador Modbus iniciado.", origin="MW/START")
