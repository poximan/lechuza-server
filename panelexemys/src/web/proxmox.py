import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import dash_daq as daq
import plotly.graph_objects as go
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from src.web.clients.proxmox_client import ProxmoxClient
from src.utils.paths import (
    load_proxmox_view_preference,
    update_proxmox_view_preference,
)
import config
from src.utils import timebox


_LAST_PROXMOX_SIGNATURE: str | None = None


def _view_pref_to_bool(pref: str) -> bool:
    return pref == "historico"


def _bool_to_view_pref(value: bool) -> str:
    return "historico" if value else "vivo"


def _default_view_preference() -> str:
    return "historico"
def _build_placeholder_card(message: str) -> html.Div:
    return html.Div(
        className="proxmox-card proxmox-card-placeholder",
        children=[
            html.Div(message, className="proxmox-card-placeholder-text"),
        ],
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_pct(value: Any) -> float:
    pct = _safe_float(value)
    if pct < 0:
        return 0.0
    if pct > 100:
        return 100.0
    return pct


def _format_pct(value: Any) -> str:
    try:
        if value is None:
            return "N/D"
        return f"{float(value):.2f}%"
    except Exception:
        return "N/D"


def _status_colors(status: Any) -> Dict[str, str]:
    normalized = str(status or "").strip().lower()
    if normalized == "running":
        return {"dot": "#27ae60", "text": "#1d7d46"}
    if normalized == "stopped":
        return {"dot": "#e74c3c", "text": "#a83223"}
    return {"dot": "#95a5a6", "text": "#566573"}


def _usage_fill_color(pct: float | None) -> str:
    if pct is None:
        return "#bdc3c7"
    if pct >= 85:
        return "#e74c3c"
    if pct >= 70:
        return "#f39c12"
    return "#2ecc71"


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return timebox.parse(value, legacy=True)
    except Exception:
        return None


def _format_local_timestamp(value: Any) -> str:
    if not value:
        return "N/D"
    try:
        return timebox.format_local(value, legacy=True)
    except Exception:
        return "N/D"


def _relative_time(value: Any) -> str:
    dt = _parse_timestamp(value)
    if dt is None:
        return ""
    now = timebox.utc_now()
    delta = now - dt
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return f"hace {seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"hace {minutes}m"
    hours = minutes // 60
    if hours < 24:
        remaining_minutes = minutes % 60
        return f"hace {hours}h {remaining_minutes}m"
    days = hours // 24
    return f"hace {days}d"


def _format_last_update_text(ts: Any) -> str:
    local_ts = _format_local_timestamp(ts)
    return f"Ultima actualizacion: {local_ts}"




def _format_capacity(used: Any, total: Any) -> str:
    used_val = _safe_float(used)
    total_val = _safe_float(total)
    if total_val <= 0:
        return "N/D"
    return f"{used_val:.1f} / {total_val:.1f} GB"


def _format_disk_total(total: Any) -> str:
    total_val = _safe_float(total)
    if total_val <= 0:
        return "Disco asignado: N/D"
    return f"Disco asignado: {total_val:.1f} GB"


def _format_rate_per_second(value: Any) -> str:
    rate = _safe_float(value)
    if rate <= 0:
        return "0 KB/s"

    units = ["B/s", "KB/s", "MB/s", "GB/s", "TB/s"]
    idx = 0
    while rate >= 1024 and idx < len(units) - 1:
        rate /= 1024.0
        idx += 1

    return f"{rate:.1f} {units[idx]}"



def _format_bytes(value: Any) -> str:
    total = _safe_float(value)
    if total <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while total >= 1024 and idx < len(units) - 1:
        total /= 1024.0
        idx += 1
    return f"{total:.1f} {units[idx]}"
def _build_disk_section(disk_total: Any, disk_read_bytes: Any, disk_write_bytes: Any) -> html.Div:
    return html.Div(
        className="proxmox-disk-section",
        children=[
            html.Div(
                _format_disk_total(disk_total),
                className="proxmox-disk-total",
            ),
            html.Div(
                className="proxmox-disk-io",
                children=[
                    html.Div(
                        className="proxmox-disk-io-item",
                        children=[
                            html.Span("Lectura ", className="proxmox-disk-io-label"),
                            html.Span(
                                _format_bytes(disk_read_bytes),
                                className="proxmox-disk-io-value",
                            ),
                        ],
                    ),
                    html.Div(
                        className="proxmox-disk-io-item",
                        children=[
                            html.Span("Escritura ", className="proxmox-disk-io-label"),
                            html.Span(
                                _format_bytes(disk_write_bytes),
                                className="proxmox-disk-io-value",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


_HISTORY_METRICS = [
    ("cpu_pct", "CPU uso", "#2980b9", "rgba(41, 128, 185, 0.25)"),
    ("mem_pct", "Memoria", "#8e44ad", "rgba(142, 68, 173, 0.25)"),
]


def _parse_history_series(history: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    if not isinstance(history, dict):
        return points
    raw_series = history.get(key, [])
    if not isinstance(raw_series, list):
        return points
    for item in raw_series:
        if not isinstance(item, dict):
            continue
        ts_raw = item.get("ts")
        value_raw = item.get("value")
        if ts_raw is None or value_raw is None:
            continue
        dt = _parse_timestamp(ts_raw)
        if dt is None:
            continue
        try:
            value = float(value_raw)
        except Exception:
            continue
        points.append({"dt": dt, "value": value})
    points.sort(key=lambda entry: entry["dt"])
    return points


def _build_history_chart(
    vmid: Any,
    metric_key: str,
    label: str,
    color: str,
    fill_color: str,
    history: Dict[str, Any],
    subtitle: str | None = None,
) -> html.Div:
    series = _parse_history_series(history, metric_key)
    fig = go.Figure()

    if series:
        x_values = []
        for point in series:
            try:
                local_dt = timebox.to_local(point["dt"])
                x_values.append(local_dt.isoformat())
            except Exception:
                x_values.append(point["dt"].isoformat())
        y_values = [point["value"] for point in series]
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                line={"color": color, "width": 2},
                fill="tozeroy",
                fillcolor=fill_color,
                hovertemplate="%{y:.2f}%<br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
            )
        )
        fig.update_yaxes(range=[0, 100])
    else:
        fig.add_annotation(
            text="Sin datos",
            showarrow=False,
            font={"color": "#95a5a6"},
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
        )
        fig.update_yaxes(range=[0, 100])

    fig.update_layout(
        margin=dict(l=0, r=4, t=8, b=36),
        height=220,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            tickformat="%Y-%m-%d %H:%M",
            color="#7f8c8d",
            tickfont=dict(size=11),
        ),
        yaxis=dict(showgrid=False, color="#7f8c8d"),
        uirevision=f"vm-{vmid}-{metric_key}",
    )

    graph_id = {"type": "proxmox-history-graph", "key": f"{vmid}-{metric_key}"}
    return html.Div(
        className="proxmox-history-chart",
        children=[
            html.Div(
                [
                    html.Span(label, className="proxmox-history-label"),
                    html.Span(subtitle or "", className="proxmox-history-subtitle"),
                ],
                className="proxmox-history-title",
            ),
            dcc.Graph(
                id=graph_id,
                figure=fig,
                className="proxmox-history-figure",
                config={"displayModeBar": False, "responsive": True},
            ),
        ],
    )


def _build_placeholder_cards(count: int = 3, message: str = "Cargando datos de Proxmox...") -> List[html.Div]:
    return [_build_placeholder_card(message) for _ in range(max(1, count))]


def _build_history_cards(vms: List[Dict[str, Any]], history_meta: Dict[str, Any]) -> List[html.Div]:
    cards: List[html.Div] = []
    for vm in sorted(vms, key=lambda item: item.get("vmid", 0)):
        name = vm.get("name", "N/D")
        vmid = vm.get("vmid", "N/D")
        status_raw = vm.get("status", "desconocido")
        status_text = str(status_raw).upper()
        status_colors = _status_colors(status_raw)
        uptime = vm.get("uptime_human", "0m")
        cpus = vm.get("cpus", "N/D")
        mem_used = vm.get("mem_used_gb")
        mem_total = vm.get("mem_total_gb")
        disk_total = vm.get("disk_total_gb")
        disk_read_bytes = vm.get("disk_read_bytes")
        disk_write_bytes = vm.get("disk_write_bytes")
        warning = vm.get("status_detail_error")
        history_payload = vm.get("history") or {}
        meta_text = f"vCPUs: {cpus} - Uptime: {uptime}"

        charts = []
        for key, label, color, fill in _HISTORY_METRICS:
            subtitle = ""
            if key == "mem_pct":
                subtitle = _format_capacity(mem_used, mem_total)
            charts.append(
                _build_history_chart(
                    vmid,
                    key,
                    label,
                    color,
                    fill,
                    history_payload,
                    subtitle=subtitle,
                )
            )

        cards.append(
            html.Div(
                className="proxmox-card proxmox-card-history",
                children=[
                    html.Div(
                        className="proxmox-card-header",
                        children=[
                            html.Div(
                                className="proxmox-card-title",
                                children=[
                                    html.Span(f"VM {vmid}", className="proxmox-card-vmid"),
                                    html.Div(
                                        className="proxmox-card-name-container",
                                        children=[
                                            html.Span(name, className="proxmox-card-name"),
                                            html.Span(
                                                meta_text,
                                                className="proxmox-card-subtitle",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="proxmox-status-wrapper",
                                children=[
                                    html.Span(
                                        status_text,
                                        className="proxmox-card-status",
                                        style={"color": status_colors["text"]},
                                    ),
                                    html.Div(
                                        className="proxmox-status-dot",
                                        style={"backgroundColor": status_colors["dot"]},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="proxmox-card-body proxmox-card-body-history",
                        children=[
                            html.Div(
                                className="proxmox-history-grid",
                                children=charts,
                            ),
                            _build_disk_section(disk_total, disk_read_bytes, disk_write_bytes),
                        ],
                    ),
                    (
                        html.Div(
                            warning,
                            className="proxmox-metric-warning",
                        )
                        if warning
                        else None
                    ),
                ],
            )
        )
    return cards


def _build_classic_cards(vms: List[Dict[str, Any]]) -> List[html.Div]:
    cards: List[html.Div] = []
    for vm in sorted(vms, key=lambda item: item.get("vmid", 0)):
        name = vm.get("name", "N/D")
        vmid = vm.get("vmid", "N/D")
        status_raw = vm.get("status", "desconocido")
        status_text = str(status_raw).upper()
        status_colors = _status_colors(status_raw)
        uptime = vm.get("uptime_human", "0m")
        # pve-service provides 'cpu_pct' (0..100); keep backward compatibility
        cpu_value_raw = vm.get("cpu_usage_pct") if vm.get("cpu_usage_pct") is not None else vm.get("cpu_pct")
        cpu_pct_value = _clamp_pct(cpu_value_raw)
        cpu_pct_display = _format_pct(cpu_value_raw)
        warning = vm.get("status_detail_error")
        cpus = vm.get("cpus", "N/D")
        mem_used = vm.get("mem_used_gb")
        mem_total = vm.get("mem_total_gb")
        disk_total = vm.get("disk_total_gb")
        disk_read_bytes = vm.get("disk_read_bytes")
        disk_write_bytes = vm.get("disk_write_bytes")
        meta_text = f"vCPUs: {cpus} - Uptime: {uptime}"

        gauge_value = max(0, min(100, cpu_pct_value))

        cards.append(
            html.Div(
                className="proxmox-card proxmox-card-classic",
                children=[
                    html.Div(
                        className="proxmox-card-header",
                        children=[
                            html.Div(
                                className="proxmox-card-title",
                                children=[
                                    html.Span(f"VM {vmid}", className="proxmox-card-vmid"),
                                    html.Div(
                                        className="proxmox-card-name-container",
                                        children=[
                                            html.Span(name, className="proxmox-card-name"),
                                            html.Span(
                                                meta_text,
                                                className="proxmox-card-subtitle",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="proxmox-status-wrapper",
                                children=[
                                    html.Span(
                                        status_text,
                                        className="proxmox-card-status",
                                        style={"color": status_colors["text"]},
                                    ),
                                    html.Div(
                                        className="proxmox-status-dot",
                                        style={"backgroundColor": status_colors["dot"]},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="proxmox-card-body",
                        children=[
                            html.Div(
                                className="proxmox-gauge-container",
                                children=[
                                    daq.Gauge(
                                        id=f"proxmox-gauge-{vmid}",
                                        min=0,
                                        max=100,
                                        value=gauge_value,
                                        color={"gradient": True, "ranges": {"green": [0, 70], "orange": [70, 85], "red": [85, 100]}},
                                        className="proxmox-gauge",
                                        label="CPU",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="proxmox-gauge-value",
                                children=[
                                    html.Span(cpu_pct_display, className="proxmox-gauge-number"),
                                ],
                            ),
                            html.Div(
                                className="proxmox-usage-section",
                                children=[
                                    html.Div(
                                        className="proxmox-usage-row",
                                        children=[
                                            html.Div(
                                                className="proxmox-usage-header",
                                                children=[
                                                    html.Span("CPU uso", className="proxmox-usage-label"),
                                                    html.Span(cpu_pct_display, className="proxmox-usage-value"),
                                                ],
                                            ),
                                            html.Div(
                                                className="proxmox-progress-track",
                                                children=[
                                                    html.Div(
                                                        className="proxmox-progress-fill",
                                                        style={"width": f"{gauge_value:.0f}%", "backgroundColor": _usage_fill_color(gauge_value)},
                                                    )
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="proxmox-usage-row",
                                        children=[
                                            html.Div(
                                                className="proxmox-usage-header",
                                                children=[
                                                    html.Span("Memoria", className="proxmox-usage-label"),
                                                    html.Span(_format_capacity(mem_used, mem_total), className="proxmox-usage-value"),
                                                ],
                                            ),
                                            html.Div(
                                                className="proxmox-progress-track",
                                                children=[
                                                    html.Div(
                                                        className="proxmox-progress-fill",
                                                        style={
                                                            "width": f"{_clamp_pct(((_safe_float(mem_used) / _safe_float(mem_total)) * 100.0) if _safe_float(mem_total) > 0 else 0)}%",
                                                            "backgroundColor": _usage_fill_color(((_safe_float(mem_used) / _safe_float(mem_total)) * 100.0) if _safe_float(mem_total) > 0 else 0),
                                                        },
                                                    )
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            _build_disk_section(disk_total, disk_read_bytes, disk_write_bytes),
                        ],
                    ),
                    (
                        html.Div(
                            warning,
                            className="proxmox-metric-warning",
                        )
                        if warning
                        else None
                    ),
                ],
            )
        )

    return cards

def _latest_history_timestamp(history_map: Dict[int, Dict[str, Any]]) -> Optional[str]:
    latest_dt: Optional[datetime] = None
    for info in history_map.values():
        history = info.get("history") if isinstance(info, dict) else None
        if not isinstance(history, dict):
            continue
        for series in history.values():
            if not isinstance(series, list):
                continue
            for point in series:
                if not isinstance(point, dict):
                    continue
                ts = point.get("ts")
                dt = _parse_timestamp(ts)
                if dt is None:
                    continue
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
    if latest_dt is None:
        return None
    return timebox.utc_iso(latest_dt)




def _render_proxmox_snapshot(view_toggle_value: Any, logger: Optional[Any] = None):
    client = ProxmoxClient(config.PVE_API_BASE)

    selected_view = "history" if _view_pref_to_bool(_default_view_preference()) else "classic"
    if isinstance(view_toggle_value, bool):
        selected_view = "history" if view_toggle_value else "classic"
    elif isinstance(view_toggle_value, str):
        normalized_view = view_toggle_value.lower()
        if normalized_view in {"history", "historico"}:
            selected_view = "history"
        elif normalized_view in {"classic", "vivo"}:
            selected_view = "classic"
    if selected_view not in {"history", "classic"}:
        selected_view = "history"

    try:
        prox = client.get_state()
    except Exception as exc:
        prox = {
            "ts": None,
            "vms": [],
            "missing": [],
            "error": str(exc),
        }

    ts = prox.get("ts") if isinstance(prox, dict) else None
    vms = prox.get("vms") if isinstance(prox, dict) else []
    missing = prox.get("missing") if isinstance(prox, dict) else []
    error = prox.get("error") if isinstance(prox, dict) else None

    history_map: Dict[str, Any] = {}
    history_meta: Dict[str, Any] = {}
    if selected_view == "history":
        try:
            hist = client.get_history()
            history_map = hist.get("vms", {}) if isinstance(hist, dict) else {}
            history_meta = hist.get("meta", {}) if isinstance(hist, dict) else {}
        except Exception:
            history_map, history_meta = {}, {}
    if not isinstance(vms, list):
        vms = []
    for vm in vms:
        if not isinstance(vm, dict):
            continue
        try:
            vmid_int = int(vm.get("vmid"))
        except Exception:
            continue
        # history_map keys may come as strings over HTTP JSON; try both
        history_payload = history_map.get(vmid_int) or history_map.get(str(vmid_int))
        if history_payload:
            vm["history"] = history_payload.get("history", {})
            if not vm.get("name") and history_payload.get("name"):
                vm["name"] = history_payload.get("name")

    history_only = False
    if not vms and history_map:
        history_only = True
        synthetic_vms: List[Dict[str, Any]] = []
        for vmid, info in history_map.items():
            synthetic_vms.append(
                {
                    "vmid": vmid,
                    "name": info.get("name") or f"VM {vmid}",
                    "status": "historico",
                    "status_display": "SIN DATOS RECIENTES",
                    "uptime_human": "N/D",
                    "cpus": "N/D",
                    "history": info.get("history") or {},
                }
            )
        vms = synthetic_vms
        if not ts:
            ts = _latest_history_timestamp(history_map)

    if history_only:
        selected_view = "history"

    if vms:
        if selected_view == "classic" and not history_only:
            cards = _build_classic_cards(vms)
        else:
            cards = _build_history_cards(vms, history_meta or {})
    else:
        cards = [
            _build_placeholder_card(
                "Sin datos disponibles. Esperando la primera actualizacion..."
            )
        ]

    last_update = _format_last_update_text(ts)

    if error:
        status_element = html.Div(
            "Hipervisor Proxmox no responde.",
            style={"color": "#c0392b", "fontWeight": "600"},
            title=str(error),
        )
    else:
        status_children: List[html.Div] = []
        if history_only:
            status_children.append(
                html.Div(
                    "Mostrando datos historicos (sin snapshot reciente).",
                    style={"color": "#e67e22", "fontWeight": "600"},
                )
            )
        else:
            status_children.append(
                html.Div(
                    "Hipervisor Proxmox en linea.",
                    style={"color": "#27ae60", "fontWeight": "600"},
                )
            )
        if missing:
            missing_str = ", ".join(str(m) for m in missing)
            status_children.append(
                html.Div(
                    f"VM sin datos en la ultima consulta: {missing_str}",
                    style={"color": "#e67e22"},
                )
            )
        status_element = html.Div(status_children)

    history_signature = _latest_history_timestamp(history_map) or ""
    signature = f"{selected_view}|{ts or history_signature or ''}|{history_signature}|{','.join(str(m) for m in sorted(missing)) if missing else ''}|{error or ''}"

    return cards, last_update, status_element, signature



def get_proxmox_layout() -> html.Div:
    poll_seconds = int(config.PVE_POLL_INTERVAL_SECONDS)
    refresh_ms = config.DASH_REFRESH_SECONDS

    pref = load_proxmox_view_preference(_default_view_preference())
    update_proxmox_view_preference(pref)
    toggle_history = _view_pref_to_bool(pref)

    global _LAST_PROXMOX_SIGNATURE
    _LAST_PROXMOX_SIGNATURE = None
    initial_cards = _build_placeholder_cards()
    initial_last_update = "Ultima actualizacion: N/D"
    initial_status = html.Div(
        "Cargando estado de Proxmox...",
        style={"color": "#7f8c8d", "fontWeight": "600"},
    )

    return html.Div(
        children=[
            dcc.Store(id="proxmox-zoom-state", data={"locked": False}),
            html.H1("Proxmox", className="main-title"),
            html.Div(
                id="proxmox-last-update",
                className="info-message",
                style={"textAlign": "center", "marginBottom": "12px"},
                children=initial_last_update,
            ),
            html.Div(
                id="proxmox-status-message",
                className="info-message",
                style={"textAlign": "center", "marginBottom": "16px"},
                children=initial_status,
            ),
            html.Div(
                className="proxmox-toolbar",
                children=[
                    html.Span("Vista", className="proxmox-toolbar-label"),
                    html.Div(
                        className="proxmox-toggle-wrapper",
                        children=[
                            html.Span("En vivo", className="proxmox-toggle-option"),
                            daq.ToggleSwitch(
                                id="proxmox-view-switch",
                                value=toggle_history,
                                persistence=True,
                                persistence_type="session",
                            ),
                            html.Span("Historico", className="proxmox-toggle-option"),
                        ],
                    ),
                ],
            ),
            html.Div(
                id="proxmox-cards",
                className="proxmox-grid",
                children=initial_cards,
            ),
            dcc.Interval(
                id="proxmox-interval-fast",
                interval=800,
                n_intervals=0,
                max_intervals=1,
            ),
            dcc.Interval(id="proxmox-interval", interval=refresh_ms, n_intervals=0),
        ]
    )


def register_proxmox_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("proxmox-zoom-state", "data"),
        Input({"type": "proxmox-history-graph", "key": ALL}, "relayoutData"),
        State("proxmox-zoom-state", "data"),
        prevent_initial_call=True,
    )
    def _sync_zoom_state(relayout_payloads, current_state):
        if not relayout_payloads:
            raise PreventUpdate
        current_state = current_state or {}
        locked = bool(current_state.get("locked"))
        new_locked = locked
        for payload in relayout_payloads:
            if not payload:
                continue
            if payload.get("xaxis.autorange"):
                new_locked = False
            elif any(key.startswith("xaxis.range") for key in payload.keys()):
                new_locked = True
        if new_locked == locked:
            raise PreventUpdate
        return {"locked": new_locked}

    @app.callback(
        Output("proxmox-cards", "children"),
        Output("proxmox-last-update", "children"),
        Output("proxmox-status-message", "children"),
        Input("proxmox-interval-fast", "n_intervals"),
        Input("proxmox-interval", "n_intervals"),
        Input("proxmox-view-switch", "value"),
        State("proxmox-zoom-state", "data"),
        prevent_initial_call=True,
    )
    def update_proxmox_cards(_n_fast: int, _n: int, view_toggle: Any, zoom_state: Dict[str, Any]):
        zoom_locked = bool((zoom_state or {}).get("locked"))
        if zoom_locked:
            return dash.no_update, dash.no_update, dash.no_update

        current_pref = load_proxmox_view_preference(_default_view_preference())
        desired_pref = current_pref

        if isinstance(view_toggle, bool):
            requested = _bool_to_view_pref(view_toggle)
            if requested != current_pref:
                update_proxmox_view_preference(requested)
                desired_pref = requested
        elif isinstance(view_toggle, str):
            normalized = view_toggle.strip().lower()
            if normalized in {"history", "historico"}:
                requested = "historico"
            elif normalized in {"classic", "vivo"}:
                requested = "vivo"
            else:
                requested = current_pref
            if requested != current_pref:
                update_proxmox_view_preference(requested)
                desired_pref = requested

        global _LAST_PROXMOX_SIGNATURE
        cards, last_update, status_element, signature = _render_proxmox_snapshot(
            _view_pref_to_bool(desired_pref), logger=app.logger
        )
        if _LAST_PROXMOX_SIGNATURE == signature:
            cards_output = dash.no_update
        else:
            _LAST_PROXMOX_SIGNATURE = signature
            cards_output = cards
        return cards_output, last_update, status_element










