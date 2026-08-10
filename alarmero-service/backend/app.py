from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from timeauthority import get_time_authority

from . import db, sync_worker


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
TIME_AUTHORITY = get_time_authority()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    sync_worker.start()
    yield
    sync_worker.stop()


app = FastAPI(title="Alarmero Service", version="1.0.0", lifespan=lifespan)


@app.get("/api/incidents")
def incidents(
    view: str = Query("active", alias="filter"),
    limit: int = Query(500, ge=1, le=5000),
):
    try:
        return {"items": db.list_incidents(view, limit)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/dashboard")
def dashboard():
    return db.dashboard()


@app.get("/health")
def health():
    sync = sync_worker.status()
    return {
        "status": "ok" if sync["state"] == "ok" else "degraded",
        "generated_at": TIME_AUTHORITY.utc_iso(),
        "sync": sync,
    }


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
