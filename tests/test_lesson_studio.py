"""Pruebas unitarias e integrales para LessonStudio (FSRS y Obsidian Vault)."""

from pathlib import Path

import pytest
from conftest import cuenta_en
from ia_falsa import ia_sustituida, respuesta_de

from aulento.db.connection import get_connection
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.db.schema import create_schema
from aulento.models.roadmap import (
    LessonPromptRequest,
    OrigenClase,
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
)
from aulento.roadmap.lesson_parser import LessonParser
from aulento.roadmap.lesson_studio import LessonStudio


@pytest.fixture
def test_setup(tmp_path):
    db_file = tmp_path / "studio.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()

    vault_dir = tmp_path / "mock_vault"
    vault_dir.mkdir(parents=True, exist_ok=True)

    repo = RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))
    studio = LessonStudio(repo=repo, vault_path=vault_dir)

    data = RoadmapCreate(
        titulo="Data Engineering GCP",
        modulos=[
            RoadmapModuleCreate(
                titulo="Streaming",
                temas=[RoadmapTopicCreate(titulo="Kafka Brokers")],
            )
        ],
    )
    created = repo.create_roadmap(data)
    topic_id = created.modulos[0].temas[0].id

    return repo, studio, topic_id, vault_dir


def test_generate_lesson_in_app(test_setup):
    repo, studio, topic_id, _ = test_setup

    with ia_sustituida(sin_clave=True):
        lesson = studio.generate_lesson_in_app(topic_id)
        assert lesson.id is not None
        assert lesson.tema_id == topic_id
        assert len(lesson.diagramas_mermaid) >= 1
        assert len(lesson.flashcards_json) >= 2
        assert "Kafka Brokers" in lesson.titulo


def test_import_external_lesson(test_setup):
    repo, studio, topic_id, _ = test_setup

    external_md = """
# Kafka Brokers & Partitions - Deep Dive

Explicación traída desde NotebookLM.

```mermaid
graph LR
    P --> B[Broker] --> C
```

```cards-fsrs
Q: ¿Qué es el Replication Factor en Kafka?
A: Número de copias que se mantienen de cada partición en distintos brokers.
```
"""
    lesson = studio.import_external_lesson(
        topic_id=topic_id,
        markdown_text=external_md,
        origen=OrigenClase.NOTEBOOKLM,
    )
    assert lesson.origen == OrigenClase.NOTEBOOKLM
    assert len(lesson.flashcards_json) == 1
    assert "Replication Factor" in lesson.flashcards_json[0]["pregunta"]


