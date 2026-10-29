import math
import time

import requests

from .clock import clock, iso

TOKEN_URL = "https://auth.api.gwf.i2owater.com/oauth2/token"
READ_SCOPE = "https://inet.api.gwf.i2owater.com/read"
GRAPHQL_URL = "https://inet.api.gwf.i2owater.com/graphql"

STREAMS = {
    "urn:mwp:datastream:flow-rate": "Caudal",
    "urn:mwp:datastream:flow-volume": "Volumen de caudal",
    "urn:mwp:datastream:battery-voltage": "Voltaje de batería",
    "urn:mwp:datastream:external-voltage": "Voltaje externo",
}

QUERY = """
query Measurements($where: MeasuredAtFilterInput!, $first: Int!, $after: String) {
  locationTimeSeries {
    measuredAt(where: $where, first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { cursor node {
        id location { id } dataStream { id unit }
        timestamp resolution value min max sd
      } }
    }
  }
}
"""


class GwfError(RuntimeError):
    pass


class GwfClient:
    def __init__(self, settings, client_id, client_secret, session=None):
        self.settings = settings
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self.token = None
        self.expires = 0

    def _post(self, url, operation, **kwargs):
        try:
            return self.session.post(
                url, timeout=self.settings.http_timeout_seconds, **kwargs
            )
        except requests.Timeout:
            raise GwfError(f"{operation}: tiempo de espera agotado") from None
        except requests.RequestException:
            raise GwfError(f"{operation}: no se pudo conectar con GWF") from None

    @staticmethod
    def _json(response, operation):
        try:
            data = response.json()
        except ValueError:
            raise GwfError(f"{operation}: respuesta JSON inválida") from None
        if not isinstance(data, dict):
            raise GwfError(f"{operation}: la respuesta debe ser un objeto JSON")
        return data

    def _token(self):
        if self.token and time.monotonic() < self.expires:
            return
        response = self._post(TOKEN_URL, "Autenticación GWF", data={
            "grant_type": "client_credentials", "scope": READ_SCOPE,
            "client_id": self.client_id, "client_secret": self.client_secret,
        }, headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
        if not response.ok:
            raise GwfError(f"Autenticación GWF: HTTP {response.status_code}")
        data = self._json(response, "Autenticación GWF")
        token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not isinstance(token, str) or not token.strip():
            raise GwfError("Autenticación GWF sin token")
        if not isinstance(data.get("token_type"), str) or data["token_type"].lower() != "bearer":
            raise GwfError("Autenticación GWF: token_type debe ser Bearer")
        if type(expires_in) is not int or expires_in <= 0:
            raise GwfError("Autenticación GWF: expires_in debe ser un entero positivo")
        self.token = token
        self.expires = time.monotonic() + max(1, expires_in - 60)

    def _graphql_error(self, errors):
        if not isinstance(errors, list) or any(not isinstance(item, dict) for item in errors):
            return "GWF devolvió una lista de errores GraphQL inválida"
        details = []
        for error in errors:
            kind = error.get("errorType") or "GraphQLError"
            message = error.get("message")
            detail = f"{kind}: {message}" if message else str(kind)
            path = error.get("path")
            if isinstance(path, list):
                detail += " (" + ".".join(str(part) for part in path) + ")"
            # Mostrar el detalle del proveedor sin filtrar secretos a la interfaz.
            for secret in (self.client_id, self.client_secret, self.token):
                if secret:
                    detail = detail.replace(secret, "[omitido]")
            details.append(detail[:500])
        return "GWF rechazó la consulta de mediciones: " + " | ".join(details)

    def measurements(self, start, end):
        where = {"when": {"start": iso(start), "end": iso(end)},
                 "resolution": self.settings.resolution,
                 "locations": {"id": [x["id"] for x in self.settings.locations]},
                 "dataStreams": {"id": list(STREAMS)}}
        records, seen_cursors, after = [], set(), None
        while True:
            for attempt in range(2):
                self._token()
                response = self._post(GRAPHQL_URL, "Consulta GWF",
                    json={"query": QUERY, "variables": {"where": where,
                          "first": self.settings.page_size, "after": after}},
                    headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"})
                if response.status_code != 401 or attempt:
                    break
                self.token = None
            if not response.ok:
                raise GwfError(f"Consulta GWF: HTTP {response.status_code}")
            payload = self._json(response, "Consulta GWF")
            if payload.get("errors"):
                raise GwfError(self._graphql_error(payload["errors"]))
            try:
                connection = payload["data"]["locationTimeSeries"]["measuredAt"]
                edges, page = connection["edges"], connection["pageInfo"]
                if not isinstance(edges, list) or not isinstance(page["hasNextPage"], bool):
                    raise ValueError()
                for edge in edges:
                    node = edge["node"]
                    timestamp = clock.parse_preserving_subseconds(node["timestamp"])
                    resolution = node["resolution"]
                    if not isinstance(resolution, str):
                        raise ValueError()
                    # GWF responde pt15m/raw; el contrato local conserva PT15M/RAW.
                    resolution = resolution.upper()
                    if (node["location"]["id"] not in where["locations"]["id"]
                        or node["dataStream"]["id"] not in STREAMS
                        or resolution != self.settings.resolution
                        or not isinstance(node["id"], str) or not node["id"]
                        or not isinstance(node["dataStream"]["unit"], str)):
                        raise ValueError()
                    for key in ("value", "min", "max", "sd"):
                        value = node.get(key)
                        if (key == "value" or value is not None) and (
                            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                            raise ValueError()
                    if start <= timestamp <= end:
                        records.append({**node, "timestamp": iso(timestamp), "resolution": resolution})
                if not page["hasNextPage"]:
                    return records
                cursor = page["endCursor"]
                if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                    raise ValueError()
                seen_cursors.add(cursor)
                after = cursor
            except (KeyError, TypeError, ValueError):
                raise GwfError("Respuesta o paginación GWF inválida") from None
