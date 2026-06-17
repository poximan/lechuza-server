import time
from src.persistencia.dao.dao_historicos import historicos_dao as dao
from src.persistencia.dao.dao_grd import grd_dao
from .modbus_driver import ModbusTcpDriver
from logosaurio import Logosaurio
from src.services.mqtt_publisher import ModbusMqttPublisher
from src import config
from src.utils import timebox

class GrdMiddlewareClient:
    """
    Cliente para monitorear GRDs via Modbus y publicar snapshots a MQTT:
      - Grado global:   config.MQTT_TOPIC_GRADO
      - GRDs down:      config.MQTT_TOPIC_GRDS
    """
    def __init__(
        self,
        modbus_driver: ModbusTcpDriver,
        default_unit_id: int,
        register_count: int,
        refresh_interval: int,
        logger: Logosaurio,
        mqtt_publisher: ModbusMqttPublisher,
    ):
        self.driver = modbus_driver
        self.default_unit_id = default_unit_id
        self.register_count = register_count
        self.refresh_interval = refresh_interval
        self.logger = logger
        self._active_grd_data = None
        self._last_grd_data_refresh = 0

        self.publisher = mqtt_publisher

        self._last_payload_grado = None
        self._last_payload_down = None

    def _refresh_grd_data(self):
        """Refresca la lista de GRDs activos desde la base de datos."""
        if time.time() - self._last_grd_data_refresh > 2000:
            self._active_grd_data = grd_dao.get_all_grds_with_descriptions(only_active=True)
            self._last_grd_data_refresh = time.time()
            if not self._active_grd_data:
                self.logger.log(
                    "No se encontraron GRDs activos en la base de datos para monitorear.",
                    origin="OBS/MW"
                )
            else:
                self.logger.log(f"GRDs activos: {list(self._active_grd_data.keys())}", origin="OBS/MW")

    @staticmethod
    def get_bit(value: int, bit_index: int) -> int:
        """Retorna el estado de un bit especifico en un entero."""
        return (value >> bit_index) & 1

    def _publish_snapshots_if_changed(self):
        """
        Calcula grado global y lista de desconectados; publica si hay cambios
        (y la primera vez siempre publica).
        """
        latest_states = dao.get_latest_states_for_all_grds()
        total = len(latest_states)
        conectados = sum(1 for v in latest_states.values() if v == 1)
        porcentaje = round((conectados / total) * 100, 2) if total else 0.0

        grado_payload = {
            "porcentaje": porcentaje,
            "total": total,
            "conectados": conectados,
            "ts": timebox.utc_iso()
        }

        down = []
        for item in dao.get_all_disconnected_grds():
            last_down = item.get("last_disconnected_timestamp")
            if last_down:
                try:
                    parsed = timebox.parse(last_down, legacy=True)
                    ultima_caida = timebox.utc_iso(parsed)
                except Exception:
                    ultima_caida = str(last_down)
            else:
                ultima_caida = ""
            down.append({
                "id": item["id_grd"],
                "nombre": item["description"],
                "ultima_caida": ultima_caida
            })

        down_timestamp = timebox.utc_iso()
        down_payload = {
            "items": down,
            "ts": down_timestamp
        }

        # Publicar grado si cambiÃ³
        if grado_payload != self._last_payload_grado:
            self.publisher.publish_grado(grado_payload)
            self._last_payload_grado = grado_payload
            self.logger.log(f"Publicado grado global en {config.MQTT_TOPIC_GRADO}: {grado_payload}", origin="OBS/MW")

        # Publicar desconectados si cambiÃ³
        if down_payload != self._last_payload_down:
            self.publisher.publish_grds(down_payload)
            self._last_payload_down = down_payload
            self.logger.log(f"Publicado snapshot de desconectados en {config.MQTT_TOPIC_GRDS}: {down_payload}", origin="OBS/MW")

    def start_observer_loop(self):
        """
        Loop principal: lee estados Modbus, persiste cambios y publica snapshots normalizados.
        """
        self.logger.log(
            f"Iniciando observador de GRD Middleware (Unit ID: {self.default_unit_id}, Intervalo: {self.refresh_interval}s)...",
            origin="OBS/MW"
        )

        # Primera publicaciÃ³n (si ya hay datos en DB)
        try:
            self._publish_snapshots_if_changed()
        except Exception:
            pass

        while True:
            self._refresh_grd_data()
            grd_ids_to_monitor = list(self._active_grd_data.keys()) if self._active_grd_data else []

            if not grd_ids_to_monitor:
                self.logger.log("No hay GRDs para monitorear. Esperando...", origin="OBS/MW")
                time.sleep(self.refresh_interval)
                continue

            timestamp_now = timebox.utc_now().strftime('%Y-%m-%d %H:%M:%S')

            if not self.driver.is_connected() and not self.driver.connect():
                self.logger.log(
                    "No se pudo establecer conexion con el servidor Modbus. Reintentando en el proximo ciclo.",
                    origin="OBS/MW"
                )
                time.sleep(self.refresh_interval)
                continue

            hubo_cambios = False

            for grd_id in grd_ids_to_monitor:
                if grd_id == 4:
                    self.logger.log(f"Omitiendo GRD_ID {grd_id} del monitoreo.", origin="OBS/MW")
                    continue

                grd_description = self._active_grd_data.get(grd_id, "Desconocido")
                modbus_start_address_offset = (grd_id - 1) * self.register_count

                registers_data = self.driver.read_input_registers(
                    modbus_start_address_offset,
                    self.register_count,
                    unit_id=self.default_unit_id
                )

                if registers_data is not None and len(registers_data) >= self.register_count:
                    reg_16_value = registers_data[15]
                    current_connected_value = self.get_bit(reg_16_value, 0)
                else:
                    self.logger.log(
                        f"Fallo al leer registros para GRD_ID {grd_id} ({grd_description}). Asumiendo estado DESCONECTADO.",
                        origin="OBS/MW"
                    )
                    current_connected_value = 0

                latest_value_in_db_for_grd = dao.get_latest_connected_state_for_grd(grd_id)

                if current_connected_value != latest_value_in_db_for_grd:
                    self.logger.log(
                        f"Cambio detectado en ({grd_description}): MB={current_connected_value}, DB={latest_value_in_db_for_grd}",
                        origin="OBS/MW"
                    )
                    dao.insert_historico_reading(grd_id, timestamp_now, current_connected_value)
                    hubo_cambios = True

            if hubo_cambios:
                self._publish_snapshots_if_changed()

            time.sleep(self.refresh_interval)
