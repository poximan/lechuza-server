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
    MicomRelayClock,
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
    MODBUS_MAX_READ_WORDS = 125
    DISTURBANCE_INDEX_WORDS = 9
    DISTURBANCE_SAMPLES_PER_SELECTOR = 6250
    DISTURBANCE_SELECTOR_BLOCKS = 16
    CHANNELS = (
        ("phase_a", 0, "phase"),
        ("phase_b", 1, "phase"),
        ("phase_c", 2, "phase"),
        ("earth", 3, "earth"),
    )
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
        started = timebox.monotonic()
        registers = self.driver.read_holding_registers(address, count, relay_id)
        if registers is None:
            status = "sin_respuesta"
            received_count = None
            error = "lectura no disponible"
        elif len(registers) != count:
            status = "cantidad_invalida"
            received_count = len(registers)
            error = f"se esperaban {count} palabras y llegaron {len(registers)}"
        else:
            try:
                values = [int(value) for value in registers]
            except (TypeError, ValueError):
                status = "datos_invalidos"
                received_count = len(registers)
                error = "datos invalidos"
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

        raise MicomReadError(
            f"Rele {relay_id}: {error} en {hex(address)} ({count} palabras)"
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

    def read_relay_clock(self, relay_id: int, date_format: int) -> MicomRelayClock:
        return MicomRelayClock.from_words(
            self._read(relay_id, 0x0800, 4),
            date_format,
        )

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
        candidates: list[tuple[int, int]] = []
        for offset in range(self.FAULT_RECORD_COUNT):
            address = self.FAULT_ADDRESS + offset
            fault_number = self._read(relay_id, address, 1)[0]
            candidates.append((fault_number, address))

        _, latest_address = max(candidates, key=lambda candidate: candidate[0])
        words = self._read(relay_id, latest_address, self.FAULT_WORDS)
        return RegistroFalla(
            words,
            date_format,
            self.logger,
        )

    def read_disturbance_references(
        self,
        relay_id: int,
    ) -> list[MicomDisturbanceReference]:
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
        # El manual ordena el directorio desde el registro mas antiguo.
        return references

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

    def read_disturbance_timing(
        self,
        relay_id: int,
        reference: MicomDisturbanceReference,
    ) -> tuple[int, int]:
        headers = self._select_channel_headers(
            relay_id,
            reference.record_number,
            0,
        )
        pre_samples = sum(header[1] for header in headers)
        post_samples = sum(header[2] for header in headers)
        return pre_samples, post_samples

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
        channel_id: int,
        block_index: int,
    ) -> list[int]:
        if slot < 1 or slot > 5:
            raise MicomReadError(
                f"Rele {relay_id}: posicion de perturbacion invalida: {slot}"
            )
        if channel_id < 0 or channel_id > 5:
            raise MicomReadError(
                f"Rele {relay_id}: canal de perturbacion invalido: {channel_id}"
            )
        if block_index < 0 or block_index >= self.DISTURBANCE_SELECTOR_BLOCKS:
            raise MicomReadError(
                f"Rele {relay_id}: bloque de perturbacion invalido: {block_index}"
            )
        selector = (
            ((0x38 + slot - 1) << 8)
            | (block_index << 4)
            | channel_id
        )
        return self._read(relay_id, selector, 11)

    def _select_channel_headers(
        self,
        relay_id: int,
        slot: int,
        channel_id: int,
    ) -> list[list[int]]:
        headers: list[list[int]] = []
        scale_signature: tuple[int, ...] | None = None
        for block_index in range(self.DISTURBANCE_SELECTOR_BLOCKS):
            header = self._select_channel(
                relay_id,
                slot,
                channel_id,
                block_index,
            )
            scale_signature = self._validate_channel_header(
                relay_id,
                block_index,
                header,
                scale_signature,
            )
            headers.append(header)
            if header[0] < self.DISTURBANCE_SAMPLES_PER_SELECTOR:
                return headers
        raise MicomReadError(
            f"Rele {relay_id}: la perturbacion supera los "
            f"{self.DISTURBANCE_SELECTOR_BLOCKS} bloques soportados por el mapa"
        )

    def _validate_channel_header(
        self,
        relay_id: int,
        block_index: int,
        header: list[int],
        expected_scale_signature: tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        sample_count = header[0]
        if sample_count < 1 or sample_count > self.DISTURBANCE_SAMPLES_PER_SELECTOR:
            raise MicomReadError(
                f"Rele {relay_id}: cantidad invalida de muestras en el bloque "
                f"{block_index}: {sample_count}"
            )
        if sample_count != header[1] + header[2]:
            raise MicomReadError(
                f"Rele {relay_id}: el bloque {block_index} no concilia muestras "
                "totales, pretiempo y post-tiempo"
            )
        scale_signature = tuple(header[3:9])
        if (
            expected_scale_signature is not None
            and scale_signature != expected_scale_signature
        ):
            raise MicomReadError(
                f"Rele {relay_id}: la escala cambio entre bloques del canal"
            )
        return scale_signature

    def _read_channel(
        self,
        relay_id: int,
        slot: int,
        channel_id: int,
    ) -> tuple[list[int], list[int], int, int, list[int]]:
        headers: list[list[int]] = []
        samples: list[int] = []
        scale_signature: tuple[int, ...] | None = None
        for block_index in range(self.DISTURBANCE_SELECTOR_BLOCKS):
            header = self._select_channel(
                relay_id,
                slot,
                channel_id,
                block_index,
            )
            scale_signature = self._validate_channel_header(
                relay_id,
                block_index,
                header,
                scale_signature,
            )
            headers.append(header)
            block_samples = self._read_selected_samples(
                relay_id,
                header[9],
                header[10],
            )
            if len(block_samples) != header[0]:
                raise MicomReadError(
                    f"Rele {relay_id}: el bloque {block_index} contiene "
                    f"{len(block_samples)} muestras y la cabecera informa {header[0]}"
                )
            samples.extend(block_samples)
            if header[0] < self.DISTURBANCE_SAMPLES_PER_SELECTOR:
                break
        else:
            raise MicomReadError(
                f"Rele {relay_id}: la perturbacion supera los "
                f"{self.DISTURBANCE_SELECTOR_BLOCKS} bloques soportados por el mapa"
            )
        if len(samples) < 2:
            raise MicomReadError(
                f"Rele {relay_id}: el canal no contiene suficientes muestras"
            )
        selected_index = self._read(
            relay_id,
            self.DISTURBANCE_INDEX_ADDRESS,
            self.DISTURBANCE_INDEX_WORDS,
        )
        pre_samples = sum(header[1] for header in headers)
        post_samples = sum(header[2] for header in headers)
        return samples, headers[0], pre_samples, post_samples, selected_index

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
            valid_word_count = (
                last_page_count
                if page == last_page
                else self.DISTURBANCE_SAMPLES_PER_PAGE
            )
            page_address = page << 8
            values = self._read(
                relay_id,
                page_address,
                self.MODBUS_MAX_READ_WORDS,
            )
            values.extend(
                self._read(
                    relay_id,
                    page_address + self.MODBUS_MAX_READ_WORDS,
                    self.MODBUS_MAX_READ_WORDS,
                )
            )
            result.extend(
                signed_word(value) for value in values[:valid_word_count]
            )
        return result

    def _parse_disturbance_index(
        self,
        words: list[int],
    ) -> dict:
        if len(words) != self.DISTURBANCE_INDEX_WORDS:
            raise MicomReadError(
                "El indice de perturbacion requiere nueve palabras"
            )
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
            "index_extension_words_raw": words[7:9],
        }
