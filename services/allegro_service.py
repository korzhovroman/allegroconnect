# services/allegro_service.py

import httpx
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.models import User, AllegroAccount
from ..utils.security import encrypt_data
from ..config import settings


class AllegroService:
    # ИСПРАВЛЕНИЕ: Конструктор теперь принимает параметры конфигурации.
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, auth_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = auth_url
        self.api_url = settings.ALLEGRO_API_URL

    def get_authorization_url(self) -> str:
        # ИСПРАВЛЕНИЕ: Используются переменные экземпляра (self.client_id), а не os.getenv
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        return f"{self.auth_url}/authorize?{urlencode(params)}"

    async def get_allegro_tokens(self, code: str) -> dict:
        auth_header = httpx.BasicAuth(self.client_id, self.client_secret)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(f"{self.auth_url}/token", auth=auth_header, data=data)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Улучшенная обработка ошибок
                error_details = e.response.json()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Не удалось обменять код на токен. Ошибка Allegro: {error_details}"
                )
        return response.json()

    # ... остальная часть файла без изменений ...
    async def get_allegro_user_details(self, access_token: str) -> dict:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.allegro.public.v1+json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_url}/me", headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not fetch Allegro user details")
        return response.json()

    async def create_or_update_account(self, db: AsyncSession, user: User, allegro_data: dict, token_data: dict):
        allegro_user_id = allegro_data['id']
        result = await db.execute(select(AllegroAccount).filter_by(owner_id=user.id, allegro_user_id=allegro_user_id))
        db_account = result.scalar_one_or_none()
        encrypted_access_token = encrypt_data(token_data['access_token'])
        encrypted_refresh_token = encrypt_data(token_data['refresh_token'])
        expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
        if db_account:
            db_account.access_token = encrypted_access_token
            db_account.refresh_token = encrypted_refresh_token
            db_account.expires_at = expires_at
        else:
            db_account = AllegroAccount(owner_id=user.id, allegro_user_id=allegro_user_id, allegro_login=allegro_data['login'], access_token=encrypted_access_token, refresh_token=encrypted_refresh_token, expires_at=expires_at)
            db.add(db_account)
        await db.commit()
        await db.refresh(db_account)
        return db_account