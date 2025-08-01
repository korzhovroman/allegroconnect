# services/allegro_service.py

import httpx
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..models.models import User, AllegroAccount
from ..utils.security import encrypt_data
from ..config import settings


class AllegroService:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, auth_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = auth_url
        self.api_url = settings.ALLEGRO_API_URL

    def get_authorization_url(self) -> str:
        params = {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri}
        return f"{self.auth_url}/authorize?{urlencode(params)}"

    async def get_allegro_tokens(self, code: str) -> dict:
        """Обменивает авторизационный код на токены доступа с подробным логгированием."""

        # --- ОТЛАДОЧНЫЙ БЛОК ---
        print("\n" + "=" * 50)
        print("--- DEBUG: Вход в get_allegro_tokens ---")

        auth_header = httpx.BasicAuth(self.client_id, self.client_secret)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        print(f"URL для запроса токена: {self.auth_url}/token")
        print(f"Отправляемые данные (data): {data}")
        print(f"Client ID для Basic Auth: {self.client_id}")
        # Из соображений безопасности не будем выводить полный Client Secret
        print(f"Client Secret для Basic Auth: ...{self.client_secret[-4:]}")
        print("=" * 50 + "\n")
        # --- КОНЕЦ ОТЛАДОЧНОГО БЛОКА ---

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(f"{self.auth_url}/token", auth=auth_header, data=data)

                # --- ОТЛАДОЧНЫЙ БЛОК ОТВЕТА ---
                print("\n" + "=" * 50)
                print("--- DEBUG: Ответ от Allegro ---")
                print(f"Статус-код ответа: {response.status_code}")
                try:
                    # Пытаемся красиво напечатать JSON, если это возможно
                    response_json = response.json()
                    print("Тело ответа (JSON):")
                    print(json.dumps(response_json, indent=2))
                except json.JSONDecodeError:
                    # Если ответ не JSON, печатаем как текст
                    print("Тело ответа (не JSON):")
                    print(response.text)
                print("=" * 50 + "\n")
                # --- КОНЕЦ ОТЛАДОЧНОГО БЛОКА ОТВЕТА ---

                response.raise_for_status()
                token_data = response.json()

                if 'access_token' not in token_data:
                    raise HTTPException(status_code=400, detail="Allegro не вернул 'access_token'.")

                return token_data

            except httpx.HTTPStatusError as e:
                # Эта ошибка будет более информативной благодаря логам выше
                raise HTTPException(status_code=400, detail=f"HTTP Ошибка от Allegro: {e.response.text}")

    # Остальная часть файла остается без изменений
    async def get_allegro_user_details(self, access_token: str) -> dict:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.allegro.public.v1+json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_url}/me", headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Не удалось получить данные пользователя Allegro.")
        return response.json()

    async def create_or_update_account(self, db: AsyncSession, user: User, allegro_data: dict, token_data: dict):
        allegro_user_id = allegro_data.get('id')
        if not allegro_user_id:
            raise HTTPException(status_code=400, detail="Ответ от Allegro не содержит 'id' пользователя.")

        access_token = token_data.get('access_token')
        if not access_token:
            raise HTTPException(status_code=400, detail="Ответ от Allegro не содержит 'access_token'.")

        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 3600)
        allegro_login = allegro_data.get('login', 'unknown')

        encrypted_access_token = encrypt_data(access_token)
        encrypted_refresh_token = encrypt_data(refresh_token)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        result = await db.execute(select(AllegroAccount).filter_by(owner_id=user.id, allegro_user_id=allegro_user_id))
        db_account = result.scalar_one_or_none()

        if db_account:
            db_account.access_token = encrypted_access_token
            db_account.refresh_token = encrypted_refresh_token
            db_account.expires_at = expires_at
        else:
            db_account = AllegroAccount(
                owner_id=user.id,
                allegro_user_id=allegro_user_id,
                allegro_login=allegro_login,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expires_at=expires_at
            )
            db.add(db_account)

        await db.commit()
        await db.refresh(db_account)
        return db_account