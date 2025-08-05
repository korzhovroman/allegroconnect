# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем нужные модели, схемы и сервисы
from models.database import get_db
from models.models import User
from schemas.user import UserResponse
from schemas.token import TokenPayload
from services.user_service import UserService
# Импортируем нашу НОВУЮ функцию для верификации токена Supabase
from utils.auth import verify_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Провайдер зависимости для UserService остается без изменений
def get_user_service() -> UserService:
    return UserService()

# ---  ЭНДПОИНТ ДЛЯ СИНХРОНИЗАЦИИ С SUPABASE ---
@router.post("/sync-user", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def sync_supabase_user(
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service),
    # Эта зависимость проверяет токен Supabase ИЗ ЗАГОЛОВКА запроса
    # и возвращает его полезную нагрузку (payload)
    token_payload: TokenPayload = Depends(verify_token)
):
    """
    Проверяет токен от Supabase. Если пользователь с таким email
    не существует в нашей БД, создает его. Если существует - возвращает его.
    Этот эндпоинт нужно вызывать с фронтенда каждый раз после успешного
    логина или регистрации через Supabase.
    """
    # Мы ожидаем, что в токене от Supabase есть email
    if not token_payload.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not found in Supabase token."
        )

    # Ищем пользователя в НАШЕЙ базе данных по email из токена
    db_user = await user_service.get_user_by_email(db, email=token_payload.email)

    # Если пользователь уже есть в нашей базе, просто возвращаем его
    if db_user:
        return db_user

    # Если пользователя нет, создаем его.
    new_user_data = User(
        email=token_payload.email,
        hashed_password="not_used" # Пароль не используется
    )

    # Сохраняем нового пользователя в нашей БД
    db.add(new_user_data)
    await db.commit()
    await db.refresh(new_user_data)

    return new_user_data
