# worker.py
import asyncio
import logging
import signal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from config import settings
from services.auto_responder_service import AutoResponderService

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Подключение к БД
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

# --- НОВЫЙ КОД: СОЗДАЕМ СОБЫТИЕ ДЛЯ ОСТАНОВКИ ---
shutdown_event = asyncio.Event()

def handle_shutdown_signal(sig, frame):
    """Обработчик сигналов, который устанавливает событие."""
    logger.info(f"Получен сигнал {sig}. Инициирую вежливое завершение...")
    shutdown_event.set()


async def process_single_task(task_id: int, account_id: int):
    """
    Обрабатывает ОДНУ задачу. (Этот код без изменений)
    """
    db_session = AsyncSessionLocal()
    service = AutoResponderService(db=db_session)
    try:
        logger.info(f"Начинаем обработку задачи #{task_id} для аккаунта #{account_id}")
        await service.process_single_account(account_id)
        await db_session.execute(
            text("UPDATE task_queue SET status = 'done', processed_at = NOW() WHERE id = :id"),
            {"id": task_id}
        )
        await db_session.commit()
        logger.info(f"Задача #{task_id} успешно завершена.")
    except Exception as e:
        logger.error(f"ОШИБКА при обработке задачи #{task_id}: {e}", exc_info=True)
        await db_session.execute(
            text("UPDATE task_queue SET status = 'failed', processed_at = NOW() WHERE id = :id"),
            {"id": task_id}
        )
        await db_session.commit()
    finally:
        await db_session.close()


async def get_next_task(db: AsyncSession):
    """Атомарно получает и блокирует следующую задачу для обработки"""
    stmt = text("""
        UPDATE task_queue 
        SET status = 'processing', processed_at = NOW()
        WHERE id = (
            SELECT id FROM task_queue 
            WHERE status = 'pending' 
            ORDER BY created_at 
            LIMIT 1 
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, allegro_account_id;
    """)
    result = await db.execute(stmt)
    return result.fetchone()


async def main_loop():
    """Основной цикл воркера с исправленной обработкой задач"""
    logger.info("Воркер запущен и готов к работе.")

    while not shutdown_event.is_set():
        db = AsyncSessionLocal()
        try:
            # Атомарно получаем следующую задачу
            task = await get_next_task(db)
            await db.commit()  # Коммитим блокировку задачи

            if task:
                task_id, account_id = task
                logger.info(f"Взял в обработку задачу #{task_id} для аккаунта #{account_id}")

                # Обрабатываем задачу
                await process_single_task(task_id, account_id)
            else:
                # Если задач нет, ждем
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass

        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле воркера: {e}", exc_info=True)
            await asyncio.sleep(15)
        finally:
            await db.close()

    logger.info("Воркер завершает работу.")


if __name__ == "__main__":
    # --- НОВЫЙ КОД: УСТАНАВЛИВАЕМ ОБРАБОТЧИКИ СИГНАЛОВ ---
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    asyncio.run(main_loop())