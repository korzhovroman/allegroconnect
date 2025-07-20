import os
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.models import User
from services.allegro_service import AllegroService
from utils.dependencies import get_current_user

router = APIRouter(prefix="/api/allegro", tags=["Allegro"])


@router.get("/auth/url")
def get_allegro_auth_url():
    """Генерирует ссылку для авторизации пользователя на Allegro."""
    client_id = os.getenv("ALLEGRO_CLIENT_ID")
    redirect_uri = os.getenv("ALLEGRO_REDIRECT_URI")
    auth_url = (
        "https://allegro.pl/auth/oauth/authorize"
        f"?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"
    )
    return {"authorization_url": auth_url}


@router.get("/auth/callback")
async def allegro_auth_callback(
        code: str = Query(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Callback эндпоинт, на который Allegro перенаправляет пользователя
    после авторизации.
    """
    try:
        # 1. Обменять код на токены
        token_data = await AllegroService.get_allegro_tokens(code)

        # 2. Получить данные пользователя Allegro
        allegro_user_data = await AllegroService.get_allegro_user_details(token_data['access_token'])

        # 3. Сохранить или обновить аккаунт в нашей БД
        await AllegroService.create_or_update_account(db, current_user, allegro_user_data, token_data)

        # 4. Перенаправить пользователя на страницу настроек в нашем приложении
        # (URL фронтенда нужно будет указать в .env)
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(url=f"{frontend_url}/settings/accounts?success=true")

    except HTTPException as e:
        # В случае ошибки перенаправляем с сообщением
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(url=f"{frontend_url}/settings/accounts?error={e.detail}")