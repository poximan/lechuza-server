import time
from typing import Optional

from src import config
from logosaurio import Logosaurio
from src.modbus.modbus_driver import ModbusTcpDriver
from src.services.ge_emar_state import GeEmarStateCache
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.utils import timebox


class GeEmarClient:
    """
    Monitorea el estado de marcha del grupo electrÃ³geno (GE) leyendo un Ãºnico registro
    Modbus y publicando cambios tanto por MQTT como vÃ­a cache para HTTP.
    """

    def __init__(
        self,
        modbus_driver: ModbusTcpDriver,
        default_unit_id: int,
        refresh_interval: int,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
        state_cache: GeEmarStateCache,
    ):
        self.driver = modbus_driver
        self.unit_id = default_unit_id
        self.refresh_interval = max(1, refresh_interval)
        self.logger = logger
        self.publisher = mqtt_publisher
        self.state_cache = state_cache
        self._last_state: Optional[str] = None

        ge_cfg = config.GE_EMAR
        self._grd_id = int(ge_cfg["grd_id"])
        self._register_offset = int(ge_cfg["register_offset"])
        self._bit_index = int(ge_cfg["bit_index"])
        self._topic = ge_cfg["topic"]

        self._address_offset = self._compute_address_offset()

    def _compute_address_offset(self) -> int:
        """
        Convierte la formula 3xxx = 30000 + (GRD_ID â€“ 1) * 16 + register_offset
        a desplazamiento zero-based para pymodbus.
        """
        zero_based_offset = max(0, self._register_offset - 1)
        return max(0, (self._grd_id - 1) * config.MB_COUNT + zero_based_offset)

    def _evaluate_state(self, raw_value: int) -> str:
        """
        Bit 0: 1 -> parado, 0 -> en marcha.
        """
        bit = (raw_value >> self._bit_index) & 1
        return "parado" if bit == 1 else "marcha"

    def _build_payload(self, state: str) -> dict:
        return {
            "estado": state,
            "ts": timebox.utc_iso(),
        }

    def start_monitoring_loop(self) -> None:
        self.logger.log(
            f"Iniciando monitor GE_EMAR (GRD {self._grd_id}, offset {self._address_offset}, bit {self._bit_index})...",
            origin="OBS/GE",
        )

        while True:
            try:
                registers = self.driver.read_input_registers(
                    address_offset=self._address_offset,
                    count=1,
                    unit_id=self.unit_id,
                )
                if registers is None or not registers:
                    self.logger.log("Lectura GE_EMAR sin registros.", origin="OBS/GE")
                else:
                    raw_value = int(registers[0])
                    state = self._evaluate_state(raw_value)
                    payload = self._build_payload(state)
                    self.state_cache.update(payload)
                    if state != self._last_state:
                        self.publisher.publish_ge_emar(payload)
                        self._last_state = state
                        self.logger.log(f"GE_EMAR actual: {state} (valor {raw_value})", origin="OBS/GE")
            except Exception as exc:
                self.logger.log(f"Error en monitoreo GE_EMAR: {exc}", origin="OBS/GE")

            time.sleep(self.refresh_interval)
