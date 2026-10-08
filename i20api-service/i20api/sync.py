import threading
from datetime import timedelta

from .clock import LOCAL, clock, iso, months_before
from .sentryx import SentryxError


class SyncManager:
    def __init__(self, settings, storage, client, now=None):
        self.settings, self.storage, self.client = settings, storage, client
        self.now = now or clock.utc_now
        self.lock = threading.RLock()
        self.busy = False
        self.manual_pending = False
        self.stop_event = threading.Event()
        self.thread = None
        interrupted = self.storage.get("last_attempt")
        if interrupted and interrupted.get("outcome") == "running":
            interrupted.update(outcome="error", error="Sincronización interrumpida por un reinicio",
                               finished_at=iso(self.now()))
            self.storage.put("last_attempt", interrupted)

    def _cycle(self, now):
        day = now.astimezone(LOCAL).date().isoformat()
        cycle = self.storage.get("cycle", {})
        if cycle.get("day") != day:
            cycle = {"day": day, "attempts": 0, "state": "waiting", "retry_at": None}
            self.storage.put("cycle", cycle)
        return cycle

    def _next(self, cycle, now):
        hour, minute = map(int, self.settings.daily_time.split(":"))
        today = now.astimezone(LOCAL).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if cycle["state"] in {"complete", "suspended"}:
            return today + timedelta(days=1)
        if cycle.get("retry_at"):
            return clock.parse(cycle["retry_at"])
        return today

    def status(self):
        with self.lock:
            now = self.now()
            cycle = self._cycle(now)
            return {"running": self.busy or self.manual_pending, "cycle": cycle, "next_attempt_at": iso(self._next(cycle, now)),
                    "last_attempt": self.storage.get("last_attempt"),
                    "last_success_at": self.storage.get("last_success_at"),
                    "timezone": "UTC−3", "daily_time": self.settings.daily_time,
                    "retry_hours": list(self.settings.retry_hours)}

    def run(self, manual=False):
        with self.lock:
            if self.busy or (self.manual_pending and not manual):
                return False
            started = self.now()
            cycle = self._cycle(started)
            if not manual and (cycle["state"] in {"complete", "suspended"} or started < self._next(cycle, started)):
                return False
            self.busy = True
            if manual:
                self.manual_pending = False
            if not manual:
                # Persist before doing HTTP so a restart cannot produce unlimited attempts.
                cycle["attempts"] += 1
                cycle["state"] = "retrying" if cycle["attempts"] <= len(self.settings.retry_hours) else "suspended"
                cycle["retry_at"] = iso(started + timedelta(hours=self.settings.retry_hours[cycle["attempts"] - 1])) if cycle["state"] == "retrying" else None
                self.storage.put("cycle", cycle)
            attempt = {"started_at": iso(started), "source": "manual" if manual else "automatic",
                       "outcome": "running", "new_records": 0, "error": None}
            self.storage.put("last_attempt", attempt)
        try:
            cutoff = months_before(started, self.settings.retention_months)
            self.storage.prune(cutoff)
            records = self.client.measurements(cutoff, started)
            count = self.storage.save(records, months_before(self.now(), self.settings.retention_months))
            attempt.update(outcome="new_data" if count else "no_new_data", new_records=count)
            self.storage.put("last_success_at", iso(self.now()))
        except Exception as exc:
            attempt.update(outcome="error", error=str(exc) if isinstance(exc, SentryxError)
                           else f"No se pudo completar la sincronización ({type(exc).__name__})")
        finally:
            with self.lock:
                attempt["finished_at"] = iso(self.now())
                self.storage.put("last_attempt", attempt)
                if not manual:
                    if attempt["outcome"] == "new_data":
                        cycle.update(state="complete", retry_at=None)
                    self.storage.put("cycle", cycle)
                self.busy = False
        return True

    def request_manual(self):
        with self.lock:
            if self.busy or (self.thread and self.thread.is_alive()):
                return False
            self.manual_pending = True
            self.thread = threading.Thread(target=self.run, kwargs={"manual": True}, daemon=True)
            self.thread.start()
            return True

    def tick(self):
        self.storage.prune(months_before(self.now(), self.settings.retention_months))
        return self.run()

    def start(self):
        def loop():
            while not self.stop_event.is_set():
                self.tick()
                self.stop_event.wait(10)
        self.scheduler = threading.Thread(target=loop, daemon=True)
        self.scheduler.start()

    def stop(self):
        self.stop_event.set()
