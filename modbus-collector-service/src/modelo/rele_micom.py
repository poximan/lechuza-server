from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


def signed_word(value: int) -> int:
    """Interpreta una palabra Modbus como entero de 16 bits con signo."""
    word = int(value)
    if word < 0 or word > 0xFFFF:
        raise ValueError(f"Palabra Modbus fuera de rango: {word}")
    return word - 0x10000 if word & 0x8000 else word


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
                * sqrt(2)
            )
        if kind == "earth":
            return (
                sample
                * self.earth_primary_ct
                / self.earth_internal_ratio
                * sqrt(2)
            )
        raise ValueError(f"Tipo de canal de perturbacion desconocido: {kind}")
