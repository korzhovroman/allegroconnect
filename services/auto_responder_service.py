# services/auto_responder_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.models import AllegroAccount
from services.allegro_client import AllegroClient
from utils.security import decrypt_data
from models.models import AutoReplyLog


class AutoResponderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_auto_responder(self):
        print("--- Запуск автоответчика ---")

        all_accounts = await self.get_active_auto_reply_accounts()

        for account in all_accounts:
            print(f"Проверяем аккаунт: {account.allegro_login} (ID: {account.id})")
            try:
                access_token = decrypt_data(account.access_token)
                client = AllegroClient(access_token)
                threads_data = await client.get_threads(limit=50)

                for thread in threads_data.get('threads', []):
                    if await self.should_reply(client, thread, account.id):
                        print(f"  -> Отправляем автоответ в диалог {thread['id']}")

                        # Используем персональный текст ответа
                        reply_text = account.auto_reply_text
                        await client.post_thread_message(thread['id'], reply_text)
                        await self.log_reply(thread['id'], account.id)

            except Exception as e:
                print(f"  ОШИБКА при обработке аккаунта {account.allegro_login}: {e}")

        print("--- Автоответчик завершил работу ---")

    async def get_active_auto_reply_accounts(self) -> list[AllegroAccount]:
        """Возвращает аккаунты с включенным автоответчиком и текстом."""
        query = select(AllegroAccount).where(
            AllegroAccount.auto_reply_enabled == True,
            AllegroAccount.auto_reply_text != None
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def should_reply(self, client: AllegroClient, thread: dict, account_id: int) -> bool:
        """Проверяет, нужно ли отвечать на сообщение."""
        thread_id = thread['id']

        # 1. Проверяем, не отвечали ли мы уже
        log_entry = await self.db.execute(select(AutoReplyLog).where(
            AutoReplyLog.conversation_id == thread_id,
            AutoReplyLog.allegro_account_id == account_id
        ))
        if log_entry.scalar_one_or_none():
            return False

        # 2. УМНАЯ ПРОВЕРКА: Получаем последнее сообщение и проверяем автора
        try:
            messages_data = await client.get_thread_messages(thread_id, limit=1)
            last_message = messages_data.get('messages', [{}])[0]

            # Если последнее сообщение от ПРОДАВЦА (SELLER), то не отвечаем
            if last_message.get('author', {}).get('role') == 'SELLER':
                return False
        except Exception:
            # Если не удалось получить сообщения, пропускаем, чтобы не рисковать
            return False

        return True

    async def log_reply(self, thread_id: str, account_id: int):
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)
        await self.db.commit()