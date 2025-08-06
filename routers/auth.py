# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from main import limiter
from models.database import get_db
from models.models import User
from schemas.user import UserResponse
from schemas.token import TokenPayload
from utils.dependencies import get_token_payload, get_current_user
from config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class FCMTokenPayload(BaseModel):
    token: str

@router.post("/sync-user", response_model=UserResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute") # Ограничение: 10 запросов в минуту с одного IP
async def sync_supabase_user(
    request: Request, # <-- Добавляем request для работы limiter'а
    db: AsyncSession = Depends(get_db),
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

    user = (await db.execute(select(User).where(User.supabase_user_id == token_payload.sub))).scalar_one_or_none()

    if user:
        if user.email != token_payload.email:
            user.email = token_payload.email
            await db.commit()
            await db.refresh(user)
        return user

    existing_user_by_email = (await db.execute(select(User).where(User.email == token_payload.email))).scalar_one_or_none()

    if existing_user_by_email:
        if existing_user_by_email.supabase_user_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already linked to another account."
            )
        else:
            existing_user_by_email.supabase_user_id = token_payload.sub
            await db.commit()
            await db.refresh(existing_user_by_email)
            return existing_user_by_email

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
@limiter.limit("20/minute") # Ограничение на регистрацию токена
async def register_fcm_token(
    request: Request, # <-- Добавляем request
    payload: FCMTokenPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Сохраняет или обновляет FCM токен для текущего пользователя."""
    current_user.fcm_token = payload.token
    await db.commit()
    return {"status": "success"}


@router.get("/me/subscription", response_model=dict)
@limiter.limit("60/minute")
async def get_my_subscription_status(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Возвращает информацию о текущей подписке пользователя,
    количестве используемых аккаунтов и доступных лимитах.
    """
    status = current_user.subscription_status
    ends_at = current_user.subscription_ends_at

    # Считаем, сколько аккаунтов уже подключено
    from .allegro import count_user_allegro_accounts  # Локальный импорт, чтобы избежать циклических зависимостей
    used_accounts = await count_user_allegro_accounts(db, current_user.id)

    limit = None  # None означает "неограниченно"

    if status == 'free':
        limit = settings.SUB_LIMIT_FREE
    elif status == 'pro':
        limit = settings.SUB_LIMIT_PRO

    return {
        "status": status,
        "ends_at": ends_at,
        "used_accounts": used_accounts,
        "limit": limit
    }