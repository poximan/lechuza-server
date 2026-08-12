from __future__ import annotations

from typing import Dict

from fastapi import FastAPI

from src import config
from src.api.generator_api import create_generator_router
from src.api.grd_api import router as grd_router
from src.api.relay_api import create_relay_router
from src.bootstrap import ApplicationContext, create_context
from src.persistencia import ddl_esquema
from src.persistencia.dao.dao_grd import grd_dao
from src.persistencia.dao.dao_reles import reles_dao


app = FastAPI(title="modbus-collector-service", version="1.0.0")
_context: ApplicationContext | None = None


def context() -> ApplicationContext:
    if _context is None:
        raise RuntimeError("Application context not initialized")
    return _context


def ensure_catalogs() -> None:
    for grd_id, description in config.GRD_DESCRIPTIONS.items():
        grd_dao.insert_grd_description(grd_id, description)
    for relay_id, description in config.ESCLAVOS_MB.items():
        if description.strip().upper().startswith("NO APLICA"):
            continue
        reles_dao.insert_rele_description(relay_id, description)


@app.on_event("startup")
def startup() -> None:
    global _context
    created = create_context()
    created.logger.log("Inicializando esquema y catalogos de Modbus Collector.", origin="MW/APP")
    ddl_esquema.create_database_schema()
    ensure_catalogs()
    _context = created
    created.orchestrator.start()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "up"}


app.include_router(grd_router)
app.include_router(create_generator_router(context))
app.include_router(create_relay_router(context))
