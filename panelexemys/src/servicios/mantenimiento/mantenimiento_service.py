from __future__ import annotations

from typing import Any

from src.dao.dao_mantenimiento import MantenimientoDao
from src.negocio.mantenimiento import CatalogoMantenimiento


class MantenimientoService:
    def __init__(
        self,
        dao: MantenimientoDao,
        public_base_url: str,
        topology_url: str,
    ):
        if not public_base_url:
            raise ValueError("public_base_url es obligatorio")
        if not topology_url.startswith("/"):
            raise ValueError("topology_url debe comenzar con /")
        self.dao = dao
        self.public_base_url = public_base_url.rstrip("/")
        self.topology_url = topology_url

    def get_contract(self) -> dict[str, Any]:
        catalog = CatalogoMantenimiento.from_source(self.dao.load_source())
        return {
            "topologia": {
                "url": self.topology_url,
                "descripcion": "Topología de la red de comunicaciones",
            },
            "telefonos": {
                group: [
                    {
                        "numero": phone.numero,
                        **(
                            {"comentario": phone.comentario}
                            if phone.comentario is not None
                            else {}
                        ),
                    }
                    for phone in phones
                ]
                for group, phones in catalog.telefonos.items()
            },
            "port_mappings": [
                {
                    "servicio": item.servicio,
                    "interno": item.interno,
                    "externo": f"{self.public_base_url}{item.externo_path}",
                    "localhost": item.localhost,
                }
                for item in catalog.port_mappings
            ],
        }
