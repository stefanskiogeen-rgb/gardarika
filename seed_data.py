"""
Скрипт наполнения базы тестовыми данными.

Создаёт ~20 всадников, ~10 тренеров, ~15 лошадей, ~50 тренировок
(часть в прошлом — со статусом "Завершено", часть на сегодня —
"Проводится", часть в будущем — "Запланировано", несколько отменённых).

Запуск:
    DATABASE_URL=postgresql://user:pass@host/db python seed_data.py

Скрипт идемпотентный: при повторном запуске удаляет содержимое таблиц
и наполняет заново, поэтому подходит для проверки триггеров/функций/представлений.
"""

import os
import random
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

# Импортируем app/db и модели из server.py
from server import (
    app,
    db,
    Role,
    User,
    Specialization,
    Trainer,
    Service,
    Breed,
    Horse,
    Rider,
    Workout,
    WorkoutParticipant,
    initialize_database,
)
from sqlalchemy import text


SPECIALIZATIONS = [
    "Конкур", "Выездка", "Иппотерапия", "Троеборье",
    "Дрессура", "Вольтижировка", "Поло",
]

BREEDS = [
    "Орловская рысистая", "Будённовская", "Чистокровная верховая",
    "Ахалтекинская", "Ганноверская", "Тракененская",
    "Голштинская", "Шетлендский пони", "Арабская",
]

SERVICES = [
    {"name": "Индивидуальное занятие", "duration": 60, "price": 2500,
     "type": "Subscription", "limit": None,
     "notes": "Персональная тренировка с тренером"},
    {"name": "Групповое занятие", "duration": 60, "price": 1500,
     "type": "Subscription", "limit": 4,
     "notes": "В группе до 4 всадников"},
    {"name": "Прогулка по полям", "duration": 90, "price": 2000,
     "type": "Rental", "limit": None, "notes": "Конная прогулка под присмотром"},
    {"name": "Аренда лошади", "duration": 60, "price": 1800,
     "type": "Rental", "limit": None, "notes": "Самостоятельное использование манежа"},
    {"name": "Иппотерапия", "duration": 45, "price": 2200,
     "type": "Subscription", "limit": None,
     "notes": "Реабилитационное занятие"},
]

HORSE_NAMES = [
    "Буцефал", "Грация", "Ветер", "Звезда", "Ураган",
    "Жасмин", "Алмаз", "Молния", "Стрелка", "Орлик",
    "Фея", "Сапфир", "Шторм", "Тайга", "Зефир",
    "Перун", "Лютик", "Заря",
]

HORSE_COLORS = ["Гнедая", "Вороная", "Рыжая", "Серая", "Соловая", "Буланая"]
HORSE_GENDERS = ["Жеребец", "Кобыла", "Мерин"]

RIDER_FIRST_NAMES = [
    "Михаил", "Анна", "Александр", "Ольга", "Дмитрий",
    "Екатерина", "Сергей", "Юлия", "Иван", "Мария",
    "Павел", "Татьяна", "Артём", "Светлана", "Никита",
    "Виктория", "Денис", "Полина", "Кирилл", "Дарья",
]

RIDER_LAST_NAMES = [
    "Юрьев", "Иванова", "Соколов", "Петрова", "Кузнецов",
    "Волкова", "Морозов", "Смирнова", "Орлов", "Лебедева",
    "Беляев", "Зайцева", "Соловьёв", "Кудрявцева", "Тихонов",
    "Назарова", "Романов", "Гордеева", "Корнилов", "Ильина",
]

TRAINER_FIRST_NAMES = [
    "Игорь", "Елена", "Андрей", "Наталья", "Владимир",
    "Лариса", "Григорий", "Алина", "Борис", "Софья",
]

TRAINER_LAST_NAMES = [
    "Громов", "Светлова", "Воронин", "Зорина", "Мельников",
    "Северская", "Грачёв", "Горина", "Туманов", "Заречная",
]


def reset_data():
    """Удаляет данные из таблиц приложения (порядок важен из-за FK)."""
    db.session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    for table in [
        "workout_participants",
        "workouts",
        "riders",
        "horses",
        "trainers",
        "services",
        "breeds",
        "specializations",
        "users",
    ]:
        try:
            db.session.execute(text(f"DELETE FROM {table};"))
        except Exception as e:
            print(f"  [skip] DELETE FROM {table}: {e}")
            db.session.rollback()
            continue
    # Сбрасываем sequence-ы, чтобы id начинались с 1
    for seq in [
        "users_id_seq",
        "specializations_id_seq",
        "breeds_id_seq",
        "services_id_seq",
        "horses_id_seq",
        "trainers_id_seq",
        "riders_id_seq",
        "workouts_id_seq",
        "workout_participants_id_seq",
    ]:
        try:
            db.session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1;"))
        except Exception as e:
            db.session.rollback()
    db.session.commit()


