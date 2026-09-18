import json
import os
import tempfile
from pathlib import Path

from timeauthority import get_time_authority


_TIME = get_time_authority()


class ConnectionStateStore:
    def __init__(self, path: str, ip: str, port: int) -> None:
        self.path = Path(path)
        self.ip = ip
        self.port = port

    def load(self) -> dict:
        if not self.path.is_file():
            return self._unknown()
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("Estado persistido del modem invalido")
        if value.get("ip") != self.ip or value.get("port") != self.port:
            return self._unknown()
        if value.get("state") not in {"abierto", "cerrado", "desconocido"}:
            raise RuntimeError("Estado persistido del modem fuera de contrato")
        _TIME.parse(str(value.get("ts")))
        return dict(value)

    def save(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                delete=False,
            ) as handle:
                temporary = handle.name
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.remove(temporary)

    def _unknown(self) -> dict:
        return {
            "ip": self.ip,
            "port": self.port,
            "state": "desconocido",
            "ts": _TIME.utc_iso(),
        }
