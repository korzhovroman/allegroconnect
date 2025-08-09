# config.py
import os
from pathlib import Path
from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet

ROOT_DIR = Path(__file__).parent.resolve()


class Settings(BaseSettings):
    """
    Класс для управления настройками приложения.
    """
    model_config = SettingsConfigDict(env_file=os.path.join(ROOT_DIR, '.env'), env_file_encoding='utf-8')
    # --- Настройки режима работы ---
    DEBUG: bool = False
    # --- Настройки базы данных ---
    DATABASE_URL: str
    # --- Настройки безопасности и JWT ---
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    CSRF_SECRET_KEY: str
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
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    # --- КЛЮЧ ДЛЯ REVENUECAT ---
    REVENUECAT_WEBHOOK_TOKEN: str
    # --- Лимиты подписок ---
    SUB_LIMITS: Dict[str, int] = {
        "free": 1,
        "trial": 1,
        "pro": 3,
        "maxi": -1,
        "canceled": -1  # Для отмененных подписок тоже сохраняем лимит до конца периода
    }

settings = Settings()

def model_post_init(self, __context):
    """Проверяем формат ключей после инициализации"""
    # Проверяем, что ENCRYPTION_KEY валидный для Fernet
    try:
        Fernet(self.ENCRYPTION_KEY.encode())
    except Exception:
        raise ValueError(
            "ENCRYPTION_KEY должен быть валидным Fernet ключом. "
            "Сгенерируйте новый: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )

# Проверка на наличие критически важных ключей
if not settings.SECRET_KEY or not settings.ENCRYPTION_KEY:
    raise ValueError(
        "Переменные SECRET_KEY и ENCRYPTION_KEY не могут быть пустыми. "
        "Пожалуйста, задайте их в вашем .env файле."
    )