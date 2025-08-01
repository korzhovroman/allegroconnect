from cryptography.fernet import Fernet
from passlib.context import CryptContext

# 1. Импортируем наш центральный объект настроек
from ..config import settings

# --- Хеширование паролей ---
# Создаем контекст passlib для хеширования
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет, соответствует ли обычный пароль хешу."""
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    """Возвращает хеш для пароля."""
    return pwd_context.hash(password)


# --- Шифрование данных (для токенов Allegro) ---
# 2. Инициализируем Fernet с ключом из настроек
# Проверка на наличие ключа уже происходит в config.py, здесь она не нужна
fernet = Fernet(settings.ENCRYPTION_KEY.encode())

def encrypt_data(data: str) -> str:
    """Шифрует строку."""
    if not isinstance(data, str):
        raise TypeError("Данные для шифрования должны быть строкой")
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Расшифровывает строку."""
    if not isinstance(encrypted_data, str):
        raise TypeError("Данные для расшифровки должны быть строкой")
    return fernet.decrypt(encrypted_data.encode()).decode()