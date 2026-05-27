import threading
from queue import Queue
from typing import Any

import dash
import dash_daq as daq
from dash import dcc, html
from dash.dependencies import Input, Output

import config
from src.utils import timebox


message_queue: Queue | None = None
mqtt_client_manager = None
_auto_start_enabled = True


def get_broker_layout():
    initial_toggle = True
    return html.Div(
        children=[
            html.H1("broker mqtt", className="main-title"),
            html.Div(
                className="broker-command-bar",
                children=[
                    html.Div(
                        className="broker-command-main",
                        children=[
                            daq.BooleanSwitch(
                                id="broker-connection-toggle",
                                label="conectar al broker",
                                labelPosition="right",
                                on=initial_toggle,
                            ),
                            html.Div(id="broker-status-pill", className="broker-status-pill broker-status-unknown"),
                        ],
                    ),
                    html.Div(
                        className="broker-command-note",
                        children="observacion local del trafico mqtt de panelexemys",
                    ),
                ],
            ),
            html.Div(id="broker-dashboard-content", className="broker-dashboard"),
            dcc.Interval(
                id="broker-status-interval",
                interval=config.DASH_REFRESH_SECONDS,
                n_intervals=0,
            ),
        ]
    )


def initialize_broker_components(manager, queue, auto_start=True):
    global mqtt_client_manager, message_queue, _auto_start_enabled
    mqtt_client_manager = manager
    message_queue = queue
    _auto_start_enabled = bool(auto_start)

    if mqtt_client_manager is not None:
        mqtt_client_manager.set_message_queue(message_queue)


def register_broker_callbacks(app: dash.Dash):
    @app.callback(
        Output("broker-status-pill", "children"),
        Output("broker-status-pill", "className"),
        Output("broker-dashboard-content", "children"),
        Input("broker-status-interval", "n_intervals"),
        Input("broker-connection-toggle", "on"),
    )
    def update_broker_dashboard(_n_intervals: int, toggle_on: bool):
        if mqtt_client_manager is None:
            return (
                "sin manager mqtt",
                "broker-status-pill broker-status-offline",
                _render_error("manager mqtt no inicializado"),
            )

        if not toggle_on:
            status = _connection_status()
            if status != "desconectado":
                mqtt_client_manager.stop()
            status = "desconectado"
        else:
            status = _ensure_connected()

        snapshot = mqtt_client_manager.get_traffic_snapshot()
        return (
            _status_text(status),
            _status_class(status),
            _render_dashboard(snapshot, status),
        )


def _ensure_connected() -> str:
    if not _auto_start_enabled:
        return _connection_status()
    status = _connection_status()
    if status == "desconectado":
        threading.Thread(target=mqtt_client_manager.start, daemon=True).start()
        return "conectando"
    return status


def _connection_status() -> str:
    return mqtt_client_manager.get_connection_status()


def _render_dashboard(snapshot: dict[str, Any], status: str):
    totals = snapshot["totals"]
    return [
        html.Div(
            className="broker-kpi-grid",
            children=[
                _kpi("estado cliente", status),
                _kpi("publicaciones", _format_int(totals["published_count"])),
                _kpi("bytes publicados", _format_bytes(totals["published_bytes"])),
                _kpi("recepciones", _format_int(totals["received_count"])),
                _kpi("bytes recibidos", _format_bytes(totals["received_bytes"])),
                _kpi("topicos activos", _format_int(len(snapshot["active_topics"]))),
            ],
        ),
        html.Div(
            className="broker-main-grid",
            children=[
                html.Section(
                    className="broker-panel broker-panel-wide",
                    children=[
                        html.H2("topicos activos", className="broker-panel-title"),
                        _topic_cloud(snapshot["active_topics"]),
                    ],
                ),
                html.Section(
                    className="broker-panel",
                    children=[
                        html.H2("publicadores locales", className="broker-panel-title"),
                        _publishers(snapshot["publishers"]),
                    ],
                ),
                html.Section(
                    className="broker-panel",
                    children=[
                        html.H2("suscriptores locales", className="broker-panel-title"),
                        _subscribers(snapshot["subscriptions"], snapshot["listeners"]),
                    ],
                ),
                _ranking_panel(
                    "ranking por cantidad publicada",
                    snapshot["rank_publicaciones"],
                    "published_count",
                    "publicaciones",
                ),
                _ranking_panel(
                    "ranking por payload acumulado",
                    snapshot["rank_payload_acumulado"],
                    "published_bytes",
                    "bytes",
                    byte_value=True,
                ),
                _ranking_panel(
                    "ranking por payload maximo",
                    snapshot["rank_payload_maximo"],
                    "published_max_bytes",
                    "maximo",
                    byte_value=True,
                ),
                _ranking_panel(
                    "ranking por recepciones",
                    snapshot["rank_recepciones"],
                    "received_count",
                    "recepciones",
                ),
                html.Section(
                    className="broker-panel broker-panel-wide",
                    children=[
                        html.H2("seguimiento reciente", className="broker-panel-title"),
                        _recent_events(snapshot["recent"]),
                    ],
                ),
            ],
        ),
    ]


