# services/notification_service.py
import firebase_admin
from firebase_admin import credentials, messaging
from config import settings
import json

# --- Инициализация из переменной окружения ---
try:
    # Преобразуем JSON-строку из переменной окружения в словарь
    creds_json = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
    cred = credentials.Certificate(creds_json)
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK инициализирован успешно.")
except json.JSONDecodeError:
    print("ОШИБКА: Не удалось прочитать FIREBASE_CREDENTIALS_JSON. Убедитесь, что это валидный JSON.")
except Exception as e:
    print(f"ОШИБКА при инициализации Firebase: {e}")


def send_notification(token: str, title: str, body: str):
    if not firebase_admin._apps:
        print("Firebase не инициализирован, отправка уведомления отменена.")
        return

    if not token:
        return

    message = messaging.message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
    )
    try:
        response = messaging(message)
        print("Successfully sent message:", response)
    except Exception as e:
        print("Error sending message:", e)