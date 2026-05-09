-- =============================================================================
-- Запросы и объекты базы данных
-- Информационная система конноспортивного клуба «Гардарика»
-- СУБД: PostgreSQL 15
--
-- Содержит:
--   1–4   — SELECT-запросы
--   5–7   — представления (VIEW)
--   8–11  — хранимые функции (FUNCTION)
--   12–13 — хранимые процедуры (PROCEDURE)
--   14–15 — триггеры (TRIGGER)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Запрос на получение расписания тренировок на заданную дату
-- -----------------------------------------------------------------------------
SELECT
    w.id                                                AS workout_id,
    w.datetime_start                                    AS start_at,
    COALESCE(t.lastname, '') || ' ' || t.name           AS trainer_full_name,
    sp.specialization_name                              AS trainer_specialization,
    s.name                                              AS service_name,
    s.duration                                          AS duration_min,
    w.status                                            AS status
FROM      workouts        AS w
LEFT JOIN trainers        AS t  ON t.id  = w.idtrainer
LEFT JOIN specializations AS sp ON sp.id = t.idspecialization
LEFT JOIN services        AS s  ON s.id  = w.idservice
WHERE w.datetime_start::date = '2025-06-15'
ORDER BY w.datetime_start;


-- -----------------------------------------------------------------------------
-- 2. Запрос на получение тренировок конкретного всадника
-- -----------------------------------------------------------------------------
SELECT
    w.id                                                AS workout_id,
    w.datetime_start                                    AS start_at,
    COALESCE(t.lastname, '') || ' ' || t.name           AS trainer_full_name,
    s.name                                              AS service_name,
    h.name                                              AS horse_name,
    w.status                                            AS status
FROM      workout_participants AS wp
JOIN      workouts             AS w  ON w.id  = wp.idworkout
LEFT JOIN trainers             AS t  ON t.id  = w.idtrainer
LEFT JOIN services             AS s  ON s.id  = w.idservice
LEFT JOIN horses               AS h  ON h.id  = wp.idhorse
WHERE wp.idrider = 5            -- идентификатор всадника
ORDER BY w.datetime_start DESC;


-- -----------------------------------------------------------------------------
-- 3. Запрос на получение списка свободных лошадей на заданное время
-- -----------------------------------------------------------------------------
SELECT
    h.id                AS horse_id,
    h.name              AS horse_name,
    b.breed_name        AS breed,
    h.gender            AS gender,
    h.status            AS status
FROM      horses AS h
LEFT JOIN breeds AS b ON b.id = h.idbreed
WHERE h.status = 'active'
  AND h.id NOT IN (
      SELECT wp.idhorse
      FROM   workouts             AS w
      JOIN   workout_participants AS wp ON wp.idworkout = w.id
      WHERE  w.datetime_start = '2025-06-15 18:00:00'
        AND  wp.idhorse IS NOT NULL
  )
ORDER BY h.name;


-- -----------------------------------------------------------------------------
-- 4. Запрос на расчёт выручки клуба за период
-- -----------------------------------------------------------------------------
SELECT
    s.type                          AS service_type,
    s.name                          AS service_name,
    COUNT(w.id)                     AS workouts_done,
    SUM(s.price)                    AS revenue
FROM      workouts AS w
LEFT JOIN services AS s ON s.id = w.idservice
WHERE w.status = 'done'
  AND w.datetime_start::date BETWEEN '2025-05-01' AND '2025-05-31'
GROUP BY s.type, s.name
ORDER BY revenue DESC NULLS LAST;


-- =============================================================================
-- ПРЕДСТАВЛЕНИЯ (VIEW)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 5. Представление для формирования полной информации о тренировках
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_workouts_full CASCADE;
CREATE VIEW v_workouts_full AS
SELECT
    w.id                                                AS workout_id,
    w.datetime_start                                    AS start_at,
    w.status                                            AS status,
    w.notes                                             AS notes,
    t.id                                                AS trainer_id,
    COALESCE(t.lastname, '') || ' ' || t.name           AS trainer_full_name,
    sp.specialization_name                              AS trainer_specialization,
    s.id                                                AS service_id,
    s.name                                              AS service_name,
    s.duration                                          AS service_duration,
    s.price                                             AS service_price
