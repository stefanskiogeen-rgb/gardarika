-- =============================================================================
-- SQL-скрипт создания базы данных
-- Информационная система конноспортивного клуба «Гардарика»
-- Курсовой проект, специальность 09.02.07
-- СУБД: PostgreSQL 15
-- =============================================================================

-- Создание базы данных и пользователя (выполняется суперпользователем postgres):
-- CREATE USER gardarika WITH PASSWORD 'SP129sGZFHNC';
-- CREATE DATABASE gardarika_db OWNER gardarika ENCODING 'UTF8';
-- \c gardarika_db
-- GRANT ALL PRIVILEGES ON SCHEMA public TO gardarika;

-- -----------------------------------------------------------------------------
-- 1. Удаление существующих объектов (для повторного запуска скрипта)
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS workout_participants CASCADE;
DROP TABLE IF EXISTS workouts             CASCADE;
DROP TABLE IF EXISTS riders               CASCADE;
DROP TABLE IF EXISTS horses               CASCADE;
DROP TABLE IF EXISTS breeds               CASCADE;
DROP TABLE IF EXISTS trainers             CASCADE;
DROP TABLE IF EXISTS specializations      CASCADE;
DROP TABLE IF EXISTS services             CASCADE;
DROP TABLE IF EXISTS users                CASCADE;
DROP TABLE IF EXISTS roles                CASCADE;

DROP VIEW IF EXISTS v_workouts_full;
DROP VIEW IF EXISTS v_riders_balance;

-- -----------------------------------------------------------------------------
-- 2. Создание таблиц
-- -----------------------------------------------------------------------------

-- Справочник ролей пользователей
CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    role_name   VARCHAR(50) UNIQUE NOT NULL
);

COMMENT ON TABLE  roles            IS 'Роли пользователей системы';
COMMENT ON COLUMN roles.role_name  IS 'Наименование роли (SuperAdmin, Admin, Trainer, Rider)';

-- Учётные записи пользователей (демографические поля живут здесь;
-- в trainers/riders они НЕ дублируются — доступ идёт через FK iduser).
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(100) UNIQUE NOT NULL,
    password    VARCHAR(255) NOT NULL,
    email       VARCHAR(120) UNIQUE,
    first_name  VARCHAR(100),
    last_name   VARCHAR(100),
    name        VARCHAR(100),
    lastname    VARCHAR(100),
    phone       VARCHAR(50),
    is_approved BOOLEAN NOT NULL DEFAULT TRUE,
    idrole      INTEGER REFERENCES roles(id) ON DELETE SET NULL
);

COMMENT ON TABLE  users             IS 'Учётные записи пользователей информационной системы';
COMMENT ON COLUMN users.password    IS 'Хеш пароля (PBKDF2-SHA256)';
COMMENT ON COLUMN users.name        IS 'Имя (используется в карточках Тренер/Всадник через iduser)';
COMMENT ON COLUMN users.lastname    IS 'Фамилия (используется в карточках Тренер/Всадник через iduser)';
COMMENT ON COLUMN users.phone       IS 'Телефон для связи';
COMMENT ON COLUMN users.is_approved IS 'Тренеры — FALSE до одобрения админом; всадники — всегда TRUE';

-- Справочник специализаций тренеров
CREATE TABLE specializations (
    id                   SERIAL PRIMARY KEY,
    specialization_name  TEXT NOT NULL
);

COMMENT ON TABLE specializations IS 'Специализации тренеров (выездка, конкур, иппотерапия и т. п.)';

-- Тренеры (имя/фамилия/телефон тренера лежат в users — берутся через iduser).
CREATE TABLE trainers (
    id                SERIAL PRIMARY KEY,
    photo             VARCHAR(255),
    iduser            INTEGER REFERENCES users(id)            ON DELETE SET NULL,
    idspecialization  INTEGER REFERENCES specializations(id)  ON DELETE SET NULL
);

COMMENT ON TABLE  trainers        IS 'Тренеры конноспортивного клуба';
COMMENT ON COLUMN trainers.iduser IS 'FK на users — оттуда берутся ФИО и телефон';

-- Справочник пород лошадей
CREATE TABLE breeds (
    id          SERIAL PRIMARY KEY,
    breed_name  TEXT NOT NULL
);

COMMENT ON TABLE breeds IS 'Породы лошадей';

-- Лошади
CREATE TABLE horses (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    status      VARCHAR(100),
    birth_year  INTEGER,
    color       VARCHAR(100),
    gender      VARCHAR(50),
    notes       TEXT,
    photo       VARCHAR(255),
    idbreed     INTEGER REFERENCES breeds(id) ON DELETE SET NULL,
    CONSTRAINT  ck_horses_birth_year CHECK (birth_year IS NULL OR birth_year BETWEEN 1950 AND 2100)
);

COMMENT ON TABLE horses IS 'Поголовье лошадей конноспортивного клуба';

