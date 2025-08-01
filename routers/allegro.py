# routers/allegro.py

from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from ..config import settings
from ..models.database import get_db
from ..models.models import User
from ..services.allegro_service import AllegroService
from ..services.user_service import UserService
from ..utils.dependencies import get_current_user, get_user_service
from ..utils.auth import create_state_token, verify_state_token


def get_allegro_service() -> AllegroService:
    return AllegroService(
        client_id=settings.ALLEGRO_CLIENT_ID,
        client_secret=settings.ALLEGRO_CLIENT_SECRET,
        redirect_uri=settings.ALLEGRO_REDIRECT_URI,
        auth_url=settings.ALLEGRO_AUTH_URL
    )


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

    print("\n--- DEBUG: Вход в /auth/callback ---")

    user_id = verify_state_token(state)
    if not user_id:
        print("--- DEBUG ERROR: Невалидный state-токен ---")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state token")

    print(f"--- DEBUG STEP 1: State-токен валиден, user_id: {user_id} ---")

    user = await user_service.get_user_by_id(db, user_id=user_id)
    if not user:
        print(f"--- DEBUG ERROR: Пользователь с ID {user_id} не найден ---")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"--- DEBUG STEP 2: Пользователь {user.email} найден в БД ---")

    try:
        print("--- DEBUG STEP 3: Попытка обменять code на токен Allegro... ---")
        token_data = await allegro_service.get_allegro_tokens(code)
        print(f"--- DEBUG STEP 4: Токены от Allegro получены: {token_data} ---")

        allegro_user_data = await allegro_service.get_allegro_user_details(token_data['access_token'])
        print(f"--- DEBUG STEP 5: Данные пользователя Allegro получены: {allegro_user_data} ---")

        await allegro_service.create_or_update_account(db, user, allegro_user_data, token_data)
        print("--- DEBUG STEP 6: Данные сохранены в БД, сейчас будет commit... ---")

        params = urlencode({"success": "true"})
        return RedirectResponse(url=f"{redirect_url}?{params}")

    except HTTPException as e:
        # Этот блок сработает, если одна из функций вернет ошибку
        print(f"--- DEBUG HTTP EXCEPTION: {e.detail} ---")
        params = urlencode({"error": e.detail})
        return RedirectResponse(url=f"{redirect_url}?{params}")
    except Exception as e:
        # Этот блок поймает любые другие ошибки (например, KeyError)
        print(f"--- DEBUG UNEXPECTED ERROR: {type(e).__name__}: {e} ---")
        params = urlencode({"error": "Произошла внутренняя ошибка сервера."})
        return RedirectResponse(url=f"{redirect_url}?{params}")