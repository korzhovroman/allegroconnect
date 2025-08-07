# worker.py
import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select
from config import settings
from services.auto_responder_service import AutoResponderService

# Настройка логирования для воркера
logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Подключение к БД (аналогично main.py)
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)


async def process_single_task(task_id: int, account_id: int):
    """
    Обрабатывает ОДНУ задачу: проверяет один аккаунт Allegro.
    """
    db_session = AsyncSessionLocal()
    service = AutoResponderService(db=db_session)
    try:
        logger.info(f"Начинаем обработку задачи #{task_id} для аккаунта #{account_id}")

        # --- Вызываем НОВЫЙ метод из сервиса, который работает с одним аккаунтом ---
        # Этот метод нам нужно будет создать в auto_responder_service.py
        await service.process_single_account(account_id)

        # Помечаем задачу как выполненную
        await db_session.execute(
            text("UPDATE task_queue SET status = 'done', processed_at = NOW() WHERE id = :id"),
            {"id": task_id}
        )
        await db_session.commit()
        logger.info(f"Задача #{task_id} успешно завершена.")

    except Exception as e:
        logger.error(f"ОШИБКА при обработке задачи #{task_id}: {e}", exc_info=True)
        # Помечаем задачу как проваленную, чтобы не пытаться ее выполнить снова
        await db_session.execute(
            text("UPDATE task_queue SET status = 'failed', processed_at = NOW() WHERE id = :id"),
            {"id": task_id}
        )
        await db_session.commit()
    finally:
        await db_session.close()


async def main_loop():
    """
    Бесконечный цикл воркера.
    """
    logger.info("Воркер запущен и готов к работе.")
    while True:
        db = AsyncSessionLocal()
        try:
            # Ищем одну задачу в статусе 'pending'
            # FOR UPDATE SKIP LOCKED - магия, которая позволяет нескольким воркерам не хватать одну и ту же задачу
            stmt = text("""
                        SELECT id, allegro_account_id
                        FROM task_queue
                        WHERE status = 'pending'
                        ORDER BY created_at LIMIT 1
                FOR
                        UPDATE SKIP LOCKED;
                        """)
            result = await db.execute(stmt)
            task = result.fetchone()

            if task:
                task_id, account_id = task

                # Помечаем, что задача взята в работу
                await db.execute(
                    text("UPDATE task_queue SET status = 'processing' WHERE id = :id"),
                    {"id": task_id}
                )
                await db.commit()

                # Запускаем обработку
                await process_single_task(task_id, account_id)
            else:
                # Если задач нет, ждем 10 секунд
                await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле воркера: {e}", exc_info=True)
            await asyncio.sleep(15)  # Ждем дольше в случае серьезной ошибки
        finally:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main_loop())