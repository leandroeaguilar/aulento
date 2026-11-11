"""Pruebas unitarias e integrales para el motor de audio TTS y pronunciación FSRS."""

import pytest
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba
from aulento.audio.tts import TTSEngine, SpeechRequest
from aulento.web.app import app
from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.fsrs.deck_seed import seed_fsrs_deck

runner = CliRunner()
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_deck(monkeypatch, tmp_path):
    """Asegura base de datos temporal con mazo sembrado para pruebas de audio."""
    db_file = tmp_path / "test_audio.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    from aulento.db.schema import init_db
    init_db(conn)
    seed_fsrs_deck(conn, administrador_de_prueba(conn).id)
    conn.close()


def test_tts_engine_phonetics():
    """Verifica la generación de guía fonética IPA para términos técnicos."""
    engine = TTSEngine()
    guide = engine.get_phonetic_guide("to address a bottleneck")
    assert "/ˈbɒt.əl.nek/" in guide

    guide_tradeoff = engine.get_phonetic_guide("trade-off")
    assert "/ˈtreɪd.ɒf/" in guide_tradeoff


def test_tts_engine_synthesize_and_config():
    """Verifica la respuesta estructurada de síntesis y metadatos de configuración."""
    engine = TTSEngine()
    req = SpeechRequest(text="data pipeline architecture", accent="en-GB", speed=0.75)
    res = engine.synthesize(req)

    assert res.text == "data pipeline architecture"
    assert res.accent == "en-GB"
    assert res.speed == 0.75
    assert len(res.phonetic_guide) > 0

    cfg = engine.get_config()
    assert "supported_accents" in cfg
    assert "supported_speeds" in cfg
    assert 0.75 in cfg["supported_speeds"]
    assert 1.0 in cfg["supported_speeds"]
    assert 1.25 in cfg["supported_speeds"]


def test_api_audio_endpoints():
    """Verifica los endpoints REST GET /api/fsrs/audio/config y POST /api/fsrs/audio/speak."""
    # 1. Config
    res_cfg = client.get("/api/fsrs/audio/config")
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert cfg_data["listening_shadowing_supported"] is True
    assert len(cfg_data["supported_accents"]) >= 2

    # 2. Speak
    res_spk = client.post(
        "/api/fsrs/audio/speak",
        json={"text": "stakeholder alignment", "accent": "en-US", "speed": 1.0}
    )
    assert res_spk.status_code == 200
    spk_data = res_spk.json()
    assert spk_data["text"] == "stakeholder alignment"
    assert "/ˈsteɪkˌhoʊl.dɚ/" in spk_data["phonetic_guide"]


def test_cli_fsrs_speak():
    """Verifica el comando CLI aulento fsrs speak tanto con texto como con ID de tarjeta."""
    # Vocalizar frase directa
    res_txt = runner.invoke(cli, ["fsrs", "speak", "trade-off", "--accent", "en-US", "--speed", "1.0"])
    assert res_txt.exit_code == 0
    assert "Vocalización y Drills" in res_txt.stdout
    assert "trade-off" in res_txt.stdout

    # Vocalizar por ID numérico de tarjeta sembrada
    res_id = runner.invoke(cli, ["fsrs", "speak", "1", "--accent", "en-GB"])
    assert res_id.exit_code == 0
    assert "Vocalización y Drills" in res_id.stdout
