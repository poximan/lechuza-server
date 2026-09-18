import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from logosaurio import Logosaurio

from src.modbus.modbus_driver import ModbusTcpReadOnlyDriver
from src.modbus.micom_relay_reader import MicomReadError, MicomRelayReader
from src.modelo.disturbance_timestamp import decode_disturbance_finish
from src.persistencia.dao.dao_fallas_reles import fallas_reles_dao
from src.persistencia.dao.dao_osciloperturbogramas import (
    osciloperturbogramas_reles_dao,
)
from src.persistencia.dao.dao_reles import reles_dao
from src.services.relay_metadata import RelayMetadataService
from src.services.relay_query_diagnostics import RelayQueryDiagnostics
from src.services.state_store import ObserverStateStore
from src.utils import timebox


class RelayMonitoringService:
    """Actualiza fallas y todos los osciloperturbogramas con vencimiento persistente."""

    CATALOG_REFRESH_SECONDS = 300
    RETRY_INTERVALS = (
        timedelta(minutes=30),
        timedelta(hours=2),
        timedelta(hours=12),
        timedelta(days=1),
    )

    def __init__(
        self,
        modbus_driver: ModbusTcpReadOnlyDriver,
        refresh_interval: int,
        logger: Logosaurio,
        observer_store: ObserverStateStore,
    ):
        self.driver = modbus_driver
        self.refresh_interval = refresh_interval
        self.logger = logger
        self.observer_store = observer_store
        self.reader = MicomRelayReader(
            modbus_driver,
            logger,
        )
        self.metadata = RelayMetadataService(self.reader, logger)
        self.query_diagnostics = RelayQueryDiagnostics()
        self.reader.query_observer = self.query_diagnostics.record
        self.relay_unit_ids: list[int] = []
        self._next_poll_datetime: datetime | None = None
        self._poll_in_progress = False
        self._state_lock = threading.RLock()
        self._last_catalog_refresh: float | None = None
        self._last_observing_status: bool | None = None
        self._failure_counts: dict[int, int] = {}
        self._stop_event = threading.Event()

    def _refresh_relay_ids(self) -> None:
        now = timebox.monotonic()
        if (
            self._last_catalog_refresh is None
            or now - self._last_catalog_refresh > self.CATALOG_REFRESH_SECONDS
        ):
            self.relay_unit_ids = list(
                reles_dao.get_all_reles_with_descriptions().keys()
            )
            self._last_catalog_refresh = now
            self.logger.log(
                f"Reles activos: {self.relay_unit_ids}",
                origin="OBS/RELE",
            )

    def _internal_id(self, relay_id: int) -> int:
        internal_id = reles_dao.get_internal_id_by_modbus_id(relay_id)
        if internal_id is None:
            raise ValueError(f"No existe el rele {relay_id}")
        return internal_id

    def read_relay_status(self, relay_id: int) -> None:
        internal_id = self._internal_id(relay_id)
        if (
            osciloperturbogramas_reles_dao.next_refresh(internal_id)
            > timebox.utc_now()
        ):
            return

        date_format = self.metadata.get_date_format(relay_id)
        if date_format is None:
            self._schedule_retry(
                relay_id,
                internal_id,
                ValueError(self.metadata.session_error(relay_id)),
            )
            return

        try:
            configuration = self.metadata.get_disturbance_configuration(relay_id)
            if configuration is None:
                raise ValueError(self.metadata.session_error(relay_id))
            references = self.reader.read_disturbance_references(relay_id)
            download_errors: list[str] = []
            for reference in references:
                if (
                    not self.observer_store.get_reles_enabled()
                    or self._stop_event.is_set()
                ):
                    return
                cached = osciloperturbogramas_reles_dao.get(
                    internal_id,
                    reference.record_number,
                )
                signature = list(reference.signature)
                if cached and cached.get("signature") == signature:
                    continue
                try:
                    payload = self.reader.read_disturbance(
                        relay_id,
                        configuration,
                        reference,
                    )
                    finish = decode_disturbance_finish(
                        payload["metadata"]["finish_words"],
                        date_format,
                    )
                    payload["metadata"]["finish_timestamp"] = (
                        timebox.utc_iso_milliseconds(finish)
                    )
                    payload["metadata"]["trigger_timestamp"] = (
                        timebox.utc_iso_milliseconds(
                            finish - timedelta(seconds=payload["post_seconds"])
                        )
                    )
                    payload["signature"] = signature
                    osciloperturbogramas_reles_dao.save(internal_id, payload)
                except (MicomReadError, ValueError) as exc:
                    download_errors.append(
                        f"registro {reference.record_number}: {exc}"
                    )
                    self.logger.log(
                        f"No se completo el osciloperturbograma "
                        f"{reference.record_number} del rele {relay_id}: {exc}",
                        origin="OBS/RELE",
                    )
            if download_errors:
                raise MicomReadError("; ".join(download_errors))
            self.metadata.get_current_profile(relay_id)
            self._refresh_latest_fault(relay_id, internal_id, date_format)
            osciloperturbogramas_reles_dao.complete(
                internal_id,
                [reference.record_number for reference in references],
            )
            self._failure_counts.pop(internal_id, None)
        except (MicomReadError, ValueError) as exc:
            self._schedule_retry(relay_id, internal_id, exc)

    def _refresh_latest_fault(
        self,
        relay_id: int,
        internal_id: int,
        date_format: int,
    ) -> None:
        record = self.reader.read_latest_fault(relay_id, date_format)
        fallas_reles_dao.replace_if_newer(
            internal_id,
            record.fault_number,
            timebox.utc_iso_milliseconds(record.fault_datetime),
            record.timestamp_format,
            record.current_phase_a,
            record.current_phase_b,
            record.current_phase_c,
            record.earth_current,
        )

    def _schedule_retry(
        self,
        relay_id: int,
        internal_id: int,
        error: Exception,
    ) -> None:
        failure_count = self._failure_counts.get(internal_id, 0) + 1
        self._failure_counts[internal_id] = failure_count
        retry_interval = self.RETRY_INTERVALS[
            min(failure_count - 1, len(self.RETRY_INTERVALS) - 1)
        ]
        osciloperturbogramas_reles_dao.failed(
            internal_id,
            error,
            retry_interval,
        )
        self.logger.log(
            f"No se completo la descarga del rele {relay_id}: {error}. "
            f"Proximo intento en {int(retry_interval.total_seconds())} segundos.",
            origin="OBS/RELE",
        )

    def _next_modbus_query_delay(self) -> float:
        now = timebox.utc_now()
        return min(
            (
                max(
                    0.0,
                    (
                        osciloperturbogramas_reles_dao.next_refresh(
                            self._internal_id(relay_id)
                        )
                        - now
                    ).total_seconds(),
                )
                for relay_id in self.relay_unit_ids
            ),
            default=float(self.refresh_interval),
        )

    def transport_required(self) -> bool:
        return self.observer_store.get_reles_enabled() and self._modbus_query_due()

    def _modbus_query_due(self) -> bool:
        return bool(self.relay_unit_ids) and self._next_modbus_query_delay() <= 0

    def _start_observer_session(self) -> None:
        with self._state_lock:
            self.metadata.reset_session()
            self.query_diagnostics.reset()
            self._last_catalog_refresh = None
            self._next_poll_datetime = None
            self._poll_in_progress = False
        self.logger.log(
            "Nueva sesion de observacion: se reutilizan los parametros MiCOM "
            "persistidos y solo se leen los faltantes.",
            origin="OBS/RELE",
        )

    def get_observer_runtime_snapshot(self) -> dict:
        enabled = self.observer_store.get_reles_enabled()
        with self._state_lock:
            starting = enabled and self._last_observing_status is not True
            return {
                "enabled": enabled,
                "poll_in_progress": bool(
                    enabled and not starting and self._poll_in_progress
                ),
                "next_poll_timestamp": (
                    timebox.utc_iso(self._next_poll_datetime)
                    if enabled
                    and not starting
                    and self._next_poll_datetime is not None
                    else None
                ),
                "refresh_interval_seconds": self.refresh_interval,
            }

    def start_monitoring_loop(
        self,
        stop_event: threading.Event,
        heartbeat: Callable[[], None],
    ) -> None:
        self.logger.log(
            f"Iniciando observador de reles (intervalo: {self.refresh_interval}s, "
            "actualizacion de registros: 30 dias).",
            origin="OBS/RELE",
        )

        self._stop_event = stop_event
        while not stop_event.is_set():
            enabled = self.observer_store.get_reles_enabled()
            if enabled != self._last_observing_status:
                if enabled:
                    self._start_observer_session()
                self.logger.log(
                    "Monitoreo de reles reanudado" if enabled else "Monitoreo de reles pausado",
                    origin="OBS/RELE",
                )
                self._last_observing_status = enabled

            if enabled:
                self._refresh_relay_ids()
                if self._modbus_query_due():
                    with self._state_lock:
                        self._poll_in_progress = True
                        self._next_poll_datetime = None
                    try:
                        for relay_id in self.relay_unit_ids:
                            if (
                                stop_event.is_set()
                                or not self.observer_store.get_reles_enabled()
                            ):
                                break
                            self.read_relay_status(relay_id)
                    finally:
                        with self._state_lock:
                            self._poll_in_progress = False
                with self._state_lock:
                    self._next_poll_datetime = (
                        timebox.utc_now()
                        + timedelta(seconds=self._next_modbus_query_delay())
                        if self.observer_store.get_reles_enabled()
                        else None
                    )
            else:
                with self._state_lock:
                    self._poll_in_progress = False
                    self._next_poll_datetime = None

            heartbeat()
            stop_event.wait(self.refresh_interval)
