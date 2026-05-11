-- Демо-данные для информационной системы конноспортивного клуба «Гардарика»
-- Запускать ПОСЛЕ schema.sql и queries_and_objects.sql.
-- Заполняет тренеров, лошадей, всадников и проведённые тренировки
-- за период март–май 2025 г., чтобы представления и запросы возвращали данные.


-- 1. Тренеры: создаём учётные записи в users (имя/фамилия/телефон живут там),
--    а затем — связанные строки в trainers с iduser.
WITH ins_users AS (
    INSERT INTO users (username, password, name, lastname, phone, idrole, is_approved)
    VALUES
        ('t_kuznetsova', 'PLACEHOLDER', 'Анна',     'Кузнецова', '+7-911-101-22-33',
            (SELECT id FROM roles WHERE role_name='Trainer'), TRUE),
        ('t_petrov',     'PLACEHOLDER', 'Иван',     'Петров',    '+7-911-202-33-44',
            (SELECT id FROM roles WHERE role_name='Trainer'), TRUE),
        ('t_sokolova',   'PLACEHOLDER', 'Ольга',    'Соколова',  '+7-911-303-44-55',
            (SELECT id FROM roles WHERE role_name='Trainer'), TRUE),
        ('t_morozov',    'PLACEHOLDER', 'Дмитрий',  'Морозов',   '+7-911-404-55-66',
            (SELECT id FROM roles WHERE role_name='Trainer'), TRUE),
        ('t_novikova',   'PLACEHOLDER', 'Екатерина','Новикова',  '+7-911-505-66-77',
            (SELECT id FROM roles WHERE role_name='Trainer'), TRUE)
    RETURNING id, username
)
INSERT INTO trainers (iduser, idspecialization)
SELECT id, CASE username
            WHEN 't_kuznetsova' THEN 1
            WHEN 't_petrov'     THEN 2
            WHEN 't_sokolova'   THEN 3
            WHEN 't_morozov'    THEN 4
            WHEN 't_novikova'   THEN 5
          END
FROM ins_users;


-- 2. Лошади (ссылаются на справочник breeds из schema.sql)
INSERT INTO horses (name, status, birth_year, color, gender, idbreed) VALUES
    ('Гром',    'active', 2015, 'Гнедая',     'жеребец', 1),
    ('Звезда',  'active', 2017, 'Серая',      'кобыла',  2),
    ('Буран',   'active', 2014, 'Вороная',    'жеребец', 3),
    ('Ветер',   'active', 2016, 'Рыжая',      'мерин',   4),
    ('Снежок',  'active', 2018, 'Белая',      'кобыла',  5),
    ('Малыш',   'active', 2019, 'Пегая',      'мерин',   7),
    ('Орлица',  'active', 2013, 'Гнедая',     'кобыла',  6);


-- 3. Всадники: имя/фамилия/телефон тоже идут в users.
WITH ins_users AS (
    INSERT INTO users (username, password, name, lastname, phone, idrole, is_approved)
    VALUES
        ('r_ivanova',    'PLACEHOLDER', 'Мария',   'Иванова',   '+7-921-111-11-11',
            (SELECT id FROM roles WHERE role_name='Rider'), TRUE),
        ('r_sidorov',    'PLACEHOLDER', 'Алексей', 'Сидоров',   '+7-921-222-22-22',
            (SELECT id FROM roles WHERE role_name='Rider'), TRUE),
        ('r_volkova',    'PLACEHOLDER', 'Елена',   'Волкова',   '+7-921-333-33-33',
            (SELECT id FROM roles WHERE role_name='Rider'), TRUE),
        ('r_grigoriev',  'PLACEHOLDER', 'Никита',  'Григорьев', '+7-921-444-44-44',
            (SELECT id FROM roles WHERE role_name='Rider'), TRUE),
        ('r_lebedeva',   'PLACEHOLDER', 'Татьяна', 'Лебедева',  '+7-921-555-55-55',
            (SELECT id FROM roles WHERE role_name='Rider'), TRUE),
        ('r_vasiliev',   'PLACEHOLDER', 'Сергей',  'Васильев',  '+7-921-666-66-66',
            (SELECT id FROM roles WHERE role_name='Rider'), TRUE),
        ('r_orlova',     'PLACEHOLDER', 'Юлия',    'Орлова',    '+7-921-777-77-77',
            (SELECT id FROM roles WHERE role_name='Rider'), TRUE)
    RETURNING id, username
)
INSERT INTO riders (iduser, datebirth, subscription_status,
                    subscription_balance, rental_balance)
