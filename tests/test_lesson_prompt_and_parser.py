"""Pruebas unitarias para el constructor de Prompt Maestro y el parser de clases."""

import re

import pytest
from conftest import cuenta_en
from aulento.db.connection import get_connection
from aulento.db.schema import create_schema
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import (
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    LessonPromptRequest,
)
from aulento.roadmap.prompt_builder import LessonPromptBuilder
from aulento.roadmap.lesson_parser import LessonParser


@pytest.fixture
def repo(tmp_path):
    db_file = tmp_path / "test_prompt.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()
    return RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))


def test_build_master_prompt(repo):
    data = RoadmapCreate(
        titulo="Cloud Architecture",
        modulos=[
            RoadmapModuleCreate(
                titulo="Storage",
                temas=[RoadmapTopicCreate(titulo="Apache Iceberg Internals", descripcion="Snapshots and manifests")],
            )
        ],
    )
    created = repo.create_roadmap(data)
    topic_id = created.modulos[0].temas[0].id

    builder = LessonPromptBuilder(repo=repo)
    opts = LessonPromptRequest(
        include_materials=True,
        include_web_research=True,
        sop_style=True,
        include_fsrs_cards=True,
        target_llm="notebooklm",
    )
    res = builder.build_prompt(topic_id, opts)

    assert res.topic_title == "Apache Iceberg Internals"
    assert "Tus materiales en Aulento" in res.master_prompt
    assert "Investigación Web" in res.master_prompt
    assert "NotebookLM" in res.master_prompt
    assert "Técnica Feynman" in res.master_prompt
    assert "Mermaid" in res.master_prompt
    assert "cards-fsrs" in res.master_prompt


def test_build_master_prompt_language_domain(repo):
    data = RoadmapCreate(
        titulo="Ruta Especializada: ingles A2 (Junior)",
        modulos=[
            RoadmapModuleCreate(
                titulo="Tiempos Verbales en Contexto Laboral",
                temas=[
                    RoadmapTopicCreate(
                        titulo="Past Simple vs Present Perfect en Daily Standups",
                        descripcion="Diferencias de uso para reportar tareas completadas y bloqueos",
                    )
                ],
            )
        ],
    )
    created = repo.create_roadmap(data)
    topic_id = created.modulos[0].temas[0].id

    builder = LessonPromptBuilder(repo=repo)
    opts = LessonPromptRequest(
        include_materials=True,
        include_web_research=True,
        sop_style=True,
        include_fsrs_cards=True,
        target_llm="chatgpt",
    )
    res = builder.build_prompt(topic_id, opts)

    assert "Profesor Experto de Inglés para Profesionales" in res.master_prompt
    assert "Fonética & Pronunciación" in res.master_prompt
    assert "Pares mínimos" in res.master_prompt
    assert "Errores Comunes de Hispanohablantes" in res.master_prompt
    assert "Roleplay" in res.master_prompt
    assert "Distinguished Engineer" not in res.master_prompt
    assert "Diagrama de Arquitectura" not in res.master_prompt
    assert "cards-fsrs" in res.master_prompt


def test_build_master_prompt_business_domain(repo):
    data = RoadmapCreate(
        titulo="Product Management & Discovery",
        categoria="Negocios / Gestión",
        modulos=[
            RoadmapModuleCreate(
                titulo="Product Discovery & Metrics",
                temas=[
                    RoadmapTopicCreate(
                        titulo="Entrevistas de Usuario y Validación de Hipótesis",
                        descripcion="Framework de Mom Test y priorización",
                    )
                ],
            )
        ],
    )
    created = repo.create_roadmap(data)
    topic_id = created.modulos[0].temas[0].id

    builder = LessonPromptBuilder(repo=repo)
    opts = LessonPromptRequest()
    res = builder.build_prompt(topic_id, opts)

    assert "Principal Product Manager" in res.master_prompt
    assert "Valor de Negocio" in res.master_prompt
    assert "CAC, LTV" in res.master_prompt
    assert "Distinguished Engineer" not in res.master_prompt


