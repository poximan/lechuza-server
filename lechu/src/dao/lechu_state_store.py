from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


_LOCK = threading.RLock()
_DATA_DIR_ENV = "LECHU_DATA_DIR"


def _state_path() -> Path:
    configured = os.getenv(_DATA_DIR_ENV)
    if configured is None or not configured.strip():
        raise EnvironmentError(
            f"Falta variable de entorno obligatoria: {_DATA_DIR_ENV}"
        )
    return Path(configured.strip()) / "lechu-state.json"


def _load() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer el estado de lechu: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"El estado de lechu no es un objeto JSON: {path}")
    return value


def read_value(key: str) -> Any:
    with _LOCK:
        return _load().get(key)


def write_value(key: str, value: Any) -> None:
    with _LOCK:
        path = _state_path()
        state = _load()
        state[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
