import requests


class I20ApiError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__("Ya hay una sincronización en curso" if status == 409
                         else f"i20api-service respondió HTTP {status}")


class I20Client:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def request(self, path, *, method="GET", params=None):
        response = requests.request(method, self.base_url + path, params=params, timeout=5)
        if not response.ok:
            raise I20ApiError(response.status_code)
        return response.json()
