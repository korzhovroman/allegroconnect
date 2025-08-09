# worker.py
import asyncio
import logging
import signal
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from config import settings
from services.auto_responder_service import AutoResponderService

print(f"WORKER SEES DATABASE_URL: {os.getenv('DATABASE_URL')}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={"statement_cache_size": 0}  # <--- И ДОБАВЬТЕ ЭТУ СТРОКУ ЗДЕСЬ
)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

shutdown_event = asyncio.Event()

def handle_shutdown_signal(sig, frame):
    logger.info(f"Получен сигнал {sig}. Инициирую вежливое завершение...")
    shutdown_event.set()

async def get_next_task(db: AsyncSession):
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
    logger.info("Воркер запущен и готов к работе.")

    while not shutdown_event.is_set():
        async with AsyncSessionLocal() as db:
            async with db.begin():
                try:
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
                    task = result.fetchone()

                    if task:
                        task_id, account_id = task
                        logger.info(f"Взял в обработку задачу #{task_id}", task_id=task_id, account_id=account_id)

                        service = AutoResponderService(db=db)
                        await service.process_single_account(account_id)

                        await db.execute(
                            text("UPDATE task_queue SET status = 'done' WHERE id = :id"),
                            {"id": task_id}
                        )
                        logger.info(f"Задача #{task_id} успешно завершена.", task_id=task_id)

                    else:
                        pass

                except Exception as e:
                    logger.error(f"Критическая ошибка при обработке задачи. Откатываем транзакцию.", error=str(e), exc_info=True)
                    if 'task_id' in locals():
                        await db.execute(
                            text("UPDATE task_queue SET status = 'failed' WHERE id = :id"),
                            {"id": task_id}
                        )
                    await asyncio.sleep(5)

        if not 'task' in locals() or not task:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass

    logger.info("Воркер завершает работу.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    asyncio.run(main_loop())