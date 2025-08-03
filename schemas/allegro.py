# schemas/allegro.py
from pydantic import BaseModel

class AllegroAccountOut(BaseModel):
    id: int
    allegro_login: str

    class Config:
        from_attributes = True # Для SQLAlchemy < 2.0 было orm_mode = True