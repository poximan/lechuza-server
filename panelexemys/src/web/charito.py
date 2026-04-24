from __future__ import annotations

import re
from typing import Any, Dict, List

import dash
from dash import dcc, html
from dash.dependencies import Input, Output

import config
from src.utils import timebox
from src.web.clients.charito_client import CharitoClient

IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
STALE_THRESHOLD_SECONDS = int(config.CHARITO_STALE_THRESHOLD_SECONDS)


def get_charito_layout() -> html.Div:
    return html.Div(
        children=[
            html.H1("charo-daemon", className="main-title"),
            html.Div(id="charito-last-update", className="info-message"),
            html.Div(id="charito-grid", className="charito-grid"),
            dcc.Interval(id="charito-interval", interval=config.DASH_REFRESH_SECONDS, n_intervals=0),
        ],
    )


def register_charito_callbacks(app: dash.Dash) -> None:
    client = CharitoClient(config.CHARITO_API_BASE)

    @app.callback(
        Output("charito-grid", "children"),
        Output("charito-last-update", "children"),
        Input("charito-interval", "n_intervals"),
    )
    def update_charito_cards(_: int):
        try:
            snapshot = client.get_state()
            items = snapshot.get("items", []) if isinstance(snapshot, dict) else []
        except Exception as exc:
            return _error_card(str(exc)), "Fallo actualizando charo-daemon"

        if not items:
            return _placeholder_card("Sin datos recibidos"), "Sin datos"

        cards = [_build_card(item) for item in items]
        last_ts = snapshot.get("ts")
        label = f"Actualizado: {_format_ts(last_ts)}"
        return cards, label


def _placeholder_card(message: str) -> List[html.Div]:
    return [
        html.Div(
            className="charito-card charito-card-placeholder",
            children=html.Div(message, className="charito-placeholder-text"),
        )
    ]


def _error_card(message: str) -> List[html.Div]:
    return [
        html.Div(
            className="charito-card charito-card-placeholder",
            children=html.Div(f"Error: {message}", className="charito-placeholder-text"),
        )
    ]


def _build_card(item: Dict[str, Any]) -> html.Div:
    alias = item.get("alias") or ""
    instance_id = item.get("instanceId") or alias or "sin-id"
    status_raw = (item.get("status") or "unknown").lower()
    data_status = str(item.get("dataStatus") or "").strip().lower()
    data_error = str(item.get("dataError") or "").strip()
    status_label = {"online": "Online", "offline": "Offline"}.get(status_raw, "Desconocido")
    if status_raw == "online" and data_status == "no_useful_metrics":
        status_label = "Online sin metricas"

    card_cls = ["charito-card"]
    status_cls = "charito-status-pill"
    if status_raw == "offline":
        card_cls.append("charito-card-stale")
        status_cls += " charito-status-pill--offline"

    cpu_value = _ratio(item.get("cpuLoad"))
    mem_value = _ratio(item.get("memoryUsageRatio"))
    cpu_label = _format_percent(item.get("cpuLoad"))
    mem_label = _format_percent(item.get("memoryUsageRatio"))
    latest_temp = _format_number(item.get("cpuTemperatureCelsius"))

    updated_at = _format_ts(item.get("receivedAt") or item.get("generatedAt"))
    samples = _format_samples(item.get("samples"))
    window_seconds = item.get("windowSeconds")
    window_label = f"Ventana {window_seconds}s" if window_seconds else "Ventana N/D"

    title_children = [
        html.Div(instance_id, className="charito-card-title"),
        html.Div(f"Actualizado: {updated_at}", className="charito-card-subtitle"),
    ]
    if alias and alias != instance_id:
        title_children.append(html.Div(alias, className="charito-card-alias"))
    title_children.append(html.Div(f"{samples} | {window_label}", className="charito-card-subtitle"))
    if status_raw == "online" and data_status == "no_useful_metrics":
        issue_label = "Metricas no disponibles"
        if data_error:
            issue_label = f"{issue_label}: {data_error}"
        title_children.append(html.Div(issue_label, className="charito-card-subtitle"))

    header = html.Div(
        className="charito-card-header",
        children=[
            html.Div(className="charito-card-title-block", children=title_children),
            html.Div(
                className=status_cls,
                children=[
                    html.Span(className=f"charito-status-dot charito-status-dot--{status_raw}"),
                    html.Span(f"{status_label}", className="charito-status-text"),
                ],
            ),
        ],
    )

    metrics_section = html.Div(
        className="charito-progress-section",
        children=[
            _progress_block("CPU", cpu_label, cpu_value, "cpu"),
            _progress_block("MEM", mem_label, mem_value, "mem"),
        ],
    )

    temp_section = html.Div(
        className="charito-metric",
        children=[
            html.Div("Temp CPU", className="charito-metric-label"),
            html.Div(f"{latest_temp} C", className="charito-metric-value"),
        ],
    )

    network_section = _build_network_section(item)
    process_section = _build_process_section(item)

    return html.Div(
        className=" ".join(card_cls),
        children=[header, metrics_section, temp_section, network_section, process_section],
    )


