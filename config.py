import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Класс для управления настройками приложения.
    Автоматически считывает переменные из .env файла.
    """
    # Указываем Pydantic, что нужно искать .env файл
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # --- Настройки базы данных ---
    # Pydantic возьмет эту переменную прямо из вашего .env
    DATABASE_URL: str

    # --- Настройки безопасности и JWT ---
    # Ключ для подписи JWT токенов. ОЧЕНЬ ВАЖНО ЕГО ЗАПОЛНИТЬ!
    SECRET_KEY: str

    # Ключ для шифрования (если используется)
    ENCRYPTION_KEY: str

    # Алгоритм подписи токенов
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Настройки Allegro API ---
    ALLEGRO_CLIENT_ID: str
    ALLEGRO_CLIENT_SECRET: str
    ALLEGRO_REDIRECT_URI: str  # URL для коллбэка от Allegro

    # --- Настройки фронтенда ---
    FRONTEND_URL: str


# Создаем единственный экземпляр настроек, который будет использоваться во всем приложении
settings = Settings()

# Проверка при запуске на наличие критически важных ключей
if not settings.SECRET_KEY or not settings.ENCRYPTION_KEY:
    raise ValueError(
        "Переменные SECRET_KEY и ENCRYPTION_KEY не могут быть пустыми. "
        "Пожалуйста, задайте их в вашем .env файле."
    )