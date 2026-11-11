"""Tests para el Programa Progresivo de Inglés (A1 -> C1) y Simulador de Consultoría IA (Feature 009)."""

import pytest
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba, cuenta_de_prueba, cuenta_en
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.db.fsrs_repository import FSRSRepository
from aulento.models.fsrs_card import FSRSCardCreate
from aulento.fsrs.progressive_deck import (
    LEVEL_METADATA,
    get_all_progressive_items,
    filter_items_by_level,
)
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.fsrs.consulting_sim import (
    ConsultingSimulator,
    ConsultingSubmission,
    ConsultingFeedback,
)
from aulento.web.app import create_app
from aulento.cli.app import cli


cli_runner = CliRunner()


def test_fsrs_progressive_deck_metadata_and_filtering():
    """Valida la taxonomía de los 5 niveles progresivos y filtros de colección."""
    assert len(LEVEL_METADATA) == 5
    expected_levels = ["a1_foundations", "a2_daily_work", "b1_data_storytelling", "b2_tech_data_ai", "c1_consulting_ai"]
    for lvl in expected_levels:
        assert lvl in LEVEL_METADATA
        assert LEVEL_METADATA[lvl]["code"] in ["a1", "a2", "b1", "b2", "c1"]
        assert len(LEVEL_METADATA[lvl]["name"]) > 0

    all_items = get_all_progressive_items()
    assert len(all_items) >= 50

    a1_items = filter_items_by_level("a1")
    assert len(a1_items) > 0
    assert all(item["categoria"] == "a1_foundations" for item in a1_items)

    c1_items = filter_items_by_level("c1_consulting_ai")
    assert len(c1_items) > 0
    assert all(item["categoria"] == "c1_consulting_ai" for item in c1_items)


def test_fsrs_repository_level_filtering(memory_db):
    """Verifica que el repositorio FSRS filtre correctamente las tarjetas por nivel."""
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)

    # Crear tarjetas de diferentes niveles
    c_a1 = repo.create_card(
        FSRSCardCreate(
            categoria="a1_foundations",
            item_pregunta="¿Cómo decir 'Hola, ¿cómo estás?'?",
            respuesta_esperada="Hello, how are you?",
        )
    )
    c_b2 = repo.create_card(
        FSRSCardCreate(
            categoria="b2_tech_data_ai",
            item_pregunta="¿Cómo decir 'deriva de esquema'?",
            respuesta_esperada="schema drift",
        )
    )
    c_c1 = repo.create_card(
        FSRSCardCreate(
            categoria="c1_consulting_ai",
            item_pregunta="¿Cómo formular 'estimación de retorno de inversión'?",
            respuesta_esperada="ROI projection and cost-benefit analysis",
        )
    )

    # Filtro por a1
    due_a1 = repo.get_due_cards(limit=10, level="a1")
    assert len(due_a1) == 1
    assert due_a1[0].id == c_a1.id

    # Filtro por c1
    due_c1 = repo.get_due_cards(limit=10, level="c1")
    assert len(due_c1) == 1
    assert due_c1[0].id == c_c1.id

    # Sin filtro (o 'all'): deben venir las 3
    due_all = repo.get_due_cards(limit=10, level=None)
    assert len(due_all) == 3


def test_seed_fsrs_deck_idempotency_and_enrichment(memory_db):
    """Verifica que seed_fsrs_deck popule los niveles progresivos y sea idempotente."""
    # Primera siembra
    total_1 = seed_fsrs_deck(memory_db, cuenta_de_prueba(memory_db).id)
    assert total_1 >= 150  # 100 base + 50+ progresivas

    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    a1_cards = repo.get_due_cards(limit=100, level="a1")
    c1_cards = repo.get_due_cards(limit=100, level="c1")
    assert len(a1_cards) >= 10
    assert len(c1_cards) >= 10

    # Segunda siembra no debe duplicar tarjetas
    total_2 = seed_fsrs_deck(memory_db, cuenta_de_prueba(memory_db).id)
    assert total_2 == total_1