def _build_process_section(item: Dict[str, Any]) -> html.Div:
    processes = _extract_processes(item)
    children: List[Any] = [html.Div("Procesos monitoreados", className="charito-section-title")]
    if not processes:
        children.append(html.Div("Sin datos de procesos", className="charito-process-empty"))
        return html.Div(children, className="charito-section")

    tiles = []
    for proc in processes:
        label, cls = _process_visuals(proc["state"])
        tiles.append(
            html.Div(
                className="charito-process-item",
                children=html.Div(
                    [
                        html.Div(proc["name"], className="charito-process-title"),
                        html.Div(label, className="charito-process-state"),
                    ],
                    className=f"charito-process-tile {cls}",
                ),
            )
        )
    children.append(html.Div(tiles, className="charito-process-row"))
    return html.Div(children, className="charito-section")


def _build_network_section(item: Dict[str, Any]) -> html.Div:
    interfaces = _extract_interfaces(item)
    children: List[Any] = [html.Div("Interfaces de red", className="charito-section-title")]
    if not interfaces:
        children.append(html.Div("Sin interfaces IPv4 visibles", className="charito-network-empty"))
        return html.Div(children, className="charito-section")

    tiles = []
    for iface in interfaces:
        status_text = "activa" if iface["up"] else "inactiva"
        name_parts = [iface["label"]]
        if iface["virtual"]:
            name_parts.append("(virtual)")
        tiles.append(
            html.Div(
                className=f"charito-network-chip {'charito-network-chip--up' if iface['up'] else 'charito-network-chip--down'}",
                children=[
                    html.Div(" ".join(name_parts), className="charito-network-name"),
                    html.Div(f"Estado: {status_text}", className="charito-network-status"),
                    html.Div(iface["ip"], className="charito-network-ip"),
                ],
            )
        )
    children.append(html.Div(tiles, className="charito-network-list"))
    return html.Div(children, className="charito-section")


def _extract_interfaces(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    sample = item.get("latestSample") or {}
    raw = sample.get("networkInterfaces") or item.get("networkInterfaces") or []
    result: List[Dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ipv4 = _pick_ipv4(entry.get("addresses") or [])
        if not ipv4:
            continue
        label = entry.get("displayName") or entry.get("name") or "Interface"
        result.append(
            {
                "label": label,
                "ip": ipv4,
                "up": bool(entry.get("up")),
                "virtual": bool(entry.get("virtual")),
            }
        )
    return result


def _pick_ipv4(addresses: Any) -> str:
    if not isinstance(addresses, list):
        return ""
    for item in addresses:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address") or "").strip()
        if not address or not IPV4_RE.match(address):
            continue
        netmask = str(item.get("netmask") or "").strip()
        if netmask and IPV4_RE.match(netmask):
            return f"{address} / {netmask}"
        return address
    return ""


def _extract_processes(item: Dict[str, Any]) -> List[Dict[str, str]]:
    sample = item.get("latestSample") or {}
    processes = sample.get("watchedProcesses") or item.get("watchedProcesses") or []
    result: List[Dict[str, str]] = []
    for proc in processes:
        if not isinstance(proc, dict):
            continue
        name = proc.get("processName") or proc.get("name") or "N/D"
        running = proc.get("running")
        if running is True:
            state = "ok"
        elif running is False:
            state = "down"
        else:
            state = "unknown"
        result.append({"name": name, "state": state})
    return result


def _process_visuals(state: str) -> Any:
    if state == "ok":
        return "activo", "charito-process-tile--ok"
    if state == "down":
        return "detenido", "charito-process-tile--down"
    return "!datos", "charito-process-tile--unknown"


def _format_percent(value: Any) -> str:
    try:
        number = float(value)
        if number < 0:
            return "N/D"
        return f"{number * 100:.1f}%"
    except Exception:
        return "N/D"


def _format_number(value: Any) -> str:
    try:
        number = float(value)
        if number < 0:
            return "N/D"
        return f"{number:.1f}"
    except Exception:
        return "N/D"


def _format_samples(value: Any) -> str:
    try:
        number = int(value)
        if number == 1:
            return "1 muestra"
        if number >= 0:
            return f"{number} muestras"
        return "N/D muestras"
    except Exception:
        return "N/D muestras"


def _format_ts(value: Any) -> str:
    if not value:
        return "N/D"
    try:
        return timebox.format_local(value)
    except Exception:
        return str(value)


def _ratio(value: Any) -> float:
    try:
        number = float(value)
        if number < 0:
            return 0.0
        if number <= 1.0:
            return number * 100.0
        return min(number, 100.0)
    except Exception:
        return 0.0


def _progress_block(title: str, value_text: str, percent: float, variant: str) -> html.Div:
    safe_percent = max(0.0, min(percent, 100.0))
    return html.Div(
        className=f"charito-progress-block charito-progress-block--{variant}",
        children=[
            html.Div(title, className="charito-metric-label"),
            html.Div(value_text, className="charito-metric-value"),
            html.Div(
                className="charito-progress-bar",
                children=html.Div(
                    className="charito-progress-fill",
                    style={"width": f"{safe_percent:.1f}%"},
                ),
            ),
        ],
    )
