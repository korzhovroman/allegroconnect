from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

# 1. Импортируем наш централизованный объект настроек
from ..config import settings
from ..models.database import get_db
from ..models.models import User
from ..services.allegro_service import AllegroService
from ..utils.dependencies import get_current_user

# 2. Создаем "провайдер" для нашего сервиса, чтобы использовать Depends
def get_allegro_service() -> AllegroService:
    """Dependency provider for AllegroService."""
    # Используем настройки для инициализации сервиса
    return AllegroService(
        client_id=settings.ALLEGRO_CLIENT_ID,
        client_secret=settings.ALLEGRO_CLIENT_SECRET,
        redirect_uri=settings.ALLEGRO_REDIRECT_URI,
        auth_url=settings.ALLEGRO_AUTH_URL
    )


router = APIRouter(prefix="/api/allegro", tags=["Allegro"])


@router.get("/auth/url")
def get_allegro_auth_url(
    # 3. Внедряем сервис через Depends
    allegro_service: AllegroService = Depends(get_allegro_service)
):
    """Генерирует ссылку для авторизации пользователя на Allegro."""
    # Вызываем метод экземпляра, а не статический метод
    return {"authorization_url": allegro_service.get_authorization_url()}


@router.get("/auth/callback")
async def allegro_auth_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    # 3. Внедряем сервис и здесь
    allegro_service: AllegroService = Depends(get_allegro_service)
):
    """
    Callback эндпоинт, на который Allegro перенаправляет пользователя
    после авторизации.
    """
    # 4. Убираем дублирование, определяя URL один раз
    redirect_url = f"{settings.FRONTEND_URL}/settings/accounts"

    try:
        token_data = await allegro_service.get_allegro_tokens(code)
        allegro_user_data = await allegro_service.get_allegro_user_details(token_data['access_token'])
        await allegro_service.create_or_update_account(db, current_user, allegro_user_data, token_data)

        # Формируем URL с параметром успеха
        params = urlencode({"success": "true"})
        return RedirectResponse(url=f"{redirect_url}?{params}")

    except HTTPException as e:
        # Формируем URL с параметром ошибки
        params = urlencode({"error": e.detail})
        return RedirectResponse(url=f"{redirect_url}?{params}")