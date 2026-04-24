from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
from src import config

from dateutil.relativedelta import relativedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from src.persistencia import ddl_esquema
from src.persistencia.dao.dao_fallas_reles import fallas_reles_dao
from src.persistencia.dao.dao_grd import grd_dao
from src.persistencia.dao.dao_historicos import historicos_dao
from src.persistencia.dao.dao_reles import reles_dao
from src.utils import timebox
from src.bootstrap import ApplicationContext, create_context

app = FastAPI(title="modbus-mw-service", version="1.0.0")

_context: ApplicationContext | None = None


def _ctx() -> ApplicationContext:
    if _context is None:
        raise RuntimeError("Application context not initialized")
    return _context


def _ensure_catalogs() -> None:
    for grd_id, description in config.GRD_DESCRIPTIONS.items():
        grd_dao.insert_grd_description(grd_id, description)
    for rel_id, description in config.ESCLAVOS_MB.items():
        if description.strip().upper().startswith("NO APLICA"):
            continue
        reles_dao.insert_rele_description(rel_id, description)


@app.on_event("startup")
def _startup() -> None:
    global _context
    ctx = create_context()
    ctx.logger.log("Inicializando esquema y catálogos de Modbus MW.", origin="MW/APP")
    ddl_esquema.create_database_schema()
    _ensure_catalogs()
    _context = ctx
    ctx.orchestrator.start()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "up"}


def _serialize_disconnected(rows: List[dict]) -> List[dict]:
    serialized: List[dict] = []
    for row in rows:
        ts = row.get("last_disconnected_timestamp")
        iso_ts = ""
        if ts:
            try:
                if isinstance(ts, str):
                    iso_ts = timebox.utc_iso(timebox.parse(ts, legacy=True))
                else:
                    iso_ts = timebox.utc_iso(ts)
            except Exception:
                iso_ts = str(ts)
        serialized.append(
            {
                "id_grd": row.get("id_grd"),
                "description": row.get("description"),
                "last_disconnected_timestamp": iso_ts,
            }
        )
    return serialized


@app.get("/api/grd/descriptions")
def get_grd_descriptions() -> Dict[str, Any]:
    return {"items": grd_dao.get_all_grds_with_descriptions()}


@app.get("/api/grd/summary")
def get_grd_summary() -> Dict[str, Any]:
    states = historicos_dao.get_latest_states_for_all_grds()
    total = len(states)
    conectados = sum(1 for v in states.values() if v == 1)
    porcentaje = round((conectados * 100.0 / total), 2) if total else 0.0
    disconnected = _serialize_disconnected(historicos_dao.get_all_disconnected_grds())
    return {
        "summary": {
            "porcentaje": porcentaje,
            "total": total,
            "conectados": conectados,
            "ts": timebox.utc_iso(),
        },
        "states": states,
        "disconnected": disconnected,
    }


def _df_to_records(df) -> List[dict]:
    records: List[dict] = []
    if df is None or df.empty:
        return records
    for _, row in df.iterrows():
        ts = row.get("timestamp")
        ts_iso = ""
        if ts:
            try:
                ts_iso = timebox.utc_iso(ts if isinstance(ts, datetime) else ts.to_pydatetime())
            except Exception:
                ts_iso = str(ts)
        records.append({"timestamp": ts_iso, "conectado": int(row.get("conectado", 0))})
    return records


def _compute_range(window: str, page: int):
    now = timebox.utc_now()
    if window == "1sem":
        end_period = now - timedelta(weeks=max(page, 0))
        start_period = end_period - timedelta(days=6)
        start = start_period.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_period.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    if window == "1mes":
        ref = now - relativedelta(months=max(page, 0))
        start = ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + relativedelta(months=1)) - timedelta(microseconds=1)
        return start, end
    start = now - timedelta(days=30)
    end = now
    return start, end