def test_lesson_parser():
    sample_markdown = """
# Apache Iceberg: Arquitectura de Metadatos

### 1. Conceptos Clave & Analogía Feynman
Imagina un libro donde en vez de reescribir hojas, agregas una página al final que dice qué hojas leer.

```mermaid
graph TD
    A[Catalog] --> B[Metadata File]
    B --> C[Manifest List]
    C --> D[Manifest File]
```

### 3. Código
```python
def read_table():
    pass
```

```cards-fsrs
Q: ¿Cuál es el rol del Catalog en Apache Iceberg?
A: Almacenar el puntero atómico a la versión actual del archivo de metadatos.

Q: ¿Qué contiene un Manifest List?
A: Una lista de punteros a archivos de manifiesto con estadísticas de particiones.
```
"""
    parsed = LessonParser.parse_markdown(sample_markdown)
    assert parsed["title"] == "Apache Iceberg: Arquitectura de Metadatos"
    assert len(parsed["diagramas_mermaid"]) == 1
    assert "graph TD" in parsed["diagramas_mermaid"][0]
    assert len(parsed["flashcards"]) == 2
    assert "Catalog" in parsed["flashcards"][0]["pregunta"]
    assert "Manifest List" in parsed["flashcards"][1]["pregunta"]


def test_build_vault_note_content():
    content = LessonParser.build_vault_note_content(
        title="Apache Iceberg",
        topic_title="Iceberg Internals",
        module_title="Storage",
        roadmap_title="Data Engineer Senior",
        markdown_body="# Contenido",
    )
    assert "type: ApunteCurso" in content
    assert 'roadmap: "Data Engineer Senior"' in content
    assert "# Contenido" in content


# --- R7 / R8: Prompt Maestro en capas ---

def _ruta_psicologia(repo, metadata=None, enfoque="academico"):
    created = repo.create_roadmap(
        RoadmapCreate(
            titulo="Psicología Cognitiva",
            categoria="data_ai",
            nivel_objetivo="Inicial",
            enfoque_estudio=enfoque,
            metadata_json=metadata or {},
            modulos=[
                RoadmapModuleCreate(
                    titulo="Procesos básicos",
                    orden=1,
                    temas=[
                        RoadmapTopicCreate(titulo="Percepción visual", orden=1),
                        RoadmapTopicCreate(titulo="Atención selectiva", descripcion="Modelos de filtro", orden=2),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="Memoria",
                    orden=2,
                    temas=[RoadmapTopicCreate(titulo="Memoria de trabajo", orden=1)],
                ),
            ],
        )
    )
    temas = [t for m in created.modulos for t in m.temas]
    return created, temas


def test_prompt_de_psicologia_no_usa_el_molde_de_ingenieria(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[1].id, LessonPromptRequest()).master_prompt

    assert "evidencia empírica" in prompt
    assert "Consideraciones éticas" in prompt
    for ajeno in ["Mermaid", "código ejecutable", "Entrevista Técnica", "Distinguished Engineer", "Diagrama de Arquitectura"]:
        assert ajeno not in prompt


def test_prompt_incluye_nucleo_fijo_para_cualquier_disciplina(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[1].id, LessonPromptRequest()).master_prompt

    assert "`# Atención selectiva`" in prompt
    assert "[!tip]" in prompt
    assert "[!warning]" in prompt
    assert "Técnica Feynman" in prompt
    assert "```cards-fsrs\nQ: " in prompt
    assert "\nA: " in prompt


def test_prompt_incluye_contexto_del_tema(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[1].id, LessonPromptRequest()).master_prompt

    assert "**Módulo:** Procesos básicos" in prompt
    assert "Nivel objetivo: Inicial" in prompt
    assert "**Enfoque de estudio:** académico" in prompt
    assert "fundamentos teóricos rigurosos" in prompt
    assert "**Detalle del tema:** Modelos de filtro" in prompt
    assert "**Tema anterior en la ruta:** Percepción visual" in prompt
    assert "**Tema siguiente en la ruta:** Memoria de trabajo" in prompt


def test_prompt_en_los_extremos_de_la_ruta_omite_vecino_inexistente(repo):
    _, temas = _ruta_psicologia(repo)
    builder = LessonPromptBuilder(repo=repo)

    primero = builder.build_prompt(temas[0].id, LessonPromptRequest()).master_prompt
    assert "Tema anterior en la ruta" not in primero
    assert "**Tema siguiente en la ruta:** Atención selectiva" in primero

    ultimo = builder.build_prompt(temas[2].id, LessonPromptRequest()).master_prompt
    assert "**Tema anterior en la ruta:** Atención selectiva" in ultimo
    assert "Tema siguiente en la ruta" not in ultimo


def test_prompt_refleja_cada_enfoque_de_estudio(repo):
    _, temas = _ruta_psicologia(repo, enfoque="personal_hobby")
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[0].id, LessonPromptRequest()).master_prompt
    assert "**Enfoque de estudio:** personal" in prompt
    assert "fundamentos teóricos rigurosos" not in prompt


