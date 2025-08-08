# routers/teams.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload, joinedload
from supabase import create_client, Client
from typing import List
from utils.dependencies import require_maxi_plan
from config import settings
from models.database import get_db
from models.models import User, Team, TeamMember, EmployeePermission, AllegroAccount
from utils.dependencies import get_current_user
from schemas.api import APIResponse
from main import logger

supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

router = APIRouter(prefix="/api/teams", tags=["Teams"])


class EmployeeInvite(BaseModel):
    email: EmailStr
    name: str


class PermissionGrant(BaseModel):
    member_id: int
    allegro_account_id: int


class TeamMemberOut(BaseModel):
    member_id: int
    user_id: int
    email: EmailStr
    name: str | None
    role: str

    class Config:
        from_attributes = True


@router.get("/members", response_model=APIResponse[List[TeamMemberOut]],
            summary="Получить список всех участников команды")
async def get_team_members(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_maxi_plan)
):
    if not current_user.team_membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вы не состоите ни в одной команде.")

    team_id = current_user.team_membership.team_id

    query = select(TeamMember).options(joinedload(TeamMember.user)).where(TeamMember.team_id == team_id)
    result = await db.execute(query)
    members = result.scalars().all()

    response_data = []
    for member in members:
        response_data.append(
            TeamMemberOut(
                member_id=member.id,
                user_id=member.user.id,
                email=member.user.email,
                name=member.user.name,
                role=member.role
            )
        )

    return APIResponse(data=response_data)


@router.post("/invite", response_model=APIResponse[dict], status_code=status.HTTP_201_CREATED,
             summary="Пригласить сотрудника в команду")
async def invite_employee(
        payload: EmployeeInvite,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_maxi_plan)
):
    if not current_user.owned_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Только владелец команды может приглашать сотрудников.")
    try:
        response = supabase_admin.auth.admin.invite_user_by_email(payload.email)
        new_supabase_user = response.user
        if not new_supabase_user:
            raise Exception("Supabase не вернул данные пользователя после приглашения.")
    except Exception as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"Пользователь с email {payload.email} уже существует.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Не удалось пригласить пользователя через Supabase: {e}")
    new_local_user = User(supabase_user_id=new_supabase_user.id, email=payload.email, name=payload.name,
                          hashed_password="invited_user_placeholder")
    db.add(new_local_user)
    await db.flush()
    await db.refresh(new_local_user)
    new_team_member = TeamMember(user_id=new_local_user.id, team_id=current_user.owned_team.id, role='employee')
    db.add(new_team_member)
    await db.commit()
    return APIResponse(data={"status": "success", "message": f"Приглашение отправлено на {payload.email}"})


@router.post("/permissions", response_model=APIResponse[dict], status_code=status.HTTP_201_CREATED,
             summary="Выдать сотруднику доступ к аккаунту Allegro")
async def grant_permission(
        payload: PermissionGrant,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_maxi_plan)
):
    if not current_user.owned_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только владелец может управлять правами.")
    allegro_account = await db.scalar(select(AllegroAccount).where(AllegroAccount.id == payload.allegro_account_id,
                                                                   AllegroAccount.owner_id == current_user.id))
    if not allegro_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Указанный аккаунт Allegro не найден или не принадлежит вам.")
    team_member = await db.scalar(
        select(TeamMember).where(TeamMember.id == payload.member_id, TeamMember.team_id == current_user.owned_team.id))
    if not team_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Указанный сотрудник не найден в вашей команде.")
    existing_permission = await db.scalar(
        select(EmployeePermission).where(EmployeePermission.member_id == payload.member_id,
                                         EmployeePermission.allegro_account_id == payload.allegro_account_id))
    if existing_permission:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Такое разрешение уже было выдано ранее.")
    new_permission = EmployeePermission(member_id=payload.member_id, allegro_account_id=payload.allegro_account_id)
    db.add(new_permission)
    await db.commit()
    return APIResponse(data={"status": "success", "message": "Разрешение успешно выдано."})


@router.delete("/permissions", response_model=APIResponse[dict], status_code=status.HTTP_200_OK,
               summary="Отозвать у сотрудника доступ к аккаунту Allegro")
async def revoke_permission(
        payload: PermissionGrant,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_maxi_plan)
):
    member = await db.scalar(select(TeamMember).where(TeamMember.id == payload.member_id))
    if not current_user.owned_team or not member or current_user.owned_team.id != member.team_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для выполнения операции.")

    stmt = delete(EmployeePermission).where(EmployeePermission.member_id == payload.member_id,
                                            EmployeePermission.allegro_account_id == payload.allegro_account_id)
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Указанное разрешение не найдено.")
    return APIResponse(data={"status": "success", "message": "Разрешение успешно отозвано."})


@router.delete("/members/{member_id}", response_model=APIResponse[dict], status_code=status.HTTP_200_OK,
               summary="Удалить сотрудника из команды")
async def delete_employee(
        member_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_maxi_plan)
):
    if not current_user.owned_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только владелец может удалять сотрудников.")
    member_to_delete = await db.scalar(
        select(TeamMember).options(selectinload(TeamMember.user)).where(TeamMember.id == member_id,
                                                                        TeamMember.team_id == current_user.owned_team.id))
    if not member_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден в вашей команде.")
    if member_to_delete.role == 'owner':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить владельца команды.")
    supabase_user_id_to_delete = member_to_delete.user.supabase_user_id
    user_to_delete = member_to_delete.user
    await db.delete(user_to_delete)  # Удаление каскадом удалит и TeamMember
    await db.commit()
    if supabase_user_id_to_delete:
        try:
            supabase_admin.auth.admin.delete_user(supabase_user_id_to_delete)
        except Exception as e:
            logger.error("Не удалось удалить пользователя из Supabase Auth", user_id=supabase_user_id_to_delete,
                         error=str(e))
            return APIResponse(data={"status": "warning",
                                     "message": "Сотрудник удален из команды, но его аккаунт не удалось полностью деактивировать."})
    return APIResponse(data={"status": "success", "message": "Сотрудник успешно удален."})