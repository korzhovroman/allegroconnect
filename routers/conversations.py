# routers/conversations.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.message import MessageCreate
from services.allegro_client import get_allegro_client
from utils.dependencies import get_premium_user
from models.models import User, AllegroAccount
from models.database import get_db
from datetime import datetime
from pydantic import BaseModel
from schemas.allegro import AllegroAccountSettingsUpdate, AllegroAccountOut
from sqlalchemy import select

# Импортируем limiter из main.py
from main import limiter

class AttachmentDeclare(BaseModel):
    file_name: str
    file_size: int

router = APIRouter(prefix="/api/allegro", tags=["Allegro Actions"])

# --- Общие сообщения ---
@router.get("/{allegro_account_id}/threads", response_model=dict)
@limiter.limit("100/minute")
async def get_allegro_threads(
    request: Request,
    allegro_account_id: int,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.get_threads()

@router.get("/{allegro_account_id}/threads/{thread_id}/messages", response_model=dict)
@limiter.limit("100/minute")
async def get_allegro_thread_messages(
    request: Request,
    allegro_account_id: int,
    thread_id: str,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.get_thread_messages(thread_id=thread_id)

@router.post("/{allegro_account_id}/threads/{thread_id}/messages", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute") # Ограничение на отправку сообщений
async def post_allegro_thread_message(
    request: Request,
    allegro_account_id: int,
    thread_id: str,
    message: MessageCreate,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.post_thread_message(thread_id=thread_id, text=message.text, attachment_id=message.attachment_id)

# --- Эндпоинты для ISSUES ---
@router.get("/{allegro_account_id}/issues", response_model=dict)
@limiter.limit("100/minute")
async def get_allegro_issues(
    request: Request,
    allegro_account_id: int,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.get_issues()

# ... (продолжение кода для conversations.py) ...

@router.get("/{allegro_account_id}/issues/{issue_id}", response_model=dict)
@limiter.limit("100/minute")
async def get_allegro_issue_details(
    request: Request,
    allegro_account_id: int,
    issue_id: str,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.get_issue_details(issue_id=issue_id)

@router.get("/{allegro_account_id}/issues/{issue_id}/messages", response_model=dict)
@limiter.limit("100/minute")
async def get_allegro_issue_messages(
    request: Request,
    allegro_account_id: int,
    issue_id: str,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.get_issue_messages(issue_id=issue_id)

@router.post("/{allegro_account_id}/issues/{issue_id}/messages", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def post_allegro_issue_message(
    request: Request,
    allegro_account_id: int,
    issue_id: str,
    message: MessageCreate,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.post_issue_message(issue_id=issue_id, text=message.text)

# --- Вспомогательные эндпоинты ---
@router.get("/{allegro_account_id}/offers/{offer_id}", response_model=dict)
@limiter.limit("100/minute")
async def get_allegro_offer_details(
    request: Request,
    allegro_account_id: int,
    offer_id: str,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.get_offer_details(offer_id=offer_id)

@router.get("/{allegro_account_id}/orders/{order_id}", response_model=dict)
@limiter.limit("100/minute")
async def get_allegro_order_details(
    request: Request,
    allegro_account_id: int,
    order_id: str,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.get_order_details(checkout_form_id=order_id)

@router.post("/{allegro_account_id}/attachments/declare", response_model=dict)
@limiter.limit("30/minute")
async def declare_allegro_attachment(
    request: Request,
    allegro_account_id: int,
    declaration: AttachmentDeclare,
    current_user: User = Depends(get_premium_user),
    db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    return await client.declare_attachment(
        file_name=declaration.file_name,
        file_size=declaration.file_size
    )

# --- ОБЪЕДИНЕННЫЙ ЭНДПОИНТ ДЛЯ ФРОНТЕНДА ---
@router.get("/{allegro_account_id}/conversations", response_model=dict)
@limiter.limit("100/minute")
async def get_all_conversations(
        request: Request,
        allegro_account_id: int,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current_user: User = Depends(get_premium_user),
        db: AsyncSession = Depends(get_db)
):
    client = await get_allegro_client(allegro_account_id, current_user.id, db)
    all_conversations = []
    errors = []

    try:
        threads_response = await client.get_threads(limit=limit, offset=offset)
        for thread in threads_response.get('threads', []):
            all_conversations.append({
                "id": thread.get('id'),
                "type": "message",
                "lastMessageDateTime": thread.get('lastMessageDateTime'),
                "read": thread.get('read'),
                "interlocutor": thread.get('interlocutor')
            })
    except Exception as e:
        print(f"ERROR fetching threads: {e}")
        errors.append("Could not fetch regular messages.")

    try:
        issues_response = await client.get_issues(limit=limit, offset=offset)
        for issue in issues_response.get('issues', []):
            all_conversations.append({
                "id": issue.get('id'),
                "type": issue.get('type', 'issue').lower(),
                "lastMessageDateTime": issue.get('lastUpdateDateTime'),
                "read": issue.get('read'),
                "subject": issue.get('subject')
            })
    except Exception as e:
        print(f"ERROR fetching issues: {e}")
        errors.append("Could not fetch discussions and claims (Allegro internal error).")

    all_conversations.sort(
        key=lambda x: datetime.fromisoformat(x['lastMessageDateTime'].replace('Z', '+00:00')),
        reverse=True
    )

    return {"conversations": all_conversations, "errors": errors}

@router.patch("/{allegro_account_id}/settings", response_model=AllegroAccountOut)
@limiter.limit("30/minute")
async def update_allegro_account_settings(
        request: Request,
        allegro_account_id: int,
        settings: AllegroAccountSettingsUpdate,
        current_user: User = Depends(get_premium_user),
        db: AsyncSession = Depends(get_db)
):
    query = select(AllegroAccount).where(
        AllegroAccount.id == allegro_account_id,
        AllegroAccount.owner_id == current_user.id
    )
    result = await db.execute(query)
    db_account = result.scalar_one_or_none()

    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = settings.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_account, key, value)

    await db.commit()
    await db.refresh(db_account)
    return db_account
