from collections import deque
from threading import Lock
from typing import Any, Dict, List

from src.utils import timebox

_MAX_ITEMS = 10
_items = deque(maxlen=_MAX_ITEMS)
_lock = Lock()


def record_mensagelo_attempt(
    *,
    ok: bool,
    recipients: List[str],
    subject: str,
    body: str,
    message_type: str | None,
    detail: str,
) -> None:
    item: Dict[str, Any] = {
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


def get_mensagelo_attempts() -> List[Dict[str, Any]]:
    with _lock:
        return list(_items)
