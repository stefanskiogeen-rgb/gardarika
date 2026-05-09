# Гардарика — система управления конноспортивным клубом

Курсовой проект. Веб-приложение на Flask + PostgreSQL для администрирования
работы конного клуба: всадники, тренеры, лошади, услуги, тренировки, абонементы.

## Стек

- **Backend:** Python 3.11+, Flask 3, Flask-SQLAlchemy 3, SQLAlchemy 2
- **БД:** PostgreSQL 15 (триггеры, хранимые процедуры, представления). Для
  быстрых dev-проверок поддерживается SQLite (без триггеров).
- **Frontend:** статические HTML/CSS/JS, шаблоны Jinja2 рендерятся прямо
  из корня репо (`template_folder='.'`).
- **Развёртывание:** Docker Compose (web + db + pgAdmin) или Gunicorn.

## Структура репозитория

```
.
├── server.py                # Точка входа Flask, все маршруты, модели, инициализация БД
├── cleanup_database.py      # Однократная миграция legacy-схемы → актуальной
├── requirements.txt         # Запинены точные версии (см. F2 в плане улучшений)
├── .env.example             # Шаблон переменных окружения (скопировать в .env)
├── Dockerfile               # Образ web-контейнера
├── docker-compose.yml       # web + db (PostgreSQL 15) + pgAdmin
├── dashboard.html           # Главный экран
├── dashboard-add.html       # Форма создания/редактирования тренировки
├── workouts-list.html       # Список тренировок
├── horses.html / horses-list.html
├── trainers.html / trainers-list.html
├── riders.html / riders-list.html
├── services.html / services-list.html
├── admin-users.html         # Управление пользователями (только SuperAdmin)
└── static/
    ├── img/                 # Логотипы, иконки
    └── uploads/             # Фото лошадей/всадников/тренеров (создаётся автоматически)
```

## Установка и запуск

### Вариант 1 — Docker Compose (как в production)

```bash
git clone https://github.com/stefanskiogeen-rgb/gardarika.git
cd gardarika
cp .env.example .env
# отредактируйте .env — как минимум сгенерируйте SECRET_KEY:
python -c "import secrets; print(secrets.token_hex(32))"
docker compose up --build
```

После старта:

- веб-приложение: <http://localhost> (порт 80 → контейнерный 8000)
- pgAdmin: <http://localhost:5050> (логин `admin@gardarika.ru`, пароль `admin123`)
- PostgreSQL: `localhost:5432`, БД `gardarika_db`, пользователь `gardarika`

> **Важно.** При первом запуске `server.py` сам создаёт таблицы, роли,
> представления, функции, процедуры и триггеры. Если вы переезжаете со
> старой схемы (с таблицами `user`, `breed`, `specialization` и колонками
> `idrider`/`idhorse` в `workouts`), сначала прогоните `cleanup_database.py`.

### Вариант 2 — без Docker (локально)

```bash
git clone https://github.com/stefanskiogeen-rgb/gardarika.git
cd gardarika
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Сгенерируйте SECRET_KEY и пропишите DATABASE_URL.

# Поднимите PostgreSQL отдельно (docker run, brew services, etc.)
# либо используйте sqlite для быстрой проверки:
export DATABASE_URL=sqlite:///local.db
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

python server.py
```

Приложение слушает <http://localhost:8000>.

### Вариант 3 — Gunicorn (production)

```bash
export GUNICORN_MAIN=1
export FLASK_ENV=production
export SECRET_KEY=...                 # ОБЯЗАТЕЛЬНО, иначе app откажется стартовать
export DATABASE_URL=postgresql://...

gunicorn -w 2 -b 0.0.0.0:8000 server:app
```

## Переменные окружения

| Переменная       | Назначение | По умолчанию |
|------------------|------------|--------------|
| `SECRET_KEY`     | Подпись Flask-сессий. **Обязательна** в production (`FLASK_ENV=production` или `GUNICORN_MAIN=1`). В dev генерируется случайно при старте. | — |
| `DATABASE_URL`   | DSN SQLAlchemy. Для PostgreSQL автоматически добавляется `connect_timeout=10` и `pool_pre_ping=True`. | `sqlite:///local.db` |
| `FLASK_ENV`      | `production` — включает строгий режим (требует `SECRET_KEY`). | — |
| `GUNICORN_MAIN`  | `1` — выполнить `initialize_database()` ровно один раз при старте gunicorn. | — |

