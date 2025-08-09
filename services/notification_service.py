# services/notification_service.py
import firebase_admin
from firebase_admin import messaging, credentials
import os
import json
import logging

logger = logging.getLogger(__name__)

def initialize_firebase():
    """Безопасная инициализация Firebase с проверкой credentials"""
    if firebase_admin._apps:
        return True

    try:
        if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
            firebase_admin.initialize_app()
            logger.info("Firebase инициализирован через GOOGLE_APPLICATION_CREDENTIALS")
            return True

        firebase_key = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')
        if firebase_key:
            try:
                service_account_info = json.loads(firebase_key)
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase инициализирован через FIREBASE_SERVICE_ACCOUNT_KEY")
                return True
            except json.JSONDecodeError:
                logger.error("Переменная окружения FIREBASE_SERVICE_ACCOUNT_KEY содержит некорректный JSON.")

        logger.warning("Учетные данные Firebase не найдены. Push-уведомления будут отключены.")
        return False

    except Exception as e:
        logger.error(f"Критическая ошибка при инициализации Firebase: {e}", exc_info=True)
        return False


FIREBASE_ENABLED = initialize_firebase()


def send_notification(token: str, title: str, body: str):
    """Отправляет push-уведомление через Firebase Cloud Messaging."""
    if not FIREBASE_ENABLED:
        return

    if not token:
        logger.warning("FCM токен отсутствует, отправка уведомления отменена.")
        return

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=token,
    )

    try:
        response = messaging.send(message)
        logger.info(f"Push-уведомление отправлено успешно: {response}")
    except messaging.UnregisteredError:
        logger.warning(f"FCM токен не зарегистрирован или истек: {token[:15]}...")
    except messaging.InvalidArgumentError as e:
        logger.error(f"Некорректные аргументы для отправки push-уведомления: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке push-уведомления: {e}", exc_info=True)