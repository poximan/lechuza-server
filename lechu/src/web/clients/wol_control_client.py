from __future__ import annotations

import http.client
import json
import socket
from pathlib import Path
from typing import Any
from urllib.parse import quote


class UnixHttpConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(str(self.socket_path))
        self.sock = connection


class WolControlClient:
    def __init__(self, socket_path: str, timeout: float = 5.0) -> None:
        if not socket_path.strip():
            raise ValueError("socket_path es obligatorio")
        self.socket_path = Path(socket_path)
        self.timeout = timeout

    def start(self, request_id: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/v1/wake",
            {"contract_version": 1, "request_id": request_id},
        )
        if payload.get("error") == "wake_in_progress":
            operation = payload.get("operation")
            if isinstance(operation, dict):
                return operation
        return payload

    def status(self, request_id: str) -> dict[str, Any]:
        safe_id = quote(request_id, safe="")
        return self._request("GET", f"/api/v1/wake/{safe_id}")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        connection = UnixHttpConnection(self.socket_path, self.timeout)
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(65537)
        finally:
            connection.close()
        if len(raw) > 65536:
            raise RuntimeError("respuesta de wol-control demasiado grande")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("respuesta JSON invalida de wol-control") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("contrato HTTP invalido de wol-control")
        if response.status == 409 and decoded.get("error") == "wake_in_progress":
            return decoded
        if response.status < 200 or response.status >= 300:
            detail = decoded.get("error") or f"HTTP {response.status}"
            raise RuntimeError(f"wol-control: {detail}")
        return decoded
