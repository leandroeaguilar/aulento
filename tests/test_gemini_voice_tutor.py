"""Pruebas unitarias e integrales del tutor de voz: evaluación, traducción y prueba de conexión con la IA de la cuenta."""

import base64
import json
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ia_falsa import instalar_red_de_ia
from aulento.audio.gemini_tutor import (
    GeminiEvaluationRequest,
    GeminiTutorClient,
    GeminiVoiceEvaluation,
    save_gemini_api_key,
)
from conftest import cuenta_de_prueba, cuenta_en
from aulento.cli import contexto
from aulento.cli.app import cli
from aulento.config import get_data_dir
from aulento.core.gemini_gateway import GeminiGateway
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.db.connection import get_connection
from aulento.web.app import app

runner = CliRunner()
client = TestClient(app)
CLAVE = "AIzaFakeKeyTest"


@pytest.fixture(autouse=True)
def red(monkeypatch):
    """La red de los tres proveedores sustituida: ningún test de este archivo sale a la red."""
    return instalar_red_de_ia(monkeypatch)


@pytest.fixture(autouse=True)
def clean_gemini_env(monkeypatch, tmp_path):
    """Asegura un entorno temporal limpio para pruebas de claves y almacenamiento."""
    data_dir = tmp_path / "study_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AULENTO_DATA_DIR", str(data_dir))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # La cuenta con la que la suite hace sus pedidos web: la única activa, así que también la de la CLI
    cuenta_en()
    contexto.indicar_cuenta(None)
    yield
    contexto.indicar_cuenta(None)


@pytest.fixture
def tutor_con_clave(memory_db) -> GeminiTutorClient:
    """El tutor de una cuenta que cargó su clave de Gemini."""
    cuenta = cuenta_de_prueba(memory_db).id
    PasarelaDeIA(memory_db, cuenta).guardar_clave("gemini", CLAVE)
    return GeminiTutorClient.de_cuenta(memory_db, cuenta)


@pytest.fixture
def tutor_sin_clave(memory_db) -> GeminiTutorClient:
    return GeminiTutorClient.de_cuenta(memory_db, cuenta_de_prueba(memory_db, "cuenta-sin-clave").id)


def test_resolve_and_save_gemini_key(memory_db, tmp_path, monkeypatch):
    """Verifica la persistencia de la API key de Gemini de una cuenta."""
    cuenta = cuenta_de_prueba(memory_db).id
    gemini = GeminiGateway(memory_db, cuenta)

    # 1. Sin clave
    assert gemini.get_active_api_key() is None

    # 2. Clave guardada (cifrada) en el almacén de la cuenta, no en un archivo
    assert save_gemini_api_key(memory_db, cuenta, "saved_key_abc_456") is None
    assert gemini.get_active_api_key() == "saved_key_abc_456"
    assert list(get_data_dir().glob("gemini*")) == []

    # 3. R12 (034): la variable de entorno del servidor ya no da ni pisa la clave de nadie
    monkeypatch.setenv("GEMINI_API_KEY", "env_key_xyz_789")
    assert gemini.get_active_api_key() == "saved_key_abc_456"


def test_el_tutor_exige_la_pasarela_de_una_cuenta(memory_db):
    """El tutor no se arma con una clave suelta ni con la gestión de claves de Gemini: solo con la pasarela."""
    cuenta = cuenta_de_prueba(memory_db).id
    for otra_cosa in ("AIzaSyClaveSuelta", None, GeminiGateway(memory_db, cuenta)):
        with pytest.raises(TypeError, match="pasarela de IA de la cuenta"):
            GeminiTutorClient(otra_cosa)
    assert GeminiTutorClient.de_cuenta(memory_db, cuenta).pasarela.user_id == cuenta


