from datetime import datetime
from typing import Any, Callable, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool

from src.bootstrap import ApplicationContext
from src.persistencia.dao.dao_fallas_reles import fallas_reles_dao
from src.persistencia.dao.dao_reles import reles_dao
from src.utils import timebox


class RelayObserverRequest(BaseModel):
    enabled: StrictBool


def create_relay_router(context: Callable[[], ApplicationContext]) -> APIRouter:
    router = APIRouter(prefix="/api/reles")

    @router.get("/faults")
    def faults() -> Dict[str, Any]:
        items: List[dict] = []
        for modbus_id, description in reles_dao.get_all_reles_with_descriptions().items():
            internal_id = reles_dao.get_internal_id_by_modbus_id(modbus_id)
            if internal_id is None:
                raise RuntimeError(
                    f"El rele Modbus {modbus_id} no tiene ID interno en el catalogo"
                )
            latest = fallas_reles_dao.get_latest_falla_for_rele(internal_id)
            if latest and latest.get("timestamp"):
                timestamp = latest["timestamp"]
                value = timestamp if isinstance(timestamp, datetime) else timebox.parse(timestamp, legacy=True)
                latest["timestamp"] = timebox.utc_iso(value)
            items.append({"id_modbus": modbus_id, "description": description, "latest": latest})
        return {"items": items}

    @router.get("/observer")
    def get_observer() -> Dict[str, Any]:
        return {"enabled": context().state_store.get_reles_enabled()}

    @router.post("/observer")
    def set_observer(payload: RelayObserverRequest) -> JSONResponse:
        context().state_store.set_reles_enabled(bool(payload.enabled))
        return JSONResponse({"enabled": bool(payload.enabled)})

    return router
