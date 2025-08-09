-- Создаем таблицу для очереди задач
CREATE TABLE public.task_queue
(
    id                 SERIAL PRIMARY KEY,
    allegro_account_id INT UNIQUE NOT NULL,
    status             VARCHAR(20) DEFAULT 'pending',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    processed_at       TIMESTAMPTZ,

    -- Создаем внешний ключ для связи с таблицей аккаунтов
    CONSTRAINT fk_allegro_account
        FOREIGN KEY(allegro_account_id)
        REFERENCES public.allegro_accounts(id)
        ON DELETE CASCADE
);

-- Создаем индекс для быстрого поиска ожидающих задач
CREATE INDEX idx_task_queue_pending ON public.task_queue (status, created_at);

-- Добавляем комментарии для ясности (опционально, но полезно)
COMMENT ON TABLE public.task_queue IS 'Очередь задач для обработки аккаунтов Allegro воркером';
COMMENT ON COLUMN public.task_queue.status IS 'Статус задачи: pending, processing, done, failed';