import math
import time

import requests

from .clock import clock, iso

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
      edges { node {
        id location { id } dataStream { id unit }
        timestamp resolution value min max sd
      } }
    }
  }
}
"""


class SentryxError(RuntimeError):
    pass


class SentryxClient:
    def __init__(self, settings, client_id, client_secret, session=None):
        self.settings = settings
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self.token = None
        self.expires = 0

    def _token(self):
        if self.token and time.monotonic() < self.expires:
            return
        response = self.session.post("https://auth.api.sentryx.cloud/oauth2/token", data={
            "grant_type": "client_credentials", "scope": "https://inet.api.sentryx.cloud/read",
            "client_id": self.client_id, "client_secret": self.client_secret,
        }, timeout=self.settings.http_timeout_seconds)
        if not response.ok:
            raise SentryxError(f"Autenticación Sentryx: HTTP {response.status_code}")
        data = response.json()
        if not data.get("access_token"):
            raise SentryxError("Autenticación Sentryx sin token")
        self.token = data["access_token"]
        self.expires = time.monotonic() + max(1, int(data.get("expires_in", 3600)) - 60)

    def measurements(self, start, end):
        where = {"when": {"start": iso(start), "end": iso(end)},
                 "resolution": self.settings.resolution,
                 "locations": {"id": [x["id"] for x in self.settings.locations]},
                 "dataStreams": {"id": list(STREAMS)}}
        records, seen_cursors, after = [], set(), None
        while True:
            for attempt in range(2):
                self._token()
                response = self.session.post("https://inet.api.sentryx.cloud/graphql",
                    json={"query": QUERY, "variables": {"where": where,
                          "first": self.settings.page_size, "after": after}},
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.settings.http_timeout_seconds)
                if response.status_code != 401 or attempt:
                    break
                self.token = None
            if not response.ok:
                raise SentryxError(f"Consulta Sentryx: HTTP {response.status_code}")
            payload = response.json()
            if payload.get("errors"):
                # Surface the provider's generic error, never request headers or credentials.
                kinds = {str(e.get("errorType", "GraphQLError")) for e in payload["errors"]}
                raise SentryxError("Sentryx rechazó la consulta de mediciones: " + ", ".join(sorted(kinds)))
            try:
                connection = payload["data"]["locationTimeSeries"]["measuredAt"]
                edges, page = connection["edges"], connection["pageInfo"]
                if not isinstance(edges, list) or not isinstance(page["hasNextPage"], bool):
                    raise ValueError()
                for edge in edges:
                    node = edge["node"]
                    timestamp = clock.parse_preserving_subseconds(node["timestamp"])
                    if (node["location"]["id"] not in where["locations"]["id"]
                        or node["dataStream"]["id"] not in STREAMS
                        or node["resolution"] != self.settings.resolution
                        or not isinstance(node["id"], str) or not node["id"]
                        or not isinstance(node["dataStream"]["unit"], str)):
                        raise ValueError()
                    for key in ("value", "min", "max", "sd"):
                        value = node.get(key)
                        if (key == "value" or value is not None) and (
                            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                            raise ValueError()
                    if start <= timestamp <= end:
                        records.append({**node, "timestamp": iso(timestamp)})
                if not page["hasNextPage"]:
                    return records
                cursor = page["endCursor"]
                if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                    raise ValueError()
                seen_cursors.add(cursor)
                after = cursor
            except (KeyError, TypeError, ValueError):
                raise SentryxError("Respuesta o paginación Sentryx inválida") from None
