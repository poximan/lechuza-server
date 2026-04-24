import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .catalog import ElementDescriptor


@dataclass
class ElementState:
    tag: str
    label: str
    voltage: str
    state: str = "desconocido"
    updated_at: Optional[str] = None
    raw_value: Optional[str] = None


class StateCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._states: Dict[str, ElementState] = {}

    async def sync_elements(self, elements: List[ElementDescriptor]) -> None:
        async with self._lock:
            desired = {element.tag for element in elements}
            for tag in list(self._states.keys()):
                if tag not in desired:
                    del self._states[tag]
            for descriptor in elements:
                if descriptor.tag not in self._states:
                    self._states[descriptor.tag] = ElementState(
                        tag=descriptor.tag,
                        label=descriptor.label,
                        voltage=descriptor.voltage,
                    )

    async def update(self, tag: str, raw_state: Optional[str], timestamp: Optional[str]) -> None:
        async with self._lock:
            state = self._states.get(tag)
            if not state:
                return
            parsed = _map_state(raw_state)
            state.state = parsed
            state.raw_value = raw_state
            state.updated_at = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")

    async def snapshot_by_tag(self) -> Dict[str, ElementState]:
        async with self._lock:
            return {tag: replace(state) for tag, state in self._states.items()}


def _map_state(raw_state: Optional[str]) -> str:
    if raw_state is None:
        return "desconocido"
    normalized = raw_state.strip().lower()
    if normalized in {"1", "cerrado", "closed"}:
        return "cerrado"
    if normalized in {"0", "abierto", "open"}:
        return "abierto"
    return "desconocido"
