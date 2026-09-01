import threading
from collections import deque
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from typing import cast

from logosaurio import Logosaurio

from src import config
from src.modelo.rele_micom import (
    MicomCurrentIdentity,
    MicomCurrentProfile,
    MicomCurrentTransformers,
    MicomDisturbanceConfiguration,
)
from src.persistencia.dao.dao_fallas_reles import fallas_reles_dao
from src.persistencia.dao.dao_reles import reles_dao
from src.services.state_store import ObserverStateStore
from src.utils import timebox

from .modbus_driver import ModbusTcpReadOnlyDriver
from .micom_relay_reader import MicomReadError, MicomRelayReader


class ProtectionRelayClient:
    """Monitorea la ultima falla y la perturbacion mas reciente de cada rele."""

    CATALOG_REFRESH_SECONDS = 300
    DISTURBANCE_RETRY_SECONDS = 60
    DISTURBANCE_READ_ATTEMPTS = 2
    FAULT_RECOGNITION_INTERVAL_SECONDS = 3600

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
            query_observer=self._record_query,
        )
        if (
            config.RELAY_LATEST_FAULT_ADDRESS != self.reader.FAULT_ADDRESS
            or config.RELAY_FAULT_REGISTER_COUNT != self.reader.FAULT_WORDS
        ):
            raise ValueError(
                "El mapa de fallas configurado no coincide con el mapa MiCOM: "
                f"direccion={hex(config.RELAY_LATEST_FAULT_ADDRESS)}, "
                f"palabras={config.RELAY_FAULT_REGISTER_COUNT}"
            )
        self.relay_unit_ids: list[int] = []
        self._last_fault_signatures: dict[int, tuple] = {}
        self._last_fault_recognitions: dict[int, float] = {}
        self._current_profiles: dict[int, MicomCurrentProfile] = {}
        self._current_profile_parts: dict[int, dict[str, object]] = {}
        self._current_profile_errors: dict[int, dict[str, str]] = {}
        self._date_formats: dict[int, int] = {}
        self._date_format_errors: dict[int, str] = {}
        self._disturbance_configurations: dict[
            int,
            MicomDisturbanceConfiguration,
        ] = {}
        self._disturbance_configuration_parts: dict[int, dict[str, int]] = {}
        self._disturbance_configuration_errors: dict[int, dict[str, str]] = {}
        self._disturbances: dict[int, dict] = {}
        self._disturbance_attempts: dict[int, float] = {}
        self._recent_queries: dict[int, deque[dict]] = {}
        self._next_poll_datetime: datetime | None = None
        self._poll_in_progress = False
        self._state_lock = threading.RLock()
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

    def _record_query(self, event: dict) -> None:
        relay_id = int(event["relay_id"])
        with self._state_lock:
            history = self._recent_queries.setdefault(relay_id, deque(maxlen=4))
            history.appendleft(deepcopy(event))

    def read_relay_status(self, relay_id: int) -> dict | None:
        self._refresh_latest_disturbance(relay_id)
        if not self._fault_recognition_due(relay_id):
            self._get_current_profile(relay_id)
            return None
        date_format = self._get_date_format(relay_id)
        if date_format is None:
            self._get_current_profile(relay_id)
            return None
        try:
            record = self.reader.read_latest_fault(relay_id, date_format)
        except (MicomReadError, ValueError) as exc:
            self.logger.log(
                f"No se pudo reconocer la ultima falla del rele {relay_id}: {exc}",
                origin="OBS/RELE",
            )
            self._get_current_profile(relay_id)
            return None
        with self._state_lock:
            self._last_fault_recognitions[relay_id] = timebox.monotonic()
        internal_id = reles_dao.get_internal_id_by_modbus_id(relay_id)
        if internal_id is None:
            raise RuntimeError(
                f"El rele Modbus {relay_id} no tiene ID interno en el catalogo migrado"
            )

        timestamp = timebox.utc_iso_milliseconds(record.fault_datetime)
        signature = (record.fault_number, timestamp)

        if self._last_fault_signatures.get(relay_id) != signature:
            replaced = fallas_reles_dao.replace_if_newer(
                id_rele=internal_id,
                numero_falla=record.fault_number,
                timestamp=timestamp,
                formato_timestamp=record.timestamp_format,
                fasea_corr=record.current_phase_a,
                faseb_corr=record.current_phase_b,
                fasec_corr=record.current_phase_c,
                tierra_corr=record.earth_current,
            )
            self._last_fault_signatures[relay_id] = signature
            if replaced:
                self.logger.log(
                    f"Falla actual del rele {relay_id} reemplazada por "
                    f"la numero {record.fault_number}.",
                    origin="OBS/RELE",
                )

        self._get_current_profile(relay_id)
        return record.to_dict()

    def _fault_recognition_due(self, relay_id: int) -> bool:
        with self._state_lock:
            last_recognition = self._last_fault_recognitions.get(relay_id)
        return (
            last_recognition is None
            or timebox.monotonic() - last_recognition
            >= self.FAULT_RECOGNITION_INTERVAL_SECONDS
        )

    def _refresh_latest_disturbance(self, relay_id: int) -> None:
        configuration = self._get_disturbance_configuration(relay_id)
        if configuration is None:
            with self._state_lock:
                errors = self._disturbance_configuration_errors.get(relay_id, {})
                message = (
                    "; ".join(errors.values())
                    or "La frecuencia nominal aun no fue leida del rele."
                )
            self._set_disturbance_error(relay_id, message)
            return

        try:
            reference = self.reader.read_latest_disturbance_reference(relay_id)
        except (MicomReadError, ValueError) as exc:
            self._set_disturbance_error(relay_id, str(exc))
            return

        signature = reference.signature
        if not self._disturbance_due(relay_id, signature):
            return
        last_error: MicomReadError | ValueError | None = None
        for attempt in range(self.DISTURBANCE_READ_ATTEMPTS):
            try:
                disturbance = self.reader.read_disturbance(
                    relay_id,
                    configuration,
                    reference,
                )
            except (MicomReadError, ValueError) as exc:
                last_error = exc
                self.driver.disconnect()
                if attempt + 1 < self.DISTURBANCE_READ_ATTEMPTS:
                    continue
                break
            disturbance["signature"] = list(signature)
            with self._state_lock:
                self._disturbances[relay_id] = disturbance
            last_error = None
            break
        if last_error is not None:
            self._set_disturbance_error(
                relay_id,
                str(last_error),
                record_number=reference.record_number,
                signature=signature,
            )
        with self._state_lock:
            self._disturbance_attempts[relay_id] = timebox.monotonic()

    def _get_current_profile(self, relay_id: int) -> MicomCurrentProfile | None:
        with self._state_lock:
            cached = self._current_profiles.get(relay_id)
        if cached is not None:
            return cached

        operations = {
            "identidad": self.reader.read_current_identity,
            "transformadores": self.reader.read_current_transformers,
        }
        with self._state_lock:
            parts = self._current_profile_parts.setdefault(relay_id, {})
            errors = self._current_profile_errors.setdefault(relay_id, {})
        for part_name, operation in operations.items():
            if part_name in parts:
                continue
            try:
                value = operation(relay_id)
            except (MicomReadError, ValueError) as exc:
                message = str(exc)
                with self._state_lock:
                    previous_error = errors.get(part_name)
                    errors[part_name] = message
                if previous_error != message:
                    self.logger.log(
                        f"No se pudo cargar {part_name} del rele {relay_id}; "
                        f"se reintentara: {message}",
                        origin="OBS/RELE",
                    )
                continue
            with self._state_lock:
                parts[part_name] = value
                errors.pop(part_name, None)

        if any(part_name not in parts for part_name in operations):
            return None

        try:
            profile = MicomCurrentProfile.from_parts(
                cast(MicomCurrentIdentity, parts["identidad"]),
                cast(MicomCurrentTransformers, parts["transformadores"]),
            )
        except ValueError as exc:
            with self._state_lock:
                errors["validacion"] = str(exc)
            return None
        with self._state_lock:
            self._current_profiles[relay_id] = profile
            self._current_profile_errors.pop(relay_id, None)
        self.logger.log(
            f"Escala del rele {relay_id} cargada para la sesion del observador.",
            origin="OBS/RELE",
        )
        return profile

    def _get_date_format(self, relay_id: int) -> int | None:
        with self._state_lock:
            if relay_id in self._date_formats:
                return self._date_formats[relay_id]
        try:
            date_format = self.reader.read_date_format(relay_id)
            if date_format not in {0, 1}:
                raise ValueError(
                    f"Formato de fecha fuera de contrato: {date_format}"
                )
        except (MicomReadError, ValueError) as exc:
            message = str(exc)
            with self._state_lock:
                previous_error = self._date_format_errors.get(relay_id)
                self._date_format_errors[relay_id] = message
            if previous_error != message:
                self.logger.log(
                    f"No se pudo cargar el formato de fecha del rele {relay_id}; "
                    f"se reintentara: {message}",
                    origin="OBS/RELE",
                )
            return None
        with self._state_lock:
            self._date_formats[relay_id] = date_format
            self._date_format_errors.pop(relay_id, None)
        return date_format

    def _get_disturbance_configuration(
        self,
        relay_id: int,
    ) -> MicomDisturbanceConfiguration | None:
        with self._state_lock:
            cached = self._disturbance_configurations.get(relay_id)
        if cached is not None:
            return cached

        operations = {
            "frecuencia": self.reader.read_nominal_frequency,
        }
        with self._state_lock:
            parts = self._disturbance_configuration_parts.setdefault(relay_id, {})
            errors = self._disturbance_configuration_errors.setdefault(relay_id, {})
        for part_name, operation in operations.items():
            if part_name in parts:
                continue
            try:
                value = operation(relay_id)
            except (MicomReadError, ValueError) as exc:
                message = str(exc)
                with self._state_lock:
                    previous_error = errors.get(part_name)
                    errors[part_name] = message
                if previous_error != message:
                    self.logger.log(
                        f"No se pudo cargar {part_name} de perturbaciones del rele "
                        f"{relay_id}; se reintentara: {message}",
                        origin="OBS/RELE",
                    )
                continue
            with self._state_lock:
                parts[part_name] = int(value)
                errors.pop(part_name, None)

        if any(part_name not in parts for part_name in operations):
            return None
        configuration = MicomDisturbanceConfiguration(
            nominal_frequency_hz=parts["frecuencia"],
        )
        with self._state_lock:
            self._disturbance_configurations[relay_id] = configuration
            self._disturbance_configuration_errors.pop(relay_id, None)
        return configuration

    def _start_observer_session(self) -> None:
        with self._state_lock:
            self._current_profiles.clear()
            self._current_profile_parts.clear()
            self._current_profile_errors.clear()
            self._date_formats.clear()
            self._date_format_errors.clear()
            self._disturbance_configurations.clear()
            self._disturbance_configuration_parts.clear()
            self._disturbance_configuration_errors.clear()
            self._disturbances.clear()
            self._disturbance_attempts.clear()
            self._recent_queries.clear()
            self._last_fault_signatures.clear()
            self._last_fault_recognitions.clear()
            self._last_catalog_refresh = None
            self._next_poll_datetime = None
            self._poll_in_progress = False
        self.logger.log(
            "Nueva sesion de observacion: se cargaran una vez los parametros MiCOM.",
            origin="OBS/RELE",
        )

    def get_current_calculation_snapshot(self, relay_id: int) -> dict:
        if (
            self.observer_store.get_reles_enabled()
            and self._last_observing_status is not True
        ):
            return {
                "status": "pending",
                "message": "La nueva sesion del observador aun no cargo la escala.",
            }
        with self._state_lock:
            profile = self._current_profiles.get(relay_id)
            errors = self._current_profile_errors.get(relay_id, {})
            if profile is not None:
                return profile.calculation_contract()
            return {
                "status": "unavailable" if errors else "pending",
                "message": (
                    "; ".join(errors.values())
                    if errors
                    else "La escala aun no fue leida del rele."
                ),
            }

    def get_query_snapshot(self, relay_id: int) -> list[dict]:
        with self._state_lock:
            return deepcopy(list(self._recent_queries.get(relay_id, ())))

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

    def _disturbance_due(self, relay_id: int, signature: tuple) -> bool:
        with self._state_lock:
            cached = self._disturbances.get(relay_id)
            if cached is None or tuple(cached.get("signature", ())) != signature:
                return True
            if cached.get("status") == "available":
                return False
            last_attempt = self._disturbance_attempts.get(relay_id)
            return (
                last_attempt is None
                or timebox.monotonic() - last_attempt >= self.DISTURBANCE_RETRY_SECONDS
            )

    def _set_disturbance_error(
        self,
        relay_id: int,
        message: str,
        *,
        record_number: int | None = None,
        signature: tuple | None = None,
    ) -> None:
        with self._state_lock:
            cached = self._disturbances.get(relay_id)
            if cached is not None and cached.get("status") == "available":
                cached["refresh_error"] = message
                cached["refresh_error_timestamp"] = timebox.utc_iso()
                return
            self._disturbances[relay_id] = {
                "status": "unavailable",
                "message": message,
                "record_number": record_number,
                "signature": list(signature or ()),
                "channels": {},
            }

    def get_disturbance_snapshot(self, relay_id: int) -> dict:
        if (
            self.observer_store.get_reles_enabled()
            and self._last_observing_status is not True
        ):
            return {
                "status": "pending",
                "message": "La nueva sesion del observador aun no leyo la perturbacion.",
                "record_number": None,
                "channels": {},
            }
        with self._state_lock:
            snapshot = self._disturbances.get(relay_id)
            if snapshot is None:
                return {
                    "status": "pending",
                    "message": "La perturbacion aun no fue leida del rele.",
                    "record_number": None,
                    "channels": {},
                }
            return deepcopy(snapshot)

    def start_monitoring_loop(
        self,
        stop_event: threading.Event,
        heartbeat: Callable[[], None],
    ) -> None:
        self.logger.log(
            f"Iniciando observador de reles (intervalo: {self.refresh_interval}s, "
            "reconocimiento de fallas: 1h).",
            origin="OBS/RELE",
        )

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
                with self._state_lock:
                    self._poll_in_progress = True
                    self._next_poll_datetime = None
                try:
                    self._refresh_relay_ids()
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
                        self._next_poll_datetime = (
                            timebox.utc_now()
                            + timedelta(seconds=self.refresh_interval)
                            if self.observer_store.get_reles_enabled()
                            else None
                        )
            else:
                with self._state_lock:
                    self._poll_in_progress = False
                    self._next_poll_datetime = None

            heartbeat()
            stop_event.wait(self.refresh_interval)
