-- Добавляем столбец для имени пользователя, если его нет
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS name VARCHAR;

-- Создаем таблицу Команд
CREATE TABLE public.teams (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL DEFAULT 'Моя команда',
    owner_id INT NOT NULL UNIQUE,
    CONSTRAINT fk_owner
        FOREIGN KEY(owner_id)
        REFERENCES public.users(id)
        ON DELETE CASCADE
);
COMMENT ON TABLE public.teams IS 'Команды, созданные пользователями-владельцами';

-- Создаем таблицу Участников команд
CREATE TABLE public.team_members (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    team_id INT NOT NULL,
    role VARCHAR NOT NULL DEFAULT 'employee',
    CONSTRAINT fk_user
        FOREIGN KEY(user_id)
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_team
        FOREIGN KEY(team_id)
        REFERENCES public.teams(id)
        ON DELETE CASCADE
);
COMMENT ON TABLE public.team_members IS 'Связь между пользователями и командами';
CREATE INDEX idx_teammembers_user_id ON public.team_members (user_id);
CREATE INDEX idx_teammembers_team_id ON public.team_members (team_id);

-- Создаем таблицу Прав доступа для сотрудников
CREATE TABLE public.employee_permissions (
    id SERIAL PRIMARY KEY,
    member_id INT NOT NULL,
    allegro_account_id INT NOT NULL,
    CONSTRAINT fk_member
        FOREIGN KEY(member_id)
        REFERENCES public.team_members(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_allegro_account
        FOREIGN KEY(allegro_account_id)
        REFERENCES public.allegro_accounts(id)
        ON DELETE CASCADE
);
COMMENT ON TABLE public.employee_permissions IS 'Права доступа сотрудников к аккаунтам Allegro';
CREATE INDEX idx_employeepermissions_member_id ON public.employee_permissions (member_id);
CREATE INDEX idx_employeepermissions_allegro_account_id ON public.employee_permissions (allegro_account_id);

-- Создаем таблицу Метаданных сообщений
CREATE TABLE public.message_metadata (
    id SERIAL PRIMARY KEY,
    allegro_message_id VARCHAR UNIQUE NOT NULL,
    thread_id VARCHAR NOT NULL,
    sent_by_user_id INT,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT fk_sender
        FOREIGN KEY(sent_by_user_id)
        REFERENCES public.users(id)
        ON DELETE SET NULL
);
COMMENT ON TABLE public.message_metadata IS 'Информация об отправителях сообщений';
CREATE INDEX idx_messagemetadata_allegro_message_id ON public.message_metadata (allegro_message_id);
CREATE INDEX idx_messagemetadata_thread_id ON public.message_metadata (thread_id);