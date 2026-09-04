from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from alarm_generator import create_alarm_generator_router

from src.api.generator_api import create_generator_router
from src.api.grd_api import create_grd_router
from src.api.relay_api import create_relay_router
from src.bootstrap import ApplicationContext, create_context
from src import config
from src.services.alarm_generator import ModbusAlarmGenerator
from src.persistencia.validador_esquema import check_database_access, validate_database_schema


_context: ApplicationContext | None = None
_alarm_generator = ModbusAlarmGenerator()


def context() -> ApplicationContext:
    if _context is None:
        raise RuntimeError("El contexto de aplicacion no fue inicializado")
    return _context


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _context
    validate_database_schema()
    created = create_context(_alarm_generator)
    _context = created
    created.logger.log(
        "Esquema validado; iniciando Modbus Collector.",
        origin="MW/APP",
    )
    try:
        created.orchestrator.start()
        yield
    finally:
        created.orchestrator.stop()
        created.publisher.close()
        _context = None


app = FastAPI(
    title="modbus-collector-service",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> JSONResponse:
    try:
        check_database_access()
        snapshot = context().orchestrator.health_snapshot()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "down",
                "error": f"{type(exc).__name__}: {exc}",
            },
        )

    status_code = 200 if snapshot["ready"] else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "up" if snapshot["ready"] else "degraded",
            **snapshot,
        },
    )


app.include_router(create_grd_router(context))
app.include_router(create_generator_router(context))
app.include_router(create_relay_router(context))
app.include_router(
    create_alarm_generator_router(
        _alarm_generator.exemys_outbox,
        config.ALARM_INTERNAL_API_KEY,
        base_path="/exemys-alarm-generator",
    )
)
app.include_router(
    create_alarm_generator_router(
        _alarm_generator.generator_outbox,
        config.ALARM_INTERNAL_API_KEY,
        base_path="/generator-alarm-generator",
    )
)
