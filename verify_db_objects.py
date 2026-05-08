"""Проверка работы всех триггеров, функций, представлений и процедур
после деплоя схемы в dbproject.
Запуск:
    DATABASE_URL=postgresql://...?sslmode=require  python verify_db_objects.py
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta

from sqlalchemy import text

from server import (
    Horse,
    Rider,
    Workout,
    WorkoutParticipant,
    app,
    db,
)


PASS = "OK"
FAIL = "FAIL"


def banner(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def check(label: str, cond: bool, detail: str = "") -> bool:
    mark = PASS if cond else FAIL
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
    return cond


def test_views() -> list[bool]:
    banner("ПРЕДСТАВЛЕНИЯ (VIEWS)")
    results: list[bool] = []

    # 1. v_dashboard_stats
    row = db.session.execute(text("SELECT * FROM v_dashboard_stats")).fetchone()
    results.append(check(
        "v_dashboard_stats возвращает 3 счётчика",
        row is not None and row.riders_count > 0 and row.horses_count > 0,
        f"riders={row.riders_count}, horses={row.horses_count}, "
        f"scheduled={row.scheduled_count}",
    ))

    # 2. v_rider_active_subscriptions
    rows = db.session.execute(text("SELECT * FROM v_rider_active_subscriptions")).fetchall()
    results.append(check(
        "v_rider_active_subscriptions содержит активных всадников",
        len(rows) > 0,
        f"rows={len(rows)}",
    ))

    # 3. v_full_schedule
    rows = db.session.execute(text("SELECT * FROM v_full_schedule LIMIT 5")).fetchall()
    results.append(check(
        "v_full_schedule возвращает данные",
        len(rows) > 0,
        f"rows>={len(rows)}",
    ))

    # 4. v_available_horses (только здоровые/без статуса)
    rows = db.session.execute(text("SELECT * FROM v_available_horses")).fetchall()
    bad = db.session.execute(text(
        "SELECT COUNT(*) FROM v_available_horses "
        "WHERE \"Статус\" NOT IN ('Здорова', 'В работе (Здорова)') "
        "AND \"Статус\" IS NOT NULL"
    )).scalar()
    results.append(check(
        "v_available_horses содержит только здоровых лошадей",
        bad == 0,
        f"healthy_in_view={len(rows)}, bad={bad}",
    ))
    return results


def test_procedures() -> list[bool]:
    banner("ПРОЦЕДУРЫ (PROCEDURES)")
    results: list[bool] = []

    # 1. sp_adjust_rider_balance — пополнить +5 абонемент, потом -3, потом проверить status_text
    rider = Rider.query.first()
    assert rider is not None
    sub_before = rider.subscription_balance or 0

    db.session.execute(
        text("CALL sp_adjust_rider_balance(:rid, :amt, :tp)"),
        {"rid": rider.id, "amt": 5, "tp": "Subscription"},
    )
    db.session.commit()
    db.session.expire_all()
    rider = db.session.get(Rider, rider.id)
    sub_after = rider.subscription_balance or 0
    results.append(check(
        "sp_adjust_rider_balance(+5, Subscription) увеличил баланс",
        sub_after == sub_before + 5,
        f"{sub_before} -> {sub_after}",
    ))

    db.session.execute(
        text("CALL sp_adjust_rider_balance(:rid, :amt, :tp)"),
        {"rid": rider.id, "amt": -3, "tp": "Subscription"},
    )
    db.session.commit()
    db.session.expire_all()
    rider = db.session.get(Rider, rider.id)
    results.append(check(
        "sp_adjust_rider_balance(-3) уменьшил баланс",
        (rider.subscription_balance or 0) == sub_after - 3,
        f"-> {rider.subscription_balance}",
    ))

    # GREATEST(0, ...) защита: уход в минус не разрешён
    db.session.execute(
        text("CALL sp_adjust_rider_balance(:rid, :amt, :tp)"),
        {"rid": rider.id, "amt": -10000, "tp": "Subscription"},
    )
    db.session.commit()
    db.session.expire_all()
    rider = db.session.get(Rider, rider.id)
    results.append(check(
        "sp_adjust_rider_balance не уходит в минус",
        (rider.subscription_balance or 0) == 0,
        f"after -10000 -> {rider.subscription_balance}",
    ))

    # status_text синхронизируется
    results.append(check(
        "fn_sync_rider_status_text обновил subscription_status",
        rider.subscription_status is not None and rider.subscription_status != "",
        f"status='{rider.subscription_status}'",
    ))

    # 2. sp_cancel_workouts_by_date — отменить все тренировки конкретного будущего дня
    fut_workout = (
        Workout.query.filter(Workout.status == "Запланировано")
        .order_by(Workout.datetime_start)
        .first()
    )
    if fut_workout:
        day = fut_workout.datetime_start.date()
        before = (
            db.session.execute(
                text(
                    "SELECT COUNT(*) FROM workouts "
                    "WHERE DATE(datetime_start) = :d AND status IN "
                    "('Запланировано','Проводится')"
                ),
                {"d": day},
            ).scalar()
        )
        db.session.execute(text("CALL sp_cancel_workouts_by_date(:d)"), {"d": day})
        db.session.commit()
        after_active = (
            db.session.execute(
                text(
                    "SELECT COUNT(*) FROM workouts "
                    "WHERE DATE(datetime_start) = :d AND status IN "
                    "('Запланировано','Проводится')"
                ),
                {"d": day},
            ).scalar()
        )
        after_cancelled = (
            db.session.execute(
                text(
                    "SELECT COUNT(*) FROM workouts "
                    "WHERE DATE(datetime_start) = :d AND status = 'Отменено'"
                ),
                {"d": day},
            ).scalar()
        )
        results.append(check(
            f"sp_cancel_workouts_by_date({day}) перевёл активные в 'Отменено'",
            after_active == 0 and after_cancelled >= before,
            f"active: {before}->{after_active}, cancelled: {after_cancelled}",
        ))
    return results


def test_triggers() -> list[bool]:
    banner("ТРИГГЕРЫ (TRIGGERS)")
    results: list[bool] = []

    # 1. trg_prevent_sick_horse_booking — попытаться добавить участника с больной лошадью
    sick = Horse.query.filter(Horse.status.notin_(["Здорова", "В работе (Здорова)"])).first()
    rider = Rider.query.first()
    workout = (
        Workout.query.filter(Workout.status == "Запланировано")
        .order_by(Workout.datetime_start.desc())
        .first()
    )
    if sick is None:
        # делаем одну больную для теста
        h = Horse.query.first()
        h.status = "Больна"
        db.session.commit()
        sick = h

    if sick and rider and workout:
        try:
            db.session.execute(
                text(
                    "INSERT INTO workout_participants (idworkout, idrider, idhorse) "
                    "VALUES (:w, :r, :h)"
                ),
                {"w": workout.id, "r": rider.id, "h": sick.id},
            )
            db.session.commit()
            results.append(check(
                "trg_prevent_sick_horse_booking блокирует больную лошадь",
                False,
                f"INSERT с лошадью status='{sick.status}' прошёл — триггер НЕ сработал",
            ))
        except Exception as e:
            db.session.rollback()
            msg = str(e)
            results.append(check(
                "trg_prevent_sick_horse_booking блокирует больную лошадь",
                "Нельзя назначить" in msg or "горш" in msg or "лошад" in msg,
                f"raised: {msg.splitlines()[0][:120]}",
            ))

    # 2. trg_on_workout_complete (DEFERRED) — создать тренировку, добавить участника,
    #    обновить status='Завершено' и проверить, что баланс уменьшился ровно на 1
    healthy = Horse.query.filter(Horse.status.in_(["Здорова", "В работе (Здорова)"])).first()
    rider2 = Rider.query.filter(Rider.subscription_balance > 0).first()
    if rider2 is None:
        # пополним
        any_rider = Rider.query.first()
        db.session.execute(
            text("CALL sp_adjust_rider_balance(:rid, 3, 'Subscription')"),
            {"rid": any_rider.id},
        )
        db.session.commit()
        db.session.expire_all()
        rider2 = db.session.get(Rider, any_rider.id)

    services_row = db.session.execute(text("SELECT id FROM services LIMIT 1")).fetchone()
    trainer_row = db.session.execute(text("SELECT id FROM trainers LIMIT 1")).fetchone()

    if services_row and trainer_row and rider2 and healthy:
        sub_before = rider2.subscription_balance or 0
        # 1. Создать тренировку и сразу же завершить — единая транзакция,
        # триггер DEFERRED отработает на коммит.
        new_w = Workout(
            datetime_start=datetime.utcnow() - timedelta(hours=2),
            idtrainer=trainer_row.id,
            idservice=services_row.id,
            status="Завершено",
            notes="verify trigger",
        )
        db.session.add(new_w)
        db.session.flush()
        db.session.add(WorkoutParticipant(
            idworkout=new_w.id,
            idrider=rider2.id,
            idhorse=healthy.id,
        ))
        db.session.commit()
        db.session.expire_all()
        rider2 = db.session.get(Rider, rider2.id)
        sub_after = rider2.subscription_balance or 0
        results.append(check(
            "trg_on_workout_complete списал занятие при INSERT 'Завершено'",
            sub_after == sub_before - 1,
            f"sub: {sub_before} -> {sub_after}",
        ))

        # cleanup — удалить созданную тренировку, чтобы не мешать
        db.session.execute(
            text("DELETE FROM workout_participants WHERE idworkout = :w"),
            {"w": new_w.id},
        )
        db.session.execute(text("DELETE FROM workouts WHERE id = :w"), {"w": new_w.id})
        db.session.commit()
    return results


def test_functions() -> list[bool]:
    banner("ФУНКЦИИ (FUNCTIONS)")
    results: list[bool] = []

    # fn_auto_update_workouts: создаём 'Запланировано' в прошлом и зовём функцию,
    # ожидаем переход в 'Проводится' / 'Завершено'.
    services_row = db.session.execute(
        text("SELECT id, duration FROM services LIMIT 1")
    ).fetchone()
    trainer_row = db.session.execute(text("SELECT id FROM trainers LIMIT 1")).fetchone()
    if services_row and trainer_row:
        # Прошедшая тренировка длительностью услуги — должна стать 'Завершено'
        long_ago = Workout(
            datetime_start=datetime.utcnow() - timedelta(days=1),
            idtrainer=trainer_row.id,
            idservice=services_row.id,
            status="Запланировано",
            notes="verify fn_auto_update",
        )
        db.session.add(long_ago)
        db.session.commit()
        long_id = long_ago.id

        db.session.execute(text("SELECT fn_auto_update_workouts()"))
        db.session.commit()
        db.session.expire_all()
        new_status = db.session.execute(
            text("SELECT status FROM workouts WHERE id = :i"), {"i": long_id}
        ).scalar()
        results.append(check(
            "fn_auto_update_workouts перевёл прошедшую тренировку в 'Завершено'",
            new_status == "Завершено",
            f"status='{new_status}'",
        ))
        # cleanup
        db.session.execute(text("DELETE FROM workouts WHERE id = :i"), {"i": long_id})
        db.session.commit()

    # fn_sync_rider_status_text: вручную выставляем балансы и проверяем формат текста
    r = Rider.query.first()
    db.session.execute(
        text("UPDATE riders SET subscription_balance = 7, rental_balance = 0 WHERE id = :i"),
        {"i": r.id},
    )
    db.session.commit()
    db.session.execute(text("SELECT fn_sync_rider_status_text(:i)"), {"i": r.id})
    db.session.commit()
    db.session.expire_all()
    r = db.session.get(Rider, r.id)
    results.append(check(
        "fn_sync_rider_status_text формирует 'Абонемент (...)' при subscription>0",
        "Абонемент" in (r.subscription_status or ""),
        f"status='{r.subscription_status}'",
    ))

    db.session.execute(
        text("UPDATE riders SET subscription_balance = 0, rental_balance = 0 WHERE id = :i"),
        {"i": r.id},
    )
    db.session.commit()
    db.session.execute(text("SELECT fn_sync_rider_status_text(:i)"), {"i": r.id})
    db.session.commit()
    db.session.expire_all()
    r = db.session.get(Rider, r.id)
    results.append(check(
        "fn_sync_rider_status_text формирует 'Закончился' при нулевых балансах",
        (r.subscription_status or "").startswith("Закон"),
        f"status='{r.subscription_status}'",
    ))
    return results


def main() -> int:
    with app.app_context():
        all_results: list[bool] = []
        try:
            all_results += test_views()
            all_results += test_procedures()
            all_results += test_triggers()
            all_results += test_functions()
        except Exception:
            traceback.print_exc()
            return 2

        passed = sum(all_results)
        total = len(all_results)
        banner(f"ИТОГО: {passed}/{total}")
        return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
