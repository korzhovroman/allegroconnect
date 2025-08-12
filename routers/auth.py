# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

from utils.rate_limiter import limiter
from models.database import get_db
from models.models import User, Team, TeamMember
from schemas.user import Token
from schemas.api import APIResponse
from schemas.token import TokenPayload
from utils.auth import create_access_token
from utils.dependencies import get_token_payload, get_current_user_from_db
from config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class FCMTokenPayload(BaseModel):
    token: str

@router.post("/sync-user", response_model=APIResponse[Token], status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def sync_and_get_token(
        request: Request,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_token_payload)
):
    """
    Проверяет токен от Supabase, синхронизирует пользователя
    и возвращает наш внутренний, "умный" JWT-токен.
    """
    if not token_payload.sub or not token_payload.email:
        raise HTTPException(status_code=400, detail="Token must contain sub (ID) and email.")

    user = await db.scalar(select(User).where(User.supabase_user_id == token_payload.sub))

    if not user:
        existing_user_by_email = await db.scalar(select(User).where(User.email == token_payload.email))
        if existing_user_by_email:
            raise HTTPException(status_code=409, detail="Email is already linked to another account.")

        user = User(
            supabase_user_id=token_payload.sub,
            email=token_payload.email,
            hashed_password="not_used",
            subscription_status="trial",
            subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=12)
        )
        db.add(user)
        await db.flush()

        new_team = Team(owner_id=user.id)
        db.add(new_team)
        await db.flush()

        owner_membership = TeamMember(user_id=user.id, team_id=new_team.id, role='owner')
        db.add(owner_membership)
        await db.commit()
        await db.refresh(user)

    custom_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "status": user.subscription_status,
        "exp_date": user.subscription_ends_at.isoformat() if user.subscription_ends_at else None
    }
    access_token = create_access_token(data=custom_token_data)

    return APIResponse(data=Token(access_token=access_token))

@router.post("/register-fcm-token", response_model=APIResponse[dict], status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def register_fcm_token(
        request: Request,
        payload: FCMTokenPayload,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user_from_db)
):
    current_user.fcm_token = payload.token
    await db.commit()
    return APIResponse(data={"status": "success"})

@router.get("/me/subscription", response_model=APIResponse[dict])
@limiter.limit("60/minute")
async def get_my_subscription_status(
        request: Request,
        current_user: User = Depends(get_current_user_from_db),
        db: AsyncSession = Depends(get_db)
):
    from .allegro import count_user_allegro_accounts
    used_accounts = await count_user_allegro_accounts(db, current_user.id)
    limit = settings.SUB_LIMITS.get(current_user.subscription_status, 0)

    subscription_data = {
        "status": current_user.subscription_status,
        "ends_at": current_user.subscription_ends_at,
        "used_accounts": used_accounts,
        "limit": limit
    }
    return APIResponse(data=subscription_data)