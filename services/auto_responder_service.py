# services/auto_responder_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Импортируем все нужные модели и сервисы
from models.models import AllegroAccount, AutoReplyLog, User
from services.allegro_client import AllegroClient
from services.notification_service import send_notification
from utils.security import decrypt_data


class AutoResponderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_auto_responder(self):
        """
        Проверяет все аккаунты, отправляет уведомления о новых сообщениях
        и, если включено, отправляет автоответы.
        """
        print("--- Запуск сервиса обработки сообщений ---")

        # 1. Получаем ВСЕ аккаунты с данными их владельцев
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
                threads_data = await client.get_threads(limit=20)

                for thread in threads_data.get('threads', []):
                    # Проверяем, есть ли в диалоге новое сообщение от покупателя, которое мы еще не обработали
                    if await self._is_new_message_from_buyer(client, thread, account_id):

                        # --- ШАГ 1: Всегда отправляем уведомление ---
                        if fcm_token:
                            print(f"  -> Обнаружено новое сообщение в диалоге {thread['id']}. Отправляем PUSH.")
                            try:
                                interlocutor = thread.get('interlocutor', {}).get('login', 'Покупатель')
                                title = f"Новое сообщение от {interlocutor}"
                                body = f"Аккаунт: {account_login}. Нажмите, чтобы ответить."
                                send_notification(token=fcm_token, title=title, body=body)
                            except Exception as e:
                                print(f"  ОШИБКА при отправке PUSH: {e}")

                        # --- ШАГ 2: Отправляем автоответ, только если он включен ---
                        if auto_reply_enabled and reply_text:
                            print(f"  -> Автоответчик включен. Отправляем ответ в диалог {thread['id']}.")
                            await client.post_thread_message(thread['id'], reply_text)

                        # --- ШАГ 3: Логируем, что диалог обработан ---
                        await self._log_conversation_as_processed(thread['id'], account_id)
                        print(f"  -> Диалог {thread['id']} помечен как обработанный.")

            except Exception as e:
                print(f"  ОШИБКА при обработке аккаунта {account_login}: {e}")

        print("--- Сервис обработки сообщений завершил работу ---")

    async def get_all_accounts_data(self) -> list[dict]:
        """
        Возвращает список ВСЕХ аккаунтов с данными для автоответчика и уведомлений.
        """
        # Убираем фильтр по auto_reply_enabled, чтобы получать все аккаунты
        query = select(
            AllegroAccount.id,
            AllegroAccount.allegro_login,
            AllegroAccount.auto_reply_enabled,  # <-- Нам все еще нужно это поле
            AllegroAccount.auto_reply_text,
            AllegroAccount.access_token,
            User.fcm_token
        ).join(User, AllegroAccount.owner_id == User.id)  # <-- JOIN остается

        result = await self.db.execute(query)

        return [
            {
                "id": row.id,
                "login": row.allegro_login,
                "auto_reply_enabled": row.auto_reply_enabled,
                "reply_text": row.auto_reply_text,
                "access_token": row.access_token,
                "fcm_token": row.fcm_token
            }
            for row in result.all()
        ]

    async def _is_new_message_from_buyer(self, client: AllegroClient, thread: dict, account_id: int) -> bool:
        """
        Проверяет, является ли последнее сообщение в диалоге новым сообщением от покупателя.
        """
        thread_id = thread['id']
        # Проверяем, не обрабатывали ли мы этот диалог ранее
        log_entry = await self.db.execute(select(AutoReplyLog).where(
            AutoReplyLog.conversation_id == thread_id,
            AutoReplyLog.allegro_account_id == account_id
        ))
        if log_entry.scalar_one_or_none():
            return False  # Уже обработано

        # Проверяем, кто автор последнего сообщения
        try:
            # Если диалог не прочитан на стороне Allegro (read=false), этого может быть достаточно
            if not thread.get('read', True):
                messages_data = await client.get_thread_messages(thread_id, limit=1)
                if not messages_data.get('messages'):
                    return False
                last_message = messages_data['messages'][0]
                # Если автор - не продавец (т.е. покупатель), возвращаем True
                if last_message.get('author', {}).get('role') != 'SELLER':
                    return True
        except Exception:
            return False

        return False

    async def _log_conversation_as_processed(self, thread_id: str, account_id: int):
        """
        Добавляет запись в лог, чтобы пометить диалог как обработанный.
        """
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)
        await self.db.commit()