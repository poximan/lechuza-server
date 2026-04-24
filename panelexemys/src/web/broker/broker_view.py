import os
import threading
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
from queue import Queue, Empty
import json
import config
import dash_daq as daq
from src.logger import logger
from src.utils import timebox
from src.utils.paths import load_observar_key, update_observar_key

message_queue: Queue | None = None
mqtt_client_manager = None
_auto_start_enabled = True

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(SCRIPT_DIR, 'estado_broker.txt')  # reservado si querés persistir algo


def get_broker_layout():
    status_interval_ms = config.DASH_REFRESH_SECONDS
    dash_interval_ms = config.DASH_REFRESH_SECONDS
    initial_toggle = bool(load_observar_key("broker_conectar", True))
    if initial_toggle:
        try:
            _ensure_connected()
        except Exception:
            pass

    return html.Div(children=[
        html.H1("Broker MQTT", className='main-title'),
        html.Div(
            className="broker-toggle-container",
            children=[
                daq.BooleanSwitch(
                    id='broker-connection-toggle',
                    label='Conectar al broker',
                    labelPosition='right',
                    on=initial_toggle,
                    style={'marginRight': '12px'}
                ),
                html.Div(id='broker-toggle-status', className='hidden-element')
            ]
        ),

        html.Div(className="status-indicator-wrapper", children=[
            html.Span("Estado de la conexión:"),
            html.Div(id='broker-status-indicator', className='status-circle status-disconnected')
        ]),

        html.Div(className='broker-grid-container', children=[
            html.Div(className='broker-panel', children=[
                html.H3("Publicaciones (snapshots retenidos)", className='text-xl font-semibold mb-4'),
                html.P("Publica snapshots con QoS/retain de acuerdo a config.py", className='text-gray-600 mb-4'),
                html.Div(className='flex flex-col space-y-4', children=[
                    html.Div(children=[
                        html.Div([
                            html.Strong("Grado global → "),
                            html.Code(config.MQTT_TOPIC_GRADO)
                        ], className='mb-1'),
                        dcc.Textarea(
                            id='payload-grado',
                            value=json.dumps({"porcentaje": 0.0, "total": 0, "conectados": 0}, ensure_ascii=False),
                            style={'width': '100%', 'height': 90}
                        ),
                        html.Button(
                            'Publicar GRADO (retain)',
                            id='btn-publish-grado',
                            n_clicks=0,
                            className='bg-blue-600 text-white font-bold py-2 px-4 rounded hover:bg-blue-700 transition duration-300'
                        ),
                    ], className='space-y-2'),

                    html.Div(children=[
                        html.Div([
                            html.Strong("GRDs desconectados → "),
                            html.Code(config.MQTT_TOPIC_GRDS)
                        ], className='mb-1'),
                        dcc.Textarea(
                            id='payload-grds',
                            value=json.dumps({"items": []}, ensure_ascii=False),
                            style={'width': '100%', 'height': 110}
                        ),
                        html.Button(
                            'Publicar GRDs (retain)',
                            id='btn-publish-grds',
                            n_clicks=0,
                            className='bg-emerald-600 text-white font-bold py-2 px-4 rounded hover:bg-emerald-700 transition duration-300'
                        ),
                    ], className='space-y-2'),

                    html.Div(children=[
                        html.Div([
                            html.Strong("Estado MÓDEM/routeo → "),
                            html.Code(config.MQTT_TOPIC_MODEM_CONEXION)
                        ], className='mb-1'),
                        dcc.Input(
                            id='payload-modem',
                            value=json.dumps({"estado": "abierto"}, ensure_ascii=False),
                            style={'width': '100%'}
                        ),
                        html.Button(
                            'Publicar MÓDEM (retain)',
                            id='btn-publish-modem',
                            n_clicks=0,
                            className='bg-purple-600 text-white font-bold py-2 px-4 rounded hover:bg-purple-700 transition duration-300'
                        ),
                    ], className='space-y-2'),

                    html.Div(id='output-publish-status', style={'display': 'none'})
                ])
            ]),
            html.Div(className='broker-panel', children=[
                html.H3("Suscripciones", className='text-xl font-semibold mb-4'),
                html.P(
                    "Mensajes recibidos de los tópicos (incluye retained y los publicados desde esta interfaz).",
                    className='text-gray-600 mb-4'
                ),
                html.Div(
                    id='subscription-display',
                    className='bg-gray-100 p-4 rounded h-96 overflow-y-scroll space-y-2 text-sm font-mono',
                    children=[html.P("Esperando mensajes...", className='text-gray-400')]
                )
            ]),
        ]),

        dcc.Interval(id='interval-component', interval=dash_interval_ms, n_intervals=0),
        dcc.Interval(id='broker-status-interval', interval=status_interval_ms, n_intervals=0)
    ])


