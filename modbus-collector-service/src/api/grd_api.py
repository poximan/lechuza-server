from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Callable

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, HTTPException

from src import config
from src.bootstrap import ApplicationContext
from src.persistencia.dao.dao_historicos import historicos_dao
from src.utils import timebox


def create_grd_router(context: Callable[[], ApplicationContext]) -> APIRouter:
    router = APIRouter(prefix="/api/grd")

    @router.get("/descriptions")
    def get_descriptions() -> dict[str, Any]:
        return {"items": context().grd_service.descriptions()}

    @router.get("/summary")
    def get_summary() -> dict[str, Any]:
        return context().grd_service.summary()

    @router.get("/history")
    def get_history(grd_id: int, window: str = "1sem", page: int = 0) -> dict[str, Any]:
        return _history_payload(context(), grd_id, window, max(page, 0))

    @router.get("/outages")
    def get_outages(grd_id: int, limit: int = 10) -> dict[str, Any]:
        if limit <= 0:
            raise HTTPException(status_code=400, detail="limit debe ser mayor a 0")
        descriptions = context().grd_service.descriptions()
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

    return router


def _history_payload(
    context: ApplicationContext,
    grd_id: int,
    window: str,
    page: int,
) -> dict[str, Any]:
    descriptions = context.grd_service.descriptions()
    if grd_id not in descriptions:
        raise HTTPException(status_code=404, detail="GRD no encontrado")
    if window not in {"1sem", "1mes", "todo"}:
        raise HTTPException(status_code=400, detail="window debe ser 1sem, 1mes o todo")

    today = timebox.utc_today_iso()
    if window == "1sem":
        frame = historicos_dao.get_weekly_data_for_grd(grd_id, today, page)
        total_periods = historicos_dao.get_total_weeks_for_grd(grd_id, today)
        plot_start, plot_end = _compute_range(window, page)
    elif window == "1mes":
        frame = historicos_dao.get_monthly_data_for_grd(grd_id, today, page)
        total_periods = historicos_dao.get_total_months_for_grd(grd_id, today)
        plot_start, plot_end = _compute_range(window, page)
    else:
        frame, total_rows = historicos_dao.get_data_page_for_grd(
            grd_id,
            page,
            config.HISTORY_PAGE_SIZE,
        )
        total_periods = math.ceil(total_rows / config.HISTORY_PAGE_SIZE)
        if not frame.empty:
            first = frame["timestamp"].min()
            last = frame["timestamp"].max()
            plot_start = first.to_pydatetime() if hasattr(first, "to_pydatetime") else first
            plot_end = last.to_pydatetime() if hasattr(last, "to_pydatetime") else last
            if plot_end <= plot_start:
                plot_end = plot_start + timedelta(seconds=1)
        else:
            plot_start, plot_end = _compute_range("1mes", 0)

    connected_before = historicos_dao.get_connected_state_before_timestamp(grd_id, plot_start)
    return {
        "grd_id": grd_id,
        "description": descriptions[grd_id],
        "window": window,
        "page": page,
        "total_periods": total_periods,
        "page_size": config.HISTORY_PAGE_SIZE if window == "todo" else None,
        "range_start": timebox.utc_iso(plot_start),
        "range_end": timebox.utc_iso(plot_end),
        "connected_before": connected_before,
        "data": _frame_records(frame),
    }


def _frame_records(frame) -> list[dict]:
    if frame.empty:
        return []
    records = []
    for _, row in frame.iterrows():
        timestamp = row.get("timestamp")
        value = timestamp if isinstance(timestamp, datetime) else timestamp.to_pydatetime()
        records.append(
            {
                "timestamp": timebox.utc_iso(value),
                "conectado": int(row["conectado"]),
            }
        )
    return records


def _compute_range(window: str, page: int):
    now = timebox.utc_now()
    if window == "1sem":
        end_period = now - timedelta(weeks=max(page, 0))
        start_period = end_period - timedelta(days=6)
        range_end = (
            now
            if page == 0
            else end_period.replace(
                hour=23,
                minute=59,
                second=59,
                microsecond=999999,
            )
        )
        return (
            start_period.replace(hour=0, minute=0, second=0, microsecond=0),
            range_end,
        )
    if window == "1mes":
        reference = now - relativedelta(months=max(page, 0))
        start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (start + relativedelta(months=1)) - timedelta(microseconds=1)
        return start, now if page == 0 else month_end
    raise ValueError(f"Ventana de historico invalida: {window}")


def _as_datetime(value):
    return value if isinstance(value, datetime) else timebox.parse(value, legacy=True)
