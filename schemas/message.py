from pydantic import BaseModel
from typing import Optional

class MessageCreate(BaseModel):
    """Схема для создания нового сообщения."""
    text: str
    attachment_id: Optional[str] = None