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
    MicomDisturbanceReference,
    MicomRelayClock,
)
from src.modelo.registro_falla import RegistroFalla
from src.persistencia.dao.dao_fallas_reles import fallas_reles_dao
from src.persistencia.dao.dao_reles import reles_dao
from src.services.state_store import ObserverStateStore
from src.utils import timebox

from .modbus_driver import ModbusTcpReadOnlyDriver
from .micom_relay_reader import MicomReadError, MicomRelayReader


class ProtectionRelayClient:
    """Monitorea la ultima falla y la perturbacion mas reciente de cada rele."""

    CATALOG_REFRESH_SECONDS = 300
    DISTURBANCE_ASSOCIATION_TOLERANCE_SECONDS = 5.0
    DISTURBANCE_PRECISE_TOLERANCE_SECONDS = 0.050
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
        self._pending_disturbance_faults: dict[int, RegistroFalla] = {}
        self._current_profiles: dict[int, MicomCurrentProfile] = {}
        self._current_profiles_refreshed: set[int] = set()
        self._current_profile_parts: dict[int, dict[str, object]] = {}
        self._current_profile_errors: dict[int, dict[str, str]] = {}
        self._date_formats: dict[int, int] = {}
        self._date_formats_refreshed: set[int] = set()
        self._date_format_errors: dict[int, str] = {}
        self._disturbance_configurations: dict[
            int,
            MicomDisturbanceConfiguration,
        ] = {}
        self._disturbance_configurations_refreshed: set[int] = set()
        self._disturbance_configuration_parts: dict[int, dict[str, int]] = {}
        self._disturbance_configuration_errors: dict[int, dict[str, str]] = {}
        self._disturbances: dict[int, dict] = {}
        self._recent_queries: dict[int, deque[dict]] = {}
        self._pending_disturbance_page_queries: dict[
            tuple[int, int], dict
        ] = {}
        self._next_poll_datetime: datetime | None = None
        self._poll_in_progress = False
        self._state_lock = threading.RLock()
        self._last_catalog_refresh: float | None = None
        self._last_observing_status: bool | None = None
        self._load_persisted_relay_metadata()

    def _load_persisted_relay_metadata(self) -> None:
        for relay_id, metadata in reles_dao.get_all_relay_metadata().items():
            date_format = metadata.get("formato_fecha")
            if date_format is not None:
                if date_format not in {0, 1}:
                    raise ValueError(
                        f"Formato de fecha persistido invalido para rele {relay_id}"
                    )
                self._date_formats[relay_id] = int(date_format)

            stored_profile = (
                metadata.get("producto"),
                metadata.get("fase_tc_primario"),
                metadata.get("fase_tc_secundario"),
                metadata.get("tierra_tc_primario"),
                metadata.get("tierra_tc_secundario"),
                metadata.get("fase_relacion_interna"),
                metadata.get("tierra_relacion_interna"),
            )
            if all(value is not None for value in stored_profile):
                self._current_profiles[relay_id] = MicomCurrentProfile(
                    phase_primary_ct=int(stored_profile[1]),
                    earth_primary_ct=int(stored_profile[3]),
                    phase_internal_ratio=int(stored_profile[5]),
                    earth_internal_ratio=int(stored_profile[6]),
                )
            elif any(value is not None for value in stored_profile):
                raise ValueError(
                    f"Perfil de corriente persistido incompleto para rele {relay_id}"
                )

            frequency = metadata.get("frecuencia_nominal")
            if frequency is not None:
                self._disturbance_configurations[relay_id] = (
                    MicomDisturbanceConfiguration(int(frequency))
                )

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
        address = int(str(event["address"]), 16)
        page = address >> 8
        page_offset = address & 0xFF
        is_disturbance_page = (
            self.reader.DISTURBANCE_PAGE_FIRST <= page <= 0x21
            and int(event["count"]) == self.reader.MODBUS_MAX_READ_WORDS
            and page_offset in {0, self.reader.MODBUS_MAX_READ_WORDS}
        )
        with self._state_lock:
            history = self._recent_queries.setdefault(relay_id, deque(maxlen=4))
            if not is_disturbance_page:
                history.appendleft(deepcopy(event))
                return

            query_key = (relay_id, page)
            if page_offset == 0:
                logical_query = deepcopy(event)
                logical_query["address"] = f"0x{page << 8:04X}"
                logical_query["count"] = self.reader.DISTURBANCE_SAMPLES_PER_PAGE
                logical_query["received_count"] = int(
                    event.get("received_count") or 0
                )
                logical_query["physical_requests"] = 1
                if event["status"] == "ok":
                    self._pending_disturbance_page_queries[query_key] = logical_query
                else:
                    history.appendleft(logical_query)
                return

            first_part = self._pending_disturbance_page_queries.pop(
                query_key,
                None,
            )
            if first_part is None:
                logical_query = deepcopy(event)
                logical_query["address"] = f"0x{page << 8:04X}"
                logical_query["count"] = self.reader.DISTURBANCE_SAMPLES_PER_PAGE
                logical_query["received_count"] = int(
                    event.get("received_count") or 0
                )
                logical_query["physical_requests"] = 1
                history.appendleft(logical_query)
                return

            received_count = int(first_part["received_count"]) + int(
                event.get("received_count") or 0
            )
            first_part["received_count"] = received_count
            first_part["physical_requests"] = 2
            first_part["duration_ms"] = round(
                float(first_part["duration_ms"]) + float(event["duration_ms"]),
                1,
            )
            first_part["timestamp"] = event["timestamp"]
            if event["status"] != "ok":
                first_part["status"] = event["status"]
            history.appendleft(first_part)

    def read_relay_status(self, relay_id: int) -> dict | None:
        self._get_current_profile(relay_id)
        date_format = self._get_date_format(relay_id)
        self._get_disturbance_configuration(relay_id)

        record: RegistroFalla | None = None
        if self._fault_recognition_due(relay_id):
            if date_format is None:
                return None
            try:
                record = self.reader.read_latest_fault(relay_id, date_format)
            except (MicomReadError, ValueError) as exc:
                self.logger.log(
                    f"No se pudo reconocer la ultima falla del rele {relay_id}: {exc}",
                    origin="OBS/RELE",
                )
                return None
            self._register_recognized_fault(relay_id, record, date_format)

        with self._state_lock:
            pending_fault = self._pending_disturbance_faults.get(relay_id)
        if pending_fault is not None and date_format is not None:
            internal_id = reles_dao.get_internal_id_by_modbus_id(relay_id)
            if internal_id is None:
                raise RuntimeError(
                    f"El rele Modbus {relay_id} no tiene ID interno en el catalogo"
                )
            if self._refresh_latest_disturbance(
                relay_id,
                internal_id,
                pending_fault,
                date_format,
            ):
                with self._state_lock:
                    current_pending = self._pending_disturbance_faults.get(relay_id)
                    if current_pending is pending_fault:
                        self._pending_disturbance_faults.pop(relay_id, None)

        return record.to_dict() if record is not None else None

    def _register_recognized_fault(
        self,
        relay_id: int,
        record: RegistroFalla,
        date_format: int,
    ) -> None:
        internal_id = reles_dao.get_internal_id_by_modbus_id(relay_id)
        if internal_id is None:
            raise RuntimeError(
                f"El rele Modbus {relay_id} no tiene ID interno en el catalogo"
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

        current_fault = fallas_reles_dao.get_current_falla_for_rele(internal_id)
        if (
            current_fault is not None
            and current_fault["numero_falla"] == record.fault_number
            and current_fault["timestamp"] == timestamp
        ):
            with self._state_lock:
                self._pending_disturbance_faults[relay_id] = record
        else:
            self.logger.log(
                f"No se vinculo una perturbacion al rele {relay_id}: "
                "la falla reconocida no coincide con la falla actual almacenada.",
                origin="OBS/RELE",
            )

        with self._state_lock:
            self._last_fault_recognitions[relay_id] = timebox.monotonic()

    def _fault_recognition_due(self, relay_id: int) -> bool:
        with self._state_lock:
            last_recognition = self._last_fault_recognitions.get(relay_id)
        return (
            last_recognition is None
            or timebox.monotonic() - last_recognition
            >= self.FAULT_RECOGNITION_INTERVAL_SECONDS
        )

    def _refresh_latest_disturbance(
        self,
        relay_id: int,
        internal_id: int,
        fault: RegistroFalla,
        date_format: int,
    ) -> bool:
        with self._state_lock:
            cached = self._disturbances.get(relay_id)
            if self._disturbance_matches_fault(cached, fault):
                return True

        persisted = fallas_reles_dao.get_current_disturbance_for_rele(internal_id)
        if persisted is not None:
            with self._state_lock:
                self._disturbances[relay_id] = persisted
            if self._disturbance_matches_fault(persisted, fault):
                return True

        configuration = self._get_disturbance_configuration(relay_id)
        if configuration is None:
            with self._state_lock:
                errors = self._disturbance_configuration_errors.get(relay_id, {})
                message = (
                    "; ".join(errors.values())
                    or "La frecuencia nominal aun no fue leida del rele."
                )
            self._set_disturbance_error(relay_id, message)
            return False

        try:
            references = self.reader.read_disturbance_references(relay_id)
            reference = self._select_disturbance_reference(
                relay_id,
                references,
                fault,
                date_format,
                configuration,
            )
        except (MicomReadError, ValueError) as exc:
            self._set_disturbance_error(relay_id, str(exc))
            return False

        signature = reference.signature
        try:
            disturbance = self.reader.read_disturbance(
                relay_id,
                configuration,
                reference,
            )
            self._associate_disturbance_with_fault(
                disturbance,
                fault,
                date_format,
            )
            disturbance["signature"] = list(signature)
            if not fallas_reles_dao.save_current_disturbance(
                internal_id,
                fault.fault_number,
                disturbance,
            ):
                raise ValueError(
                    "La falla actual cambio antes de guardar la perturbacion"
                )
        except (MicomReadError, ValueError) as exc:
            self.driver.disconnect()
            self._set_disturbance_error(
                relay_id,
                str(exc),
                record_number=reference.record_number,
                signature=signature,
            )
            return False
        with self._state_lock:
            self._disturbances[relay_id] = disturbance
        return True

    @staticmethod
    def _disturbance_matches_fault(
        disturbance: dict | None,
        fault: RegistroFalla,
    ) -> bool:
        if not isinstance(disturbance, dict):
            return False
        metadata = disturbance.get("metadata")
        return (
            disturbance.get("status") == "available"
            and disturbance.get("fault_number") == fault.fault_number
            and isinstance(metadata, dict)
            and metadata.get("fault_timestamp")
            == timebox.utc_iso_milliseconds(fault.fault_datetime)
        )

    def _associate_disturbance_with_fault(
        self,
        disturbance: dict,
        fault: RegistroFalla,
        date_format: int,
    ) -> None:
        metadata = disturbance.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("La perturbacion no contiene metadatos validos")
        finish_words = metadata.get("finish_words")
        if (
            not isinstance(finish_words, list)
            or len(finish_words) != 4
            or any(not isinstance(word, int) for word in finish_words)
        ):
            raise ValueError("La perturbacion no contiene una estampa final valida")
        finish_datetime = self._decode_disturbance_finish(
            finish_words,
            date_format,
        )
        post_seconds = disturbance.get("post_seconds")
        sample_rate = disturbance.get("sample_rate_hz")
        if (
            not isinstance(post_seconds, (int, float))
            or not isinstance(sample_rate, (int, float))
            or post_seconds < 0
            or sample_rate <= 0
        ):
            raise ValueError("La perturbacion contiene una ventana temporal invalida")

        trigger_datetime = finish_datetime - timedelta(
            seconds=float(post_seconds)
        )
        signed_offset_seconds = (
            trigger_datetime - fault.fault_datetime
        ).total_seconds()
        offset_seconds = abs(signed_offset_seconds)
        precise_tolerance = max(
            self.DISTURBANCE_PRECISE_TOLERANCE_SECONDS,
            2.0 / float(sample_rate),
        )

        observations: list[str] = []
        if metadata.get("start_origin_code") not in {1, 2}:
            observations.append(
                "La perturbacion mas cercana no fue iniciada por disparo "
                "ni por un umbral instantaneo."
            )
        if offset_seconds > self.DISTURBANCE_ASSOCIATION_TOLERANCE_SECONDS:
            observations.append(
                "La perturbacion mas cercana no corresponde temporalmente "
                "a la falla actual: "
                f"diferencia={offset_seconds:.3f}s, tolerancia=+/-"
                f"{self.DISTURBANCE_ASSOCIATION_TOLERANCE_SECONDS:.3f}s. "
                "Se muestra por ser la mejor disponible."
            )
        elif offset_seconds > precise_tolerance:
            observations.append(
                "La perturbacion mas cercana difiere de la falla actual: "
                f"diferencia={offset_seconds:.3f}s; se encuentra dentro de "
                "la tolerancia de +/-"
                f"{self.DISTURBANCE_ASSOCIATION_TOLERANCE_SECONDS:.3f}s."
            )

        disturbance["fault_number"] = fault.fault_number
        disturbance["association_warning"] = " ".join(observations) or None
        metadata["finish_timestamp"] = timebox.utc_iso_milliseconds(
            finish_datetime
        )
        metadata["trigger_timestamp"] = timebox.utc_iso_milliseconds(
            trigger_datetime
        )
        metadata["fault_timestamp"] = timebox.utc_iso_milliseconds(
            fault.fault_datetime
        )
        metadata["fault_offset_ms"] = round(offset_seconds * 1000, 3)
        metadata["fault_signed_offset_ms"] = round(
            signed_offset_seconds * 1000,
            3,
        )
        metadata["association_tolerance_seconds"] = (
            self.DISTURBANCE_ASSOCIATION_TOLERANCE_SECONDS
        )
        metadata["association_within_tolerance"] = (
            offset_seconds <= self.DISTURBANCE_ASSOCIATION_TOLERANCE_SECONDS
        )

    def _select_disturbance_reference(
        self,
        relay_id: int,
        references: list[MicomDisturbanceReference],
        fault: RegistroFalla,
        date_format: int,
        configuration: MicomDisturbanceConfiguration,
    ) -> MicomDisturbanceReference:
        scored: list[tuple[float, MicomDisturbanceReference]] = []
        errors: list[str] = []
        for reference in references:
            finish_datetime = self._decode_disturbance_finish(
                list(reference.finish_words),
                date_format,
            )
            try:
                _, post_samples = self.reader.read_disturbance_timing(
                    relay_id,
                    reference,
                )
            except (MicomReadError, ValueError) as exc:
                errors.append(str(exc))
                continue
            trigger_datetime = finish_datetime - timedelta(
                seconds=post_samples / configuration.sample_rate_hz
            )
            scored.append(
                (
                    abs(
                        (
                            trigger_datetime - fault.fault_datetime
                        ).total_seconds()
                    ),
                    reference,
                )
            )
        if not scored:
            detail = "; ".join(errors) or "sin cabeceras temporales validas"
            raise ValueError(
                "No se pudo comparar ninguna perturbacion almacenada con "
                f"la falla {fault.fault_number}: {detail}"
            )
        return min(scored, key=lambda candidate: candidate[0])[1]

    def _decode_disturbance_finish(
        self,
        finish_words: list[int],
        date_format: int,
    ) -> datetime:
        if len(finish_words) != 4:
            raise ValueError(
                "La fecha de perturbacion requiere cuatro palabras"
            )
        if date_format == RegistroFalla.DATE_FORMAT_PRIVATE:
            seconds_since_epoch = (
                finish_words[1] << 16
            ) | finish_words[0]
            milliseconds = (finish_words[3] << 16) | finish_words[2]
            if milliseconds > 999:
                raise ValueError(
                    "Milisegundos privados de perturbacion fuera de rango: "
                    f"{milliseconds}"
                )
            return RegistroFalla.PRIVATE_EPOCH + timedelta(
                seconds=seconds_since_epoch,
                milliseconds=milliseconds,
            )
        if date_format == RegistroFalla.DATE_FORMAT_IEC_870:
            return MicomRelayClock.from_words(
                finish_words,
                date_format,
            ).timestamp
        raise ValueError(f"Formato de fecha MiCOM desconocido: {date_format}")

    def _get_current_profile(self, relay_id: int) -> MicomCurrentProfile | None:
        with self._state_lock:
            cached = self._current_profiles.get(relay_id)
            if relay_id in self._current_profiles_refreshed:
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
            return cached

        try:
            profile = MicomCurrentProfile.from_parts(
                cast(MicomCurrentIdentity, parts["identidad"]),
                cast(MicomCurrentTransformers, parts["transformadores"]),
            )
        except ValueError as exc:
            with self._state_lock:
                errors["validacion"] = str(exc)
            return cached
        identity = cast(MicomCurrentIdentity, parts["identidad"])
        transformers = cast(MicomCurrentTransformers, parts["transformadores"])
        reles_dao.save_current_profile(
            relay_id,
            product=identity.product,
            phase_primary_ct=transformers.phase_primary_ct,
            phase_secondary_ct=transformers.phase_secondary_ct,
            earth_primary_ct=transformers.earth_primary_ct,
            earth_secondary_ct=transformers.earth_secondary_ct,
            phase_internal_ratio=identity.phase_internal_ratio,
            earth_internal_ratio=identity.earth_internal_ratio,
        )
        with self._state_lock:
            self._current_profiles[relay_id] = profile
            self._current_profiles_refreshed.add(relay_id)
            self._current_profile_errors.pop(relay_id, None)
        self.logger.log(
            f"Escala del rele {relay_id} cargada para la sesion del observador.",
            origin="OBS/RELE",
        )
        return profile

    def _get_date_format(self, relay_id: int) -> int | None:
        with self._state_lock:
            cached = self._date_formats.get(relay_id)
            if relay_id in self._date_formats_refreshed:
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
            return cached
        reles_dao.save_date_format(relay_id, date_format)
        with self._state_lock:
            self._date_formats[relay_id] = date_format
            self._date_formats_refreshed.add(relay_id)
            self._date_format_errors.pop(relay_id, None)
        return date_format

    def _get_disturbance_configuration(
        self,
        relay_id: int,
    ) -> MicomDisturbanceConfiguration | None:
        with self._state_lock:
            cached = self._disturbance_configurations.get(relay_id)
            if relay_id in self._disturbance_configurations_refreshed:
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
            return cached
        configuration = MicomDisturbanceConfiguration(
            nominal_frequency_hz=parts["frecuencia"],
        )
        reles_dao.save_nominal_frequency(
            relay_id,
            configuration.nominal_frequency_hz,
        )
        with self._state_lock:
            self._disturbance_configurations[relay_id] = configuration
            self._disturbance_configurations_refreshed.add(relay_id)
            self._disturbance_configuration_errors.pop(relay_id, None)
        return configuration

    def _start_observer_session(self) -> None:
        with self._state_lock:
            self._current_profiles_refreshed.clear()
            self._current_profile_parts.clear()
            self._current_profile_errors.clear()
            self._date_formats_refreshed.clear()
            self._date_format_errors.clear()
            self._disturbance_configurations_refreshed.clear()
            self._disturbance_configuration_parts.clear()
            self._disturbance_configuration_errors.clear()
            self._recent_queries.clear()
            self._pending_disturbance_page_queries.clear()
            self._last_fault_signatures.clear()
            self._last_fault_recognitions.clear()
            self._pending_disturbance_faults.clear()
            self._last_catalog_refresh = None
            self._next_poll_datetime = None
            self._poll_in_progress = False
        self.logger.log(
            "Nueva sesion de observacion: se cargaran una vez los parametros MiCOM.",
            origin="OBS/RELE",
        )

    def get_current_calculation_snapshot(self, relay_id: int) -> dict:
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

    def read_clock_on_demand(self, relay_id: int) -> dict:
        with self._state_lock:
            date_format = self._date_formats.get(relay_id)
        if date_format is None:
            raise RuntimeError(
                f"El rele {relay_id} no tiene un formato de fecha previamente leido"
            )

        clock = self.reader.read_relay_clock(relay_id, date_format)
        metadata = reles_dao.get_relay_metadata(relay_id)
        if metadata is None:
            raise RuntimeError(f"No existe el rele Modbus {relay_id}")
        return {
            "id_modbus": relay_id,
            "description": metadata["descripcion"],
            "product": metadata["producto"],
            "timestamp": timebox.utc_iso_milliseconds(clock.timestamp),
            "timestamp_format": clock.timestamp_format,
            "milliseconds_raw": clock.milliseconds_raw,
            "nominal_frequency_hz": metadata["frecuencia_nominal"],
            "current_calculation": self.get_current_calculation_snapshot(relay_id),
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

    def _next_modbus_query_delay(self) -> float:
        now = timebox.monotonic()
        with self._state_lock:
            if not self.relay_unit_ids:
                return float(self.refresh_interval)
            if self._pending_disturbance_faults:
                return float(self.refresh_interval)
            for relay_id in self.relay_unit_ids:
                if (
                    relay_id not in self._current_profiles_refreshed
                    or relay_id not in self._date_formats_refreshed
                    or relay_id not in self._disturbance_configurations_refreshed
                    or relay_id not in self._last_fault_recognitions
                ):
                    return float(self.refresh_interval)
            remaining = [
                max(
                    0.0,
                    self.FAULT_RECOGNITION_INTERVAL_SECONDS
                    - (now - self._last_fault_recognitions.get(relay_id, 0.0)),
                )
                for relay_id in self.relay_unit_ids
            ]
        return min(remaining, default=float(self.refresh_interval))

    def _modbus_query_due(self) -> bool:
        now = timebox.monotonic()
        with self._state_lock:
            if self._pending_disturbance_faults:
                return True
            for relay_id in self.relay_unit_ids:
                if (
                    relay_id not in self._current_profiles_refreshed
                    or relay_id not in self._date_formats_refreshed
                    or relay_id not in self._disturbance_configurations_refreshed
                ):
                    return True
                last_recognition = self._last_fault_recognitions.get(relay_id)
                if (
                    last_recognition is None
                    or now - last_recognition
                    >= self.FAULT_RECOGNITION_INTERVAL_SECONDS
                ):
                    return True
        return False

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
        with self._state_lock:
            snapshot = self._disturbances.get(relay_id)
            if snapshot is not None and snapshot.get("status") == "available":
                return deepcopy(snapshot)

        internal_id = reles_dao.get_internal_id_by_modbus_id(relay_id)
        if internal_id is None:
            raise RuntimeError(
                f"El rele Modbus {relay_id} no tiene ID interno en el catalogo"
            )
        persisted = fallas_reles_dao.get_current_disturbance_for_rele(internal_id)
        if persisted is not None:
            with self._state_lock:
                self._disturbances[relay_id] = persisted
            return deepcopy(persisted)

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
