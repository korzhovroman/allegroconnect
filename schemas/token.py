# schemas/token.py
from pydantic import BaseModel
from typing import Optional

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    email: Optional[str] = None
