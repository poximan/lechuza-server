import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .clock import iso


class Storage:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS measurements (
                    id TEXT NOT NULL, resolution TEXT NOT NULL, location_id TEXT NOT NULL,
                    stream_id TEXT NOT NULL, timestamp TEXT NOT NULL, value REAL NOT NULL,
                    unit TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id, resolution)
                );
                CREATE INDEX IF NOT EXISTS ix_measurements_time ON measurements(location_id, timestamp);
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value)))

    def prune(self, cutoff):
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM measurements WHERE timestamp < ?", (iso(cutoff),))

    def save(self, records, cutoff):
        new = 0
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM measurements WHERE timestamp < ?", (iso(cutoff),))
            for node in records:
                if node["timestamp"] < iso(cutoff):
                    continue
                existing = db.execute("SELECT 1 FROM measurements WHERE id=? AND resolution=?",
                                      (node["id"], node["resolution"])).fetchone()
                new += int(existing is None)
                db.execute("INSERT OR REPLACE INTO measurements VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (node["id"], node["resolution"], node["location"]["id"],
                     node["dataStream"]["id"], node["timestamp"], node["value"],
                     node["dataStream"]["unit"], json.dumps(node)))
        return new

    def series(self, location_id, start, end, resolution):
        with self.lock, self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM measurements WHERE location_id=? AND resolution=? AND timestamp>=? "
                "AND timestamp<=? ORDER BY timestamp, stream_id", (location_id, resolution, iso(start), iso(end)))]

    def bounds(self, location_id, resolution):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT MIN(timestamp) first, MAX(timestamp) last, COUNT(*) count "
                             "FROM measurements WHERE location_id=? AND resolution=?", (location_id, resolution)).fetchone()
            return dict(row)
