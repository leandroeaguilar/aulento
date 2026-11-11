"""Pruebas unitarias para el asesor de evolución pedagógica y nivel adaptativo FSRS con Gemini."""

import sqlite3
import pytest
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba
from ia_falsa import instalar_red_de_ia
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.db.connection import get_connection
from aulento.db.fsrs_repository import FSRSRepository
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.fsrs.evolution_advisor import (
    diagnose_evolution,
    get_student_evolution_metrics,
)
from aulento.web.app import app

client = TestClient(app)


@pytest.fixture
def seeded_db():
    conn = get_connection(":memory:")
    from aulento.db.schema import create_schema
    create_schema(conn)
    seed_fsrs_deck(conn, administrador_de_prueba(conn).id)
    return conn


def test_student_evolution_metrics_fresh_deck(seeded_db):
    """Verifica que las métricas iniciales arrojen un diagnóstico de nivel A1/A2 coherente."""
    metrics = get_student_evolution_metrics(seeded_db, administrador_de_prueba(seeded_db).id)
    assert "breakdown" in metrics
    assert len(metrics["breakdown"]) == 5
    assert metrics["global_mastery"] == 0
    assert metrics["cefr_rating"] in ("A1", "A2")
    assert metrics["total_cards"] > 0
    assert metrics["recommended_level"] == "a1_foundations"


DIAGNOSTICO_DE_LA_IA = (
    '{"diagnostic_summary": "Excelente base técnica. Estás listo para B1.", '
    '"strengths": ["Vocabulario operativo A1/A2"], '
    '"focus_areas": ["Storytelling de métricas B1"], '
    '"next_milestone": "Completar 10 repasos en B1", '
    '"recommended_level": "b1_data_storytelling"}'
)
CLAVE = "AIzaSyMockKeyForEvolution"


def test_diagnose_evolution_local_heuristic(seeded_db, monkeypatch):
    """Sin clave de IA en la cuenta el diagnóstico es el heurístico local, sin ningún pedido a la red."""
    red = instalar_red_de_ia(monkeypatch)

    diag = diagnose_evolution(seeded_db, administrador_de_prueba(seeded_db).id)

    assert red.pedidos == []
    assert diag.cefr_rating in ("A1", "A2")
    assert diag.mastery_score == 0
    assert (diag.model_used, diag.provider_used, diag.motivo_sin_ia) == ("local-heuristic", None, None)
    assert len(diag.strengths) > 0
    assert len(diag.focus_areas) > 0
    assert len(diag.level_breakdown) == 5


def test_diagnose_evolution_with_gemini_mock(seeded_db, monkeypatch):
    """Con clave, el diagnóstico es el que devuelve la IA de la cuenta y dice qué modelo y proveedor respondieron."""
    red = instalar_red_de_ia(monkeypatch)
    red.texto = DIAGNOSTICO_DE_LA_IA
    cuenta = administrador_de_prueba(seeded_db).id
    PasarelaDeIA(seeded_db, cuenta).guardar_clave("gemini", CLAVE)

    diag = diagnose_evolution(seeded_db, cuenta)

    assert red.claves() == [CLAVE]
    assert red.pedidos[0].cuerpo["generationConfig"] == {"responseMimeType": "application/json", "temperature": 0.2}
    assert diag.recommended_level == "b1_data_storytelling"
    assert "B1" in diag.diagnostic_summary
    assert (diag.model_used, diag.provider_used, diag.motivo_sin_ia) == ("gemini-flash-lite-latest", "gemini", None)


def test_diagnose_evolution_dice_por_que_no_hubo_ia(seeded_db, monkeypatch):
    """Con la cuota agotada el diagnóstico es el local y lleva el motivo, sin el texto crudo del proveedor."""
    red = instalar_red_de_ia(monkeypatch)
    red.estado_por_clave = {CLAVE: 429}
    cuenta = administrador_de_prueba(seeded_db).id
    PasarelaDeIA(seeded_db, cuenta).guardar_clave("gemini", CLAVE)

    diag = diagnose_evolution(seeded_db, cuenta)

    assert red.pedidos != []
    assert (diag.model_used, diag.provider_used) == ("local-heuristic", None)
    assert "agotó su cuota" in diag.motivo_sin_ia
    assert CLAVE not in diag.motivo_sin_ia and "TEXTO-CRUDO" not in diag.motivo_sin_ia


def test_api_evolution_endpoints(seeded_db):
    """Verifica los endpoints REST /api/fsrs/evolution/status y /diagnose."""
    from aulento.web.dependencies import get_db_connection
    app.dependency_overrides[get_db_connection] = lambda: seeded_db

    try:
        # 1. GET status
        res_status = client.get("/api/fsrs/evolution/status")
        assert res_status.status_code == 200
        data_status = res_status.json()
        assert "breakdown" in data_status
        assert "global_mastery" in data_status

        # 2. POST diagnose
        res_diag = client.post("/api/fsrs/evolution/diagnose")
        assert res_diag.status_code == 200
        data_diag = res_diag.json()
        assert "cefr_rating" in data_diag
        assert "diagnostic_summary" in data_diag
        assert "recommended_level" in data_diag
    finally:
        app.dependency_overrides.clear()


def test_repository_get_due_cards_adaptive(seeded_db):
    """Verifica que el repositorio entregue una mezcla adaptativa cuando level='adaptive'."""
    repo = FSRSRepository(seeded_db, administrador_de_prueba(seeded_db).id)
    cards = repo.get_due_cards(limit=10, level="adaptive")
    assert len(cards) > 0
    assert len(cards) <= 10
    # Comprobar que no hay duplicados
    ids = [c.id for c in cards]
    assert len(ids) == len(set(ids))
