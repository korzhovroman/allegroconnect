# services/auto_responder_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError
from models.models import AllegroAccount, AutoReplyLog, User, MessageMetadata
from services.allegro_client import AllegroClient
from services.notification_service import send_notification
from schemas.allegro_api import ThreadsResponse, MessagesResponse, AllegroThread
from utils.logger import logger

class AutoResponderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_single_account(self, account_id: int):
        query = select(AllegroAccount).join(User, AllegroAccount.owner_id == User.id).where(
            AllegroAccount.id == account_id).with_for_update()

        allegro_account = (await self.db.execute(query)).scalar_one_or_none()

        if not allegro_account:
            logger.warning(f"Аккаунт с ID {account_id} не найден во время обработки задачи.", account_id=account_id)
            return

        client = AllegroClient(db=self.db, allegro_account=allegro_account)
        account_login = allegro_account.allegro_login
        fcm_token = allegro_account.owner.fcm_token
        auto_reply_enabled = allegro_account.auto_reply_enabled
        reply_text = allegro_account.auto_reply_text

        logger.info(f"Обрабатываем аккаунт: {account_login}", account_id=account_id)

        try:
            raw_threads_data = await client.get_threads(limit=20, offset=0)
            try:
                threads_response = ThreadsResponse.model_validate(raw_threads_data)
            except ValidationError as e:
                logger.error(f"Ошибка валидации ответа Allegro (threads)", details=str(e), account_id=account_id)
                return

            for thread in threads_response.threads:
                if not thread.read and await self._is_new_message_from_buyer(client, thread, account_id):
                    logger.info(f"Обнаружен новый непрочитанный диалог", thread_id=thread.id)
                    if fcm_token:
                        try:
                            interlocutor = thread.interlocutor.login if thread.interlocutor else 'Kupujący'
                            title = f"Nowa wiadomość od {interlocutor}"
                            body = f"Konto: {account_login}. Kliknij, aby odpowiedzieć."
                            send_notification(token=fcm_token, title=title, body=body)
                        except Exception as e:
                            logger.error(f"Ошибка при отправке PUSH-уведомления", details=str(e))
                    if auto_reply_enabled and reply_text:
                        logger.info(f"Автоответчик включен. Отправляем ответ.", thread_id=thread.id)
                        await client.post_thread_message(thread.id, reply_text)
                    await self._log_conversation_as_processed(thread.id, account_id)
                    logger.info(f"Диалог помечен как обработанный.", thread_id=thread.id)
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке аккаунта {account_login}", details=str(e), exc_info=True)
            raise e

    async def _is_new_message_from_buyer(self, client: AllegroClient, thread: AllegroThread, account_id: int) -> bool:
        thread_id = thread.id
        log_entry = await self.db.execute(select(AutoReplyLog).where(AutoReplyLog.conversation_id == thread_id,
                                                                     AutoReplyLog.allegro_account_id == account_id))
        if log_entry.scalar_one_or_none():
            return False
        try:
            raw_messages_data = await client.get_thread_messages(thread_id, limit=1)
            try:
                messages_response = MessagesResponse.model_validate(raw_messages_data)
            except ValidationError as e:
                logger.error("Ошибка валидации ответа Allegro (messages)", thread_id=thread_id, details=str(e))
                return False

            if not messages_response.messages:
                return False

            last_message = messages_response.messages[0]
            if last_message.author.role != 'SELLER':
                return True
        except Exception as e:
            logger.error("Не удалось проверить сообщения для диалога", thread_id=thread_id, details=str(e))
            return False
        return False

    async def _log_conversation_as_processed(self, thread_id: str, account_id: int):
        new_log = AutoReplyLog(conversation_id=thread_id, allegro_account_id=account_id)
        self.db.add(new_log)

    async def cleanup_old_logs(self):
        try:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            stmt = delete(AutoReplyLog).where(AutoReplyLog.reply_time < thirty_days_ago)
            result = await self.db.execute(stmt)
            await self.db.commit()
            logger.info("Очистка логов автоответчика завершена", deleted_rows=result.rowcount)
        except Exception as e:
            logger.error("ОШИБКА во время очистки логов автоответчика:", details=str(e))
            await self.db.rollback()

    async def cleanup_old_message_metadata(self):
        try:
            retention_period_days = 90
            ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=retention_period_days)
            stmt = delete(MessageMetadata).where(MessageMetadata.sent_at < ninety_days_ago)
            result = await self.db.execute(stmt)
            await self.db.commit()
            logger.info("Очистка метаданных сообщений завершена", deleted_rows=result.rowcount)
        except Exception as e:
            logger.error("ОШИБКА во время очистки метаданных сообщений", details=str(e))
            await self.db.rollback()