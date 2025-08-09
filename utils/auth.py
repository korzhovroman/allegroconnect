# utils/auth.py

from datetime import datetime, timedelta, timezone
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


def create_state_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode = {"exp": expire, "sub": str(user_id)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_state_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload.get("sub"))
        return user_id
    except (JWTError, ValueError, TypeError):
        return None

# ИЗМЕНЕНА ФУНКЦИЯ
def verify_token(token: str, credentials_exception: HTTPException) -> TokenPayload:
    """
    Декодирует и ВАЛИДИРУЕТ токен от Supabase.
    Добавлены критические проверки 'iss' и 'aud'.
    """
    try:
        # Используем секрет от Supabase для декодирования
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[settings.ALGORITHM],
            # Проверяем, что токен предназначен для аутентифицированных пользователей
            audience="authenticated"
        )

        # --- КРИТИЧЕСКИ ВАЖНЫЕ ПРОВЕРКИ ---
        # 1. Проверка издателя (issuer)
        # Убеждаемся, что токен выдан именно нашим инстансом Supabase
        expected_issuer = f"{settings.SUPABASE_URL}/auth/v1"
        if payload.get("iss") != expected_issuer:
            raise credentials_exception

        # 2. Проверка 'sub' (ID пользователя)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception

        # 3. Извлекаем email
        email = payload.get("email")
        if email is None:
            raise credentials_exception

        token_data = TokenPayload(sub=user_id, email=email)

    except (JWTError, ValueError):
        # Если токен невалиден, истек или имеет неверную структуру
        raise credentials_exception
    return token_data
