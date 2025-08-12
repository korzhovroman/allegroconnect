# utils/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
from jose import jwt, JWTError
from async_lru import alru_cache

from config import settings
from models.database import get_db
from models.models import User, AllegroAccount, TeamMember, EmployeePermission
from schemas.token import TokenPayload
from .auth import verify_token as verify_supabase_token

# Схема для нашего внутреннего токена, который будет использоваться везде
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
# Схема для токена от Supabase (используется только в /sync-user)
oauth2_scheme_supabase = OAuth2PasswordBearer(tokenUrl="/api/auth/sync-user")

def get_token_payload(token: str = Depends(oauth2_scheme_supabase)) -> TokenPayload:
    """Проверяет токен от Supabase. Используется только один раз при обмене токенов."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate Supabase token",
    )
    return verify_supabase_token(token, credentials_exception)

def get_current_user_payload(token: str = Depends(oauth2_scheme)) -> dict:
    """Быстро расшифровывает наш ВНУТРЕННИЙ JWT и возвращает его содержимое. Не делает запросов к БД."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        exp_date_str = payload.get("exp_date")
        if exp_date_str:
            exp_date = datetime.fromisoformat(exp_date_str.replace('Z', '+00:00'))
            if exp_date < datetime.now(timezone.utc):
                payload["status"] = "expired"
        return payload
    except JWTError:
        raise credentials_exception

def plan_checker(allowed_plans: List[str]):
    """Проверяет статус подписки из токена. Не делает запросов к БД."""
    def check_subscription(payload: dict = Depends(get_current_user_payload)) -> dict:
        if payload.get("status") not in allowed_plans:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature is only available for the following plans: {', '.join(allowed_plans)}."
            )
        return payload
    return check_subscription

require_pro_plan = plan_checker(["pro", "maxi", "trial"])
require_maxi_plan = plan_checker(["maxi", "trial"])

async def get_current_user_from_db(
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Получает полный объект User из БД по ID из токена. Используется только там, где нужен сам объект User."""
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = await db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@alru_cache(maxsize=1024, ttl=300)
async def _check_permission_in_db(db: AsyncSession, user_id: int, allegro_account_id: int) -> bool:
    account = await db.scalar(
        select(AllegroAccount.id).where(AllegroAccount.id == allegro_account_id, AllegroAccount.owner_id == user_id)
    )
    if account:
        return True
    permission = await db.scalar(
        select(EmployeePermission.id).join(TeamMember).where(
            TeamMember.user_id == user_id,
            EmployeePermission.allegro_account_id == allegro_account_id
        )
    )
    return bool(permission)

async def get_authorized_allegro_account(
    allegro_account_id: int,
    current_user: User = Depends(get_current_user_from_db),
    db: AsyncSession = Depends(get_db)
) -> AllegroAccount:
    permission_granted = await _check_permission_in_db(
        db=db, user_id=current_user.id, allegro_account_id=allegro_account_id
    )
    if not permission_granted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission for this Allegro account.")
    final_account_obj = await db.get(AllegroAccount, allegro_account_id)
    if not final_account_obj:
        raise HTTPException(status_code=404, detail="Allegro account not found.")
    return final_account_obj