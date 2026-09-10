from datetime import timedelta
from .alarm_time import _iso
from .dashboard_repository import load_dashboard
from .dashboard_metrics import summarize_dashboard
from timeauthority import get_time_authority

from . import db, sync_worker


class AlarmService:
    def __init__(self) -> None:
        self._time_authority = get_time_authority()

    def list_incidents(self, view: str, limit: int) -> dict:
        return {"items": db.list_incidents(view, limit)}

    def dashboard(self) -> dict:
        now = self._time_authority.utc_now()
        boundaries = tuple(_iso(now - timedelta(days=days)) for days in (1, 7, 30, 365))
        return summarize_dashboard(*load_dashboard(boundaries))

    def catalog(self) -> dict:
        return {"items": db.list_catalog()}

    def update_notification_settings(
        self,
        source_id: str,
        alarm_key: str,
        send_start: bool,
        send_end: bool,
    ) -> dict:
        db.update_notification_settings(
            source_id,
            alarm_key,
            send_start,
            send_end,
        )
        return {"ok": True}

    def health(self) -> dict:
        sync = sync_worker.status()
        return {
            "status": "ok" if sync["state"] == "ok" else "degraded",
            "generated_at": self._time_authority.utc_iso(),
            "sync": sync,
        }
