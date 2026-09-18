import config
from src.web.clients.domain_http_client import DomainHttpClient
class GeneratorClient:
    def __init__(self): self.http=DomainHttpClient(config.GENERATOR_COLLECTOR_API_BASE,config.MODBUS_COLLECTOR_HTTP_TIMEOUT)
    def get_ge_status(self): return self.get_ge_edif_estivariz_status()
    def get_ge_edif_estivariz_status(self): return self.http.request("GET","/api/ge/edif-estivariz/status")
    def get_ge_edif_fontana_status(self): return self.http.request("GET","/api/ge/edif-fontana/status")
generator_client=GeneratorClient()
