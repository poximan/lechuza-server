import asyncio
from typing import Any, Dict

import httpx
from urllib.parse import quote

from . import config


class DaemonClient:
    def __init__(self) -> None:
        self._base_url = config.SCADA_DAEMON_BASE_URL.rstrip("/")
        timeout_seconds = config.ADAPTER_QUERY_INTERVAL_SECONDS * 2
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_tag(self, tag: str) -> Dict[str, Any]:
        safe_tag = quote(tag, safe="")
        url = f"{self._base_url}/scada/tags/{safe_tag}"
        response = await self._client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"daemon respondio {response.status_code}: {response.text}")
        return response.json()

    async def fetch_tags_summary(self) -> Dict[str, Any]:
        url = f"{self._base_url}/scada/tags"
        response = await self._client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"daemon respondio {response.status_code}: {response.text}")
        return response.json()


daemon_client_singleton: DaemonClient | None = None


async def get_client() -> DaemonClient:
    global daemon_client_singleton
    if daemon_client_singleton is None:
        daemon_client_singleton = DaemonClient()
    return daemon_client_singleton


async def close_client() -> None:
    global daemon_client_singleton
    if daemon_client_singleton:
        await daemon_client_singleton.close()
        daemon_client_singleton = None
