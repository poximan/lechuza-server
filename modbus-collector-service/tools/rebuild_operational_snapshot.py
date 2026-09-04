from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from src.persistencia.ddl_esquema import SCHEMA_SQL, SCHEMA_VERSION  # noqa: E402


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table});").fetchall()
    }


def _require_columns(
    connection: sqlite3.Connection,
    table: str,
    required: set[str],
) -> set[str]:
    found = _columns(connection, table)
    missing = required - found
    if missing:
        raise RuntimeError(
            f"La base de origen no cumple {table}: faltan {sorted(missing)}"
        )
    return found


def _parse_utc(value: object) -> datetime:
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Estampa UTC invalida en origen: {raw!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"Estampa sin zona UTC en origen: {raw!r}")
    return parsed.astimezone(timezone.utc)


def _utc_seconds(value: object) -> str:
    return _parse_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_milliseconds(value: object) -> str:
    parsed = _parse_utc(value)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond // 1000:03d}Z"


def _copy_grd(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    _require_columns(source, "grd", {"id", "descripcion", "activo"})
    target.executemany(
        "INSERT INTO grd (id, descripcion, activo) VALUES (?, ?, ?);",
        source.execute("SELECT id, descripcion, activo FROM grd ORDER BY id;"),
    )


def _history_rows(source: sqlite3.Connection) -> Iterable[tuple[int, str, int]]:
    cursor = source.execute(
        "SELECT id_grd, timestamp, conectado FROM historicos "
        "ORDER BY id_grd, timestamp;"
    )
    for row in cursor:
        yield int(row["id_grd"]), _utc_seconds(row["timestamp"]), int(row["conectado"])


def _copy_history(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    _require_columns(source, "historicos", {"id_grd", "timestamp", "conectado"})
    target.executemany(
        "INSERT INTO historicos (id_grd, timestamp, conectado) VALUES (?, ?, ?);",
        _history_rows(source),
    )
    target.execute(
        """
        INSERT INTO grd_estado_actual (id_grd, timestamp, conectado)
        SELECT h.id_grd, h.timestamp, h.conectado
        FROM historicos h
        JOIN (
            SELECT id_grd, MAX(timestamp) AS timestamp
            FROM historicos
            GROUP BY id_grd
        ) latest USING (id_grd, timestamp);
        """
    )


RELAY_METADATA_COLUMNS = (
    "producto",
    "formato_fecha",
    "fase_tc_primario",
    "fase_tc_secundario",
    "tierra_tc_primario",
    "tierra_tc_secundario",
    "fase_relacion_interna",
    "tierra_relacion_interna",
    "frecuencia_nominal",
)


def _copy_relays(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    found = _require_columns(source, "reles", {"id", "id_modbus", "descripcion"})
    available_metadata = [name for name in RELAY_METADATA_COLUMNS if name in found]
    selected = ["id", "id_modbus", "descripcion", *available_metadata]
    placeholders = ",".join("?" for _ in selected)
    target.executemany(
        f"INSERT INTO reles ({','.join(selected)}) VALUES ({placeholders});",
        source.execute(f"SELECT {','.join(selected)} FROM reles ORDER BY id;"),
    )


def _latest_fault_rows(
    source: sqlite3.Connection,
    legacy_fault_time_format: str | None,
) -> list[tuple]:
    found = _require_columns(
        source,
        "fallas_reles",
        {
            "id_rele",
            "numero_falla",
            "timestamp",
            "fasea_corr",
            "faseb_corr",
            "fasec_corr",
            "tierra_corr",
        },
    )
    if "formato_timestamp" not in found and legacy_fault_time_format is None:
        raise RuntimeError(
            "La base legada no informa formato_timestamp; indique "
            "--legacy-fault-time-format private o iec870"
        )
    optional = [
        name
        for name in (
            "formato_timestamp",
            "perturbacion_registro",
            "perturbacion_json",
        )
        if name in found
    ]
    selected = [
        "id_rele",
        "numero_falla",
        "timestamp",
        "fasea_corr",
        "faseb_corr",
        "fasec_corr",
        "tierra_corr",
        *optional,
    ]
    latest: dict[int, tuple[datetime, int, sqlite3.Row]] = {}
    for row in source.execute(f"SELECT {','.join(selected)} FROM fallas_reles;"):
        instant = _parse_utc(row["timestamp"])
        relay_id = int(row["id_rele"])
        fault_number = int(row["numero_falla"])
        candidate = (instant, fault_number, row)
        current = latest.get(relay_id)
        if current is None or candidate[:2] > current[:2]:
            latest[relay_id] = candidate

    result = []
    for relay_id in sorted(latest):
        _, _, row = latest[relay_id]
        timestamp_format = (
            str(row["formato_timestamp"])
            if "formato_timestamp" in found
            else legacy_fault_time_format
        )
        if timestamp_format not in {"private", "iec870"}:
            raise ValueError(
                f"Formato de falla invalido para rele interno {relay_id}: "
                f"{timestamp_format!r}"
            )
        disturbance_record = (
            row["perturbacion_registro"]
            if "perturbacion_registro" in found
            else None
        )
        disturbance_json = (
            row["perturbacion_json"] if "perturbacion_json" in found else None
        )
        if (disturbance_record is None) != (disturbance_json is None):
            raise ValueError(f"Perturbacion incompleta para rele interno {relay_id}")
        if disturbance_json is not None:
            payload = json.loads(str(disturbance_json))
            if not isinstance(payload, dict):
                raise ValueError(f"Perturbacion invalida para rele interno {relay_id}")
        result.append(
            (
                relay_id,
                int(row["numero_falla"]),
                _utc_milliseconds(row["timestamp"]),
                timestamp_format,
                row["fasea_corr"],
                row["faseb_corr"],
                row["fasec_corr"],
                row["tierra_corr"],
                disturbance_record,
                disturbance_json,
            )
        )
    return result


def _copy_latest_faults(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    legacy_fault_time_format: str | None,
) -> None:
    target.executemany(
        """
        INSERT INTO fallas_reles (
            id_rele, numero_falla, timestamp, formato_timestamp,
            fasea_corr, faseb_corr, fasec_corr, tierra_corr,
            perturbacion_registro, perturbacion_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        _latest_fault_rows(source, legacy_fault_time_format),
    )


def _count(connection: sqlite3.Connection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError(f"La consulta de control no devolvio filas: {query}")
    return int(row[0])


def _validate_preserved_scope(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
) -> None:
    comparisons = (
        (
            "catalogo GRD",
            _count(source, "SELECT COUNT(*) FROM grd;"),
            _count(target, "SELECT COUNT(*) FROM grd;"),
        ),
        (
            "historicos GRD",
            _count(source, "SELECT COUNT(*) FROM historicos;"),
            _count(target, "SELECT COUNT(*) FROM historicos;"),
        ),
        (
            "catalogo MiCOM",
            _count(source, "SELECT COUNT(*) FROM reles;"),
            _count(target, "SELECT COUNT(*) FROM reles;"),
        ),
        (
            "ultima falla MiCOM",
            _count(source, "SELECT COUNT(DISTINCT id_rele) FROM fallas_reles;"),
            _count(target, "SELECT COUNT(*) FROM fallas_reles;"),
        ),
        (
            "estado GRD reconstruido",
            _count(source, "SELECT COUNT(DISTINCT id_grd) FROM historicos;"),
            _count(target, "SELECT COUNT(*) FROM grd_estado_actual;"),
        ),
    )
    mismatches = [
        f"{label}: origen={source_count}, destino={target_count}"
        for label, source_count, target_count in comparisons
        if source_count != target_count
    ]
    if mismatches:
        raise RuntimeError(
            "La reconstruccion no preservo el alcance contratado: "
            + "; ".join(mismatches)
        )


def rebuild(
    source_path: Path,
    target_path: Path,
    *,
    legacy_fault_time_format: str | None = None,
) -> None:
    source_file = source_path.resolve(strict=True)
    target_file = target_path.resolve()
    if source_file == target_file:
        raise ValueError("Origen y destino deben ser archivos distintos")
    target_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target_file, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(descriptor)

    source = sqlite3.connect(f"file:{source_file}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(target_file)
    try:
        target.executescript(SCHEMA_SQL)
        target.execute("BEGIN IMMEDIATE;")
        _copy_grd(source, target)
        _copy_history(source, target)
        _copy_relays(source, target)
        _copy_latest_faults(source, target, legacy_fault_time_format)
        target.commit()
        _validate_preserved_scope(source, target)
        integrity = target.execute("PRAGMA integrity_check;").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError(f"SQLite integrity_check fallo: {integrity}")
        foreign_keys = target.execute("PRAGMA foreign_key_check;").fetchall()
        if foreign_keys:
            raise RuntimeError(
                f"La reconstruccion contiene {len(foreign_keys)} claves invalidas"
            )
        version = int(target.execute("PRAGMA user_version;").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise RuntimeError(f"Version inesperada luego de reconstruir: {version}")
    except Exception:
        target.close()
        source.close()
        os.remove(target_file)
        raise
    target.close()
    source.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Crea una base nueva y conserva catalogo/historia GRD y el ultimo "
            "registro MiCOM por rele."
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--legacy-fault-time-format",
        choices=("private", "iec870"),
        help="Obligatorio si el origen no guarda formato_timestamp.",
    )
    arguments = parser.parse_args()
    rebuild(
        arguments.source,
        arguments.target,
        legacy_fault_time_format=arguments.legacy_fault_time_format,
    )
    print(f"Snapshot operativo creado: {arguments.target.resolve()}")


if __name__ == "__main__":
    main()
