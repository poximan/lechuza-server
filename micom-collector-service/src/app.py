from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.api.relay_api import create_relay_router
from src.bootstrap import ApplicationContext, create_context
from src.persistencia.schema import ensure_database


_context: ApplicationContext | None = None


def context() -> ApplicationContext:
    if _context is None:
        raise RuntimeError("Contexto MiCOM no inicializado")
    return _context


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _context
    ensure_database()
    _context = create_context()
    _context.orchestrator.start()
    try:
        yield
    finally:
        _context.orchestrator.stop()
        _context = None


app = FastAPI(
    title="micom-collector-service",
    version="1.1.0",
    lifespan=lifespan,
)
app.include_router(create_relay_router(context))


@app.get("/health")
def health():
    snapshot = context().orchestrator.health_snapshot()
    return JSONResponse(
        status_code=200 if snapshot["ready"] else 503,
        content=snapshot,
    )
