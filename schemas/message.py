from pydantic import BaseModel
from typing import Optional

class MessageCreate(BaseModel):
    text: str
    attachment_id: Optional[str] = None