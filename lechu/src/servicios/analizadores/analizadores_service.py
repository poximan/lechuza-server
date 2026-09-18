class AnalizadoresService:
    def __init__(self,client): self.client=client
    def get_contract(self): return self.client.get_analyzers()
