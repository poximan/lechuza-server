from typing import Any, Callable, Dict

from fastapi import APIRouter, HTTPException

from src.bootstrap import ApplicationContext


def create_generator_router(context: Callable[[], ApplicationContext]) -> APIRouter:
    router = APIRouter(prefix="/api/ge")

    def snapshot(name: str) -> Dict[str, Any]:
        try:
            return context().generator_cache.snapshot(name)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/edif-estivariz/status")
    def estivariz_status() -> Dict[str, Any]:
        return snapshot("edif-estivariz")

    @router.get("/edif-fontana/status")
    def fontana_status() -> Dict[str, Any]:
        return snapshot("edif-fontana")

    @router.get("/status")
    def status() -> Dict[str, Any]:
        return estivariz_status()

    return router
