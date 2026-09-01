from __future__ import annotations

from collections.abc import Callable

from logosaurio import Logosaurio

from src.modelo.registro_falla import RegistroFalla
from src.modelo.rele_micom import (
    MicomCurrentIdentity,
    MicomCurrentTransformers,
    MicomDisturbanceConfiguration,
    MicomDisturbanceReference,
    MicomDisturbanceScale,
    signed_word,
)
from src.utils import timebox

from .modbus_driver import ModbusTcpReadOnlyDriver


class MicomReadError(RuntimeError):
    pass


class MicomRelayReader:
    """Adapta el mapa MiCOM usando exclusivamente lecturas Modbus 03."""

    FAULT_ADDRESS = 0x3700
    FAULT_WORDS = 15
    FAULT_RECORD_COUNT = 25
    DISTURBANCE_INDEX_ADDRESS = 0x2200
    DISTURBANCE_AVAILABLE_ADDRESS = 0x3D00
    DISTURBANCE_PAGE_FIRST = 0x09
    DISTURBANCE_SAMPLES_PER_PAGE = 250
    DISTURBANCE_SAMPLES_PER_SELECTOR = 6250
    CHANNELS = (
        ("phase_a", 0, "phase"),
        ("phase_b", 1, "phase"),
        ("phase_c", 2, "phase"),
        ("earth", 3, "earth"),
    )
    READ_ATTEMPTS = 2

    START_ORIGINS = {
        1: "disparo RL1",
        2: "arranque instantaneo",
        3: "arranque remoto",
        4: "entrada logica",
    }

    def __init__(
        self,
        driver: ModbusTcpReadOnlyDriver,
        logger: Logosaurio,
        query_observer: Callable[[dict], None] | None = None,
    ):
        self.driver = driver
        self.logger = logger
        self.query_observer = query_observer

    def _read(self, relay_id: int, address: int, count: int) -> list[int]:
        last_error = "lectura no disponible"
        for attempt in range(self.READ_ATTEMPTS):
            started = timebox.monotonic()
            registers = self.driver.read_holding_registers(address, count, relay_id)
            if registers is None:
                status = "sin_respuesta"
                received_count = None
                last_error = "lectura no disponible"
            elif len(registers) != count:
                status = "cantidad_invalida"
                received_count = len(registers)
                last_error = (
                    f"se esperaban {count} palabras y llegaron {len(registers)}"
                )
            else:
                try:
                    values = [int(value) for value in registers]
                except (TypeError, ValueError):
                    status = "datos_invalidos"
                    received_count = len(registers)
                    last_error = "datos invalidos"
                else:
                    self._report_query(
                        relay_id,
                        address,
                        count,
                        "ok",
                        started,
                        received_count=len(values),
                    )
                    return values

            self._report_query(
                relay_id,
                address,
                count,
                status,
                started,
                received_count=received_count,
            )
            self.driver.disconnect()
            if attempt + 1 == self.READ_ATTEMPTS:
                break

        raise MicomReadError(
            f"Rele {relay_id}: {last_error} en {hex(address)} ({count} palabras)"
        )

    def _report_query(
        self,
        relay_id: int,
        address: int,
        count: int,
        status: str,
        started: float,
        *,
        received_count: int | None,
    ) -> None:
        if self.query_observer is None:
            return
        self.query_observer(
            {
                "relay_id": relay_id,
                "address": f"0x{address:04X}",
                "count": count,
                "received_count": received_count,
                "status": status,
                "timestamp": timebox.utc_iso(),
                "duration_ms": round(
                    max(0.0, timebox.monotonic() - started) * 1000,
                    1,
                ),
            }
        )

    @staticmethod
    def _decode_product(words: list[int]) -> str:
        raw = bytearray()
        for word in words:
            raw.extend(((word >> 8) & 0xFF, word & 0xFF))
        return raw.decode("ascii", errors="replace").strip(" \x00")

    def read_current_identity(self, relay_id: int) -> MicomCurrentIdentity:
        identity = self._read(relay_id, 0x0000, 9)
        return MicomCurrentIdentity(
            product=self._decode_product(identity[:3]),
            phase_internal_ratio=identity[7],
            earth_internal_ratio=identity[8],
        )

    def read_current_transformers(
        self,
        relay_id: int,
    ) -> MicomCurrentTransformers:
        transformers = self._read(relay_id, 0x0120, 4)
        return MicomCurrentTransformers(
            phase_primary_ct=transformers[0],
            phase_secondary_ct=transformers[1],
            earth_primary_ct=transformers[2],
            earth_secondary_ct=transformers[3],
        )

    def read_date_format(self, relay_id: int) -> int:
        return self._read(relay_id, 0x0135, 1)[0]

    def read_nominal_frequency(self, relay_id: int) -> int:
        frequency = self._read(relay_id, 0x0104, 1)[0]
        if frequency not in {50, 60}:
            raise MicomReadError(
                f"Rele {relay_id}: frecuencia nominal no soportada: {frequency}"
            )
        return frequency

    def read_latest_fault(
        self,
        relay_id: int,
        date_format: int,
    ) -> RegistroFalla:
        candidates: list[tuple[int, int, list[int]]] = []
        for offset in range(self.FAULT_RECORD_COUNT):
            address = self.FAULT_ADDRESS + offset
            words = self._read(relay_id, address, self.FAULT_WORDS)
            candidates.append((words[0], address, words))

        _, _, words = max(candidates, key=lambda candidate: candidate[0])
        return RegistroFalla(
            words,
            date_format,
            self.logger,
        )

    def read_latest_disturbance_reference(
        self,
        relay_id: int,
    ) -> MicomDisturbanceReference:
        directory = self._read(
            relay_id,
            self.DISTURBANCE_AVAILABLE_ADDRESS,
            36,
        )
        available = directory[0]
        if available == 0:
            raise MicomReadError(f"Rele {relay_id}: no hay perturbaciones almacenadas")
        if available < 0 or available > 5:
            raise MicomReadError(
                f"Rele {relay_id}: cantidad de perturbaciones invalida: {available}"
            )

        references: list[MicomDisturbanceReference] = []
        for index in range(available):
            offset = 1 + index * 7
            record = directory[offset : offset + 7]
            acknowledged = record[6]
            if acknowledged not in {0, 1}:
                raise MicomReadError(
                    f"Rele {relay_id}: reconocimiento de perturbacion invalido: "
                    f"{acknowledged}"
                )
            try:
                reference = MicomDisturbanceReference(
                    record_number=record[0],
                    finish_words=tuple(record[1:5]),
                    start_origin_code=record[5],
                    acknowledged=bool(acknowledged),
                )
            except ValueError as exc:
                raise MicomReadError(f"Rele {relay_id}: {exc}") from exc
            references.append(reference)

        if len({reference.record_number for reference in references}) != available:
            raise MicomReadError(
                f"Rele {relay_id}: el directorio repite numeros de perturbacion"
            )
        unused_words = directory[1 + available * 7 :]
        if any(unused_words):
            raise MicomReadError(
                f"Rele {relay_id}: el directorio contiene reservas no nulas"
            )

        # El manual ordena el directorio desde el registro mas antiguo.
        return references[-1]

    def read_disturbance(
        self,
        relay_id: int,
        configuration: MicomDisturbanceConfiguration,
        reference: MicomDisturbanceReference,
    ) -> dict:
        (
            phase_a_samples,
            phase_a_header,
            pre_samples,
            post_samples,
            index,
        ) = self._read_channel(
            relay_id,
            reference.record_number,
            0,
        )
        metadata = self._parse_disturbance_index(index)
        self._validate_disturbance_reference(relay_id, reference, metadata)
        pre_seconds = pre_samples / configuration.sample_rate_hz
        post_seconds = post_samples / configuration.sample_rate_hz

        channels: dict[str, list[float]] = {}
        for name, channel_id, kind in self.CHANNELS:
            if channel_id == 0:
                raw_samples = phase_a_samples
                header = phase_a_header
                channel_pre_samples = pre_samples
                channel_post_samples = post_samples
            else:
                (
                    raw_samples,
                    header,
                    channel_pre_samples,
                    channel_post_samples,
                    index,
                ) = self._read_channel(
                    relay_id,
                    reference.record_number,
                    channel_id,
                )
                channel_metadata = self._parse_disturbance_index(index)
                self._validate_disturbance_reference(
                    relay_id,
                    reference,
                    channel_metadata,
                )
                if channel_metadata != metadata:
                    raise MicomReadError(
                        f"Rele {relay_id}: el indice cambio al leer el canal {name}"
                    )
            if (
                channel_pre_samples != pre_samples
                or channel_post_samples != post_samples
            ):
                raise MicomReadError(
                    f"Rele {relay_id}: la ventana del canal {name} no coincide"
                )
            scale = MicomDisturbanceScale.from_header(header)
            channels[name] = [
                round(scale.scale(sample, kind), 4) for sample in raw_samples
            ]

        metadata["acknowledged"] = reference.acknowledged
        return {
            "status": "available",
            "message": None,
            "record_number": reference.record_number,
            "pre_seconds": pre_seconds,
            "post_seconds": post_seconds,
            "sample_rate_hz": configuration.sample_rate_hz,
            "unit": "A",
            "metadata": metadata,
            "channels": channels,
        }

    def _validate_disturbance_reference(
        self,
        relay_id: int,
        reference: MicomDisturbanceReference,
        metadata: dict,
    ) -> None:
        index_signature = (
            metadata["record_number"],
            *metadata["finish_words"],
            metadata["start_origin_code"],
        )
        if index_signature != reference.signature:
            raise MicomReadError(
                f"Rele {relay_id}: el indice no coincide con el directorio"
            )

    def _select_channel(
        self,
        relay_id: int,
        slot: int,
        chunk: int,
        channel_id: int,
    ) -> list[int]:
        if slot < 1 or slot > 5:
            raise MicomReadError(
                f"Rele {relay_id}: posicion de perturbacion invalida: {slot}"
            )
        if chunk < 0 or chunk > 4:
            raise MicomReadError(
                f"Rele {relay_id}: bloque de perturbacion invalido: {chunk}"
            )
        if channel_id < 0 or channel_id > 5:
            raise MicomReadError(
                f"Rele {relay_id}: canal de perturbacion invalido: {channel_id}"
            )
        selector = ((0x38 + slot - 1) << 8) | (chunk << 4) | channel_id
        return self._read(relay_id, selector, 11)

    def _read_channel(
        self,
        relay_id: int,
        slot: int,
        channel_id: int,
    ) -> tuple[list[int], list[int], int, int, list[int]]:
        samples: list[int] = []
        first_header: list[int] | None = None
        pre_samples = 0
        post_samples = 0
        selected_index: list[int] | None = None
        for chunk in range(5):
            header = self._select_channel(relay_id, slot, chunk, channel_id)
            if first_header is None:
                first_header = header
            elif header[3:9] != first_header[3:9]:
                raise MicomReadError(
                    f"Rele {relay_id}: la escala del canal cambio entre bloques"
                )
            sample_count = header[0]
            if sample_count < 1 or sample_count > self.DISTURBANCE_SAMPLES_PER_SELECTOR:
                raise MicomReadError(
                    f"Rele {relay_id}: cantidad invalida de muestras en selector: {sample_count}"
                )
            if sample_count != header[1] + header[2]:
                raise MicomReadError(
                    f"Rele {relay_id}: la cabecera no concilia muestras totales, "
                    "pretiempo y post-tiempo"
                )
            mapping_samples = self._read_selected_samples(
                relay_id,
                header[9],
                header[10],
            )
            if len(mapping_samples) != sample_count:
                raise MicomReadError(
                    f"Rele {relay_id}: el mapa contiene {len(mapping_samples)} "
                    f"muestras y la cabecera informa {sample_count}"
                )
            samples.extend(mapping_samples)
            pre_samples += header[1]
            post_samples += header[2]
            chunk_index = self._read(
                relay_id,
                self.DISTURBANCE_INDEX_ADDRESS,
                7,
            )
            if selected_index is None:
                selected_index = chunk_index
            elif chunk_index != selected_index:
                raise MicomReadError(
                    f"Rele {relay_id}: el indice cambio entre bloques del canal"
                )
            if sample_count < self.DISTURBANCE_SAMPLES_PER_SELECTOR:
                break
        else:
            raise MicomReadError(
                f"Rele {relay_id}: el canal excede los cinco bloques documentados"
            )
        if first_header is None:
            raise MicomReadError(f"Rele {relay_id}: canal de perturbacion vacio")
        if len(samples) < 2:
            raise MicomReadError(
                f"Rele {relay_id}: el canal no contiene suficientes muestras"
            )
        if len(samples) != pre_samples + post_samples:
            raise MicomReadError(
                f"Rele {relay_id}: el canal no concilia su ventana temporal"
            )
        if selected_index is None:
            raise MicomReadError(f"Rele {relay_id}: indice de perturbacion ausente")
        return samples, first_header, pre_samples, post_samples, selected_index

    def _read_selected_samples(
        self,
        relay_id: int,
        last_page: int,
        last_page_count: int,
    ) -> list[int]:
        if last_page < self.DISTURBANCE_PAGE_FIRST or last_page > 0x21:
            raise MicomReadError(
                f"Rele {relay_id}: ultima pagina de perturbacion invalida: "
                f"{hex(last_page)}"
            )
        if last_page_count < 1 or last_page_count > self.DISTURBANCE_SAMPLES_PER_PAGE:
            raise MicomReadError(
                f"Rele {relay_id}: palabras invalidas en la ultima pagina: "
                f"{last_page_count}"
            )
        result: list[int] = []
        for page in range(self.DISTURBANCE_PAGE_FIRST, last_page + 1):
            page_count = (
                last_page_count
                if page == last_page
                else self.DISTURBANCE_SAMPLES_PER_PAGE
            )
            first_count = min(page_count, 125)
            values = self._read(relay_id, page << 8, first_count)
            if page_count > first_count:
                values.extend(
                    self._read(relay_id, (page << 8) + first_count, page_count - first_count)
                )
            result.extend(signed_word(value) for value in values)
        return result

    def _parse_disturbance_index(
        self,
        words: list[int],
    ) -> dict:
        if len(words) != 7:
            raise MicomReadError("El indice de perturbacion requiere siete palabras")
        origin = words[5]
        if origin not in self.START_ORIGINS:
            raise MicomReadError(
                f"Origen de perturbacion MiCOM desconocido: {origin}"
            )
        return {
            "record_number": words[0],
            "finish_words": words[1:5],
            "start_origin_code": origin,
            "start_origin": self.START_ORIGINS[origin],
            "post_time_frequency_raw": words[6],
        }
