from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from . import config as cfg
from .utils import timebox
from .logger import logger


class SnapshotRepository:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: Dict[str, Any] = {}
        self._path = self._resolve_path()
        self._load()

    def _resolve_path(self) -> str:
        os.makedirs(cfg.DATA_DIR, exist_ok=True)
        return os.path.join(cfg.DATA_DIR, cfg.STATE_FILE)

    def _load(self) -> None:
        with self._lock:
            try:
                if not os.path.exists(self._path):
                    return
                with open(self._path, "r", encoding="utf-8") as fh:
                    content = fh.read().strip()
                if not content:
                    return
                data = json.loads(content)
                if isinstance(data, dict):
                    self._snapshot = dict(data)
            except Exception as exc:
                logger.log(f"No se pudo cargar snapshot persistido: {exc}", "PVE/STORE")

    def _persist(self) -> None:
        tmp_path = f"{self._path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(self._snapshot, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._path)

    def store(self, snapshot: Dict[str, Any]) -> None:
        with self._lock:
            if not isinstance(snapshot, dict):
                logger.log(
                    f"Snapshot inválido recibido ({type(snapshot).__name__}), se descarta",
                    "PVE/STORE",
                )
                return
            self._snapshot = dict(snapshot)
            try:
                self._persist()
            except Exception as exc:
                logger.log(f"No se pudo persistir snapshot actual: {exc}", "PVE/STORE")

    def read(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._snapshot)

    def age_seconds(self) -> Optional[float]:
        with self._lock:
            ts = self._snapshot.get("ts")
        if not ts:
            return None
        try:
            snap_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
        return (datetime.now(timezone.utc) - snap_dt).total_seconds()
