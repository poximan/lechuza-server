import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from .clock import clock, iso, months_before
from .settings import Settings, credentials
from .sentryx import SentryxClient
from .storage import Storage
from .sync import SyncManager


def create_app(settings, storage, manager):
    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        yield
        manager.stop()

    app = FastAPI(title="i20api-service", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "up", "sync": manager.status()}

    @app.get("/api/caudalimetros")
    def index():
        cutoff = months_before(clock.utc_now(), settings.retention_months)
        storage.prune(cutoff)
        return {"locations": [{**item, **storage.bounds(item["id"], settings.resolution)} for item in settings.locations],
                "resolution": settings.resolution, "retention_months": settings.retention_months,
                "retained_from": iso(cutoff), "sync": manager.status()}

    @app.get("/api/measurements")
    def measurements(location_id: str, start: str = Query(...), end: str = Query(...)):
        if location_id not in {x["id"] for x in settings.locations}:
            raise HTTPException(404, "Ubicación no configurada")
        try:
            since, until = clock.parse(start), clock.parse(end)
            if until <= since:
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(400, "Rango temporal inválido") from None
        cutoff = months_before(clock.utc_now(), settings.retention_months)
        storage.prune(cutoff)
        return {"location_id": location_id, "resolution": settings.resolution,
                "start": iso(max(since, cutoff)), "end": iso(until),
                "items": storage.series(location_id, max(since, cutoff), until, settings.resolution)}

    @app.post("/api/sync", status_code=202)
    def synchronize():
        if not manager.request_manual():
            raise HTTPException(409, "Ya hay una sincronización en curso")
        return {"accepted": True}

    return app


def app_factory():
    settings = Settings.load(os.environ["I20_CONFIG_FILE"])
    storage = Storage(os.environ["I20_DATABASE_PATH"])
    client = SentryxClient(settings, *credentials(os.environ["I20_CREDENTIALS_FILE"]))
    return create_app(settings, storage, SyncManager(settings, storage, client))
