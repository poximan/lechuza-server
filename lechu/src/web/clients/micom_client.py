import config
from src.web.clients.domain_http_client import DomainHttpClient
class MicomClient:
    def __init__(self): self.http=DomainHttpClient(config.MICOM_COLLECTOR_API_BASE,config.MODBUS_COLLECTOR_HTTP_TIMEOUT)
    def get_reles_faults(self): return self.http.request("GET","/api/reles/faults")
    def get_rele_disturbances(self,relay_id): return self.http.request("GET",f"/api/reles/{relay_id}/disturbances")
    def get_rele_disturbance(self,relay_id,record_number): return self.http.request("GET",f"/api/reles/{relay_id}/disturbances/{record_number}")
    def read_rele_clock(self,relay_id): return self.http.request("POST",f"/api/reles/{relay_id}/clock-snapshot",body={},timeout=config.MODBUS_COLLECTOR_RELAY_HTTP_TIMEOUT)
    def get_reles_observer(self): return bool(self.http.request("GET","/api/reles/observer").get("enabled"))
    def set_reles_observer(self,enabled): return bool(self.http.request("POST","/api/reles/observer",body={"enabled":bool(enabled)}).get("enabled"))
micom_client=MicomClient()
