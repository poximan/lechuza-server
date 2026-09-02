import threading
from dataclasses import dataclass

from logosaurio import Logosaurio
from pymodbus.client import ModbusTcpClient


@dataclass(frozen=True)
class ModbusTcpConnectionConfig:
    name: str
    host: str
    port: int
    timeout: int
    attempts: int


class ModbusTcpReadOnlyDriver:
    """Conexion Modbus TCP de solo lectura con reintentos controlados."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: int,
        attempts: int,
        logger: Logosaurio,
        name: str = "modbus",
    ):
        if timeout < 1:
            raise ValueError("El timeout Modbus debe ser positivo")
        if attempts < 1:
            raise ValueError("La cantidad de intentos Modbus debe ser positiva")
        self.host = host
        self.port = port
        self.timeout = timeout
        self.attempts = attempts
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
        return cls(
            host=cfg.host,
            port=cfg.port,
            timeout=cfg.timeout,
            attempts=cfg.attempts,
            logger=logger,
            name=cfg.name,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.name} {self.host}:{self.port}"

    def connect(self) -> bool:
        """Abre la conexion TCP de este conjunto si todavia no esta conectada."""
        with self._io_lock:
            if self._shutdown:
                return False
            if self._is_connected and self._client:
                return True

            self.disconnect()
            try:
                self._client = ModbusTcpClient(
                    self.host,
                    port=self.port,
                    timeout=self.timeout,
                    retries=0,
                )
                if self._client.connect():
                    self._is_connected = True
                    self.logger.log(
                        f"Conectado exitosamente a {self.endpoint}",
                        origin="OBS/DRV",
                    )
                    return True
            except Exception as exc:
                self.logger.log(
                    f"Error al conectar a {self.endpoint}: "
                    f"{type(exc).__name__}: {exc}",
                    origin="OBS/DRV",
                )
            self._is_connected = False
            return False

    def disconnect(self) -> None:
        """Cierra la conexion y descarta cualquier respuesta tardia."""
        with self._io_lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None
            self._is_connected = False

    def shutdown(self) -> None:
        """Cierra el driver e impide reconexiones durante el apagado."""
        with self._io_lock:
            self._shutdown = True
            self.disconnect()

    def read_input_registers(
        self,
        address_offset: int,
        count: int,
        unit_id: int,
    ):
        """Lee registros de entrada con la politica comun de reintentos."""
        return self._read_registers(
            method_name="read_input_registers",
            operation="input registers",
            address_offset=address_offset,
            count=count,
            unit_id=unit_id,
        )

    def read_holding_registers(
        self,
        address_offset: int,
        count: int,
        unit_id: int,
    ):
        """Lee registros de retencion con la politica comun de reintentos."""
        return self._read_registers(
            method_name="read_holding_registers",
            operation="holding registers",
            address_offset=address_offset,
            count=count,
            unit_id=unit_id,
        )

    def _read_registers(
        self,
        *,
        method_name: str,
        operation: str,
        address_offset: int,
        count: int,
        unit_id: int,
    ):
        with self._io_lock:
            total_attempts = self.attempts
            for attempt in range(1, total_attempts + 1):
                if not self._is_connected and not self.connect():
                    reason = "conexion no disponible"
                else:
                    try:
                        operation_method = getattr(self._client, method_name)
                        result = operation_method(
                            address_offset,
                            count=count,
                            slave=unit_id,
                        )
                        registers = getattr(result, "registers", None)
                        if (
                            result is not None
                            and not (
                                hasattr(result, "isError")
                                and result.isError()
                            )
                            and registers
                        ):
                            return registers
                        reason = f"respuesta invalida: {result}"
                    except Exception as exc:
                        reason = f"{type(exc).__name__}: {exc}"
                self.logger.log(
                    f"Fallo {operation} en {self.endpoint}, Unit ID {unit_id}, "
                    f"Addr {address_offset}, intento {attempt}/{total_attempts}: "
                    f"{reason}",
                    origin="OBS/DRV",
                )
                self.disconnect()
            return None

    def is_connected(self) -> bool:
        """Informa si este canal TCP permanece conectado."""
        return bool(self._is_connected)
