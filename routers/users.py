# routers/users.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import get_db
from models.models import User
from schemas.api import APIResponse
from schemas.user import ProfileUpdate, UserResponse
from utils.dependencies import get_current_user_from_db

router = APIRouter(prefix="/api/me", tags=["User Profile"])


@router.get("", response_model=APIResponse[UserResponse])
async def get_user_profile(
        request: Request,
        current_user: User = Depends(get_current_user_from_db)
):
    """
    Возвращает текущие данные профиля аутентифицированного пользователя.
    """
    return APIResponse(data=current_user)


@router.patch("", response_model=APIResponse[UserResponse])
async def update_user_profile(
        request: Request,
        payload: ProfileUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user_from_db)
):
    """
    Позволяет пользователю обновить данные своего профиля для выставления счетов.
    Передавать можно только те поля, которые нужно изменить.
    """
    update_data = payload.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(current_user, key, value)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return APIResponse(data=current_user)