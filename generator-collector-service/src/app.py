from contextlib import asynccontextmanager

from alarm_generator import create_alarm_generator_router
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src import config
from src.api.generator_api import create_generator_router
from src.bootstrap import ApplicationContext, create_context
from src.services.alarm_generator import GeneratorAlarmGenerator


_context: ApplicationContext | None = None
_alarms = GeneratorAlarmGenerator()


def context() -> ApplicationContext:
    if _context is None:
        raise RuntimeError("Contexto de generadores no inicializado")
    return _context


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _context
    _context = create_context(_alarms)
    _context.orchestrator.start()
    try:
        yield
    finally:
        _context.orchestrator.stop()
        _context.publisher.close()
        _context = None


app = FastAPI(
    title="generator-collector-service",
    version="1.1.0",
    lifespan=lifespan,
)
app.include_router(create_generator_router(context))
app.include_router(
    create_alarm_generator_router(
        _alarms.generator_outbox,
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
