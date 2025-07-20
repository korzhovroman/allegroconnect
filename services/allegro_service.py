import httpx
import os
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.models import User, AllegroAccount
from utils.security import encrypt_data  # Предполагаем, что этот файл создан
from datetime import datetime, timedelta

# URL-адреса API Allegro
ALLEGRO_AUTH_URL = "https://allegro.pl/auth/oauth"
ALLEGRO_API_URL = "https://api.allegro.pl"


class AllegroService:
    @staticmethod
    async def get_allegro_tokens(code: str) -> dict:
        """Обменивает авторизационный код на токены доступа."""
        client_id = os.getenv("ALLEGRO_CLIENT_ID")
        client_secret = os.getenv("ALLEGRO_CLIENT_SECRET")
        redirect_uri = os.getenv("ALLEGRO_REDIRECT_URI")

        auth_header = httpx.BasicAuth(client_id, client_secret)

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{ALLEGRO_AUTH_URL}/token", auth=auth_header, data=data)

        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not exchange code for token")

        return response.json()

    @staticmethod
    async def get_allegro_user_details(access_token: str) -> dict:
        """Получает детали пользователя с API Allegro."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.allegro.public.v1+json"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ALLEGRO_API_URL}/me", headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not fetch Allegro user details")

        return response.json()

    @staticmethod
    async def create_or_update_account(db: AsyncSession, user: User, allegro_data: dict, token_data: dict):
        """Создает или обновляет привязанный аккаунт Allegro в нашей БД."""
        allegro_user_id = allegro_data['id']

        # Проверяем, существует ли уже такой аккаунт
        result = await db.execute(
            select(AllegroAccount).filter_by(owner_id=user.id, allegro_user_id=allegro_user_id)
        )
        db_account = result.scalar_one_or_none()

        # Шифруем токены
        encrypted_access_token = encrypt_data(token_data['access_token'])
        encrypted_refresh_token = encrypt_data(token_data['refresh_token'])
        expires_in = token_data['expires_in']
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

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