# services/allegro_client.py

import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from utils.security import decrypt_data
from models.database import get_db
from models.models import AllegroAccount

ALLEGRO_API_URL = "https://api.allegro.pl"


class AllegroClient:
    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Access token is required")
        self.access_token = access_token
        self.base_headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.allegro.public.v1+json"
        }
        self.client = httpx.AsyncClient(base_url=ALLEGRO_API_URL, headers=self.base_headers)

    async def _request(self, method: str, url: str, headers: dict = None, **kwargs):
        """Внутренний метод-обертка для всех запросов для обработки ошибок."""
        request_headers = self.base_headers.copy()
        if headers:
            request_headers.update(headers)

        try:
            response = await self.client.request(method, url, headers=request_headers, **kwargs)
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error making request to {e.request.url}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to make request to Allegro API: {e.response.text}"
            )

    async def get_threads(self, limit: int = 20, offset: int = 0):
        return await self._request("GET", f"/messaging/threads?limit={limit}&offset={offset}")

    async def get_thread_messages(self, thread_id: str, limit: int = 20, offset: int = 0):
        return await self._request("GET", f"/messaging/threads/{thread_id}/messages?limit={limit}&offset={offset}")

    async def post_thread_message(self, thread_id: str, text: str, attachment_id: str = None):
        message_data = {"text": text, "type": "REGULAR"}
        if attachment_id:
            message_data["attachment"] = {"id": attachment_id}
        return await self._request("POST", f"/messaging/threads/{thread_id}/messages", json={"message": message_data})

    async def get_offer_details(self, offer_id: str):
        return await self._request("GET", f"/sale/offers/{offer_id}")

    async def get_issues(self, limit: int = 20, offset: int = 0):
        headers = {"Accept": "application/vnd.allegro.beta.v1+json"}
        return await self._request("GET", f"/sale/issues?limit={limit}&offset={offset}", headers=headers)

    async def get_issue_details(self, issue_id: str):
        headers = {"Accept": "application/vnd.allegro.beta.v1+json"}
        return await self._request("GET", f"/sale/issues/{issue_id}", headers=headers)

    async def get_issue_messages(self, issue_id: str):
        headers = {"Accept": "application/vnd.allegro.beta.v1+json"}
        return await self._request("GET", f"/sale/issues/{issue_id}/chat", headers=headers)

    async def post_issue_message(self, issue_id: str, text: str):
        headers = {"Accept": "application/vnd.allegro.beta.v1+json"}
        message_data = {"text": text, "type": "REGULAR"}
        return await self._request("POST", f"/sale/issues/{issue_id}/message", json=message_data, headers=headers)

    async def get_order_details(self, checkout_form_id: str):
        return await self._request("GET", f"/order/checkout-forms/{checkout_form_id}")

    async def declare_attachment(self, file_name: str, file_size: int) -> dict:
        """
        Объявляет о намерении загрузить вложение.
        """
        declaration_data = {
            "fileName": file_name,
            "fileSize": file_size
        }
        # Для этого эндпоинта нужен особый Content-Type
        headers = {"Content-Type": "application/vnd.allegro.public.v1+json"}
        return await self._request("POST", "/sale/message-attachments", json=declaration_data, headers=headers)


# "Фабрика" для создания клиента
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
    access_token = decrypt_data(allegro_account.access_token)
    return AllegroClient(access_token)