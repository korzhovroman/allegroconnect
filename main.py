# main.py
import logging
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from schemas.api import APIResponse
from sqlalchemy import text
from routers import auth, allegro, conversations, webhooks, teams
from services.auto_responder_service import AutoResponderService
from config import settings
from utils.rate_limiter import limiter
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from pydantic import BaseModel
from models.database import AsyncSessionLocal

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO if settings.DEBUG else logging.WARNING),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger()

scheduler = AsyncIOScheduler()

class CsrfSettings(BaseModel):
    secret_key: str

@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings(secret_key=settings.CSRF_SECRET_KEY)

async def run_task_producer():
    logger.info("Планировщик запускает задачу 'Производителя'...")
    db_session = AsyncSessionLocal()
    try:
        result = await db_session.execute(text("SELECT id FROM allegro_accounts;"))
        account_ids = []
        for raw_id in result.scalars().all():
            try:
                account_ids.append(int(raw_id))
            except (ValueError, TypeError):
                logger.warning(f"Не удалось преобразовать ID аккаунта в число: {raw_id}. Пропускаем.")
                continue

        if not account_ids:
            logger.info("Нет аккаунтов для обработки.")
            return

        for acc_id in account_ids:
            insert_stmt = text("""
                INSERT INTO task_queue (allegro_account_id, status)
                VALUES (:acc_id, 'pending')
                ON CONFLICT (allegro_account_id) DO NOTHING;
            """)
            await db_session.execute(insert_stmt, {"acc_id": acc_id})

        await db_session.commit()
        logger.info(f"Добавлено {len(account_ids)} задач в очередь.")

    except Exception as e:
        logger.error(f"Ошибка в 'Производителе' задач: {e}", exc_info=True)
    finally:
        await db_session.close()


async def run_cleanup_task():
    logger.info("Планировщик запускает задачу очистки логов...")
    db_session = AsyncSessionLocal()
    try:
        service = AutoResponderService(db=db_session)
        await service.cleanup_old_logs()
    except Exception as e:
        logger.error(f"Ошибка при очистке логов: {e}", exc_info=True)
    finally:
        await db_session.close()

async def run_cleanup_metadata_task():
    logger.info("Планировщик запускает задачу очистки метаданных...")
    db_session = AsyncSessionLocal()
    try:
        service = AutoResponderService(db=db_session)
        await service.cleanup_old_message_metadata()
    except Exception as e:
        logger.error(f"Ошибка при очистке метаданных: {e}", exc_info=True)
    finally:
        await db_session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from models.database import create_tables
    #await create_tables()

    scheduler.add_job(run_task_producer, 'interval', minutes=5, id="task_producer_job")
    scheduler.add_job(run_cleanup_task, 'cron', hour=3, minute=0, id="cleanup_job")
    scheduler.add_job(run_cleanup_metadata_task, 'cron', hour=3, minute=30, id="cleanup_metadata_job")
    scheduler.start()
    logger.info("Планировщик задач запущен")
    yield
    scheduler.shutdown()
    logger.info("Планировщик задач остановлен")


app = FastAPI(
    title="Allegro Connect API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


if not settings.DEBUG:
    from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
    app.add_middleware(HTTPSRedirectMiddleware)

allowed_origins = []
if settings.FRONTEND_URL:
    allowed_origins.append(settings.FRONTEND_URL)
if settings.DEBUG:
    allowed_origins.extend(["http://localhost:3000", "http://127.0.0.1:3000", "https://app.flutterflow.io"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):

    logger.error(
        "Unhandled exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        method=str(request.method),
        url=str(request.url),
        exc_info=settings.DEBUG
    )
    return JSONResponse(
        status_code=500,
        content=APIResponse(
            success=False,
            error_message="Internal server error",
            error_code="INTERNAL_ERROR"
        ).model_dump()
    )

@app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            error_message=exc.message,
            error_code="CSRF_ERROR"
        ).model_dump()
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            error_message=exc.detail,
            error_code=f"HTTP_{exc.status_code}" # Пример кода ошибки
        ).model_dump()
    )

app.include_router(auth.router)
app.include_router(allegro.router)
app.include_router(conversations.router)
app.include_router(webhooks.router)
app.include_router(teams.router)

@app.get("/api/csrf-token", response_model=APIResponse[dict])
def get_csrf_token(csrf_protect: CsrfProtect = Depends()):
    response = JSONResponse(
        status_code=200,
        content=APIResponse(data={"detail": "CSRF cookie set"}).model_dump()
    )
    csrf_protect.set_csrf_cookie(response)
    return response

@app.get("/")
async def root():
    return {"message": "Allegro Connect API is running"}


@app.get("/health")
async def health_check():
    """Health check endpoint для мониторинга."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}