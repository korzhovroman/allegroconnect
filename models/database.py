from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator

# 1. Импортируем наш центральный объект настроек
from config import settings

# 2. Создаем движок, используя URL из настроек
# echo=settings.DB_ECHO можно добавить в конфиг, чтобы включать/выключать логирование SQL
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# Фабрика асинхронных сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Базовый класс для моделей
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency provider для получения асинхронной сессии БД.
    """
    # 3. Упрощенная и более идиоматичная версия. `async with` все делает за нас.
    async with AsyncSessionLocal() as session:
        yield session