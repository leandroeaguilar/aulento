"""Pruebas unitarias e integrales para reconocimiento de voz, shadowing y evaluación fonética."""

import pytest
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba
from aulento.audio.tts import (
    TTSEngine,
    PronunciationRequest,
    normalize_speech_text,
)
from aulento.web.app import app
from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.fsrs.deck_seed import seed_fsrs_deck

runner = CliRunner()
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_deck(monkeypatch, tmp_path):
    """Asegura base de datos temporal con mazo sembrado para pruebas de audio."""
    db_file = tmp_path / "test_shadowing.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    from aulento.db.schema import init_db
    init_db(conn)
    seed_fsrs_deck(conn, administrador_de_prueba(conn).id)
    conn.close()


def test_normalize_speech_text_contractions():
    """Verifica que las contracciones comunes en inglés se expandan y se normalice puntuación."""
    raw = "I'm testing, don't worry! We've seen it's working."
    norm = normalize_speech_text(raw)
    assert norm == "i am testing do not worry we have seen it is working"

    raw_contractions = "they'll shouldn't wouldn't let's"
    norm_contractions = normalize_speech_text(raw_contractions)
    assert norm_contractions == "they will should not would not let us"


def test_evaluate_pronunciation_exact_match():
    """Verifica evaluación fonética con coincidencia exacta (100%)."""
    engine = TTSEngine()
    req = PronunciationRequest(
        expected="to address a bottleneck",
        spoken="to address a bottleneck",
        accent="en-US"
    )
    result = engine.evaluate_pronunciation(req)

    assert result.accuracy_score == 100.0
    assert result.suggested_rating == 4  # Easy
    assert "Excelente" in result.verdict
    assert len(result.missing_words) == 0
    assert "/ˈbɒt.əl.nek/" in result.phonetic_guide


def test_evaluate_pronunciation_good_and_hard_match():
    """Verifica evaluación fonética con diferencias menores y omisión de palabras."""
    engine = TTSEngine()

    # Pequeña diferencia o omisión menor (Good -> 3)
    req_good = PronunciationRequest(
        expected="we need to optimize throughput and latency",
        spoken="we need to optimize throughput",
        accent="en-US"
    )
    res_good = engine.evaluate_pronunciation(req_good)
    assert 60.0 <= res_good.accuracy_score < 85.0
    assert res_good.suggested_rating in [2, 3]
    assert "latency" in res_good.missing_words

    # Gran disparidad (Again -> 1)
    req_poor = PronunciationRequest(
        expected="designing distributed consensus protocols",
        spoken="banana apple orange",
        accent="en-US"
    )
    res_poor = engine.evaluate_pronunciation(req_poor)
    assert res_poor.accuracy_score < 40.0
    assert res_poor.suggested_rating == 1
    assert "Repetir" in res_poor.verdict


def test_api_evaluate_pronunciation_endpoint():
    """Verifica el endpoint REST POST /api/fsrs/audio/evaluate-pronunciation."""
    payload = {
        "expected": "to mitigate a high-severity incident",
        "spoken": "to mitigate a high severity incident",
        "accent": "en-US"
    }
    response = client.post("/api/fsrs/audio/evaluate-pronunciation", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "accuracy_score" in data
    assert data["accuracy_score"] >= 90.0
    assert data["suggested_rating"] in [3, 4]
    assert "verdict" in data
    assert isinstance(data["missing_words"], list)


def test_cli_evaluate_pronunciation_command():
    """Verifica la invocación del comando CLI aulento fsrs evaluate-pronunciation."""
    result = runner.invoke(cli, [
        "fsrs",
        "evaluate-pronunciation",
        "--expected", "data warehouse migration",
        "--spoken", "data warehouse migration"
    ])
    assert result.exit_code == 0
    assert "Análisis de Pronunciación" in result.output
    assert "100.0%" in result.output
    assert "Easy" in result.output
