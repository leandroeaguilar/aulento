"""Tests exhaustivos para la meta-herramienta study_copilot y el motor StudyCopilotEngine."""

import sqlite3
import pytest
from pathlib import Path
from conftest import cuenta_en
from mcp.server.mcpserver import MCPServer

from aulento.db.schema import init_db
from aulento.db.repository import LibroRepository, CursoRepository
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.libro import LibroCreate, EstadoLibro
from aulento.models.curso import CursoCreate
from aulento.models.roadmap import (
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    EstadoTema,
)
from aulento.mcp.copilot import StudyCopilotEngine, register_copilot_tool
from aulento.mcp.server import create_study_mcp_server


@pytest.fixture
def copilot_test_db(tmp_path, operar_por_mcp):
    """Inicializa una base de datos de prueba completa con libros, cursos, roadmaps y FSRS."""
    db_file = tmp_path / "test_copilot.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    cuenta = operar_por_mcp(cuenta_en(db_file))

    # 1. Crear libro activo
    libro_repo = LibroRepository(conn, cuenta)
    libro_repo.create(LibroCreate(
        titulo="Designing Data-Intensive Applications",
        capitulo_actual=2,
        total_capitulos=12,
        pagina_actual=40,
        total_paginas=600,
        estado=EstadoLibro.LEYENDO,
    ))

    # 2. Crear curso
    curso_repo = CursoRepository(conn, cuenta)
    curso_repo.create(CursoCreate(
        plataforma_id=1,
        nombre_curso="BigQuery for Data Engineers",
        url_aula="https://coursera.org/learn/gcp-bigquery",
        progreso_pct=25.0,
    ))
    conn.close()

    # 3. Crear roadmap y temas
    rm_repo = RoadmapRepository(cuenta, db_file)
    rm = rm_repo.create_roadmap(RoadmapCreate(
        titulo="Ruta Data Engineer & BigQuery",
        descripcion="Especialización técnica en BigQuery",
        nivel_objetivo="Senior",
        categoria="data_ai",
        enfoque_estudio="certificacion",
        modulos=[
            RoadmapModuleCreate(
                titulo="Módulo 1: Almacenamiento y Optimización",
                orden=1,
                temas=[
                    RoadmapTopicCreate(
                        titulo="Particionado y Clustering en BigQuery",
                        orden=1,
                        estado=EstadoTema.PENDIENTE,
                    )
                ],
            )
        ],
    ))

    return db_file


def test_copilot_intent_classification(copilot_test_db):
    engine = StudyCopilotEngine(db_path=copilot_test_db)

    # Briefing
    intents = engine.classify_intents("Dame un resumen de cómo voy hoy")
    assert any(i.name == "BRIEFING" for i in intents)

    # Lectura relativa
    intents = engine.classify_intents("Hoy leí 25 páginas de Designing Data-Intensive")
    reading_intent = next(i for i in intents if i.name == "READING_UPDATE")
    assert reading_intent.parameters.get("page_delta") == 25

    # Lectura absoluta
    intents = engine.classify_intents("Voy por la página 150 del libro")
    reading_intent = next(i for i in intents if i.name == "READING_UPDATE")
    assert reading_intent.parameters.get("target_page") == 150

    # Curso
    intents = engine.classify_intents("Avancé el curso de BigQuery al 50%")
    course_intent = next(i for i in intents if i.name == "COURSE_UPDATE")
    assert course_intent.parameters.get("progress_pct") == 50.0

    # Roadmap
    intents = engine.classify_intents("¿Qué tema me toca estudiar en el roadmap?")
    assert any(i.name == "ROADMAP_QUERY" for i in intents)

    # Sesión tiempo
    intents = engine.classify_intents("Estudié 45 min hoy con pomodoro")
    schedule_intent = next(i for i in intents if i.name == "SCHEDULE_LOG")
    assert schedule_intent.parameters.get("minutes") == 45


def test_copilot_reading_update_execution(copilot_test_db):
    engine = StudyCopilotEngine(db_path=copilot_test_db)

    # Inicialmente está en la página 40 de 600
    res = engine.execute_plan("Leí 30 páginas de Designing Data-Intensive")
    assert len(res.actions_taken) > 0
    assert "Pág. 70/600" in res.actions_taken[0]
    assert "11.7%" in res.actions_taken[0]

    # Verificar en DB que la página ahora es 70
    conn = sqlite3.connect(str(copilot_test_db))
    conn.row_factory = sqlite3.Row
    libro = LibroRepository(conn, cuenta_en(copilot_test_db)).list_all()[0]
    conn.close()
    assert libro.pagina_actual == 70


