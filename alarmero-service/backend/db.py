from __future__ import annotations

import json
import math
import sqlite3
import statistics
import threading
from datetime import datetime

from timeauthority import get_time_authority

from . import config


_LOCK = threading.RLock()
_AUTH = get_time_authority()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    config.DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id TEXT PRIMARY KEY,
                alarm_key TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                active INTEGER NOT NULL,
                notified INTEGER NOT NULL,
                expected_clearance_minutes INTEGER NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                qualified_at TEXT,
                notified_at TEXT,
                recovery_started_at TEXT,
                resolved_at TEXT,
                last_event_type TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_incidents_status_seen
            ON incidents(status, first_seen_at DESC);
            CREATE TABLE IF NOT EXISTS lifecycle_events (
                source_event_id INTEGER PRIMARY KEY,
                incident_id TEXT NOT NULL,
                alarm_key TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dispatches (
                incident_id TEXT PRIMARY KEY,
                recipients TEXT NOT NULL,
                subject TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS sync_state (
                source TEXT PRIMARY KEY,
                cursor_value INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def get_alarm_cursor() -> int:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT cursor_value FROM sync_state WHERE source = 'panelexemys';"
        ).fetchone()
        return int(row["cursor_value"]) if row else 0


def _event_status(event_type: str) -> tuple[str, int]:
    if event_type == "potential":
        return "potential", 1
    if event_type in {"active", "active_again", "notification_accepted"}:
        return "active", 1
    if event_type == "recovering":
        return "recovering", 1
    if event_type in {"resolved", "cancelled"}:
        return "resolved", 0
    raise ValueError(f"Evento de alarma desconocido: {event_type}")


def ingest_alarm_snapshot(snapshot: dict) -> None:
    incidents = snapshot.get("incidents")
    events = snapshot.get("events")
    if not isinstance(incidents, list) or not isinstance(events, list):
        raise ValueError("Contrato invalido de panelexemys")

    with _LOCK, _connect() as conn:
        for event in events:
            event_id = int(event["event_id"])
            incident_id = str(event["incident_id"])
            alarm_key = str(event["alarm_key"])
            event_type = str(event["event_type"])
            occurred_at = str(event["occurred_at"])
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            status, active = _event_status(event_type)
            conn.execute(
                """
                INSERT OR IGNORE INTO lifecycle_events (
                    source_event_id, incident_id, alarm_key, event_type, occurred_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (event_id, incident_id, alarm_key, event_type, occurred_at,
                 json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )
            conn.execute(
                """
                INSERT INTO incidents (
                    incident_id, alarm_key, title, category, status, active, notified,
                    expected_clearance_minutes, first_seen_at, last_seen_at,
                    qualified_at, notified_at, recovery_started_at, resolved_at,
                    last_event_type
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, NULL, NULL, NULL, NULL, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    status = excluded.status,
                    active = excluded.active,
                    last_seen_at = excluded.last_seen_at,
                    last_event_type = excluded.last_event_type,
                    title = CASE WHEN excluded.title != excluded.alarm_key THEN excluded.title ELSE incidents.title END,
                    category = CASE WHEN excluded.category != 'other' THEN excluded.category ELSE incidents.category END,
                    expected_clearance_minutes = CASE
                        WHEN excluded.expected_clearance_minutes > 0 THEN excluded.expected_clearance_minutes
                        ELSE incidents.expected_clearance_minutes END;
                """,
                (
                    incident_id, alarm_key, str(payload.get("title") or alarm_key),
                    str(payload.get("category") or "other"), status, active,
                    int(payload.get("expected_clearance_minutes") or 0),
                    occurred_at, occurred_at, event_type,
                ),
            )
            if event_type == "active":
                conn.execute(
                    "UPDATE incidents SET qualified_at = COALESCE(qualified_at, ?) WHERE incident_id = ?;",
                    (occurred_at, incident_id),
                )
            elif event_type == "notification_accepted":
                conn.execute(
                    "UPDATE incidents SET notified = 1, notified_at = COALESCE(notified_at, ?) WHERE incident_id = ?;",
                    (occurred_at, incident_id),
                )
            elif event_type == "recovering":
                conn.execute(
                    "UPDATE incidents SET recovery_started_at = ? WHERE incident_id = ?;",
                    (occurred_at, incident_id),
                )
            elif event_type == "active_again":
                conn.execute(
                    "UPDATE incidents SET recovery_started_at = NULL WHERE incident_id = ?;",
                    (incident_id,),
                )
            elif event_type in {"resolved", "cancelled"}:
                conn.execute(
                    "UPDATE incidents SET resolved_at = ? WHERE incident_id = ?;",
                    (occurred_at, incident_id),
                )

        for item in incidents:
            conn.execute(
                """
                INSERT INTO incidents (
                    incident_id, alarm_key, title, category, status, active, notified,
                    expected_clearance_minutes, first_seen_at, last_seen_at,
                    qualified_at, notified_at, recovery_started_at, resolved_at,
                    last_event_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    title = excluded.title, category = excluded.category,
                    status = excluded.status, active = excluded.active,
                    notified = excluded.notified,
                    expected_clearance_minutes = excluded.expected_clearance_minutes,
                    last_seen_at = excluded.last_seen_at,
                    qualified_at = excluded.qualified_at,
                    notified_at = excluded.notified_at,
                    recovery_started_at = CASE
                        WHEN excluded.status = 'resolved' THEN incidents.recovery_started_at
                        ELSE excluded.recovery_started_at END,
                    resolved_at = excluded.resolved_at;
                """,
                (
                    str(item["incident_id"]), str(item["alarm_key"]), str(item["title"]),
                    str(item["category"]), str(item["status"]), int(item["active"]),
                    int(item["notified"]), int(item["expected_clearance_minutes"]),
                    str(item["first_seen_at"]), str(item["last_seen_at"]),
                    item.get("qualified_at"), item.get("notified_at"),
                    item.get("recovery_started_at"), item.get("resolved_at"),
                    str(item["status"]),
                ),
            )

        cursor = int(snapshot.get("last_event_id") or 0)
        if cursor == 0:
            current = conn.execute(
                "SELECT cursor_value FROM sync_state WHERE source = 'panelexemys';"
            ).fetchone()
            cursor = int(current["cursor_value"]) if current else 0
        conn.execute(
            """
            INSERT INTO sync_state(source, cursor_value, updated_at)
            VALUES ('panelexemys', ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                cursor_value = excluded.cursor_value, updated_at = excluded.updated_at;
            """,
            (cursor, _AUTH.utc_iso()),
        )


def ingest_dispatches(items: list[dict]) -> None:
    with _LOCK, _connect() as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO dispatches (
                    incident_id, recipients, subject, status, created_at, updated_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    recipients = excluded.recipients, subject = excluded.subject,
                    status = excluded.status, updated_at = excluded.updated_at,
                    last_error = excluded.last_error;
                """,
                (
                    str(item["idempotency_key"]),
                    json.dumps(item["recipients"], ensure_ascii=False),
                    str(item["subject"]), str(item["status"]),
                    str(item["created_at"]), str(item["updated_at"]),
                    item.get("last_error"),
                ),
            )


def list_incidents(view_filter: str, limit: int) -> list[dict]:
    clauses = {
        "potential": "i.status = 'potential'",
        "active": "i.status IN ('active', 'recovering')",
        "all": "1 = 1",
    }
    if view_filter not in clauses:
        raise ValueError("Filtro invalido")
    safe_limit = min(5000, max(1, int(limit)))
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT i.*, d.recipients, d.status AS dispatch_status,
                   d.updated_at AS dispatch_updated_at, d.last_error AS dispatch_error
            FROM incidents i
            LEFT JOIN dispatches d ON d.incident_id = i.incident_id
            WHERE {clauses[view_filter]}
            ORDER BY i.first_seen_at DESC
            LIMIT ?;
            """,
            (safe_limit,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["recipients"] = json.loads(item["recipients"]) if item["recipients"] else []
            result.append(item)
        return result


def _minutes_between(start: str, end: str) -> float:
    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return max(0.0, (parse(end) - parse(start)).total_seconds() / 60.0)


def dashboard() -> dict:
    with _LOCK, _connect() as conn:
        count_rows = conn.execute(
            "SELECT status, COUNT(*) AS total FROM incidents GROUP BY status;"
        ).fetchall()
        frequent_rows = conn.execute(
            """
            SELECT alarm_key, MAX(title) AS title, MAX(category) AS category,
                   COUNT(*) AS total
            FROM incidents
            WHERE qualified_at IS NOT NULL
            GROUP BY alarm_key
            ORDER BY total DESC, alarm_key ASC
            LIMIT 10;
            """
        ).fetchall()
        clearance_rows = conn.execute(
            """
            SELECT alarm_key, title, category, expected_clearance_minutes,
                   qualified_at, recovery_started_at, resolved_at
            FROM incidents
            WHERE qualified_at IS NOT NULL;
            """
        ).fetchall()

    groups: dict[str, dict] = {}
    for row in clearance_rows:
        key = str(row["alarm_key"])
        entry = groups.setdefault(key, {
            "alarm_key": key, "title": str(row["title"]),
            "category": str(row["category"]),
            "configured_minutes": int(row["expected_clearance_minutes"]), "samples": [],
        })
        clearance_at = row["recovery_started_at"] or row["resolved_at"]
        if clearance_at is not None:
            entry["samples"].append(
                _minutes_between(str(row["qualified_at"]), str(clearance_at))
            )
    clearance = []
    for entry in groups.values():
        samples = sorted(entry.pop("samples"))
        entry["sample_count"] = len(samples)
        entry["median_minutes"] = round(statistics.median(samples), 1) if samples else None
        entry["p90_minutes"] = (
            round(samples[max(0, math.ceil(len(samples) * 0.9) - 1)], 1)
            if samples else None
        )
        clearance.append(entry)
    clearance.sort(key=lambda item: (-item["sample_count"], item["alarm_key"]))
    counts = {str(row["status"]): int(row["total"]) for row in count_rows}
    return {
        "counts": {
            "potential": counts.get("potential", 0),
            "active": counts.get("active", 0),
            "recovering": counts.get("recovering", 0),
            "resolved": counts.get("resolved", 0),
        },
        "frequent": [dict(row) for row in frequent_rows],
        "clearance": clearance[:20],
    }
