import threading
from src.utils import timebox
from src.web.clients.domain_http_client import DomainHttpClient
import config

class GrdClient:
    def __init__(self):
        self.http=DomainHttpClient(config.GRD_COLLECTOR_API_BASE,config.MODBUS_COLLECTOR_HTTP_TIMEOUT); self.lock=threading.RLock(); self.cache=None; self.cache_ts=0.0
    def get_descriptions(self):
        with self.lock:
            now=timebox.monotonic()
            if self.cache is None or now-self.cache_ts>=300:
                items=self.http.request("GET","/api/grd/descriptions").get("items") or {}; self.cache={int(k):str(v) for k,v in items.items()}; self.cache_ts=now
            return self.cache
    def get_summary(self): return self.http.request("GET","/api/grd/summary")
    def get_history(self,grd_id,window,page): return self.http.request("GET","/api/grd/history",params={"grd_id":grd_id,"window":window,"page":page})
    def get_outages(self,grd_id,limit=10): return self.http.request("GET","/api/grd/outages",params={"grd_id":grd_id,"limit":limit})
grd_client=GrdClient()
