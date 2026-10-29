from collections.abc import Callable

from fastapi import APIRouter
from pydantic import BaseModel, StrictBool

from src.bootstrap import ApplicationContext


class ObserverRequest(BaseModel):
    enabled: StrictBool


def create_analyzers_router(
    context: Callable[[], ApplicationContext],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/analizadores")
    def analyzers() -> dict:
        return context().collector.snapshot()

    @router.get("/api/analizadores/observer")
    def observer() -> dict[str, bool]:
        return {"enabled": context().collector.get_observer()}

    @router.post("/api/analizadores/observer")
    def set_observer(body: ObserverRequest) -> dict[str, bool]:
        return {"enabled": context().collector.set_observer(body.enabled)}

    return router
