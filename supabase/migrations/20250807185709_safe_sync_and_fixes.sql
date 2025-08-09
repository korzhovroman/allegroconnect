-- Безопасное добавление недостающих колонок в таблицу "users"
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS supabase_user_id VARCHAR,
ADD COLUMN IF NOT EXISTS subscription_status VARCHAR NOT NULL DEFAULT 'free',
ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS fcm_token VARCHAR;

-- Безопасное создание индекса
CREATE INDEX IF NOT EXISTS ix_users_supabase_user_id ON public.users (supabase_user_id);

-- Безопасное изменение колонки reply_time в "auto_reply_log"
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'auto_reply_log' AND column_name = 'reply_time'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'auto_reply_log'
            AND column_name = 'reply_time'
            AND data_type = 'timestamp with time zone'
        ) THEN
            ALTER TABLE public.auto_reply_log ALTER COLUMN reply_time TYPE TIMESTAMPTZ USING reply_time AT TIME ZONE 'UTC';
        END IF;
    END IF;
END
$$;

-- Устанавливаем значение по умолчанию для reply_time
ALTER TABLE public.auto_reply_log ALTER COLUMN reply_time SET DEFAULT now();