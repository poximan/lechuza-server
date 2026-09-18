import config
from src.web.clients.domain_http_client import DomainHttpClient
class JanitzaClient:
    def __init__(self): self.http=DomainHttpClient(config.JANITZA_COLLECTOR_API_BASE,config.MODBUS_COLLECTOR_HTTP_TIMEOUT)
    def get_analyzers(self): return self.http.request("GET","/api/analizadores")
janitza_client=JanitzaClient()
