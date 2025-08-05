# services/notification_service.py
import firebase_admin
from firebase_admin import messaging

# --- Бесключевая инициализация ---
try:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
        print("Firebase Admin SDK инициализирован автоматически.")
except Exception as e:
    print(f"ОШИБКА при автоматической инициализации Firebase: {e}")


def send_notification(token: str, title: str, body: str):
    """
    Отправляет push-уведомление через Firebase Cloud Messaging.
    """
    if not firebase_admin._apps:
        print("Firebase не инициализирован, отправка уведомления отменена.")
        return

    if not token:
        print("FCM токен отсутствует, отправка уведомления отменена.")
        return

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
    )
    try:

        response = messaging.Message(message)
        print("Successfully sent message:", response)
    except Exception as e:
        print("Error sending message:", e)