# utils/auth.py
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import HTTPException

from config import settings
from schemas.token import TokenPayload
from utils.logger import logger

def create_access_token(data: dict) -> str:
    """Создает наш собственный JWT со сроком жизни в 1 день."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=1)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_state_token(user_id: int) -> str:
    """Создает временный токен для OAuth-процесса Allegro."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode = {"exp": expire, "sub": str(user_id)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_state_token(token: str) -> int | None:
    """Проверяет временный токен для OAuth-процесса Allegro."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None

def verify_token(token: str, credentials_exception: HTTPException) -> TokenPayload:
    """Декодирует и ВАЛИДИРУЕТ первоначальный токен от Supabase."""
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[settings.ALGORITHM],
            audience="authenticated"
        )
        expected_issuer = f"{settings.SUPABASE_URL}/auth/v1"
        if payload.get("iss") != expected_issuer:
            logger.error(f"JWT Issuer mismatch. Expected: {expected_issuer}, Got: {payload.get('iss')}")
            raise credentials_exception

        user_id = payload.get("sub")
        email = payload.get("email")
        if user_id is None or email is None:
            raise credentials_exception
        return TokenPayload(sub=user_id, email=email)
    except JWTError as e:
        logger.error(f"Ошибка верификации JWT от Supabase: {e}", exc_info=True)
        raise credentials_exception
