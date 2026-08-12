import threading
from collections.abc import Callable

from logosaurio import Logosaurio

from src import config
from src.modelo.registro_falla import RegistroFalla
from src.persistencia.dao.dao_fallas_reles import fallas_reles_dao
from src.persistencia.dao.dao_reles import reles_dao
from src.services.state_store import ObserverStateStore
from src.utils import timebox

from .modbus_driver import ModbusTcpDriver


class ProtectionRelayClient:
    """Monitorea el bloque de la ultima falla informado por cada rele."""

    CATALOG_REFRESH_SECONDS = 300

    def __init__(
        self,
        modbus_driver: ModbusTcpDriver,
        refresh_interval: int,
        logger: Logosaurio,
        observer_store: ObserverStateStore,
    ):
        self.driver = modbus_driver
        self.refresh_interval = refresh_interval
        self.logger = logger
        self.observer_store = observer_store
        self.relay_unit_ids: list[int] = []
        self._last_fault_signatures: dict[int, tuple[int, str]] = {}
        self._last_catalog_refresh: float | None = None
        self._last_observing_status: bool | None = None

    def _refresh_relay_ids(self) -> None:
        now = timebox.monotonic()
        if (
            self._last_catalog_refresh is None
            or now - self._last_catalog_refresh > self.CATALOG_REFRESH_SECONDS
        ):
            self.relay_unit_ids = list(reles_dao.get_all_reles_with_descriptions().keys())
            self._last_catalog_refresh = now
            self.logger.log(
                f"Reles activos: {self.relay_unit_ids}",
                origin="OBS/RELE",
            )

    def read_relay_status(self, relay_id: int) -> dict | None:
        address = config.RELAY_LATEST_FAULT_ADDRESS
        count = config.RELAY_FAULT_REGISTER_COUNT
        registers = self.driver.read_holding_registers(
            address,
            count,
            unit_id=relay_id,
        )
        if registers is None:
            self.logger.log(
                f"Lectura no disponible para rele {relay_id} en {hex(address)}.",
                origin="OBS/RELE",
            )
            return None

        record = RegistroFalla(registers, self.logger)
        if record.fault_datetime is None or record.fault_date_validity != 0:
            self.logger.log(
                f"Rele {relay_id} devolvio una falla sin timestamp valido; no se persiste.",
                origin="OBS/RELE",
            )
            return None

        internal_id = reles_dao.get_internal_id_by_modbus_id(relay_id)
        if internal_id is None:
            raise RuntimeError(
                f"El rele Modbus {relay_id} no tiene ID interno en el catalogo migrado"
            )

        timestamp = timebox.utc_iso(record.fault_datetime)
        signature = (record.fault_number, timestamp)
        if self._last_fault_signatures.get(relay_id) == signature:
            return record.to_dict()

        inserted = fallas_reles_dao.insert_if_absent(
            id_rele=internal_id,
            numero_falla=record.fault_number,
            timestamp=timestamp,
            fasea_corr=record.current_phase_a,
            faseb_corr=record.current_phase_b,
            fasec_corr=record.current_phase_c,
            tierra_corr=record.earth_current,
        )
        self._last_fault_signatures[relay_id] = signature
        if inserted:
            self.logger.log(
                f"Falla {record.fault_number} del rele {relay_id} persistida.",
                origin="OBS/RELE",
            )
        return record.to_dict()

    def start_monitoring_loop(
        self,
        stop_event: threading.Event,
        heartbeat: Callable[[], None],
    ) -> None:
        self.logger.log(
            f"Iniciando observador de reles (intervalo: {self.refresh_interval}s, "
            f"registro: {hex(config.RELAY_LATEST_FAULT_ADDRESS)}).",
            origin="OBS/RELE",
        )

        while not stop_event.is_set():
            enabled = self.observer_store.get_reles_enabled()
            if enabled != self._last_observing_status:
                self.logger.log(
                    "Monitoreo de reles reanudado" if enabled else "Monitoreo de reles pausado",
                    origin="OBS/RELE",
                )
                self._last_observing_status = enabled

            if enabled:
                self._refresh_relay_ids()
                for relay_id in self.relay_unit_ids:
                    if stop_event.is_set() or not self.observer_store.get_reles_enabled():
                        break
                    self.read_relay_status(relay_id)

            heartbeat()
            stop_event.wait(self.refresh_interval)
