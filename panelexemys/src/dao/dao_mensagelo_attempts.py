from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any

from src.utils import timebox


_MAX_ITEMS = 10
_items: deque[dict[str, Any]] = deque(maxlen=_MAX_ITEMS)
_lock = Lock()


def record_mensagelo_attempt(
    *,
    ok: bool,
    recipients: list[str],
    subject: str,
    body: str,
    message_type: str | None,
    detail: str,
) -> None:
    item: dict[str, Any] = {
        "ts": timebox.utc_iso(),
        "ok": bool(ok),
        "recipients": list(recipients or []),
        "subject": str(subject or ""),
        "body": str(body or ""),
        "message_type": message_type or "",
        "detail": str(detail or ""),
    }
    with _lock:
        _items.appendleft(item)


class MensageloAttemptsDao:
    def latest(self) -> list[dict[str, Any]]:
        with _lock:
            return list(_items)
