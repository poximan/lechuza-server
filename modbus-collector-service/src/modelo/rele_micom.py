from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def signed_word(value: int) -> int:
    """Interpreta una palabra Modbus como entero de 16 bits con signo."""
    word = int(value)
    if word < 0 or word > 0xFFFF:
        raise ValueError(f"Palabra Modbus fuera de rango: {word}")
    return word - 0x10000 if word & 0x8000 else word


@dataclass(frozen=True)
class MicomRelayClock:
    timestamp: datetime
    timestamp_format: str
    milliseconds_raw: int

    @classmethod
    def from_words(cls, words: list[int], date_format: int) -> "MicomRelayClock":
        if len(words) != 4 or any(word < 0 or word > 0xFFFF for word in words):
            raise ValueError("La hora MiCOM requiere cuatro palabras de 16 bits")
        if date_format == 0:
            year = words[0]
            if year < 1994 or year > 2093:
                raise ValueError(f"Anio privado MiCOM fuera de rango: {year}")
            month = (words[1] >> 8) & 0xFF
            day = words[1] & 0xFF
            hour = (words[2] >> 8) & 0xFF
            minute = words[2] & 0xFF
            timestamp_format = "private"
        elif date_format == 1:
            year_value = words[0] & 0x7F
            if year_value > 99:
                raise ValueError(
                    f"Anio IEC MiCOM fuera de rango: {year_value}"
                )
            year = 1900 + year_value if year_value >= 94 else 2000 + year_value
            month = (words[1] >> 8) & 0x0F
            day = words[1] & 0x1F
            hour = (words[2] >> 8) & 0x1F
            minute = words[2] & 0x3F
            timestamp_format = "iec870"
        else:
            raise ValueError(f"Formato de fecha MiCOM desconocido: {date_format}")

        milliseconds_raw = words[3]
        if not 0 <= milliseconds_raw <= 59999:
            raise ValueError(
                f"Milisegundos dentro del minuto fuera de rango: {milliseconds_raw}"
            )
        second, millisecond = divmod(milliseconds_raw, 1000)
        try:
            timestamp = datetime(
                year,
                month,
                day,
                hour,
                minute,
                second,
                millisecond * 1000,
                tzinfo=timezone.utc,
            )
        except ValueError as exc:
            raise ValueError(
                "Componentes invalidos en la hora MiCOM: "
                f"{year:04d}-{month:02d}-{day:02d} "
                f"{hour:02d}:{minute:02d}:{second:02d}.{millisecond:03d}"
            ) from exc
        return cls(
            timestamp=timestamp,
            timestamp_format=timestamp_format,
            milliseconds_raw=milliseconds_raw,
        )


@dataclass(frozen=True)
class MicomCurrentIdentity:
    product: str
    phase_internal_ratio: int
    earth_internal_ratio: int


@dataclass(frozen=True)
class MicomCurrentTransformers:
    phase_primary_ct: int
    phase_secondary_ct: int
    earth_primary_ct: int
    earth_secondary_ct: int


@dataclass(frozen=True)
class MicomCurrentProfile:
    phase_primary_ct: int
    earth_primary_ct: int
    phase_internal_ratio: int
    earth_internal_ratio: int

    @classmethod
    def from_parts(
        cls,
        identity: MicomCurrentIdentity,
        transformers: MicomCurrentTransformers,
    ) -> "MicomCurrentProfile":
        return cls(
            phase_primary_ct=transformers.phase_primary_ct,
            earth_primary_ct=transformers.earth_primary_ct,
            phase_internal_ratio=identity.phase_internal_ratio,
            earth_internal_ratio=identity.earth_internal_ratio,
        )

    def __post_init__(self) -> None:
        positive_fields = {
            "TC primario de fase": self.phase_primary_ct,
            "TC primario de tierra": self.earth_primary_ct,
            "relacion interna de fase": self.phase_internal_ratio,
            "relacion interna de tierra": self.earth_internal_ratio,
        }
        for name, value in positive_fields.items():
            if value <= 0:
                raise ValueError(f"{name} invalida: {value}")

    def calculation_contract(self) -> dict:
        return {
            "status": "available",
            "phase_primary_ct": self.phase_primary_ct,
            "phase_internal_ratio": self.phase_internal_ratio,
            "earth_primary_ct": self.earth_primary_ct,
            "earth_internal_ratio": self.earth_internal_ratio,
        }


@dataclass(frozen=True)
class MicomDisturbanceConfiguration:
    nominal_frequency_hz: int

    @property
    def sample_rate_hz(self) -> int:
        if self.nominal_frequency_hz not in {50, 60}:
            raise ValueError(
                f"Frecuencia nominal no soportada: {self.nominal_frequency_hz}"
            )
        return self.nominal_frequency_hz * 32


@dataclass(frozen=True)
class MicomDisturbanceReference:
    record_number: int
    finish_words: tuple[int, int, int, int]
    start_origin_code: int
    acknowledged: bool

    def __post_init__(self) -> None:
        if self.record_number < 1 or self.record_number > 5:
            raise ValueError(
                f"Numero de perturbacion MiCOM invalido: {self.record_number}"
            )
        if len(self.finish_words) != 4 or any(
            word < 0 or word > 0xFFFF for word in self.finish_words
        ):
            raise ValueError("Fecha cruda de perturbacion MiCOM invalida")
        if self.start_origin_code not in {1, 2, 3, 4}:
            raise ValueError(
                f"Origen de perturbacion MiCOM invalido: {self.start_origin_code}"
            )

    @property
    def signature(self) -> tuple[int, int, int, int, int, int]:
        return (
            self.record_number,
            *self.finish_words,
            self.start_origin_code,
        )


@dataclass(frozen=True)
class MicomDisturbanceScale:
    phase_primary_ct: int
    earth_primary_ct: int
    phase_internal_ratio: int
    earth_internal_ratio: int

    def __post_init__(self) -> None:
        if min(
            self.phase_primary_ct,
            self.earth_primary_ct,
            self.phase_internal_ratio,
            self.earth_internal_ratio,
        ) <= 0:
            raise ValueError("La perturbacion informa relaciones de TC invalidas")

    @classmethod
    def from_header(cls, header: list[int]) -> "MicomDisturbanceScale":
        if len(header) < 9:
            raise ValueError("La cabecera de perturbacion requiere nueve palabras")
        return cls(
            phase_primary_ct=header[3],
            earth_primary_ct=header[5],
            phase_internal_ratio=header[7],
            earth_internal_ratio=header[8],
        )

    def scale(self, sample: int, kind: str) -> float:
        if kind == "phase":
            return (
                sample
                * self.phase_primary_ct
                / self.phase_internal_ratio
                * 2
            )
        if kind == "earth":
            return (
                sample
                * self.earth_primary_ct
                / self.earth_internal_ratio
                * 2
            )
        raise ValueError(f"Tipo de canal de perturbacion desconocido: {kind}")
