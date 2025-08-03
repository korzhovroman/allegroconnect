# services/allegro_client.py

import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select  # <--- ДОБАВЬТЕ ЭТОТ ИМПОРТ

from utils.security import decrypt_data
from models.database import get_db
from models.models import AllegroAccount


ALLEGRO_API_URL = "https://api.allegro.pl"

class AllegroClient:
    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Access token is required")

        self.access_token = access_token
        self.client = httpx.AsyncClient(
            base_url=ALLEGRO_API_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/vnd.allegro.public.v1+json"
            }
        )

    async def get_threads(self, limit: int = 20, offset: int = 0):
        """
        Получает список диалогов (threads) из Allegro.
        Эндпоинт: GET /messaging/threads
        """
        try:
            response = await self.client.get(
                f"/messaging/threads?limit={limit}&offset={offset}"
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error fetching threads: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail="Failed to fetch threads from Allegro API"
            )

async def get_allegro_client(
    allegro_account_id: int,
    current_user_id: int,
    db: AsyncSession = Depends(get_db)
) -> AllegroClient:
    """
    Фабрика для создания AllegroClient для КОНКРЕТНОГО аккаунта Allegro.
    Проверяет, что аккаунт принадлежит текущему пользователю.
    """
    query = select(AllegroAccount).where(
        AllegroAccount.id == allegro_account_id,
        AllegroAccount.owner_id == current_user_id
    )
    result = await db.execute(query)
    allegro_account = result.scalar_one_or_none()

    if not allegro_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allegro account not found or you do not have permission to access it."
        )

    access_token = decrypt_data(allegro_account.access_token)
    return AllegroClient(access_token)