# services/auto_responder_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone
from models.models import AllegroAccount, AutoReplyLog, User, \
    MessageMetadata  # Убедитесь, что MessageMetadata импортирована
from services.allegro_client import AllegroClient
from services.notification_service import send_notification
from utils.security import decrypt_data


class AutoResponderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_single_account(self, account_id: int):
        """
        Обрабатывает один конкретный аккаунт Allegro. Вызывается воркером.
        """
        # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
        # Шаг 1: Получаем ПОЛНЫЙ объект аккаунта из БД, включая данные его владельца (для fcm_token)
        query = select(AllegroAccount).join(User, AllegroAccount.owner_id == User.id).where(
            AllegroAccount.id == account_id)
        allegro_account = (await self.db.execute(query)).scalar_one_or_none()

        if not allegro_account:
            print(f"Аккаунт с ID {account_id} не найден.")
            return

        # Шаг 2: Создаем клиент ПРАВИЛЬНЫМ способом, передавая сессию и весь объект
        client = AllegroClient(db=self.db, allegro_account=allegro_account)

        account_login = allegro_account.allegro_login
        fcm_token = allegro_account.owner.fcm_token  # Получаем fcm_token через связь
        auto_reply_enabled = allegro_account.auto_reply_enabled
        reply_text = allegro_account.auto_reply_text

        print(f"Обрабатываем аккаунт: {account_login} (ID: {account_id})")

        try:
            # Теперь все запросы к client будут автоматически обновлять токен при необходимости
            threads_data = await client.get_threads(limit=20, offset=0)
            threads = threads_data.get('threads', [])

            for thread in threads:
                if not thread.get('read', True) and await self._is_new_message_from_buyer(client, thread, account_id):
                    print(f"  -> Обнаружен новый непрочитанный диалог {thread['id']}.")
                    if fcm_token:
                        try:
                            interlocutor = thread.get('interlocutor', {}).get('login', 'Покупатель')
                            title = f"Новое сообщение от {interlocutor}"
                            body = f"Аккаунт: {account_login}. Нажмите, чтобы ответить."
                            send_notification(token=fcm_token, title=title, body=body)
                        except Exception as e:
                            print(f"  ОШИБКА при отправке PUSH: {e}")
                    if auto_reply_enabled and reply_text:
                        print(f"  -> Автоответчик включен. Отправляем ответ.")
                        await client.post_thread_message(thread['id'], reply_text)
                    await self._log_conversation_as_processed(thread['id'], account_id)
                    print(f"  -> Диалог {thread['id']} помечен как обработанный.")
        except Exception as e:
            print(f"  ОШИБКА при обработке аккаунта {account_login}: {e}")

    async def _is_new_message_from_buyer(self, client: AllegroClient, thread: dict, account_id: int) -> bool:
        thread_id = thread['id']
        log_entry = await self.db.execute(select(AutoReplyLog).where(AutoReplyLog.conversation_id == thread_id,
                                                                     AutoReplyLog.allegro_account_id == account_id))
        if log_entry.scalar_one_or_none():
            return False
        try:
            messages_data = await client.get_thread_messages(thread_id, limit=1)
            if not messages_data.get('messages'):
                return False
            last_message = messages_data['messages'][0]
            if last_message.get('author', {}).get('role') != 'SELLER':
                return True
        except Exception:
            return False
        return False

    async def _log_conversation_as_processed(self, thread_id: str, account_id: int):
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)
        await self.db.commit()

    async def cleanup_old_logs(self):
        try:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            stmt = delete(AutoReplyLog).where(AutoReplyLog.reply_time < thirty_days_ago)
            result = await self.db.execute(stmt)
            await self.db.commit()
            print(f"--- Очистка логов автоответчика завершена. Удалено {result.rowcount} старых записей. ---")
        except Exception as e:
            print(f"ОШИБКА во время очистки логов автоответчика: {e}")
            await self.db.rollback()

    async def cleanup_old_message_metadata(self):
        retention_period_days = 90
        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=retention_period_days)
        try:
            stmt = delete(MessageMetadata).where(MessageMetadata.sent_at < ninety_days_ago)
            result = await self.db.execute(stmt)
            await self.db.commit()
            print(f"--- Очистка метаданных сообщений завершена. Удалено {result.rowcount} старых записей. ---")
        except Exception as e:
            print(f"ОШИБКА во время очистки метаданных сообщений: {e}")
            await self.db.rollback()