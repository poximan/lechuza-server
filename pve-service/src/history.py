from copy import deepcopy
import math
import os
import json
import threading
from typing import Any, Dict, List, Tuple

from . import config as cfg
from src.utils import timebox
from .logger import logger

_LOCK = threading.RLock()
_HISTORY_CACHE: Dict[str, Any] | None = None


def _path(filename: str) -> str:
    os.makedirs(cfg.DATA_DIR, exist_ok=True)
    return os.path.join(cfg.DATA_DIR, filename)


def _read_json(filename: str, default: Dict[str, Any]) -> Dict[str, Any]:
    path = _path(filename)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("vms"), dict) or not isinstance(data.get("meta"), dict):
        raise ValueError(f"Historico invalido: {path}")
    return data


def _write_json(filename: str, data: Dict[str, Any]) -> None:
    tmp = _path(filename) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, _path(filename))


def _metric(vm, key):
    value = vm[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Metrica PVE invalida: vm={vm.get('vmid')} campo={key}")
    return float(value)


def _history() -> Dict[str, Any]:
    global _HISTORY_CACHE
    if _HISTORY_CACHE is None:
        _HISTORY_CACHE = _read_json(cfg.HISTORY_FILE, {"meta": {}, "vms": {}})
    return _HISTORY_CACHE


def update_history(snapshot: Dict[str, Any], poll_seconds: int, hours: int) -> Tuple[Dict[str, Any], int]:
    global _HISTORY_CACHE
    max_entries = int((hours * 3600 + poll_seconds - 1) / poll_seconds)
    with _LOCK:
        history = deepcopy(_history())
        history.setdefault("meta", {})
        history.setdefault("vms", {})
        history["meta"].update({"hours": hours, "poll_seconds": poll_seconds, "max_entries": max_entries})
        vms_section = history["vms"]
        ts = snapshot["ts"]
        timebox.parse(ts)
        for vm in snapshot["vms"]:
            vmid = str(int(vm["vmid"]))
            # Una VM sin metricas no produce una muestra numerica inventada.
            try:
                entry = {"ts": ts, "cpu": _metric(vm, "cpu_pct"),
                         "mem": _metric(vm, "mem_pct"), "disk": _metric(vm, "disk_pct")}
            except (KeyError, ValueError) as error:
                logger.log(f"Muestra historica rechazada VM {vmid}: {error}", "PVE/HISTORY")
                continue
            vm_rec = vms_section.setdefault(vmid, {"name": vm.get("name") or vmid, "history": []})
            vm_rec["name"] = vm.get("name") or vm_rec.get("name") or vmid
            lst = vm_rec.get("history") or []
            lst.insert(0, entry)
            if len(lst) > max_entries:
                lst = lst[:max_entries]
            vm_rec["history"] = lst
        _write_json(cfg.HISTORY_FILE, history)
        _HISTORY_CACHE = history
        return history, max_entries


def load_history_for_dashboard() -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    with _LOCK:
        history = _history()
        result: Dict[int, Dict[str, Any]] = {}
        for vmid_str, data in (history.get("vms") or {}).items():
            vmid = int(vmid_str)
            entries = data.get("history") or []
            prepared = {"cpu_pct": [], "mem_pct": [], "disk_pct": []}
            for item in reversed(entries):
                ts = item["ts"]
                timebox.parse(ts)
                prepared["cpu_pct"].append({"ts": ts, "value": item["cpu"]})
                prepared["mem_pct"].append({"ts": ts, "value": item["mem"]})
                prepared["disk_pct"].append({"ts": ts, "value": item["disk"]})
            result[vmid] = {"name": data.get("name"), "history": prepared}
        return result, dict(history.get("meta", {}))
