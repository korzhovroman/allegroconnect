# routers/conversations.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.message import MessageCreate
from schemas.api import APIResponse
from services.allegro_client import AllegroClient
from utils.dependencies import get_authorized_allegro_account
from models.models import AllegroAccount
from models.database import get_db
from datetime import datetime
from pydantic import BaseModel
from schemas.allegro import AllegroAccountSettingsUpdate, AllegroAccountOut
from utils.rate_limiter import limiter

class AttachmentDeclare(BaseModel):
    file_name: str
    file_size: int

router = APIRouter(prefix="/api/allegro", tags=["Allegro Actions"])


@router.get("/{allegro_account_id}/threads", response_model=APIResponse[dict], summary="Получить только диалоги (threads)")
@limiter.limit("100/minute")
async def get_allegro_threads(
    request: Request,
    allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Возвращает список только обычных диалогов (threads)."""
    client = AllegroClient(db=db, allegro_account=allegro_account)
    data = await client.get_threads(limit=limit, offset=offset)
    return APIResponse(data=data)


@router.get("/{allegro_account_id}/issues", response_model=APIResponse[dict], summary="Получить только обсуждения (issues)")
@limiter.limit("100/minute")
async def get_allegro_issues(
    request: Request,
    allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Возвращает список только обсуждений и претензий (issues)."""
    client = AllegroClient(db=db, allegro_account=allegro_account)
    data = await client.get_issues(limit=limit, offset=offset)
    return APIResponse(data=data)


@router.get("/{allegro_account_id}/conversations", response_model=APIResponse[dict], summary="Получить все диалоги и обсуждения вместе")
@limiter.limit("100/minute")
async def get_all_conversations(
        request: Request,
        allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        db: AsyncSession = Depends(get_db)
):
    client = AllegroClient(db=db, allegro_account=allegro_account)
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
        logger.error("Ошибка получения threads", error=str(e))
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
        logger.error("Ошибка получения issues", error=str(e))
        errors.append("Could not fetch discussions and claims (Allegro internal error).")

    all_conversations.sort(
        key=lambda x: datetime.fromisoformat(x['lastMessageDateTime'].replace('Z', '+00:00')),
        reverse=True
    )

    data = {"conversations": all_conversations, "errors": errors}
    return APIResponse(data=data)


@router.get("/{allegro_account_id}/threads/{thread_id}/messages", response_model=APIResponse[dict], summary="Получить сообщения из диалога")
@limiter.limit("100/minute")
async def get_allegro_thread_messages(
    request: Request,
    thread_id: str,
    allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
    db: AsyncSession = Depends(get_db)
):
    client = AllegroClient(db=db, allegro_account=allegro_account)
    data = await client.get_thread_messages(thread_id=thread_id)
    return APIResponse(data=data)

@router.post("/{allegro_account_id}/threads/{thread_id}/messages", response_model=APIResponse[dict], status_code=status.HTTP_201_CREATED, summary="Отправить сообщение в диалог")
@limiter.limit("60/minute")
async def post_allegro_thread_message(
    request: Request,
    thread_id: str,
    message: MessageCreate,
    allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
    db: AsyncSession = Depends(get_db)
):
    client = AllegroClient(db=db, allegro_account=allegro_account)
    data = await client.post_thread_message(thread_id=thread_id, text=message.text, attachment_id=message.attachment_id)
    return APIResponse(data=data)


@router.get("/{allegro_account_id}/issues/{issue_id}/messages", response_model=APIResponse[dict], summary="Получить сообщения из обсуждения")
@limiter.limit("100/minute")
async def get_allegro_issue_messages(
    request: Request,
    issue_id: str,
    allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
    db: AsyncSession = Depends(get_db)
):
    client = AllegroClient(db=db, allegro_account=allegro_account)
    data = await client.get_issue_messages(issue_id=issue_id)
    return APIResponse(data=data)

@router.post("/{allegro_account_id}/issues/{issue_id}/messages", response_model=APIResponse[dict], status_code=status.HTTP_201_CREATED, summary="Отправить сообщение в обсуждение")
@limiter.limit("60/minute")
async def post_allegro_issue_message(
    request: Request,
    issue_id: str,
    message: MessageCreate,
    allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
    db: AsyncSession = Depends(get_db)
):
    client = AllegroClient(db=db, allegro_account=allegro_account)
    data = await client.post_issue_message(issue_id=issue_id, text=message.text)
    return APIResponse(data=data)


@router.patch("/{allegro_account_id}/settings", response_model=APIResponse[AllegroAccountOut], summary="Изменить настройки автоответчика")
@limiter.limit("30/minute")
async def update_allegro_account_settings(
        request: Request,
        settings: AllegroAccountSettingsUpdate,
        allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
        db: AsyncSession = Depends(get_db)
):
    update_data = settings.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(allegro_account, key, value)

    await db.commit()
    await db.refresh(allegro_account)
    return APIResponse(data=allegro_account)

@router.post("/{allegro_account_id}/attachments/declare", response_model=APIResponse[dict], summary="Загрузить вложение для сообщения")
@limiter.limit("30/minute")
async def declare_allegro_attachment(
    request: Request,
    declaration: AttachmentDeclare,
    allegro_account: AllegroAccount = Depends(get_authorized_allegro_account),
    db: AsyncSession = Depends(get_db)
):
    client = AllegroClient(db=db, allegro_account=allegro_account)
    data = await client.declare_attachment(
        file_name=declaration.file_name,
        file_size=declaration.file_size
    )
    return APIResponse(data=data)