from pathlib import Path
from typing import Any, Callable

from flask import jsonify, send_file


class TopologyApi:
    """Entrega el mapa privado de la instalacion tras autorizar cada solicitud."""

    def __init__(self, filename: str, require_protected: Callable[[], Any | None]):
        self.filename = Path(filename)
        self.require_protected = require_protected

    def get(self) -> Any:
        denied = self.require_protected()
        if denied is not None:
            return denied
        if not self.filename.is_file():
            return jsonify({"error": "topology_not_configured"}), 404
        response = send_file(self.filename, mimetype="image/png", conditional=False)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
