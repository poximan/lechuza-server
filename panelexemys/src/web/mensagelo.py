from __future__ import annotations

import dash
from dash import dcc, html
from dash.dependencies import Input, Output

import config
from src.servicios.email.mensagelo_attempt_log import get_mensagelo_attempts
from src.utils import timebox


def get_mensagelo_layout() -> html.Div:
    return html.Div(
        children=[
            html.H1("mensagelo", className="main-title"),
            html.Div(
                className="kpi-item",
                children=[
                    html.H2("Ultimos intentos de envio", className="sub-title"),
                    html.Div(id="mensagelo-attempts-table"),
                    dcc.Interval(
                        id="mensagelo-attempts-interval",
                        interval=config.DASH_REFRESH_SECONDS,
                        n_intervals=0,
                    ),
                ],
            ),
        ]
    )


def register_mensagelo_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("mensagelo-attempts-table", "children"),
        Input("mensagelo-attempts-interval", "n_intervals"),
    )
    def update_mensagelo_attempts(_n_intervals: int):
        attempts = get_mensagelo_attempts()
        if not attempts:
            return html.Div(
                "Sin intentos registrados desde el ultimo reinicio.",
                className="disconnected-table-empty-message",
            )

        rows = []
        for item in attempts:
            try:
                ts = timebox.format_local(timebox.parse(item.get("ts"), legacy=True), legacy=True)
            except Exception:
                ts = item.get("ts", "")
            rows.append(
                html.Tr(
                    children=[
                        html.Td(ts, className="disconnected-table-data-cell"),
                        html.Td(
                            "si" if item.get("ok") else "no",
                            className="disconnected-table-data-cell",
                        ),
                        html.Td(", ".join(item.get("recipients", [])), className="disconnected-table-data-cell"),
                        html.Td(item.get("message_type", ""), className="disconnected-table-data-cell"),
                        html.Td(item.get("subject", ""), className="disconnected-table-data-cell"),
                        html.Td(
                            item.get("body", ""),
                            className="disconnected-table-data-cell",
                            style={"whiteSpace": "pre-wrap", "minWidth": "240px"},
                        ),
                        html.Td(
                            item.get("detail", ""),
                            className="disconnected-table-data-cell",
                            style={"whiteSpace": "pre-wrap", "minWidth": "180px"},
                        ),
                    ]
                )
            )

        return html.Div(
            className="disconnected-table-wrapper",
            children=[
                html.Table(
                    className="disconnected-table",
                    children=[
                        html.Thead(
                            html.Tr(
                                children=[
                                    html.Th("Fecha", className="disconnected-table-header-cell"),
                                    html.Th("Exito", className="disconnected-table-header-cell"),
                                    html.Th("Destinatarios", className="disconnected-table-header-cell"),
                                    html.Th("Tipo", className="disconnected-table-header-cell"),
                                    html.Th("Asunto", className="disconnected-table-header-cell"),
                                    html.Th("Mensaje", className="disconnected-table-header-cell"),
                                    html.Th("Detalle", className="disconnected-table-header-cell"),
                                ]
                            )
                        ),
                        html.Tbody(rows),
                    ],
                )
            ],
        )
