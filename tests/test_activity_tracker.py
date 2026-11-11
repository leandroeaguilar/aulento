"""Tests exhaustivos para ActivityTracker y cálculo de rachas y Heatmap de consistencia."""

import sqlite3
import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient

from conftest import cuenta_en
from aulento.db.schema import init_db
from aulento.core.activity_tracker import ActivityTracker
from aulento.web.app import create_app


@pytest.fixture
def activity_test_db(tmp_path):
    db_file = tmp_path / "test_activity.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.close()
    return str(db_file)


def test_activity_tracker_empty(activity_test_db):
    tracker = ActivityTracker(cuenta_en(activity_test_db), db_path=activity_test_db)
    res = tracker.get_heatmap(days=14)

    assert len(res.days) == 14
    for d in res.days:
        assert d.score == 0.0
        assert d.level == 0
    assert res.streak.current_streak == 0
    assert res.streak.longest_streak == 0
    assert res.streak.total_active_days == 0


def test_activity_tracker_aggregation_and_scoring(activity_test_db):
    conn = sqlite3.connect(activity_test_db)
    cursor = conn.cursor()
    today_str = date.today().isoformat()

    # 1. Sesión de estudio de 45 minutos (45 * 0.1 = 4.5 pts)
    cursor.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (cuenta_en(activity_test_db), 45, "pomodoro", f"{today_str}T15:30:00Z"),
    )
    # 2. 10 tarjetas FSRS repasadas (10 * 0.5 = 5.0 pts)
    cursor.execute(
        "INSERT INTO fsrs_items (id, user_id, item_pregunta, respuesta_esperada) VALUES (1, ?, 'P', 'R');",
        (cuenta_en(activity_test_db),),
    )
    for _ in range(10):
        cursor.execute(
            "INSERT INTO fsrs_review_logs (card_id, rating, state, review_datetime) VALUES (?, ?, ?, ?);",
            (1, 3, 2, f"{today_str}T16:00:00Z"),
        )
    conn.commit()
    conn.close()

    tracker = ActivityTracker(cuenta_en(activity_test_db), db_path=activity_test_db)
    res = tracker.get_heatmap(days=7)

    today_item = next(d for d in res.days if d.date == today_str)
    assert today_item.study_minutes == 45
    assert today_item.fsrs_reviews == 10
    # Score esperado: 4.5 + 5.0 = 9.5 pts -> Nivel 2 (5 < score <= 15)
    assert 9.0 <= today_item.score <= 10.0
    assert today_item.level == 2


def test_streak_calculation_today_and_yesterday(activity_test_db):
    conn = sqlite3.connect(activity_test_db)
    cursor = conn.cursor()
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    # Actividad hoy, ayer y anteayer
    for d in (today, yesterday, day_before):
        cursor.execute(
            "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
            (cuenta_en(activity_test_db), 25, "focus", f"{d.isoformat()}T10:00:00Z"),
        )
    conn.commit()
    conn.close()

    tracker = ActivityTracker(cuenta_en(activity_test_db), db_path=activity_test_db)
    res = tracker.get_heatmap(days=7)

    assert res.streak.current_streak == 3
    assert res.streak.longest_streak == 3
    assert res.streak.total_active_days == 3


def test_streak_grace_period_for_current_day(activity_test_db):
    conn = sqlite3.connect(activity_test_db)
    cursor = conn.cursor()
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    # Actividad solo ayer y anteayer (hoy aún no estudia)
    for d in (yesterday, day_before):
        cursor.execute(
            "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
            (cuenta_en(activity_test_db), 30, "lectura", f"{d.isoformat()}T18:00:00Z"),
        )
    conn.commit()
    conn.close()

    tracker = ActivityTracker(cuenta_en(activity_test_db), db_path=activity_test_db)
    res = tracker.get_heatmap(days=7)

    # Debe mantener la racha de 2 días activa por período de gracia diurno
    assert res.streak.current_streak == 2


def test_broken_streak(activity_test_db):
    conn = sqlite3.connect(activity_test_db)
    cursor = conn.cursor()
    today = date.today()
    three_days_ago = today - timedelta(days=3)

    # Actividad hace 3 días solamente
    cursor.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (cuenta_en(activity_test_db), 40, "focus", f"{three_days_ago.isoformat()}T14:00:00Z"),
    )
    conn.commit()
    conn.close()

    tracker = ActivityTracker(cuenta_en(activity_test_db), db_path=activity_test_db)
    res = tracker.get_heatmap(days=7)

    assert res.streak.current_streak == 0
    assert res.streak.longest_streak == 1


def test_activity_api_endpoints(activity_test_db, monkeypatch):
    monkeypatch.setenv("AULENTO_DB_PATH", activity_test_db)
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/activity/heatmap?days=30")
    assert res.status_code == 200
    data = res.json()
    assert len(data["days"]) == 30
    assert "streak" in data
    assert "current_streak" in data["streak"]

    res_st = client.get("/api/activity/streak")
    assert res_st.status_code == 200
    data_st = res_st.json()
    assert "longest_streak" in data_st
