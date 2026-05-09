"""Общая конфигурация pytest для тестов приложения."""
import os
import sys
import tempfile

import pytest

# Добавляем корень проекта в sys.path, чтобы import server работал
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Используем временный SQLite файл, чтобы тесты не трогали PostgreSQL
_db_fd, _db_path = tempfile.mkstemp(prefix="gardarika_test_", suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"


@pytest.fixture(scope="session")
def app():
    """Тестовое Flask-приложение с инициализированной БД."""
    from server import app as flask_app, db, Role, User
    from werkzeug.security import generate_password_hash

    flask_app.config.update(TESTING=True)

    with flask_app.app_context():
        db.drop_all()
        db.create_all()

        # Заполняем минимальный набор справочников для тестов
        if not Role.query.filter_by(role_name="Admin").first():
            db.session.add(Role(role_name="SuperAdmin"))
            db.session.add(Role(role_name="Admin"))
            db.session.add(Role(role_name="Trainer"))
            db.session.add(Role(role_name="Rider"))
            db.session.commit()

        admin_role = Role.query.filter_by(role_name="Admin").first()
        if not User.query.filter_by(username="testadmin").first():
            db.session.add(User(
                username="testadmin",
                password=generate_password_hash("admin-pass"),
                email="admin@example.com",
                first_name="Test",
                last_name="Admin",
                idrole=admin_role.id,
            ))
            db.session.commit()

    yield flask_app

    try:
        os.close(_db_fd)
        os.remove(_db_path)
    except OSError:
        pass


@pytest.fixture()
def client(app):
    """HTTP-клиент Flask для функциональных тестов."""
    return app.test_client()
