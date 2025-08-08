# schemas/allegro.py
from pydantic import BaseModel, Field # ИЗМЕНЕНО: импортируем Field
from typing import Optional


class AllegroAccountSettingsUpdate(BaseModel):
    auto_reply_enabled: Optional[bool] = None
    # ИЗМЕНЕНО: Добавляем ограничение на максимальную длину текста автоответчика.
    # Это защищает базу данных от переполнения и обеспечивает предсказуемость.
    auto_reply_text: Optional[str] = Field(None, max_length=1000)

class AllegroAccountOut(BaseModel):
    id: int
    allegro_login: str

    class Config:
        from_attributes = True