PERFIL_PERSONALIZADO = {
    "disciplina": "Psicología experimental",
    "arquetipo": "ciencias_sociales_salud",
    "rol_docente": "Investigadora de laboratorio,\nescéptica y didáctica",
    "secciones": [
        {"titulo": "Pregunta de investigación", "instruccion": "- Formula la pregunta que motiva el tema."},
        {"titulo": "Paradigma experimental", "instruccion": "- Describe el paradigma y sus variables."},
        {"titulo": "Resultados y tamaño del efecto", "instruccion": "- Reporta resultados con su tamaño del efecto."},
        {"titulo": "Replicaciones", "instruccion": "- Indica si el hallazgo se replicó."},
    ],
    "usa_codigo": False,
    "usa_diagramas": False,
    "tipo_fuentes": "preregistros y metaanálisis de la carpeta Laboratorio",
    "flashcards_ejemplo": [
        {"pregunta": "¿Qué es un preregistro?", "respuesta": "Un plan de análisis\npublicado antes de recolectar datos."}
    ],
    "origen": "editado",
}


def test_prompt_usa_el_perfil_guardado_con_sus_secciones_en_orden(repo):
    _, temas = _ruta_psicologia(repo, metadata={"perfil_pedagogico": PERFIL_PERSONALIZADO})
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[1].id, LessonPromptRequest()).master_prompt

    encabezados = [
        "### 1. Pregunta de investigación",
        "### 2. Paradigma experimental",
        "### 3. Resultados y tamaño del efecto",
        "### 4. Replicaciones",
        "### 5. Tarjetas de Active Recall",
    ]
    posiciones = [prompt.index(e) for e in encabezados]
    assert posiciones == sorted(posiciones)
    assert "- Describe el paradigma y sus variables." in prompt

    # Rol docente como una sola línea de tono.
    assert "**Rol y tono docente:** Actúa como Investigadora de laboratorio, escéptica y didáctica.\n" in prompt
    assert "Disciplina: Psicología experimental" in prompt
    assert "preregistros y metaanálisis de la carpeta Laboratorio" in prompt
    assert "Q: ¿Qué es un preregistro?\nA: Un plan de análisis publicado antes de recolectar datos." in prompt
    # Nada del arquetipo resuelto al vuelo se mezcla con el perfil guardado.
    assert "Evidencia empírica y estudios clásicos" not in prompt


@pytest.mark.parametrize(
    "usa_codigo, usa_diagramas",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_prompt_exige_codigo_y_diagramas_solo_si_el_perfil_los_usa(repo, usa_codigo, usa_diagramas):
    perfil = dict(PERFIL_PERSONALIZADO, usa_codigo=usa_codigo, usa_diagramas=usa_diagramas)
    _, temas = _ruta_psicologia(repo, metadata={"perfil_pedagogico": perfil})
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[0].id, LessonPromptRequest()).master_prompt

    assert ("código ejecutable" in prompt) is usa_codigo
    assert ("Mermaid" in prompt) is usa_diagramas


