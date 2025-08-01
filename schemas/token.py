# schemas/token.py
from pydantic import BaseModel

class TokenPayload(BaseModel):
    sub: str | None = None