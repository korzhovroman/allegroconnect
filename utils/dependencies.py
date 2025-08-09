# utils/dependencies.py
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from async_lru import alru_cache
from .auth import verify_token
from models.database import get_db
from models.models import User, AllegroAccount, TeamMember, EmployeePermission
from schemas.token import TokenPayload

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/sync-user")


def get_user_service():
    from services.user_service import UserService
    return UserService()


def plan_checker(allowed_plans: List[str]):
    async def check_subscription(current_user: User = Depends(get_current_user)) -> User:
        if current_user.subscription_status not in allowed_plans:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature is only available for the following plans: {', '.join(allowed_plans)}."
            )
        return current_user
    return check_subscription


require_pro_plan = plan_checker(["pro", "maxi", "trial"])
require_maxi_plan = plan_checker(["maxi", "trial"])

async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = verify_token(token, credentials_exception)
    if token_data.sub is None:
        raise credentials_exception
    user = await db.scalar(select(User).where(User.supabase_user_id == token_data.sub))
    if user is None:
        raise credentials_exception
    return user


@alru_cache(maxsize=1024, ttl=300)
async def _check_permission_in_db(db: AsyncSession, user_id: int, allegro_account_id: int) -> bool:
    account = await db.scalar(
        select(AllegroAccount.id).where(
            AllegroAccount.id == allegro_account_id,
            AllegroAccount.owner_id == user_id
        )
    )
    if account:
        return True

    permission = await db.scalar(
        select(EmployeePermission.id)
        .join(TeamMember, TeamMember.id == EmployeePermission.member_id)
        .where(
            TeamMember.user_id == user_id,
            EmployeePermission.allegro_account_id == allegro_account_id
        )
    )
    if permission:
        return True

    return False

async def get_authorized_allegro_account(
        allegro_account_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
) -> AllegroAccount:
    permission_granted = await _check_permission_in_db(
        db=db,
        user_id=current_user.id,
        allegro_account_id=allegro_account_id
    )

    if not permission_granted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this Allegro account."
        )

    final_account_obj = await db.get(AllegroAccount, allegro_account_id)
    if not final_account_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allegro account not found.")

    return final_account_obj

def get_premium_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.subscription_status not in ["trial", "pro", "maxi"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires an active premium subscription."
        )
    return current_user


def get_token_payload(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return verify_token(token, credentials_exception)