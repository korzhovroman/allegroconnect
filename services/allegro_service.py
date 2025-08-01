# services/allegro_service.py

import httpx
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.models import User, AllegroAccount
# Важно: Убедитесь, что у вас есть этот файл и функция
from ..utils.security import encrypt_data, decrypt_data
from ..config import settings # Импортируем наш центральный конфиг


class AllegroService:
    def __init__(self):
        """
        Инициализирует сервис с конфигурацией из центрального файла.
        """
        self.client_id = settings.ALLEGRO_CLIENT_ID
        self.client_secret = settings.ALLEGRO_CLIENT_SECRET
        self.redirect_uri = settings.ALLEGRO_REDIRECT_URI
        self.auth_url = settings.ALLEGRO_AUTH_URL
        self.api_url = settings.ALLEGRO_API_URL

    def get_authorization_url(self) -> str:
        """
        Генерирует полную ссылку для редиректа на авторизацию Allegro.
        """
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "prompt": "confirm" # Рекомендуется для явного подтверждения пользователя
        }
        # Используем urlencode для корректного форматирования параметров
        authorize_url = f"{self.auth_url}/authorize?{urlencode(params)}"
        return authorize_url

    async def get_allegro_tokens(self, code: str) -> dict:
        """
        Обменивает авторизационный код на токены доступа.
        """
        auth_header = httpx.BasicAuth(self.client_id, self.client_secret)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(f"{self.auth_url}/token", auth=auth_header, data=data)
                response.raise_for_status() # Вызовет исключение для 4xx/5xx ответов
            except httpx.HTTPStatusError as e:
                # Логируем ошибку и возвращаем понятное сообщение
                print(f"Allegro API error: {e.response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Не удалось обменять код на токен. Проверьте конфигурацию или код авторизации."
                ) from e

        return response.json()

    async def get_allegro_user_details(self, access_token: str) -> dict:
        """Получает детали пользователя с API Allegro."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.allegro.public.v1+json"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.api_url}/me", headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                print(f"Allegro API error: {e.response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Не удалось получить данные пользователя Allegro."
                ) from e

        return response.json()

    async def create_or_update_account(
        self, db: AsyncSession, user: User, allegro_data: dict, token_data: dict
    ):
        """Создает или обновляет привязанный аккаунт Allegro в нашей БД."""
        allegro_user_id = allegro_data['id']

        result = await db.execute(
            select(AllegroAccount).filter_by(owner_id=user.id, allegro_user_id=allegro_user_id)
        )
        db_account = result.scalar_one_or_none()

        # Шифруем токены перед сохранением
        encrypted_access_token = encrypt_data(token_data['access_token'])
        encrypted_refresh_token = encrypt_data(token_data['refresh_token'])
        expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])

        if db_account:
            # Если аккаунт есть, обновляем токены
            db_account.access_token = encrypted_access_token
            db_account.refresh_token = encrypted_refresh_token
            db_account.expires_at = expires_at
        else:
            # Если аккаунта нет, создаем новый
            db_account = AllegroAccount(
                owner_id=user.id,
                allegro_user_id=allegro_user_id,
                allegro_login=allegro_data['login'],
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expires_at=expires_at
            )
            db.add(db_account)

        await db.commit()
        await db.refresh(db_account)
        return db_account