def _render_error(message: str):
    return html.Div(className="broker-panel broker-error", children=message)


def _kpi(label: str, value: str):
    return html.Div(
        className="broker-kpi",
        children=[
            html.Div(label, className="broker-kpi-label"),
            html.Div(value, className="broker-kpi-value"),
        ],
    )


def _topic_cloud(topics: list[str]):
    if not topics:
        return html.Div("sin topicos observados", className="broker-empty")
    return html.Div(
        className="broker-topic-cloud",
        children=[html.Code(topic, className="broker-topic-chip") for topic in topics[:48]],
    )


def _publishers(items: list[dict[str, Any]]):
    rows = [
        [item["source"], _format_int(item["published_count"]), _format_bytes(item["published_bytes"]), _format_ts(item["last_publish_ts"])]
        for item in items[:12]
    ]
    return _table(["publicador", "cantidad", "bytes", "ultimo"], rows)


def _subscribers(subscriptions: list[dict[str, Any]], listeners: list[dict[str, Any]]):
    rows = []
    for item in subscriptions:
        rows.append([item["source"], "suscripcion", item["topic"], f"qos {item['qos']}"])
    for item in listeners:
        rows.append([item["source"], "listener", item["prefix"], "prefijo local"])
    return _table(["origen", "tipo", "topico", "detalle"], rows[:16])


def _ranking_panel(title: str, items: list[dict[str, Any]], key: str, label: str, byte_value: bool = False):
    rows = []
    for item in items[:10]:
        raw_value = item[key]
        value = _format_bytes(raw_value) if byte_value else _format_int(raw_value)
        rows.append([item["topic"], value])
    return html.Section(
        className="broker-panel",
        children=[
            html.H2(title, className="broker-panel-title"),
            _table(["topico", label], rows),
        ],
    )


def _recent_events(items: list[dict[str, Any]]):
    rows = []
    for item in items[:14]:
        qos = "-" if item["qos"] is None else f"qos {item['qos']}"
        retain = "-" if item["retain"] is None else ("retain" if item["retain"] else "no retain")
        rows.append(
            [
                _format_ts(item["ts"]),
                item["direction"],
                item["source"],
                item["topic"],
                _format_bytes(item["bytes"]),
                qos,
                retain,
            ]
        )
    return _table(["ts", "sentido", "origen", "topico", "bytes", "qos", "retain"], rows)


def _format_ts(value: Any) -> str:
    if not value:
        return "-"
    return timebox.format_local(value)


def _table(headers: list[str], rows: list[list[Any]]):
    if not rows:
        return html.Div("sin datos en memoria", className="broker-empty")
    return html.Div(
        className="broker-table-wrap",
        children=html.Table(
            className="broker-table",
            children=[
                html.Thead(html.Tr([html.Th(header) for header in headers])),
                html.Tbody(
                    [
                        html.Tr([html.Td(value) for value in row])
                        for row in rows
                    ]
                ),
            ],
        ),
    )


def _format_bytes(value: int) -> str:
    amount = float(value)
    units = ("B", "KB", "MB", "GB")
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    if unit == "B":
        return f"{int(amount)} {unit}"
    return f"{amount:.1f} {unit}"


def _format_int(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _status_text(status: str) -> str:
    if status == "conectado":
        return "conectado"
    if status == "conectando":
        return "conectando"
    return "desconectado"


def _status_class(status: str) -> str:
    if status == "conectado":
        return "broker-status-pill broker-status-online"
    if status == "conectando":
        return "broker-status-pill broker-status-waiting"
    return "broker-status-pill broker-status-offline"
