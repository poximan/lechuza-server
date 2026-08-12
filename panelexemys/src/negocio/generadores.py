from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _record(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} debe ser un objeto")
    return value


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} debe ser texto no vacio")
    return value


@dataclass(frozen=True)
class InterruptorGenerador:
    bit: int | None
    estado: str

    @classmethod
    def from_source(cls, source: Any, context: str) -> "InterruptorGenerador":
        item = _record(source, context)
        bit = item.get("bit")
        estado = _text(item.get("estado"), f"{context}.estado").lower()
        if bit is None and estado in {"incierto", "desconocido"}:
            return cls(bit=None, estado=estado)
        if type(bit) is not int or bit not in {0, 1}:
            raise ValueError(f"{context}.bit debe ser 0, 1 o null")
        expected = "cerrado" if bit == 1 else "abierto"
        if estado != expected:
            raise ValueError(f"{context} no coincide entre bit y estado")
        return cls(bit=bit, estado=estado)

    def contract(self) -> dict[str, Any]:
        return {"bit": self.bit, "estado": self.estado}


def build_generator_contract(source: Any, context: str) -> dict[str, Any]:
    item = _record(source, context)
    line = InterruptorGenerador.from_source(
        item.get("interruptor_linea"),
        f"{context}.interruptor_linea",
    )
    group = InterruptorGenerador.from_source(
        item.get("interruptor_grupo"),
        f"{context}.interruptor_grupo",
    )
    alarm = (
        line.bit is not None
        and group.bit is not None
        and line.bit == group.bit
    )
    if alarm and line.bit == 1:
        summary = "Alarma: red externa y GE cerrados sobre la barra"
    elif alarm:
        summary = "Alarma: barra sin alimentación"
    elif group.bit is None:
        summary = f"Red externa {line.estado}; lado grupo incierto"
    elif line.bit == 1 and group.bit == 0:
        summary = "Carga alimentada desde red externa"
    else:
        summary = "Carga alimentada desde grupo electrógeno"

    contract = {
        "interruptor_linea": line.contract(),
        "interruptor_grupo": group.contract(),
        "alarm": alarm,
        "summary": summary,
    }
    error = item.get("error")
    if error is not None:
        contract["error"] = _text(error, f"{context}.error")
    return contract
