import os
import json
import threading
from typing import Any, Dict, Optional

# -------------------------
# resolucion de rutas base
# -------------------------

_OBSERVAR_LOCK = threading.RLock()
_CHARO_LOCK = threading.RLock()
_PROX_OBSERVAR_LOCK = threading.RLock()
_PROX_VIEW_VALUES = {"vivo", "historico"}
_DATA_DIR_ENV = "PANELEXEMYS_DATA_DIR"


def get_project_root() -> str:
    """
    retorna ruta absoluta a la raiz del proyecto
    """
    here = os.path.dirname(os.path.abspath(__file__))
    # utils -> src -> raiz
    return os.path.abspath(os.path.join(here, "..", ".."))


def get_servicios_dir() -> str:
    """
    retorna ruta absoluta al directorio src/servicios
    """
    return os.path.join(get_project_root(), "src", "servicios")


def get_data_dir() -> str:
    """
    retorna ruta absoluta al directorio persistente de panelexemys
    """
    configured = os.getenv(_DATA_DIR_ENV)
    if configured and configured.strip():
        return configured.strip()
    return os.path.join(get_project_root(), "data")


def get_legacy_observar_path() -> str:
    return os.path.join(get_servicios_dir(), "observar.json")


def get_legacy_proxmox_observar_path() -> str:
    return os.path.join(get_project_root(), "src", "web", "clients", "observar.json")


def get_observar_path() -> str:
    """
    retorna la ruta absoluta al estado operativo persistente de panelexemys
    """
    path = os.path.join(get_data_dir(), "observar.json")
    _seed_json_file(path, [
        os.path.join(get_data_dir(), "modbus-mw-state.json"),
        get_legacy_observar_path(),
    ])
    return path


def get_charo_state_path() -> str:
    """
    retorna la ruta absoluta a charo.json dentro de data/
    """
    return os.path.join(get_data_dir(), "charo.json")


def get_proxmox_observar_path() -> str:
    """
    retorna la ruta absoluta al estado persistente de Proxmox para la UI
    """
    path = os.path.join(get_data_dir(), "proxmox-observar.json")
    _seed_json_file(path, [get_legacy_proxmox_observar_path()])
    return path


# -------------------------
# helpers json genericos
# -------------------------


def _ensure_parent_dir(path: str) -> None:
    """
    asegura existencia del directorio padre
    """
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _load_json_file(path: str) -> Dict[str, Any]:
    """
    carga json de disco; si no existe o esta vacio retorna {}
    """
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception:
        return {}


def _seed_json_file(target_path: str, legacy_paths: list[str]) -> None:
    if os.path.exists(target_path):
        return

    merged: Dict[str, Any] = {}
    for legacy_path in legacy_paths:
        if os.path.abspath(legacy_path) == os.path.abspath(target_path):
            continue
        data = _load_json_file(legacy_path)
        if isinstance(data, dict) and data:
            merged.update(data)

    if not merged:
        return

    try:
        _ensure_parent_dir(target_path)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def _save_json_file(path: str, data: Dict[str, Any]) -> bool:
    """
    persiste dict como json; retorna True si tuvo exito
    """
    try:
        _ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False


# -------------------------
# api especifica observar.json
# -------------------------


def load_observar() -> Dict[str, Any]:
    """
    retorna todo el contenido de observar.json como dict
    """
    with _OBSERVAR_LOCK:
        return _load_json_file(get_observar_path())


def save_observar(data: Dict[str, Any]) -> bool:
    """
    guarda el dict completo en observar.json
    """
    with _OBSERVAR_LOCK:
        return _save_json_file(get_observar_path(), data)


def load_observar_key(key: str, default: Optional[Any] = None) -> Any:
    """
    retorna el valor de una clave en observar.json o default si no existe
    """
    data = load_observar()
    return data.get(key, default)


def update_observar_key(key: str, value: Any) -> bool:
    """
    actualiza una clave en observar.json preservando el resto
    """
    with _OBSERVAR_LOCK:
        path = get_observar_path()
        data = _load_json_file(path)
        data[key] = value
        return _save_json_file(path, data)


# -------------------------
# api especifica charo.json
# -------------------------


def load_charo_state() -> Dict[str, Any]:
    """
    retorna el contenido de charo.json como dict
    """
    with _CHARO_LOCK:
        return _load_json_file(get_charo_state_path())


def save_charo_state(data: Dict[str, Any]) -> bool:
    """
    persiste el estado completo en charo.json
    """
    with _CHARO_LOCK:
        return _save_json_file(get_charo_state_path(), data)


def load_proxmox_observar() -> Dict[str, Any]:
    """
    retorna el contenido del snapshot de proxmox
    """
    with _PROX_OBSERVAR_LOCK:
        return _load_json_file(get_proxmox_observar_path())


def save_proxmox_observar(data: Dict[str, Any]) -> bool:
    """
    persiste el snapshot de proxmox completo
    """
    with _PROX_OBSERVAR_LOCK:
        return _save_json_file(get_proxmox_observar_path(), data)


def load_proxmox_state(default: Optional[Any] = None) -> Any:
    """
    retorna el valor de la clave proxmox_estado en el snapshot dedicado
    """
    data = load_proxmox_observar()
    return data.get("proxmox_estado", default)


def update_proxmox_state(snapshot: Any) -> bool:
    """
    actualiza la clave proxmox_estado
    """
    with _PROX_OBSERVAR_LOCK:
        path = get_proxmox_observar_path()
        data = _load_json_file(path)
        data["proxmox_estado"] = snapshot
        return _save_json_file(path, data)


def load_proxmox_view_preference(default: str = "historico") -> str:
    pref = str(load_proxmox_observar().get("proxmox_vistadefault", default)).strip().lower()
    if pref not in _PROX_VIEW_VALUES:
        pref = default if default in _PROX_VIEW_VALUES else "historico"
    return pref


def update_proxmox_view_preference(preference: str) -> bool:
    normalized = str(preference).strip().lower()
    if normalized not in _PROX_VIEW_VALUES:
        raise ValueError("proxmox_vistadefault debe ser 'vivo' o 'historico'")
    with _PROX_OBSERVAR_LOCK:
        path = get_proxmox_observar_path()
        data = _load_json_file(path)
        data["proxmox_vistadefault"] = normalized
        return _save_json_file(path, data)
