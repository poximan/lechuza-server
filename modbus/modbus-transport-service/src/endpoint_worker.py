from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from pymodbus.client import ModbusTcpClient

from .config import EndpointConfig
from .contracts import ReadRequest


@dataclass
class WorkItem:
    caller: str
    request: ReadRequest | None = None
    done: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None


class EndpointWorker:
    """Unico propietario de un socket y de la cola de su endpoint fisico."""

    def __init__(self, config: EndpointConfig, queue_maxsize: int) -> None:
        self.config = config
        self.queue: queue.Queue[WorkItem | None] = queue.Queue(maxsize=queue_maxsize)
        self.client: ModbusTcpClient | None = None
        self.connected = False
        self.stop_event = threading.Event()
        self.state_lock = threading.RLock()
        self.active: dict[str, Any] | None = None
        self.recent: list[dict[str, Any]] = []
        self.started_at = time.monotonic()
        self.busy_seconds = 0.0
        self.completed = 0
        self.failed = 0
        self.attempts_total = 0
        self.thread = threading.Thread(
            target=self._run,
            name=f"modbus-{config.name}",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass
        self.thread.join(
            timeout=self.config.timeout_seconds * self.config.attempts + 5
        )
        if self.thread.is_alive():
            raise RuntimeError(f"El worker Modbus {self.config.name} no pudo detenerse")
        self._disconnect()

    def submit_read(self, request: ReadRequest, wait_timeout: int) -> dict[str, Any]:
        return self._submit(WorkItem(caller=request.caller, request=request), wait_timeout)

    def submit_connect(self, caller: str, wait_timeout: int) -> dict[str, Any]:
        return self._submit(WorkItem(caller=caller), wait_timeout)

    def _submit(self, item: WorkItem, wait_timeout: int) -> dict[str, Any]:
        try:
            self.queue.put_nowait(item)
        except queue.Full as exc:
            raise HTTPException(
                status_code=503,
                detail=f"cola {self.config.name} completa",
            ) from exc
        if not item.done.wait(wait_timeout):
            item.cancelled.set()
            raise HTTPException(
                status_code=504,
                detail=f"espera agotada en cola {self.config.name}; consulta cancelada",
            )
        return item.result or {
            "ok": False,
            "connected": False,
            "error": "resultado ausente",
        }

    def _connect(self) -> bool:
        if self.connected and self.client is not None:
            return True
        self._disconnect()
        try:
            self.client = ModbusTcpClient(
                self.config.host,
                port=self.config.port,
                timeout=self.config.timeout_seconds,
                retries=0,
            )
            self.connected = bool(self.client.connect())
        except Exception:
            self.connected = False
        return self.connected

    def _disconnect(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self.connected = False

    def _run(self) -> None:
        while not self.stop_event.is_set():
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                return
            if item.cancelled.is_set():
                item.result = {
                    "ok": False,
                    "connected": self.connected,
                    "error": "consulta cancelada antes del despacho",
                }
                item.done.set()
                self.queue.task_done()
                continue
            self._execute_item(item)

    def _execute_item(self, item: WorkItem) -> None:
        started = time.monotonic()
        request = item.request
        active = {
            "source": item.caller,
            "operation": "read" if request is not None else "connect",
            "attempt": 0,
            "_started_monotonic": started,
        }
        if request is not None:
            active.update(
                {
                    "unit_id": request.unit_id,
                    "function_code": request.function_code,
                    "address": f"0x{request.address:04X}",
                    "count": request.count,
                }
            )
        with self.state_lock:
            self.active = active
        try:
            if request is None:
                connected = self._connect()
                item.result = {
                    "ok": connected,
                    "connected": connected,
                    "error": None if connected else "conexion no disponible",
                }
            else:
                item.result = self._execute_read(request)
        except Exception as exc:
            self._disconnect()
            item.result = {
                "ok": False,
                "connected": False,
                "registers": None,
                "error": f"{type(exc).__name__}: {exc}",
                "exception_code": None,
            }
        finally:
            elapsed = max(0.0, time.monotonic() - started)
            succeeded = bool(item.result and item.result.get("ok"))
            with self.state_lock:
                recent = {
                    key: value
                    for key, value in (self.active or {}).items()
                    if not key.startswith("_")
                }
                self.busy_seconds += elapsed
                self.completed += 1
                if not succeeded:
                    self.failed += 1
                self.recent.insert(
                    0,
                    {**recent, "ok": succeeded, "duration_ms": round(elapsed * 1000, 1)},
                )
                del self.recent[20:]
                self.active = None
            item.done.set()
            self.queue.task_done()

    def _execute_read(self, request: ReadRequest) -> dict[str, Any]:
        last_error = "lectura no disponible"
        last_exception_code = None
        for attempt in range(1, self.config.attempts + 1):
            with self.state_lock:
                self.attempts_total += 1
                if self.active is not None:
                    self.active["attempt"] = attempt
            if not self._connect():
                last_error = "conexion no disponible"
                last_exception_code = None
                continue
            try:
                method = (
                    self.client.read_holding_registers
                    if request.function_code == 3
                    else self.client.read_input_registers
                )
                result = method(
                    request.address,
                    count=request.count,
                    slave=request.unit_id,
                )
                registers = getattr(result, "registers", None)
                if (
                    result is not None
                    and not result.isError()
                    and registers is not None
                    and len(registers) == request.count
                ):
                    return {
                        "ok": True,
                        "connected": True,
                        "registers": [int(value) for value in registers],
                        "error": None,
                        "exception_code": None,
                    }
                raw_code = getattr(result, "exception_code", None)
                last_exception_code = int(raw_code) if raw_code is not None else None
                last_error = f"respuesta Modbus invalida: {result}"
            except Exception as exc:
                last_exception_code = None
                last_error = f"{type(exc).__name__}: {exc}"
            self._disconnect()
        return {
            "ok": False,
            "connected": self.connected,
            "registers": None,
            "error": last_error,
            "exception_code": last_exception_code,
        }

    def diagnostics(self) -> dict[str, Any]:
        with self.state_lock:
            elapsed = max(0.001, time.monotonic() - self.started_at)
            current = None
            if self.active is not None:
                current = {
                    key: value
                    for key, value in self.active.items()
                    if not key.startswith("_")
                }
                current["elapsed_ms"] = round(
                    (time.monotonic() - self.active["_started_monotonic"]) * 1000,
                    1,
                )
            recent = list(self.recent)
            completed = self.completed
            failed = self.failed
            attempts = self.attempts_total
            busy_seconds = self.busy_seconds
            connected = self.connected
            if self.active is not None:
                busy_seconds += max(
                    0.0,
                    time.monotonic() - self.active["_started_monotonic"],
                )
        with self.queue.mutex:
            pending = list(self.queue.queue)[:10]
        durations = [float(entry["duration_ms"]) for entry in recent]
        return {
            "endpoint": self.config.name,
            "target": f"{self.config.host}:{self.config.port}",
            "connected": connected,
            "worker_running": self.thread.is_alive(),
            "busy_percent": round(min(100.0, busy_seconds / elapsed * 100.0), 1),
            "queue_depth": self.queue.qsize(),
            "completed": completed,
            "failed": failed,
            "attempts": attempts,
            "average_duration_ms": (
                round(sum(durations) / len(durations), 1) if durations else None
            ),
            "current": current,
            "next": [self._pending_contract(item) for item in pending if item is not None],
            "recent": recent,
        }

    @staticmethod
    def _pending_contract(item: WorkItem) -> dict[str, Any]:
        if item.request is None:
            return {"source": item.caller, "operation": "connect"}
        request = item.request
        return {
            "source": request.caller,
            "operation": "read",
            "unit_id": request.unit_id,
            "function_code": request.function_code,
            "address": f"0x{request.address:04X}",
            "count": request.count,
        }
