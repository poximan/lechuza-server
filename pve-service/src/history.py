import os
import json
import threading
from typing import Any, Dict, List, Tuple

from . import config as cfg
from src.utils import timebox

_LOCK = threading.RLock()


def _path(filename: str) -> str:
    os.makedirs(cfg.DATA_DIR, exist_ok=True)
    return os.path.join(cfg.DATA_DIR, filename)


def _read_json(filename: str, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        path = _path(filename)
        if not os.path.exists(path):
            return default
        content = open(path, "r", encoding="utf-8").read().strip()
        if not content:
            return default
        return json.loads(content)
    except Exception:
        return default


def _write_json(filename: str, data: Dict[str, Any]) -> None:
    try:
        tmp = _path(filename) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _path(filename))
    except Exception:
        pass


def update_history(snapshot: Dict[str, Any], poll_seconds: int, hours: int) -> Tuple[Dict[str, Any], int]:
    max_entries = int((hours * 3600 + poll_seconds - 1) / poll_seconds)
    with _LOCK:
        history = _read_json(cfg.HISTORY_FILE, {"meta": {}, "vms": {}})
        history.setdefault("meta", {})
        history.setdefault("vms", {})
        history["meta"].update({"hours": hours, "poll_seconds": poll_seconds, "max_entries": max_entries})
        vms_section = history["vms"]
        ts = snapshot.get("ts") or timebox.utc_iso()
        for vm in snapshot.get("vms", []):
            try:
                vmid = str(int(vm.get("vmid")))
            except Exception:
                continue
            entry = {
                "ts": ts,
                "cpu": float(vm.get("cpu_pct") or 0.0),
                "mem": float(vm.get("mem_pct") or 0.0) if vm.get("mem_pct") is not None else 0.0,
                "disk": float(vm.get("disk_pct") or 0.0) if vm.get("disk_pct") is not None else 0.0,
            }
            vm_rec = vms_section.setdefault(vmid, {"name": vm.get("name") or vmid, "history": []})
            vm_rec["name"] = vm.get("name") or vm_rec.get("name") or vmid
            lst = vm_rec.get("history") or []
            lst.insert(0, entry)
            if len(lst) > max_entries:
                lst = lst[:max_entries]
            vm_rec["history"] = lst
        _write_json(cfg.HISTORY_FILE, history)
        return history, max_entries


def load_history_for_dashboard() -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    with _LOCK:
        history = _read_json(cfg.HISTORY_FILE, {"meta": {}, "vms": {}})
    result: Dict[int, Dict[str, Any]] = {}
    for vmid_str, data in (history.get("vms") or {}).items():
        try:
            vmid = int(vmid_str)
        except Exception:
            continue
        entries = data.get("history") or []
        prepared = {"cpu_pct": [], "mem_pct": [], "disk_pct": []}
        for item in reversed(entries):
            ts = item.get("ts")
            if not ts:
                continue
            prepared["cpu_pct"].append({"ts": ts, "value": item.get("cpu", 0.0)})
            prepared["mem_pct"].append({"ts": ts, "value": item.get("mem", 0.0)})
            prepared["disk_pct"].append({"ts": ts, "value": item.get("disk", 0.0)})
        result[vmid] = {"name": data.get("name"), "history": prepared}
    return result, history.get("meta", {})
