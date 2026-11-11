"""Pruebas unitarias para estadísticas y métricas FSRS."""

import pytest
from datetime import datetime, timezone, timedelta
from conftest import cuenta_de_prueba
from aulento.fsrs.stats import calculate_retention_rate, calculate_streak, get_full_fsrs_stats
from aulento.db.fsrs_repository import FSRSRepository
from aulento.models.fsrs_card import FSRSCardCreate, FSRSRating


def test_fsrs_stats_empty(memory_db):
    stats = get_full_fsrs_stats(memory_db, cuenta_de_prueba(memory_db).id)
    assert stats["total_cards"] == 0
    assert stats["due_today"] == 0
    assert stats["retention_rate"] == 0.0
    assert stats["streak_days"] == 0


def test_fsrs_stats_with_reviews(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    c1 = repo.create_card(FSRSCardCreate(item_pregunta="P1", respuesta_esperada="R1"))
    c2 = repo.create_card(FSRSCardCreate(item_pregunta="P2", respuesta_esperada="R2"))

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    yesterday_iso = (now - timedelta(days=1)).isoformat()

    # Log 1: ayer (Good = 3)
    repo.add_review_log(c1.id, 3, yesterday_iso, 1.0, 3.0, 2)
    # Log 2: hoy (Good = 3)
    repo.add_review_log(c1.id, 3, now_iso, 1.0, 4.0, 2)
    # Log 3: hoy (Again = 1)
    repo.add_review_log(c2.id, 1, now_iso, 0.0, 0.1, 1)

    retention = calculate_retention_rate(memory_db, cuenta_de_prueba(memory_db).id)
    # 2 de 3 recordados = 66.7%
    assert retention == 66.7

    streak = calculate_streak(memory_db, cuenta_de_prueba(memory_db).id, now)
    assert streak == 2

    full = get_full_fsrs_stats(memory_db, cuenta_de_prueba(memory_db).id, now)
    assert full["total_cards"] == 2
    assert full["total_reviews"] == 3
    assert full["retention_rate"] == 66.7
    assert full["streak_days"] == 2