def test_copilot_compound_instruction(copilot_test_db):
    engine = StudyCopilotEngine(db_path=copilot_test_db)

    # Instrucción compuesta: lectura + tiempo + consulta de roadmap
    res = engine.execute_plan(
        "Hoy leí 10 páginas de Designing Data y estudié 30 min, ¿qué tema sigue en mi ruta?"
    )
    md = res.to_markdown()

    assert "Acciones Ejecutadas" in md
    assert "Lectura actualizada" in md
    assert "Sesión registrada" in md
    assert "Particionado y Clustering en BigQuery" in md
    assert "Próxima Mejor Acción Recomendada" in md


def test_copilot_read_only_protection(copilot_test_db):
    engine = StudyCopilotEngine(db_path=copilot_test_db, read_only=True)

    res = engine.execute_plan("Leí 50 páginas del libro y estudié 60 min")
    assert len(res.warnings) >= 1
    assert any("Read-Only" in w for w in res.warnings)

    # Verificar que en base de datos NO cambió la página original (40)
    conn = sqlite3.connect(str(copilot_test_db))
    conn.row_factory = sqlite3.Row
    libro = LibroRepository(conn, cuenta_en(copilot_test_db)).list_all()[0]
    conn.close()
    assert libro.pagina_actual == 40


@pytest.mark.anyio
async def test_mcp_server_study_copilot_tool(copilot_test_db):
    server = create_study_mcp_server(read_only=False, db_path=copilot_test_db)

    res = await server.call_tool(
        "study_copilot",
        {"instruction": "Resumen de mi día y qué me toca hacer hoy"},
    )
    text = res.content[0].text
    assert "# 🧠 Aulento Copilot — Resumen de Acción" in text
    assert "Tarjetas FSRS Vencidas Hoy" in text
    assert "Libro Activo" in text
    assert "Designing Data-Intensive Applications" in text
    assert "Próxima Mejor Acción Recomendada" in text

    # Verificar registro en tabla mcp_audit_logs
    conn = sqlite3.connect(str(copilot_test_db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM mcp_audit_logs WHERE tool_name = 'study_copilot'")
    rows = cur.fetchall()
    conn.close()
    assert len(rows) >= 1
    assert rows[0]["status"] == "success"


def test_copilot_course_update_execution(copilot_test_db):
    engine = StudyCopilotEngine(db_path=copilot_test_db)

    res = engine.execute_plan("Completé el módulo del curso de BigQuery al 75%")
    assert len(res.actions_taken) >= 1
    assert "75.0%" in res.actions_taken[0]

    conn = sqlite3.connect(str(copilot_test_db))
    conn.row_factory = sqlite3.Row
    curso = CursoRepository(conn, cuenta_en(copilot_test_db)).list_all()[0]
    conn.close()
    assert curso.progreso_pct == 75.0


def test_copilot_nba_priorities(copilot_test_db):
    engine = StudyCopilotEngine(db_path=copilot_test_db)

    # 1. Cuando hay tarjetas FSRS vencidas
    nba_fsrs = engine._generate_next_best_action({
        "Tarjetas FSRS Vencidas Hoy": "8 pendientes",
        "Próximo Tema Desbloqueado": "Tema #1: BigQuery",
    })
    assert "Prioridad 1" in nba_fsrs
    assert "8 tarjetas FSRS" in nba_fsrs

    # 2. Cuando FSRS = 0 y hay tema pendiente
    nba_topic = engine._generate_next_best_action({
        "Tarjetas FSRS Vencidas Hoy": "0 pendientes",
        "Próximo Tema Desbloqueado": "Tema #1: Particionado",
    })
    assert "Prioridad 2" in nba_topic
    assert "Particionado" in nba_topic

    # 3. Cuando la ruta está al 100% y hay libro activo
    nba_book = engine._generate_next_best_action({
        "Tarjetas FSRS Vencidas Hoy": "0 pendientes",
        "Ruta Activa": "Ruta BigQuery (100% completada)",
        "Libro Activo": "Designing Data-Intensive (Pág. 70/600, 11.7%)",
    })
    assert "Prioridad 3" in nba_book
    assert "Designing Data-Intensive" in nba_book

    # 4. Cuando todo está al día
    nba_done = engine._generate_next_best_action({
        "Tarjetas FSRS Vencidas Hoy": "0 pendientes",
        "Ruta Activa": "Ruta BigQuery (100% completada)",
        "Libro Activo": "Ninguno en estado 'leyendo'",
    })
    assert "¡Estás al día!" in nba_done
