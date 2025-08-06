# main.py
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from routers import auth, allegro, conversations, webhooks
from services.auto_responder_service import AutoResponderService
from config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Rate limiter (ограничитель частоты запросов)
limiter = Limiter(key_func=get_remote_address)

# Асинхронная сессия для фоновых задач
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
scheduler = AsyncIOScheduler()

async def run_auto_responder_task():
    """Функция-обертка для запуска сервиса автоответчика."""
    logger.info("Планировщик запускает задачу автоответчика...")
    db_session = AsyncSessionLocal()
    try:
        service = AutoResponderService(db=db_session)
        await service.run_auto_responder()
    except Exception as e:
        logger.error(f"Ошибка в автоответчике: {e}", exc_info=True)
    finally:
        await db_session.close()

async def run_cleanup_task():
    """Функция-обертка для запуска сервиса очистки."""
    logger.info("Планировщик запускает задачу очистки логов...")
    db_session = AsyncSessionLocal()
    try:
        service = AutoResponderService(db=db_session)
        await service.cleanup_old_logs()
    except Exception as e:
        logger.error(f"Ошибка при очистке логов: {e}", exc_info=True)
    finally:
        await db_session.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запуск при старте приложения
    scheduler.add_job(run_auto_responder_task, 'interval', minutes=5, id="auto_responder_job")
    scheduler.add_job(run_cleanup_task, 'cron', hour=3, minute=0, id="cleanup_job")
    scheduler.start()
    logger.info("Планировщик задач запущен")
    yield
    # Остановка при завершении приложения
    scheduler.shutdown()
    logger.info("Планировщик задач остановлен")

# Создание приложения
app = FastAPI(
    title="Allegro Connect API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

# Подключение Rate limiter'а
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Безопасность: HTTPS redirect в production
if not settings.DEBUG:
    app.add_middleware(HTTPSRedirectMiddleware)

# Безопасные CORS настройки
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

# Глобальный обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Необработанная ошибка: {exc} at {request.method} {request.url}", exc_info=True)
    if not settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )
    # В режиме отладки показываем ошибку
    raise exc

# Отладочный эндпоинт (только для разработки)
if settings.DEBUG:
    @app.get("/debug/run-responder")
    async def debug_run_responder():
        """Немедленно запускает задачу автоответчика."""
        await run_auto_responder_task()
        return {"message": "Auto-responder task has been triggered successfully."}

# Подключение роутеров
app.include_router(auth.router)
app.include_router(allegro.router)
app.include_router(conversations.router)
app.include_router(webhooks.router)

@app.get("/")
@limiter.limit("100/minute")
async def root(request: Request):
    return {"message": "Allegro Connect API is running", "version": "1.0.0"}

@app.get("/health")
@limiter.limit("100/minute")
async def health_check(request: Request):
    """Health check endpoint для мониторинга."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
