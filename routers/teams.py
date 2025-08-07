# routers/teams.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from supabase import create_client, Client

from config import settings
from models.database import get_db
from models.models import User, Team, TeamMember, EmployeePermission, AllegroAccount
from utils.dependencies import get_current_user

# Инициализируем админ-клиент Supabase
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

router = APIRouter(prefix="/api/teams", tags=["Teams"])


# --- Модели для запросов ---

class EmployeeInvite(BaseModel):
    email: EmailStr
    name: str


class PermissionGrant(BaseModel):
    member_id: int  # ID участника команды (НЕ user_id)
    allegro_account_id: int


# --- Эндпоинты ---

@router.post("/invite", status_code=status.HTTP_201_CREATED, summary="Пригласить сотрудника в команду")
async def invite_employee(
        payload: EmployeeInvite,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Приглашает нового сотрудника в команду текущего пользователя."""
    if not current_user.owned_team:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только владелец команды может приглашать сотрудников."
        )

    try:
        response = supabase_admin.auth.admin.invite_user_by_email(payload.email)
        new_supabase_user = response.user
        if not new_supabase_user:
            raise Exception("Supabase не вернул данные пользователя после приглашения.")
    except Exception as e:
        if "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Пользователь с email {payload.email} уже существует."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось пригласить пользователя через Supabase: {e}"
        )

    new_local_user = User(
        supabase_user_id=new_supabase_user.id,
        email=payload.email,
        name=payload.name,
        hashed_password="invited_user_placeholder"
    )
    db.add(new_local_user)
    await db.flush()
    await db.refresh(new_local_user)

    new_team_member = TeamMember(
        user_id=new_local_user.id,
        team_id=current_user.owned_team.id,
        role='employee'
    )
    db.add(new_team_member)
    await db.commit()

    return {"status": "success", "message": f"Приглашение отправлено на {payload.email}"}


# --- НОВЫЙ ЭНДПОИНТ ДЛЯ ВЫДАЧИ ПРАВ ---
@router.post("/permissions", status_code=status.HTTP_201_CREATED, summary="Выдать сотруднику доступ к аккаунту Allegro")
async def grant_permission(
        payload: PermissionGrant,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Выдает сотруднику разрешение на доступ к одному из аккаунтов Allegro владельца."""
    # Шаг 1: Проверка, что текущий пользователь - владелец
    if not current_user.owned_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только владелец может управлять правами.")

    # Шаг 2: Проверка, что аккаунт Allegro принадлежит этому владельцу
    allegro_account = await db.scalar(
        select(AllegroAccount).where(
            AllegroAccount.id == payload.allegro_account_id,
            AllegroAccount.owner_id == current_user.id
        )
    )
    if not allegro_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Указанный аккаунт Allegro не найден или не принадлежит вам.")

    # Шаг 3: Проверка, что сотрудник (member_id) состоит в команде этого владельца
    team_member = await db.scalar(
        select(TeamMember).where(
            TeamMember.id == payload.member_id,
            TeamMember.team_id == current_user.owned_team.id
        )
    )
    if not team_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Указанный сотрудник не найден в вашей команде.")

    # Шаг 4: Проверка, что такого разрешения еще не существует
    existing_permission = await db.scalar(
        select(EmployeePermission).where(
            EmployeePermission.member_id == payload.member_id,
            EmployeePermission.allegro_account_id == payload.allegro_account_id
        )
    )
    if existing_permission:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Такое разрешение уже было выдано ранее.")

    # Шаг 5: Создание нового разрешения
    new_permission = EmployeePermission(
        member_id=payload.member_id,
        allegro_account_id=payload.allegro_account_id
    )
    db.add(new_permission)
    await db.commit()

    return {"status": "success", "message": "Разрешение успешно выдано."}


# --- НОВЫЙ ЭНДПОИНТ ДЛЯ ОТЗЫВА ПРАВ ---
@router.delete("/permissions", status_code=status.HTTP_200_OK,
               summary="Отозвать у сотрудника доступ к аккаунту Allegro")
async