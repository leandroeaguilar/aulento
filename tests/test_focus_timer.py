"""Pruebas unitarias e integrales para el Focus Timer (Pomodoro) y registro en Obsidian."""

import pytest
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba, cuenta_en
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.db.focus_repository import FocusRepository
from aulento.models.focus_session import FocusSessionCreate
from aulento.vault.weekly_digest import WeeklyDigestExporter
from aulento.web.app import app
from aulento.cli.app import cli

runner = CliRunner()
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch, tmp_path):
    """Configura una base de datos SQLite temporal y limpia."""
    db_file = tmp_path / "test_focus.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    conn.close()


def test_focus_repository_record_and_list():
    """Verifica la persistencia y listado de sesiones reales de estudio en SQLite."""
    conn = get_connection()
    try:
        repo = FocusRepository(conn, administrador_de_prueba(conn).id)
        session_create = FocusSessionCreate(
            bloque_id=None,
            duracion_minutos=25,
            tipo="pomodoro",
            notas="Lectura de Paper de Transformers",
        )
        saved = repo.record_session(session_create)

        assert saved.id is not None
        assert saved.duracion_minutos == 25
        assert saved.tipo == "pomodoro"
        assert saved.notas == "Lectura de Paper de Transformers"
        assert saved.fecha_hora is not None

        sessions = repo.list_sessions(limit=10)
        assert len(sessions) == 1
        assert sessions[0].id == saved.id
    finally:
        conn.close()


def test_focus_repository_weekly_stats():
    """Verifica el cálculo de estadísticas semanales y de hoy por tipo."""
    conn = get_connection()
    try:
        repo = FocusRepository(conn, administrador_de_prueba(conn).id)
        repo.record_session(FocusSessionCreate(duracion_minutos=25, tipo="pomodoro"))
        repo.record_session(FocusSessionCreate(duracion_minutos=50, tipo="curso"))
        repo.record_session(FocusSessionCreate(duracion_minutos=15, tipo="ingles_fsrs"))

        stats = repo.get_weekly_stats()
        assert stats["minutos_semana"] == 90
        assert stats["horas_semana"] == 1.5
        assert stats["sesiones_semana"] == 3
        assert stats["minutos_hoy"] == 90
        assert stats["por_tipo_minutos"]["pomodoro"] == 25
        assert stats["por_tipo_minutos"]["curso"] == 50
        assert stats["por_tipo_minutos"]["ingles_fsrs"] == 15
    finally:
        conn.close()


def test_api_focus_endpoints():
    """Verifica los endpoints REST POST /api/focus/sessions, GET /api/focus/sessions y GET /api/focus/stats."""
    # 1. Crear sesión
    payload = {
        "bloque_id": None,
        "duracion_minutos": 45,
        "tipo": "lectura_libro",
        "notas": "Designing Data-Intensive Applications cap 3"
    }
    res_post = client.post("/api/focus/sessions", json=payload)
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post["duracion_minutos"] == 45
    assert data_post["tipo"] == "lectura_libro"

    # 2. Listar
    res_list = client.get("/api/focus/sessions")
    assert res_list.status_code == 200
    data_list = res_list.json()
    assert len(data_list) >= 1

    # 3. Stats
    res_stats = client.get("/api/focus/stats")
    assert res_stats.status_code == 200
    data_stats = res_stats.json()
    assert data_stats["minutos_semana"] >= 45
    assert "por_tipo_minutos" in data_stats


def test_weekly_digest_includes_focus_hours(tmp_path):
    """Verifica que el Weekly Digest de Obsidian incorpore la sección de horas de estudio y cumplimiento."""
    conn = get_connection()
    try:
        repo = FocusRepository(conn, administrador_de_prueba(conn).id)
        repo.record_session(FocusSessionCreate(duracion_minutos=60, tipo="curso"))
        repo.record_session(FocusSessionCreate(duracion_minutos=30, tipo="pomodoro"))

        exporter = WeeklyDigestExporter(administrador_de_prueba(conn).id, conn=conn, vault_path=tmp_path / "vault")
        digest = exporter.build_digest("2026-W39")

        content = digest["content"]
        assert "Horas Reales Estudiadas (Focus & Pomodoro)" in content
        assert "1.5 hrs" in content
        assert "90 min" in content

        metrics = digest["metrics"]
        assert "focus_hours" in metrics
        assert metrics["focus_hours"] == 1.5
        assert metrics["focus_sessions"] == 2
    finally:
        conn.close()


def test_cli_focus_start_and_stats():
    """Verifica la ejecución de los comandos CLI aulento focus start y aulento focus stats."""
    cuenta_en()

    # Start (con --no-wait para testing ágil)
    res_start = runner.invoke(cli, [
        "focus",
        "start",
        "--minutes", "25",
        "--tipo", "pomodoro",
        "--notas", "FastAPI testing",
        "--no-wait",
    ])
    assert res_start.exit_code == 0
    assert "Sesión de Enfoque Iniciada" in res_start.output
    assert "completada y registrada" in res_start.output

    # Stats
    res_stats = runner.invoke(cli, ["focus", "stats"])
    assert res_stats.exit_code == 0
    assert "Métricas de Estudio Real" in res_stats.output
    assert "pomodoro" in res_stats.output
