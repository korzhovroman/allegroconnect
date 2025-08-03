# utils/auth.py

from datetime import datetime, timedelta, timezone  # <-- ИСПРАВЛЕНИЕ ЗДЕСЬ
from jose import JWTError, jwt
from fastapi import HTTPException, status

from config import settings
from schemas.token import TokenPayload


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# НОВАЯ ФУНКЦИЯ для создания state-токена
def create_state_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode = {"exp": expire, "sub": str(user_id)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# НОВАЯ ФУНКЦИЯ для проверки state-токена
def verify_state_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload.get("sub"))
        return user_id
    except (JWTError, ValueError, TypeError):
        return None

def verify_token(token: str, credentials_exception: HTTPException) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (JWTError, ValueError):
        raise credentials_exception
    return token_data