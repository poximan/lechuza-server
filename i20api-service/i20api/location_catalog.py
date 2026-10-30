from .clock import clock, iso


class LocationCatalogError(RuntimeError):
    pass


class LocationCatalog:
    """Publica el catalogo de GWF desde persistencia local, sin hacer HTTP."""

    KEY = "location_catalog"

    def __init__(self, settings, storage):
        self.settings = settings
        self.storage = storage
        self._read()

    @staticmethod
    def _validate_locations(locations):
        if not isinstance(locations, list):
            raise LocationCatalogError("El catálogo de GWF debe ser una lista")
        seen = set()
        result = []
        for item in locations:
            if (not isinstance(item, dict)
                or not isinstance(item.get("id"), str) or not item["id"].strip()
                or not isinstance(item.get("name"), str) or not item["name"].strip()
                or item["id"] in seen):
                raise LocationCatalogError("El catálogo de GWF contiene ubicaciones inválidas o duplicadas")
            seen.add(item["id"])
            result.append({"id": item["id"], "name": item["name"]})
        return result

    def _selected(self, available):
        if self.settings.location_mode == "all":
            return available
        ids = {item["id"] for item in self.settings.locations}
        missing = ids - {item["id"] for item in available}
        if missing:
            raise LocationCatalogError("Las ubicaciones configuradas no están disponibles en GWF: " + ", ".join(sorted(missing)))
        return [item for item in available if item["id"] in ids]

    def _read(self):
        persisted = self.storage.get(self.KEY)
        if persisted is None:
            return None
        if (not isinstance(persisted, dict) or type(persisted.get("version")) is not int or persisted["version"] != 1
            or not isinstance(persisted.get("updated_at"), str)
            or not persisted["updated_at"].endswith("Z")):
            raise LocationCatalogError("El catálogo persistido de GWF es inválido")
        try:
            clock.parse(persisted["updated_at"])
        except (ValueError, TypeError):
            raise LocationCatalogError("La fecha UTC del catálogo persistido de GWF es inválida") from None
        locations = self._validate_locations(persisted.get("locations"))
        return {"locations": locations, "updated_at": persisted["updated_at"]}

    def snapshot(self):
        persisted = self._read()
        if persisted is None:
            return {"locations": [], "catalog": {
                "mode": self.settings.location_mode, "state": "pending", "updated_at": None,
            }}
        return {"locations": self._selected(persisted["locations"]), "catalog": {
            "mode": self.settings.location_mode, "state": "available",
            "updated_at": persisted["updated_at"],
        }}

    def replace(self, locations, updated_at):
        self._read()
        available = self._validate_locations(locations)
        selected = self._selected(available)
        self.storage.put(self.KEY, {"version": 1, "updated_at": iso(updated_at), "locations": available})
        return selected
