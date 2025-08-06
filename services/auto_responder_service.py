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

    async def run_auto_responder(self):
        """
        Проверяет САМЫЕ НОВЫЕ непрочитанные диалоги, отправляет уведомления
        и, если включено, автоответы.
        """
        print("--- Запуск сервиса обработки сообщений ---")

        all_accounts_data = await self.get_all_accounts_data()

        for account_data in all_accounts_data:
            account_id = account_data["id"]
            account_login = account_data["login"]
            fcm_token = account_data["fcm_token"]
            auto_reply_enabled = account_data["auto_reply_enabled"]
            reply_text = account_data["reply_text"]

            print(f"Проверяем аккаунт: {account_login} (ID: {account_id})")

            try:
                access_token = decrypt_data(account_data["access_token"])
                client = AllegroClient(access_token)

                # --- ИЗМЕНЕНИЕ: УБИРАЕМ ПАГИНАЦИЮ. ЗАПРАШИВАЕМ ТОЛЬКО ПЕРВУЮ СТРАНИЦУ ---
                print("  -> Запрашиваем только первую страницу диалогов (самые новые).")
                threads_data = await client.get_threads(limit=20, offset=0)
                threads = threads_data.get('threads', [])

                for thread in threads:
                    # Проверяем, является ли диалог непрочитанным и не обработанным нами ранее
                    if not thread.get('read', True) and await self._is_new_message_from_buyer(client, thread,
                                                                                              account_id):
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

        print("--- Сервис обработки сообщений завершил работу ---")

    async def _is_new_message_from_buyer(self, client: AllegroClient, thread: dict, account_id: int) -> bool:
        """
        Проверяет, не обработан ли диалог нами ранее И является ли последнее сообщение от покупателя.
        """
        thread_id = thread['id']
        # 1. Проверяем, не обработали ли мы его на предыдущих запусках
        log_entry = await self.db.execute(select(AutoReplyLog).where(
            AutoReplyLog.conversation_id == thread_id,
            AutoReplyLog.allegro_account_id == account_id
        ))
        if log_entry.scalar_one_or_none():
            return False  # Уже обработан

        # 2. Проверяем, кто автор последнего сообщения (на всякий случай, если read-флаг запаздывает)
        try:
            messages_data = await client.get_thread_messages(thread_id, limit=1)
            if not messages_data.get('messages'):
                return False
            last_message = messages_data['messages'][0]
            # Если автор НЕ продавец, значит, сообщение от покупателя
            if last_message.get('author', {}).get('role') != 'SELLER':
                return True
        except Exception:
            return False

        return False

    # ... (остальные методы без изменений) ...
    async def get_all_accounts_data(self) -> list[dict]:
        query = select(
            AllegroAccount.id,
            AllegroAccount.allegro_login,
            AllegroAccount.auto_reply_enabled,
            AllegroAccount.auto_reply_text,
            AllegroAccount.access_token,
            User.fcm_token
        ).join(User, AllegroAccount.owner_id == User.id)
        result = await self.db.execute(query)
        return [{"id": row.id, "login": row.allegro_login, "auto_reply_enabled": row.auto_reply_enabled,
                 "reply_text": row.auto_reply_text, "access_token": row.access_token, "fcm_token": row.fcm_token} for
                row in result.all()]

    async def _log_conversation_as_processed(self, thread_id: str, account_id: int):
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)
        await self.db.commit()

    async def cleanup_old_logs(self):
        """Удаляет записи из лога автоответчика старше 30 дней."""
        try:
            # Определяем дату, раньше которой нужно удалить записи
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

            # Создаем и выполняем запрос на удаление
            stmt = delete(AutoReplyLog).where(AutoReplyLog.reply_time < thirty_days_ago)
            result = await self.db.execute(stmt)
            await self.db.commit()

            # result.rowcount содержит количество удаленных строк
            print(f"--- Очистка логов завершена. Удалено {result.rowcount} старых записей. ---")
        except Exception as e:
            print(f"ОШИБКА во время очистки логов: {e}")
            await self.db.rollback()  # Откатываем транзакцию в случае ошибки