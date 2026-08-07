from __future__ import annotations

import json
import threading
import uuid
from datetime import timedelta

from src.utils import timebox

from .dao_base import with_connection


class AlarmIncidentsDAO:
    """Fuente durable del ciclo de vida de alarmas detectadas por panelexemys."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._ensure_schema()

    @staticmethod
    def _append_event(conn, incident_id: str, alarm_key: str, event_type: str, payload=None) -> None:
        conn.execute(
            """
            INSERT INTO alarm_events (incident_id, alarm_key, event_type, occurred_at, payload)
            VALUES (?, ?, ?, ?, ?);
            """,
            (incident_id, alarm_key, event_type, timebox.utc_iso(),
             json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)),
        )

    def _ensure_schema(self) -> None:
        def _init(conn):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alarm_incidents (
                    alarm_key TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    notified INTEGER NOT NULL,
                    activated_at TEXT NOT NULL,
                    notified_at TEXT,
                    resolved_at TEXT,
                    recovery_started_at TEXT,
                    status TEXT,
                    title TEXT,
                    category TEXT,
                    expected_clearance_minutes INTEGER,
                    first_seen_at TEXT,
                    last_seen_at TEXT,
                    qualified_at TEXT
                );
                """
            )
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(alarm_incidents);").fetchall()}
            additions = {
                "recovery_started_at": "TEXT", "status": "TEXT", "title": "TEXT",
                "category": "TEXT", "expected_clearance_minutes": "INTEGER",
                "first_seen_at": "TEXT", "last_seen_at": "TEXT", "qualified_at": "TEXT",
            }
            for name, sql_type in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE alarm_incidents ADD COLUMN {name} {sql_type};")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alarm_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    alarm_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alarm_events_incident ON alarm_events(incident_id, event_id);")
            conn.execute(
                """
                UPDATE alarm_incidents
                SET status = CASE WHEN active = 1 THEN 'active' ELSE 'resolved' END,
                    title = COALESCE(title, alarm_key),
                    category = COALESCE(category, 'legacy'),
                    expected_clearance_minutes = COALESCE(expected_clearance_minutes, 0),
                    first_seen_at = COALESCE(first_seen_at, activated_at),
                    last_seen_at = COALESCE(last_seen_at, activated_at),
                    qualified_at = COALESCE(qualified_at, activated_at)
                WHERE status IS NULL OR first_seen_at IS NULL;
                """
            )
        with self._lock:
            with_connection(_init)

    @staticmethod
    def _metadata(metadata: dict | None, alarm_key: str) -> tuple[str, str, int]:
        value = metadata if isinstance(metadata, dict) else {}
        title = str(value.get("title") or alarm_key).strip()
        category = str(value.get("category") or "other").strip()
        expected = int(value.get("expected_clearance_minutes") or 0)
        if expected < 0:
            raise ValueError("expected_clearance_minutes no puede ser negativo")
        return title, category, expected

    def prepare_notification(self, alarm_key: str, metadata: dict | None = None) -> str | None:
        """Confirma la incidencia y retorna su ID, o None si ya fue notificada."""
        key = str(alarm_key or "").strip()
        if not key:
            raise ValueError("alarm_key es obligatorio")
        title, category, expected = self._metadata(metadata, key)

        def _prepare(conn):
            row = conn.execute(
                "SELECT incident_id, active, notified, status FROM alarm_incidents WHERE alarm_key = ?;",
                (key,),
            ).fetchone()
            now = timebox.utc_iso()
            if row is not None and int(row["active"]) == 1:
                if int(row["notified"]) == 1:
                    return None
                incident_id = str(row["incident_id"])
                conn.execute(
                    """
                    UPDATE alarm_incidents
                    SET status = 'active', title = ?, category = ?,
                        expected_clearance_minutes = ?, qualified_at = COALESCE(qualified_at, ?),
                        last_seen_at = ?, recovery_started_at = NULL
                    WHERE alarm_key = ? AND incident_id = ?;
                    """,
                    (title, category, expected, now, now, key, incident_id),
                )
                if str(row["status"]) != "active":
                    self._append_event(conn, incident_id, key, "active", {
                        "title": title, "category": category,
                        "expected_clearance_minutes": expected,
                    })
                return incident_id

            incident_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO alarm_incidents (
                    alarm_key, incident_id, active, notified, activated_at,
                    notified_at, resolved_at, recovery_started_at, status,
                    title, category, expected_clearance_minutes, first_seen_at,
                    last_seen_at, qualified_at
                ) VALUES (?, ?, 1, 0, ?, NULL, NULL, NULL, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alarm_key) DO UPDATE SET
                    incident_id = excluded.incident_id, active = 1, notified = 0,
                    activated_at = excluded.activated_at, notified_at = NULL,
                    resolved_at = NULL, recovery_started_at = NULL, status = 'active',
                    title = excluded.title, category = excluded.category,
                    expected_clearance_minutes = excluded.expected_clearance_minutes,
                    first_seen_at = excluded.first_seen_at, last_seen_at = excluded.last_seen_at,
                    qualified_at = excluded.qualified_at;
                """,
                (key, incident_id, now, title, category, expected, now, now, now),
            )
            self._append_event(conn, incident_id, key, "active", {
                "title": title, "category": category,
                "expected_clearance_minutes": expected,
            })
            return incident_id
        with self._lock:
            return with_connection(_prepare)

    def mark_notified(self, alarm_key: str, incident_id: str) -> None:
        def _mark(conn):
            cursor = conn.execute(
                "UPDATE alarm_incidents SET notified = 1, notified_at = ? WHERE alarm_key = ? AND incident_id = ? AND active = 1 AND notified = 0;",
                (timebox.utc_iso(), alarm_key, incident_id),
            )
            if cursor.rowcount == 1:
                self._append_event(conn, incident_id, alarm_key, "notification_accepted")
        with self._lock:
            with_connection(_mark)

    def observe_condition(self, alarm_key: str, condition_active: bool,
                          recovery_minutes: int, metadata: dict | None = None) -> bool:
        """Observa la condicion y ejecuta las transiciones propiedad de panelexemys."""
        key = str(alarm_key or "").strip()
        if not key:
            raise ValueError("alarm_key es obligatorio")
        recovery_duration = timedelta(minutes=max(1, int(recovery_minutes)))
        title, category, expected = self._metadata(metadata, key)

        def _observe(conn):
            row = conn.execute("SELECT * FROM alarm_incidents WHERE alarm_key = ?;", (key,)).fetchone()
            now = timebox.utc_now()
            now_iso = timebox.utc_iso(now)
            if condition_active:
                if row is None or int(row["active"]) != 1:
                    incident_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO alarm_incidents (
                            alarm_key, incident_id, active, notified, activated_at,
                            notified_at, resolved_at, recovery_started_at, status,
                            title, category, expected_clearance_minutes, first_seen_at,
                            last_seen_at, qualified_at
                        ) VALUES (?, ?, 1, 0, ?, NULL, NULL, NULL, 'potential', ?, ?, ?, ?, ?, NULL)
                        ON CONFLICT(alarm_key) DO UPDATE SET
                            incident_id = excluded.incident_id, active = 1, notified = 0,
                            activated_at = excluded.activated_at, notified_at = NULL,
                            resolved_at = NULL, recovery_started_at = NULL, status = 'potential',
                            title = excluded.title, category = excluded.category,
                            expected_clearance_minutes = excluded.expected_clearance_minutes,
                            first_seen_at = excluded.first_seen_at, last_seen_at = excluded.last_seen_at,
                            qualified_at = NULL;
                        """,
                        (key, incident_id, now_iso, title, category, expected, now_iso, now_iso),
                    )
                    self._append_event(conn, incident_id, key, "potential", {
                        "title": title, "category": category,
                        "expected_clearance_minutes": expected,
                    })
                    return False
                incident_id = str(row["incident_id"])
                previous_status = str(row["status"] or "active")
                conn.execute(
                    """
                    UPDATE alarm_incidents SET last_seen_at = ?, title = ?, category = ?,
                        expected_clearance_minutes = ?, recovery_started_at = NULL,
                        status = CASE WHEN status = 'recovering' THEN 'active' ELSE status END
                    WHERE alarm_key = ? AND active = 1;
                    """,
                    (now_iso, title, category, expected, key),
                )
                if previous_status == "recovering":
                    self._append_event(conn, incident_id, key, "active_again")
                return False

            if row is None or int(row["active"]) != 1:
                return False
            incident_id = str(row["incident_id"])
            if str(row["status"]) == "potential" and int(row["notified"]) == 0:
                conn.execute(
                    "UPDATE alarm_incidents SET active = 0, status = 'resolved', resolved_at = ?, last_seen_at = ? WHERE alarm_key = ? AND incident_id = ?;",
                    (now_iso, now_iso, key, incident_id),
                )
                self._append_event(conn, incident_id, key, "cancelled")
                return True
            recovery_started_at = row["recovery_started_at"]
            if recovery_started_at is None:
                conn.execute(
                    "UPDATE alarm_incidents SET recovery_started_at = ?, status = 'recovering' WHERE alarm_key = ? AND active = 1;",
                    (now_iso, key),
                )
                self._append_event(conn, incident_id, key, "recovering")
                return False
            if now - timebox.parse(str(recovery_started_at), legacy=True) < recovery_duration:
                return False
            cursor = conn.execute(
                "UPDATE alarm_incidents SET active = 0, status = 'resolved', resolved_at = ?, recovery_started_at = NULL, last_seen_at = ? WHERE alarm_key = ? AND active = 1;",
                (now_iso, now_iso, key),
            )
            if cursor.rowcount == 1:
                self._append_event(conn, incident_id, key, "resolved")
                return True
            return False
        with self._lock:
            return bool(with_connection(_observe))

    def active_keys(self, prefix: str) -> list[str]:
        def _list(conn):
            rows = conn.execute("SELECT alarm_key FROM alarm_incidents WHERE active = 1 AND alarm_key LIKE ?;", (f"{prefix}%",)).fetchall()
            return [str(row["alarm_key"]) for row in rows]
        with self._lock:
            return list(with_connection(_list))

    def snapshot(self, after_event_id: int = 0, event_limit: int = 1000) -> dict:
        """Contrato de lectura HTTP para consumidores, sin exponer SQLite."""
        after = max(0, int(after_event_id))
        limit = min(5000, max(1, int(event_limit)))
        def _read(conn):
            incidents = conn.execute(
                """
                SELECT alarm_key, incident_id, status, active, notified, title, category,
                       expected_clearance_minutes, first_seen_at, last_seen_at, qualified_at,
                       notified_at, recovery_started_at, resolved_at
                FROM alarm_incidents ORDER BY first_seen_at DESC;
                """
            ).fetchall()
            rows = conn.execute(
                "SELECT event_id, incident_id, alarm_key, event_type, occurred_at, payload FROM alarm_events WHERE event_id > ? ORDER BY event_id ASC LIMIT ?;",
                (after, limit),
            ).fetchall()
            events = []
            for row in rows:
                item = dict(row)
                item["payload"] = json.loads(str(item["payload"]))
                events.append(item)
            return {"incidents": [dict(row) for row in incidents], "events": events,
                    "last_event_id": events[-1]["event_id"] if events else after,
                    "has_more": len(events) == limit}
        with self._lock:
            return dict(with_connection(_read))


alarm_incidents_dao = AlarmIncidentsDAO()
