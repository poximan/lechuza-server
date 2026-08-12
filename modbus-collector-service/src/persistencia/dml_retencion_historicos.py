from __future__ import annotations

import argparse

from src.persistencia.dao.dao_base import get_db_connection
from src.persistencia.validador_esquema import validate_database_schema
from src.utils import timebox


DELETE_CANDIDATES_SQL = """
FROM historicos AS h
WHERE h.timestamp < ?
  AND h.timestamp < (
      SELECT MAX(anchor.timestamp)
      FROM historicos AS anchor
      WHERE anchor.id_grd = h.id_grd
        AND anchor.timestamp < ?
  )
"""


def prune_history(before: str, apply_changes: bool = False) -> int:
    """Elimina historia anterior al corte y conserva un ancla por GRD."""
    cutoff = timebox.utc_iso(timebox.parse(before))
    conn = get_db_connection()
    try:
        validate_database_schema(conn)
        conn.execute("BEGIN IMMEDIATE;" if apply_changes else "BEGIN;")
        count = int(
            conn.execute(
                f"SELECT COUNT(1) {DELETE_CANDIDATES_SQL}",
                (cutoff, cutoff),
            ).fetchone()[0]
        )
        if apply_changes and count:
            conn.execute(
                f"DELETE {DELETE_CANDIDATES_SQL}",
                (cutoff, cutoff),
            )
            conn.commit()
        else:
            conn.rollback()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica retencion historica con un corte UTC explicito."
    )
    parser.add_argument(
        "--before",
        required=True,
        help="Instante ISO-8601 UTC; por ejemplo 2024-01-01T00:00:00Z",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Confirma el borrado. Sin esta bandera solo informa la cantidad.",
    )
    args = parser.parse_args()
    count = prune_history(args.before, args.apply)
    action = "eliminadas" if args.apply else "candidatas"
    print(f"Filas {action}: {count}")


if __name__ == "__main__":
    main()
