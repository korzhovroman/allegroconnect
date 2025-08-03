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

        account_ids = await self.get_active_account_ids()

        for account_id in account_ids:
            account = await self.db.get(AllegroAccount, account_id)
            if not account:
                continue

            print(f"Проверяем аккаунт: {account.allegro_login} (ID: {account.id})")

            reply_text = account.auto_reply_text
            if not reply_text or not reply_text.strip():
                print(f"  -> Пропускаем аккаунт {account.allegro_login}, так как текст автоответа пуст.")
                continue

            try:
                access_token = decrypt_data(account.access_token)
                client = AllegroClient(access_token)
                threads_data = await client.get_threads(limit=20)

                for thread in threads_data.get('threads', []):
                    if await self.should_reply(client, thread, account.id):
                        # =======================================================
                        # ===         ФИНАЛЬНАЯ ОТЛАДОЧНАЯ ПРОВЕРКА           ===
                        # =======================================================
                        print(f"  -> ГОТОВИМСЯ К ОТПРАВКЕ. Текст сообщения: '{reply_text}'")
                        # =======================================================

                        print(f"  -> Отправляем автоответ в диалог {thread['id']}")
                        await client.post_thread_message(thread['id'], reply_text)
                        await self.log_reply(thread['id'], account.id)
                        print(f"  -> Успешно отправлено и залогировано для диалога {thread['id']}")


            except Exception as e:
                print(f"  ОШИБКА при обработке аккаунта {account.allegro_login}: {e}")

        print("--- Автоответчик завершил работу ---")

    async def get_active_account_ids(self) -> list[int]:
        """Возвращает ID аккаунтов с включенным автоответчиком."""
        query = select(AllegroAccount.id).where(
            AllegroAccount.auto_reply_enabled == True
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def should_reply(self, client: AllegroClient, thread: dict, account_id: int) -> bool:
        """Проверяет, нужно ли отвечать на сообщение."""
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
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)
        await self.db.commit()