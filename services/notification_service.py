# services/notification_service.py
import firebase_admin
from firebase_admin import credentials, messaging

# --- Бесключевая инициализация ---
# В среде Railway/Google Cloud учетные данные подхватятся автоматически
try:
    firebase_admin.initialize_app()
    print("Firebase Admin SDK инициализирован автоматически.")
except Exception as e:
    print(f"ОШИБКА при автоматической инициализации Firebase: {e}")


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