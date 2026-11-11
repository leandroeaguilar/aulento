"""Pruebas del servidor MCP y ejecución de herramientas académicas."""

import json
import pytest
from aulento.mcp.server import create_study_mcp_server


@pytest.mark.anyio
async def test_mcp_server_lists_all_tools():
    server = create_study_mcp_server()
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    expected_tools = {
        "materials_search",
        "materials_read",
        "study_list_roadmaps",
        "study_get_roadmap_topics",
        "study_get_topic_master_prompt",
        "study_get_topic_lesson",
        "study_create_or_update_lesson",
        "study_list_courses",
        "study_update_course_progress",
        "study_add_course",
        "study_list_books",
        "study_update_book_progress",
        "study_add_book",
        "study_get_fsrs_due_cards",
        "study_review_fsrs_card",
        "study_create_flashcard",
        "study_get_today_schedule",
        "study_log_study_session",
    }
    assert expected_tools.issubset(tool_names)
    assert not {n for n in tool_names if n.startswith(("gdrive_", "onedrive_", "cloud_"))}


@pytest.mark.anyio
async def test_mcp_server_read_only_mode():
    """Verifica que el modo read_only excluya herramientas de modificación."""
    server = create_study_mcp_server(read_only=True)
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}

    assert "study_list_roadmaps" in tool_names
    assert "study_list_courses" in tool_names
    assert "study_list_books" in tool_names

    mutating_tools = {
        "study_create_or_update_lesson",
        "study_update_course_progress",
        "study_add_course",
        "study_update_book_progress",
        "study_add_book",
        "study_review_fsrs_card",
        "study_create_flashcard",
        "study_log_study_session",
    }
    for mt in mutating_tools:
        assert mt not in tool_names


@pytest.mark.anyio
async def test_mcp_server_prompts_and_resources():
    """Verifica que las plantillas de prompts y los recursos URI estén registrados."""
    server = create_study_mcp_server()

    prompts = await server.list_prompts()
    prompt_names = {p.name for p in prompts}
    assert "crear-clase-magistral" in prompt_names
    assert "repaso-socratico-ingles" in prompt_names
    assert "resumen-semanal-estudio" in prompt_names

    resources = await server.list_resources()
    resource_uris = {r.uri for r in resources}
    assert "study://roadmaps/active" in resource_uris
    assert "study://courses/list" in resource_uris
    assert "study://books/reading" in resource_uris


def _subir(user_id: int, nombre: str, texto: str) -> dict:
    from aulento.core.materiales import AlmacenDeMateriales

    return AlmacenDeMateriales.con_conexion_propia(user_id).guardar(nombre, texto.encode("utf-8"))


@pytest.mark.anyio
async def test_mcp_server_materials_search(cuenta_mcp):
    material = _subir(cuenta_mcp, "BigQuery.md", "BigQuery separa el almacenamiento del cómputo (Dremel).")
    server = create_study_mcp_server()

    res = await server.call_tool("materials_search", {"query": "BigQuery"})

    assert not res.is_error
    text = res.content[0].text
    assert "Encontrados 1 material(es)" in text
    assert f"[{material['id']}] BigQuery.md" in text


@pytest.mark.anyio
async def test_mcp_server_materials_search_sin_coincidencias(cuenta_mcp):
    server = create_study_mcp_server()
    res = await server.call_tool("materials_search", {"query": "BigQuery"})
    assert "No se encontraron materiales" in res.content[0].text


@pytest.mark.anyio
async def test_mcp_server_materials_read_con_y_sin_consulta(cuenta_mcp):
    from materiales_de_prueba import texto_largo

    from aulento.mcp.server import MAX_CARACTERES_POR_LECTURA

    largo = texto_largo(MAX_CARACTERES_POR_LECTURA * 2, al_final="Pasaje final sobre Dremel y Colossus.")
    material = _subir(cuenta_mcp, "Largo.md", largo)
    server = create_study_mcp_server()

    con_consulta = (await server.call_tool("materials_read", {"material_id": material["id"], "query": "Dremel"})).content[0].text
    sin_consulta = (await server.call_tool("materials_read", {"material_id": material["id"]})).content[0].text

    assert "Pasaje final sobre Dremel y Colossus." in con_consulta
    assert "Pasajes sobre 'Dremel'" in con_consulta
    assert "Pasaje final" not in sin_consulta
    assert f"Primeros {MAX_CARACTERES_POR_LECTURA} de {material['caracteres']} caracteres" in sin_consulta
    assert len(sin_consulta) < MAX_CARACTERES_POR_LECTURA + 500


@pytest.mark.anyio
async def test_mcp_server_materials_read_inexistente(cuenta_mcp):
    server = create_study_mcp_server()
    res = await server.call_tool("materials_read", {"material_id": 987654})
    assert "Error: Material 987654 no encontrado." in res.content[0].text
