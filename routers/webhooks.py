# routers/webhooks.py
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any
from models.database import get_db
from models.models import User
from config import settings
from utils.security import safe_compare
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# --- Модели для данных от RevenueCat ---
class Event(BaseModel):
    app_user_id: str = Field(..., alias="app_user_id")
    type: str
    expires_at_ms: int | None = Field(None, alias="expires_at_ms")
    product_identifier: str | None = None  # Поле для определения типа подписки
    period_type: str | None = None  # Поле для определения, триал ли это

class WebhookPayload(BaseModel):
    api_version: str
    event: Event

# --- Эндпоинт для приема вебхуков ---
@router.post("/revenuecat")
async def handle_revenuecat_webhook(
    payload: WebhookPayload,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db)
):
    expected_token = f"Bearer {settings.REVENUECAT_WEBHOOK_TOKEN}"
    if not authorization or not safe_compare(authorization, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # 2. Ищем пользователя по его ID, который пришел от RevenueCat
    # app_user_id от RevenueCat - это наш supabase_user_id
    user_id = payload.event.app_user_id
    user = (await db.execute(select(User).where(User.supabase_user_id == user_id))).scalar_one_or_none()

    if not user:
        # Если пользователя нет, мы ничего не можем сделать.
        # Это может произойти, если вебхук пришел раньше, чем пользователь
        # был синхронизирован через /sync-user. Это редкий, но возможный случай.
        # Просто сообщаем RevenueCat, что все в порядке, чтобы он не повторял попытку.
        return {"status": "User not found, but acknowledged"}

    # 3. Обновляем статус подписки в зависимости от типа события
    event_type = payload.event.type
    new_status = user.subscription_status
    new_end_date = user.subscription_ends_at

    # Обработка начала триала
    if event_type == "INITIAL_PURCHASE" and payload.event.period_type == "TRIAL":
        new_status = "trial"
        if payload.event.expires_at_ms:
            new_end_date = datetime.fromtimestamp(payload.event.expires_at_ms / 1000)

    # Обработка покупок и возобновлений
    elif event_type in ["INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION"]:
        product_id = payload.event.product_identifier
        if product_id == "pro_subscription":
            new_status = "pro"
        elif product_id == "maxi_subscription":
            new_status = "maxi"
        # Если пришел триал от Maxi подписки, он тоже будет maxi (согласно вашей логике)
        elif payload.event.period_type == "TRIAL":
            new_status = "trial"

        if payload.event.expires_at_ms:
            new_end_date = datetime.fromtimestamp(payload.event.expires_at_ms / 1000)

    # Обработка отмены и истечения срока (без изменений)
    elif event_type == "CANCELLATION":
        # При отмене подписка еще действует до конца периода, но мы можем сменить статус
        # на pro_canceled / maxi_canceled, если хотим это отслеживать.
        # Пока оставляем просто "canceled".
        new_status = "canceled"
    elif event_type == "EXPIRATION":
        new_status = "free"

    user.subscription_status = new_status
    user.subscription_ends_at = new_end_date
    await db.commit()

    return {"status": "success"}