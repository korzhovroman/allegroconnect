# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from models.database import get_db
from models.models import User
from schemas.user import UserResponse
from schemas.token import TokenPayload
# ИМПОРТИРУЕМ ПРАВИЛЬНЫЕ ЗАВИСИМОСТИ:
from utils.dependencies import get_token_payload, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class FCMTokenPayload(BaseModel):
    token: str

@router.post("/sync-user", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def sync_supabase_user(
    db: AsyncSession = Depends(get_db),
    # ИСПОЛЬЗУЕМ ИСПРАВЛЕННУЮ ЗАВИСИМОСТЬ:
    token_payload: TokenPayload = Depends(get_token_payload)
):
    """
    Безопасная синхронизация. supabase_user_id - главный ключ.
    Предотвращает захват аккаунта через старый email.
    """
    if not token_payload.sub or not token_payload.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token must contain sub (ID) and email."
        )

    # Шаг 1: Всегда ищем пользователя по его ID из Supabase.
    user = (await db.execute(select(User).where(User.supabase_user_id == token_payload.sub))).scalar_one_or_none()

    if user:
        # Пользователь найден. Обновим email, если он изменился.
        if user.email != token_payload.email:
            user.email = token_payload.email
            await db.commit()
            await db.refresh(user)
        return user

    # Шаг 2: Если по ID не нашли, проверим, не занят ли email.
    existing_user_by_email = (await db.execute(select(User).where(User.email == token_payload.email))).scalar_one_or_none()

    if existing_user_by_email:
        # Email занят. Проверяем, не попытка ли это захвата аккаунта.
        if existing_user_by_email.supabase_user_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already linked to another account."
            )
        else:
            # Это старый пользователь, привязываем его к Supabase ID.
            existing_user_by_email.supabase_user_id = token_payload.sub
            await db.commit()
            await db.refresh(existing_user_by_email)
            return existing_user_by_email

    # Шаг 3: Создаем нового пользователя.
    new_user = User(
        supabase_user_id=token_payload.sub,
        email=token_payload.email,
        hashed_password="not_used"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/register-fcm-token", status_code=status.HTTP_200_OK)
async def register_fcm_token(
    payload: FCMTokenPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Сохраняет или обновляет FCM токен для текущего пользователя."""
    current_user.fcm_token = payload.token
    await db.commit()
    return {"status": "success"}