def _history_payload(grd_id: int, window: str, page: int) -> Dict[str, Any]:
    descriptions = grd_dao.get_all_grds_with_descriptions()
    if grd_id not in descriptions:
        raise HTTPException(status_code=404, detail="GRD no encontrado")

    today_str = timebox.utc_now().strftime("%Y-%m-%d")
    window_norm = window if window in {"1sem", "1mes", "todo"} else "1sem"
    plot_start = plot_end = None

    if window_norm == "1sem":
        df = historicos_dao.get_weekly_data_for_grd(grd_id, today_str, page)
        total_periods = max(1, historicos_dao.get_total_weeks_for_grd(grd_id, today_str))
        plot_start, plot_end = _compute_range(window_norm, page)
    elif window_norm == "1mes":
        df = historicos_dao.get_monthly_data_for_grd(grd_id, today_str, page)
        total_periods = max(1, historicos_dao.get_total_months_for_grd(grd_id, today_str))
        plot_start, plot_end = _compute_range(window_norm, page)
    else:
        df = historicos_dao.get_all_data_for_grd(grd_id)
        total_periods = 1
        if df is not None and not df.empty:
            timestamps = df["timestamp"]
            first_ts = timestamps.min()
            last_ts = timestamps.max()
            plot_start = (
                first_ts.to_pydatetime() if hasattr(first_ts, "to_pydatetime") else first_ts
            )
            plot_end = (
                last_ts.to_pydatetime() if hasattr(last_ts, "to_pydatetime") else last_ts
            )
        else:
            plot_start, plot_end = _compute_range(window_norm, page)

    connected_before = historicos_dao.get_connected_state_before_timestamp(grd_id, plot_start)
    if connected_before is None:
        connected_before = 0

    return {
        "grd_id": grd_id,
        "description": descriptions.get(grd_id, ""),
        "window": window_norm,
        "page": page,
        "total_periods": total_periods,
        "range_start": timebox.utc_iso(plot_start),
        "range_end": timebox.utc_iso(plot_end),
        "connected_before": int(connected_before),
        "data": _df_to_records(df),
    }


@app.get("/api/grd/history")
def get_grd_history(grd_id: int, window: str = "1sem", page: int = 0) -> Dict[str, Any]:
    return _history_payload(grd_id, window, max(page, 0))


def _outages_payload(grd_id: int, limit: int) -> Dict[str, Any]:
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit debe ser mayor a 0")

    descriptions = grd_dao.get_all_grds_with_descriptions()
    if grd_id not in descriptions:
        raise HTTPException(status_code=404, detail="GRD no encontrado")

    now_utc = timebox.utc_now()
    outages_raw = historicos_dao.get_latest_outages_for_grd(grd_id, limit)
    items: List[dict] = []

    for row in outages_raw:
        start_value = row["start_timestamp"]
        end_value = row["end_timestamp"]
        start_dt = start_value if isinstance(start_value, datetime) else timebox.parse(start_value, legacy=True)
        end_dt = now_utc if end_value is None else (
            end_value if isinstance(end_value, datetime) else timebox.parse(end_value, legacy=True)
        )

        delta_seconds = (end_dt - start_dt).total_seconds()
        duration_minutes = int(delta_seconds // 60) if delta_seconds > 0 else 0

        items.append(
            {
                "start_timestamp": timebox.utc_iso(start_dt),
                "duration_minutes": duration_minutes,
            }
        )

    return {
        "grd_id": grd_id,
        "description": descriptions[grd_id],
        "items": items,
    }


@app.get("/api/grd/outages")
def get_grd_outages(grd_id: int, limit: int = 10) -> Dict[str, Any]:
    return _outages_payload(grd_id, limit)


@app.get("/api/ge/status")
def get_ge_status() -> Dict[str, str]:
    return _ctx().ge_cache.snapshot()


@app.get("/api/reles/faults")
def get_reles_faults() -> Dict[str, Any]:
    active = reles_dao.get_all_reles_with_descriptions()
    items: List[dict] = []
    for modbus_id, description in active.items():
        internal_id = reles_dao.get_internal_id_by_modbus_id(modbus_id)
        if internal_id is None:
            continue
        latest = fallas_reles_dao.get_latest_falla_for_rele(internal_id)
        if latest:
            ts_value = latest.get("timestamp")
            if ts_value:
                try:
                    parsed = ts_value if isinstance(ts_value, datetime) else timebox.parse(ts_value, legacy=True)
                    latest["timestamp"] = timebox.utc_iso(parsed)
                except Exception:
                    latest["timestamp"] = str(ts_value)
        items.append(
            {
                "id_modbus": modbus_id,
                "description": description,
                "latest": latest,
            }
        )
    return {"items": items}


@app.get("/api/reles/observer")
def get_reles_observer() -> Dict[str, Any]:
    return {"enabled": _ctx().state_store.get_reles_enabled()}


@app.post("/api/reles/observer")
def set_reles_observer(payload: Dict[str, Any]) -> JSONResponse:
    enabled = bool(payload.get("enabled", False))
    _ctx().state_store.set_reles_enabled(enabled)
    return JSONResponse({"enabled": enabled})
