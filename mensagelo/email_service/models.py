from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional

class SendRequest(BaseModel):
    recipients: List[EmailStr] = Field(min_items=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    message_type: Optional[str] = None

class SendResponse(BaseModel):
    ok: bool
    queued: bool = False
    message: str
    id: Optional[str] = None  # si quisieras asignar IDs de cola en el futuro.