SELECT id,
       CASE username
            WHEN 'r_ivanova'   THEN DATE '1995-03-12'
            WHEN 'r_sidorov'   THEN DATE '1990-07-23'
            WHEN 'r_volkova'   THEN DATE '2002-11-04'
            WHEN 'r_grigoriev' THEN DATE '1998-01-30'
            WHEN 'r_lebedeva'  THEN DATE '1985-09-15'
            WHEN 'r_vasiliev'  THEN DATE '1992-05-08'
            WHEN 'r_orlova'    THEN DATE '2000-12-19'
       END,
       CASE WHEN username = 'r_grigoriev' THEN 'paused' ELSE 'active' END,
       CASE username
            WHEN 'r_ivanova'   THEN 8
            WHEN 'r_sidorov'   THEN 5
            WHEN 'r_volkova'   THEN 6
            WHEN 'r_grigoriev' THEN 0
            WHEN 'r_lebedeva'  THEN 3
            WHEN 'r_vasiliev'  THEN 7
            WHEN 'r_orlova'    THEN 4
       END,
       CASE username
            WHEN 'r_sidorov'   THEN 2
            WHEN 'r_grigoriev' THEN 4
            WHEN 'r_lebedeva'  THEN 1
            WHEN 'r_orlova'    THEN 2
            ELSE 0
       END
FROM ins_users;


-- 4. Тренировки за март–май 2025 (все со статусом 'done')
--    Привязаны к разным тренерам и услугам, чтобы в сводке были разные строки.
INSERT INTO workouts (datetime_start, idtrainer, idservice, status, notes) VALUES
    -- Март 2025
    ('2025-03-04 10:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-03-04 12:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-03-06 18:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-03-08 11:00', 4, 4, 'done', 'Прокат 60 мин'),
    ('2025-03-11 16:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-03-13 17:00', 3, 5, 'done', 'Иппотерапия'),
    ('2025-03-15 10:00', 5, 1, 'done', 'Индивидуальная — обучение'),
    ('2025-03-18 18:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-03-20 19:00', 4, 3, 'done', 'Прокат 30 мин'),
    ('2025-03-22 11:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-03-25 18:00', 3, 5, 'done', 'Иппотерапия'),
    ('2025-03-29 12:00', 5, 1, 'done', 'Индивидуальная — обучение'),

    -- Апрель 2025
    ('2025-04-01 10:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-04-03 18:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-04-05 11:00', 4, 4, 'done', 'Прокат 60 мин'),
    ('2025-04-08 17:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-04-10 19:00', 3, 5, 'done', 'Иппотерапия'),
    ('2025-04-12 10:00', 5, 1, 'done', 'Индивидуальная — обучение'),
    ('2025-04-15 18:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-04-17 12:00', 4, 3, 'done', 'Прокат 30 мин'),
    ('2025-04-19 11:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-04-22 17:00', 3, 5, 'done', 'Иппотерапия'),
    ('2025-04-26 18:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-04-29 10:00', 5, 1, 'done', 'Индивидуальная — обучение'),

    -- Май 2025
    ('2025-05-02 10:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-05-04 12:00', 4, 4, 'done', 'Прокат 60 мин'),
    ('2025-05-06 18:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-05-08 11:00', 3, 5, 'done', 'Иппотерапия'),
    ('2025-05-10 17:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-05-13 19:00', 5, 1, 'done', 'Индивидуальная — обучение'),
    ('2025-05-15 18:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-05-18 10:00', 4, 3, 'done', 'Прокат 30 мин'),
    ('2025-05-20 18:00', 1, 1, 'done', 'Индивидуальная — выездка'),
    ('2025-05-22 17:00', 3, 5, 'done', 'Иппотерапия'),
    ('2025-05-25 11:00', 2, 2, 'done', 'Групповая — конкур'),
    ('2025-05-29 12:00', 5, 1, 'done', 'Индивидуальная — обучение'),

    -- Несколько запланированных и отменённых, чтобы данные были реалистичными
    ('2025-06-15 18:00', 1, 1, 'planned',   'Запланированная индивидуальная'),
    ('2025-06-15 18:00', 2, 2, 'planned',   'Запланированная групповая'),
    ('2025-05-10 15:00', 4, 3, 'cancelled', 'Отменена по болезни тренера');


-- 5. Участники тренировок (всадник + лошадь).
--    Заполняем массово через генератор, чтобы не писать 50 строк руками.
DO $$
DECLARE
    w RECORD;
    rider_id INTEGER;
    horse_id INTEGER;
    cnt      INTEGER := 0;
BEGIN
    FOR w IN SELECT id, idservice FROM workouts WHERE status = 'done' ORDER BY id LOOP
        cnt := cnt + 1;
        -- Чередуем всадников и лошадей по кругу
        rider_id := ((cnt - 1) % 7) + 1;
        horse_id := ((cnt - 1) % 7) + 1;

        INSERT INTO workout_participants (idworkout, idrider, idhorse)
        VALUES (w.id, rider_id, horse_id);

        -- Для групповых тренировок добавляем второго участника
        IF w.idservice = 2 THEN
            INSERT INTO workout_participants (idworkout, idrider, idhorse)
            VALUES (w.id, ((cnt) % 7) + 1, ((cnt) % 7) + 1);
        END IF;
    END LOOP;
END $$;


-- 6. Контрольные запросы (чтобы проверить, что данные подгрузились):
-- SELECT * FROM v_revenue_summary;
-- SELECT * FROM v_workouts_full WHERE start_at::date = '2025-05-06';
-- SELECT * FROM v_riders_balance ORDER BY rider_full_name;
-- SELECT fn_revenue_for_period('2025-05-01', '2025-05-31') AS may_revenue;
-- SELECT fn_trainer_workouts_count(1, '2025-03-01', '2025-05-31') AS anna_done;
