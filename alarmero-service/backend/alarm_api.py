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

    @router.get("/api/catalog")
    def catalog():
        return service.catalog()

    @router.put("/api/catalog/{source_id}/{alarm_key:path}")
    def update_catalog_item(source_id: str, alarm_key: str, payload: dict):
        send_start = payload.get("send_start")
        send_end = payload.get("send_end")
        if not isinstance(send_start, bool) or not isinstance(send_end, bool):
            raise HTTPException(
                status_code=422,
                detail="send_start y send_end deben ser booleanos",
            )
        try:
            return service.update_notification_settings(
                source_id,
                alarm_key,
                send_start,
                send_end,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/health")
    def health():
        return service.health()

    return router
