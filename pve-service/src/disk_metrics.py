"""Capacidades configuradas y ocupacion medida son datos distintos.

Los sistemas de archivos del agente pueden abarcar varios discos (LVM/RAID).
Se conservan por volumen y nunca se atribuyen por posicion a un disco de QEMU.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any


def byte_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        return None
    return int(value) if value >= 0 else None


def capacity(value: str) -> int | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGTPE]?)(?:i?B)?", value, re.IGNORECASE)
    if match is None:
        return None
    try:
        amount = Decimal(match[1]) * (1024 ** (' KMGTPE'.index(match[2].upper()) if match[2] else 0))
        return int(amount) if amount == amount.to_integral_value() else None
    except (InvalidOperation, ValueError):
        return None


def usage(used: Any, total: Any, available: Any = None) -> dict[str, Any]:
    used_bytes, total_bytes = byte_count(used), byte_count(total)
    free_bytes = byte_count(available)
    if free_bytes is None and used_bytes is not None and total_bytes is not None:
        free_bytes = max(0, total_bytes - used_bytes)
    return {
        'used_bytes': used_bytes,
        'total_bytes': total_bytes,
        'available_bytes': free_bytes,
        'used_pct': round(used_bytes / total_bytes * 100, 2)
        if used_bytes is not None and total_bytes else None,
    }


def configured_disks(config: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for identifier, raw in config.items():
        if not re.fullmatch(r'(?:scsi|virtio|sata|ide)\d+', identifier) or not isinstance(raw, str):
            continue
        parts = raw.split(',')
        options = dict(part.split('=', 1) for part in parts[1:] if '=' in part)
        volume = parts[0].removeprefix('file=')
        if volume in {'none', 'cdrom', ''} or options.get('media') == 'cdrom':
            continue
        result.append({'id': identifier, 'volume': volume,
                       'total_bytes': capacity(options.get('size', ''))})
    return sorted(result, key=lambda disk: (re.sub(r'\d+$', '', disk['id']), int(re.search(r'\d+$', disk['id'])[0])))


def agent_enabled(config: dict[str, Any]) -> bool:
    raw = str(config.get('agent', '0'))
    first = raw.split(',')[0].removeprefix('enabled=').lower()
    return first in {'1', 'true', 'yes', 'on'}


def guest_filesystems(data: Any) -> list[dict[str, Any]]:
    # Proxmox envuelve el resultado de guest-get-fsinfo dentro de data.result.
    if not isinstance(data, dict) or not isinstance(data.get('result'), list):
        raise ValueError('El agente no devolvió una lista de volúmenes')
    result = []
    seen = set()
    for row in data['result']:
        if not isinstance(row, dict) or not all(isinstance(row.get(key), str) for key in ('name', 'mountpoint', 'type')):
            raise ValueError('Volumen del agente inválido')
        identity = row['name'], row['mountpoint']
        if identity in seen:
            continue
        seen.add(identity)
        devices = []
        for disk in row.get('disk', []):
            if not isinstance(disk, dict):
                continue
            devices.append({key: disk[key] for key in ('dev', 'serial', 'bus-type', 'bus', 'target', 'unit')
                            if key in disk and isinstance(disk[key], (str, int))})
        result.append({'name': row['name'], 'mountpoint': row['mountpoint'], 'type': row['type'],
                       'devices': devices,
                       **usage(row.get('used-bytes'), row.get('total-bytes-privileged', row.get('total-bytes')))})
    return sorted(result, key=lambda row: (row['mountpoint'], row['name']))


def host_storages(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError('La API no devolvió una lista de almacenamientos')
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('storage'), str):
            raise ValueError('Almacenamiento Proxmox inválido')
        if not row.get('enabled'):
            continue
        result.append({'id': row['storage'], 'type': row.get('type'), 'shared': bool(row.get('shared')),
                       'active': bool(row.get('active')), **usage(row.get('used'), row.get('total'), row.get('avail'))})
    return sorted(result, key=lambda row: row['id'])
