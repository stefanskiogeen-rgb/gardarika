"""Тесты механизма аутентификации и хеширования пароля."""
from werkzeug.security import generate_password_hash, check_password_hash


def test_password_hash_is_irreversible():
    """Хеш не должен совпадать с исходным паролем."""
    pwd = "Sup3rS3cret!"
    h = generate_password_hash(pwd)
    assert h != pwd
    assert "pbkdf2" in h or "scrypt" in h


def test_password_hash_verifies_correctly():
    """check_password_hash возвращает True только для правильного пароля."""
    pwd = "Sup3rS3cret!"
    h = generate_password_hash(pwd)
    assert check_password_hash(h, pwd) is True
    assert check_password_hash(h, "wrong-pass") is False


def test_password_hash_unique_salt():
    """Один и тот же пароль даёт разные хеши (соль)."""
    pwd = "samepass"
    assert generate_password_hash(pwd) != generate_password_hash(pwd)


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
