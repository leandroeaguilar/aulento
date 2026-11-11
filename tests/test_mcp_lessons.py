"""Tests para las herramientas MCP de generación y guardado de clases magistrales."""

import sqlite3
import pytest
from pathlib import Path
from conftest import cuenta_en, vault_de_prueba
from mcp.server.mcpserver import MCPServer

from aulento.db.schema import create_schema
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import (
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    EstadoTema,
    EnfoqueEstudio,
)
from aulento.mcp.prompts import register_mcp_prompts
from aulento.mcp.tools_lessons import register_lesson_tools


@pytest.fixture
def test_roadmap_db(tmp_path, operar_por_mcp):
    db_file = tmp_path / "test_roadmap.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    conn.close()

    repo = RoadmapRepository(operar_por_mcp(cuenta_en(db_file)), db_file)
    r = repo.create_roadmap(RoadmapCreate(
        titulo="Data Engineering & AI",
        descripcion="Ruta integral de datos e IA",
        categoria="data_ai",
        nivel_objetivo="Senior",
        enfoque_estudio=EnfoqueEstudio.PROFESIONAL,
        modulos=[
            RoadmapModuleCreate(
                titulo="Almacenamiento Distribuido",
                orden=1,
                temas=[
                    RoadmapTopicCreate(
                        titulo="BigQuery Particionamiento y Clustering",
                        descripcion="Estrategias de optimización de costos y performance en BigQuery",
                        orden=1,
                    ),
                    RoadmapTopicCreate(
                        titulo="Modelado Dimensional en el Lakehouse",
                        descripcion="Esquemas estrella vs Snowflake",
                        orden=2,
                    ),
                ],
            )
        ],
    ))
    t1_id = r.modulos[0].temas[0].id
    t2_id = r.modulos[0].temas[1].id
    return db_file, r.id, t1_id, t2_id


@pytest.mark.anyio
async def test_study_list_roadmaps(test_roadmap_db):
    db_file, r_id, t1_id, _ = test_roadmap_db
    server = MCPServer(name="test-server")
    register_lesson_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_list_roadmaps", {"category": "data_ai"})
    text = res.content[0].text
    assert "Data Engineering & AI" in text
    assert "Senior" in text


@pytest.mark.anyio
async def test_study_get_roadmap_topics(test_roadmap_db):
    db_file, r_id, t1_id, _ = test_roadmap_db
    server = MCPServer(name="test-server")
    register_lesson_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_get_roadmap_topics", {"roadmap_id": r_id, "status": "all"})
    text = res.content[0].text
    assert "Almacenamiento Distribuido" in text
    assert "BigQuery Particionamiento y Clustering" in text
    assert "Sin clase generada" in text


@pytest.mark.anyio
async def test_study_get_topic_master_prompt(test_roadmap_db):
    db_file, r_id, t1_id, _ = test_roadmap_db
    server = MCPServer(name="test-server")
    register_lesson_tools(server, read_only=False, db_path=db_file)

    res = await server.call_tool("study_get_topic_master_prompt", {
        "topic_id": t1_id,
        "include_materials": True,
        "target_llm": "claude",
    })
    prompt = res.content[0].text
    assert "BigQuery Particionamiento y Clustering" in prompt
    assert "materials_search" in prompt
    assert "cards-fsrs" in prompt


