from fastapi import APIRouter, HTTPException, Query

from .alarm_service import AlarmService


def create_alarm_router(service: AlarmService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/incidents")
    def incidents(
        view: str = Query("active", alias="filter"),
        limit: int = Query(500, ge=1, le=5000),
    ):
        try:
            return service.list_incidents(view, limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/dashboard")
    def dashboard():
        return service.dashboard()

    @router.get("/health")
    def health():
        return service.health()

    return router
