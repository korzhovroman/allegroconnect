# services/notification_service.py
import firebase_admin
from firebase_admin import messaging, credentials
import os
import json
import logging

# Используем стандартный logging, так как этот модуль может импортироваться раньше
# конфигурации structlog в `shared.py`, чтобы избежать циклических зависимостей.
logger = logging.getLogger(__name__)


def initialize_firebase():
    """Безопасная инициализация Firebase с проверкой credentials"""
    # Если уже инициализировано, ничего не делаем
    if firebase_admin._apps:
        return True

    try:
        # Вариант 1: Через переменную окружения с путем к файлу (стандартный для Google Cloud)
        if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
            firebase_admin.initialize_app()
            logger.info("Firebase инициализирован через GOOGLE_APPLICATION_CREDENTIALS")
            return True

        # Вариант 2: Через JSON-строку в переменной окружения (удобно для Railway/Heroku)
        firebase_key = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')
        if firebase_key:
            try:
                # Парсим JSON из переменной окружения
                service_account_info = json.loads(firebase_key)
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase инициализирован через FIREBASE_SERVICE_ACCOUNT_KEY")
                return True
            except json.JSONDecodeError:
                logger.error("Переменная окружения FIREBASE_SERVICE_ACCOUNT_KEY содержит некорректный JSON.")

        # Если ни один из способов не сработал - отключаем уведомления
        logger.warning("Учетные данные Firebase не найдены. Push-уведомления будут отключены.")
        return False

    except Exception as e:
        logger.error(f"Критическая ошибка при инициализации Firebase: {e}", exc_info=True)
        return False


# Инициализируем Firebase при первом импорте этого модуля
FIREBASE_ENABLED = initialize_firebase()


def send_notification(token: str, title: str, body: str):
    """Отправляет push-уведомление через Firebase Cloud Messaging."""
    if not FIREBASE_ENABLED:
        # Это сообщение можно закомментировать, чтобы не засорять логи, если уведомления не настроены
        # logger.info(f"Firebase отключен. Пропускаем отправку уведомления: {title}")
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
        # Эта ошибка означает, что токен больше не действителен (например, пользователь удалил приложение)
        # В будущем здесь можно добавить логику для удаления недействительного токена из БД
        logger.warning(f"FCM токен не зарегистрирован или истек: {token[:15]}...")
    except messaging.InvalidArgumentError as e:
        logger.error(f"Некорректные аргументы для отправки push-уведомления: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке push-уведомления: {e}", exc_info=True)