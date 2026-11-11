"""Métricas y estadísticas de retención y progreso FSRS."""

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any

from aulento.db.cuenta import exigir_cuenta

_REPASOS_DE_LA_CUENTA = "fsrs_review_logs l JOIN fsrs_items i ON i.id = l.card_id WHERE i.user_id = ?"


def calculate_retention_rate(conn: sqlite3.Connection, user_id: int) -> float:
    """Calcula el porcentaje histórico de respuestas recordadas (Good y Easy sobre Total) de una cuenta."""
    exigir_cuenta(user_id)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT count(*) as total, sum(CASE WHEN l.rating IN (3, 4) THEN 1 ELSE 0 END) as remembered "
        f"FROM {_REPASOS_DE_LA_CUENTA};",
        (user_id,),
    )
    row = cursor.fetchone()
    total = row["total"] or 0
    remembered = row["remembered"] or 0
    if total == 0:
        return 0.0
    return round((remembered / total) * 100.0, 1)


def calculate_streak(conn: sqlite3.Connection, user_id: int, now_utc: datetime | None = None) -> int:
    """Calcula la racha de días consecutivos de estudio de una cuenta hasta hoy."""
    exigir_cuenta(user_id)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT DISTINCT date(l.review_datetime) as r_date FROM {_REPASOS_DE_LA_CUENTA} ORDER BY r_date DESC;",
        (user_id,),
    )
    dates = [row["r_date"] for row in cursor.fetchall()]
    if not dates:
        return 0

    today_str = now_utc.strftime("%Y-%m-%d")
    yesterday_str = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")

    # Si no se repasó hoy ni ayer, la racha es 0
    if dates[0] not in (today_str, yesterday_str):
        return 0

    streak = 1
    current = datetime.strptime(dates[0], "%Y-%m-%d").date()
    for d_str in dates[1:]:
        d_date = datetime.strptime(d_str, "%Y-%m-%d").date()
        if d_date == current - timedelta(days=1):
            streak += 1
            current = d_date
        else:
            break
    return streak


def get_full_fsrs_stats(conn: sqlite3.Connection, user_id: int, now_utc: datetime | None = None) -> dict[str, Any]:
    """Retorna un consolidado completo de métricas FSRS de una cuenta."""
    exigir_cuenta(user_id)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    cursor = conn.cursor()
    cursor.execute("SELECT count(*) as total FROM fsrs_items WHERE user_id = ?;", (user_id,))
    total = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT count(*) as due_today FROM fsrs_items WHERE user_id = ? AND (due IS NULL OR due <= ?);",
        (user_id, now_iso),
    )
    due_today = cursor.fetchone()["due_today"]

    cursor.execute("SELECT state, count(*) as count FROM fsrs_items WHERE user_id = ? GROUP BY state;", (user_id,))
    by_state = {row["state"]: row["count"] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT categoria, count(*) as count FROM fsrs_items WHERE user_id = ? GROUP BY categoria;", (user_id,)
    )
    by_cat = {row["categoria"]: row["count"] for row in cursor.fetchall()}

    cursor.execute(f"SELECT count(*) as total_reviews FROM {_REPASOS_DE_LA_CUENTA};", (user_id,))
    total_reviews = cursor.fetchone()["total_reviews"]

    retention_rate = calculate_retention_rate(conn, user_id)
    streak = calculate_streak(conn, user_id, now_utc)

    return {
        "total_cards": total,
        "due_today": due_today,
        "new": by_state.get(0, 0),
        "learning": by_state.get(1, 0),
        "review": by_state.get(2, 0),
        "relearning": by_state.get(3, 0),
        "total_reviews": total_reviews,
        "retention_rate": retention_rate,
        "streak_days": streak,
        "categories": by_cat,
    }