def test_export_flashcards_to_fsrs(test_setup):
    repo, studio, topic_id, _ = test_setup

    with ia_sustituida(sin_clave=True):
        lesson = studio.generate_lesson_in_app(topic_id)
        inserted = studio.export_flashcards_to_fsrs(lesson.id)
        assert inserted >= 2

        # Verificar que existen en fsrs_items
        conn = get_connection(repo.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM fsrs_items WHERE categoria LIKE 'roadmap_%';")
        count = cursor.fetchone()["c"]
        conn.close()
        assert count == inserted


def test_export_lesson_to_vault(test_setup):
    repo, studio, topic_id, vault_dir = test_setup

    with ia_sustituida(sin_clave=True):
        lesson = studio.generate_lesson_in_app(topic_id)
        file_path_str = studio.export_lesson_to_vault(lesson.id)

        file_path = Path(file_path_str)
        assert file_path.exists()
        content = file_path.read_text(encoding="utf-8")
        assert "type: ApunteCurso" in content
        assert "Data Engineering GCP" in content
        assert "Kafka Brokers" in content


# --- R12: clase de reserva construida con el perfil de la ruta ---

BANNER_RESERVA = "[!warning] Generación en Modo Reserva Local"


def _tema_de_ruta(repo, titulo_ruta, titulo_tema, metadata=None, categoria="data_ai"):
    created = repo.create_roadmap(
        RoadmapCreate(
            titulo=titulo_ruta,
            categoria=categoria,
            metadata_json=metadata or {},
            modulos=[RoadmapModuleCreate(titulo="Ética helenística", temas=[RoadmapTopicCreate(titulo=titulo_tema)])],
        )
    )
    return created.modulos[0].temas[0].id


def test_reserva_de_filosofia_usa_secciones_del_perfil_y_no_contenido_de_ingenieria(test_setup):
    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía estoica", "La dicotomía del control")

    with ia_sustituida(sin_clave=True):
        lesson = studio.generate_lesson_in_app(topic_id)

    md = lesson.contenido_markdown
    assert md.startswith("# La dicotomía del control")
    assert BANNER_RESERVA in md
    for encabezado in ["### 1. Problema y contexto", "### 3. Reconstrucción del argumento", "### 6. Pregunta de ensayo"]:
        assert encabezado in md
    for ajeno in ["```python", "```mermaid", "idempot", "Kafka", "Entrevista", "Producción", "aeropuerto"]:
        assert ajeno not in md
    assert lesson.diagramas_mermaid == []

    parsed = LessonParser.parse_markdown(md)
    assert parsed["title"] == "La dicotomía del control"
    assert len(parsed["flashcards"]) >= 2
    assert parsed["flashcards"] == lesson.flashcards_json
    assert all(c["pregunta"] and c["respuesta"] for c in parsed["flashcards"])
    assert "Ética helenística" in parsed["flashcards"][1]["respuesta"]


def test_reserva_usa_el_perfil_guardado_en_la_ruta(test_setup):
    repo, studio, _, _ = test_setup
    perfil = {
        "disciplina": "Historia del arte",
        "arquetipo": "arte_hobby",
        "rol_docente": "Curadora de museo",
        "secciones": [
            {"titulo": "Mirar la obra", "instruccion": "- Describe lo que se ve antes de interpretar."},
            {"titulo": "Contexto del taller", "instruccion": "- Ubica al artista y su taller."},
            {"titulo": "Lectura iconográfica", "instruccion": "- Interpreta los símbolos."},
        ],
        "usa_codigo": False,
        "usa_diagramas": False,
        "tipo_fuentes": "catálogos razonados",
        "flashcards_ejemplo": [],
        "origen": "editado",
    }
    topic_id = _tema_de_ruta(repo, "Barroco", "El claroscuro de Caravaggio", metadata={"perfil_pedagogico": perfil})

    with ia_sustituida(sin_clave=True):
        lesson = studio.generate_lesson_in_app(topic_id)

    md = lesson.contenido_markdown
    posiciones = [md.index(h) for h in ["### 1. Mirar la obra", "### 2. Contexto del taller", "### 3. Lectura iconográfica"]]
    assert posiciones == sorted(posiciones)
    assert "- Interpreta los símbolos." in md
    assert "### 4." not in md
    assert "Mirar la obra; Contexto del taller; Lectura iconográfica" in lesson.flashcards_json[0]["respuesta"]


def test_reserva_tecnica_conserva_banner_y_diagrama_derivado_del_perfil(test_setup):
    _, studio, topic_id, _ = test_setup

    with ia_sustituida(sin_clave=True):
        lesson = studio.generate_lesson_in_app(topic_id)

    assert BANNER_RESERVA in lesson.contenido_markdown
    assert "```python" not in lesson.contenido_markdown
    assert len(lesson.diagramas_mermaid) == 1
    assert "Conceptos Clave & Analogía Feynman" in lesson.diagramas_mermaid[0]
    assert "Kafka Brokers" in lesson.diagramas_mermaid[0]


def test_generacion_in_app_envia_prompt_sin_directivas_de_busqueda(test_setup):
    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "El método socrático")
    respuesta = respuesta_de("# El método socrático\n\nClase generada.\n\n```cards-fsrs\nQ: ¿Qué es la mayéutica?\nA: El arte de dar a luz ideas preguntando.\n```")
    with ia_sustituida(siempre=respuesta) as mock_gen:
        lesson = studio.generate_lesson_in_app(topic_id)

    enviado = mock_gen.call_args.args[0].usuario
    assert "materials_search" not in enviado
    assert "Investigación Web" not in enviado
    assert "no inventes citas" in enviado
    assert "Reconstrucción del argumento" in enviado
    assert BANNER_RESERVA not in lesson.contenido_markdown
    assert lesson.flashcards_json == [{"pregunta": "¿Qué es la mayéutica?", "respuesta": "El arte de dar a luz ideas preguntando."}]


# --- 023: generación in-app con opciones del Prompt Maestro ---

def _prompt_enviado_a_gemini(studio, topic_id, options=None):
    respuesta = respuesta_de("# El método socrático\n\nClase generada.\n\n```cards-fsrs\nQ: ¿Qué es la mayéutica?\nA: Preguntar para dar a luz ideas.\n```")
    with ia_sustituida(siempre=respuesta) as mock_gen:
        studio.generate_lesson_in_app(topic_id, options)
    return mock_gen.call_args.args[0].usuario


def test_generacion_in_app_respeta_las_opciones_de_contenido(test_setup):
    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "El método socrático")
    options = LessonPromptRequest(
        include_visuals=True,
        include_slides=True,
        include_quiz=True,
        include_glossary=True,
        depth="breve",
    )

    enviado = _prompt_enviado_a_gemini(studio, topic_id, options)

    assert "```svg" in enviado
    assert "```slides" in enviado
    assert "Autoevaluación" in enviado
    assert "Glosario y lecturas recomendadas" in enviado
    assert "entre 600 y 900 palabras" in enviado


