# services/allegro_client.py

import httpx
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

from utils.security import decrypt_data, encrypt_data
from models.models import AllegroAccount
from config import settings
from .allegro_service import AllegroService

ALLEGRO_API_URL = "https://api.allegro.pl"


class AllegroClient:
    """
    Асинхронный клиент для взаимодействия с Allegro REST API.
    Этот клиент инкапсулирует логику аутентификации, автоматического
    обновления токенов и выполнения запросов.
    """

    def __init__(self, db: AsyncSession, allegro_account: AllegroAccount):
        self.db = db
        self.allegro_account = allegro_account
        # Мы не создаем httpx.AsyncClient здесь, чтобы избежать утечек ресурсов.
        # Вместо этого мы будем использовать его как контекстный менеджер.

    @asynccontextmanager
    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Приватный контекстный менеджер для управления жизненным циклом httpx.AsyncClient.
        Гарантирует, что клиент всегда будет закрыт после использования.
        """
        access_token = decrypt_data(self.allegro_account.access_token)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.allegro.public.v1+json",
            "Content-Type": "application/vnd.allegro.public.v1+json"
        }
        async with httpx.AsyncClient(base_url=ALLEGRO_API_URL, headers=headers) as client:
            yield client

    async def _request(self, method: str, url: str, is_retry: bool = False, **kwargs):
        """
        Основной метод для выполнения запросов к API.
        Обрабатывает ошибки, включая истечение срока действия токена.
        """
        try:
            async with self._get_http_client() as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                # Для методов без тела ответа (201, 202, 204)
                return response.json() if response.content else {}
        except httpx.HTTPStatusError as e:
            # Если токен истек (401) и это первая попытка запроса
            if e.response.status_code == status.HTTP_401_UNAUTHORIZED and not is_retry:
                print(f"Токен для аккаунта {self.allegro_account.allegro_login} истек. Пытаемся обновить...")
                refreshed = await self._refresh_and_save_tokens()
                if refreshed:
                    # Повторяем изначальный запрос с флагом is_retry=True
                    return await self._request(method, url, is_retry=True, **kwargs)
            # Если обновить не удалось или ошибка другая, логируем и пробрасываем ее дальше
            error_details = e.response.text
            print(f"Ошибка от API Allegro для {e.request.url}: {error_details}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Error from Allegro API: {error_details}"
            )
        except httpx.RequestError as e:
            # Обработка сетевых ошибок
            print(f"Сетевая ошибка при запросе к Allegro API: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to Allegro API."
            )

    async def _refresh_and_save_tokens(self) -> bool:
        """
        Внутренний метод для обновления и сохранения токенов в БД.
        Важно: этот метод не делает commit. Коммит должен управляться
        на уровне эндпоинта, чтобы обеспечить атомарность транзакции.
        """
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

        # Обновляем данные в объекте SQLAlchemy
        self.allegro_account.access_token = encrypt_data(new_token_data['access_token'])
        self.allegro_account.refresh_token = encrypt_data(new_token_data['refresh_token'])
        expires_in = new_token_data.get('expires_in', 3600)
        self.allegro_account.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        # Не делаем commit здесь! Сессия будет закоммичена в вызывающем коде (в роутере).
        # Это позволяет включить обновление токена в одну транзакцию с другими операциями.
        self.db.add(self.allegro_account)
        await self.db.flush()  # Применяем изменения к сессии, чтобы они были доступны, но не коммитим.

        print(f"Токен для аккаунта {self.allegro_account.allegro_login} успешно обновлен в сессии.")
        return True

    # --- Методы для работы с API Allegro ---
    # Все они используют _request, который обеспечивает безопасное выполнение запросов.

    async def get_threads(self, limit: int = 20, offset: int = 0):
        """Получает список диалогов (threads)."""
        return await self._request("GET", f"/messaging/threads?limit={limit}&offset={offset}")

    async def get_thread_messages(self, thread_id: str, limit: int = 20, offset: int = 0):
        """Получает сообщения из конкретного диалога."""
        return await self._request("GET", f"/messaging/threads/{thread_id}/messages?limit={limit}&offset={offset}")

    async def post_thread_message(self, thread_id: str, text: str, attachment_id: str = None):
        """Отправляет сообщение в диалог."""
        message_data = {"text": text, "type": "REGULAR"}
        if attachment_id:
            message_data["attachment"] = {"id": attachment_id}

        return await self._request("POST", f"/messaging/threads/{thread_id}/messages", json=message_data)

    async def get_issues(self, limit: int = 20, offset: int = 0):
        """Получает список обсуждений/претензий (issues)."""
        headers = {"Accept": "application/vnd.allegro.beta.v1+json"}
        return await self._request("GET", f"/sale/issues?limit={limit}&offset={offset}", headers=headers)

    async def get_issue_messages(self, issue_id: str):
        """Получает сообщения из обсуждения."""
        headers = {"Accept": "application/vnd.allegro.beta.v1+json"}
        return await self._request("GET", f"/sale/issues/{issue_id}/messages", headers=headers)

    async def post_issue_message(self, issue_id: str, text: str):
        """Отправляет сообщение в обсуждение."""
        headers = {"Accept": "application/vnd.allegro.beta.v1+json",
                   "Content-Type": "application/vnd.allegro.beta.v1+json"}
        message_data = {"content": text}
        return await self._request("POST", f"/sale/issues/{issue_id}/messages", headers=headers, json=message_data)

    async def declare_attachment(self, file_name: str, file_size: int):
        """Объявляет вложение для последующей загрузки."""
        declaration_data = {
            "name": file_name,
            "size": file_size,
        }
        return await self._request("POST", "/messaging/message-attachments", json=declaration_data)