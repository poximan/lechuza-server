from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, sync_worker


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    sync_worker.start()
    yield
    sync_worker.stop()


app = FastAPI(title="Alarmero Service", version="1.0.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


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
    return {"status": "ok" if sync["state"] == "ok" else "degraded", "sync": sync}
