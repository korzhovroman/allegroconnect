# services/auto_responder_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError

from models.models import AllegroAccount, AutoReplyLog, User, MessageMetadata
from services.allegro_client import AllegroClient
from services.notification_service import send_notification
# --- ШАГ 1: Импортируем модели для валидации ---
# (Предполагается, что вы создали этот файл, как в моем предыдущем ответе)
from schemas.allegro_api import ThreadsResponse, MessagesResponse, AllegroThread


class AutoResponderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_single_account(self, account_id: int):
        """
        Обрабатывает один конкретный аккаунт Allegro. Вызывается воркером.
        """
        query = select(AllegroAccount).join(User, AllegroAccount.owner_id == User.id).where(
            AllegroAccount.id == account_id)
        allegro_account = (await self.db.execute(query)).scalar_one_or_none()

        if not allegro_account:
            print(f"Аккаунт с ID {account_id} не найден.")
            return

        client = AllegroClient(db=self.db, allegro_account=allegro_account)
        account_login = allegro_account.allegro_login
        fcm_token = allegro_account.owner.fcm_token
        auto_reply_enabled = allegro_account.auto_reply_enabled
        reply_text = allegro_account.auto_reply_text

        print(f"Обрабатываем аккаунт: {account_login} (ID: {account_id})")

        try:
            # Получаем сырые данные
            raw_threads_data = await client.get_threads(limit=20, offset=0)

            # --- ШАГ 2: ВАЛИДИРУЕМ ДАННЫЕ С Pydantic ---
            try:
                threads_response = ThreadsResponse.model_validate(raw_threads_data)
            except ValidationError as e:
                print(f"  ОШИБКА ВАЛИДАЦИИ ответа от Allegro (threads): {e}")
                return # Прерываем, так как данные не соответствуют контракту

            # --- ШАГ 3: РАБОТАЕМ С БЕЗОПАСНЫМИ ОБЪЕКТАМИ ---
            for thread in threads_response.threads:
                if not thread.read and await self._is_new_message_from_buyer(client, thread, account_id):
                    # Теперь мы используем `thread.id`, а не `thread['id']`
                    print(f"  -> Обнаружен новый непрочитанный диалог {thread.id}.")
                    if fcm_token:
                        try:
                            interlocutor = thread.interlocutor.login if thread.interlocutor else 'Покупатель'
                            title = f"Новое сообщение от {interlocutor}"
                            body = f"Аккаунт: {account_login}. Нажмите, чтобы ответить."
                            send_notification(token=fcm_token, title=title, body=body)
                        except Exception as e:
                            print(f"  ОШИБКА при отправке PUSH: {e}")
                    if auto_reply_enabled and reply_text:
                        print(f"  -> Автоответчик включен. Отправляем ответ.")
                        await client.post_thread_message(thread.id, reply_text)
                    await self._log_conversation_as_processed(thread.id, account_id)
                    print(f"  -> Диалог {thread.id} помечен как обработанный.")
        except Exception as e:
            print(f"  ОШИБКА при обработке аккаунта {account_login}: {e}")

    # --- ШАГ 4: ИЗМЕНЯЕМ ТИП АРГУМЕНТА ---
    async def _is_new_message_from_buyer(self, client: AllegroClient, thread: AllegroThread, account_id: int) -> bool:
        thread_id = thread.id
        log_entry = await self.db.execute(select(AutoReplyLog).where(AutoReplyLog.conversation_id == thread_id,
                                                                     AutoReplyLog.allegro_account_id == account_id))
        if log_entry.scalar_one_or_none():
            return False
        try:
            # --- ШАГ 5: ПОВТОРЯЕМ ВАЛИДАЦИЮ ДЛЯ СООБЩЕНИЙ ---
            raw_messages_data = await client.get_thread_messages(thread_id, limit=1)
            try:
                messages_response = MessagesResponse.model_validate(raw_messages_data)
            except ValidationError as e:
                print(f"  ОШИБКА ВАЛИДАЦИИ ответа от Allegro (messages) для диалога {thread_id}: {e}")
                return False

            if not messages_response.messages:
                return False

            last_message = messages_response.messages[0]
            # Безопасное обращение к полю, так как модель прошла валидацию
            if last_message.author.role != 'SELLER':
                return True
        except Exception as e:
            print(f"  Не удалось проверить сообщения для диалога {thread_id}: {e}")
            return False
        return False

    async def _log_conversation_as_processed(self, thread_id: str, account_id: int):
        # Этот метод не делает commit, чтобы обеспечить транзакционность
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)

    async def cleanup_old_logs(self):
        # ... (код без изменений)
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
        # ... (код без изменений)
        try:
            retention_period_days = 90
            ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=retention_period_days)
            stmt = delete(MessageMetadata).where(MessageMetadata.sent_at < ninety_days_ago)
            result = await self.db.execute(stmt)
            await self.db.commit()
            print(f"--- Очистка метаданных сообщений завершена. Удалено {result.rowcount} старых записей. ---")
        except Exception as e:
            print(f"ОШИБКА во время очистки метаданных сообщений: {e}")
            await self.db.rollback()