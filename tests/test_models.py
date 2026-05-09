"""Тесты моделей предметной области."""
import datetime as dt


def test_role_model_create(app):
    from server import db, Role
    with app.app_context():
        r = Role(role_name="TestRole")
        db.session.add(r)
        db.session.commit()
        assert r.id is not None
        # cleanup
        db.session.delete(r)
        db.session.commit()


def test_user_is_admin_property(app):
    from server import User, Role
    with app.app_context():
        admin_role = Role.query.filter_by(role_name="Admin").first()
        rider_role = Role.query.filter_by(role_name="Rider").first()
        u_admin = User(username="admin1", password="x", idrole=admin_role.id)
        u_admin.role = admin_role
        u_rider = User(username="rider1", password="x", idrole=rider_role.id)
        u_rider.role = rider_role

        assert u_admin.is_admin is True
        assert u_rider.is_admin is False


def test_horse_create(app):
    from server import db, Horse, Breed
    with app.app_context():
        b = Breed(name="ТестПорода")
        db.session.add(b)
        db.session.commit()

        h = Horse(name="Гром", status="active", birth_year=2018,
                  color="вороной", gender="жеребец", idbreed=b.id)
        db.session.add(h)
        db.session.commit()
        assert h.id is not None
        assert h.name == "Гром"
        # cleanup
        db.session.delete(h)
        db.session.delete(b)
        db.session.commit()


def test_rider_default_balance_zero(app):
    from server import db, Rider
    with app.app_context():
        r = Rider(name="Иван", lastname="Иванов", phone="+79991234567")
        db.session.add(r)
        db.session.commit()
        assert r.subscription_balance == 0
        assert r.rental_balance == 0
        # cleanup
        db.session.delete(r)
        db.session.commit()


def test_service_create(app):
    from server import db, Service
    with app.app_context():
        s = Service(name="Тестовая услуга", duration=60, price=2000,
                    type="individual", limit=1, notes="")
        db.session.add(s)
        db.session.commit()
        assert s.id is not None
        # cleanup
        db.session.delete(s)
        db.session.commit()


def test_workout_create(app):
    from server import db, Workout, Trainer, Service
    with app.app_context():
        t = Trainer(name="Тестовый", lastname="Тренер")
        s = Service(name="Тестовая", duration=60, price=2000, type="individual", limit=1)
        db.session.add(t)
        db.session.add(s)
        db.session.commit()

        w = Workout(datetime_start=dt.datetime(2025, 5, 20, 12, 0),
                    idtrainer=t.id, idservice=s.id, status="planned")
        db.session.add(w)
        db.session.commit()
        assert w.id is not None
        # cleanup
        db.session.delete(w)
        db.session.delete(t)
        db.session.delete(s)
        db.session.commit()
