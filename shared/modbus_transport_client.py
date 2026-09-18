from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class ModbusReadResult:
    registers: list[int] | None
    error: str | None = None
    exception_code: int | None = None


class ModbusTcpReadOnlyDriver:
    """Adaptador compatible con los colectores; el socket pertenece al transporte."""

    def __init__(
        self,
        base_url: str,
        endpoint_name: str,
        caller: str,
        api_key: str,
        timeout: int,
        logger: Any,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint_name = endpoint_name
        self.caller = caller
        self.timeout = timeout
        self.logger = logger
        self._headers = {"X-API-Key": api_key}
        self._session = requests.Session()
        self._connected = False
        self._shutdown = False

    @property
    def endpoint(self) -> str:
        return self.endpoint_name

    def connect(self) -> bool:
        if self._shutdown:
            return False
        try:
            response = self._session.post(
                f"{self.base_url}/internal/v1/endpoints/{self.endpoint_name}/connect",
                headers=self._headers,
                json={"caller": self.caller},
                timeout=self.timeout,
            )
            response.raise_for_status()
            self._connected = bool(response.json().get("connected"))
        except (requests.RequestException, ValueError):
            self._connected = False
        return self._connected

    def disconnect(self) -> None:
        self._connected = False

    def shutdown(self) -> None:
        self._shutdown = True
        self._connected = False
        self._session.close()

    def is_connected(self) -> bool:
        return self._connected

    def read_input_registers(self, address_offset: int, count: int, unit_id: int):
        return self._read(4, address_offset, count, unit_id).registers

    def read_holding_registers(self, address_offset: int, count: int, unit_id: int):
        return self._read(3, address_offset, count, unit_id).registers

    def read_holding_registers_result(
        self, address_offset: int, count: int, unit_id: int
    ) -> ModbusReadResult:
        return self._read(3, address_offset, count, unit_id)

    def _read(
        self, function_code: int, address: int, count: int, unit_id: int
    ) -> ModbusReadResult:
        if self._shutdown:
            return ModbusReadResult(None, "driver apagado")
        try:
            response = self._session.post(
                f"{self.base_url}/internal/v1/read",
                headers=self._headers,
                json={
                    "endpoint": self.endpoint_name,
                    "caller": self.caller,
                    "function_code": function_code,
                    "unit_id": unit_id,
                    "address": address,
                    "count": count,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            self._connected = False
            return ModbusReadResult(None, f"transporte no disponible: {exc}")

        self._connected = bool(payload.get("connected", payload.get("ok")))
        registers = payload.get("registers")
        if payload.get("ok") is True and isinstance(registers, list):
            return ModbusReadResult([int(value) for value in registers])
        return ModbusReadResult(
            None,
            str(payload.get("error") or "lectura Modbus no disponible"),
            int(payload["exception_code"])
            if payload.get("exception_code") is not None
            else None,
        )
