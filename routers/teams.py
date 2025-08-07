# routers/teams.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import create_client, Client

from config import settings
from models.database import get_db
from models.models import User, Team, TeamMember
from utils.dependencies import get_current_user

# Инициализируем админ-клиент Supabase один раз при старте
# Он будет использоваться для создания пользователей-сотрудников
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

router = APIRouter(prefix="/api/teams", tags=["Teams"])

class EmployeeInvite(BaseModel):
    email: EmailStr
    name: str

@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_employee(
    payload: EmployeeInvite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Приглашает нового сотрудника в команду текущего пользователя.
    1. Проверяет, что у пользователя есть команда (он владелец).
    2. Создает пользователя в Supabase Auth через invite.
    3. Создает пользователя и участника команды в локальной БД.
    """
    # Шаг 1: Убедиться, что текущий пользователь является владельцем команды.
    # Мы предполагаем, что команда создается автоматически при регистрации владельца.
    # Если owned_team нет, значит, он не владелец.
    if not current_user.owned_team:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только владелец команды может приглашать сотрудников."
        )

    # Шаг 2: Создать пользователя в Supabase Auth с отправкой приглашения.
    try:
        response = supabase_admin.auth.admin.invite_user_by_email(payload.email)
        new_supabase_user = response.user
        if not new_supabase_user:
            raise Exception("Supabase не вернул данные пользователя после приглашения.")
    except Exception as e:
        # Обрабатываем случай, если пользователь уже существует в Supabase
        if "already exists" in str(e):
             raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Пользователь с email {payload.email} уже существует."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось пригласить пользователя через Supabase: {e}"
        )

    # Шаг 3: Создать пользователя в НАШЕЙ базе данных.
    new_local_user = User(
        supabase_user_id=new_supabase_user.id,
        email=payload.email,
        name=payload.name,
        hashed_password="invited_user_placeholder" # Пароль не используется, т.к. вход через Supabase
    )
    db.add(new_local_user)
    # Используем flush, чтобы получить ID нового пользователя до коммита
    await db.flush()
    await db.refresh(new_local_user)

    # Шаг 4: Добавить нового пользователя в команду как сотрудника.
    new_team_member = TeamMember(
        user_id=new_local_user.id,
        team_id=current_user.owned_team.id,
        role='employee'
    )
    db.add(new_team_member)
    await db.commit()

    return {"status": "success", "message": f"Приглашение отправлено на {payload.email}"}