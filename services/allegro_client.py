# services/allegro_client.py

import httpx
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from utils.security import decrypt_data, encrypt_data
from models.database import get_db
from models.models import AllegroAccount
from config import settings
from .allegro_service import AllegroService

ALLEGRO_API_URL = "https://api.allegro.pl"


class AllegroClient:
    # --- ИЗМЕНЯЕМ КОНСТРУКТОР КЛАССА ---
    def __init__(self, db: AsyncSession, allegro_account: AllegroAccount):
        self.db = db
        self.allegro_account = allegro_account
        self.access_token = decrypt_data(allegro_account.access_token)
        self.base_headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.allegro.public.v1+json"
        }
        self.client = httpx.AsyncClient(base_url=ALLEGRO_API_URL, headers=self.base_headers)

    # --- ЗДЕСЬ ВСЯ МАГИЯ ---
    async def _request(self, method: str, url: str, is_retry: bool = False, **kwargs):
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            # Для POST/PUT и др. методов без тела ответа
            if response.status_code in [status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED, status.HTTP_204_NO_CONTENT]:
                return response.json() if response.content else {}
            return response.json()
        except httpx.HTTPStatusError as e:
            # Если токен истек и это первая попытка запроса
            if e.response.status_code == status.HTTP_401_UNAUTHORIZED and not is_retry:
                print(f"Токен для аккаунта {self.allegro_account.allegro_login} истек. Пытаемся обновить...")
                refreshed = await self._refresh_and_save_tokens()
                if refreshed:
                    # Повторяем изначальный запрос, но с флагом is_retry=True, чтобы избежать бесконечного цикла
                    return await self._request(method, url, is_retry=True, **kwargs)
            # Если обновить не удалось или ошибка другая, пробрасываем ее дальше
            print(f"Error from Allegro API for request {e.request.url}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Error from Allegro API: {e.response.text}"
            )

    async def _refresh_and_save_tokens(self) -> bool:
        """Внутренний метод для обновления и сохранения токенов."""
        # Создаем экземпляр сервиса Allegro
        service = AllegroService(
            client_id=settings.ALLEGRO_CLIENT_ID,
            client_secret=settings.ALLEGRO_CLIENT_SECRET,
            redirect_uri=settings.ALLEGRO_REDIRECT_URI,
            auth_url=settings.ALLEGRO_AUTH_URL
        )

        decrypted_refresh_token = decrypt_data(self.allegro_account.refresh_token)
        new_token_data = await service.refresh_tokens(decrypted_refresh_token)

        if not new_token_data or 'access_token' not in new_token_data:
            print(f"Критическая ошибка: не удалось обновить токен для аккаунта {self.allegro_account.id}")
            return False

        # Обновляем данные в объекте и в базе
        self.allegro_account.access_token = encrypt_data(new_token_data['access_token'])
        self.allegro_account.refresh_token = encrypt_data(new_token_data['refresh_token'])
        expires_in = new_token_data.get('expires_in', 3600)
        self.allegro_account.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        await self.db.commit()
        await self.db.refresh(self.allegro_account)

        # Обновляем токен и заголовки в текущем экземпляре клиента
        self.access_token = new_token_data['access_token']
        self.client.headers["Authorization"] = f"Bearer {self.access_token}"

        print(f"Токен для аккаунта {self.allegro_account.allegro_login} успешно обновлен.")
        return True

    # Методы ниже теперь используют умный _request, который умеет обновлять токен
    async def get_threads(self, limit: int = 20, offset: int = 0):
        return await self._request("GET", f"/messaging/threads?limit={limit}&offset={offset}")

    async def get_thread_messages(self, thread_id: str, limit: int = 20, offset: int = 0):
        return await self._request("GET", f"/messaging/threads/{thread_id}/messages?limit={limit}&offset={offset}")

    async def post_thread_message(self, thread_id: str, text: str, attachment_id: str = None):
        message_data = {
            "text": text,
            "type": "REGULAR",
            "attachment": {"id": attachment_id} if attachment_id else None
        }
        headers = {"Content-Type": "application/vnd.allegro.public.v1+json"}
        return await self._request("POST", f"/messaging/threads/{thread_id}/messages", headers=headers,
                                   json=message_data)

    # ... и так далее для всех остальных методов API ...
    async def get_issues(self, limit: int = 20, offset: int = 0):
        headers = {"Accept": "application/vnd.allegro.beta.v1+json"}
        return await self._request("GET", f"/sale/issues?limit={limit}&offset={offset}", headers=headers)

    # ... (остальные методы без изменений, они автоматически будут использовать новую логику)


# --- ОБНОВЛЯЕМ "ФАБРИКУ" КЛИЕНТА ---
async def get_allegro_client(allegro_account_id: int, current_user_id: int,
                             db: AsyncSession = Depends(get_db)) -> AllegroClient:
    query = select(AllegroAccount).where(
        AllegroAccount.id == allegro_account_id,
        AllegroAccount.owner_id == current_user_id
    )
    result = await db.execute(query)
    allegro_account = result.scalar_one_or_none()

    if not allegro_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Allegro account not found or you do not have permission to access it.")

    # Теперь мы передаем в клиент сессию и весь объект аккаунта
    return AllegroClient(db=db, allegro_account=allegro_account)