"""Tests de integración para los nuevos endpoints de Rutas, Grafo DAG, Sílabos, System Prompts y Analítica."""

import json
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import aulento.web as web_pkg
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.web.app import create_app
from tests.front import js_del_front

COMPONENTES_JS = Path(web_pkg.__file__).parent / "static" / "componentes.js"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "web_advanced_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    data_dir = tmp_path / "mock_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AULENTO_DATA_DIR", str(data_dir))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_PAID_API_KEY", raising=False)

    conn = get_connection(db_file)
    init_db(conn)
    conn.close()

    app = create_app()
    return TestClient(app)


def test_import_syllabus_preview_and_create(client):
    # 1. Preview
    payload = {
        "titulo": "Syllabus Machine Learning",
        "contenido_texto": "# Modulo 1: Fundamentos\n- Algebra Lineal\n- Probabilidad",
        "categoria": "data_ai",
        "nivel_objetivo": "Junior",
        "enfoque_estudio": "academico",
        "enhance_with_ai": False,
    }
    r = client.post("/api/roadmap/import-syllabus", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["titulo"] == "Syllabus Machine Learning"
    assert len(data["modulos"]) == 1
    assert len(data["modulos"][0]["temas"]) == 2

    # 2. Direct create
    r_create = client.post("/api/roadmap/import-syllabus?create_direct=true", json=payload)
    assert r_create.status_code == 200
    res_create = r_create.json()
    assert res_create["mode"] == "created"
    roadmap_id = res_create["roadmap"]["id"]
    assert roadmap_id is not None

    # Verificar que existe
    r_get = client.get(f"/api/roadmap/{roadmap_id}")
    assert r_get.status_code == 200
    assert r_get.json()["enfoque_estudio"] == "academico"


def test_graph_and_prerequisites_api(client):
    # Crear ruta con 2 temas
    create_payload = {
        "titulo": "Ruta Grafos Test",
        "modulos": [
            {
                "titulo": "Módulo 1",
                "temas": [
                    {"titulo": "Nodo A"},
                    {"titulo": "Nodo B"},
                ],
            }
        ],
    }
    r_create = client.post("/api/roadmap", json=create_payload)
    roadmap = r_create.json()
    r_id = roadmap["id"]
    t_a_id = roadmap["modulos"][0]["temas"][0]["id"]
    t_b_id = roadmap["modulos"][0]["temas"][1]["id"]

    # 1. Get graph
    r_graph = client.get(f"/api/roadmap/{r_id}/graph")
    assert r_graph.status_code == 200
    g_data = r_graph.json()
    assert len(g_data["nodes"]) == 2
    assert "mermaid_code" in g_data

    # 2. Add custom prerequisite
    r_add_pre = client.post(
        f"/api/roadmap/{r_id}/prerequisites",
        json={"tema_origen_id": t_a_id, "tema_destino_id": t_b_id, "tipo": "estricta"},
    )
    assert r_add_pre.status_code == 200
    assert r_add_pre.json()["status"] == "ok"

    # 3. Delete prerequisite
    r_del = client.delete(f"/api/roadmap/{r_id}/prerequisites/{t_a_id}/{t_b_id}")
    assert r_del.status_code == 200
    assert r_del.json()["status"] == "ok"


def test_system_prompts_endpoints(client):
    # 1. Get defaults
    r_get = client.get("/api/roadmap/system-prompts")
    assert r_get.status_code == 200
    data = r_get.json()
    assert "Backward Design" in data["roadmap_default"]
    assert "Educador Pedagógico" in data["lesson_default"]

    # 2. Update custom prompt
    custom_content = "Eres un mentor socrático altamente personalizado para ingenieros de software."
    r_post = client.post(
        "/api/roadmap/system-prompts",
        json={"prompt_type": "roadmap", "content": custom_content},
    )
    assert r_post.status_code == 200
    assert r_post.json()["status"] == "ok"

    # Verificar que cambió
    r_check = client.get("/api/roadmap/system-prompts")
    assert r_check.json()["roadmap_prompt"] == custom_content

    # 3. Reset
    r_reset = client.post(
        "/api/roadmap/system-prompts/reset",
        json={"prompt_type": "roadmap"},
    )
    assert r_reset.status_code == 200

    r_check_reset = client.get("/api/roadmap/system-prompts")
    assert "Backward Design" in r_check_reset.json()["roadmap_prompt"]


def test_analytics_and_keys_endpoints(client):
    # 1. Token summary
    r_summary = client.get("/api/analytics/tokens?days=7")
    assert r_summary.status_code == 200
    summary = r_summary.json()
    assert "total_tokens" in summary
    assert "total_estimated_cost_usd" in summary

    # 2. Get keys status
    r_keys = client.get("/api/config/gemini-keys")
    assert r_keys.status_code == 200
    status = r_keys.json()
    assert "has_free_key" in status
    assert "active_tier" in status

    # 3. Update keys and tier
    r_update = client.post(
        "/api/config/gemini-keys",
        json={
            "gemini_free_key": "AIzaSy_FreeKeyTest123",
            "gemini_paid_key": "AIzaSy_PaidKeyTest456",
            "active_tier": "auto",
        },
    )
    assert r_update.status_code == 200
    up_status = r_update.json()
    assert up_status["has_free_key"] is True
    assert up_status["has_paid_key"] is True
    assert up_status["active_tier"] == "auto"
    assert "..." in up_status["free_key_masked"]


# --- Interfaz web: alcance, aviso de fallback, perfil pedagógico y expansión de materia ---

def test_html_servido_incluye_alcance_perfil_y_aviso(client):
    html = client.get("/").text

    for element_id in [
        'id="new-roadmap-alcance"',
        'id="modal-pedagogical-profile"',
        'id="pedagogical-profile-sections"',
        'id="roadmap-fallback-aviso"',
    ]:
        assert element_id in html
    for alcance in ['value="curso"', 'value="especializacion"', 'value="carrera"']:
        assert alcance in html
    assert 'data-accion="ruta-abrir-perfil"' in html
    assert _accion(_app_js(client), "ruta-abrir-perfil") == "openPedagogicalProfileModal()"


def test_html_ofrece_las_plantillas_por_su_titulo_completo(client):
    """El selector debe enviar el título exacto: las coincidencias parciales ya no devuelven plantilla."""
    html = client.get("/").text
    selector = html[html.index('id="new-roadmap-template"'):]
    selector = selector[:selector.index("</select>")]
    valores = {unescape(v) for v in re.findall(r'<option value="([^"]*)"', selector)}

    titulos = {tmpl["titulo"] for tmpl in client.get("/api/roadmap/templates").json()}
    assert valores - {""} == titulos


def test_app_js_usa_los_endpoints_de_perfil_expansion_y_alcance(client):
    r = client.get("/static/app.js")
    assert r.status_code == 200
    js = js_del_front()

    assert "/pedagogical-profile`" in js
    assert "method: 'PUT'" in js
    assert "/api/roadmap/modules/${moduleId}/expand`" in js
    assert "Expandir materia" in js
    assert "getElementById('new-roadmap-alcance')" in js
    assert "alcance: alcance" in js
    assert "metadata_json.aviso" in js


def test_app_js_inserta_el_texto_del_perfil_y_del_aviso_sin_html_crudo(client):
    js = js_del_front()

    perfil = js[js.index("// --- MODAL PERFIL PEDAGÓGICO ---"):js.index("// --- MODAL NUEVA RUTA ---")]
    assert "savePedagogicalProfile" in perfil
    assert "innerHTML" not in perfil
    assert "insertAdjacentHTML" not in perfil
    assert "textContent" in perfil

    aviso = js[js.index("function renderRoadmapFallbackAviso"):js.index("function renderEmptyRoadmapState")]
    assert "text.textContent = aviso" in aviso
    assert "innerHTML" not in aviso


# --- 023: visor de clase (render saneado, pestañas, diapositivas) y opciones del prompt ---

def _app_js(client=None) -> str:
    """Frontend concatenado con finales de línea normalizados."""
    return js_del_front().replace("\r\n", "\n")


def _accion(js: str, nombre: str) -> str:
    """072: lo que hace una acción delegada, tal como la registra la tabla de pantalla-roadmap.js."""
    m = re.search(rf"\['{re.escape(nombre)}', \([^)]*\) => (.+?)\],\n", js)
    assert m, f"la acción {nombre} no está registrada"
    return m.group(1)


def _funcion_js(js: str, nombre: str) -> str:
    """Cuerpo de una función de nivel superior de app.js (hasta su llave de cierre en columna 0)."""
    inicio = js.index(f"function {nombre}(")
    return js[inicio:js.index("\n}\n", inicio) + 3]


def _seccion_visor(js: str) -> str:
    return js[js.index("// --- MODAL VISOR DE CLASE ---"):js.index("// --- MODAL COMPARADOR DE PDFS")]


def test_html_carga_las_librerias_del_visor_desde_la_propia_app(client):
    html = client.get("/").text

    for archivo in ["marked.min.js", "purify.min.js"]:
        assert re.search(rf'<script\s+src="/static/vendor/{re.escape(archivo)}"\s+defer></script>', html)
        r = client.get(f"/static/vendor/{archivo}")
        assert r.status_code == 200
        assert len(r.content) > 10_000

    assert "/static/vendor/mermaid.min.js" not in html
    assert "mermaid.initialize" not in html

    r_mermaid = client.get("/static/vendor/mermaid.min.js")
    assert r_mermaid.status_code == 200
    assert len(r_mermaid.content) > 10_000

    sw = (COMPONENTES_JS.parent / "sw.js").read_text(encoding="utf-8")
    assert "/static/vendor/mermaid.min.js" in sw

    js_roadmap = (COMPONENTES_JS.parent / "js" / "pantalla-roadmap.js").read_text(encoding="utf-8")
    assert "/static/vendor/mermaid.min.js" in js_roadmap

    # Las librerías deben estar cargadas antes que app.js.
    assert html.index("/static/vendor/purify.min.js") < html.index("/static/app.js?v=")


def test_la_pagina_no_carga_scripts_que_su_csp_bloquea(client):
    # La CSP no permite CDNs de scripts (Tailwind ahora está compilado en local)
    # y ningún <script src> debe provenir de un origen externo no autorizado.
    r = client.get("/")
    script_src = next(d for d in r.headers["content-security-policy"].split(";") if d.strip().startswith("script-src"))
    assert "cdn.tailwindcss.com" not in script_src
    assert "cdn.tailwindcss.com" not in r.headers["content-security-policy"]
    externos = re.findall(r'<script[^>]*\bsrc="(https?://[^/"]+)', r.text)
    assert not externos, f"No debe haber scripts de orígenes externos: {externos}"
    assert "cdn.jsdelivr.net" not in r.text[: r.text.index("</head>")]
    assert "cdn.tailwindcss.com" not in r.text


def test_html_del_visor_tiene_estilos_para_el_markdown_renderizado(client):
    html = client.get("/").text
    assert ".lesson-md table" in html
    assert ".lesson-md img, .lesson-md svg { max-width: 100%;" in html


def test_visor_solo_inserta_html_saneado_por_dompurify(client):
    visor = _seccion_visor(_app_js(client))

    assert visor.count("innerHTML") == 1
    assert "container.innerHTML = window.DOMPurify.sanitize(html, LESSON_SANITIZE_CONFIG);" in visor
    for sumidero in ["insertAdjacentHTML", "outerHTML", "document.write", "createContextualFragment"]:
        assert sumidero not in visor
    for funcion in ["viewLessonModal", "renderLessonSlides", "renderLessonFlashcards", "renderLessonPlainText", "switchLessonView"]:
        assert "innerHTML" not in _funcion_js(visor, funcion)

    config = visor[visor.index("const LESSON_SANITIZE_CONFIG"):visor.index("let lessonMarkdownParser")]
    assert "USE_PROFILES: { html: true, svg: true, svgFilters: true }" in config
    assert "'style'" in config and "'form'" in config


def test_visor_sin_librerias_muestra_texto_plano_escapado(client):
    visor = _seccion_visor(_app_js(client))

    disponibles = _funcion_js(visor, "lessonLibsReady")
    assert "window.marked" in disponibles
    assert "window.DOMPurify" in disponibles

    render = _funcion_js(visor, "renderLessonMarkdown")
    respaldo = render.index("if (!lessonLibsReady()) {\n    renderLessonPlainText(body, container);\n    return;\n  }")
    assert respaldo < render.index(".parse(body)") < render.index("DOMPurify.sanitize")

    plano = _funcion_js(visor, "renderLessonPlainText")
    assert "pre.textContent = markdown;" in plano
    assert "notice.textContent = " in plano


def test_visor_dibuja_bloques_especiales_y_oculta_tarjetas_y_diapositivas(client):
    visor = _seccion_visor(_app_js(client))

    parser = _funcion_js(visor, "getLessonMarkdownParser")
    assert 'if (lang === \'mermaid\') return `<div class="mermaid">${escapeHtml(text)}</div>\\n`;' in parser
    assert 'if (lang === \'svg\') return `<figure class="lesson-figure">${text}</figure>\\n`;' in parser
    assert "if (lang === 'cards-fsrs' || lang === 'slides') return '';" in parser

    render = _funcion_js(visor, "renderLessonMarkdown")
    assert "extractFencedBlock(extractFencedBlock(markdown, 'cards-fsrs').rest, 'slides').rest" in render
    assert render.index("DOMPurify.sanitize") < render.index("decorateLessonCallouts(container)") < render.index("mermaid.run")

    callouts = _funcion_js(visor, "decorateLessonCallouts")
    assert r"\[!(tip|warning|note)\]" in callouts
    assert "const rest = marker.nodeValue.slice(match[0].length);" in callouts
    assert "LESSON_CALLOUTS[kind]" in callouts
    assert "label.textContent = " in callouts
    assert "innerHTML" not in callouts

    html = client.get("/").text
    for clase in [".lesson-callout-tip", ".lesson-callout-warning", ".lesson-callout-note"]:
        assert clase in html


def test_visor_inserta_las_flashcards_como_texto(client):
    js = _app_js(client)
    tarjetas = _funcion_js(js, "renderLessonFlashcards")

    assert "question.textContent = card.pregunta;" in tarjetas
    assert "answer.textContent = card.respuesta;" in tarjetas
    visor = _seccion_visor(js)
    assert "${card.pregunta}" not in visor
    assert "${card.respuesta}" not in visor
    assert "renderLessonFlashcards(lesson.flashcards_json);" in _funcion_js(js, "viewLessonModal")


def test_html_del_visor_tiene_las_tres_pestanas_y_sus_paneles(client):
    html = client.get("/").text
    modal = html[html.index('id="modal-view-lesson"'):html.index('id="modal-pdf-gap"')]

    for element_id in [
        "viewer-tab-preview",
        "viewer-tab-markdown",
        "viewer-tab-slides",
        "viewer-content-body",
        "viewer-markdown-source",
        "viewer-slides",
        "viewer-slide-stage",
        "viewer-slide-prev",
        "viewer-slide-next",
        "viewer-slide-counter",
        "viewer-cards-list",
    ]:
        assert modal.count(f'id="{element_id}"') == 1
    js = _app_js(client)
    assert _accion(js, "ruta-cambiar-vista-clase") == "switchLessonView(datos.vista)"
    for vista in ["preview", "markdown", "slides"]:
        assert re.search(rf'data-accion="ruta-cambiar-vista-clase"[^>]*data-vista="{vista}"|data-vista="{vista}"[^>]*data-accion="ruta-cambiar-vista-clase"', modal)
    assert '<pre id="viewer-markdown-source"' in modal
    for accion, funcion in [
        ("ruta-copiar-markdown-clase", "copyLessonMarkdown()"),
        ("ruta-anterior-slide-clase", "prevLessonSlide()"),
        ("ruta-siguiente-slide-clase", "nextLessonSlide()"),
    ]:
        assert f'data-accion="{accion}"' in modal and _accion(js, accion) == funcion

    # Vista previa es la pestaña inicial; Diapositivas arranca oculta hasta saber si hay bloque slides.
    assert re.search(r'id="viewer-tab-preview"[^>]*aria-selected="true"', modal)
    assert re.search(r'id="viewer-tab-slides"[^>]*class="[^"]*\bhidden\b', modal)
    assert re.search(r'id="viewer-slides" class="[^"]*\bhidden\b', modal)


def test_app_js_implementa_las_vistas_del_visor(client):
    js = _app_js(client)
    for funcion in ["switchLessonView", "renderLessonSlides", "copyLessonMarkdown", "nextLessonSlide", "prevLessonSlide", "extractFencedBlock"]:
        assert f"function {funcion}(" in js

    abrir = _funcion_js(js, "viewLessonModal")
    assert "document.getElementById('viewer-markdown-source').textContent = markdown;" in abrir
    assert "state.lessonSlides = splitLessonSlides(extractFencedBlock(markdown, 'slides').content);" in abrir
    assert "state.lessonSlideIndex = 0;" in abrir
    assert "switchLessonView('preview');" in abrir

    vistas = _funcion_js(js, "switchLessonView")
    assert "getElementById('viewer-tab-slides').classList.toggle('hidden', !hasSlides)" in vistas
    assert "(view === 'slides' && hasSlides)" in vistas

    diapositivas = _funcion_js(js, "renderLessonSlides")
    assert "renderLessonMarkdown(state.lessonSlides[state.lessonSlideIndex], document.getElementById('viewer-slide-stage'));" in diapositivas
    assert "`${state.lessonSlideIndex + 1} / ${total}`" in diapositivas

    assert "/^\\s*-{3,}\\s*$/" in _funcion_js(js, "splitLessonSlides")
    assert "navigator.clipboard.writeText(state.currentLesson.contenido_markdown" in _funcion_js(js, "copyLessonMarkdown")

    visor = _seccion_visor(js)
    teclado = visor[visor.index("document.addEventListener('keydown'"):visor.index("function copyLessonMarkdown(")]
    assert "if (state.lessonView !== 'slides') return;" in teclado
    assert "if (!Au.modal.abierto('modal-view-lesson')) return;" in teclado
    assert teclado.index("'ArrowRight'") < teclado.index("nextLessonSlide();")
    assert teclado.index("'ArrowLeft'") < teclado.index("prevLessonSlide();")


OPCIONES_NUEVAS = {
    "include_visuals": "prompt-toggle-visuals",
    "include_slides": "prompt-toggle-slides",
    "include_quiz": "prompt-toggle-quiz",
    "include_glossary": "prompt-toggle-glossary",
    "include_bridge": "prompt-toggle-bridge",
}


def test_html_del_prompt_expone_las_opciones_nuevas_y_quita_formato_sop(client):
    html = client.get("/").text
    modal = html[html.index('id="modal-topic-prompt"'):html.index('id="modal-import-lesson"')]

    assert _accion(_app_js(client), "ruta-refrescar-prompt-tema") == "refreshTopicPrompt()"
    for element_id in OPCIONES_NUEVAS.values():
        assert re.search(rf'<input type="checkbox" id="{element_id}"[^>]*data-accion="ruta-refrescar-prompt-tema"', modal)
    selector = modal[modal.index('<select id="prompt-depth" data-accion="ruta-refrescar-prompt-tema"'):]
    selector = selector[:selector.index("</select>")]
    assert re.findall(r'<option value="([^"]*)"', selector) == ["breve", "estandar", "exhaustiva"]
    assert '<option value="estandar" selected>' in selector

    assert "prompt-toggle-sop" not in html
    assert "Formato SOP" not in html

    # Figuras y diapositivas arrancan activadas; las otras tres opciones, apagadas.
    def marcado(element_id):
        return " checked" in re.search(rf'<input type="checkbox" id="{element_id}"[^>]*>', modal).group(0)

    assert marcado("prompt-toggle-visuals") and marcado("prompt-toggle-slides")
    assert not any(marcado(i) for i in ["prompt-toggle-quiz", "prompt-toggle-glossary", "prompt-toggle-bridge"])


def test_app_js_envia_las_opciones_al_construir_el_prompt_y_al_generar(client):
    js = _app_js(client)
    assert "prompt-toggle-sop" not in js

    opciones = _funcion_js(js, "readPromptOptions")
    for campo, element_id in OPCIONES_NUEVAS.items():
        assert f"{campo}: isChecked('{element_id}')," in opciones
    assert "depth: document.getElementById('prompt-depth').value," in opciones
    assert "include_materials: isChecked('prompt-toggle-materiales')," in opciones
    assert "include_drive_search" not in js
    for campo in ["include_web_research", "include_fsrs_cards", "target_llm"]:
        assert f"{campo}: " in opciones

    construir = _funcion_js(js, "refreshTopicPrompt")
    assert "const options = readPromptOptions();" in construir
    assert "/build-prompt`" in construir
    assert "body: JSON.stringify(options)" in construir

    # Una respuesta que llega tarde no debe pisar el prompt de la última selección.
    assert "const seq = ++promptRequestSeq;" in construir
    assert construir.count("if (seq !== promptRequestSeq) return;") == 2

    generar = _funcion_js(js, "generateLessonInApp")
    assert "/generate-lesson`" in generar
    assert "headers: { 'Content-Type': 'application/json' }," in generar
    assert "const options = readPromptOptions();" in generar
    assert "body: JSON.stringify(options)" in generar
    # El diálogo de confirmación dice qué opciones se van a aplicar.
    assert "options.include_visuals && 'figuras'" in generar
    assert "options.include_slides && 'diapositivas'" in generar


def test_visor_aisla_los_ids_de_las_figuras_y_no_fuerza_pestana_nueva_en_anclas(client):
    visor = _seccion_visor(_app_js(client))

    render = _funcion_js(visor, "renderLessonMarkdown")
    assert "container.querySelectorAll('svg').forEach(namespaceLessonSvgIds);" in render
    assert "if (/^https?:/i.test(href)) {" in render
    assert "link.removeAttribute('href');" in render

    aislar = _funcion_js(visor, "namespaceLessonSvgIds")
    assert "const prefix = `lesson-fig-${++lessonSvgCounter}-`;" in aislar
    assert "el.id = prefix + el.id;" in aislar
    assert "url(" in aislar and "'xlink:href'" in aislar


def test_visor_no_captura_flechas_con_modificadores_ni_copia_sin_portapapeles(client):
    visor = _seccion_visor(_app_js(client))
    assert "if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;" in visor

    copiar = _funcion_js(visor, "copyLessonMarkdown")
    assert copiar.index("if (!navigator.clipboard || !navigator.clipboard.writeText) {") < copiar.index(
        "navigator.clipboard.writeText(state.currentLesson"
    )


# --- 024: grafo de prelaciones dibujado, edición desde el grafo y sugerencias con IA ---

def _seccion_grafo(js: str) -> str:
    return js[js.index("// --- GRAFO DIBUJADO:"):js.index("function copyRoadmapMermaid(")]


def _contenedor_dag(html: str) -> str:
    inicio = html.index('id="roadmap-dag-container"')
    return html[inicio:html.index("</section>", inicio)]


def test_html_del_grafo_tiene_diagrama_aviso_panel_y_leyenda(client):
    dag = _contenedor_dag(client.get("/").text)

    for element_id in ["dag-diagram", "dag-diagram-notice", "dag-node-panel"]:
        assert dag.count(f'id="{element_id}"') == 1
    # La tarjeta del grafo va al inicio de la vista, antes de los indicadores y del tablero de tarjetas.
    assert dag.index('id="dag-diagram"') < dag.index('id="dag-kpis-container"') < dag.index('id="dag-nodes-board"')
    assert re.search(r'id="dag-diagram-notice"[^>]*class="[^"]*\bhidden\b"', dag)
    leyenda = dag[: dag.index('id="dag-diagram-notice"')]
    for texto in ["Dominado", "En progreso", "Disponible", "Bloqueado", "Camino principal", "Estricta", "Recomendada", "Inferida"]:
        assert texto in leyenda


def test_mermaid_sigue_en_modo_estricto_y_sin_callbacks_propios(client):
    js = _app_js(client)
    init_mermaid = _funcion_js(js, "inicializarMermaid")
    assert "securityLevel: 'strict'" in init_mermaid
    assert "securityLevel: 'loose'" not in js
    # Los clics se enganchan desde app.js sobre el SVG ya dibujado, no con callbacks de Mermaid.
    assert "el.addEventListener('click', () => selectDagNode(nodeId));" in _funcion_js(js, "renderDagDiagram")


def test_app_js_dibuja_el_grafo_con_mermaid_render_y_tiene_respaldo(client):
    js = _app_js(client)
    dibujar = _funcion_js(js, "renderDagDiagram")

    assert "await mermaid.render(renderId, graphData.mermaid_code)" in dibujar
    # Sin Mermaid: aviso y nada de dibujo; el tablero de tarjetas no se toca.
    sin_mermaid = dibujar.index("if (!window.mermaid) {")
    assert sin_mermaid < dibujar.index("mermaid.render(")
    assert "setDagDiagramNotice('No se pudo cargar Mermaid" in dibujar[sin_mermaid:dibujar.index("mermaid.render(")]
    # Si el dibujo falla: aviso, sin dejar un diagrama a medias.
    fallo = dibujar[dibujar.index("} catch (err) {"):]
    assert "container.replaceChildren();" in fallo
    assert "setDagDiagramNotice('No se pudo dibujar el grafo." in fallo
    assert "dag-nodes-board" not in dibujar
    # Un dibujo que llega tarde no pisa al de la carga más nueva.
    assert "const seq = ++dagRenderSeq;" in dibujar
    assert dibujar.count("if (seq !== dagRenderSeq) return;") == 3

    # Los nodos se enlazan por el id que Mermaid 10 les pone.
    assert r"/^flowchart-T_(\d+)-\d+$/" in _funcion_js(js, "dagNodeIdFromElement")
    assert "container.querySelectorAll('g.node').forEach(" in dibujar

    aviso = _funcion_js(js, "setDagDiagramNotice")
    assert "notice.textContent = message || '';" in aviso
    assert "getElementById('dag-diagram-notice')" in aviso

    # El grafo se vuelve a dibujar con cada carga, y lo que se copia a Obsidian es el mismo código (R11).
    render = _funcion_js(js, "renderRoadmapGraph")
    assert "renderDagDiagram(" not in render
    assert "renderDagDiagram(graphData);" in _funcion_js(js, "loadRoadmapGraph")
    assert "mermaidPre.textContent = graphData.mermaid_code" in render
    assert "navigator.clipboard.writeText(state.activeGraphData.mermaid_code)" in _funcion_js(js, "copyRoadmapMermaid")


def test_app_js_no_inserta_datos_de_temas_como_html_en_el_grafo(client):
    js = _app_js(client)
    seccion = _seccion_grafo(js)

    # El único HTML que se inserta es el SVG que devuelve Mermaid en modo estricto.
    assert seccion.count("innerHTML") == 1
    assert "container.innerHTML = svg;" in _funcion_js(js, "renderDagDiagram")
    for sumidero in ["insertAdjacentHTML", "outerHTML", "document.write", "createContextualFragment"]:
        assert sumidero not in seccion
    for funcion in [
        "selectDagNode",
        "renderDagNodePanel",
        "buildDagEdgeRow",
        "buildDagEdgeSection",
        "renderDagAvailable",
        "renderPrerequisiteSuggestions",
        "applyDagSelectionStyles",
    ]:
        assert "innerHTML" not in _funcion_js(js, funcion)
    assert "if (text !== undefined && text !== null) el.textContent = text;" in _funcion_js(js, "dagEl")


def test_app_js_resalta_el_nodo_sus_prerrequisitos_y_sus_dependientes(client):
    js = _app_js(client)
    html = client.get("/").text

    seleccionar = _funcion_js(js, "selectDagNode")
    assert "applyDagSelectionStyles();" in seleccionar
    assert "renderDagNodePanel(node);" in seleccionar

    estilos = _funcion_js(js, "applyDagSelectionStyles")
    assert "new Set(selected ? selected.prerequisites : [])" in estilos
    assert "new Set(selected ? selected.dependents : [])" in estilos
    for clase in ["dag-node-selected", "dag-node-prereq", "dag-node-dependent", "dag-node-dimmed"]:
        assert f"el.classList.add('{clase}')" in estilos
        assert f"g.node.{clase}" in html

    panel = _funcion_js(js, "renderDagNodePanel")
    assert "getElementById('dag-node-panel')" in panel
    assert "node.titulo" in panel and "node.modulo_titulo" in panel and "dagNodeStatusLabel(node)" in panel

    # Las tarjetas y la secuencia siguen llamando a highlightGraphNode, que ahora usa la selección común.
    assert "selectDagNode(nodeId);" in _funcion_js(js, "highlightGraphNode")


def test_html_del_grafo_tiene_interruptor_disponibles_y_modal_de_sugerencias(client):
    html = client.get("/").text
    dag = _contenedor_dag(html)

    for element_id in ["dag-toggle-implicit", "dag-available-list", "btn-dag-suggest"]:
        assert dag.count(f'id="{element_id}"') == 1
    js = _app_js(client)
    assert re.search(r'<input type="checkbox" id="dag-toggle-implicit" data-accion="ruta-alternar-secuencia-implicita"', dag)
    assert _accion(js, "ruta-alternar-secuencia-implicita") == "toggleDagImplicitSequence(el.checked)"
    assert re.search(r'id="btn-dag-suggest"[^>]*data-accion="ruta-sugerir-requisitos"|data-accion="ruta-sugerir-requisitos"[^>]*id="btn-dag-suggest"', dag)
    assert _accion(js, "ruta-sugerir-requisitos") == "requestPrerequisiteSuggestions()"

    assert html.count('id="modal-prerequisite-suggestions"') == 1
    modal = html[html.index('id="modal-prerequisite-suggestions"'):html.index('id="modal-new-roadmap"')]
    for element_id in [
        "prereq-suggestions-summary",
        "prereq-suggestions-list",
        "prereq-suggestions-disable-implicit",
        "prereq-suggestions-status",
        "btn-accept-prereq-suggestions",
    ]:
        assert modal.count(f'id="{element_id}"') == 1
    assert 'data-accion="ruta-aceptar-sugerencias-requisitos"' in modal
    assert _accion(js, "ruta-aceptar-sugerencias-requisitos") == "acceptPrerequisiteSuggestions()"
    assert re.search(r'<input type="checkbox" id="prereq-suggestions-disable-implicit"', modal)
    assert "/static/app.js?v=2.24" in html


def test_app_js_edita_prelaciones_desde_el_panel_del_nodo(client):
    js = _app_js(client)

    fila = _funcion_js(js, "buildDagEdgeRow")
    # Las inferidas se muestran pero no se pueden quitar ni cambiar: no están guardadas.
    assert fila.index("if (edge.inferida) {") < fila.index("} else {") < fila.index("changeDagPrerequisiteType(")
    assert "changeDagPrerequisiteType(edge.tema_origen_id, edge.tema_destino_id, nextType)" in fila
    assert "removeDagPrerequisite(edge.tema_origen_id, edge.tema_destino_id)" in fila
    assert "const nextType = edge.tipo === 'estricta' ? 'recomendada' : 'estricta';" in fila

    panel = _funcion_js(js, "renderDagNodePanel")
    assert "edges.filter(e => e.tema_destino_id === node.id)" in panel
    assert "edges.filter(e => e.tema_origen_id === node.id)" in panel
    assert "openAddPrerequisiteWithDefaults(node.id)" in panel

    quitar = _funcion_js(js, "removeDagPrerequisite")
    assert "/prerequisites/${origenId}/${destinoId}`" in quitar
    assert "method: 'DELETE'" in quitar
    assert "await loadRoadmapGraph();" in quitar

    cambiar = _funcion_js(js, "changeDagPrerequisiteType")
    assert "/prerequisites`" in cambiar and "method: 'POST'" in cambiar
    assert "tipo: tipo" in cambiar
    assert "await loadRoadmapGraph();" in cambiar

    interruptor = _funcion_js(js, "toggleDagImplicitSequence")
    assert "/graph-settings`" in interruptor and "method: 'PUT'" in interruptor
    assert "JSON.stringify({ secuencia_implicita: enabled })" in interruptor
    assert "await loadRoadmapGraph();" in interruptor
    assert "toggle.checked = !enabled;" in interruptor
    assert "implicitToggle.checked = graphData.secuencia_implicita !== false;" in _funcion_js(js, "renderRoadmapGraph")

    assert "await loadRoadmapGraph();" in _funcion_js(js, "submitCreatePrerequisite")


def test_app_js_muestra_que_estudiar_ahora(client):
    js = _app_js(client)
    disponibles = _funcion_js(js, "renderDagAvailable")

    assert "getElementById('dag-available-list')" in disponibles
    # Se respeta el orden que envía el servidor (curricular), sin reordenar en el cliente.
    assert "(graphData.disponibles || []).map(id => nodesById.get(id))" in disponibles
    assert ".sort(" not in disponibles
    assert "if (node.is_critical_path) {" in disponibles
    assert "btn.addEventListener('click', () => highlightGraphNode(node.id));" in disponibles
    assert "renderDagAvailable(graphData);" in _funcion_js(js, "renderRoadmapGraph")
    assert "scrollIntoView(" in _funcion_js(js, "highlightGraphNode")


def test_app_js_pide_sugerencias_y_las_acepta_en_bloque(client):
    js = _app_js(client)

    pedir = _funcion_js(js, "requestPrerequisiteSuggestions")
    assert "/prerequisites/suggest`, { method: 'POST' }" in pedir
    assert "state.prerequisiteSuggestions = data.sugerencias || [];" in pedir
    assert "renderPrerequisiteSuggestions(data.descartadas || 0);" in pedir
    # Sin IA (503) se muestra el error y no se abre el modal ni se guarda nada.
    assert pedir.index("if (!res.ok) throw new Error(") < pedir.index("Au.modal.abrir('modal-prerequisite-suggestions')")
    assert "/prerequisites/bulk" not in pedir and "/prerequisites`" not in pedir

    lista = _funcion_js(js, "renderPrerequisiteSuggestions")
    assert "check.type = 'checkbox';" in lista
    assert "check.checked = true;" in lista
    assert "suggestion.origen_titulo" in lista and "suggestion.destino_titulo" in lista and "suggestion.motivo" in lista
    assert "${discarded}" in lista

    aceptar = _funcion_js(js, "acceptPrerequisiteSuggestions")
    assert "/prerequisites/bulk`" in aceptar and "method: 'POST'" in aceptar
    assert ".filter(check => check.checked)" in aceptar
    assert "getElementById('prereq-suggestions-disable-implicit').checked ? false : null" in aceptar
    assert "await loadRoadmapGraph();" in aceptar


def test_mermaid_admite_rutas_grandes_y_el_error_de_validacion_es_legible(client):
    js = _app_js(client)
    assert "maxTextSize: 500000" in js and "maxEdges: 5000" in js

    detalle = _funcion_js(js, "dagErrorDetail")
    assert "Array.isArray(body.detail)" in detalle


# --- Árbol de la ruta: títulos y descripciones generados por la IA se insertan como texto ---

ARNES_DEL_ARBOL = r"""
const fs = require('fs');
const js = fs.readFileSync(process.argv[2], 'utf8').replace(/\r\n/g, '\n');
const funcion = (nombre) => {
  const inicio = js.indexOf(`function ${nombre}(`);
  return js.slice(inicio, js.indexOf('\n}\n', inicio) + 2);
};
const elementos = {};
const elemento = () => ({ textContent: '', innerHTML: '', className: '', style: {}, hijos: [], appendChild(h) { this.hijos.push(h); } });
globalThis.document = {
  getElementById: (id) => (elementos[id] = elementos[id] || elemento()),
  createElement: () => elemento(),
};
globalThis.renderRoadmapFallbackAviso = () => {};
// 072: el árbol arma las insignias con Au.*; componentes.js necesita window y addEventListener
globalThis.window = globalThis;
const listeners = [];
globalThis.document.addEventListener = (tipo, fn) => {
  if (tipo === 'click') listeners.push(fn);
};
eval(fs.readFileSync(process.argv[3], 'utf8'));
const accionesMatch = js.match(/\/\/\s*---\s*ACCIONES DELEGADAS DE RUTAS[\s\S]*?forEach\(\(\[nombre, fn\]\)\s*=>\s*Au\.acciones\.registrar\(nombre,\s*fn\)\);/);
if (accionesMatch) eval(accionesMatch[0]);
eval(funcion('escapeHtml') + '\n' + funcion('renderRoadmap') + '\nglobalThis.renderRoadmap = renderRoadmap;');
const hostil = (campo) => `<img src=x onerror="alert('${campo}')">`;
renderRoadmap({
  nivel_objetivo: 'Senior', temas_completados: 0, total_temas: 1, progreso_pct: 0,
  modulos: [{
    id: 7, titulo: hostil('modulo'), descripcion: hostil('descripcion del modulo'),
    temas: [{ id: '3); alert(1', estado: "pendiente'); alert('estado", titulo: hostil('tema'), descripcion: hostil('descripcion del tema'), clase: true, fuente: 'ia' }],
  }],
});
const html = elementos['roadmap-tree-container'].hijos.map((h) => h.innerHTML).join('');

let invocacion = null;
globalThis.toggleTopicStatus = (id, estado) => {
  invocacion = { idEsNaN: Number.isNaN(id), estado };
};
const accionRegistrada = typeof Au !== 'undefined' && Boolean(Au.acciones && Au.acciones.existe('cambiar-estado-tema'));
const accionMatch = html.match(/data-accion="(cambiar-estado-tema)"/);
const topicIdMatch = html.match(/data-topic-id="([^"]+)"/);
const estadoMatch = html.match(/data-estado="([^"]+)"/);

globalThis.Element = class {};
const fakeBtn = Object.assign(new Element(), {
  tagName: 'BUTTON',
  dataset: {
    accion: accionMatch ? accionMatch[1] : undefined,
    topicId: topicIdMatch ? topicIdMatch[1] : undefined,
    estado: estadoMatch ? estadoMatch[1] : undefined,
  },
  classList: { contains: () => false },
  hasAttribute: (attr) => attr in fakeBtn.dataset,
  matches: (sel) => sel.split(', ').includes('button'),
  closest: (sel) => fakeBtn,
  contains: (other) => other === fakeBtn,
});
listeners.forEach((fn) => fn({ type: 'click', target: fakeBtn, preventDefault: () => {} }));

console.log(JSON.stringify({ html, invocacion, accionRegistrada }));
"""


def test_el_arbol_de_la_ruta_inserta_titulos_y_descripciones_hostiles_como_texto(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node no está instalado")
    arnes = tmp_path / "arnes.js"
    arnes.write_text(ARNES_DEL_ARBOL, encoding="utf-8")
    front_js = tmp_path / "front.js"
    front_js.write_text(js_del_front(), encoding="utf-8")

    corrida = subprocess.run(
        [node, str(arnes), str(front_js), str(COMPONENTES_JS)], capture_output=True, encoding="utf-8", timeout=30, check=False
    )

    assert corrida.returncode == 0, corrida.stderr
    salida = json.loads(corrida.stdout)
    html = salida["html"]
    assert "<img" not in html
    for campo in ("modulo", "descripcion del modulo", "tema", "descripcion del tema"):
        assert f"&lt;img src=x onerror=&quot;alert(&#39;{campo}&#39;)&quot;&gt;" in html
    # El id y el estado van en data-* leídos por el listener delegado (R14):
    # el texto hostil no se ejecuta como JS y un id no numérico llega como NaN a toggleTopicStatus.
    assert "alert(1" not in html and "alert('estado" not in html
    assert 'data-accion="cambiar-estado-tema"' in html
    assert 'data-topic-id="NaN"' in html
    assert 'data-estado="pendiente"' in html
    assert "toggleTopicStatus(" not in html
    assert salida["accionRegistrada"] is True
    assert salida["invocacion"] is not None
    assert salida["invocacion"]["idEsNaN"] is True
    assert salida["invocacion"]["estado"] == "pendiente"


def test_el_comparador_de_pdfs_inserta_las_brechas_como_texto(client):
    analisis = _funcion_js(_app_js(client), "submitPdfGapAnalysis")
    assert "${escapeHtml(g.titulo)}" in analisis
    assert "${escapeHtml(g.descripcion || 'Sin descripción')}" in analisis
    assert not re.search(r"\$\{g\.(titulo|descripcion)", analisis)


def test_mapa_interactivo_integrado_en_contenedor_del_grafo(client):
    r_create = client.post(
        "/api/roadmap",
        json={
            "titulo": "Ruta de Prueba DAG",
            "modulos": [{"titulo": "Módulo 1", "temas": [{"titulo": "Nodo A"}, {"titulo": "Nodo B"}]}],
        },
    )
    roadmap_id = r_create.json()["id"]
    res_map = client.get(f"/api/roadmap/{roadmap_id}/interactive-map")
    assert res_map.status_code == 200
    assert "text/html" in res_map.headers["content-type"]
    assert res_map.headers.get("x-frame-options") == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in res_map.headers.get("content-security-policy", "")
    assert "Ruta de Prueba DAG" in res_map.text
    assert "aulento-dag-bridge-v2" in res_map.text

    node = shutil.which("node")
    if node is not None:
        scripts = re.findall(r"<script>(.*?)</script>", res_map.text, re.DOTALL)
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write("\n".join(scripts))
            js_file = fh.name
        check = subprocess.run([node, "--check", js_file], capture_output=True, text=True, check=False)
        assert check.returncode == 0, check.stderr

    res_html = client.get("/")
    assert res_html.status_code == 200
    assert 'id="dag-interactive-frame"' in res_html.text
    assert 'id="btn-dag-mode-schema"' not in res_html.text


def test_mapa_interactivo_no_inserta_el_titulo_de_un_tema_como_html(client):
    """El título sale de dataset (ya sin escape): el panel de selección lo vuelve a escapar antes de pintarlo."""
    malicioso = '<img src=x onerror="alert(1)">'
    roadmap_id = client.post(
        "/api/roadmap",
        json={"titulo": "Ruta con título raro", "modulos": [{"titulo": "M", "temas": [{"titulo": malicioso}]}]},
    ).json()["id"]

    html_del_mapa = client.get(f"/api/roadmap/{roadmap_id}/interactive-map").text

    assert malicioso not in html_del_mapa
    assert "${escaparHtml(selectedTitle)}" in html_del_mapa
    assert "${selectedTitle}" not in html_del_mapa
    # Tras arrastrar el mapa, el clic siguiente sobre un tema tiene que seleccionarlo
    al_apretar = html_del_mapa.split("addEventListener('pointerdown'")[1].split("});")[0]
    assert al_apretar.index("dragMoved = false") < al_apretar.index("g.dag-node")


def test_el_visor_de_documentacion_sanea_el_html_como_las_clases(client):
    visor = _funcion_js(_app_js(client), "renderManualMarkdown")

    assert "window.DOMPurify.sanitize(html, LESSON_SANITIZE_CONFIG)" in visor
    assert "container.innerHTML = html" not in visor
    # Sin DOMPurify no se inserta HTML: se muestra el texto plano
    assert visor.index("container.textContent = cleanText") < visor.index("container.innerHTML")
    # El cuerpo de las alertas también se convierte de Markdown (marked no lo hace dentro de un bloque HTML)
    assert "${marked.parse(body)}" in _funcion_js(_app_js(client), "parseMarkdownAlerts")


def test_la_app_y_el_mapa_solo_se_hablan_con_su_mismo_origen(client):
    js = _app_js(client)
    assert "postMessage({ type: 'dag-highlight-topic', topicId: state.selectedGraphNodeId, center: true }, window.location.origin)" in js
    assert "if (ev.origin !== window.location.origin || !ev.data || ev.data.type !== 'dag-select-topic') return;" in js

    roadmap_id = client.post("/api/roadmap", json={"titulo": "R", "modulos": [{"titulo": "M", "temas": [{"titulo": "T"}]}]}).json()["id"]
    mapa = client.get(f"/api/roadmap/{roadmap_id}/interactive-map").text
    assert "postMessage({ type: 'dag-select-topic', topicId: topicId }, window.location.origin)" in mapa
    assert "ev.origin !== window.location.origin" in mapa
    assert ", '*')" not in mapa and ", '*')" not in js


def test_el_panel_de_estado_muestra_lo_que_esta_encendido_de_verdad(client):
    js = _app_js(client)
    html = client.get("/").text
    panel = html[html.index('id="system-health-popover"'):html.index("Verificar conexiones")]

    # Nada fijo en el HTML: lo llena renderSystemHealth con la IA y el índice de la cuenta
    for fijo in ("Conectado", "Listo", "Activos", "768d"):
        assert fijo not in panel
    estado = _funcion_js(js, "renderSystemHealth")
    assert "fetch('/api/config/ia')" in estado and "state.vectorOnline" in estado
    # Sin Drive ni OneDrive, el panel ya no cuenta conectores de nube (048, R12)
    assert "cloudProviders" not in js and "Conectores de nube" not in estado
    assert "encendidos === servicios.length ? 'bg-emerald-400'" in estado
