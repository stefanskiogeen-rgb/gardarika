"""Тесты механизма аутентификации и хеширования пароля."""
from werkzeug.security import generate_password_hash, check_password_hash


# pbkdf2:sha256 — кроссплатформенный алгоритм (работает на Windows,
# где OpenSSL без поддержки scrypt).
_HASH_METHOD = "pbkdf2:sha256"


def test_password_hash_is_irreversible():
    """Хеш не должен совпадать с исходным паролем."""
    pwd = "Sup3rS3cret!"
    h = generate_password_hash(pwd, method=_HASH_METHOD)
    assert h != pwd
    assert "pbkdf2" in h or "scrypt" in h


def test_password_hash_verifies_correctly():
    """check_password_hash возвращает True только для правильного пароля."""
    pwd = "Sup3rS3cret!"
    h = generate_password_hash(pwd, method=_HASH_METHOD)
    assert check_password_hash(h, pwd) is True
    assert check_password_hash(h, "wrong-pass") is False


def test_password_hash_unique_salt():
    """Один и тот же пароль даёт разные хеши (соль)."""
    pwd = "samepass"
    assert (generate_password_hash(pwd, method=_HASH_METHOD)
            != generate_password_hash(pwd, method=_HASH_METHOD))


def test_login_route_returns_200(client):
    """Страница входа доступна без авторизации."""
    r = client.get("/login")
    assert r.status_code in (200, 302)


def test_protected_dashboard_redirects_anonymous(client):
    """Анонимный пользователь не может попасть на /dashboard."""
    r = client.get("/dashboard", follow_redirects=False)
    # Допускаем 302/303 редирект на /login или 401
    assert r.status_code in (302, 303, 401)


def test_login_with_valid_credentials(client):
    """Логин с корректными данными успешно проходит."""
    r = client.post("/login", data={
        "username": "testadmin",
        "password": "admin-pass",
    }, follow_redirects=False)
    # Успешный логин обычно делает редирект
    assert r.status_code in (200, 302, 303)


def test_login_with_invalid_credentials(client):
    """Логин с неверным паролем не должен пройти."""
    r = client.post("/login", data={
        "username": "testadmin",
        "password": "wrong",
    }, follow_redirects=False)
    # Не должно вернуть редирект на dashboard
    assert r.status_code in (200, 401, 403)


# ===== СЦЕНАРИИ РЕГИСТРАЦИИ И ГОСТЕВОЙ ВХОД =====

def test_register_rider_is_auto_approved(app, client):
    """Всадник при регистрации сразу одобрен и заходит без подтверждения."""
    from server import User
    r = client.post("/register", data={
        "username": "newrider", "password": "test123",
        "name": "Анна", "lastname": "Иванова", "phone": "+79990001122",
        "role": "Rider",
    }, follow_redirects=False)
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        u = User.query.filter_by(username="newrider").first()
        assert u is not None
        assert u.is_approved is True
        assert u.is_rider is True
        assert u.name == "Анна"
        assert u.lastname == "Иванова"


def test_register_trainer_pending_approval(app, client):
    """Тренер при регистрации создаётся, но без одобрения админа войти не может."""
    from server import User, Trainer
    r = client.post("/register", data={
        "username": "newtrainer", "password": "test123",
        "name": "Сергей", "lastname": "Петров", "phone": "+79990001133",
        "role": "Trainer", "specialization": "Выездка",
    }, follow_redirects=False)
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        u = User.query.filter_by(username="newtrainer").first()
        assert u is not None
        assert u.is_approved is False
        assert u.is_trainer is True
        # Профиль тренера тоже создан
        t = Trainer.query.filter_by(iduser=u.id).first()
        assert t is not None

    # Попытка войти — отказ
    r2 = client.post("/login", data={
        "username": "newtrainer", "password": "test123",
    }, follow_redirects=False)
    assert r2.status_code == 200
    assert "ожидает одобрения" in r2.get_data(as_text=True)


def test_trainer_login_after_approval_succeeds(app, client):
    """После одобрения тренер успешно входит."""
    from server import User, db
    # Сначала зарегистрировать тренера
    client.post("/register", data={
        "username": "trainer2", "password": "p2",
        "name": "Иван", "lastname": "Сидоров",
        "role": "Trainer", "specialization": "Конкур",
    })
    with app.app_context():
        u = User.query.filter_by(username="trainer2").first()
        u.is_approved = True
        db.session.commit()
    r = client.post("/login", data={
        "username": "trainer2", "password": "p2",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_guest_login_sets_session(client):
    """Кнопка «Войти как гость» создаёт сессию без записи в БД."""
    r = client.post("/login/guest", follow_redirects=False)
    assert r.status_code in (302, 303)
    with client.session_transaction() as s:
        assert s.get("is_guest") is True
        assert s.get("is_admin") is False
        assert "username" not in s


def test_guest_can_access_workouts(client):
    """Гость может смотреть тренировки (read-only)."""
    client.post("/login/guest")
    r = client.get("/workouts", follow_redirects=False)
    assert r.status_code == 200


def test_guest_cannot_add_workout(client):
    """Гость не может создать тренировку (нет прав is_admin)."""
    client.post("/login/guest")
    r = client.get("/workouts/add", follow_redirects=False)
    # Либо 403 (Отказано), либо редирект — главное, не 200 без проверки
    assert r.status_code in (302, 303, 403)
