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

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# --- Модели для данных от RevenueCat ---
class Event(BaseModel):
    app_user_id: str = Field(..., alias="app_user_id")
    type: str
    expires_at_ms: int | None = Field(None, alias="expires_at_ms")

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
    # 1. Проверяем "секретное слово" (токен)
    if not authorization or authorization != f"Bearer {settings.REVENUECAT_WEBHOOK_TOKEN}":
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

    if event_type in ["INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION"]:
        new_status = "active"
        if payload.event.expires_at_ms:
            new_end_date = datetime.fromtimestamp(payload.event.expires_at_ms / 1000)
    elif event_type == "CANCELLATION":
        # При отмене подписка еще действует до конца оплаченного периода
        new_status = "canceled"
    elif event_type == "EXPIRATION":
        # Подписка закончилась
        new_status = "free"

    user.subscription_status = new_status
    user.subscription_ends_at = new_end_date
    await db.commit()

    return {"status": "success"}