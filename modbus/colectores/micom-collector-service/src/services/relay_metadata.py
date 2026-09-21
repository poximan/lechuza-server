import threading
from typing import cast

from src.modelo.rele_micom import (
    MicomCurrentIdentity, MicomCurrentProfile, MicomCurrentTransformers,
    MicomDisturbanceConfiguration,
)
from src.persistencia.dao.dao_reles import reles_dao
from src.modbus.micom_relay_reader import MicomReadError
from src.utils import timebox


class RelayMetadataService:
    """Carga parametros MiCOM y expone su contrato de escala y reloj."""

    def __init__(self, reader, logger):
        self.reader = reader
        self.logger = logger
        self._state_lock = threading.RLock()
        self._current_profiles = {}
        self._current_profile_parts = {}
        self._current_profile_errors = {}
        self._date_formats = {}
        self._date_format_errors = {}
        self._disturbance_configurations = {}
        self._disturbance_configuration_parts = {}
        self._disturbance_configuration_errors = {}
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

    def get_current_profile(self, relay_id: int) -> MicomCurrentProfile | None:
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
            self._current_profile_errors.pop(relay_id, None)
        self.logger.log(
            f"Escala del rele {relay_id} cargada y persistida.",
            origin="OBS/RELE",
        )
        return profile

    def get_date_format(self, relay_id: int) -> int | None:
        with self._state_lock:
            cached = self._date_formats.get(relay_id)
            if cached is not None:
                return cached
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
            self._date_format_errors.pop(relay_id, None)
        return date_format

    def get_disturbance_configuration(
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
            self._disturbance_configuration_errors.pop(relay_id, None)
        return configuration

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

    def reset_session(self) -> None:
        with self._state_lock:
            self._current_profile_parts.clear()
            self._current_profile_errors.clear()
            self._date_format_errors.clear()
            self._disturbance_configuration_parts.clear()
            self._disturbance_configuration_errors.clear()

    def session_error(self, relay_id: int) -> str:
        with self._state_lock:
            errors = [
                *self._current_profile_errors.get(relay_id, {}).values(),
                *(
                    [self._date_format_errors[relay_id]]
                    if relay_id in self._date_format_errors
                    else []
                ),
                *self._disturbance_configuration_errors.get(
                    relay_id,
                    {},
                ).values(),
            ]
        return "; ".join(dict.fromkeys(errors)) or (
            "Los parametros MiCOM aun no fueron leidos ni persistidos"
        )
