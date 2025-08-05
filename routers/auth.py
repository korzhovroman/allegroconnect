# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import get_db
from models.models import User
from schemas.user import UserResponse
from schemas.token import TokenPayload
from utils.auth import verify_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/sync-user", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def sync_supabase_user(
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(verify_token)
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

    # Шаг 1: Всегда ищем пользователя по его ID из Supabase. Это наш главный ключ.
    user = (await db.execute(select(User).where(User.supabase_user_id == token_payload.sub))).scalar_one_or_none()

    if user:
        # Пользователь найден. Это обычный повторный вход.
        # Просто обновим его email, если он изменился, и вернем данные.
        if user.email != token_payload.email:
            user.email = token_payload.email
            await db.commit()
            await db.refresh(user)
        return user

    # Шаг 2: Если пользователь с таким ID не найден, проверим, не занят ли его email.
    existing_user_by_email = (await db.execute(select(User).where(User.email == token_payload.email))).scalar_one_or_none()

    if existing_user_by_email:
        # Email уже используется в нашей базе.
        # Если у него УЖЕ есть supabase_user_id, значит, кто-то пытается захватить аккаунт.
        if existing_user_by_email.supabase_user_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already linked to another account."
            )
        else:
            # Это наш старый пользователь. Привязываем его к Supabase ID.
            existing_user_by_email.supabase_user_id = token_payload.sub
            await db.commit()
            await db.refresh(existing_user_by_email)
            return existing_user_by_email

    # Шаг 3: Если и ID, и email новые, создаем совершенно нового пользователя.
    new_user = User(
        supabase_user_id=token_payload.sub,
        email=token_payload.email,
        hashed_password="not_used"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user