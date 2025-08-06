# config.py

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Определяем путь к корневой папке проекта
ROOT_DIR = Path(__file__).parent.resolve()


class Settings(BaseSettings):
    """
    Класс для управления настройками приложения.
    """
    model_config = SettingsConfigDict(env_file=os.path.join(ROOT_DIR, '.env'), env_file_encoding='utf-8')

    # --- Настройки режима работы ---
    # По умолчанию выключено для безопасности.
    # Для локальной разработки добавьте DEBUG=true в .env файл.
    DEBUG: bool = False

    # --- Настройки базы данных ---
    DATABASE_URL: str

    # --- Настройки безопасности и JWT ---
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Настройки Allegro API ---
    ALLEGRO_CLIENT_ID: str
    ALLEGRO_CLIENT_SECRET: str
    ALLEGRO_REDIRECT_URI: str
    ALLEGRO_API_URL: str = "https://api.allegro.pl"
    ALLEGRO_AUTH_URL: str = "https://allegro.pl/auth/oauth"

    # --- Настройки фронтенда ---
    FRONTEND_URL: str

    # --- Настройки Supabase ---
    SUPABASE_JWT_SECRET: str

    # --- КЛЮЧ ДЛЯ REVENUECAT ---
    REVENUECAT_WEBHOOK_TOKEN: str


# Создаем единственный экземпляр настроек
settings = Settings()

# Проверка на наличие критически важных ключей
if not settings.SECRET_KEY or not settings.ENCRYPTION_KEY:
    raise ValueError(
        "Переменные SECRET_KEY и ENCRYPTION_KEY не могут быть пустыми. "
        "Пожалуйста, задайте их в вашем .env файле."
    )