# schemas/allegro.py
from pydantic import BaseModel, Field
from typing import Optional


class AllegroAccountSettingsUpdate(BaseModel):
    auto_reply_enabled: Optional[bool] = None
    auto_reply_text: Optional[str] = Field(None, max_length=1000)

class AllegroAccountOut(BaseModel):
    id: int
    allegro_login: str

    class Config:
        from_attributes = True