def test_gemini_tutor_fallback_local(tutor_sin_clave, red):
    """Verifica el fallback local heurístico ante ausencia de clave: sin pedidos y sin motivo (falta la clave)."""
    req = GeminiEvaluationRequest(
        expected_text="We need to evaluate trade-offs between latency and throughput",
        spoken_text="We need to evaluate trade-offs between latency and throughput",
        context_type="shadowing",
    )
    res = tutor_sin_clave.evaluate(req)

    assert red.pedidos == []
    assert isinstance(res, GeminiVoiceEvaluation)
    assert res.is_fallback is True
    assert (res.model_used, res.provider_used, res.motivo_sin_ia) == ("local-heuristic", None, None)
    assert res.accuracy_score >= 85
    assert res.verdict == "Excelente"
    assert "trade-off" in res.consulting_tip.lower() or "directores" in res.consulting_tip.lower()
    assert res.suggested_fsrs_rating in (3, 4)


def test_gemini_tutor_evaluate_with_text_mocked_success(tutor_con_clave, red):
    """Verifica el pedido de evaluar la transcripción y el desempaquetado de la respuesta del modelo."""
    red.texto = json.dumps({
        "spoken_text": "We need to mitigate the bottleneck in our data pipeline",
        "accuracy_score": 92,
        "verdict": "Excelente",
        "phonetic_feedback": "Excelente pronunciación de bottleneck (/bɒt.əl.nek/). Buen linking entre 'mitigate the'.",
        "consulting_tip": "Al presentar a C-Levels, utiliza un tono asertivo y destaca el impacto en costos de nube.",
        "suggested_fsrs_rating": 4,
    })
    req = GeminiEvaluationRequest(
        expected_text="We need to mitigate the bottleneck in our data pipeline",
        spoken_text="We need to mitigate the bottleneck in our data pipeline",
        context_type="discovery_call",
    )
    result = tutor_con_clave.evaluate(req)

    assert result.is_fallback is False
    assert (result.model_used, result.provider_used, result.motivo_sin_ia) == ("gemini-flash-lite-latest", "gemini", None)
    assert result.accuracy_score == 92
    assert result.verdict == "Excelente"
    assert "bottleneck" in result.phonetic_feedback
    assert "C-Levels" in result.consulting_tip
    assert result.suggested_fsrs_rating == 4

    (pedido,) = red.pedidos
    assert "?key=" not in pedido.url and CLAVE not in pedido.url
    assert pedido.cabeceras.get("x-goog-api-key") == CLAVE
    assert pedido.cuerpo["generationConfig"] == {"responseMimeType": "application/json", "temperature": 0.2}
    assert "<context>discovery_call</context>" in pedido.cuerpo["contents"][0]["parts"][0]["text"]


def test_gemini_tutor_evaluate_multimodal_audio_mocked_success(tutor_con_clave, red):
    """Verifica la evaluación multimodal: el audio viaja como adjunto, en base64, con su tipo."""
    red.texto = json.dumps({
        "spoken_text": "idempotent consumer architecture",
        "accuracy_score": 88,
        "verdict": "Excelente",
        "phonetic_feedback": "Acentuación precisa en 'idempotent' (/aɪˈdɛm.pə.tənt/).",
        "consulting_tip": "Proyecta confianza técnica en diseño de eventos distribuidos.",
        "suggested_fsrs_rating": 4,
    })
    audio = base64.b64encode(b"audio-de-prueba").decode("ascii")
    req = GeminiEvaluationRequest(expected_text="idempotent consumer architecture", audio_base64=audio, mime_type="audio/webm")
    result = tutor_con_clave.evaluate(req)

    assert result.is_fallback is False
    assert result.accuracy_score == 88
    assert result.spoken_text == "idempotent consumer architecture"
    assert "idempotent" in result.phonetic_feedback
    assert result.provider_used == "gemini"
    (pedido,) = red.pedidos
    assert pedido.cuerpo["contents"][0]["parts"][0] == {"inlineData": {"mimeType": "audio/webm", "data": audio}}


