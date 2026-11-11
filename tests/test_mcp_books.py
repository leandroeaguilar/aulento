"""Tests para las herramientas MCP de seguimiento de lectura de libros por páginas y capítulos."""

import sqlite3

import pytest
from conftest import cuenta_en
from mcp.server.mcpserver import MCPServer

from aulento.db.repository import LibroRepository
from aulento.db.schema import create_schema
from aulento.mcp.tools_books import register_book_tools
from aulento.models.libro import EstadoLibro, LibroCreate


@pytest.fixture
def test_books_db(tmp_path, operar_por_mcp):
    db_file = tmp_path / "test_books.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    cuenta = operar_por_mcp(cuenta_en(db_file))
    repo = LibroRepository(conn, cuenta)

    libro = repo.create(LibroCreate(
        titulo="Designing Data-Intensive Applications",
        capitulo_actual=1,
        total_capitulos=12,
        pagina_actual=50,
        total_paginas=550,
        estado=EstadoLibro.LEYENDO,
    ))
    conn.close()
    return db_file, libro.id


@pytest.mark.anyio
async def test_study_list_books(test_books_db):
    db_file, _libro_id = test_books_db
    server = MCPServer(name="test-server")
    register_book_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_list_books", {"status": "all"})
    text = res.content[0].text
    assert "Designing Data-Intensive Applications" in text
    assert "Pág. 50/550" in text
    assert "Cap. 1/12" in text
    assert "9.1%" in text  # 50/550 * 100 = 9.09% -> 9.1%


@pytest.mark.anyio
async def test_study_update_book_progress_by_pages(test_books_db):
    db_file, _libro_id = test_books_db
    server = MCPServer(name="test-server")
    register_book_tools(server, read_only=False, db_path=db_file)

    # Actualizar avance por página a 275 páginas (50%)
    res = await server.call_tool("study_update_book_progress", {
        "book_identifier": "Designing Data-Intensive",
        "current_page": 275,
        "current_chapter": 6,
    })
    text = res.content[0].text
    assert "275/550" in text
    assert "50.0%" in text
    assert "Cap. 6/12" in text


@pytest.mark.anyio
async def test_study_update_book_auto_completion(test_books_db):
    db_file, libro_id = test_books_db
    server = MCPServer(name="test-server")
    register_book_tools(server, read_only=False, db_path=db_file)

    # Llegar a la página final (550) -> Auto completado
    res = await server.call_tool("study_update_book_progress", {
        "book_identifier": str(libro_id),
        "current_page": 550,
    })
    text = res.content[0].text
    assert "100.0%" in text
    assert "completado" in text


@pytest.mark.anyio
async def test_study_add_book(test_books_db):
    db_file, _ = test_books_db
    server = MCPServer(name="test-server")
    register_book_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_add_book", {
        "title": "Building Microservices 2nd Edition",
        "total_pages": 612,
        "total_chapters": 16,
        "current_page": 30,
        "current_chapter": 2,
    })
    text = res.content[0].text
    assert "Building Microservices" in text
    assert "30/612" in text
    assert "4.9%" in text  # 30/612 = 4.9%



@pytest.mark.anyio
async def test_study_sync_google_books(test_books_db):
    db_file, _ = test_books_db
    server = MCPServer(name="test-server")
    register_book_tools(server, read_only=False, db_path=db_file)

    # Sin autorización previa
    res = await server.call_tool("study_sync_google_books", {})
    text = res.content[0].text
    assert "Google Play Libros no está vinculado" in text
