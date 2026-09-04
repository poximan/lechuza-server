from flask import has_request_context, request

import config


class LechuNavigation:
    base_path = "/lechu"
    secure_mode = "secure"
    protected_mode = "protected"

    _items = (
        ("exemys", "/lechu/exemys", True),
        ("charito", "/lechu/charito", True),
        ("generadores", "/lechu/generadores", False),
        ("proxmox", "/lechu/proxmox", True),
        ("reles MiCOM", "/lechu/reles", False),
        ("mantenimiento", "/lechu/mantenimiento", True),
        ("mensagelo", "/lechu/mensagelo", True),
        ("broker", "/lechu/broker", True),
        ("correo", "/lechu/email", True),
    )

    def current_mode(self) -> str:
        if has_request_context() and request.headers.get("X-Edge-Mode") == self.protected_mode:
            return self.protected_mode
        return self.secure_mode

    def visible_items(self, mode: str) -> tuple[tuple[str, str, bool], ...]:
        if mode not in {self.secure_mode, self.protected_mode}:
            raise ValueError(f"Modo de navegacion desconocido: {mode}")
        return tuple(item for item in self._items if not item[2] or mode == self.protected_mode)

    def contract(self, mode: str) -> dict:
        return {
            "base_path": self.base_path,
            "mode": mode,
            "refresh_ms": config.LECHU_REFRESH_MS,
            "items": [
                {"label": label, "href": href, "protected": protected}
                for label, href, protected in self.visible_items(mode)
            ],
        }


lechu_navigation = LechuNavigation()
