from __future__ import annotations

import re
import socket
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Callable

from timeauthority import get_time_authority


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
TERMINAL_STATUSES = {"ssh_open", "failed"}


class WakeOperationBusy(RuntimeError):
    def __init__(self, operation: dict[str, Any]) -> None:
        super().__init__("ya hay un encendido en seguimiento")
        self.operation = operation


class WakeOperationNotFound(KeyError):
    pass


class WakeOperationManager:
    """Unico propietario de la emision WoL y del seguimiento por SSH."""

    def __init__(
        self,
        *,
        target_ip: str,
        target_mac: bytes,
        broadcast_ip: str,
        ssh_timeout_seconds: int,
        retained_operations: int = 32,
    ) -> None:
        self.target_ip = target_ip
        self.target_mac = target_mac
        self.broadcast_ip = broadcast_ip
        self.ssh_timeout_seconds = ssh_timeout_seconds
        self.retained_operations = retained_operations
        self.time = get_time_authority()
        self._lock = threading.RLock()
        self._operations: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._observers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._active_request_id: str | None = None

    def trigger(
        self,
        request_id: str,
        source: str,
        observer: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        normalized_id = str(request_id or "").strip()
        normalized_source = str(source or "").strip()
        if REQUEST_ID_PATTERN.fullmatch(normalized_id) is None:
            raise ValueError("request_id invalido")
        if not normalized_source:
            raise ValueError("source es obligatorio")

        start_worker = False
        with self._lock:
            existing = self._operations.get(normalized_id)
            if existing is not None:
                if observer is not None:
                    self._observers.setdefault(normalized_id, []).append(observer)
                snapshot = deepcopy(existing)
            else:
                if self._active_request_id is not None:
                    raise WakeOperationBusy(
                        deepcopy(self._operations[self._active_request_id])
                    )
                now = self.time.utc_iso()
                operation = {
                    "contract_version": 1,
                    "request_id": normalized_id,
                    "source": normalized_source,
                    "status": "accepted",
                    "target_ip": self.target_ip,
                    "target_port": 22,
                    "broadcast_ip": self.broadcast_ip,
                    "started_at": now,
                    "updated_at": now,
                    "packet_bytes": None,
                    "error": None,
                }
                self._operations[normalized_id] = operation
                if observer is not None:
                    self._observers[normalized_id] = [observer]
                self._active_request_id = normalized_id
                self._trim_unlocked()
                snapshot = deepcopy(operation)
                start_worker = True

        if start_worker:
            threading.Thread(
                target=self._wake_and_watch,
                args=(normalized_id,),
                name="wol-ssh-watch",
                daemon=True,
            ).start()
        else:
            self._notify_one(observer, snapshot)
        return snapshot

    def get(self, request_id: str) -> dict[str, Any]:
        with self._lock:
            operation = self._operations.get(request_id)
            if operation is None:
                raise WakeOperationNotFound(request_id)
            return deepcopy(operation)

    def current(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_request_id is None:
                return None
            return deepcopy(self._operations[self._active_request_id])

    def _wake_and_watch(self, request_id: str) -> None:
        try:
            packet = b"\xff" * 6 + self.target_mac * 16
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sent = udp_socket.sendto(packet, (self.broadcast_ip, 9))
            if sent != len(packet):
                raise OSError(f"envio UDP incompleto: {sent}/{len(packet)} bytes")
            self._update(request_id, "packet_sent", packet_bytes=sent)

            deadline = time.monotonic() + self.ssh_timeout_seconds
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection((self.target_ip, 22), timeout=1.0):
                        self._update(request_id, "ssh_open")
                        return
                except OSError:
                    time.sleep(2.0)
            self._update(
                request_id,
                "failed",
                error=(
                    f"el puerto 22 de {self.target_ip} no abrio dentro de "
                    f"{self.ssh_timeout_seconds} segundos"
                ),
            )
        except Exception as exc:
            self._update(
                request_id,
                "failed",
                error=f"no se pudo emitir WoL: {type(exc).__name__}: {exc}",
            )

    def _update(self, request_id: str, status: str, **values: Any) -> None:
        with self._lock:
            operation = self._operations[request_id]
            operation.update(
                status=status,
                updated_at=self.time.utc_iso(),
                **values,
            )
            snapshot = deepcopy(operation)
            if status in TERMINAL_STATUSES:
                self._active_request_id = None
        self._notify(request_id, snapshot)
        if status in TERMINAL_STATUSES:
            with self._lock:
                self._observers.pop(request_id, None)

    def _notify(self, request_id: str, snapshot: dict[str, Any]) -> None:
        with self._lock:
            observers = list(self._observers.get(request_id, ()))
        for observer in observers:
            self._notify_one(observer, snapshot)

    @staticmethod
    def _notify_one(
        observer: Callable[[dict[str, Any]], None] | None,
        snapshot: dict[str, Any],
    ) -> None:
        if observer is None:
            return
        try:
            observer(deepcopy(snapshot))
        except Exception as exc:
            print(
                f"wol-service: no se pudo publicar una actualizacion: {exc}",
                flush=True,
            )

    def _trim_unlocked(self) -> None:
        while len(self._operations) > self.retained_operations:
            oldest_id = next(iter(self._operations))
            if oldest_id == self._active_request_id:
                break
            self._operations.pop(oldest_id)
            self._observers.pop(oldest_id, None)
