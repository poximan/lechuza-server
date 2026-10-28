from __future__ import annotations

import requests
import urllib3
from typing import Any, Dict, List, Tuple
from urllib3.exceptions import InsecureRequestWarning

from . import config as cfg
from .logger import logger
from .disk_metrics import agent_enabled, configured_disks, guest_filesystems, host_storages, usage
from .utils import timebox


class PveCollector:
    """
    Encapsula la interacción con la API de Proxmox.
    """

    def __init__(self) -> None:
        # recrear explicitamente la sesion para evitar residuos entre builds
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
            urllib3.disable_warnings(InsecureRequestWarning)
            self._verify_target = False

    def _fetch_qemu(self) -> List[Dict[str, Any]]:
        data = self._get(f"/nodes/{cfg.PVE_NODE_NAME}/qemu")
        return data if isinstance(data, list) else []

    def _get(self, path: str) -> Any:
        url = f"{cfg.PVE_BASE_URL.rstrip('/')}{path}"
        response = self._session.get(
            url,
            headers=self._headers,
            timeout=cfg.PVE_HTTP_TIMEOUT_SECONDS,
            verify=self._verify_target,
        )
        response.raise_for_status()
        return response.json().get("data")

    def _fetch_status(self, vmid: int) -> Dict[str, Any]:
        data = self._get(f"/nodes/{cfg.PVE_NODE_NAME}/qemu/{vmid}/status/current")
        return data if isinstance(data, dict) else {}

    def _guest_disks(self, vmid: int, running: bool) -> Dict[str, Any]:
        result: Dict[str, Any] = {'virtual_disks': [], 'filesystems': [],
                                  'disk_usage_status': 'unavailable', 'disk_usage_error': None}
        try:
            config = self._get(f"/nodes/{cfg.PVE_NODE_NAME}/qemu/{vmid}/config")
            if not isinstance(config, dict):
                raise ValueError('Configuración de discos inválida')
            result['virtual_disks'] = configured_disks(config)
        except Exception:
            result.update(disk_usage_status='config_unavailable',
                          disk_usage_error='No se pudo consultar la configuración de los discos de esta VM.')
            return result
        if not running:
            result.update(disk_usage_status='stopped', disk_usage_error='Esta VM está detenida. La ocupación de sus discos no está disponible.')
            return result
        if not agent_enabled(config):
            result.update(disk_usage_status='agent_disabled',
                          disk_usage_error='QEMU Guest Agent está deshabilitado en esta VM. Habilitalo en sus opciones de Proxmox.')
            return result
        try:
            result['filesystems'] = guest_filesystems(self._get(f"/nodes/{cfg.PVE_NODE_NAME}/qemu/{vmid}/agent/get-fsinfo"))
            complete = bool(result['filesystems']) and all(fs['used_pct'] is not None for fs in result['filesystems'])
            result['disk_usage_status'] = 'ok' if complete else 'partial'
            if not complete:
                result['disk_usage_error'] = 'El agente de esta VM no informó la ocupación de todos sus volúmenes.'
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                result.update(disk_usage_status='permission_denied',
                              disk_usage_error='Proxmox rechazó la consulta: falta el permiso VM.Monitor en el token para esta VM.')
            else:
                result.update(disk_usage_status='agent_unavailable',
                              disk_usage_error='El agente de esta VM no respondió. Comprobá que QEMU Guest Agent esté instalado y en ejecución dentro de ella.')
        except Exception:
            result.update(disk_usage_status='agent_unavailable',
                          disk_usage_error='No se pudo obtener una medición válida del agente de esta VM.')
        return result

    def _host_storage(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {'rootfs': None, 'storages': [], 'errors': []}
        try:
            node = self._get(f"/nodes/{cfg.PVE_NODE_NAME}/status")
            root = node['rootfs']
            if not isinstance(root, dict):
                raise ValueError('Disco raíz inválido')
            result['rootfs'] = usage(root.get('used'), root.get('total'), root.get('avail'))
        except Exception:
            result['errors'].append('No se pudo consultar el disco del sistema del hipervisor.')
        try:
            result['storages'] = host_storages(self._get(f"/nodes/{cfg.PVE_NODE_NAME}/storage"))
        except Exception:
            result['errors'].append('No se pudo consultar el uso de los almacenamientos de Proxmox.')
        return result

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
            disk_total = float(status.get("maxdisk") or row.get("maxdisk") or 0.0)
            read_b = float(status.get("diskread") or row.get("diskread") or 0.0)
            write_b = float(status.get("diskwrite") or row.get("diskwrite") or 0.0)

            cpu_fraction = status.get("cpu", row.get("cpu"))
            cpu_pct = round(float(cpu_fraction or 0.0) * 100.0, 2)
            mem_pct = (mem_used_raw / mem_max_raw) * 100.0 if mem_max_raw > 0 else None
            disks = self._guest_disks(vmid, row.get('status') == 'running')

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
                    # QEMU status.disk=0 no mide el espacio ocupado dentro de la VM.
                    "disk_pct": None,
                    **disks,
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
            "host_storage": self._host_storage(),
        }
        return snapshot, {}
