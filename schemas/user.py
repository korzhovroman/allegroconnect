from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class AllegroAccountResponse(BaseModel):
    id: int
    allegro_user_id: str
    allegro_login: str
    expires_at: datetime

    # Config должен быть ВНУТРИ этого класса
    class Config:
        from_attributes = True

class UserResponse(UserBase):
    id: int
    created_at: datetime
    allegro_accounts: List[AllegroAccountResponse] = []

    # И этот Config тоже должен быть ВНУТРИ
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[int] = None