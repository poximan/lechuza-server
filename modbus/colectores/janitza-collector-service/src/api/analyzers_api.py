from collections.abc import Callable

from fastapi import APIRouter

from src.bootstrap import ApplicationContext


def create_analyzers_router(
    context: Callable[[], ApplicationContext],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/analizadores")
    def analyzers() -> dict:
        return context().collector.snapshot()

    return router
