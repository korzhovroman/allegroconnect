# main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from routers import auth, allegro, conversations
from services.auto_responder_service import AutoResponderService
from config import settings

# --- ЛОГИКА АВТООТВЕТЧИКА И LIFESPAN ---

# Создаем асинхронную сессию для фоновой задачи
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
scheduler = AsyncIOScheduler()

async def run_auto_responder_task():
    """Функция-обертка для запуска сервиса автоответчика."""
    print("Планировщик запускает задачу автоответчика...")
    db_session = AsyncSessionLocal()
    try:
        service = AutoResponderService(db=db_session)
        await service.run_auto_responder()
    finally:
        await db_session.close()

# НОВЫЙ, СОВРЕМЕННЫЙ СПОСОБ УПРАВЛЕНИЯ ФОНОВЫМИ ЗАДАЧАМИ
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Этот код выполняется при старте приложения
    scheduler.add_job(run_auto_responder_task, 'interval', minutes=5)
    scheduler.start()
    print("Планировщик задач запущен. Автоответчик будет работать в фоновом режиме.")
    yield
    # Этот код выполняется при остановке приложения (если нужно)
    scheduler.shutdown()
    print("Планировщик задач остановлен.")

app = FastAPI(title="Allegro Connect API", version="1.0.0", lifespan=lifespan)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ОТЛАДОЧНЫЙ ЭНДПОИНТ ДЛЯ ТЕСТИРОВАНИЯ ---
@app.get("/debug/run-responder")
async def debug_run_responder():
    """Немедленно запускает задачу автоответчика."""
    await run_auto_responder_task()
    return {"message": "Auto-responder task has been triggered successfully."}

# --- Подключение роутеров ---
app.include_router(auth.router)
app.include_router(allegro.router)
app.include_router(conversations.router)

@app.get("/")
async def root():
    return {"message": "Allegro Connect API is running"}