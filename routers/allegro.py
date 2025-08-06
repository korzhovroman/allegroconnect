# routers/allegro.py

from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.allegro import AllegroAccountOut
from urllib.parse import urlencode
from typing import List
from sqlalchemy import select, func
from models.models import AllegroAccount
from config import settings
from models.database import get_db
from models.models import User
from services.allegro_service import AllegroService
from services.user_service import UserService
from utils.dependencies import get_current_user, get_user_service
from utils.auth import create_state_token, verify_state_token


def get_allegro_service() -> AllegroService:
    return AllegroService(
        client_id=settings.ALLEGRO_CLIENT_ID,
        client_secret=settings.ALLEGRO_CLIENT_SECRET,
        redirect_uri=settings.ALLEGRO_REDIRECT_URI,
        auth_url=settings.ALLEGRO_AUTH_URL
    )
async def count_user_allegro_accounts(db: AsyncSession, user_id: int) -> int:
    """Подсчитывает количество аккаунтов Allegro у пользователя."""
    query = select(func.count(AllegroAccount.id)).where(AllegroAccount.owner_id == user_id)
    result = await db.execute(query)
    return result.scalar_one()

async def get_user_allegro_accounts(db: AsyncSession, user_id: int) -> List[AllegroAccount]:
    query = select(AllegroAccount).where(AllegroAccount.owner_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


router = APIRouter(prefix="/api/allegro", tags=["Allegro"])


@router.get("/auth/url")
def get_allegro_auth_url(
        current_user: User = Depends(get_current_user),
        allegro_service: AllegroService = Depends(get_allegro_service)
):
    state_token = create_state_token(user_id=current_user.id)
    auth_url = allegro_service.get_authorization_url()
    return {"authorization_url": f"{auth_url}&state={state_token}"}


@router.get("/auth/callback")
async def allegro_auth_callback(
        code: str = Query(...),
        state: str = Query(...),
        db: AsyncSession = Depends(get_db),
        user_service: UserService = Depends(get_user_service),
        allegro_service: AllegroService = Depends(get_allegro_service)
):
    redirect_url = f"{settings.FRONTEND_URL}/settings/accounts"

    user_id = verify_state_token(state)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state token")


    user = await user_service.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


    try:
        token_data = await allegro_service.get_allegro_tokens(code)

        allegro_user_data = await allegro_service.get_allegro_user_details(token_data['access_token'])
        # --- ИЗМЕНЕНИЕ ЗДЕСЬ: ПРОВЕРКА ЛИМИТА АККАУНТОВ ---
        # Проверяем, существует ли уже такой аккаунт у пользователя
        existing_account_query = select(AllegroAccount).filter_by(owner_id=user.id,
                                                                  allegro_user_id=allegro_user_data.get('id'))
        existing_account = (await db.execute(existing_account_query)).scalar_one_or_none()

        # Если аккаунт новый (не обновление токена существующего)
        if not existing_account:
            # Если у пользователя подписка Pro
            if user.subscription_status == 'pro':
                current_accounts_count = await count_user_allegro_accounts(db, user_id=user.id)
                if current_accounts_count >= 5:
                    error_params = urlencode({"error": "Достигнут лимит в 5 аккаунтов для подписки Pro."})
                    return RedirectResponse(url=f"{redirect_url}?{error_params}")

            # Для бесплатных пользователей можно установить лимит в 1 аккаунт
            elif user.subscription_status == 'free':
                current_accounts_count = await count_user_allegro_accounts(db, user_id=user.id)
                if current_accounts_count >= 1:  # Например, лимит в 1 аккаунт для бесплатных
                    error_params = urlencode({"error": "Бесплатный план позволяет добавить только 1 аккаунт."})
                    return RedirectResponse(url=f"{redirect_url}?{error_params}")

        # Если лимит не превышен (или это подписка Maxi/Trial), создаем или обновляем аккаунт
        await allegro_service.create_or_update_account(db, user, allegro_user_data, token_data)

        params = urlencode({"success": "true"})
        return RedirectResponse(url=f"{redirect_url}?{params}")

    except HTTPException as e:
        # Этот блок сработает, если одна из функций вернет ошибку
        params = urlencode({"error": e.detail})
        return RedirectResponse(url=f"{redirect_url}?{params}")
    except Exception as e:
        # Этот блок поймает любые другие ошибки (например, KeyError)
        params = urlencode({"error": "Произошла внутренняя ошибка сервера."})
        return RedirectResponse(url=f"{redirect_url}?{params}")

@router.get("/accounts", response_model=List[AllegroAccountOut])
async def list_user_allegro_accounts(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
        """
        Возвращает список всех привязанных аккаунтов Allegro для текущего пользователя.
        """
        accounts = await get_user_allegro_accounts(db=db, user_id=current_user.id)
        return accounts