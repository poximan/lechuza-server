from pydantic import BaseModel, Field, model_validator


class ReadRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=64)
    caller: str = Field(min_length=1, max_length=64)
    function_code: int
    unit_id: int = Field(ge=0, le=255)
    address: int = Field(ge=0, le=65535)
    count: int = Field(ge=1, le=125)

    @model_validator(mode="after")
    def validate_register_range(self) -> "ReadRequest":
        if self.function_code not in {3, 4}:
            raise ValueError("function_code debe ser 3 o 4")
        if self.address + self.count > 65536:
            raise ValueError("El rango de registros excede el mapa Modbus")
        return self


class ConnectRequest(BaseModel):
    caller: str = Field(min_length=1, max_length=64)
