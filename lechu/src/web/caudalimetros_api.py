from flask import jsonify, request
from src.web.clients.i20_client import I20ApiError


class CaudalimetrosApi:
    def __init__(self, client, response):
        self.client, self.response = client, response

    def get(self):
        return self.response(lambda: self.client.request("/api/caudalimetros"))

    def measurements(self):
        params = {key: request.args.get(key, "") for key in ("location_id", "start", "end")}
        if not all(params.values()):
            return jsonify({"error": "Se requieren location_id, start y end"}), 400
        return self.response(lambda: self.client.request("/api/measurements", params=params))

    def sync(self):
        if not request.is_json:
            return jsonify({"error": "Se requiere application/json"}), 415
        try:
            return jsonify(self.client.request("/api/sync", method="POST")), 202
        except I20ApiError as exc:
            return jsonify({"error": str(exc)}), exc.status
        except Exception:
            return jsonify({"error": "No se pudo contactar i20api-service"}), 502
