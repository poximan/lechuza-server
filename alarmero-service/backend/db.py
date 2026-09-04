from __future__ import annotations

import json
import math
import os
import sqlite3
import statistics
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from timeauthority import get_time_authority

from . import config


SCHEMA_VERSION = 1
_LOCK = threading.RLock()
_TIME = get_time_authority()

SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE alarm_catalog (
    source_id TEXT NOT NULL,
    alarm_key TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    activation_seconds INTEGER NOT NULL CHECK (activation_seconds >= 0),
    recovery_seconds INTEGER NOT NULL CHECK (recovery_seconds >= 0),
    expected_clearance_minutes INTEGER NOT NULL CHECK (expected_clearance_minutes >= 0),
    send_start INTEGER NOT NULL DEFAULT 1 CHECK (send_start IN (0, 1)),
    send_end INTEGER NOT NULL DEFAULT 0 CHECK (send_end IN (0, 1)),
    catalog_active INTEGER NOT NULL DEFAULT 1 CHECK (catalog_active IN (0, 1)),
    current_condition INTEGER CHECK (current_condition IN (0, 1)),
    condition_since_at TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (source_id, alarm_key)
) WITHOUT ROWID;

CREATE TABLE alarm_state (
    source_id TEXT NOT NULL,
    alarm_key TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL CHECK (
        lifecycle_state IN ('inactive', 'pending_start', 'active', 'pending_end')
    ),
    condition_active INTEGER NOT NULL CHECK (condition_active IN (0, 1)),
    condition_since_at TEXT NOT NULL,
    incident_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source_id, alarm_key),
    FOREIGN KEY (source_id, alarm_key)
        REFERENCES alarm_catalog(source_id, alarm_key)
) WITHOUT ROWID;

CREATE TABLE incidents (
    incident_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    alarm_key TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('potential', 'active', 'recovering', 'resolved')
    ),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    notified INTEGER NOT NULL CHECK (notified IN (0, 1)),
    expected_clearance_minutes INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    qualified_at TEXT,
    notified_at TEXT,
    recovery_started_at TEXT,
    resolved_at TEXT,
    last_event_type TEXT NOT NULL,
    FOREIGN KEY (source_id, alarm_key)
        REFERENCES alarm_catalog(source_id, alarm_key)
);

CREATE TABLE lifecycle_events (
    lifecycle_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    source_event_id INTEGER,
    incident_id TEXT,
    alarm_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (source_id, source_event_id)
);

CREATE TABLE dispatches (
    dispatch_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('start', 'end')),
    recipients TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'processing', 'sent', 'failed')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accepted_at TEXT,
    last_error TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id),
    UNIQUE (incident_id, phase)
);

CREATE TABLE source_cursors (
    source_id TEXT PRIMARY KEY,
    cursor_value INTEGER NOT NULL CHECK (cursor_value >= 0),
    updated_at TEXT NOT NULL
) WITHOUT ROWID;

CREATE INDEX idx_incidents_status_seen
ON incidents(status, first_seen_at DESC);

CREATE INDEX idx_dispatches_delivery
ON dispatches(accepted_at, created_at);