@pytest.mark.parametrize("audio", ["esto no es base64 !!", "====", "   "])
def test_un_audio_ilegible_se_evalua_en_local_y_lo_dice(tutor_con_clave, red, audio):
    req = GeminiEvaluationRequest(expected_text="idempotent consumer", spoken_text="idempotent consumer", audio_base64=audio)

    result = tutor_con_clave.evaluate(req)

    assert red.pedidos == []
    assert (result.is_fallback, result.model_used) == (True, "local-heuristic")
    assert "no se pudo leer" in result.motivo_sin_ia


def test_gemini_tutor_network_error_triggers_graceful_fallback(tutor_con_clave, red):
    """Un error HTTP 500 del proveedor conmuta al fallback sin lanzar excepción y dice el motivo."""
    red.estado_por_clave = {CLAVE: 500}
    req = GeminiEvaluationRequest(
        expected_text="Addressing scalability challenges",
        spoken_text="Addressing scalability challenges",
    )
    result = tutor_con_clave.evaluate(req)

    assert red.pedidos != []
    assert result.is_fallback is True
    assert result.model_used == "local-heuristic"
    assert result.verdict in ("Excelente", "Aceptable")
    assert "no está disponible en este momento" in result.motivo_sin_ia
    assert CLAVE not in result.motivo_sin_ia and "TEXTO-CRUDO" not in result.motivo_sin_ia


@pytest.mark.parametrize("texto", ["no es JSON", "[1, 2]", '{"accuracy_score": "muchísimo"}'])
def test_una_evaluacion_que_no_se_puede_leer_cae_al_motor_local_con_su_motivo(tutor_con_clave, red, texto):
    red.texto = texto

    result = tutor_con_clave.evaluate(GeminiEvaluationRequest(expected_text="trade-off", spoken_text="trade off"))

    assert (result.is_fallback, result.model_used, result.provider_used) == (True, "local-heuristic", None)
    assert result.motivo_sin_ia == "Gemini devolvió una evaluación que no se pudo leer."


def test_api_gemini_status_and_key_endpoints():
    """Verifica los endpoints REST GET /gemini-status y POST /gemini-key."""
    # 1. Status inicial (sin clave)
    status_res = client.get("/api/fsrs/audio/gemini-status")
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["configured"] is False
    assert data["free_tier"] is True

    # 2. Configurar clave
    set_key_res = client.post("/api/fsrs/audio/gemini-key", json={"key": "AIzaSyTestValidKey12345"})
    assert set_key_res.status_code == 200
    assert set_key_res.json()["status"] == "saved"

    # 3. Status tras guardar clave
    status_res2 = client.get("/api/fsrs/audio/gemini-status")
    assert status_res2.status_code == 200
    data2 = status_res2.json()
    assert data2["configured"] is True
    assert data2["mode"] == "gemini-1.5-flash"


