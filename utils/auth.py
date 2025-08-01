from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status

# 1. Импортируем наш центральный объект настроек
from ..config import settings
from ..schemas.token import TokenPayload  # <-- Рекомендую создать эту Pydantic-схему


def create_access_token(data: dict) -> str:
    """
    Создает новый JWT токен.
    """
    to_encode = data.copy()

    # 2. Берем время жизни токена из центральных настроек
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    # 3. Используем ключ и алгоритм из настроек
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str, credentials_exception: HTTPException) -> TokenPayload:
    """
    Проверяет JWT токен и возвращает его полезную нагрузку (payload).
    В случае ошибки выбрасывает credentials_exception.
    """
    try:
        # 4. Используем ключ и алгоритм из настроек
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # 5. Валидируем содержимое токена с помощью Pydantic-схемы
        token_data = TokenPayload(**payload)

    except (JWTError, ValueError) as e:
        # Если токен невалиден или его структура некорректна
        raise credentials_exception from e

    return token_data