## Тестовые роли и логины

После первой регистрации можно вручную в БД (или через `/admin/users` под
SuperAdmin) назначить роли. Доступные значения в таблице `roles`:

- `SuperAdmin` — полный доступ, единственный, кто видит и меняет роли.
- `Admin` — CRUD по всадникам/тренерам/лошадям/услугам/тренировкам.
- `Trainer` — пока приравнивается к обычному пользователю (без админ-прав).
- `Rider` — обычный пользователь, по умолчанию выдаётся при регистрации.

Для локального dev обычно удобно сделать первого зарегистрированного
пользователя SuperAdmin:

```sql
UPDATE users SET idrole = (SELECT id FROM roles WHERE role_name = 'SuperAdmin')
WHERE username = '<ваш_логин>';
```

## Главные маршруты

| Метод | Путь | Доступ | Что делает |
|------:|------|--------|------------|
| GET | `/` | публичный | Редирект на `/dashboard` или `/login`. |
| GET/POST | `/login`, `/register` | публичный | Авторизация и регистрация (роль `Rider`). |
| GET | `/dashboard` | авторизованные | Сводка + ближайшие тренировки. Если БД недоступна — показывает баннер «Нет связи с БД» (B15). |
| `*` | `/horses`, `/trainers`, `/riders`, `/services` | смотрят все, изменяют только Admin | CRUD карточек. |
| `*` | `/workouts` | смотрят все, изменяют только Admin | Тренировки + участники + статусы. |
| GET | `/admin/users` | только SuperAdmin | Управление ролями и удаление пользователей. |
| GET | `/logout` | авторизованные | Сброс сессии. |

## Структура БД (PostgreSQL)

Основные таблицы (создаются автоматически в `initialize_database()`):

- `roles` — справочник ролей.
- `users` — пользователи системы (логин, хэш пароля, FK на `roles`).
- `specializations`, `trainers` — тренеры и их специализации.
- `breeds`, `horses` — породы и лошади.
- `riders` — всадники с балансами `subscription_balance` / `rental_balance`.
- `services` — услуги (длительность, цена, тип, лимит участников).
- `workouts` — тренировки (`datetime_start`, `idtrainer`, `idservice`, `status`).
- `workout_participants` — связь тренировка ↔ всадник ↔ лошадь (плюс `guest_name`
  для разовых посещений).

Дополнительно (только PostgreSQL):

- Представления `v_dashboard_stats`, `v_rider_active_subscriptions`.
- Функции `fn_auto_update_workouts()`, `fn_sync_rider_status_text(r_id)`,
  `fn_deduct_lessons_trigger()`.
- Процедура `sp_adjust_rider_balance(r_id, amount, b_type)`.
- Constraint trigger `trg_on_workout_complete` (списание занятий при переводе
  тренировки в статус «Завершено»).

## Как добавить нового админа

1. Зайдите под уже существующим SuperAdmin (или назначьте такого вручную в БД).
2. Откройте `/admin/users`.
3. Нажмите «Сделать админом» рядом с нужным пользователем.

## Полезные команды разработки

```bash
# Smoke-тест без БД (используется sqlite):
DATABASE_URL=sqlite:///test.db SECRET_KEY=dev python -c "
import server
c = server.app.test_client()
print(c.get('/').status_code, c.get('/login').status_code)
"

# Применить cleanup-миграцию (если приехали со старой схемы):
python cleanup_database.py
```

## Известные ограничения и план улучшений

См. `improvement-proposal.md` (если приложен к работе) — там расписаны
группы пунктов A/B/C/D/E/F/G. В этом коммите реализованы:

- **A3** — `SECRET_KEY` из окружения, хардкод убран.
- **A1** — `is_admin` грузится из БД в `before_request`, чистый POST больше не
  отдаёт 403 на свежей сессии.
- **A2** — введённые в форму данные сохраняются при ошибке валидации
  (`/workouts/add` и `/workouts/edit`).
- **A11** — `connect_timeout=10` и `pool_pre_ping=True` для PostgreSQL DSN.
- **B15** — баннер «Нет связи с БД» на дашборде при недоступности PostgreSQL.
- **C3** — декораторы `@admin_required` / `@super_admin_required`, повторяющиеся
  проверки прав вырезаны из 20+ мест.
- **F2** — точные версии зависимостей в `requirements.txt`.
- **F5** — этот README.