FROM      workouts        AS w
LEFT JOIN trainers        AS t  ON t.id  = w.idtrainer
LEFT JOIN specializations AS sp ON sp.id = t.idspecialization
LEFT JOIN services        AS s  ON s.id  = w.idservice;

-- Пример использования:
-- SELECT * FROM v_workouts_full
--  WHERE start_at::date = '2025-06-15';


-- -----------------------------------------------------------------------------
-- 6. Представление для формирования таблицы баланса абонементов всадников
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_riders_balance CASCADE;
CREATE VIEW v_riders_balance AS
SELECT
    r.id                                                AS rider_id,
    COALESCE(r.lastname, '') || ' ' || r.name           AS rider_full_name,
    r.phone                                             AS phone,
    r.subscription_status                               AS subscription_status,
    r.subscription_balance                              AS subscription_balance,
    r.rental_balance                                    AS rental_balance,
    COALESCE(stat.done_count, 0)                        AS done_workouts_total
FROM riders AS r
LEFT JOIN (
    SELECT
        wp.idrider,
        COUNT(*) FILTER (WHERE w.status = 'done') AS done_count
    FROM      workout_participants AS wp
    LEFT JOIN workouts             AS w ON w.id = wp.idworkout
    GROUP BY wp.idrider
) AS stat ON stat.idrider = r.id;

-- Пример использования:
-- SELECT * FROM v_riders_balance
--  WHERE subscription_balance > 0
--  ORDER BY rider_full_name;


-- -----------------------------------------------------------------------------
-- 7. Представление для формирования сводки по выручке клуба
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_revenue_summary CASCADE;
CREATE VIEW v_revenue_summary AS
SELECT
    DATE_TRUNC('month', w.datetime_start)::date         AS period_month,
    s.type                                              AS service_type,
    s.name                                              AS service_name,
    COUNT(w.id)                                         AS workouts_done,
    SUM(s.price)                                        AS revenue
FROM      workouts AS w
LEFT JOIN services AS s ON s.id = w.idservice
WHERE w.status = 'done'
GROUP BY DATE_TRUNC('month', w.datetime_start), s.type, s.name
ORDER BY period_month DESC, revenue DESC;

-- Пример использования:
-- SELECT * FROM v_revenue_summary
--  WHERE period_month >= DATE '2025-01-01';


-- =============================================================================
-- ХРАНИМЫЕ ФУНКЦИИ
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 8. Хранимая функция для расчёта выручки клуба за период
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_revenue_for_period(d_from DATE, d_to DATE)
RETURNS NUMERIC AS $$
DECLARE
    total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(s.price), 0)
      INTO total
      FROM      workouts AS w
      LEFT JOIN services AS s ON s.id = w.idservice
     WHERE w.status = 'done'
       AND w.datetime_start::date BETWEEN d_from AND d_to;

    RETURN total;
END;
$$ LANGUAGE plpgsql STABLE;

-- Пример вызова:
-- SELECT fn_revenue_for_period('2025-05-01', '2025-05-31') AS revenue;


-- -----------------------------------------------------------------------------
-- 9. Хранимая функция для расчёта количества проведённых тренировок
--    тренера за период
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_trainer_workouts_count(
    trainer_id INTEGER,
    d_from     DATE,
    d_to       DATE
)
RETURNS INTEGER AS $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*)
      INTO cnt
      FROM workouts AS w
     WHERE w.idtrainer = trainer_id
       AND w.status    = 'done'
       AND w.datetime_start::date BETWEEN d_from AND d_to;

    RETURN cnt;
END;
$$ LANGUAGE plpgsql STABLE;

-- Пример вызова:
-- SELECT fn_trainer_workouts_count(3, '2025-05-01', '2025-05-31') AS workouts_done;


-- -----------------------------------------------------------------------------
-- 10. Хранимая функция для уменьшения остатка абонемента всадника
-- -----------------------------------------------------------------------------
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
        RAISE EXCEPTION 'Нет активного абонемента у всадника id=%', rider_id;
    END IF;

    RETURN new_balance;
