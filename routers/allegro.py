# routers/allegro.py

from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from ..config import settings
from ..models.database import get_db
from ..models.models import User
from ..services.allegro_service import AllegroService
from ..services.user_service import UserService # <-- Добавляем импорт UserService
from ..utils.dependencies import get_current_user, get_user_service # <-- И провайдер для него
from ..utils.auth import create_state_token, verify_state_token # <-- Импортируем новые функции

def get_allegro_service() -> AllegroService:
    # ... (эта функция остается без изменений) ...
    return AllegroService(
        client_id=settings.ALLEGRO_CLIENT_ID,
        client_secret=settings.ALLEGRO_CLIENT_SECRET,
        redirect_uri=settings.ALLEGRO_REDIRECT_URI,
        auth_url=settings.ALLEGRO_AUTH_URL
    )

router = APIRouter(prefix="/api/allegro", tags=["Allegro"])

# ИЗМЕНЕНИЕ 1: Теперь этот эндпоинт требует авторизации и создает state
@router.get("/auth/url")
def get_allegro_auth_url(
    current_user: User = Depends(get_current_user), # <-- Пользователь должен быть залогинен
    allegro_service: AllegroService = Depends(get_allegro_service)
):
    """Генерирует ссылку для авторизации пользователя на Allegro."""
    state_token = create_state_token(user_id=current_user.id)
    auth_url = allegro_service.get_authorization_url()
    # Добавляем state к URL
    return {"authorization_url": f"{auth_url}&state={state_token}"}


# ИЗМЕНЕНИЕ 2: Убираем JWT-аутентификацию, используем state
@router.get("/auth/callback")
async def allegro_auth_callback(
    code: str = Query(...),
    state: str = Query(...), # <-- Получаем state от Allegro
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service), # <-- Получаем UserService
    allegro_service: AllegroService = Depends(get_allegro_service)
):
    redirect_url = f"{settings.FRONTEND_URL}/settings/accounts"

    # Проверяем state и получаем ID пользователя
    user_id = verify_state_token(state)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state token")

    # Находим пользователя по ID
    user = await user_service.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        # Продолжаем логику, как и раньше, но с пользователем, найденным через state
        token_data = await allegro_service.get_allegro_tokens(code)
        allegro_user_data = await allegro_service.get_allegro_user_details(token_data['access_token'])
        await allegro_service.create_or_update_account(db, user, allegro_user_data, token_data)

        params = urlencode({"success": "true"})
        return RedirectResponse(url=f"{redirect_url}?{params}")

    except HTTPException as e:
        params = urlencode({"error": e.detail})
        return RedirectResponse(url=f"{redirect_url}?{params}")