@pytest.mark.anyio
async def test_study_create_or_update_lesson_with_fsrs_and_completion(test_roadmap_db, tmp_path, monkeypatch):
    db_file, r_id, t1_id, t2_id = test_roadmap_db
    vault_dir = vault_de_prueba(db_file)

    server = MCPServer(name="test-server")
    register_lesson_tools(server, read_only=False, db_path=db_file)

    markdown_lesson = """# BigQuery Particionamiento y Clustering

### 1. Conceptos Clave & Analogía Feynman
Particionar una tabla en BigQuery es como organizar un archivo físico por año y mes:
en lugar de revisar todas las carpetas del depósito, vas directo a la gaveta de 2026-09.

```mermaid
graph TD
    Query[Consulta SQL con filtro de fecha] --> PartitionFilter[Pruning de Particiones]
    PartitionFilter --> DataScan[Escaneo de 2 MB en vez de 500 GB]
```

### 2. Laboratorio Práctico en SQL
```sql
CREATE OR REPLACE TABLE `dataset.eventos_particionados`
PARTITION BY DATE(timestamp)
CLUSTER BY user_id, event_type AS
SELECT * FROM `dataset.eventos_raw`;
```

```cards-fsrs
Q: ¿Cuál es el límite máximo de particiones por tabla en Google BigQuery?
A: El límite es de 10,000 particiones por tabla.

Q: ¿En qué orden se evalúan las columnas de clustering en BigQuery?
A: En el orden exacto en que fueron especificadas en la cláusula CLUSTER BY (hasta 4 columnas).
```
"""

    res = await server.call_tool("study_create_or_update_lesson", {
        "topic_id": t1_id,
        "markdown_content": markdown_lesson,
        "sync_vault": True,
        "extract_flashcards": True,
        "mark_completed": True,
    })
    text = res.content[0].text
    assert "guardada exitosamente" in text
    assert "Tarjetas FSRS v5" in text and "2" in text
    assert "Completado" in text

    # Verificar que el tema quedó completado en la BD y el roadmap tiene 50% de avance (1 de 2 temas)
    repo = RoadmapRepository(cuenta_en(db_file), db_file)
    roadmap = repo.get_roadmap(r_id)
    assert roadmap.modulos[0].temas[0].estado == EstadoTema.COMPLETADO
    assert roadmap.progreso_pct == 50.0

    # La nota quedó en el vault de la cuenta que opera
    notas = list(vault_dir.rglob("*.md"))
    assert len(notas) == 1 and notas[0].parent.parent == vault_dir / "04 Knowledge" / "Cursos"

    # Verificar que study_get_topic_lesson recupera la clase guardada
    lesson_res = await server.call_tool("study_get_topic_lesson", {"topic_id": t1_id})
    assert "BigQuery Particionamiento y Clustering" in lesson_res.content[0].text
    assert "claude_mcp" in lesson_res.content[0].text


# --- R12: prompt MCP y Prompt Maestro neutros respecto de la disciplina ---

@pytest.mark.anyio
async def test_prompt_mcp_crear_clase_magistral_es_neutro():
    server = MCPServer(name="test-server")
    register_mcp_prompts(server)

    res = await server.get_prompt("crear-clase-magistral", {"tema_o_id": "42"})
    texto = "\n".join(m.content.text for m in res.messages)

    assert "'42'" in texto
    assert "study_get_topic_master_prompt" in texto
    assert "directivas del Prompt Maestro" in texto
    assert "cards-fsrs" in texto
    for fijo in ["Distinguished Engineer", "Mermaid", "mini-labs", "labs", "diagramas de arquitectura", "libros técnicos"]:
        assert fijo not in texto


@pytest.mark.anyio
async def test_study_get_topic_master_prompt_se_adapta_a_la_disciplina(tmp_path, operar_por_mcp):
    db_file = tmp_path / "test_filosofia.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    conn.close()
    creada = RoadmapRepository(operar_por_mcp(cuenta_en(db_file)), db_file).create_roadmap(RoadmapCreate(
        titulo="Filosofía estoica",
        modulos=[RoadmapModuleCreate(titulo="Ética", temas=[RoadmapTopicCreate(titulo="La dicotomía del control")])],
    ))

    server = MCPServer(name="test-server")
    register_lesson_tools(server, read_only=False, db_path=db_file)
    res = await server.call_tool("study_get_topic_master_prompt", {"topic_id": creada.modulos[0].temas[0].id})
    prompt = res.content[0].text

    assert "Reconstrucción del argumento" in prompt
    assert "cards-fsrs" in prompt
    for ajeno in ["Distinguished Engineer", "Mermaid", "código ejecutable", "Entrevista Técnica"]:
        assert ajeno not in prompt

    herramientas = {t.name: t for t in await server.list_tools()}
    descripcion = herramientas["study_get_topic_master_prompt"].description
    assert "perfil pedagógico" in descripcion
    assert "Mermaid" not in descripcion
    assert "Labs" not in descripcion
