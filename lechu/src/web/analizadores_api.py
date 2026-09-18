class AnalizadoresApi:
    def __init__(self,service,response): self.service=service; self.response=response
    def get(self): return self.response(self.service.get_contract)
