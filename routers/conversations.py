# routers/conversations.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Изменяем импорт
from services.allegro_client import get_allegro_client
from utils.dependencies import get_current_user
from models.models import User
from models.database import get_db

router = APIRouter(
    # Изменяем префикс, чтобы он был более логичным
    prefix="/api/allegro",
    tags=["Allegro Actions"]
)

# Изменяем URL, чтобы он включал ID аккаунта
@router.get("/{allegro_account_id}/threads", response_model=dict)
async def get_user_allegro_threads(
    allegro_account_id: int, # Получаем ID из URL
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получает список диалогов (threads) для КОНКРЕТНОГО аккаунта Allegro.
    """
    try:
        # Передаем ID аккаунта и ID пользователя в нашу новую фабрику
        allegro_client = await get_allegro_client(
            allegro_account_id=allegro_account_id,
            current_user_id=current_user.id,
            db=db
        )

        threads_data = await allegro_client.get_threads()
        return threads_data

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))