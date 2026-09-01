import threading
from dataclasses import dataclass

from pymodbus.client import ModbusTcpClient
from logosaurio import Logosaurio


@dataclass(frozen=True)
class ModbusTcpConnectionConfig:
    name: str
    host: str
    port: int
    timeout: int = 10


class ModbusTcpReadOnlyDriver:
    """
    Driver generico para la conexion y comunicacion con un servidor Modbus TCP.
    Encapsula la logica de conexion, reintento y manejo de errores basicos.
    """
    def __init__(self, host: str, port: int, timeout: int, logger: Logosaurio, name: str = "modbus"):
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
        self.name = name
        self._client = None
        self._is_connected = False
        self._shutdown = False
        self._io_lock = threading.RLock()

    @classmethod
    def from_config(
        cls,
        cfg: ModbusTcpConnectionConfig,
        logger: Logosaurio,
    ) -> "ModbusTcpReadOnlyDriver":
        return cls(host=cfg.host, port=cfg.port, timeout=cfg.timeout, logger=logger, name=cfg.name)

    @property
    def endpoint(self) -> str:
        return f"{self.name} {self.host}:{self.port}"

    def connect(self) -> bool:
        """
        Intenta establecer una conexion con el servidor Modbus TCP.
        """
        with self._io_lock:
            if self._shutdown:
                return False
            if self._is_connected and self._client:
                self.logger.log(f"Ya conectado a {self.endpoint}. No se necesita reconectar.", origin="OBS/DRV")
                return True

            self.logger.log(f"Intentando conectar a {self.endpoint}...", origin="OBS/DRV")
            self.disconnect()

            try:
                self._client = ModbusTcpClient(self.host, port=self.port, timeout=self.timeout)

                if self._client.connect():
                    self._is_connected = True
                    self.logger.log(f"Conectado exitosamente a {self.endpoint}", origin="OBS/DRV")
                    return True
                else:
                    self._is_connected = False
                    self.logger.log(f"No se pudo conectar a {self.endpoint}", origin="OBS/DRV")
                    return False
            except Exception as e:
                self._is_connected = False
                self.logger.log(f"Error al intentar conectar a {self.endpoint}: {e}", origin="OBS/DRV")
                return False

    def disconnect(self):
        """
        Cierra la conexion Modbus TCP.
        """
        with self._io_lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
                was_connected = self._is_connected
                self._is_connected = False
                if was_connected:
                    self.logger.log(f"Desconectado de {self.endpoint}", origin="OBS/DRV")

    def shutdown(self) -> None:
        """Cierra el driver e impide reconexiones durante el apagado."""
        with self._io_lock:
            self._shutdown = True
            self.disconnect()

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
                    # Una excepcion del gateway puede dejar una respuesta tardia en
                    # la conexion. Se descarta para que la proxima consulta no la
                    # confunda con la respuesta de otro esclavo.
                    self.disconnect()
                    return None
                registers = getattr(result, 'registers', None)
                if registers is None:
                    self.disconnect()
                    return None
                return registers
            except Exception as e:
                self.logger.log(
                    f"Excepcion en lectura de holding registers para Unit ID {unit_id}, Addr {address_offset}: {e}",
                    origin="OBS/DRV"
                )
                self.disconnect()
                return None

    def is_connected(self) -> bool:
        """
        Retorna el estado actual de la conexion.
        """
        return bool(self._is_connected)
