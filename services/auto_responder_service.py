# services/auto_responder_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.models import AllegroAccount, AutoReplyLog
from services.allegro_client import AllegroClient
from utils.security import decrypt_data


class AutoResponderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_auto_responder(self):
        print("--- Запуск автоответчика ---")

        # Получаем все необходимые данные заранее
        active_accounts_data = await self.get_active_accounts_data()

        for account_data in active_accounts_data:
            account_id = account_data["id"]
            account_login = account_data["login"]
            reply_text = account_data["reply_text"]

            print(f"Проверяем аккаунт: {account_login} (ID: {account_id})")

            try:
                access_token = decrypt_data(account_data["access_token"])
                client = AllegroClient(access_token)
                threads_data = await client.get_threads(limit=20)

                for thread in threads_data.get('threads', []):
                    # Теперь передаем только ID, а не весь объект
                    if await self.should_reply(client, thread, account_id):
                        print(f"  -> Отправляем автоответ в диалог {thread['id']}")
                        await client.post_thread_message(thread['id'], reply_text)
                        await self.log_reply(thread['id'], account_id)
                        print(f"  -> Успешно отправлено и залогировано для диалога {thread['id']}")

            except Exception as e:
                # Используем заранее сохраненный логин
                print(f"  ОШИБКА при обработке аккаунта {account_login}: {e}")

        print("--- Автоответчик завершил работу ---")

    async def get_active_accounts_data(self) -> list[dict]:
        """
        Возвращает список словарей с данными аккаунтов,
        а не объекты SQLAlchemy.
        """
        query = select(
            AllegroAccount.id,
            AllegroAccount.allegro_login,
            AllegroAccount.auto_reply_text,
            AllegroAccount.access_token
        ).where(
            AllegroAccount.auto_reply_enabled == True,
            AllegroAccount.auto_reply_text.isnot(None)
        )
        result = await self.db.execute(query)

        # Преобразуем результат в список словарей
        return [
            {
                "id": row.id,
                "login": row.allegro_login,
                "reply_text": row.auto_reply_text,
                "access_token": row.access_token
            }
            for row in result.all()
        ]

    async def should_reply(self, client: AllegroClient, thread: dict, account_id: int) -> bool:
        # Этот метод остается без изменений
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
            if last_message.get('author', {}).get('role') == 'SELLER':
                return False
        except Exception:
            return False
        return True

    async def log_reply(self, thread_id: str, account_id: int):
        # Этот метод остается без изменений
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)
        await self.db.commit()