END;
$$ LANGUAGE plpgsql;

-- Пример вызова:
-- SELECT fn_decrement_subscription(5) AS remaining_balance;


-- -----------------------------------------------------------------------------
-- 11. Хранимая функция для проверки доступности лошади на заданное время
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_horse_available(
    horse_id INTEGER,
    at_time  TIMESTAMP
)
RETURNS BOOLEAN AS $$
DECLARE
    busy_count INTEGER;
    horse_st   VARCHAR(100);
BEGIN
    SELECT status INTO horse_st FROM horses WHERE id = horse_id;
    IF horse_st IS DISTINCT FROM 'active' THEN
        RETURN FALSE;
    END IF;

    SELECT COUNT(*)
      INTO busy_count
      FROM workouts             AS w
      JOIN workout_participants AS wp ON wp.idworkout = w.id
     WHERE wp.idhorse        = horse_id
       AND w.datetime_start  = at_time
       AND w.status          IN ('planned', 'done');

    RETURN busy_count = 0;
END;
$$ LANGUAGE plpgsql STABLE;

-- Пример вызова:
-- SELECT fn_horse_available(2, '2025-06-15 18:00:00') AS is_free;


-- =============================================================================
-- ХРАНИМЫЕ ПРОЦЕДУРЫ
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 12. Хранимая процедура закрытия тренировки и списания занятий
-- -----------------------------------------------------------------------------
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

-- Пример вызова:
-- CALL sp_close_workout(17);


-- -----------------------------------------------------------------------------
-- 13. Хранимая процедура добавления нового всадника
-- -----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_add_rider(
    p_name                  VARCHAR,
    p_lastname              VARCHAR,
    p_datebirth             DATE,
    p_phone                 VARCHAR,
    p_subscription_status   VARCHAR,
    p_subscription_balance  INTEGER DEFAULT 0,
    p_rental_balance        INTEGER DEFAULT 0,
    p_iduser                INTEGER DEFAULT NULL
)
LANGUAGE plpgsql AS $$
DECLARE
    new_id INTEGER;
BEGIN
    IF p_subscription_balance < 0 OR p_rental_balance < 0 THEN
        RAISE EXCEPTION
            'Баланс абонемента/проката не может быть отрицательным';
    END IF;

    INSERT INTO riders (
        name, lastname, datebirth, phone,
        subscription_status, subscription_balance, rental_balance, iduser
    ) VALUES (
        p_name, p_lastname, p_datebirth, p_phone,
        p_subscription_status, p_subscription_balance, p_rental_balance, p_iduser
    )
    RETURNING id INTO new_id;

    RAISE NOTICE 'Новый всадник добавлен, id=%', new_id;
END;
$$;

-- Пример вызова:
-- CALL sp_add_rider(
--     'Иван', 'Петров', DATE '2005-04-12',
--     '+7-900-123-45-67', 'active', 8, 0, NULL
-- );


-- =============================================================================
-- ТРИГГЕРЫ
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 14. Триггер для проверки пересечения тренировок одного тренера
-- -----------------------------------------------------------------------------
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
     WHERE idtrainer       = NEW.idtrainer
       AND id              <> COALESCE(NEW.id, -1)
       AND datetime_start  = NEW.datetime_start;

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

-- Пример проверки:
-- INSERT INTO workouts (datetime_start, idtrainer, idservice, status)
--      VALUES ('2025-06-15 18:00:00', 3, 1, 'planned');
-- -- При попытке вставить вторую запись на то же время того же тренера —
-- -- срабатывает RAISE EXCEPTION.


-- -----------------------------------------------------------------------------
-- 15. Триггер приведения username к нижнему регистру
-- -----------------------------------------------------------------------------
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

-- Пример проверки:
-- INSERT INTO users (username, password, email, idrole)
--      VALUES ('IvanovAdmin', '<hash>', 'ivan@example.com', 2);
-- SELECT username FROM users WHERE email = 'ivan@example.com';
-- -- Ожидается: 'ivanovadmin'


-- =============================================================================
-- Конец скрипта
-- =============================================================================