def ensure_roles():
    if not Role.query.first():
        for name in ["SuperAdmin", "Admin", "Trainer", "Rider"]:
            db.session.add(Role(role_name=name))
        db.session.commit()


def seed_specializations():
    objs = [Specialization(name=s) for s in SPECIALIZATIONS]
    db.session.add_all(objs)
    db.session.commit()
    return objs


def seed_breeds():
    objs = [Breed(name=b) for b in BREEDS]
    db.session.add_all(objs)
    db.session.commit()
    return objs


def seed_services():
    objs = [Service(**s) for s in SERVICES]
    db.session.add_all(objs)
    db.session.commit()
    return objs


def seed_users():
    super_role = Role.query.filter_by(role_name="SuperAdmin").first()
    admin_role = Role.query.filter_by(role_name="Admin").first()
    trainer_role = Role.query.filter_by(role_name="Trainer").first()
    rider_role = Role.query.filter_by(role_name="Rider").first()

    users = [
        User(
            username="superadmin",
            password=generate_password_hash("admin", method='pbkdf2:sha256'),
            email="super@gardarika.local",
            first_name="Главный",
            last_name="Администратор",
            idrole=super_role.id,
        ),
        User(
            username="admin",
            password=generate_password_hash("admin", method='pbkdf2:sha256'),
            email="admin@gardarika.local",
            first_name="Иван",
            last_name="Админов",
            idrole=admin_role.id,
        ),
    ]
    # Аккаунты тренеров (логины: trainer1..trainerN)
    for i in range(1, 11):
        users.append(
            User(
                username=f"trainer{i}",
                password=generate_password_hash("trainer", method='pbkdf2:sha256'),
                email=f"trainer{i}@gardarika.local",
                first_name=TRAINER_FIRST_NAMES[i - 1],
                last_name=TRAINER_LAST_NAMES[i - 1],
                idrole=trainer_role.id,
            )
        )
    # Аккаунты всадников (логины: rider1..riderN)
    for i in range(1, 21):
        users.append(
            User(
                username=f"rider{i}",
                password=generate_password_hash("rider", method='pbkdf2:sha256'),
                email=f"rider{i}@gardarika.local",
                first_name=RIDER_FIRST_NAMES[i - 1],
                last_name=RIDER_LAST_NAMES[i - 1],
                idrole=rider_role.id,
            )
        )
    db.session.add_all(users)
    db.session.commit()
    return users


def seed_trainers(specs):
    trainers = []
    for i in range(10):
        t = Trainer(
            name=TRAINER_FIRST_NAMES[i],
            lastname=TRAINER_LAST_NAMES[i],
            phone=f"+7-9{random.randint(10, 99):02d}-{random.randint(100, 999):03d}-"
                  f"{random.randint(10, 99):02d}-{random.randint(10, 99):02d}",
            iduser=User.query.filter_by(username=f"trainer{i + 1}").first().id,
            idspecialization=random.choice(specs).id,
        )
        trainers.append(t)
    db.session.add_all(trainers)
    db.session.commit()
    return trainers


def seed_horses(breeds):
    horses = []
    statuses = ["Здорова"] * 12 + ["Болеет", "Травма", "На отдыхе"]
    for i in range(15):
        h = Horse(
            name=HORSE_NAMES[i],
            status=statuses[i],
            birth_year=random.randint(2008, 2020),
            color=random.choice(HORSE_COLORS),
            gender=random.choice(HORSE_GENDERS),
            notes="Тестовая запись" if i % 3 == 0 else None,
            idbreed=random.choice(breeds).id,
        )
        horses.append(h)
    db.session.add_all(horses)
    db.session.commit()
    return horses


def seed_riders():
    riders = []
    for i in range(20):
        sub = random.choice([0, 4, 6, 8, 10])
        rent = random.choice([0, 0, 2, 4])
        # Текстовый статус потом синхронизируется триггером/функцией
        if sub > 0 and rent > 0:
            sub_status = f"Абонемент: {sub}; Аренда: {rent}"
        elif sub > 0:
            sub_status = f"Абонемент: {sub}"
        elif rent > 0:
            sub_status = f"Аренда: {rent}"
        else:
            sub_status = "Без абонемента (разовые)"
        r = Rider(
            name=RIDER_FIRST_NAMES[i],
            lastname=RIDER_LAST_NAMES[i],
            datebirth=f"{random.randint(1985, 2010)}-{random.randint(1, 12):02d}-"
                      f"{random.randint(1, 28):02d}",
            phone=f"+7-9{random.randint(10, 99):02d}-{random.randint(100, 999):03d}-"
                  f"{random.randint(10, 99):02d}-{random.randint(10, 99):02d}",
            subscription_status=sub_status,
            subscription_balance=sub,
            rental_balance=rent,
            iduser=User.query.filter_by(username=f"rider{i + 1}").first().id,
        )
        riders.append(r)
    db.session.add_all(riders)
    db.session.commit()
    # Триггерами/функцией текстовый статус выставится при следующем UPDATE,
    # но при инициализации можно явно вызвать процедуру синхронизации.
    for r in riders:
        try:
            db.session.execute(
                text("SELECT fn_sync_rider_status_text(:rid)"),
                {"rid": r.id},
            )
        except Exception:
            db.session.rollback()
    db.session.commit()
    return riders


