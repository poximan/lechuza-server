from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from alarm_generator import create_alarm_generator_router
from src import config
from src.api.grd_api import create_grd_router
from src.bootstrap import ApplicationContext, create_context
from src.persistencia.schema import ensure_database
from src.services.alarm_generator import GrdAlarmGenerator

_context: ApplicationContext | None = None
_alarms = GrdAlarmGenerator()

def context() -> ApplicationContext:
    if _context is None:
        raise RuntimeError("Contexto GRD no inicializado")
    return _context

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _context
    ensure_database()
    _context = create_context(_alarms)
    _context.orchestrator.start()
    try:
        yield
    finally:
        _context.orchestrator.stop()
        _context.publisher.close()
        _context = None

app = FastAPI(title="grd-collector-service", version="1.1.0", lifespan=lifespan)
app.include_router(create_grd_router(context))
app.include_router(
    create_alarm_generator_router(
        _alarms.exemys_outbox,
        config.ALARM_INTERNAL_API_KEY,
        base_path="",
    )
)

@app.get("/health")
def health():
    snapshot = context().orchestrator.health_snapshot()
    return JSONResponse(
        status_code=200 if snapshot["ready"] else 503,
        content=snapshot,
    )