def test_api_gemini_evaluate_endpoint():
    """Verifica el endpoint POST /api/fsrs/audio/gemini-evaluate."""
    payload = {
        "expected_text": "We have an SLA of four nines",
        "spoken_text": "We have an SLA of four nines",
        "context_type": "shadowing",
    }
    res = client.post("/api/fsrs/audio/gemini-evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "accuracy_score" in data
    assert "phonetic_feedback" in data
    assert "consulting_tip" in data
    assert "suggested_fsrs_rating" in data


def test_gemini_test_connection_endpoint(red):
    """Verifica el endpoint POST /api/fsrs/audio/gemini-test con y sin clave."""
    # 1. Sin clave configurada
    res = client.post("/api/fsrs/audio/gemini-test")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert "No hay API key configurada" in data["error"]

    # 2. Con clave y respuesta simulada exitosa
    conn = get_connection()
    try:
        save_gemini_api_key(conn, cuenta_en(), "AIzaSyTestKeyForPing")
    finally:
        conn.close()
    res2 = client.post("/api/fsrs/audio/gemini-test")
    assert res2.status_code == 200
    assert res2.json() == {"ok": True, "model": "gemini-flash-lite-latest", "provider": "gemini", "status": "connected"}
    assert red.claves() == ["AIzaSyTestKeyForPing"]

    # 3. Con la clave rechazada: el mensaje propio del caso, sin el texto del proveedor ni la clave
    red.estado_por_clave = {"AIzaSyTestKeyForPing": 401}
    res3 = client.post("/api/fsrs/audio/gemini-test")
    assert res3.status_code == 200
    assert res3.json() == {"ok": False, "error": "Gemini rechazó la clave de tu cuenta. Revisala o volvé a cargarla en Configuración."}


def test_cli_gemini_config_and_evaluate():
    """Verifica los comandos CLI gemini-config y gemini-evaluate."""
    # 1. Config status
    res_status = runner.invoke(cli, ["fsrs", "gemini-config", "--status"])
    assert res_status.exit_code == 0
    assert "Estado del Tutor de Voz Gemini" in res_status.output

    # 2. Set key
    res_set = runner.invoke(cli, ["fsrs", "gemini-config", "--set-key", "AIzaSyCliTestKey999"])
    assert res_set.exit_code == 0
    assert "guardada exitosamente" in res_set.output

    # 3. Evaluate CLI
    res_eval = runner.invoke(
        cli,
        [
            "fsrs",
            "gemini-evaluate",
            "--expected",
            "trade-off analysis",
            "--spoken",
            "trade-off analysis",
        ],
    )
    assert res_eval.exit_code == 0
    assert "Evaluación de Voz" in res_eval.output
    assert "Precisión Fonética" in res_eval.output
    assert "Tip de Consultoría" in res_eval.output


def test_gemini_translate_to_spanish(tutor_sin_clave, tutor_con_clave, red):
    """Verifica la traducción técnica con la IA de la cuenta y su fallback local."""
    # 1. Fallback sin clave: el texto original, sin pedidos
    sin_ia = tutor_sin_clave.translate_to_spanish("event-driven architecture")
    assert (sin_ia.texto, sin_ia.modelo, sin_ia.proveedor, sin_ia.motivo_sin_ia) == (
        "event-driven architecture",
        "local-fallback",
        None,
        None,
    )
    assert red.pedidos == []

    # 2. Con clave: la traducción del modelo, sin las comillas que la envuelven
    red.texto = "\"arquitectura guiada por eventos\""
    traduccion = tutor_con_clave.translate_to_spanish("event-driven architecture")
    assert (traduccion.texto, traduccion.modelo, traduccion.proveedor) == (
        "arquitectura guiada por eventos",
        "gemini-flash-lite-latest",
        "gemini",
    )
    (pedido,) = red.pedidos
    assert pedido.cuerpo["generationConfig"] == {"temperature": 0.1}
    assert pedido.cuerpo["contents"][0]["parts"] == [{"text": "event-driven architecture"}]

    # 3. Con la cuota agotada: el texto original y el motivo
    red.estado_por_clave = {CLAVE: 429}
    sin_cuota = tutor_con_clave.translate_to_spanish("event-driven architecture")
    assert (sin_cuota.texto, sin_cuota.modelo, sin_cuota.proveedor) == ("event-driven architecture", "local-fallback", None)
    assert "agotó su cuota" in sin_cuota.motivo_sin_ia

    # 4. Un texto vacío no se le pide a nadie
    red.vaciar()
    assert tutor_con_clave.translate_to_spanish("   ").modelo == "local-fallback"
    assert red.pedidos == []


def test_api_translate_endpoint():
    """Verifica el endpoint POST /api/fsrs/translate."""
    # 1. Endpoint con fallback
    res = client.post("/api/fsrs/translate", json={"text": "idempotent job", "target_lang": "es"})
    assert res.status_code == 200
    data = res.json()
    assert data["original_text"] == "idempotent job"
    assert "translated_text" in data
    assert "model_used" in data
