import requests
import config


class GrupoElectrogenoClient:
    """
    Cliente HTTP para recuperar el estado de marcha/parada del grupo electrГіgeno
    expuesto por modbus-mw-service.
    """

    def __init__(self) -> None:
        self.base_url = config.MODBUS_MW_API_BASE.rstrip("/")
        self.timeout = int(config.MODBUS_MW_HTTP_TIMEOUT)
        self._session = requests.Session()

    def get_status(self) -> dict:
        url = f"{self.base_url}/api/ge/status"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or "estado" not in data:
            raise ValueError("Respuesta invalida desde /api/ge/status")
        return {
            "estado": str(data.get("estado", "desconocido")),
            "ts": str(data.get("ts", "")),
        }


group_elect_client = GrupoElectrogenoClient()
