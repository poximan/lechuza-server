from datetime import timedelta
from .alarm_time import _parse_instant, _iso


def condition_transition(state, active: bool, occurred_at: str) -> str:
    """Decide el ciclo de vida sin depender de SQL ni de infraestructura."""
    instant = _parse_instant(occurred_at)
    if state is None:
        return "condition_started" if active else "baseline_inactive"
    if instant < _parse_instant(state["condition_since_at"]):
        raise ValueError("Evento anterior a la condicion vigente")
    if bool(state["condition_active"]) == active:
        return "condition_repeated"
    transitions = {
        ("inactive", True): "condition_started",
        ("pending_start", False): "cancelled",
        ("active", False): "recovering",
        ("pending_end", True): "active_again",
    }
    key = (state["lifecycle_state"], active)
    if key not in transitions:
        raise ValueError(f"Transicion de alarma invalida: {key}")
    return transitions[key]


def due_transition(state, now_iso: str):
    """Devuelve la transicion vencida y su instante efectivo en UTC."""
    lifecycle = state["lifecycle_state"]
    if lifecycle not in {"pending_start", "pending_end"}:
        return None
    starting = lifecycle == "pending_start"
    delay = int(state["activation_seconds" if starting else "recovery_seconds"])
    deadline = _parse_instant(state["condition_since_at"]) + timedelta(seconds=delay)
    if _parse_instant(now_iso) < deadline:
        return None
    return ("activate" if starting else "resolve", _iso(deadline))
