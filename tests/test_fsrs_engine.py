"""Pruebas del motor FSRSEngine y cálculo de curva de olvido."""

import pytest
from datetime import datetime, timezone, timedelta
from conftest import cuenta_de_prueba
from aulento.db.fsrs_repository import FSRSRepository
from aulento.fsrs.engine import FSRSEngine
from aulento.models.fsrs_card import FSRSCardCreate, FSRSRating, FSRSState


def test_fsrs_engine_initial_review_good(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    engine = FSRSEngine(repo)

    c = repo.create_card(
        FSRSCardCreate(
            categoria="cloud_ia",
            item_pregunta="¿Cómo decir 'mitigar alucinaciones'?",
            respuesta_esperada="mitigate hallucinations",
            contexto_uso="We use ground truth and prompt guardrails to mitigate hallucinations.",
        )
    )

    now = datetime.now(timezone.utc)
    card, log = engine.review(c.id, FSRSRating.GOOD, review_time=now)

    assert card.stability is not None
    assert card.stability > 0.0
    assert card.difficulty is not None
    assert card.reps == 1
    assert log.rating == 3
    assert log.card_id == c.id


def test_fsrs_engine_again_resets_or_steps(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    engine = FSRSEngine(repo)

    c = repo.create_card(
        FSRSCardCreate(
            categoria="bi_analytics",
            item_pregunta="¿Cómo decir 'análisis detallado'?",
            respuesta_esperada="drill-down analysis",
        )
    )

    now = datetime.now(timezone.utc)
    # Primera revisión con Good
    card1, _ = engine.review(c.id, FSRSRating.GOOD, review_time=now)
    # Segunda revisión con Again
    card2, log2 = engine.review(c.id, FSRSRating.AGAIN, review_time=now + timedelta(days=2))

    assert card2.reps == 2
    assert log2.rating == 1