-- Наездники (клиенты клуба) — ФИО/телефон хранятся в users.
CREATE TABLE riders (
    id                    SERIAL PRIMARY KEY,
    datebirth             DATE,
    subscription_status   VARCHAR(255),
    subscription_balance  INTEGER DEFAULT 0,
    rental_balance        INTEGER DEFAULT 0,
    notes                 TEXT,
    photo                 VARCHAR(255),
    iduser                INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT ck_riders_subscription_nonneg CHECK (subscription_balance >= 0),
    CONSTRAINT ck_riders_rental_nonneg       CHECK (rental_balance       >= 0)
);

COMMENT ON TABLE  riders        IS 'Наездники — клиенты конноспортивного клуба';
COMMENT ON COLUMN riders.iduser IS 'FK на users — оттуда берутся ФИО и телефон';

-- Услуги
CREATE TABLE services (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    duration    INTEGER,
    price       INTEGER,
    type        VARCHAR(100),
    "limit"     INTEGER,
    notes       TEXT,
    CONSTRAINT  ck_services_price_nonneg CHECK (price IS NULL OR price >= 0)
);

COMMENT ON TABLE services IS 'Услуги конноспортивного клуба (тренировки, прокат)';

-- Тренировки
CREATE TABLE workouts (
    id              SERIAL PRIMARY KEY,
    datetime_start  TIMESTAMP NOT NULL,
    idtrainer       INTEGER REFERENCES trainers(id) ON DELETE SET NULL,
    idservice       INTEGER REFERENCES services(id) ON DELETE SET NULL,
    status          TEXT,
    notes           TEXT
);

COMMENT ON TABLE  workouts            IS 'Расписание тренировок';
COMMENT ON COLUMN workouts.status     IS 'Статус: planned / done / cancelled';

-- Участники тренировок (связующая таблица)
CREATE TABLE workout_participants (
    id          SERIAL PRIMARY KEY,
    idworkout   INTEGER REFERENCES workouts(id) ON DELETE CASCADE,
    idrider     INTEGER REFERENCES riders(id)   ON DELETE SET NULL,
    idhorse     INTEGER REFERENCES horses(id)   ON DELETE SET NULL,
    guest_name  VARCHAR(100)
);

COMMENT ON TABLE workout_participants IS 'Участники тренировок (наездник + лошадь)';

-- -----------------------------------------------------------------------------
-- 3. Индексы для типовых выборок
-- -----------------------------------------------------------------------------

CREATE INDEX idx_workouts_dt          ON workouts(datetime_start);
CREATE INDEX idx_workouts_trainer     ON workouts(idtrainer);
CREATE INDEX idx_wp_workout           ON workout_participants(idworkout);
CREATE INDEX idx_wp_rider             ON workout_participants(idrider);
CREATE INDEX idx_horses_breed         ON horses(idbreed);
CREATE INDEX idx_trainers_user        ON trainers(iduser);
CREATE INDEX idx_riders_user          ON riders(iduser);

-- -----------------------------------------------------------------------------
-- 4. Представления (VIEW)
-- -----------------------------------------------------------------------------

-- Полная информация о тренировках с тренером и услугой
CREATE OR REPLACE VIEW v_workouts_full AS
SELECT
    w.id,
    w.datetime_start,
    w.status,
    w.notes,
    t.id                                       AS trainer_id,
    COALESCE(t.lastname, '') || ' ' || t.name  AS trainer_full_name,
    sp.specialization_name                     AS trainer_specialization,
    s.id                                       AS service_id,
    s.name                                     AS service_name,
    s.duration                                 AS service_duration,
    s.price                                    AS service_price
FROM      workouts        AS w
LEFT JOIN trainers        AS t  ON t.id  = w.idtrainer
LEFT JOIN specializations AS sp ON sp.id = t.idspecialization
LEFT JOIN services        AS s  ON s.id  = w.idservice;

COMMENT ON VIEW v_workouts_full IS 'Тренировки с расширенной информацией о тренере и услуге';

-- Остатки абонементов наездников и кол-во проведённых тренировок
CREATE OR REPLACE VIEW v_riders_balance AS
SELECT
    r.id,
    r.lastname,
    r.name,
    r.subscription_status,
    r.subscription_balance,
    r.rental_balance,
    COALESCE(stat.done_count, 0) AS done_workouts_total
FROM riders AS r
LEFT JOIN (
    SELECT
        wp.idrider,
        COUNT(*) FILTER (WHERE w.status = 'done') AS done_count
    FROM      workout_participants AS wp
    LEFT JOIN workouts             AS w ON w.id = wp.idworkout
    GROUP BY wp.idrider
) AS stat ON stat.idrider = r.id;

COMMENT ON VIEW v_riders_balance IS 'Остатки абонементов и статистика тренировок наездников';

-- -----------------------------------------------------------------------------
-- 5. Хранимые функции и процедуры
-- -----------------------------------------------------------------------------

