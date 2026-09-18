from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from src.api.analyzers_api import create_analyzers_router
from src.bootstrap import ApplicationContext, create_context


_context: ApplicationContext | None = None


def context() -> ApplicationContext:
    if _context is None:
        raise RuntimeError("Contexto Janitza no inicializado")
    return _context


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _context
    _context = create_context()
    _context.collector.start()
    try:
        yield
    finally:
        _context.collector.stop()
        _context = None


app = FastAPI(
    title="janitza-collector-service",
    version="1.1.0",
    lifespan=lifespan,
)
app.include_router(create_analyzers_router(context))


@app.get("/health")
def health() -> dict:
    if not context().collector.thread.is_alive():
        raise HTTPException(status_code=503, detail="Recolector Janitza detenido")
    return {"status": "up"}
