from __future__ import annotations

import json
import os
import re
import socketserver
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .wake_operation import (
    REQUEST_ID_PATTERN,
    WakeOperationBusy,
    WakeOperationManager,
    WakeOperationNotFound,
)


STATUS_PATH = re.compile(r"^/api/v1/wake/([^/]+)$")


class UnixThreadingServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


class ControlApi:
    def __init__(self, socket_path: Path, manager: WakeOperationManager) -> None:
        self.socket_path = socket_path
        self.manager = manager
        self.server: UnixThreadingServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        manager = self.manager

        class Handler(BaseHTTPRequestHandler):
            server_version = "lechu-wol-control/1"

            def log_message(self, pattern: str, *args: object) -> None:
                print(f"wol-control: {pattern % args}", flush=True)

            def send_json(self, status: int, payload: object) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = urlsplit(self.path).path
                if path == "/health":
                    self.send_json(200, {"status": "UP", "active": manager.current()})
                    return
                match = STATUS_PATH.fullmatch(path)
                if match is None:
                    self.send_json(404, {"error": "endpoint_no_encontrado"})
                    return
                request_id = unquote(match.group(1))
                if REQUEST_ID_PATTERN.fullmatch(request_id) is None:
                    self.send_json(400, {"error": "request_id_invalido"})
                    return
                try:
                    self.send_json(200, manager.get(request_id))
                except WakeOperationNotFound:
                    self.send_json(404, {"error": "operacion_no_encontrada"})

            def do_POST(self) -> None:
                if urlsplit(self.path).path != "/api/v1/wake":
                    self.send_json(404, {"error": "endpoint_no_encontrado"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_json(400, {"error": "content_length_invalido"})
                    return
                if length < 2 or length > 4096:
                    self.send_json(413, {"error": "cuerpo_fuera_de_rango"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self.send_json(400, {"error": "json_invalido"})
                    return
                if not isinstance(payload, dict) or set(payload) != {
                    "contract_version",
                    "request_id",
                }:
                    self.send_json(400, {"error": "contrato_de_solicitud_invalido"})
                    return
                if payload.get("contract_version") != 1:
                    self.send_json(400, {"error": "version_de_contrato_invalida"})
                    return
                try:
                    operation = manager.trigger(
                        str(payload.get("request_id") or ""),
                        "lechu-maintenance-http",
                    )
                except ValueError as exc:
                    self.send_json(400, {"error": str(exc)})
                    return
                except WakeOperationBusy as exc:
                    self.send_json(
                        409,
                        {"error": "wake_in_progress", "operation": exc.operation},
                    )
                    return
                self.send_json(202, operation)

        self.server = UnixThreadingServer(str(self.socket_path), Handler)
        os.chmod(self.socket_path, 0o660)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="wol-control-http",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.socket_path.unlink(missing_ok=True)
