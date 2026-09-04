import threading
from collections.abc import Callable
from typing import Optional

from src import config
from logosaurio import Logosaurio
from src.modbus.modbus_driver import ModbusTcpReadOnlyDriver
from src.services.generator_state import GeneratorStateCache
from src.services.alarm_generator import ModbusAlarmGenerator
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.utils import timebox


class EdifEstivarizGeneratorClient:
    """
    Monitorea los interruptores asociados al grupo electrogeno leyendo un unico
    registro Modbus y exponiendo el estado por cache HTTP y MQTT.
    """

    def __init__(
        self,
        modbus_driver: ModbusTcpReadOnlyDriver,
        default_unit_id: int,
        refresh_interval: int,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
        state_cache: GeneratorStateCache,
        alarm_generator: ModbusAlarmGenerator,
    ):
        self.driver = modbus_driver
        self.unit_id = default_unit_id
        self.refresh_interval = max(1, refresh_interval)
        self.logger = logger
        self.publisher = mqtt_publisher
        self.state_cache = state_cache
        self.alarm_generator = alarm_generator
        self._last_line_bit: Optional[int] = None

        ge_cfg = config.EDIF_ESTIVARIZ_GE
        self._name = str(ge_cfg["name"])
        self._grd_id = int(ge_cfg["grd_id"])
        self._register_offset = int(ge_cfg["register_offset"])
        self._line_bit_index = int(ge_cfg["line_bit_index"])
        self._generator_bit_index = int(ge_cfg["generator_bit_index"])
        self._topic = ge_cfg["topic"]

        self._address_offset = self._compute_address_offset()

    def _compute_address_offset(self) -> int:
        """
        Convierte la formula 3xxx = 30000 + (GRD_ID - 1) * 16 + register_offset
        a desplazamiento zero-based para pymodbus.
        """
        zero_based_offset = max(0, self._register_offset - 1)
        return max(0, (self._grd_id - 1) * config.MW_EXEMYS["register_count"] + zero_based_offset)

    def _decode_breaker(self, raw_value: int, bit_index: int) -> dict:
        bit = (raw_value >> bit_index) & 1
        return {
            "bit": bit,
            "estado": "cerrado" if bit == 1 else "abierto",
        }

    def _build_payload(self, raw_value: int) -> dict:
        return {
            "edificio": self._name,
            "interruptor_linea": self._decode_breaker(raw_value, self._line_bit_index),
            "interruptor_grupo": self._decode_breaker(raw_value, self._generator_bit_index),
            "raw_value": raw_value,
            "ts": timebox.utc_iso(),
        }

    def _build_line_payload(self, payload: dict) -> dict:
        return {
            "edificio": payload["edificio"],
            "interruptor_linea": dict(payload["interruptor_linea"]),
            "ts": payload["ts"],
        }

    def _run_cycle(self) -> None:
        registers = self.driver.read_input_registers(
            address_offset=self._address_offset,
            count=1,
            unit_id=self.unit_id,
        )
        if registers is None or not registers:
            self.logger.log("Lectura edif-estivariz sin registros.", origin="OBS/GE")
            return

        raw_value = int(registers[0])
        payload = self._build_payload(raw_value)
        self.state_cache.update(self._name, payload)
        self.alarm_generator.observe_generator(self._name, payload)
        line_bit = int(payload["interruptor_linea"]["bit"])
        if line_bit != self._last_line_bit and self.publisher.publish_ge_status(
            self._topic,
            self._build_line_payload(payload),
        ):
            self._last_line_bit = line_bit
            self.logger.log(
                "edif-estivariz linea: "
                f"{payload['interruptor_linea']['estado']} "
                f"/ grupo: {payload['interruptor_grupo']['estado']} "
                f"(valor {raw_value})",
                origin="OBS/GE",
            )

    def start_monitoring_loop(
        self,
        stop_event: threading.Event,
        heartbeat: Callable[[], None],
    ) -> None:
        self.logger.log(
            f"Iniciando monitor edif-estivariz (GRD {self._grd_id}, offset {self._address_offset}, bits linea/grupo {self._line_bit_index}/{self._generator_bit_index})...",
            origin="OBS/GE",
        )

        while not stop_event.is_set():
            self._run_cycle()
            heartbeat()
            stop_event.wait(self.refresh_interval)