PRAGMA user_version = {SCHEMA_VERSION};
COMMIT;
"""

EXPECTED_COLUMNS = {
    "alarm_catalog": {
        "source_id", "alarm_key", "title", "category", "activation_seconds",
        "recovery_seconds", "expected_clearance_minutes", "send_start",
        "send_end", "catalog_active", "current_condition",
        "condition_since_at", "subject", "body",
    },
    "alarm_state": {
        "source_id", "alarm_key", "lifecycle_state", "condition_active",
        "condition_since_at", "incident_id", "updated_at",
    },
    "incidents": {
        "incident_id", "source_id", "alarm_key", "title", "category", "status",
        "active", "notified", "expected_clearance_minutes", "first_seen_at",
        "last_seen_at", "qualified_at", "notified_at", "recovery_started_at",
        "resolved_at", "last_event_type",
    },
    "lifecycle_events": {
        "lifecycle_event_id", "source_id", "source_event_id", "incident_id",
        "alarm_key", "event_type", "occurred_at", "payload",
    },
    "dispatches": {
        "dispatch_id", "incident_id", "phase", "recipients", "subject", "body",
        "status", "created_at", "updated_at", "accepted_at", "last_error",
    },
    "source_cursors": {
        "source_id", "cursor_value", "updated_at",
    },
}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(
        config.DATABASE_PATH,
        timeout=10,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA busy_timeout = 10000;")
    return connection


def init_db() -> None:
    config.DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    target = os.path.abspath(config.DATABASE_PATH)
    if not os.path.exists(target):
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(target)
            connection.executescript(SCHEMA_SQL)
            connection.close()
        except Exception:
            if connection is not None:
                connection.close()
            if os.path.exists(target):
                os.remove(target)
            raise
    validate_schema()


def validate_schema() -> None:
    expected_tables = {
        "alarm_catalog",
        "alarm_state",
        "incidents",
        "lifecycle_events",
        "dispatches",
        "source_cursors",
    }
    with _LOCK, _connect() as connection:
        version = int(connection.execute("PRAGMA user_version;").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise RuntimeError(
                f"Esquema Alarmero invalido: esperado={SCHEMA_VERSION}, encontrado={version}"
            )
        found = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%';"
            ).fetchall()
        }
        if found != expected_tables:
            raise RuntimeError(
                f"Tablas Alarmero invalidas: esperadas={sorted(expected_tables)}, "
                f"encontradas={sorted(found)}"
            )
        for table, expected_columns in EXPECTED_COLUMNS.items():
            columns = {
                str(row[1])
                for row in connection.execute(
                    f"PRAGMA table_info({table});"
                ).fetchall()
            }
            if columns != expected_columns:
                raise RuntimeError(
                    f"Columnas Alarmero invalidas en {table}: "
                    f"esperadas={sorted(expected_columns)}, "
                    f"encontradas={sorted(columns)}"
                )
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check;").fetchall()
        if foreign_key_errors:
            raise RuntimeError(
                f"Alarmero contiene {len(foreign_key_errors)} claves foraneas invalidas"
            )


def get_source_cursor(source_id: str) -> int:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT cursor_value FROM source_cursors WHERE source_id = ?;",
            (source_id,),
        ).fetchone()
        return int(row["cursor_value"]) if row else 0


def reconcile_configured_sources(source_ids: set[str]) -> None:
    if not source_ids:
        raise ValueError("La lista de fuentes configuradas no puede estar vacia")
    placeholders = ",".join("?" for _ in source_ids)
    with _LOCK, _connect() as connection:
        connection.execute(
            f"UPDATE alarm_catalog SET catalog_active = 0 "
            f"WHERE source_id NOT IN ({placeholders});",
            tuple(sorted(source_ids)),
        )


def ingest_catalog(source_id: str, alarms: list[dict[str, Any]]) -> None:
    with _LOCK, _connect() as connection:
        connection.execute("BEGIN IMMEDIATE;")
        connection.execute(
            "UPDATE alarm_catalog SET catalog_active = 0 WHERE source_id = ?;",
            (source_id,),
        )
        for alarm in alarms:
            parsed = _parse_catalog_alarm(alarm)
            connection.execute(
                """
                INSERT INTO alarm_catalog (
                    source_id, alarm_key, title, category, activation_seconds,
                    recovery_seconds, expected_clearance_minutes, send_start,
                    send_end, catalog_active, current_condition,
                    condition_since_at, subject, body
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 1, ?, ?, ?, ?)
                ON CONFLICT(source_id, alarm_key) DO UPDATE SET
                    title = excluded.title,
                    category = excluded.category,
                    activation_seconds = excluded.activation_seconds,
                    recovery_seconds = excluded.recovery_seconds,
                    expected_clearance_minutes = excluded.expected_clearance_minutes,
                    catalog_active = 1,
                    current_condition = excluded.current_condition,
                    condition_since_at = excluded.condition_since_at,
                    subject = excluded.subject,
                    body = excluded.body;
                """,
                (
                    source_id,
                    parsed["alarm_key"],
                    parsed["title"],
                    parsed["category"],
                    parsed["activation_seconds"],
                    parsed["recovery_seconds"],
                    parsed["expected_clearance_minutes"],
                    parsed["condition_active"],
                    parsed["condition_since_at"],
                    parsed["subject"],
                    parsed["body"],
                ),
            )
            if parsed["condition_active"] is not None:
                existing = connection.execute(
                    "SELECT 1 FROM alarm_state WHERE source_id = ? AND alarm_key = ?;",
                    (source_id, parsed["alarm_key"]),
                ).fetchone()
                if existing is None:
                    _apply_condition(
                        connection,
                        source_id,
                        parsed["alarm_key"],
                        bool(parsed["condition_active"]),
                        str(parsed["condition_since_at"]),
                        source_event_id=None,
                        payload={"origin": "catalog_baseline"},
                    )
        connection.commit()


def ingest_events(source_id: str, events: list[dict[str, Any]]) -> int:
    with _LOCK, _connect() as connection:
        connection.execute("BEGIN IMMEDIATE;")
        cursor_row = connection.execute(
            "SELECT cursor_value FROM source_cursors WHERE source_id = ?;",
            (source_id,),
        ).fetchone()
        cursor = int(cursor_row["cursor_value"]) if cursor_row else 0
        for raw_event in events:
            event = _parse_source_event(raw_event)
            event_id = event["event_id"]
            if event_id <= cursor:
                continue
            if event_id != cursor + 1:
                raise ValueError(
                    f"Secuencia incompleta de {source_id}: "
                    f"esperado={cursor + 1}, recibido={event_id}"
                )
            _apply_condition(
                connection,
                source_id,
                event["alarm_key"],
                event["condition_active"],
                event["occurred_at"],
                source_event_id=event_id,
                payload={
                    "subject": event["subject"],
                    "body": event["body"],
                },
            )
            connection.execute(
                """
                UPDATE alarm_catalog
                SET current_condition = ?, condition_since_at = ?, subject = ?, body = ?
                WHERE source_id = ? AND alarm_key = ?;
                """,
                (
                    int(event["condition_active"]),
                    event["occurred_at"],
                    event["subject"],
                    event["body"],
                    source_id,
                    event["alarm_key"],
                ),
            )
            cursor = event_id
        connection.execute(
            """
            INSERT INTO source_cursors (source_id, cursor_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                cursor_value = excluded.cursor_value,
                updated_at = excluded.updated_at;
            """,
            (source_id, cursor, _TIME.utc_iso()),
        )
        connection.commit()
        return cursor


def process_due_transitions(now_iso: str, recipients: list[str]) -> None:
    now = _parse_instant(now_iso)
    with _LOCK, _connect() as connection:
        connection.execute("BEGIN IMMEDIATE;")
        rows = connection.execute(
            """
            SELECT s.*, c.title, c.category, c.activation_seconds,
                   c.recovery_seconds, c.expected_clearance_minutes,
                   c.send_start, c.send_end, c.subject, c.body
            FROM alarm_state s
            JOIN alarm_catalog c USING (source_id, alarm_key)
            WHERE c.catalog_active = 1
              AND s.lifecycle_state IN ('pending_start', 'pending_end');
            """
        ).fetchall()
        for row in rows:
            condition_since = _parse_instant(str(row["condition_since_at"]))
            elapsed = (now - condition_since).total_seconds()
            if row["lifecycle_state"] == "pending_start":
                if elapsed < int(row["activation_seconds"]):
                    continue
                qualified_at = _iso(
                    condition_since + timedelta(seconds=int(row["activation_seconds"]))
                )
                _activate_incident(connection, row, qualified_at, recipients)
            elif elapsed >= int(row["recovery_seconds"]):
                resolved_at = _iso(
                    condition_since + timedelta(seconds=int(row["recovery_seconds"]))
                )
                _resolve_incident(connection, row, resolved_at, recipients)
        connection.commit()


def pending_dispatches(limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM dispatches
            WHERE accepted_at IS NULL AND status = 'pending'
            ORDER BY created_at, dispatch_id
            LIMIT ?;
            """,
            (min(500, max(1, int(limit))),),
        ).fetchall()
        return [_dispatch_dict(row) for row in rows]


