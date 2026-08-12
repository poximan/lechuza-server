from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db, sync_worker
from .alarm_api import create_alarm_router
from .alarm_service import AlarmService


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    sync_worker.start()
    yield
    sync_worker.stop()


app = FastAPI(title="Alarmero Service", version="1.0.0", lifespan=lifespan)
app.include_router(create_alarm_router(AlarmService()))
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
