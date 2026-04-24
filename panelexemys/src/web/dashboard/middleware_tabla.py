import dash
from dash import html
from dash.dependencies import Input, Output
from src.utils import timebox
from src.web.clients.modbus_client import modbus_client

def get_main_data_table_layout():
    """
    Define el layout para el bloque de caidas del GRD y su titulo.
    """
    return html.Div(children=[
        html.H2(id='grd-data-title', className='grd-data-title'),
        html.Div(id='grd-data-table', className='grd-table-container'),
    ])


def register_main_data_table_callbacks(app: dash.Dash):
    """
    Registra los callbacks relacionados con el bloque de caidas del GRD.
    """
    @app.callback(
        Output('grd-data-title', 'children'),
        Output('grd-data-table', 'children'),
        [Input('time-window-state', 'data'),
         Input('interval-component', 'n_intervals')] # La tabla tambien se actualiza con el intervalo
    )
    def update_grd_data_table(time_window_state_data, _n_intervals):
        selected_grd_id = time_window_state_data['current_grd_id']

        try:
            current_db_grd_descriptions = modbus_client.get_descriptions()
        except Exception as exc:
            error_message = f"Fallo al obtener descripciones de GRD: {exc}"
            print(error_message)
            return "Detalles del Equipo", html.P(error_message, className="warning-text")

        if not current_db_grd_descriptions:
            no_grd_message = "ADVERTENCIA: No se han encontrado equipos GRD en la base de datos para consulta."
            return "Detalles del Equipo", html.P(no_grd_message, className="warning-text")

        if selected_grd_id is None:
            default_message = "Por favor, seleccione un equipo GRD del menu desplegable."
            return "Detalles del Equipo", html.P(default_message, className="info-text")

        if selected_grd_id not in current_db_grd_descriptions:
            no_desc_message = f"No existe descripcion para el GRD {selected_grd_id} en el catalogo actual."
            print(no_desc_message)
            return "Detalles del Equipo", html.P(no_desc_message, className="warning-text")

        grd_description_for_table_title = current_db_grd_descriptions[selected_grd_id]
        grd_data_title_text = f"Ultimas caidas de comunicacion de {grd_description_for_table_title}"

        try:
            outages_payload = modbus_client.get_outages(selected_grd_id, limit=10)
        except Exception as exc:
            print(f"Fallo al obtener caidas del GRD {selected_grd_id}: {exc}")
            table_content = html.P(
                f"No se pudieron obtener las caidas del GRD {selected_grd_id}: {exc}",
                className="warning-text",
            )
            return grd_data_title_text, table_content

        if "items" not in outages_payload:
            no_items_message = f"El endpoint de caidas no incluyo el campo items para el GRD {selected_grd_id}."
            print(no_items_message)
            return grd_data_title_text, html.P(no_items_message, className="warning-text")

        outages_items = outages_payload["items"]

        if not outages_items:
            return grd_data_title_text, html.P(
                f"No hay caidas registradas para el GRD {selected_grd_id}.",
                className="info-text",
            )

        def build_outage_item(position: int, outage_data: dict):
            start_timestamp = outage_data["start_timestamp"]
            start_display = timebox.format_local(start_timestamp, fmt="%Y-%m-%d %H:%M:%S", legacy=True)
            duration_minutes = int(outage_data["duration_minutes"])
            return html.Div(
                className="outage-item-card",
                children=[
                    html.Div(f"Caida {position}", className="outage-item-title"),
                    html.Div(
                        className="outage-item-inline",
                        children=[
                            html.Span(f"Inicio {start_display}", className="outage-item-inline-text"),
                            html.Span(f"Duracion {duration_minutes} min", className="outage-item-inline-text"),
                        ],
                    ),
                ],
            )

        outage_cards = [
            build_outage_item(index + 1, outage_data)
            for index, outage_data in enumerate(outages_items[:10])
        ]

        return grd_data_title_text, html.Div(
            className="outages-three-columns",
            children=outage_cards,
        )
