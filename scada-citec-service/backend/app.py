import asyncio
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .catalog import MimicCatalog
from .daemon_client import DaemonClient
from .logger import logger
from .state_cache import StateCache

app = FastAPI(title="scada-citec-service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"]
)

state_cache = StateCache()
catalog = MimicCatalog()
daemon_client: DaemonClient | None = None
refresh_task: asyncio.Task | None = None
catalog_task: asyncio.Task | None = None


@app.on_event("startup")
async def _startup() -> None:
    global daemon_client, refresh_task, catalog_task
    daemon_client = DaemonClient()
    catalog_task = asyncio.create_task(_catalog_loop())
    await _refresh_catalog_once()
    if config.REFRESH_ON_START:
        refresh_task = asyncio.create_task(_refresh_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global daemon_client, refresh_task, catalog_task
    if catalog_task:
        catalog_task.cancel()
        try:
            await catalog_task
        except asyncio.CancelledError:
            pass
        catalog_task = None
    if refresh_task:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
        refresh_task = None
    if daemon_client:
        await daemon_client.close()
        daemon_client = None


async def _refresh_loop() -> None:
    assert daemon_client is not None
    while True:
        await _refresh_cycle_once()
        await asyncio.sleep(config.ADAPTER_QUERY_INTERVAL_SECONDS)


async def _catalog_loop() -> None:
    assert daemon_client is not None
    while True:
        await _refresh_catalog_once()
        await asyncio.sleep(config.TAG_REFRESH_INTERVAL_SECONDS)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "up"}


@app.get("/api/mimic/elements")
async def get_elements() -> Dict[str, Any]:
    groups = await catalog.groups()
    payload = [
        {
            "prefix": group.prefix,
            "label": group.label,
            "elements": [
                {
                    "tag": element.tag,
                    "label": element.label,
                    "voltage": element.voltage,
                }
                for element in group.elements
            ],
        }
        for group in groups
    ]
    return {"groups": payload}


@app.get("/api/mimic/state")
async def get_state() -> Dict[str, List[Dict[str, Any]]]:
    groups = await catalog.groups()
    state_map = await state_cache.snapshot_by_tag()
    response_groups: List[Dict[str, Any]] = []
    for group in groups:
        elements_payload: List[Dict[str, Any]] = []
        for element in group.elements:
            state_entry = state_map.get(element.tag)
            elements_payload.append(
                {
                    "tag": element.tag,
                    "label": element.label,
                    "voltage": element.voltage,
                    "state": state_entry.state if state_entry else "desconocido",
                    "updated_at": state_entry.updated_at if state_entry else None,
                    "raw_value": state_entry.raw_value if state_entry else None,
                }
            )
        response_groups.append(
            {
                "prefix": group.prefix,
                "label": group.label,
                "elements": elements_payload,
            }
        )
    return {"groups": response_groups}


@app.post("/api/mimic/refresh")
async def manual_refresh() -> JSONResponse:
    if not daemon_client:
        return JSONResponse({"status": "adapter"}, status_code=503)
    await _refresh_cycle_once()
    return JSONResponse({"status": "ok"})


async def _refresh_cycle_once() -> None:
    if not daemon_client:
        return
    elements = await catalog.elements()
    if not elements:
        return
    for element in elements:
        tag = element.tag
        try:
            result = await daemon_client.fetch_tag(tag)
        except Exception as exc:  # pragma: no cover
            logger.warning("Fallo refrescando %s: %s", tag, exc, origin="SCADA-CITEC")
            continue
        await state_cache.update(tag, result.get("state"), result.get("timestamp"))


async def _refresh_catalog_once() -> None:
    if not daemon_client:
        return
    try:
        summary = await daemon_client.fetch_tags_summary()
    except Exception as exc:  # pragma: no cover
        logger.warning("Fallo obteniendo catalogo de tags: %s", exc, origin="SCADA-CITEC")
        return
    items = summary.get("items") or []
    tags = [item.get("tag") for item in items if isinstance(item, dict) and item.get("tag")]
    if not tags:
        logger.warning("Catalogo SCADA sin tags disponibles", origin="SCADA-CITEC")
        return
    await catalog.update_from_tags(tags)
    elements_snapshot = await catalog.elements()
    await state_cache.sync_elements(elements_snapshot)


frontend_path = config.FRONTEND_DIR
if not frontend_path.exists():
    frontend_path.mkdir(parents=True, exist_ok=True)

app.mount("/", StaticFiles(directory=str(frontend_path), html=True, check_dir=False), name="frontend")
