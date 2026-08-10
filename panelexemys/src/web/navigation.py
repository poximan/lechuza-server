from flask import has_request_context, request


class PanelexemysNavigation:
    base_path = "/dash"
    secure_mode = "secure"
    protected_mode = "protected"

    _items = (
        ("dash exemys", "/dash", False),
        ("charito", "/dash/charito", False),
        ("generadores", "/dash/generadores", False),
        ("proxmox", "/dash/proxmox", False),
        ("reles MiCOM", "/dash/reles", True),
        ("mantenimiento", "/dash/mantenimiento", True),
        ("mensagelo", "/dash/mensagelo", True),
        ("broker", "/dash/broker", True),
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
            "items": [
                {"label": label, "href": href, "protected": protected}
                for label, href, protected in self.visible_items(mode)
            ],
        }


panelexemys_navigation = PanelexemysNavigation()
