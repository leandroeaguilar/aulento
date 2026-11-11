"""Tests para las herramientas MCP de repetición espaciada FSRS y gestión de agenda/tiempo de estudio."""

import sqlite3
import pytest
from pathlib import Path
from conftest import cuenta_en
from mcp.server.mcpserver import MCPServer

from aulento.db.schema import create_schema
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.repository import BloqueHorarioRepository
from aulento.models.fsrs_card import FSRSCardCreate
from aulento.models.horario import BloqueHorarioCreate, TipoBloque
from aulento.mcp.tools_fsrs import register_fsrs_tools
from aulento.mcp.tools_schedule import register_schedule_tools


@pytest.fixture
def test_fsrs_schedule_db(tmp_path, operar_por_mcp):
    db_file = tmp_path / "test_fsrs_schedule.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    cuenta = operar_por_mcp(cuenta_en(db_file))

    # Crear una tarjeta FSRS
    fsrs_repo = FSRSRepository(conn, cuenta)
    card = fsrs_repo.create_card(FSRSCardCreate(
        categoria="ingles_tecnico",
        item_pregunta="To align on business outcomes",
        respuesta_esperada="Alinear expectativas y objetivos de negocio medibles",
        contexto_uso="Stakeholder Management",
    ))

    # Crear un bloque horario para hoy
    import datetime
    dia_hoy = datetime.datetime.now().weekday() + 1
    bloque_repo = BloqueHorarioRepository(conn, cuenta)
    bloque_repo.create(BloqueHorarioCreate(
        dia_semana=dia_hoy,
        hora_inicio="09:00",
        hora_fin="10:30",
        tipo=TipoBloque.INGLES,
        descripcion="Sesión de active recall y shadowing de inglés técnico",
        url_acceso="https://study.local",
    ))

    conn.close()
    return db_file, card.id


@pytest.mark.anyio
async def test_mcp_fsrs_due_cards_and_review(test_fsrs_schedule_db):
    db_file, card_id = test_fsrs_schedule_db
    server = MCPServer(name="test-server")
    register_fsrs_tools(server, read_only=False, db_path=db_file)

    # 1. Obtener tarjetas
    res_due = await server.call_tool("study_get_fsrs_due_cards", {"category": "ingles_tecnico", "limit": 5})
    text_due = res_due.content[0].text
    assert "To align on business outcomes" in text_due
    assert "Stakeholder Management" in text_due

    # 2. Registrar calificación Good (3)
    res_rev = await server.call_tool("study_review_fsrs_card", {"card_id": card_id, "rating": 3})
    text_rev = res_rev.content[0].text
    assert "Good" in text_rev
    assert "Estabilidad:" in text_rev


@pytest.mark.anyio
async def test_mcp_create_flashcard(test_fsrs_schedule_db):
    db_file, _ = test_fsrs_schedule_db
    server = MCPServer(name="test-server")
    register_fsrs_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_create_flashcard", {
        "question": "Deadlock vs Livelock",
        "answer": "Deadlock es bloqueo mutuo estático; Livelock es cambio activo constante sin progreso.",
        "context": "Concurrencia Distribuida",
        "category": "software_arch",
    })
    text = res.content[0].text
    assert "Deadlock vs Livelock" in text
    assert "software_arch" in text


@pytest.mark.anyio
async def test_mcp_schedule_and_session_logging(test_fsrs_schedule_db):
    db_file, _ = test_fsrs_schedule_db
    server = MCPServer(name="test-server")
    register_schedule_tools(server, read_only=False, db_path=db_file)

    # 1. Consultar agenda de hoy
    res_sched = await server.call_tool("study_get_today_schedule", {})
    text_sched = res_sched.content[0].text
    assert "09:00 - 10:30" in text_sched
    assert "INGLES" in text_sched

    # 2. Registrar sesión de estudio de 45 minutos
    res_log = await server.call_tool("study_log_study_session", {
        "activity_type": "ingles",
        "duration_minutes": 45,
        "notes": "Drill de 20 colocaciones y shadowing de llamadas técnicas",
    })
    text_log = res_log.content[0].text
    assert "45 minutos" in text_log
    assert "INGLES" in text_log