def test_generacion_in_app_no_pide_busquedas_aunque_las_opciones_las_pidan(test_setup):
    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "El método socrático")
    options = LessonPromptRequest(
        include_materials=True,
        include_web_research=True,
        target_llm="notebooklm",
        include_fsrs_cards=False,
        include_slides=True,
    )

    enviado = _prompt_enviado_a_gemini(studio, topic_id, options)

    for directiva in ["Tus materiales en Aulento", "materials_search", "Investigación Web", "NotebookLM"]:
        assert directiva not in enviado
    assert "no inventes citas" in enviado
    assert "```cards-fsrs" in enviado
    assert enviado.index("```slides") < enviado.index("```cards-fsrs")
    # Las opciones del llamador no se alteran.
    assert options.target_llm == "notebooklm"
    assert options.sin_herramientas is False


def test_generacion_in_app_sin_opciones_no_pide_contenido_opcional(test_setup):
    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "El método socrático")

    enviado = _prompt_enviado_a_gemini(studio, topic_id)

    for ausente in ["svg", "slides", "Autoevaluación", "Glosario"]:
        assert ausente not in enviado
    assert "entre 1500 y 2500 palabras" in enviado
    assert "no inventes citas" in enviado
    assert "```cards-fsrs" in enviado


def test_generacion_fallida_no_reemplaza_una_clase_existente(test_setup):
    from aulento.roadmap.lesson_studio import ClaseNoGeneradaError

    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "El método socrático")
    studio.import_external_lesson(topic_id, "# El método socrático\n\nClase buena escrita a mano.")

    with (
        ia_sustituida(sin_clave=True),
        pytest.raises(ClaseNoGeneradaError),
    ):
        studio.generate_lesson_in_app(topic_id)

    assert "Clase buena escrita a mano." in repo.get_lesson_by_topic_id(topic_id).contenido_markdown


def test_generacion_fallida_sin_clase_previa_guarda_la_reserva(test_setup):
    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "El método socrático")

    with ia_sustituida(sin_clave=True):
        clase = studio.generate_lesson_in_app(topic_id)

    assert "Modo Reserva Local" in clase.contenido_markdown


def test_el_banner_de_reserva_dice_por_que_no_hubo_ia_y_como_obtener_la_clase():
    """Sin clave, con la IA caída o en la demo: el banner dice el caso real y ofrece clave, MCP o el Prompt Maestro."""
    from aulento.roadmap.lesson_studio import banner_de_reserva

    sin_clave = banner_de_reserva(None)
    caida = banner_de_reserva("Se agotó la cuota diaria (HTTP 429).")
    demo = banner_de_reserva(None, cuenta_compartida=True)

    for banner in (sin_clave, caida, demo):
        assert banner.startswith("> " + BANNER_RESERVA)
        assert "clave de API" in banner and "MCP" in banner and "Prompt Maestro" in banner
    assert "no hay clave de IA cargada" in sin_clave and "429" not in sin_clave
    assert "la IA no respondió" in caida and "**Motivo:** Se agotó la cuota diaria (HTTP 429)." in caida
    assert "estás en una cuenta compartida" in demo and "tu propia cuenta" in demo
    # Una demo con clave (la de las grabaciones) cuya IA falló muestra el motivo real, no "la demo no tiene IA"
    demo_con_clave = banner_de_reserva("Se agotó la cuota diaria (HTTP 429).", cuenta_compartida=True)
    assert demo_con_clave == caida


def test_en_la_demo_la_clase_de_reserva_explica_que_es_una_demo(test_setup):
    repo, _, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "La mayéutica")

    with ia_sustituida(sin_clave=True):
        clase = LessonStudio(repo=repo, cuenta_compartida=True).generate_lesson_in_app(topic_id)

    assert "Modo Reserva Local: estás en una cuenta compartida" in clase.contenido_markdown


def test_en_la_demo_no_regenerar_una_clase_lo_explica_como_demo(test_setup):
    from aulento.roadmap.lesson_studio import ClaseNoGeneradaError

    repo, studio, _, _ = test_setup
    topic_id = _tema_de_ruta(repo, "Filosofía antigua", "La ironía socrática")
    studio.import_external_lesson(topic_id, "# La ironía socrática\n\nClase de muestra.")

    with ia_sustituida(sin_clave=True), pytest.raises(ClaseNoGeneradaError) as error:
        LessonStudio(repo=repo, cuenta_compartida=True).generate_lesson_in_app(topic_id)

    assert "Estás en una cuenta compartida" in str(error.value) and "Se conservó la clase" in str(error.value)
    assert "cuota" not in str(error.value)