def test_consulting_simulator_engine():
    """Verifica la lógica de evaluación, scoring y pulido Krashen (i+1) del simulador."""
    sim = ConsultingSimulator()
    scenarios = sim.list_scenarios()
    assert len(scenarios) >= 4

    first = scenarios[0]
    assert sim.get_scenario(first.id) is not None
    assert sim.get_scenario("non_existent") is None

    # Respuesta sólida usando vocabulario consultivo
    submission = ConsultingSubmission(
        scenario_id=first.id,
        user_response="What is the daily transaction volume and the financial cost associated with reconciliation bottlenecks? If we implement an event-driven ledger, what ROI timeline does leadership expect?",
    )
    feedback = sim.evaluate(submission)
    assert isinstance(feedback, ConsultingFeedback)
    assert feedback.score >= 70
    assert len(feedback.krashen_correction) > 0
    assert len(feedback.consulting_tip) > 0
    assert len(feedback.recommended_model_answer) > 0

    # Respuesta corta / básica
    short_sub = ConsultingSubmission(
        scenario_id=first.id,
        user_response="How many errors do you have?",
    )
    short_feedback = sim.evaluate(short_sub)
    assert short_feedback.score <= 50


@pytest.fixture
def web_test_client(tmp_path, monkeypatch):
    """Fixture con base de datos temporal para endpoints FastAPI."""
    db_file = tmp_path / "web_progressive_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    seed_fsrs_deck(conn, administrador_de_prueba(conn).id)
    conn.close()

    app = create_app()
    return TestClient(app)


def test_rest_api_progressive_levels_and_consulting(web_test_client):
    """Valida los endpoints REST para niveles progresivos y simulador de consultoría."""
    # 1. GET /api/fsrs/levels
    res_levels = web_test_client.get("/api/fsrs/levels")
    assert res_levels.status_code == 200
    levels = res_levels.json()
    assert isinstance(levels, dict)
    assert len(levels) == 5
    assert "a1_foundations" in levels
    assert "c1_consulting_ai" in levels

    # 2. GET /api/fsrs/due con filtro por nivel
    res_due_a1 = web_test_client.get("/api/fsrs/due?level=a1&limit=5")
    assert res_due_a1.status_code == 200
    cards_a1 = res_due_a1.json()
    assert len(cards_a1) > 0
    assert all("a1" in c["categoria"] for c in cards_a1)

    # 3. GET /api/fsrs/consulting/scenarios
    res_scenarios = web_test_client.get("/api/fsrs/consulting/scenarios")
    assert res_scenarios.status_code == 200
    scenarios = res_scenarios.json()
    assert len(scenarios) >= 4

    # 4. POST /api/fsrs/consulting/evaluate
    eval_payload = {
        "scenario_id": scenarios[0]["id"],
        "user_response": "Could you break down the impact on revenue and operational turnaround time if we automate this with AI agents?",
    }
    res_eval = web_test_client.post("/api/fsrs/consulting/evaluate", json=eval_payload)
    assert res_eval.status_code == 200
    feedback = res_eval.json()
    assert feedback["score"] >= 60
    assert "krashen_correction" in feedback
    assert "recommended_model_answer" in feedback


def test_cli_progressive_commands(tmp_path, monkeypatch):
    """Valida los comandos CLI: aulento fsrs levels y study --level."""
    db_file = tmp_path / "cli_progressive_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    cuenta_en()

    # Inicializar con semillas
    cli_runner.invoke(cli, ["db", "init", "--seed"])

    # 1. fsrs levels
    res_levels = cli_runner.invoke(cli, ["fsrs", "levels"])
    assert res_levels.exit_code == 0
    assert "Programa Progresivo de Inglés" in res_levels.stdout
    assert "C1 Consulting" in res_levels.stdout

    # 2. fsrs study con --level a1
    res_study = cli_runner.invoke(
        cli,
        ["fsrs", "study", "--level", "a1", "--limit", "2", "--auto-rating", "3"],
    )
    assert res_study.exit_code == 0
    assert "Sesión de Estudio FSRS" in res_study.stdout
    assert "Nivel Filtrado: a1" in res_study.stdout
