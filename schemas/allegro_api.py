# schemas/allegro_api.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# --- Модели для ответов от Allegro API ---

class AllegroInterlocutor(BaseModel):
    login: str

class AllegroThread(BaseModel):
    id: str
    read: bool
    last_message_date_time: datetime = Field(..., alias="lastMessageDateTime")
    interlocutor: Optional[AllegroInterlocutor] = None

class ThreadsResponse(BaseModel):
    threads: List[AllegroThread]
    count: int
    total_count: int = Field(..., alias="totalCount")

class AllegroMessageAuthor(BaseModel):
    role: str # SELLER или BUYER

class AllegroMessage(BaseModel):
    id: str
    author: AllegroMessageAuthor
    # Добавьте другие поля по необходимости

class MessagesResponse(BaseModel):
    messages: List[AllegroMessage]