# routers/allegro.py
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from urllib.parse import urlencode
from schemas.allegro import AllegroAccountOut
from schemas.api import APIResponse
from models.models import AllegroAccount, User
from config import settings
from models.database import get_db
from services.allegro_service import AllegroService
from utils.dependencies import get_current_user_from_db
from utils.auth import create_state_token, verify_state_token
from utils.rate_limiter import limiter

router = APIRouter(prefix="/api/allegro", tags=["Allegro"])


def get_allegro_service() -> AllegroService:
    return AllegroService(
        client_id=settings.ALLEGRO_CLIENT_ID,
        client_secret=settings.ALLEGRO_CLIENT_SECRET,
        redirect_uri=settings.ALLEGRO_REDIRECT_URI,
        auth_url=settings.ALLEGRO_AUTH_URL,
    )


async def count_user_allegro_accounts(db: AsyncSession, user_id: int) -> int:
    query = select(func.count(AllegroAccount.id)).where(AllegroAccount.owner_id == user_id)
    return (await db.execute(query)).scalar_one()


async def get_user_allegro_accounts(db: AsyncSession, user_id: int) -> List[AllegroAccount]:
    query = select(AllegroAccount).where(AllegroAccount.owner_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/auth/url", response_model=APIResponse[dict])
@limiter.limit("20/minute")
async def get_allegro_auth_url(
        request: Request,
        current_user: User = Depends(get_current_user_from_db),
        allegro_service: AllegroService = Depends(get_allegro_service),
):
    state_token = create_state_token(user_id=current_user.id)
    auth_url = allegro_service.get_authorization_url()
    return APIResponse(data={"authorization_url": f"{auth_url}&state={state_token}"})


@router.get("/auth/callback")
@limiter.limit("20/minute")
async def allegro_auth_callback(
        request: Request,
        code: str = Query(...),
        state: str = Query(...),
        db: AsyncSession = Depends(get_db),
        allegro_service: AllegroService = Depends(get_allegro_service),
):
    redirect_url = f"{settings.FRONTEND_URL}/settings/accounts"

    user_id = verify_state_token(state)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state token")

    # --- Получаем пользователя напрямую из БД ---
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # -----------------------------------------------------------

    try:
        current_status = user.subscription_status
        limit = settings.SUB_LIMITS.get(current_status, 0)

        # Проверяем лимит перед добавлением нового аккаунта
        existing_account_query = select(AllegroAccount).filter_by(owner_id=user.id)
        existing_accounts = (await db.execute(existing_account_query)).scalars().all()

        if limit != -1 and len(existing_accounts) >= limit:
            error_message = f"Osiągnięto limit {limit} kont dla Twojego planu taryfowego '{current_status}'."
            error_params = urlencode({"error": error_message})
            return RedirectResponse(url=f"{redirect_url}?{error_params}")

        token_data = await allegro_service.get_allegro_tokens(code)
        allegro_user_data = await allegro_service.get_allegro_user_details(token_data['access_token'])

        await allegro_service.create_or_update_account(db, user, allegro_user_data, token_data)
        params = urlencode({"success": "true"})
        return RedirectResponse(url=f"{redirect_url}?{params}")

    except HTTPException as e:
        params = urlencode({"error": e.detail})
        return RedirectResponse(url=f"{redirect_url}?{params}")
    except Exception as e:
        from utils.logger import logger
        logger.error("Ошибка в коллбэке Allegro", error=str(e), exc_info=True)
        error_message = "Wystąpił wewnętrzny błąd serwera."
        params = urlencode({"error": error_message})
        return RedirectResponse(url=f"{redirect_url}?{params}")


@router.get("/accounts", response_model=APIResponse[List[AllegroAccountOut]])
@limiter.limit("100/minute")
async def list_user_allegro_accounts(
        request: Request,
        current_user: User = Depends(get_current_user_from_db),
        db: AsyncSession = Depends(get_db),
):
    accounts = await get_user_allegro_accounts(db=db, user_id=current_user.id)
    return APIResponse(data=accounts)