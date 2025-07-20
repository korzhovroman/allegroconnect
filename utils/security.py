from cryptography.fernet import Fernet
import os

# Убедитесь, что эта переменная есть в вашем .env файле
# Сгенерировать ключ можно командой: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# Проверяем, что ключ загружен
if not ENCRYPTION_KEY:
    raise ValueError("Необходимо установить ENCRYPTION_KEY в .env файле")

fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_data(data: str) -> str:
    if not isinstance(data, str):
        raise TypeError("Данные для шифрования должны быть строкой")
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    if not isinstance(encrypted_data, str):
        raise TypeError("Данные для расшифровки должны быть строкой")
    return fernet.decrypt(encrypted_data.encode()).decode()