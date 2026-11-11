"""Tests para las herramientas MCP de gestión de cursos externos (Hub de Plataformas)."""

import sqlite3
import pytest
from pathlib import Path
from conftest import cuenta_en
from mcp.server.mcpserver import MCPServer

from aulento.db.schema import create_schema, seed_plataformas
from aulento.db.repository import PlataformaRepository, CursoRepository
from aulento.models.plataforma import PlataformaCreate
from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
from aulento.mcp.tools_courses import register_course_tools


@pytest.fixture
def test_db(tmp_path, operar_por_mcp):
    db_file = tmp_path / "test_courses.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    cuenta = operar_por_mcp(cuenta_en(db_file))
    seed_plataformas(conn, cuenta)
    plat_repo = PlataformaRepository(conn, cuenta)
    curso_repo = CursoRepository(conn, cuenta)

    plat = plat_repo.list_all()[0]
    curso = curso_repo.create(CursoCreate(
        plataforma_id=plat.id,
        nombre_curso="Arquitectura en Google Cloud",
        url_aula="https://cloudskillsboost.google/course/gcp-architect",
        progreso_pct=25.0,
        estado=EstadoCurso.EN_CURSO,
        prioridad=PrioridadCurso.ALTA,
    ))
    conn.close()
    return db_file, curso.id


@pytest.mark.anyio
async def test_study_list_courses(test_db):
    db_file, curso_id = test_db
    server = MCPServer(name="test-server")
    register_course_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_list_courses", {"platform": "", "status": "all"})
    text = res.content[0].text
    assert "Arquitectura en Google Cloud" in text
    assert "25.0%" in text
    assert "https://cloudskillsboost.google/course/gcp-architect" in text


@pytest.mark.anyio
async def test_study_update_course_progress_by_url(test_db):
    db_file, curso_id = test_db
    server = MCPServer(name="test-server")
    register_course_tools(server, read_only=False, db_path=db_file)

    # 1. Actualizar por URL exacta
    res_url = await server.call_tool("study_update_course_progress", {
        "course_identifier": "https://cloudskillsboost.google/course/gcp-architect",
        "progreso_pct": 75.0,
    })
    text_url = res_url.content[0].text
    assert "75.0%" in text_url
    assert "Arquitectura en Google Cloud" in text_url

    # 2. Actualizar por URL parcial (slug) al 100% -> Auto-completado
    res_slug = await server.call_tool("study_update_course_progress", {
        "course_identifier": "gcp-architect",
        "progreso_pct": 100.0,
    })
    text_slug = res_slug.content[0].text
    assert "100.0%" in text_slug
    assert "completado" in text_slug


@pytest.mark.anyio
async def test_study_update_course_progress_by_name(test_db):
    db_file, curso_id = test_db
    server = MCPServer(name="test-server")
    register_course_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_update_course_progress", {
        "course_identifier": "Google Cloud",
        "progreso_pct": 50.0,
    })
    text = res.content[0].text
    assert "50.0%" in text
    assert "Curso actualizado exitosamente" in text


@pytest.mark.anyio
async def test_study_add_course(test_db):
    db_file, _ = test_db
    server = MCPServer(name="test-server")
    register_course_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_add_course", {
        "platform_name": "Anthropic Academy",
        "course_name": "Prompt Engineering Interactivo",
        "url_aula": "https://anthropic.com/courses/prompt-eng",
        "progreso_pct": 10.0,
        "prioridad": "alta",
    })
    text = res.content[0].text
    assert "Prompt Engineering Interactivo" in text
    assert "Anthropic Academy" in text

    # Verificar que aparece en el listado
    list_res = await server.call_tool("study_list_courses", {"platform": "Anthropic"})
    list_text = list_res.content[0].text
    assert "Prompt Engineering Interactivo" in list_text


@pytest.mark.anyio
async def test_un_permiso_negado_frena_el_curso_por_mcp_sin_dejar_una_plataforma_vacia(test_db):
    """062 R4/R5: por MCP rige el mismo enganche `puede()` que en la web, antes de crear la plataforma."""
    from aulento.core import permisos

    db_file, _ = test_db
    server = MCPServer(name="test-server")
    register_course_tools(server, read_only=False, db_path=db_file)

    def niega_cursos(*, user_id, accion, conn, **detalle):
        if accion == permisos.CREAR_CURSO:
            return permisos.Decision(False, "Tope de cursos de prueba.")
        return None

    conn = sqlite3.connect(db_file)
    antes = conn.execute("SELECT COUNT(*) FROM plataformas;").fetchone()[0]
    conn.close()
    permisos.registrar_permisos([niega_cursos])
    try:
        res = await server.call_tool(
            "study_add_course",
            {"platform_name": "Plataforma Nueva", "course_name": "Curso", "url_aula": "https://p.test/c"},
        )
    finally:
        permisos.desregistrar_permisos([niega_cursos])

    assert "Tope de cursos de prueba." in res.content[0].text
    conn = sqlite3.connect(db_file)
    try:
        assert conn.execute("SELECT COUNT(*) FROM plataformas;").fetchone()[0] == antes
        assert conn.execute("SELECT COUNT(*) FROM cursos_externos WHERE nombre_curso = 'Curso';").fetchone()[0] == 0
    finally:
        conn.close()
