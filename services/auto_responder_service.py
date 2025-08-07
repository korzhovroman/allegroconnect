# services/auto_responder_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone
from models.models import AllegroAccount, AutoReplyLog, User
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
        # Исправленный запрос, который выбирает все необходимые поля
        query = select(
            AllegroAccount.id,
            AllegroAccount.allegro_login,
            AllegroAccount.auto_reply_enabled,
            AllegroAccount.auto_reply_text,
            AllegroAccount.access_token,
            User.fcm_token
        ).join(User, AllegroAccount.owner_id == User.id).where(AllegroAccount.id == account_id)

        result = await self.db.execute(query)
        account_data = result.mappings().first()

        if not account_data:
            print(f"Аккаунт с ID {account_id} не найден.")
            return

        # Теперь все ключи будут на месте
        account_login = account_data["allegro_login"]
        fcm_token = account_data["fcm_token"]
        auto_reply_enabled = account_data["auto_reply_enabled"]
        reply_text = account_data["auto_reply_text"]

        print(f"Обрабатываем аккаунт: {account_login} (ID: {account_id})")

        try:
            access_token = decrypt_data(account_data["access_token"])
            client = AllegroClient(access_token)
            threads_data = await client.get_threads(limit=20, offset=0)
            threads = threads_data.get('threads', [])

            for thread in threads:
                if not thread.get('read', True) and await self._is_new_message_from_buyer(client, thread, account_id):
                    print(f"  -> Обнаружен новый непрочитанный диалог {thread['id']}.")

                    # Отправляем PUSH-уведомление
                    if fcm_token:
                        try:
                            interlocutor = thread.get('interlocutor', {}).get('login', 'Покупатель')
                            title = f"Новое сообщение от {interlocutor}"
                            body = f"Аккаунт: {account_login}. Нажмите, чтобы ответить."
                            send_notification(token=fcm_token, title=title, body=body)
                        except Exception as e:
                            print(f"  ОШИБКА при отправке PUSH: {e}")

                    # Отправляем автоответ, если включен
                    if auto_reply_enabled and reply_text:
                        print(f"  -> Автоответчик включен. Отправляем ответ.")
                        await client.post_thread_message(thread['id'], reply_text)

                    # Логируем, чтобы не обработать снова
                    await self._log_conversation_as_processed(thread['id'], account_id)
                    print(f"  -> Диалог {thread['id']} помечен как обработанный.")

        except Exception as e:
            print(f"  ОШИБКА при обработке аккаунта {account_login}: {e}")

    async def _is_new_message_from_buyer(self, client: AllegroClient, thread: dict, account_id: int) -> bool:
        """
        Проверяет, не обработан ли диалог нами ранее И является ли последнее сообщение от покупателя.
        """
        thread_id = thread['id']
        log_entry = await self.db.execute(select(AutoReplyLog).where(
            AutoReplyLog.conversation_id == thread_id,
            AutoReplyLog.allegro_account_id == account_id
        ))
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
        """Удаляет записи из лога автоответчика старше 30 дней."""
        try:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            stmt = delete(AutoReplyLog).where(AutoReplyLog.reply_time < thirty_days_ago)
            result = await self.db.execute(stmt)
            await self.db.commit()
            print(f"--- Очистка логов завершена. Удалено {result.rowcount} старых записей. ---")
        except Exception as e:
            print(f"ОШИБКА во время очистки логов: {e}")
            await self.db.rollback()