# utils/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cachetools import TTLCache, cached
from typing import List
from .auth import verify_token
from models.database import get_db
from models.models import User, AllegroAccount, TeamMember, EmployeePermission
from schemas.token import TokenPayload
from asyncio import Lock

# --- 1. Создаем кеш ---
# maxsize=1024: Хранить до 1024 записей о правах.
# ttl=300: Каждая запись хранится 300 секунд (5 минут).
permission_cache = TTLCache(maxsize=1024, ttl=300)
cache_lock = Lock()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/sync-user")


def get_user_service():
    # ... (Этот код без изменений)
    from services.user_service import UserService
    return UserService()


def plan_checker(allowed_plans: List[str]):
    """
    Это "фабрика", которая создает зависимость для проверки подписки.
    """

    async def check_subscription(current_user: User = Depends(get_current_user)) -> User:
        """
        Сама зависимость, которая будет проверять план пользователя.
        """
        # Можно добавить 'trial', если триал дает доступ ко всем функциям
        if current_user.subscription_status not in allowed_plans:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature is only available for the following plans: {', '.join(allowed_plans)}."
            )
        return current_user

    return check_subscription


# Создаем конкретные зависимости для каждого плана
require_pro_plan = plan_checker(["pro", "maxi", "trial"])
require_maxi_plan = plan_checker(["maxi", "trial"])

async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
) -> User:
    # ... (Этот код без изменений)
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


# --- 2. НОВАЯ ЦЕНТРАЛИЗОВАННАЯ ФУНКЦИЯ ПРОВЕРКИ ПРАВ ---
# Мы используем декоратор @cached, чтобы автоматически кешировать результат
@cached(permission_cache)
async def _check_permission_in_db(db: AsyncSession, user_id: int, allegro_account_id: int) -> bool:
    """
    Эта "приватная" функция реально лезет в БД. Ее результат будет закеширован.
    Возвращает True, если доступ разрешен, иначе False.
    """
    # Проверка на владельца
    account = await db.scalar(
        select(AllegroAccount).where(
            AllegroAccount.id == allegro_account_id,
            AllegroAccount.owner_id == user_id
        )
    )
    if account:
        return True

    # Проверка на сотрудника с правами
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
    """
    Основная зависимость. Проверяет права доступа с атомарным кешированием
    и возвращает объект AllegroAccount, если доступ разрешен.
    """
    cache_key = (current_user.id, allegro_account_id)

    # Быстрая проверка кеша без блокировки
    if cache_key in permission_cache:
        if permission_cache[cache_key]:
            account_obj = await db.get(AllegroAccount, allegro_account_id)
            if account_obj:
                return account_obj
        else: # Если в кеше явно указано, что доступа нет
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by cache.")

    # Если в кеше нет, используем блокировку для предотвращения race condition
    async with cache_lock:
        # Повторная проверка кеша внутри блокировки на случай, если другой поток уже записал значение
        if cache_key in permission_cache:
            if permission_cache[cache_key]:
                account_obj = await db.get(AllegroAccount, allegro_account_id)
                if account_obj:
                    return account_obj
            else:
                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied by cache.")

        # Если в кеше все еще нет, лезем в базу данных
        # Проверка на владельца
        account = await db.scalar(select(AllegroAccount.id).where(AllegroAccount.id == allegro_account_id,
                                                                  AllegroAccount.owner_id == current_user.id))
        has_permission = bool(account)

        # Если не владелец, проверка на сотрудника
        if not has_permission:
            permission = await db.scalar(
                select(EmployeePermission.id).join(TeamMember).where(TeamMember.user_id == current_user.id,
                                                                     EmployeePermission.allegro_account_id == allegro_account_id))
            has_permission = bool(permission)

        # Сохраняем результат в кеш
        permission_cache[cache_key] = has_permission

    if not has_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You do not have permission to access this Allegro account.")

    # Если права есть, получаем сам объект аккаунта
    final_account_obj = await db.get(AllegroAccount, allegro_account_id)
    if not final_account_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allegro account not found.")

    return final_account_obj

def get_premium_user(current_user: User = Depends(get_current_user)) -> User:
    # ... (Этот код без изменений)
    if current_user.subscription_status not in ["trial", "pro", "maxi"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires an active premium subscription."
        )
    return current_user


def get_token_payload(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    # ... (Этот код без изменений)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return verify_token(token, credentials_exception)