def test_prompt_sin_tarjetas_no_incluye_bloque_cards_fsrs(repo):
    _, temas = _ruta_psicologia(repo)
    builder = LessonPromptBuilder(repo=repo)

    sin_tarjetas = builder.build_prompt(temas[0].id, LessonPromptRequest(include_fsrs_cards=False)).master_prompt
    assert "cards-fsrs" not in sin_tarjetas
    assert "FSRS" not in sin_tarjetas
    assert "Q:" not in sin_tarjetas

    con_tarjetas = builder.build_prompt(temas[0].id, LessonPromptRequest(include_fsrs_cards=True)).master_prompt
    assert "```cards-fsrs" in con_tarjetas


def test_prompt_para_gemini_in_app_no_pide_buscar_y_prohibe_inventar_citas(repo):
    _, temas = _ruta_psicologia(repo)
    builder = LessonPromptBuilder(repo=repo)
    opts = LessonPromptRequest(
        include_materials=True, include_web_research=True, target_llm="gemini", sin_herramientas=True
    )
    prompt = builder.build_prompt(temas[0].id, opts).master_prompt

    for directiva in ["Tus materiales en Aulento", "materials_search", "Investigación Web", "NotebookLM"]:
        assert directiva not in prompt
    assert "no inventes citas" in prompt

    externo = builder.build_prompt(temas[0].id, LessonPromptRequest(target_llm="claude")).master_prompt
    assert "Tus materiales en Aulento" in externo
    assert "Investigación Web" in externo
    assert "manuales universitarios" in externo


def test_prompt_para_gemini_elegido_por_el_usuario_respeta_sus_interruptores(repo):
    # Elegir "gemini" como destino externo (Gemini Web tiene buscador) no es la generación in-app.
    _, temas = _ruta_psicologia(repo)
    opts = LessonPromptRequest(include_materials=True, include_web_research=True, target_llm="gemini")
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[0].id, opts).master_prompt
    assert "Tus materiales en Aulento" in prompt
    assert "Investigación Web" in prompt
    assert "no tienes buscador" not in prompt


def test_prompt_respeta_los_interruptores_de_fuentes(repo):
    _, temas = _ruta_psicologia(repo)
    opts = LessonPromptRequest(include_materials=False, include_web_research=False, target_llm="chatgpt")
    prompt = LessonPromptBuilder(repo=repo).build_prompt(temas[0].id, opts).master_prompt
    assert "materials_search" not in prompt
    assert "Investigación Web" not in prompt
    assert "Fuentes de Información" not in prompt


def test_prompt_de_ruta_previa_sin_perfil_resuelve_al_vuelo_sin_subcadenas(repo):
    created = repo.create_roadmap(
        RoadmapCreate(
            titulo="Streaming en AWS",
            categoria="data_engineering",
            modulos=[
                RoadmapModuleCreate(
                    titulo="Kafka",
                    temas=[RoadmapTopicCreate(titulo="Productores Idempotentes en EC2")],
                )
            ],
        )
    )
    assert "perfil_pedagogico" not in created.metadata_json
    prompt = LessonPromptBuilder(repo=repo).build_prompt(created.modulos[0].temas[0].id, LessonPromptRequest()).master_prompt

    assert "Distinguished Engineer" in prompt
    assert "Mermaid" in prompt
    assert "código ejecutable" in prompt
    assert "Principal Product Manager" not in prompt
    assert "Profesor Experto de Inglés" not in prompt


def test_build_prompt_tema_inexistente(repo):
    with pytest.raises(ValueError):
        LessonPromptBuilder(repo=repo).build_prompt(9999, LessonPromptRequest())


# --- 023: opciones de contenido del Prompt Maestro ---

def _prompt(repo, tema_id, **opciones):
    return LessonPromptBuilder(repo=repo).build_prompt(tema_id, LessonPromptRequest(**opciones)).master_prompt