-- Уменьшение остатка абонемента наездника
CREATE OR REPLACE FUNCTION fn_decrement_subscription(rider_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    new_balance INTEGER;
BEGIN
    UPDATE riders
       SET subscription_balance = subscription_balance - 1
     WHERE id = rider_id
       AND subscription_balance > 0
    RETURNING subscription_balance INTO new_balance;

    IF new_balance IS NULL THEN
        RAISE EXCEPTION 'Нет активного абонемента у наездника id=%', rider_id;
    END IF;

    RETURN new_balance;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_decrement_subscription(INTEGER)
    IS 'Уменьшает остаток абонемента наездника на 1; возвращает новое значение';

-- Закрытие тренировки: статус => done и списание занятий у участников
CREATE OR REPLACE PROCEDURE sp_close_workout(workout_id INTEGER)
LANGUAGE plpgsql AS $$
DECLARE
    rider RECORD;
BEGIN
    UPDATE workouts
       SET status = 'done'
     WHERE id = workout_id;

    FOR rider IN
        SELECT idrider
          FROM workout_participants
         WHERE idworkout = workout_id
           AND idrider IS NOT NULL
    LOOP
        PERFORM fn_decrement_subscription(rider.idrider);
    END LOOP;
END;
$$;

COMMENT ON PROCEDURE sp_close_workout(INTEGER)
    IS 'Завершает тренировку и списывает занятия у участников-наездников';

-- Выручка клуба за период
CREATE OR REPLACE FUNCTION fn_revenue_for_period(d_from DATE, d_to DATE)
RETURNS NUMERIC AS $$
DECLARE
    total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(s.price), 0)
      INTO total
      FROM workouts AS w
      LEFT JOIN services AS s ON s.id = w.idservice
     WHERE w.status = 'done'
       AND w.datetime_start::date BETWEEN d_from AND d_to;

    RETURN total;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION fn_revenue_for_period(DATE, DATE)
    IS 'Возвращает суммарную выручку клуба за период (по проведённым тренировкам)';

-- -----------------------------------------------------------------------------
-- 6. Триггеры
-- -----------------------------------------------------------------------------

-- Запрет пересечения тренировок одного тренера по времени
CREATE OR REPLACE FUNCTION trg_check_workout_overlap()
RETURNS TRIGGER AS $$
DECLARE
    overlap_count INTEGER;
BEGIN
    IF NEW.idtrainer IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT COUNT(*) INTO overlap_count
      FROM workouts
     WHERE idtrainer = NEW.idtrainer
       AND id <> COALESCE(NEW.id, -1)
       AND datetime_start = NEW.datetime_start;

    IF overlap_count > 0 THEN
        RAISE EXCEPTION
            'У тренера id=% уже есть тренировка на %',
            NEW.idtrainer, NEW.datetime_start;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_workout_overlap ON workouts;
CREATE TRIGGER trg_workout_overlap
    BEFORE INSERT OR UPDATE ON workouts
    FOR EACH ROW
    EXECUTE FUNCTION trg_check_workout_overlap();

-- Приведение логина к нижнему регистру
CREATE OR REPLACE FUNCTION trg_users_username_lower()
RETURNS TRIGGER AS $$
BEGIN
    NEW.username := lower(NEW.username);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_username_lower ON users;
CREATE TRIGGER trg_users_username_lower
    BEFORE INSERT OR UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION trg_users_username_lower();

-- -----------------------------------------------------------------------------
-- 7. Заполнение справочников начальными данными
-- -----------------------------------------------------------------------------

INSERT INTO roles (role_name) VALUES
    ('SuperAdmin'),
    ('Admin'),
    ('Trainer'),
    ('Rider')
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO specializations (specialization_name) VALUES
    ('Выездка'),
    ('Конкур'),
    ('Иппотерапия'),
    ('Прокат'),
    ('Обучение начинающих')
ON CONFLICT DO NOTHING;

INSERT INTO breeds (breed_name) VALUES
    ('Орловская рысистая'),
    ('Русская рысистая'),
    ('Будённовская'),
    ('Тракененская'),
    ('Ахалтекинская'),
    ('Чистокровная верховая'),
    ('Шетлендский пони')
ON CONFLICT DO NOTHING;

INSERT INTO services (name, duration, price, type, "limit", notes) VALUES
    ('Индивидуальная тренировка',           60, 2500, 'individual', 1, 'Тренировка с тренером один на один'),
    ('Групповая тренировка',                60, 1500, 'group',      6, 'Группа до 6 наездников'),
    ('Прокат лошади 30 минут',              30,  900, 'rental',     1, 'Прокат с инструктором'),
    ('Прокат лошади 60 минут',              60, 1500, 'rental',     1, 'Прокат с инструктором'),
    ('Иппотерапия',                         45, 2000, 'therapy',    1, 'Лечебная верховая езда'),
    ('Абонемент: 8 индивидуальных занятий', 60, 18000,'subscription',1,'Действует 60 дней')
ON CONFLICT DO NOTHING;

-- =============================================================================
-- Конец скрипта
-- =============================================================================
