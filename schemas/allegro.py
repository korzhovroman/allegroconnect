# schemas/allegro.py
from pydantic import BaseModel
from typing import Optional


class AllegroAccountSettingsUpdate(BaseModel):
    auto_reply_enabled: Optional[bool] = None
    auto_reply_text: Optional[str] = None

class AllegroAccountOut(BaseModel):
    id: int
    allegro_login: str

    class Config:
        from_attributes = True # Для SQLAlchemy < 2.0 было orm_mode = True