def initialize_broker_components(manager, queue, auto_start=True):
    """
    Inyecta referencias compartidas. Si el manager expone set_message_queue/msg_queue,
    se fuerza a que comparta la misma cola que esta vista.
    """
    global mqtt_client_manager, message_queue, _auto_start_enabled
    mqtt_client_manager = manager
    message_queue = queue
    _auto_start_enabled = bool(auto_start)

    if mqtt_client_manager is None:
        return

    try:
        if hasattr(mqtt_client_manager, 'set_message_queue'):
            mqtt_client_manager.set_message_queue(message_queue)
        elif hasattr(mqtt_client_manager, 'msg_queue'):
            mqtt_client_manager.msg_queue = message_queue

        if not _auto_start_enabled:
            return

        desired = bool(load_observar_key("broker_conectar", True))
        if desired:
            threading.Thread(target=mqtt_client_manager.start, daemon=True).start()
        else:
            try:
                mqtt_client_manager.stop()
            except Exception:
                pass
    except Exception:
        pass


def _ensure_connected():
    """Si no está conectado, dispara reconnect en un thread para no bloquear Dash."""
    if mqtt_client_manager is None or not _auto_start_enabled:
        return False
    desired = bool(load_observar_key("broker_conectar", True))
    if not desired:
        return False
    try:
        status = mqtt_client_manager.get_connection_status()
    except Exception:
        status = 'desconectado'
    if status == 'conectado':
        return True
    threading.Thread(target=mqtt_client_manager.start, daemon=True).start()
    return False

def _prepare_payload_with_ts(raw_value: str, context: str, required_keys: tuple[str, ...]) -> str:
    """
    Valida que el payload sea un objeto JSON con las claves requeridas
    y escribe el campo ts con un valor UTC.
    """
    obj = json.loads(raw_value)
    if not isinstance(obj, dict):
        logger.error(
            "%s: payload debe ser objeto JSON. Recibido %s",
            context,
            type(obj).__name__,
            origin="BROKER/PUBLISH",
        )
        raise ValueError(f"{context}: payload debe ser objeto JSON")

    missing = [key for key in required_keys if key not in obj]
    if missing:
        logger.error("%s: faltan claves obligatorias %s", context, missing, origin="BROKER/PUBLISH")
        raise ValueError(f"{context}: faltan claves obligatorias {missing}")

    obj["ts"] = timebox.utc_iso()
    return json.dumps(obj, ensure_ascii=False)