def mark_dispatch_accepted(dispatch_id: str, accepted_at: str) -> None:
    with _LOCK, _connect() as connection:
        connection.execute("BEGIN IMMEDIATE;")
        row = connection.execute(
            "SELECT incident_id, phase FROM dispatches WHERE dispatch_id = ?;",
            (dispatch_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Despacho desconocido: {dispatch_id}")
        connection.execute(
            """
            UPDATE dispatches
            SET accepted_at = ?, updated_at = ?, last_error = NULL
            WHERE dispatch_id = ?;
            """,
            (accepted_at, accepted_at, dispatch_id),
        )
        if row["phase"] == "start":
            connection.execute(
                """
                UPDATE incidents
                SET notified = 1, notified_at = COALESCE(notified_at, ?)
                WHERE incident_id = ?;
                """,
                (accepted_at, row["incident_id"]),
            )
        connection.commit()


def mark_dispatch_error(dispatch_id: str, message: str, updated_at: str) -> None:
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE dispatches
            SET updated_at = ?, last_error = ?
            WHERE dispatch_id = ? AND accepted_at IS NULL;
            """,
            (updated_at, message, dispatch_id),
        )


def ingest_dispatches(items: list[dict[str, Any]]) -> None:
    allowed = {"pending", "processing", "sent", "failed"}
    with _LOCK, _connect() as connection:
        connection.execute("BEGIN IMMEDIATE;")
        for item in items:
            dispatch_id = str(item.get("idempotency_key") or "")
            delivery_status = str(item.get("status") or "")
            if not dispatch_id or delivery_status not in allowed:
                continue
            connection.execute(
                """
                UPDATE dispatches
                SET status = ?, updated_at = ?, last_error = ?
                WHERE dispatch_id = ?;
                """,
                (
                    delivery_status,
                    str(item.get("updated_at") or _TIME.utc_iso()),
                    item.get("last_error"),
                    dispatch_id,
                ),
            )
        connection.commit()


def list_incidents(view_filter: str, limit: int) -> list[dict[str, Any]]:
    clauses = {
        "potential": "i.status = 'potential'",
        "active": "i.status IN ('active', 'recovering')",
        "all": "1 = 1",
    }
    if view_filter not in clauses:
        raise ValueError("Filtro invalido")
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT i.*, d.recipients, d.status AS dispatch_status,
                   d.updated_at AS dispatch_updated_at, d.last_error AS dispatch_error
            FROM incidents i
            LEFT JOIN dispatches d ON d.dispatch_id = i.incident_id || ':start'
            WHERE {clauses[view_filter]}
            ORDER BY i.first_seen_at DESC
            LIMIT ?;
            """,
            (min(5000, max(1, int(limit))),),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["recipients"] = (
                json.loads(item["recipients"]) if item["recipients"] else []
            )
            result.append(item)
        return result


def list_catalog() -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT source_id, alarm_key, title, category, activation_seconds,
                   recovery_seconds, send_start, send_end, current_condition,
                   condition_since_at
            FROM alarm_catalog
            WHERE catalog_active = 1
            ORDER BY source_id, category, title;
            """
        ).fetchall()
        return [dict(row) for row in rows]


def update_notification_settings(
    source_id: str,
    alarm_key: str,
    send_start: bool,
    send_end: bool,
) -> None:
    with _LOCK, _connect() as connection:
        result = connection.execute(
            """
            UPDATE alarm_catalog
            SET send_start = ?, send_end = ?
            WHERE source_id = ? AND alarm_key = ? AND catalog_active = 1;
            """,
            (int(send_start), int(send_end), source_id, alarm_key),
        )
        if result.rowcount != 1:
            raise KeyError(f"Alarma desconocida: {source_id}/{alarm_key}")


def dashboard() -> dict[str, Any]:
    now = _TIME.utc_now()
    boundaries = {
        "daily": now - timedelta(days=1),
        "weekly": now - timedelta(days=7),
        "monthly": now - timedelta(days=30),
        "annual": now - timedelta(days=365),
    }
    with _LOCK, _connect() as connection:
        count_rows = connection.execute(
            "SELECT status, COUNT(*) AS total FROM incidents GROUP BY status;"
        ).fetchall()
        condition_row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN current_condition = 1 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN current_condition = 0 THEN 1 ELSE 0 END) AS inactive,
                SUM(CASE WHEN current_condition IS NULL THEN 1 ELSE 0 END) AS unknown
            FROM alarm_catalog
            WHERE catalog_active = 1;
            """
        ).fetchone()
        frequency_rows = connection.execute(
            """
            SELECT c.source_id, c.alarm_key, c.title, c.category,
                   COUNT(i.incident_id) AS total,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS daily,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS weekly,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS monthly,
                   SUM(CASE WHEN i.qualified_at >= ? THEN 1 ELSE 0 END) AS annual
            FROM alarm_catalog c
            LEFT JOIN incidents i
              ON i.source_id = c.source_id
             AND i.alarm_key = c.alarm_key
             AND i.qualified_at IS NOT NULL
            WHERE c.catalog_active = 1
            GROUP BY c.source_id, c.alarm_key, c.title, c.category
            ORDER BY total DESC, c.source_id, c.alarm_key;
            """,
            tuple(_iso(boundaries[key]) for key in ("daily", "weekly", "monthly", "annual")),
        ).fetchall()
        lifetime_rows = connection.execute(
            """
            SELECT c.source_id, c.alarm_key, c.title, c.category,
                   c.expected_clearance_minutes,
                   i.qualified_at, i.resolved_at
            FROM alarm_catalog c
            LEFT JOIN incidents i
              ON i.source_id = c.source_id
             AND i.alarm_key = c.alarm_key
             AND i.qualified_at IS NOT NULL
            WHERE c.catalog_active = 1
            ORDER BY c.source_id, c.alarm_key, i.qualified_at;
            """
        ).fetchall()

    metrics: dict[tuple[str, str], dict[str, Any]] = {}
    for row in lifetime_rows:
        source_id = str(row["source_id"])
        alarm_key = str(row["alarm_key"])
        key = (source_id, alarm_key)
        entry = metrics.setdefault(
            key,
            {
                "source_id": source_id,
                "alarm_key": alarm_key,
                "title": str(row["title"]),
                "category": str(row["category"]),
                "configured_minutes": int(row["expected_clearance_minutes"]),
                "active_samples": [],
                "inactive_samples": [],
                "last_resolved_at": None,
            },
        )
        if row["qualified_at"] is None:
            continue
        last_resolved_at = entry["last_resolved_at"]
        if last_resolved_at is not None:
            entry["inactive_samples"].append(
                _minutes_between(str(last_resolved_at), str(row["qualified_at"]))
            )
        if row["resolved_at"] is not None:
            entry["active_samples"].append(
                _minutes_between(str(row["qualified_at"]), str(row["resolved_at"]))
            )
            entry["last_resolved_at"] = str(row["resolved_at"])
    lifetimes = []
    for entry in metrics.values():
        active_samples = sorted(entry.pop("active_samples"))
        inactive_samples = sorted(entry.pop("inactive_samples"))
        entry.pop("last_resolved_at")
        entry.update(_sample_metrics(active_samples, "active"))
        entry.update(_sample_metrics(inactive_samples, "inactive"))
        lifetimes.append(entry)
    lifetimes.sort(
        key=lambda item: (
            -item["active_sample_count"],
            item["source_id"],
            item["alarm_key"],
        )
    )
    counts = {str(row["status"]): int(row["total"]) for row in count_rows}
    return {
        "counts": {
            "potential": counts.get("potential", 0),
            "active": counts.get("active", 0),
            "recovering": counts.get("recovering", 0),
            "resolved": counts.get("resolved", 0),
        },
        "conditions": {
            "active": int(condition_row["active"] or 0),
            "inactive": int(condition_row["inactive"] or 0),
            "unknown": int(condition_row["unknown"] or 0),
        },
        "frequent": [dict(row) for row in frequency_rows],
        "clearance": lifetimes,
    }


def _sample_metrics(samples: list[float], prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_sample_count": len(samples),
        f"median_{prefix}_minutes": (
            round(statistics.median(samples), 1) if samples else None
        ),
        f"p90_{prefix}_minutes": (
            round(samples[max(0, math.ceil(len(samples) * 0.9) - 1)], 1)
            if samples
            else None
        ),
    }


def _apply_condition(
    connection: sqlite3.Connection,
    source_id: str,
    alarm_key: str,
    active: bool,
    occurred_at: str,
    *,
    source_event_id: int | None,
    payload: dict[str, Any],
) -> None:
    _parse_instant(occurred_at)
    catalog = connection.execute(
        "SELECT * FROM alarm_catalog "
        "WHERE source_id = ? AND alarm_key = ? AND catalog_active = 1;",
        (source_id, alarm_key),
    ).fetchone()
    if catalog is None:
        raise ValueError(f"Evento para alarma no catalogada: {source_id}/{alarm_key}")
    if source_event_id is not None:
        existing_event = connection.execute(
            "SELECT 1 FROM lifecycle_events WHERE source_id = ? AND source_event_id = ?;",
            (source_id, source_event_id),
        ).fetchone()
        if existing_event is not None:
            return

    state = connection.execute(
        "SELECT * FROM alarm_state WHERE source_id = ? AND alarm_key = ?;",
        (source_id, alarm_key),
    ).fetchone()
    if state is None:
        if active:
            incident_id = str(uuid.uuid4())
            _insert_potential_incident(
                connection,
                incident_id,
                source_id,
                alarm_key,
                catalog,
                occurred_at,
            )
            lifecycle_state = "pending_start"
        else:
            incident_id = None
            lifecycle_state = "inactive"
        connection.execute(
            """
            INSERT INTO alarm_state (
                source_id, alarm_key, lifecycle_state, condition_active,
                condition_since_at, incident_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                source_id,
                alarm_key,
                lifecycle_state,
                int(active),
                occurred_at,
                incident_id,
                occurred_at,
            ),
        )
        event_type = "condition_started" if active else "baseline_inactive"
    else:
        previous_active = bool(state["condition_active"])
        if previous_active == active:
            event_type = "condition_repeated"
        elif active and state["lifecycle_state"] == "inactive":
            incident_id = str(uuid.uuid4())
            _insert_potential_incident(
                connection,
                incident_id,
                source_id,
                alarm_key,
                catalog,
                occurred_at,
            )
            connection.execute(
                """
                UPDATE alarm_state
                SET lifecycle_state = 'pending_start', condition_active = 1,
                    condition_since_at = ?, incident_id = ?, updated_at = ?
                WHERE source_id = ? AND alarm_key = ?;
                """,
                (occurred_at, incident_id, occurred_at, source_id, alarm_key),
            )
            event_type = "condition_started"
        elif not active and state["lifecycle_state"] == "pending_start":
            incident_id = state["incident_id"]
            connection.execute(
                """
                UPDATE incidents
                SET status = 'resolved', active = 0, last_seen_at = ?,
                    resolved_at = ?, last_event_type = 'cancelled'
                WHERE incident_id = ?;
                """,
                (occurred_at, occurred_at, incident_id),
            )
            connection.execute(
                """
                UPDATE alarm_state
                SET lifecycle_state = 'inactive', condition_active = 0,
                    condition_since_at = ?, incident_id = NULL, updated_at = ?
                WHERE source_id = ? AND alarm_key = ?;
                """,
                (occurred_at, occurred_at, source_id, alarm_key),
            )
            event_type = "cancelled"
        elif not active and state["lifecycle_state"] == "active":
            incident_id = state["incident_id"]
            connection.execute(
                """
                UPDATE incidents
                SET status = 'recovering', last_seen_at = ?,
                    recovery_started_at = ?, last_event_type = 'recovering'
                WHERE incident_id = ?;
                """,
                (occurred_at, occurred_at, incident_id),
            )
            connection.execute(
                """
                UPDATE alarm_state
                SET lifecycle_state = 'pending_end', condition_active = 0,
                    condition_since_at = ?, updated_at = ?
                WHERE source_id = ? AND alarm_key = ?;
                """,
                (occurred_at, occurred_at, source_id, alarm_key),
            )
            event_type = "recovering"
        elif active and state["lifecycle_state"] == "pending_end":
            incident_id = state["incident_id"]
            connection.execute(
                """
                UPDATE incidents
                SET status = 'active', last_seen_at = ?, recovery_started_at = NULL,
                    last_event_type = 'active_again'
                WHERE incident_id = ?;
                """,
                (occurred_at, incident_id),
            )
            connection.execute(
                """
                UPDATE alarm_state
                SET lifecycle_state = 'active', condition_active = 1,
                    condition_since_at = ?, updated_at = ?
                WHERE source_id = ? AND alarm_key = ?;
                """,
                (occurred_at, occurred_at, source_id, alarm_key),
            )
            event_type = "active_again"
        else:
            raise RuntimeError(
                f"Transicion invalida para {source_id}/{alarm_key}: "
                f"{state['lifecycle_state']} -> {active}"
            )

    current = connection.execute(
        "SELECT incident_id FROM alarm_state WHERE source_id = ? AND alarm_key = ?;",
        (source_id, alarm_key),
    ).fetchone()
    _append_lifecycle(
        connection,
        source_id,
        source_event_id,
        current["incident_id"] if current else None,
        alarm_key,
        event_type,
        occurred_at,
        payload,
    )


def _activate_incident(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    now_iso: str,
    recipients: list[str],
) -> None:
    incident_id = str(row["incident_id"])
    connection.execute(
        """
        UPDATE incidents
        SET status = 'active', active = 1, last_seen_at = ?,
            qualified_at = ?, last_event_type = 'active'
        WHERE incident_id = ?;
        """,
        (now_iso, now_iso, incident_id),
    )
    connection.execute(
        """
        UPDATE alarm_state
        SET lifecycle_state = 'active', updated_at = ?
        WHERE source_id = ? AND alarm_key = ?;
        """,
        (now_iso, row["source_id"], row["alarm_key"]),
    )
    _append_lifecycle(
        connection,
        str(row["source_id"]),
        None,
        incident_id,
        str(row["alarm_key"]),
        "active",
        now_iso,
        {},
    )
    if bool(row["send_start"]):
        _queue_dispatch(
            connection,
            incident_id,
            "start",
            recipients,
            str(row["subject"]),
            str(row["body"]),
            now_iso,
        )


def _resolve_incident(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    now_iso: str,
    recipients: list[str],
) -> None:
    incident_id = str(row["incident_id"])
    connection.execute(
        """
        UPDATE incidents
        SET status = 'resolved', active = 0, last_seen_at = ?,
            resolved_at = ?, last_event_type = 'resolved'
        WHERE incident_id = ?;
        """,
        (now_iso, now_iso, incident_id),
    )
    connection.execute(
        """
        UPDATE alarm_state
        SET lifecycle_state = 'inactive', incident_id = NULL, updated_at = ?
        WHERE source_id = ? AND alarm_key = ?;
        """,
        (now_iso, row["source_id"], row["alarm_key"]),
    )
    _append_lifecycle(
        connection,
        str(row["source_id"]),
        None,
        incident_id,
        str(row["alarm_key"]),
        "resolved",
        now_iso,
        {},
    )
    if bool(row["send_end"]):
        _queue_dispatch(
            connection,
            incident_id,
            "end",
            recipients,
            f"FIN: {row['subject']}",
            f"La condicion de alarma finalizo.\n\n{row['body']}",
            now_iso,
        )


def _insert_potential_incident(
    connection: sqlite3.Connection,
    incident_id: str,
    source_id: str,
    alarm_key: str,
    catalog: sqlite3.Row,
    occurred_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO incidents (
            incident_id, source_id, alarm_key, title, category, status,
            active, notified, expected_clearance_minutes, first_seen_at,
            last_seen_at, last_event_type
        ) VALUES (?, ?, ?, ?, ?, 'potential', 1, 0, ?, ?, ?, 'potential');
        """,
        (
            incident_id,
            source_id,
            alarm_key,
            catalog["title"],
            catalog["category"],
            catalog["expected_clearance_minutes"],
            occurred_at,
            occurred_at,
        ),
    )


def _append_lifecycle(
    connection: sqlite3.Connection,
    source_id: str,
    source_event_id: int | None,
    incident_id: str | None,
    alarm_key: str,
    event_type: str,
    occurred_at: str,
    payload: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO lifecycle_events (
            source_id, source_event_id, incident_id, alarm_key,
            event_type, occurred_at, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            source_id,
            source_event_id,
            incident_id,
            alarm_key,
            event_type,
            occurred_at,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )


def _queue_dispatch(
    connection: sqlite3.Connection,
    incident_id: str,
    phase: str,
    recipients: list[str],
    subject: str,
    body: str,
    now_iso: str,
) -> None:
    dispatch_id = f"{incident_id}:{phase}"
    connection.execute(
        """
        INSERT OR IGNORE INTO dispatches (
            dispatch_id, incident_id, phase, recipients, subject, body,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?);
        """,
        (
            dispatch_id,
            incident_id,
            phase,
            json.dumps(recipients, ensure_ascii=False),
            f"{config.ALARM_SUBJECT_PREFIX}{subject}",
            body,
            now_iso,
            now_iso,
        ),
    )


def _parse_catalog_alarm(alarm: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(alarm, dict):
        raise ValueError("Entrada de catalogo invalida")
    result = {
        "alarm_key": _required_text(alarm, "alarm_key"),
        "title": _required_text(alarm, "title"),
        "category": _required_text(alarm, "category"),
        "activation_seconds": _non_negative_int(alarm, "activation_seconds"),
        "recovery_seconds": _non_negative_int(alarm, "recovery_seconds"),
        "expected_clearance_minutes": _non_negative_int(
            alarm, "expected_clearance_minutes"
        ),
        "condition_active": alarm.get("condition_active"),
        "condition_since_at": alarm.get("condition_since_at"),
        "subject": _required_text(alarm, "subject"),
        "body": str(alarm.get("body") or ""),
    }
    if result["condition_active"] not in {None, False, True}:
        raise ValueError("condition_active debe ser booleano o null")
    if result["condition_active"] is not None:
        if not isinstance(result["condition_since_at"], str):
            raise ValueError("Una condicion observada requiere condition_since_at")
        _parse_instant(result["condition_since_at"])
        if not result["body"].strip():
            raise ValueError("Una condicion observada requiere cuerpo")
    elif result["condition_since_at"] is not None:
        raise ValueError("condition_since_at requiere una condicion observada")
    return result


def _parse_source_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("Evento de fuente invalido")
    event_id = _non_negative_int(event, "event_id")
    if event_id < 1:
        raise ValueError("event_id debe ser mayor que cero")
    active = event.get("condition_active")
    if not isinstance(active, bool):
        raise ValueError("condition_active debe ser booleano")
    occurred_at = _required_text(event, "occurred_at")
    _parse_instant(occurred_at)
    return {
        "event_id": event_id,
        "alarm_key": _required_text(event, "alarm_key"),
        "condition_active": active,
        "occurred_at": occurred_at,
        "subject": _required_text(event, "subject"),
        "body": _required_text(event, "body"),
    }


def _required_text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} debe ser texto no vacio")
    return value.strip()


def _non_negative_int(record: dict[str, Any], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} debe ser entero no negativo")
    return value


def _parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"Timestamp fuera de UTC: {value}")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _minutes_between(start: str, end: str) -> float:
    return max(0.0, (_parse_instant(end) - _parse_instant(start)).total_seconds() / 60.0)


def _dispatch_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["recipients"] = json.loads(str(result["recipients"]))
    return result
