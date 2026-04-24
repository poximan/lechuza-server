from __future__ import annotations

import requests
from typing import Any, Dict, List, Tuple

from . import config as cfg
from .logger import logger
from .utils import timebox


class PveCollector:
    """
    Encapsula la interacción con la API de Proxmox.
    """

    def __init__(self) -> None:
        # recrear explícitamente la sesión para evitar residuos entre builds
        self._session = requests.Session()
        token = cfg.PVE_API_TOKEN
        self._token = token if token.lower().startswith("pveapitoken") else f"PVEAPIToken={token}"
        self._headers = {"Authorization": self._token}

        if cfg.PVE_VERIFY_SSL:
            self._verify_target = cfg.PVE_CA_BUNDLE or True
        else:
            logger.log(
                "PVE_VERIFY_SSL=false: se deshabilita la verificación TLS (no recomendado)",
                "PVE/COLLECT",
            )
            self._verify_target = False

    def _fetch_qemu(self) -> List[Dict[str, Any]]:
        url = f"{cfg.PVE_BASE_URL.rstrip('/')}/nodes/{cfg.PVE_NODE_NAME}/qemu"
        response = self._session.get(
            url,
            headers=self._headers,
            timeout=cfg.PVE_HTTP_TIMEOUT_SECONDS,
            verify=self._verify_target,
        )
        response.raise_for_status()
        data = response.json().get("data")
        return data if isinstance(data, list) else []

    def _fetch_status(self, vmid: int) -> Dict[str, Any]:
        url = f"{cfg.PVE_BASE_URL.rstrip('/')}/nodes/{cfg.PVE_NODE_NAME}/qemu/{vmid}/status/current"
        response = self._session.get(
            url,
            headers=self._headers,
            timeout=cfg.PVE_HTTP_TIMEOUT_SECONDS,
            verify=self._verify_target,
        )
        response.raise_for_status()
        data = response.json().get("data")
        return data if isinstance(data, dict) else {}

    def collect(self) -> Tuple[Dict[str, Any], Dict[int, Tuple[float, float]]]:
        qemus = self._fetch_qemu()
        vm_by_id = {int(item.get("vmid")): item for item in qemus if "vmid" in item}
        vms: List[Dict[str, Any]] = []
        missing: List[int] = []

        for vmid in cfg.PVE_VHOST_IDS:
            row = vm_by_id.get(vmid)
            if not row:
                missing.append(vmid)
                continue
            try:
                status = self._fetch_status(vmid)
            except Exception as exc:  # pragma: no cover - solo logging
                logger.log(f"Error obteniendo status VM {vmid}: {exc}", "PVE/COLLECT")
                status = {"_status_error": str(exc)}

            mem_used_raw = float(status.get("mem") or row.get("mem") or 0.0)
            mem_max_raw = float(status.get("maxmem") or row.get("maxmem") or 0.0)
            disk_used = float(status.get("disk") or row.get("disk") or 0.0)
            disk_total = float(status.get("maxdisk") or row.get("maxdisk") or 0.0)
            read_b = float(status.get("diskread") or row.get("diskread") or 0.0)
            write_b = float(status.get("diskwrite") or row.get("diskwrite") or 0.0)

            cpu_fraction = status.get("cpu", row.get("cpu"))
            cpu_pct = round(float(cpu_fraction or 0.0) * 100.0, 2)
            mem_pct = (mem_used_raw / mem_max_raw) * 100.0 if mem_max_raw > 0 else None
            disk_pct = (disk_used / disk_total) * 100.0 if disk_total > 0 else None

            vms.append(
                {
                    "vmid": vmid,
                    "name": row.get("name") or f"VM-{vmid}",
                    "status": row.get("status") or "desconocido",
                    "cpus": int(row.get("cpus") or 0),
                    "cpu_pct": cpu_pct,
                    "mem_used_gb": round(mem_used_raw / (1024**3), 2),
                    "mem_total_gb": round(mem_max_raw / (1024**3), 2),
                    "mem_pct": round(mem_pct, 2) if mem_pct is not None else None,
                    "disk_total_gb": round(disk_total / (1024**3), 2),
                    "disk_read_bytes": read_b,
                    "disk_write_bytes": write_b,
                    "disk_pct": round(disk_pct, 2) if disk_pct is not None else None,
                    "uptime_human": row.get("uptime_human", "0m"),
                }
            )

        snapshot = {
            "ts": timebox.utc_iso(),
            "node": cfg.PVE_NODE_NAME,
            "status": "online",
            "vms": vms,
            "missing": missing,
            "error": None,
        }
        return snapshot, {}
