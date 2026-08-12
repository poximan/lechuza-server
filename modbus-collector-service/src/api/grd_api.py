from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any, Dict, List

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, HTTPException

from src import config
from src.persistencia.dao.dao_grd import grd_dao
from src.persistencia.dao.dao_historicos import historicos_dao
from src.utils import timebox


router = APIRouter(prefix="/api/grd")


@router.get("/descriptions")
def get_descriptions() -> Dict[str, Any]:
    return {"items": grd_dao.get_all_grds_with_descriptions()}


@router.get("/summary")
def get_summary() -> Dict[str, Any]:
    states = historicos_dao.get_latest_states_for_all_grds()
    total = len(states)
    connected = sum(1 for value in states.values() if value == 1)
    percentage = round((connected * 100.0 / total), 2) if total else 0.0
    return {
        "summary": {
            "porcentaje": percentage,
            "total": total,
            "conectados": connected,
            "ts": timebox.utc_iso(),
        },
        "states": states,
        "disconnected": _serialize_disconnected(historicos_dao.get_all_disconnected_grds()),
    }


@router.get("/history")
def get_history(grd_id: int, window: str = "1sem", page: int = 0) -> Dict[str, Any]:
    return _history_payload(grd_id, window, max(page, 0))


@router.get("/outages")
def get_outages(grd_id: int, limit: int = 10) -> Dict[str, Any]:
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit debe ser mayor a 0")
    descriptions = grd_dao.get_all_grds_with_descriptions()
    if grd_id not in descriptions:
        raise HTTPException(status_code=404, detail="GRD no encontrado")
    now = timebox.utc_now()
    items = []
    for row in historicos_dao.get_latest_outages_for_grd(grd_id, limit):
        start = _as_datetime(row["start_timestamp"])
        end = now if row["end_timestamp"] is None else _as_datetime(row["end_timestamp"])
        seconds = (end - start).total_seconds()
        items.append(
            {
                "start_timestamp": timebox.utc_iso(start),
                "duration_minutes": int(seconds // 60) if seconds > 0 else 0,
            }
        )
    return {"grd_id": grd_id, "description": descriptions[grd_id], "items": items}


def _serialize_disconnected(rows: List[dict]) -> List[dict]:
    serialized = []
    for row in rows:
        timestamp = row.get("last_disconnected_timestamp")
        iso_timestamp = ""
        if timestamp:
            try:
                iso_timestamp = timebox.utc_iso(
                    timebox.parse(timestamp, legacy=True) if isinstance(timestamp, str) else timestamp
                )
            except Exception:
                iso_timestamp = str(timestamp)
        serialized.append(
            {
                "id_grd": row.get("id_grd"),
                "description": row.get("description"),
                "last_disconnected_timestamp": iso_timestamp,
            }
        )
    return serialized


def _history_payload(grd_id: int, window: str, page: int) -> Dict[str, Any]:
    descriptions = grd_dao.get_all_grds_with_descriptions()
    if grd_id not in descriptions:
        raise HTTPException(status_code=404, detail="GRD no encontrado")
    if window not in {"1sem", "1mes", "todo"}:
        raise HTTPException(status_code=400, detail="window debe ser 1sem, 1mes o todo")

    today = timebox.utc_today_iso()
    plot_start = plot_end = None
    if window == "1sem":
        frame = historicos_dao.get_weekly_data_for_grd(grd_id, today, page)
        total_periods = max(1, historicos_dao.get_total_weeks_for_grd(grd_id, today))
        plot_start, plot_end = _compute_range(window, page)
    elif window == "1mes":
        frame = historicos_dao.get_monthly_data_for_grd(grd_id, today, page)
        total_periods = max(1, historicos_dao.get_total_months_for_grd(grd_id, today))
        plot_start, plot_end = _compute_range(window, page)
    else:
        frame, total_rows = historicos_dao.get_data_page_for_grd(
            grd_id,
            page,
            config.HISTORY_PAGE_SIZE,
        )
        total_periods = max(1, math.ceil(total_rows / config.HISTORY_PAGE_SIZE))
        if frame is not None and not frame.empty:
            first = frame["timestamp"].min()
            last = frame["timestamp"].max()
            plot_start = first.to_pydatetime() if hasattr(first, "to_pydatetime") else first
            plot_end = last.to_pydatetime() if hasattr(last, "to_pydatetime") else last
        else:
            plot_start, plot_end = _compute_range("1mes", 0)

    connected_before = historicos_dao.get_connected_state_before_timestamp(grd_id, plot_start)
    return {
        "grd_id": grd_id,
        "description": descriptions.get(grd_id, ""),
        "window": window,
        "page": page,
        "total_periods": total_periods,
        "page_size": config.HISTORY_PAGE_SIZE if window == "todo" else None,
        "range_start": timebox.utc_iso(plot_start),
        "range_end": timebox.utc_iso(plot_end),
        "connected_before": int(connected_before or 0),
        "data": _frame_records(frame),
    }


def _frame_records(frame) -> List[dict]:
    if frame is None or frame.empty:
        return []
    records = []
    for _, row in frame.iterrows():
        timestamp = row.get("timestamp")
        iso_timestamp = ""
        if timestamp:
            try:
                value = timestamp if isinstance(timestamp, datetime) else timestamp.to_pydatetime()
                iso_timestamp = timebox.utc_iso(value)
            except Exception:
                iso_timestamp = str(timestamp)
        records.append({"timestamp": iso_timestamp, "conectado": int(row.get("conectado", 0))})
    return records


def _compute_range(window: str, page: int):
    now = timebox.utc_now()
    if window == "1sem":
        end_period = now - timedelta(weeks=max(page, 0))
        start_period = end_period - timedelta(days=6)
        return (
            start_period.replace(hour=0, minute=0, second=0, microsecond=0),
            end_period.replace(hour=23, minute=59, second=59, microsecond=999999),
        )
    if window == "1mes":
        reference = now - relativedelta(months=max(page, 0))
        start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, (start + relativedelta(months=1)) - timedelta(microseconds=1)
    raise ValueError(f"Ventana de historico invalida: {window}")


def _as_datetime(value):
    return value if isinstance(value, datetime) else timebox.parse(value, legacy=True)