def register_broker_callbacks(app: dash.Dash):

    @app.callback(
        Output('broker-toggle-status', 'children'),
        Input('broker-connection-toggle', 'on'),
        prevent_initial_call=False
    )
    def handle_broker_toggle(is_enabled: bool):
        try:
            update_observar_key("broker_conectar", bool(is_enabled))
        except Exception:
            pass

        if mqtt_client_manager is None:
            return dash.no_update
        if not _auto_start_enabled:
            return dash.no_update

        if is_enabled:
            threading.Thread(target=mqtt_client_manager.start, daemon=True).start()
        else:
            try:
                mqtt_client_manager.stop()
            except Exception:
                pass

        return dash.no_update

    @app.callback(
        Output('output-publish-status', 'children'),
        [
            Input('btn-publish-grado', 'n_clicks'),
            Input('btn-publish-grds', 'n_clicks'),
            Input('btn-publish-modem', 'n_clicks')
        ],
        [
            State('payload-grado', 'value'),
            State('payload-grds', 'value'),
            State('payload-modem', 'value'),
        ],
        prevent_initial_call=True
    )
    def handle_publish(n_grado, n_grds, n_modem, v_grado, v_grds, v_modem):
        ctx = dash.callback_context
        if not ctx.triggered:
            return ""

        if mqtt_client_manager is None:
            return "NO_MQTT_MANAGER"

        if not bool(load_observar_key("broker_conectar", True)):
            return "BROKER_DISABLED"

        # reconexión no bloqueante si hace falta
        connected = _ensure_connected()
        if not connected:
            return "RECONNECTING"

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        qos = int(config.MQTT_PUBLISH_QOS_STATE)
        retain = bool(config.MQTT_PUBLISH_RETAIN_STATE)

        try:
            if button_id == 'btn-publish-grado':
                payload = _prepare_payload_with_ts(
                    v_grado,
                    "GRADO",
                    ("porcentaje", "total", "conectados"),
                )
                mqtt_client_manager.publish(config.MQTT_TOPIC_GRADO, payload, qos=qos, retain=retain)
                return "PUBLISHED_GRADO"

            if button_id == 'btn-publish-grds':
                payload = _prepare_payload_with_ts(
                    v_grds,
                    "GRDS",
                    ("items",),
                )
                mqtt_client_manager.publish(config.MQTT_TOPIC_GRDS, payload, qos=qos, retain=retain)
                return "PUBLISHED_GRDS"

            if button_id == 'btn-publish-modem':
                payload = _prepare_payload_with_ts(
                    v_modem,
                    "MODEM",
                    ("estado",),
                )
                mqtt_client_manager.publish(config.MQTT_TOPIC_MODEM_CONEXION, payload, qos=qos, retain=retain)
                return "PUBLISHED_MODEM"

            return ""
        except json.JSONDecodeError:
            return "PAYLOAD_INVALID_JSON"
        except Exception as e:
            return f"PUBLISH_ERROR: {e}"

    @app.callback(
        Output('subscription-display', 'children'),
        [Input('interval-component', 'n_intervals')],
        [State('subscription-display', 'children')]
    )
    def update_subscriptions(_n, current_children):
        # cola compartida (vista/manager)
        q = message_queue
        if q is None and mqtt_client_manager is not None and hasattr(mqtt_client_manager, 'msg_queue'):
            q = mqtt_client_manager.msg_queue

        if q is None:
            return current_children

        new_blocks = []
        while True:
            try:
                topic, payload = q.get_nowait()
            except Empty:
                break
            except Exception:
                break

            # pretty-print si es JSON
            try:
                pretty = json.dumps(json.loads(payload), ensure_ascii=False, indent=2)
            except Exception:
                pretty = payload

            new_blocks.append(
                html.Div([
                    html.Div(f"[{topic}]", className='font-semibold'),
                    html.Pre(pretty, className='bg-white p-2 rounded overflow-x-auto')
                ], className='bg-gray-200 p-2 rounded')
            )

        if not new_blocks:
            return current_children

        existing = current_children if isinstance(current_children, list) else [current_children]
        # mantenemos hasta 50 bloques
        return (new_blocks + existing)[:50]

    @app.callback(
        Output('broker-status-indicator', 'className'),
        Input('broker-status-interval', 'n_intervals'),
        Input('broker-connection-toggle', 'on'),
    )
    def update_broker_status(_n, toggle_on):
        if not toggle_on:
            return 'status-circle status-disconnected'

        status = "desconectado"
        if mqtt_client_manager is not None:
            try:
                status = mqtt_client_manager.get_connection_status()
            except Exception:
                status = 'desconectado'

        if status == 'desconectado':
            _ensure_connected()

        if status == 'conectado':
            return 'status-circle status-connected'
        if status == 'conectando':
            return 'status-circle status-connecting'
        return 'status-circle status-disconnected'

