from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PHONE_GROUPS = ("fontana", "estivariz", "general")


def _record(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} debe ser un objeto")
    return value


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} debe ser texto no vacio")
    return value


@dataclass(frozen=True)
class TelefonoMantenimiento:
    numero: str
    comentario: str | None

    @classmethod
    def from_source(cls, source: Any, context: str) -> "TelefonoMantenimiento":
        item = _record(source, context)
        comentario = item.get("comentario")
        if comentario is not None:
            comentario = _text(comentario, f"{context}.comentario")
        return cls(
            numero=_text(item.get("numero"), f"{context}.numero"),
            comentario=comentario,
        )


@dataclass(frozen=True)
class MapeoPuertoMantenimiento:
    servicio: str
    interno: str
    externo_path: str
    localhost: str

    @classmethod
    def from_source(cls, source: Any, context: str) -> "MapeoPuertoMantenimiento":
        item = _record(source, context)
        externo_path = _text(item.get("externo_path"), f"{context}.externo_path")
        if not externo_path.startswith("/"):
            raise ValueError(f"{context}.externo_path debe comenzar con /")
        return cls(
            servicio=_text(item.get("servicio"), f"{context}.servicio"),
            interno=_text(item.get("interno"), f"{context}.interno"),
            externo_path=externo_path,
            localhost=_text(item.get("localhost"), f"{context}.localhost"),
        )


@dataclass(frozen=True)
class CatalogoMantenimiento:
    telefonos: dict[str, tuple[TelefonoMantenimiento, ...]]
    port_mappings: tuple[MapeoPuertoMantenimiento, ...]

    @classmethod
    def from_source(cls, source: dict[str, Any]) -> "CatalogoMantenimiento":
        phones_source = _record(source.get("telefonos"), "mantenimiento.telefonos")
        if set(phones_source) != set(PHONE_GROUPS):
            raise ValueError(
                "mantenimiento.telefonos debe declarar fontana, estivariz y general"
            )
        telefonos: dict[str, tuple[TelefonoMantenimiento, ...]] = {}
        for group in PHONE_GROUPS:
            entries = phones_source[group]
            if not isinstance(entries, list):
                raise ValueError(f"mantenimiento.telefonos.{group} debe ser una lista")
            telefonos[group] = tuple(
                TelefonoMantenimiento.from_source(
                    item,
                    f"mantenimiento.telefonos.{group}[{index}]",
                )
                for index, item in enumerate(entries)
            )

        mappings_source = source.get("port_mappings")
        if not isinstance(mappings_source, list):
            raise ValueError("mantenimiento.port_mappings debe ser una lista")
        mappings = tuple(
            MapeoPuertoMantenimiento.from_source(
                item,
                f"mantenimiento.port_mappings[{index}]",
            )
            for index, item in enumerate(mappings_source)
        )
        return cls(telefonos=telefonos, port_mappings=mappings)
