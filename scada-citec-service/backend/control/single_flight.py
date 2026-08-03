import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


class AsyncSingleFlight:
    """Serializa una operacion y expone si ya existe una ejecucion activa."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            return await operation()

