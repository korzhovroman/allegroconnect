# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from utils.rate_limiter import limiter
from models.database import get_db
from models.models import User, Team, TeamMember
from schemas.user import UserResponse
from schemas.token import TokenPayload
from schemas.api import APIResponse
from utils.dependencies import get_token_payload, get_current_user
from config import settings
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class FCMTokenPayload(BaseModel):
    token: str


@router.post("/sync-user", response_model=APIResponse[UserResponse], status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def sync_supabase_user(
        request: Request,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_token_payload)
):

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
        return APIResponse(data=user)

    existing_user_by_email = (
        await db.execute(select(User).where(User.email == token_payload.email))).scalar_one_or_none()

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
            return APIResponse(data=existing_user_by_email)

    new_user = User(
        supabase_user_id=token_payload.sub,
        email=token_payload.email,
        hashed_password="not_used"
    )
    db.add(new_user)
    await db.flush()

    new_team = Team(
        owner_id=new_user.id
    )
    db.add(new_team)
    await db.flush()

    owner_membership = TeamMember(
        user_id=new_user.id,
        team_id=new_team.id,
        role='owner'
    )
    db.add(owner_membership)

    await db.commit()

    final_user_query = (
        select(User)
        .options(
            selectinload(User.owned_team),
            selectinload(User.team_membership),
            selectinload(User.allegro_accounts)
        )
        .where(User.id == new_user.id)
    )
    result = await db.execute(final_user_query)
    final_user = result.scalar_one()

    return APIResponse(data=final_user)

@router.post("/register-fcm-token", response_model=APIResponse[dict], status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def register_fcm_token(
        request: Request,
        payload: FCMTokenPayload,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    current_user.fcm_token = payload.token
    await db.commit()
    return APIResponse(data={"status": "success"})


@router.get("/me/subscription", response_model=APIResponse[dict])
@limiter.limit("60/minute")
async def get_my_subscription_status(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):

    status_val = current_user.subscription_status
    ends_at = current_user.subscription_ends_at

    from .allegro import count_user_allegro_accounts
    used_accounts = await count_user_allegro_accounts(db, current_user.id)

    limit = settings.SUB_LIMITS.get(status_val, 0)

    subscription_data = {
        "status": status_val,
        "ends_at": ends_at,
        "used_accounts": used_accounts,
        "limit": limit
    }
    return APIResponse(data=subscription_data)