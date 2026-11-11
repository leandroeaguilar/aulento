"""Pruebas de persistencia para FSRSRepository."""

import pytest
from datetime import datetime, timezone, timedelta
from conftest import cuenta_de_prueba
from aulento.db.fsrs_repository import FSRSRepository
from aulento.models.fsrs_card import FSRSCardCreate, FSRSRating


def test_fsrs_create_and_get_card(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    card = repo.create_card(
        FSRSCardCreate(
            categoria="data_engineering",
            item_pregunta="¿Cómo decir 'cuello de botella en el pipeline'?",
            respuesta_esperada="bottleneck in the pipeline",
            contexto_uso="We identified a severe bottleneck in the pipeline.",
        )
    )
    assert card.id > 0
    assert card.categoria == "data_engineering"
    assert card.state == 1  # Learning inicial

    fetched = repo.get_card_by_id(card.id)
    assert fetched is not None
    assert fetched.respuesta_esperada == "bottleneck in the pipeline"


def test_fsrs_due_cards_selection(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    now = datetime.now(timezone.utc)

    # Tarjeta 1: Due en el pasado (debe salir)
    c1 = repo.create_card(
        FSRSCardCreate(
            item_pregunta="Pregunta 1",
            respuesta_esperada="Respuesta 1",
        )
    )
    past_iso = (now - timedelta(hours=2)).isoformat()
    repo.update_card_fsrs(c1.id, 1, 0, 1.0, 5.0, past_iso, past_iso, 1, 0)

    # Tarjeta 2: Due en el futuro (NO debe salir)
    c2 = repo.create_card(
        FSRSCardCreate(
            item_pregunta="Pregunta 2",
            respuesta_esperada="Respuesta 2",
        )
    )
    future_iso = (now + timedelta(days=5)).isoformat()
    repo.update_card_fsrs(c2.id, 2, 0, 5.0, 3.0, future_iso, now.isoformat(), 2, 0)

    due_cards = repo.get_due_cards(limit=10, now_utc=now)
    assert len(due_cards) == 1
    assert due_cards[0].id == c1.id

    # Con force=True (práctica extra / cram), debe entregar ambas tarjetas
    extra_cards = repo.get_due_cards(limit=10, now_utc=now, force=True)
    assert len(extra_cards) == 2
    assert extra_cards[0].id == c1.id  # La vencida primero
    assert extra_cards[1].id == c2.id  # La futura después


def test_fsrs_add_review_log(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    c = repo.create_card(
        FSRSCardCreate(
            item_pregunta="Pregunta Log",
            respuesta_esperada="Respuesta Log",
        )
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    log = repo.add_review_log(c.id, int(FSRSRating.GOOD), now_iso, 0.5, 2.0, 2)
    assert log.id > 0
    assert log.card_id == c.id
    assert log.rating == 3
