import threading
from collections.abc import Callable

from logosaurio import Logosaurio

from src import config
from src.control.latest_state_registry import LatestStateRegistry
from src.persistencia.dao.dao_estado_grd import grd_state_dao
from src.persistencia.dao.dao_grd import grd_dao
from src.services.grd_service import GrdService
from src.services.alarm_generator import ModbusAlarmGenerator
from src.services.mqtt_publisher import ModbusMqttPublisher
from src.utils import timebox

from .modbus_driver import ModbusTcpReadOnlyDriver


class GrdMiddlewareClient:
    """Monitorea GRD, persiste transiciones y publica snapshots MQTT."""

    CATALOG_REFRESH_SECONDS = 300

    def __init__(
        self,
        modbus_driver: ModbusTcpReadOnlyDriver,
        default_unit_id: int,
        register_count: int,
        refresh_interval: int,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
        state_registry: LatestStateRegistry,
        grd_service: GrdService,
        alarm_generator: ModbusAlarmGenerator,
    ):
        self.driver = modbus_driver
        self.default_unit_id = default_unit_id
        self.register_count = register_count
        self.refresh_interval = refresh_interval
        self.logger = logger
        self.publisher = mqtt_publisher
        self.state_registry = state_registry
        self.grd_service = grd_service
        self.alarm_generator = alarm_generator
        self.failure_threshold = config.GRD_FAILURE_THRESHOLD

        self._active_grd_data: dict[int, str] | None = None
        self._last_grd_data_refresh: float | None = None
        self._last_payload_grado: dict | None = None
        self._last_payload_down: dict | None = None

    def _refresh_grd_data(self) -> None:
        now = timebox.monotonic()
        if (
            self._last_grd_data_refresh is None
            or now - self._last_grd_data_refresh > self.CATALOG_REFRESH_SECONDS
        ):
            self._active_grd_data = grd_dao.get_all_grds_with_descriptions(only_active=True)
            self._last_grd_data_refresh = now
            if not self._active_grd_data:
                self.logger.log(
                    "No hay GRD activos en el catalogo operativo.",
                    origin="OBS/MW",
                )
            else:
                self.logger.log(
                    f"GRD activos: {list(self._active_grd_data.keys())}",
                    origin="OBS/MW",
                )

    @staticmethod
    def get_bit(value: int, bit_index: int) -> int:
        return (value >> bit_index) & 1

    def _publish_snapshots_if_changed(self) -> None:
        contract = self.grd_service.summary()
        summary = contract["summary"]
        grado_state = {
            "porcentaje": summary["porcentaje"],
            "total": summary["total"],
            "conectados": summary["conectados"],
            "no_disponibles": summary["no_disponibles"],
        }
        down_state = {
            "items": [
                {
                    "id": item["id_grd"],
                    "nombre": item["description"],
                    "ultima_caida": item["last_disconnected_timestamp"],
                }
                for item in contract["disconnected"]
            ]
        }

        if grado_state != self._last_payload_grado:
            payload = {**grado_state, "ts": timebox.utc_iso()}
            if self.publisher.publish_grado(payload):
                self._last_payload_grado = grado_state
                self.logger.log(
                    f"Publicado grado global en {config.MQTT_TOPIC_GRADO}: {payload}",
                    origin="OBS/MW",
                )

        if down_state != self._last_payload_down:
            payload = {**down_state, "ts": timebox.utc_iso()}
            if self.publisher.publish_grds(payload):
                self._last_payload_down = down_state
                self.logger.log(
                    f"Publicado snapshot de desconectados en {config.MQTT_TOPIC_GRDS}: {payload}",
                    origin="OBS/MW",
                )

    def _read_grd_state(self, grd_id: int, description: str, timestamp: str) -> int | None:
        address = (grd_id - 1) * self.register_count
        registers = self.driver.read_input_registers(
            address,
            self.register_count,
            unit_id=self.default_unit_id,
        )
        if registers is not None and len(registers) >= 16:
            self.state_registry.mark_read_success(grd_id)
            return self.get_bit(int(registers[15]), 0)

        failures = self.state_registry.mark_read_failure(grd_id, timestamp)
        self.logger.log(
            f"Lectura no disponible para GRD {grd_id} ({description}); "
            f"fallos consecutivos={failures}/{self.failure_threshold}.",
            origin="OBS/MW",
        )
        if failures < self.failure_threshold:
            return None

        self.logger.log(
            f"GRD {grd_id} ({description}) declarado desconectado luego de "
            f"{failures} fallos consecutivos.",
            origin="OBS/MW",
        )
        return 0

    def _run_cycle(self, stop_event: threading.Event) -> None:
        unavailable_before = self.state_registry.unavailable_snapshot()
        self._refresh_grd_data()
        grd_data = self._active_grd_data or {}
        if not grd_data:
            if self._last_payload_grado is None or self._last_payload_down is None:
                self._publish_snapshots_if_changed()
            return

        timestamp = timebox.utc_iso()
        if not self.driver.is_connected() and not self.driver.connect():
            for grd_id in grd_data:
                if grd_id != 4:
                    self.state_registry.mark_read_failure(
                        grd_id,
                        timestamp,
                        confirmable=False,
                    )
            self.logger.log(
                "Servidor Modbus no disponible; se conserva el ultimo estado confirmado.",
                origin="OBS/MW",
            )
            if unavailable_before != self.state_registry.unavailable_snapshot():
                self._publish_snapshots_if_changed()
            return

        changed = False
        monitored = [item for item in grd_data.items() if item[0] != 4]
        for index, (grd_id, description) in enumerate(monitored):
            if stop_event.is_set():
                break
            current = self._read_grd_state(grd_id, description, timestamp)
            if current is not None and current != self.state_registry.get(grd_id):
                grd_state_dao.record_transition(grd_id, timestamp, current)
                self.state_registry.update(grd_id, current)
                changed = True
                self.logger.log(
                    f"Transicion confirmada en {description}: conectado={current}",
                    origin="OBS/MW",
                )

            if not self.driver.is_connected():
                for pending_id, _pending_description in monitored[index + 1:]:
                    self.state_registry.mark_read_failure(
                        pending_id,
                        timestamp,
                        confirmable=False,
                    )
                break

        if (
            changed
            or unavailable_before != self.state_registry.unavailable_snapshot()
            or self._last_payload_grado is None
            or self._last_payload_down is None
        ):
            self._publish_snapshots_if_changed()
        self.alarm_generator.observe_grd_snapshot(
            self.grd_service.summary(),
            grd_data,
        )

    def start_observer_loop(
        self,
        stop_event: threading.Event,
        heartbeat: Callable[[], None],
    ) -> None:
        self.logger.log(
            f"Iniciando observador GRD (Unit ID: {self.default_unit_id}, "
            f"intervalo: {self.refresh_interval}s).",
            origin="OBS/MW",
        )
        self._publish_snapshots_if_changed()

        while not stop_event.is_set():
            self._run_cycle(stop_event)
            heartbeat()
            stop_event.wait(self.refresh_interval)