def seed_workouts(trainers, services, riders, horses):
    """Создаёт ~50 тренировок, разнесённых по времени:
    - Прошедшие (на > 1 день назад): "Завершено"
    - Сегодня в прошлом: "Проводится" / "Завершено"
    - Будущие: "Запланировано"
    - Несколько отменённых.
    """
    now = datetime.utcnow() + timedelta(hours=3)  # МСК
    healthy_horses = [h for h in horses if h.status in ("Здорова",)]

    workouts = []
    # 25 в прошлом → "Завершено"
    for i in range(25):
        days_ago = random.randint(2, 30)
        when = (now - timedelta(days=days_ago)).replace(
            hour=random.choice([10, 12, 14, 16, 18]),
            minute=0,
            second=0,
            microsecond=0,
        )
        w = Workout(
            datetime_start=when,
            idtrainer=random.choice(trainers).id,
            idservice=random.choice(services).id,
            status="Завершено",
            notes=None,
        )
        workouts.append(w)

    # 5 отменённых
    for i in range(5):
        days_ago = random.randint(1, 10)
        when = (now - timedelta(days=days_ago)).replace(
            hour=random.choice([10, 12, 14, 16]),
            minute=0,
            second=0,
            microsecond=0,
        )
        w = Workout(
            datetime_start=when,
            idtrainer=random.choice(trainers).id,
            idservice=random.choice(services).id,
            status="Отменено",
            notes="Отмена по погоде",
        )
        workouts.append(w)

    # 20 в будущем → "Запланировано"
    for i in range(20):
        days_ahead = random.randint(0, 14)
        when = (now + timedelta(days=days_ahead)).replace(
            hour=random.choice([10, 12, 14, 16, 18]),
            minute=0,
            second=0,
            microsecond=0,
        )
        w = Workout(
            datetime_start=when,
            idtrainer=random.choice(trainers).id,
            idservice=random.choice(services).id,
            status="Запланировано",
            notes=None,
        )
        workouts.append(w)

    db.session.add_all(workouts)
    db.session.flush()  # получаем id

    # Добавляем участников. ВАЖНО: для уже завершённых тренировок участники
    # должны быть добавлены до COMMIT, чтобы DEFERRED-триггер списал занятия.
    for w in workouts:
        # 1-2 участника на тренировку
        n = random.choice([1, 1, 1, 2])
        used_riders = random.sample(riders, k=n)
        for r in used_riders:
            horse_for = random.choice(healthy_horses) if healthy_horses else None
            db.session.add(
                WorkoutParticipant(
                    idworkout=w.id,
                    idrider=r.id,
                    idhorse=horse_for.id if horse_for else None,
                )
            )

    db.session.commit()
    return workouts


def main():
    with app.app_context():
        print("== Инициализация схемы (таблицы/триггеры/функции/процедуры/представления) ==")
        initialize_database()

        print("== Сброс старых данных ==")
        reset_data()

        print("== Базовые роли ==")
        ensure_roles()

        print("== Специализации ==")
        specs = seed_specializations()
        print(f"  + {len(specs)}")

        print("== Породы ==")
        breeds = seed_breeds()
        print(f"  + {len(breeds)}")

        print("== Услуги ==")
        services = seed_services()
        print(f"  + {len(services)}")

        print("== Пользователи ==")
        users = seed_users()
        print(f"  + {len(users)} (1 super, 1 admin, 10 trainer*, 20 rider*)")

        print("== Тренеры ==")
        trainers = seed_trainers(specs)
        print(f"  + {len(trainers)}")

        print("== Лошади ==")
        horses = seed_horses(breeds)
        print(f"  + {len(horses)}")

        print("== Всадники ==")
        riders = seed_riders()
        print(f"  + {len(riders)}")

        print("== Тренировки ==")
        workouts = seed_workouts(trainers, services, riders, horses)
        print(f"  + {len(workouts)}")

        print("\n== Готово ==")
        print(f"Логины:")
        print(f"  superadmin / admin   (SuperAdmin)")
        print(f"  admin / admin        (Admin)")
        print(f"  trainer1..10 / trainer")
        print(f"  rider1..20 / rider")


if __name__ == "__main__":
    random.seed(42)
    main()
