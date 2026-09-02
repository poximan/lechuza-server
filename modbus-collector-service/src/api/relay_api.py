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
        application = context()
        items: List[dict] = []
        for modbus_id, description in reles_dao.get_all_reles_with_descriptions().items():
            internal_id = reles_dao.get_internal_id_by_modbus_id(modbus_id)
            if internal_id is None:
                raise RuntimeError(
                    f"El rele Modbus {modbus_id} no tiene ID interno en el catalogo"
                )
            latest = fallas_reles_dao.get_current_falla_for_rele(internal_id)
            if latest and latest.get("timestamp"):
                timestamp = latest["timestamp"]
                value = (
                    timestamp
                    if isinstance(timestamp, datetime)
                    else timebox.parse_preserving_subseconds(
                        timestamp,
                        legacy=True,
                    )
                )
                latest["timestamp"] = timebox.utc_iso_milliseconds(value)
                latest["timestamp_format"] = latest.pop("formato_timestamp")
                latest["phase_a_raw"] = latest.pop("fasea_corr")
                latest["phase_b_raw"] = latest.pop("faseb_corr")
                latest["phase_c_raw"] = latest.pop("fasec_corr")
                latest["earth_raw"] = latest.pop("tierra_corr")
                latest["current_calculation"] = (
                    application.orchestrator.relay_current_calculation_snapshot(modbus_id)
                )
            items.append(
                {
                    "id_modbus": modbus_id,
                    "description": description,
                    "latest": latest,
                    "modbus_queries": application.orchestrator.relay_query_snapshot(
                        modbus_id
                    ),
                }
            )
        return {
            "items": items,
            "observer_runtime": (
                application.orchestrator.relay_observer_runtime_snapshot()
            ),
        }

    @router.get("/observer")
    def get_observer() -> Dict[str, Any]:
        return {"enabled": context().state_store.get_reles_enabled()}

    @router.post("/observer")
    def set_observer(payload: RelayObserverRequest) -> JSONResponse:
        context().state_store.set_reles_enabled(bool(payload.enabled))
        return JSONResponse({"enabled": bool(payload.enabled)})

    @router.get("/{relay_id}/latest-disturbance")
    def latest_disturbance(relay_id: int) -> Any:
        if reles_dao.get_internal_id_by_modbus_id(relay_id) is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"No existe el rele Modbus {relay_id}"},
            )
        return context().orchestrator.relay_disturbance_snapshot(relay_id)

    @router.post("/{relay_id}/clock-snapshot")
    def clock_snapshot(relay_id: int) -> Any:
        if reles_dao.get_internal_id_by_modbus_id(relay_id) is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"No existe el rele Modbus {relay_id}"},
            )
        return context().orchestrator.relay_clock_on_demand(relay_id)

    return router
