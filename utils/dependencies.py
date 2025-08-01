# utils/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

# 1. Используем обновленные утилиты
from .auth import verify_token
from ..models.database import get_db
from ..models.models import User
from ..services.user_service import UserService  # <-- Будем использовать сервис
from ..schemas.token import TokenPayload

# Указываем FastAPI, откуда брать токен (из эндпоинта /api/auth/login)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# Провайдер для UserService
def get_user_service() -> UserService:
    return UserService()


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
        user_service: UserService = Depends(get_user_service)  # <-- Внедряем сервис
) -> User:
    """
    Зависимость для получения текущего пользователя из JWT токена.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 2. Проверяем токен
    token_data = verify_token(token, credentials_exception)

    if token_data.sub is None:
        raise credentials_exception

    # 3. Получаем пользователя через сервис, а не прямым запросом
    user = await user_service.get_user_by_email(db, email=token_data.sub)

    if user is None:
        raise credentials_exception

    return user