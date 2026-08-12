from timeauthority import get_time_authority

from . import db, sync_worker


class AlarmService:
    def __init__(self) -> None:
        self._time_authority = get_time_authority()

    def list_incidents(self, view: str, limit: int) -> dict:
        return {"items": db.list_incidents(view, limit)}

    def dashboard(self) -> dict:
        return db.dashboard()

    def health(self) -> dict:
        sync = sync_worker.status()
        return {
            "status": "ok" if sync["state"] == "ok" else "degraded",
            "generated_at": self._time_authority.utc_iso(),
            "sync": sync,
        }
