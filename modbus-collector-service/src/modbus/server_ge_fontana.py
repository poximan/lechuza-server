import threading
from collections.abc import Callable

from logosaurio import Logosaurio
from src.modbus.modbus_driver import ModbusTcpDriver
from src.services.generator_state import GeneratorStateCache
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.utils import timebox


class EdifFontanaGeneratorClient:
    """
    Monitorea los interruptores de red externa y grupo de Edificio Fontana.
    """

    def __init__(
        self,
        modbus_driver: ModbusTcpDriver,
        unit_id: int,
        register_offset: int,
        register_count: int,
        line_bit_index: int,
        generator_bit_index: int,
        refresh_interval: int,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
        state_cache: GeneratorStateCache,
        topic: str,
        name: str,
    ):
        self.driver = modbus_driver
        self.unit_id = unit_id
        self.register_offset = max(0, register_offset)
        self.register_count = max(1, register_count)
        self.line_bit_index = line_bit_index
        self.generator_bit_index = generator_bit_index
        self.refresh_interval = max(1, refresh_interval)
        self.logger = logger
        self.publisher = mqtt_publisher
        self.state_cache = state_cache
        self.topic = topic
        self.name = name
        self._last_bits: tuple[int, int] | None = None

    @staticmethod
    def _decode_breaker(raw_value: int, bit_index: int) -> dict:
        bit = (raw_value >> bit_index) & 1
        return {
            "bit": bit,
            "estado": "cerrado" if bit == 1 else "abierto",
        }

    def _build_payload(self, raw_value: int) -> dict:
        return {
            "edificio": self.name,
            "interruptor_linea": self._decode_breaker(raw_value, self.line_bit_index),
            "interruptor_grupo": self._decode_breaker(raw_value, self.generator_bit_index),
            "raw_value": raw_value,
            "ts": timebox.utc_iso(),
        }

    def _build_line_payload(self, payload: dict) -> dict:
        return {
            "edificio": payload["edificio"],
            "interruptor_linea": dict(payload["interruptor_linea"]),
            "interruptor_grupo": dict(payload["interruptor_grupo"]),
            "ts": payload["ts"],
        }

    def _run_cycle(self) -> None:
        registers = self.driver.read_holding_registers(
            address_offset=self.register_offset,
            count=self.register_count,
            unit_id=self.unit_id,
        )
        if registers is None or not registers:
            self.logger.log("Lectura edif-fontana sin registros.", origin="OBS/GE")
            return

        raw_value = int(registers[0])
        payload = self._build_payload(raw_value)
        self.state_cache.update(self.name, payload)
        current_bits = (
            int(payload["interruptor_linea"]["bit"]),
            int(payload["interruptor_grupo"]["bit"]),
        )
        if current_bits != self._last_bits and self.publisher.publish_ge_status(
            self.topic,
            self._build_line_payload(payload),
        ):
            self._last_bits = current_bits
            self.logger.log(
                "edif-fontana linea: "
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
            f"Iniciando monitor edif-fontana ({self.driver.endpoint}, HR offset {self.register_offset}, bits linea/grupo {self.line_bit_index}/{self.generator_bit_index})...",
            origin="OBS/GE",
        )

        while not stop_event.is_set():
            self._run_cycle()
            heartbeat()
            stop_event.wait(self.refresh_interval)
