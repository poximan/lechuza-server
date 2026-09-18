import requests

class DomainHttpClient:
    def __init__(self,base_url:str,timeout:int):
        self.base_url=base_url.rstrip("/"); self.timeout=timeout; self.session=requests.Session()
    def request(self,method:str,path:str,*,body=None,params=None,timeout=None):
        response=self.session.request(method,f"{self.base_url}{path}",json=body,params=params,timeout=timeout or self.timeout)
        response.raise_for_status(); payload=response.json()
        if not isinstance(payload,dict): raise RuntimeError(f"Contrato HTTP invalido en {path}")
        return payload
