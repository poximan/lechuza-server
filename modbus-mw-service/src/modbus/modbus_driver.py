import threading

from pymodbus.client import ModbusTcpClient
from logosaurio import Logosaurio

class ModbusTcpDriver:
    """
    Driver generico para la conexion y comunicacion con un servidor Modbus TCP.
    Encapsula la logica de conexion, reintento y manejo de errores basicos.
    """
    def __init__(self, host: str, port: int, timeout: int, logger: Logosaurio):
        """
        Inicializa el driver Modbus TCP.

        Args:
            host (str): Direccion IP o nombre de host del servidor Modbus TCP.
            port (int): Puerto del servidor Modbus TCP (por defecto 502).
            timeout (int): Tiempo de espera en segundos para intentar la conexion.
            logger (Logosaurio): Instancia del logger para registrar eventos.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logger = logger
        self._client = None
        self._is_connected = False
        self._io_lock = threading.RLock()

    def connect(self) -> bool:
        """
        Intenta establecer una conexion con el servidor Modbus TCP.
        """
        with self._io_lock:
            if self._is_connected and self._client:
                self.logger.log(f"Ya conectado a {self.host}:{self.port}. No se necesita reconectar.", origin="OBS/DRV")
                return True

            self.logger.log(f"Intentando conectar a {self.host}:{self.port}...", origin="OBS/DRV")
            self.disconnect()

            try:
                self._client = ModbusTcpClient(self.host, port=self.port, timeout=self.timeout)

                if self._client.connect():
                    self._is_connected = True
                    self.logger.log(f"Conectado exitosamente a {self.host}:{self.port}", origin="OBS/DRV")
                    return True
                else:
                    self._is_connected = False
                    self.logger.log(f"No se pudo conectar a {self.host}:{self.port}", origin="OBS/DRV")
                    return False
            except Exception as e:
                self._is_connected = False
                self.logger.log(f"Error al intentar conectar a {self.host}:{self.port}: {e}", origin="OBS/DRV")
                return False

    def disconnect(self):
        """
        Cierra la conexion Modbus TCP.
        """
        with self._io_lock:
            if self._client and self._is_connected:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._is_connected = False
                self.logger.log(f"Desconectado de {self.host}:{self.port}", origin="OBS/DRV")

    def read_input_registers(self, address_offset: int, count: int, unit_id: int):
        """
        Lee una serie de registros de entrada (Input Registers) del esclavo Modbus.

        Args:
            address_offset (int): La direccion de inicio del registro (offset 0 para 30001).
            count (int): La cantidad de registros a leer.
            unit_id (int): El Unit ID del esclavo al que consultar.

        Returns:
            list[int] | None: Lista de valores si la lectura fue exitosa, o None en caso de error.
        """
        with self._io_lock:
            if not self._is_connected and not self.connect():
                self.logger.log(f"Fallo al conectar para leer registros de entrada (Unit ID {unit_id})", origin="OBS/DRV")
                return None

            try:
                result = self._client.read_input_registers(address_offset, count=count, slave=unit_id)

                if result is None:
                    self.logger.log(
                        f"Error de comunicacion o respuesta invalida del servidor para Unit ID {unit_id}, Addr {address_offset}, Cant {count}.",
                        origin="OBS/DRV"
                    )
                    return None

                if hasattr(result, 'isError') and result.isError():
                    self.logger.log(
                        f"El esclavo (Unit ID {unit_id}) reporto un error de protocolo: {result} al leer {address_offset}.",
                        origin="OBS/DRV"
                    )
                    return None

                elif getattr(result, 'registers', None):
                    return result.registers
                else:
                    self.logger.log(
                        f"Se recibio una respuesta valida, pero sin registros para Unit ID {unit_id}, Addr {address_offset}, Cant {count}.",
                        origin="OBS/DRV"
                    )
                    return None
            except Exception as e:
                self.logger.log(
                    f"Excepcion en lectura para Unit ID {unit_id}, Addr {address_offset}, Cant {count}: {e}.",
                    origin="OBS/DRV"
                )
                self.disconnect()
                return None

    def read_holding_registers(self, address_offset: int, count: int, unit_id: int):
        """
        Lee una serie de registros de retencion (Holding Registers) del esclavo Modbus.
        """
        with self._io_lock:
            if not self._is_connected and not self.connect():
                self.logger.log(f"Fallo al conectar para leer holding registers (Unit ID {unit_id})", origin="OBS/DRV")
                return None

            try:
                result = self._client.read_holding_registers(address_offset, count=count, slave=unit_id)
                if result is None or (hasattr(result, 'isError') and result.isError()):
                    self.logger.log(
                        f"Error al leer holding registers para Unit ID {unit_id}, Addr {address_offset}: {result}",
                        origin="OBS/DRV"
                    )
                    return None
                return getattr(result, 'registers', None)
            except Exception as e:
                self.logger.log(
                    f"Excepcion en lectura de holding registers para Unit ID {unit_id}, Addr {address_offset}: {e}",
                    origin="OBS/DRV"
                )
                self.disconnect()
                return None

    def write_single_register(self, address_offset: int, value: int, unit_id: int):
        """
        Escribe un unico registro de retencion (Holding Register) en el esclavo Modbus.
        """
        with self._io_lock:
            if not self._is_connected and not self.connect():
                self.logger.log(f"Fallo al conectar para escribir registro (Unit ID {unit_id})", origin="OBS/DRV")
                return False

            try:
                result = self._client.write_register(address_offset, value, slave=unit_id)
                if result is None or (hasattr(result, 'isError') and result.isError()):
                    self.logger.log(
                        f"Error al escribir registro para Unit ID {unit_id}, Addr {address_offset}, Value {value}: {result}",
                        origin="OBS/DRV"
                    )
                    return False

                self.logger.log(f"Escritura exitosa: Unit ID {unit_id}, Addr {address_offset}, Value {value}", origin="OBS/DRV")
                return True
            except Exception as e:
                self.logger.log(
                    f"Excepcion al escribir registro para Unit ID {unit_id}, Addr {address_offset}, Value {value}: {e}",
                    origin="OBS/DRV"
                )
                self.disconnect()
                return False

    def is_connected(self) -> bool:
        """
        Retorna el estado actual de la conexion.
        """
        with self._io_lock:
            return self._is_connected
