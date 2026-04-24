from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Dict, Optional


class Logosaurio:
    """Registrador central que evita repetir mensajes consecutivos por origen/nivel."""

    def __init__(self) -> None:
        self._last_messages: Dict[str, Optional[str]] = {}

    def _format_message(self, message: str, args: tuple) -> str:
        if not args:
            return str(message)
        try:
            return str(message) % args
        except Exception:
            joined = " ".join(str(arg) for arg in args)
            return f"{message} {joined}".strip()

    def _emit(self, level: str, message: str, origin: str, args: tuple, include_traceback: bool = False) -> None:
        normalized_level = str(level or "INFO").upper()
        normalized_origin = str(origin or "APP")
        formatted = self._format_message(message, args)
        if include_traceback:
            tb = traceback.format_exc()
            if tb and tb.strip() != "NoneType: None":
                formatted = f"{formatted}\n{tb.rstrip()}"
        dedupe_key = f"{normalized_origin}:{normalized_level}"
        last = self._last_messages.get(dedupe_key)
        if last == formatted:
            return
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        print(f"[{timestamp}] - [{normalized_level}] - [{normalized_origin}] - {formatted}")
        self._last_messages[dedupe_key] = formatted

    def log(self, message: str, origin: str = "APP", *args) -> None:
        self._emit("INFO", message, origin, args)

    def info(self, message: str, *args, origin: str = "APP") -> None:
        self._emit("INFO", message, origin, args)

    def debug(self, message: str, *args, origin: str = "APP") -> None:
        self._emit("DEBUG", message, origin, args)

    def warning(self, message: str, *args, origin: str = "APP") -> None:
        self._emit("WARNING", message, origin, args)

    def warn(self, message: str, *args, origin: str = "APP") -> None:
        self.warning(message, *args, origin=origin)

    def error(self, message: str, *args, origin: str = "APP") -> None:
        self._emit("ERROR", message, origin, args)

    def exception(self, message: str, *args, origin: str = "APP") -> None:
        self._emit("ERROR", message, origin, args, include_traceback=True)


logger = Logosaurio()