def test_prompt_por_defecto_no_menciona_las_opciones_de_contenido(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = _prompt(repo, temas[1].id).lower()

    for ausente in ["svg", "slides", "diapositiva", "autoevaluación", "glosario", "repaso"]:
        assert ausente not in prompt


def test_prompt_con_figuras_pide_bloques_svg_autocontenidos(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = _prompt(repo, temas[1].id, include_visuals=True)

    assert "entre 2 y 4 figuras" in prompt
    assert "```svg" in prompt
    assert "`viewBox`" in prompt
    assert "texto legible" in prompt
    assert "sin `<script>`" in prompt
    assert "sin recursos externos" in prompt
    assert "pie de figura" in prompt
    assert "junto al concepto que ilustra" in prompt


def test_prompt_con_diapositivas_pide_bloque_slides_antes_de_las_flashcards(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = _prompt(repo, temas[1].id, include_slides=True)

    assert "```slides\n# " in prompt
    assert "6 a 10 diapositivas" in prompt
    assert "separadas por una línea `---`" in prompt
    assert "título `#`" in prompt
    assert "3 a 5 viñetas" in prompt
    assert "no anides bloques de código" in prompt
    assert "antes del bloque de flashcards" in prompt
    assert prompt.index("```slides") < prompt.index("```cards-fsrs")

    sin_tarjetas = _prompt(repo, temas[1].id, include_slides=True, include_fsrs_cards=False)
    assert "```slides" in sin_tarjetas
    assert "flashcards" not in sin_tarjetas


def test_prompt_incluye_una_indicacion_de_extension_distinta_por_profundidad(repo):
    _, temas = _ruta_psicologia(repo)
    esperado = {
        "breve": "entre 600 y 900 palabras",
        "estandar": "entre 1500 y 2500 palabras",
        "exhaustiva": "3500 palabras o más",
    }
    prompts = {depth: _prompt(repo, temas[1].id, depth=depth) for depth in esperado}

    for depth, texto in esperado.items():
        assert texto in prompts[depth]
        for otra, texto_ajeno in esperado.items():
            if otra != depth:
                assert texto_ajeno not in prompts[depth]
    assert _prompt(repo, temas[1].id) == prompts["estandar"]


def test_profundidad_desconocida_no_es_valida():
    with pytest.raises(ValueError):
        LessonPromptRequest(depth="enciclopedica")


def test_prompt_con_autoevaluacion_prohibe_los_prefijos_de_flashcards(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = _prompt(repo, temas[1].id, include_quiz=True, include_fsrs_cards=False)

    assert "Autoevaluación" in prompt
    assert "5 preguntas de opción múltiple numeradas" in prompt
    assert "`a)`, `b)`, `c)` y `d)`" in prompt
    assert "Soluciones" in prompt
    assert "no uses los prefijos" in prompt
    for prefijo in ["`Q:`", "`A:`", "`Pregunta:`", "`Respuesta:`", "`P:`", "`R:`"]:
        assert prefijo in prompt


def test_prompt_con_glosario_pide_lecturas_sin_inventar_referencias(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = _prompt(repo, temas[1].id, include_glossary=True)

    assert "Glosario y lecturas recomendadas" in prompt
    assert "términos clave" in prompt
    assert "No inventes títulos, autores ni enlaces" in prompt


def test_prompt_con_puente_repasa_el_tema_anterior_y_anticipa_el_siguiente(repo):
    _, temas = _ruta_psicologia(repo)
    prompt = _prompt(repo, temas[1].id, include_bridge=True)

    assert "Abre la clase con un repaso breve" in prompt
    assert "tema anterior, «Percepción visual»" in prompt
    assert "Cierra la clase con un párrafo «Qué sigue»" in prompt
    assert "tema siguiente, «Memoria de trabajo»" in prompt


def test_puente_omite_la_mitad_que_no_aplica_en_los_extremos(repo):
    _, temas = _ruta_psicologia(repo)

    primero = _prompt(repo, temas[0].id, include_bridge=True)
    assert "repaso breve" not in primero
    assert "tema siguiente, «Atención selectiva»" in primero

    ultimo = _prompt(repo, temas[2].id, include_bridge=True)
    assert "tema anterior, «Atención selectiva»" in ultimo
    assert "Qué sigue" not in ultimo


def test_secciones_opcionales_se_numeran_tras_el_perfil_y_fsrs_queda_ultima(repo):
    _, temas = _ruta_psicologia(repo, metadata={"perfil_pedagogico": PERFIL_PERSONALIZADO})
    prompt = _prompt(
        repo,
        temas[1].id,
        include_visuals=True,
        include_slides=True,
        include_quiz=True,
        include_glossary=True,
        include_bridge=True,
        depth="exhaustiva",
    )

    encabezados = [
        "### 1. Pregunta de investigación",
        "### 4. Replicaciones",
        "### 5. Glosario y lecturas recomendadas",
        "### 6. Autoevaluación",
        "### 7. Diapositivas de repaso",
        "### 8. Tarjetas de Active Recall",
    ]
    posiciones = [prompt.index(e) for e in encabezados]
    assert posiciones == sorted(posiciones)

    estructura = prompt[prompt.index("## Estructura Requerida de la Clase:"):]
    numeros = [int(n) for n in re.findall(r"^### (\d+)\. ", estructura, re.MULTILINE)]
    assert numeros == list(range(1, 9))
    assert estructura.rstrip().endswith("listo para ser importado al Vault de Obsidian y al motor FSRS.")
    assert estructura.index("```cards-fsrs") > estructura.index("```slides")


def test_solo_algunas_opciones_mantienen_la_numeracion_consecutiva(repo):
    _, temas = _ruta_psicologia(repo, metadata={"perfil_pedagogico": PERFIL_PERSONALIZADO})
    prompt = _prompt(repo, temas[1].id, include_quiz=True)

    assert "### 5. Autoevaluación" in prompt
    assert "### 6. Tarjetas de Active Recall" in prompt
    assert "### 7." not in prompt


QUIZ_SIN_BLOQUE_DE_TARJETAS = """# Atención selectiva

### 1. Idea central
La atención selectiva filtra estímulos.

### 5. Autoevaluación

1. ¿Qué propone el modelo de filtro temprano de Broadbent?
   a) Que todo estímulo se procesa semánticamente
   b) Que la selección ocurre antes del análisis semántico
   c) Que no existe selección
   d) Que la selección depende de la memoria a largo plazo

2. ¿Qué tarea usó Cherry para estudiar el efecto cóctel?
   a) Stroop
   b) Búsqueda visual
   c) Escucha dicótica
   d) Priming

#### Soluciones

1. b) La selección se hace por rasgos físicos, antes del significado.
2. c) En la escucha dicótica se atiende un oído y se ignora el otro.
"""


def test_quiz_con_el_formato_pedido_no_se_confunde_con_flashcards():
    parsed = LessonParser.parse_markdown(QUIZ_SIN_BLOQUE_DE_TARJETAS)
    assert parsed["flashcards"] == []

    # Control: con los prefijos prohibidos el parser de respaldo sí crea tarjetas.
    con_prefijos = QUIZ_SIN_BLOQUE_DE_TARJETAS + "\nPregunta: ¿Qué es el efecto cóctel?\nRespuesta: Oír tu nombre en el canal ignorado.\n"
    assert len(LessonParser.parse_markdown(con_prefijos)["flashcards"]) == 1


def test_figuras_se_piden_sin_hojas_de_estilo(repo):
    # El visor descarta <style> al sanear: una figura estilada con clases quedaría en negro.
    _, temas = _ruta_psicologia(repo)
    prompt = _prompt(repo, temas[1].id, include_visuals=True)
    assert "no uses `<style>` ni clases CSS" in prompt


def test_el_contexto_no_pide_puente_si_la_opcion_esta_apagada(repo):
    _, temas = _ruta_psicologia(repo)
    apagado = _prompt(repo, temas[1].id)
    assert "puente" not in apagado.lower()
    assert "Tema siguiente en la ruta" in apagado

    encendido = _prompt(repo, temas[1].id, include_bridge=True)
    assert "Qué sigue" in encendido


def test_el_titulo_de_la_clase_no_sale_de_las_diapositivas():
    markdown = (
        "Introducción sin encabezado de primer nivel.\n\n"
        "## Desarrollo\n\nTexto.\n\n"
        "```slides\n# Primera diapositiva\n- punto\n---\n# Segunda\n- punto\n```\n"
    )
    assert LessonParser.parse_markdown(markdown, default_title="Memoria de trabajo")["title"] == "Memoria de trabajo"

    con_titulo = "# La clase\n\n```slides\n# Diapositiva\n- punto\n```\n"
    assert LessonParser.parse_markdown(con_titulo, default_title="X")["title"] == "La clase"
