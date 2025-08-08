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
from schemas.api import APIResponse

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

class Event(BaseModel):
    app_user_id: str = Field(..., alias="app_user_id")
    type: str
    expires_at_ms: int | None = Field(None, alias="expires_at_ms")
    product_identifier: str | None = None
    period_type: str | None = None

class WebhookPayload(BaseModel):
    api_version: str
    event: Event

@router.post("/revenuecat", response_model=APIResponse[dict])
async def handle_revenuecat_webhook(
    payload: WebhookPayload,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db)
):
    expected_token = f"Bearer {settings.REVENUECAT_WEBHOOK_TOKEN}"
    if not authorization or not safe_compare(authorization, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.event.app_user_id
    user = (await db.execute(select(User).where(User.supabase_user_id == user_id))).scalar_one_or_none()

    if not user:
        return APIResponse(data={"status": "User not found, but acknowledged"})

    event_type = payload.event.type
    new_status = user.subscription_status
    new_end_date = user.subscription_ends_at

    if event_type == "INITIAL_PURCHASE" and payload.event.period_type == "TRIAL":
        new_status = "trial"
        if payload.event.expires_at_ms:
            new_end_date = datetime.fromtimestamp(payload.event.expires_at_ms / 1000)

    elif event_type in ["INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION"]:
        product_id = payload.event.product_identifier
        if product_id == "pro_subscription":
            new_status = "pro"
        elif product_id == "maxi_subscription":
            new_status = "maxi"
        elif payload.event.period_type == "TRIAL":
            new_status = "trial"

        if payload.event.expires_at_ms:
            new_end_date = datetime.fromtimestamp(payload.event.expires_at_ms / 1000)

    elif event_type == "CANCELLATION":
        new_status = "canceled"
    elif event_type == "EXPIRATION":
        new_status = "free"

    user.subscription_status = new_status
    user.subscription_ends_at = new_end_date
    await db.commit()

    return APIResponse(data={"status": "success"})