"""Tests para la feature 055 (arreglos rápidos) y 056-T5 (interfaz sin enServidor, con seTiene y Mis notas)."""

import json
import random
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import administrador_de_prueba, vault_de_prueba
from fastapi.testclient import TestClient
from front import js_del_front

from aulento.core.ia.anthropic import ProveedorAnthropic
from aulento.core.ia.base import RespuestaHTTP
from aulento.core.materiales import AlmacenDeMateriales
from aulento.db.connection import get_connection
from aulento.db.repository import CursoRepository, PlataformaRepository
from aulento.db.schema import create_schema, seed_plataformas
from aulento.exams.generator import ExamGenerator
from aulento.exams.models import QuestionType
from aulento.mcp.agent import Fragmento, FuenteDelTutor
from aulento.models.curso import CursoCreate, EstadoCurso
from aulento.vault.models import VaultNote
from aulento.web.app import create_app

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def cliente_api(tmp_path, monkeypatch):
    db_file = tmp_path / "test_arreglos.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    create_schema(conn)
    admin = administrador_de_prueba(conn)
    seed_plataformas(conn, admin.id)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mcp_tokens (usuario_id, token_hash, nombre, creado_en) VALUES (?, ?, ?, ?);",
        (admin.id, "test_token_hash_123", "test_token", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    vault_dir = vault_de_prueba(db_file)

    app = create_app()
    client = TestClient(app)
    client.cookies.set("session_token", "token_de_prueba")
    return client, db_file, admin.id, vault_dir


# -----------------------------------------------------------------------------
# R1 / T1: Sync sin porcentaje no cambia el avance
# -----------------------------------------------------------------------------


def test_t1_sync_sin_porcentaje_con_datos_viejos_no_cambia_avance(cliente_api):
    client, db_file, user_id, _ = cliente_api
    conn = get_connection(db_file)
    c_repo = CursoRepository(conn, user_id)
    p_repo = PlataformaRepository(conn, user_id)
    plat = p_repo.list_all()[0]

    # Curso con 40% y datos viejos en sync_config_json que tienen 0%
    curso = c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Curso Avanzado de Prueba",
            url_aula="https://aula.example.com",
            progreso_pct=40.0,
            estado=EstadoCurso.EN_CURSO,
            sync_config_json=json.dumps({"progreso_pct": 0.0, "completed_labs": 0, "total_labs": 10}),
        )
    )
    conn.close()

    # POST con payload vacío {}
    resp = client.post(f"/api/hub/courses/{curso.id}/sync", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["progreso_pct"] == 40.0
    assert data["estado"] == "en_curso"
    assert "Sin cambios" in data["mensaje"]

    # Verificar en DB que sigue en 40%
    conn2 = get_connection(db_file)
    actualizado = CursoRepository(conn2, user_id).get_by_id(curso.id)
    conn2.close()
    assert actualizado.progreso_pct == 40.0
    assert actualizado.estado == EstadoCurso.EN_CURSO


def test_t1_sync_sin_porcentaje_sin_datos_viejos_no_cambia_avance(cliente_api):
    client, db_file, user_id, _ = cliente_api
    conn = get_connection(db_file)
    c_repo = CursoRepository(conn, user_id)
    p_repo = PlataformaRepository(conn, user_id)
    plat = p_repo.list_all()[0]

    # Curso con 40% y sync_config_json None
    curso = c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Curso Sin Config Previa",
            url_aula="https://aula.example.com",
            progreso_pct=40.0,
            estado=EstadoCurso.EN_CURSO,
            sync_config_json=None,
        )
    )
    conn.close()

    # POST con payload vacío {}
    resp = client.post(f"/api/hub/courses/{curso.id}/sync", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["progreso_pct"] == 40.0
    assert data["estado"] == "en_curso"
    assert "Sin cambios" in data["mensaje"]


def test_t1_sync_con_porcentaje_actualiza_correctamente(cliente_api):
    client, db_file, user_id, _ = cliente_api
    conn = get_connection(db_file)
    c_repo = CursoRepository(conn, user_id)
    p_repo = PlataformaRepository(conn, user_id)
    plat = p_repo.list_all()[0]

    curso = c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Curso Para Actualizar",
            url_aula="https://aula.example.com",
            progreso_pct=40.0,
            estado=EstadoCurso.EN_CURSO,
        )
    )
    conn.close()

    # POST con {"progreso_pct": 70}
    resp = client.post(f"/api/hub/courses/{curso.id}/sync", json={"progreso_pct": 70.0})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["progreso_pct"] == 70.0
    assert data["estado"] == "en_curso"


# -----------------------------------------------------------------------------
# R2 / T2: Modales: el último abierto queda adelante
# -----------------------------------------------------------------------------


def test_t2_el_apilado_de_modales_vive_en_au_modal():
    # Con la 072 todo modal es .au-modal y lo apila Au.modal.abrir; el comportamiento lo prueba
    # tests/e2e/test_componentes.py::test_r4_un_modal_abierto_desde_otro_queda_adelante_aunque_este_antes_en_el_dom
    componentes = (Path(__file__).resolve().parents[1] / "src" / "aulento" / "web" / "static" / "componentes.js").read_text(encoding="utf-8")
    assert "el.style.zIndex = String(50 + abiertos.length)" in componentes
    # El observador viejo miraba la clase hidden de los .fixed.inset-0: ya no queda ninguno que mirar
    assert "initModalZIndexObserver" not in js_del_front()


# -----------------------------------------------------------------------------
# R3 / T3: Examen con opciones mezcladas y sin onclick con datos
# -----------------------------------------------------------------------------


def test_t3_examen_opciones_mezcladas_varias_semillas():
    note = VaultNote(
        id="nota-prueba",
        title="Star Schema Dimensional Modeling",
        folder="Cursos",
        path="04 Knowledge/Cursos/nota-prueba.md",
        content="Contenido de prueba sobre star schema y fact tables",
        clean_text="Contenido de prueba sobre star schema y fact tables",
        headings=["Tablas de Hechos"],
        wikilinks=[],
    )

    generator = ExamGenerator(vault_reader=None)

    # Con varias semillas, la respuesta correcta no debe quedar siempre en la posición 0
    posiciones = []
    for seed in range(20):
        random.seed(seed)
        exam = generator.generate_exam_for_note(note, question_types=[QuestionType.MULTIPLE_CHOICE], count=1)
        q = exam.questions[0]
        pos = q.options.index(q.correct_answer)
        posiciones.append(pos)

    # Al menos dos posiciones distintas deben aparecer
    posiciones_unicas = set(posiciones)
    assert len(posiciones_unicas) > 1, f"Las opciones no variaron de posición: {posiciones}"
    assert any(p != 0 for p in posiciones), "La respuesta correcta quedó siempre en la posición 0"


def test_t3_app_js_sin_onclick_con_datos_en_examen():
    content = js_del_front()

    # No debe haber onclick con explanation ni encodeURIComponent en el examen
    assert 'onclick="selectQuizOption(this,' not in content
    assert "encodeURIComponent(q.explanation)" not in content
    # El botón usa la acción delegada y data-q
    assert 'data-accion="elegir-opcion-quiz"' in content
    # Y la explicación se muestra escapada
    assert "escapeHtml(explanation)" in content


# -----------------------------------------------------------------------------
# R4 / T4: Similitud aparte del curso en las fuentes del tutor
# -----------------------------------------------------------------------------


def test_t4_similitud_en_fuente_del_tutor_y_no_en_course_hint(cliente_api):
    client, _db_file, _user_id, vault_dir = cliente_api

    fragmento = Fragmento(
        nombre="[MATERIAL] Apunte de Redes",
        origen="vector",
        texto="Texto recuperado sobre arquitectura",
        material_id=1,
        pista=None,
        similitud=0.88,
    )
    fuente = FuenteDelTutor(
        material_id=fragmento.material_id,
        name=fragmento.nombre,
        provider=fragmento.origen,
        course_hint=fragmento.pista,
        relevance_snippet="Texto recuperado",
        similitud=fragmento.similitud,
    )

    assert fuente.similitud == 0.88
    assert fuente.course_hint is None or "Similitud" not in fuente.course_hint

    # Guardar nota desde el tutor no debe crear curso ni carpeta con 'Similitud'
    resp = client.post(
        "/api/mcp/agent/save-note",
        json={
            "title": "Nota desde Tutor",
            "content": "# Síntesis",
            "folder": fuente.course_hint,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    rel_path = data.get("relative_path", "")
    assert "Similitud" not in rel_path

    # Verificar que en el vault no se creó ninguna carpeta llamada Similitud
    carpetas = [p.name for p in vault_dir.glob("**/*") if p.is_dir()]
    assert not any("similitud" in c.lower() for c in carpetas)


# -----------------------------------------------------------------------------
# R5 / T5: Previsualizar un apunte no escribe
# -----------------------------------------------------------------------------


def test_t5_previsualizar_apunte_no_crea_cursos_ni_archivos(cliente_api):
    client, db_file, user_id, vault_dir = cliente_api
    conn = get_connection(db_file)
    c_repo = CursoRepository(conn, user_id)
    cursos_antes = len(c_repo.list_all())
    conn.close()

    archivos_antes = len(list(vault_dir.glob("**/*")))

    # Crear material en la cuenta
    conn_mat = get_connection(db_file)
    almacen = AlmacenDeMateriales(conn_mat, user_id)
    mat = almacen.guardar("Material Huérfano Sin Curso.txt", b"Texto sobre algoritmos distribuidos.")
    conn_mat.close()

    # Previsualizar apunte (save_to_vault=False)
    resp = client.post(
        "/api/vault/notes/from-material?save_to_vault=false",
        json={"material_id": mat["id"], "topic": "Algoritmos Distribuidos"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "preview"

    # Verificar que la cantidad de cursos en DB y archivos en vault no cambió
    conn2 = get_connection(db_file)
    cursos_despues = len(CursoRepository(conn2, user_id).list_all())
    conn2.close()
    assert cursos_despues == cursos_antes

    archivos_despues = len(list(vault_dir.glob("**/*")))
    assert archivos_despues == archivos_antes


# -----------------------------------------------------------------------------
# R6 y R7 / T6: Botones de IA y paginación de modelos
# -----------------------------------------------------------------------------


def test_t6_botones_ia_arrancan_ocultos_en_html():
    html_path = Path("src/aulento/web/static/index.html")
    content = html_path.read_text(encoding="utf-8")

    for btn_id in [
        "btn-config-test-anthropic",
        "btn-config-remove-anthropic",
        "btn-config-models-anthropic",
        "btn-config-test-openai",
        "btn-config-remove-openai",
        "btn-config-models-openai",
        "btn-config-test-gemini",
        "btn-config-remove-gemini",
    ]:
        match = re.search(rf'id="{btn_id}"[^>]*class="([^"]*)"', content)
        if not match:
            # Atributos en orden invertido class="..." id="..."
            match = re.search(rf'class="([^"]*)"[^>]*id="{btn_id}"', content)
        assert match is not None, f"Botón {btn_id} no encontrado en index.html"
        assert "hidden" in match.group(1).split(), f"El botón {btn_id} no arranca con clase hidden"


def test_t6_anthropic_modelos_pagina_hasta_el_final():
    adaptador = ProveedorAnthropic()

    # Simular un cliente HTTP que devuelve 3 páginas
    paginas = [
        {"data": [{"id": f"claude-pag1-{i}"} for i in range(20)], "has_more": True, "last_id": "claude-pag1-19"},
        {"data": [{"id": f"claude-pag2-{i}"} for i in range(20)], "has_more": True, "last_id": "claude-pag2-19"},
        {"data": [{"id": f"claude-pag3-{i}"} for i in range(5)], "has_more": False, "last_id": "claude-pag3-4"},
    ]

    mock_get = MagicMock()
    mock_get.side_effect = [
        RespuestaHTTP(datos=paginas[0], latencia_ms=10.0),
        RespuestaHTTP(datos=paginas[1], latencia_ms=10.0),
        RespuestaHTTP(datos=paginas[2], latencia_ms=10.0),
    ]

    adaptador._get = mock_get

    modelos = adaptador.modelos("test-key")
    assert len(modelos) == 45
    assert "claude-pag1-0" in modelos
    assert "claude-pag2-10" in modelos
    assert "claude-pag3-4" in modelos
    assert mock_get.call_count == 3


def test_t6_app_js_sin_prompt_para_modelos():
    content = js_del_front()

    # Extraer la función fetchProviderModelsUI
    idx_fn = content.find("function fetchProviderModelsUI")
    assert idx_fn != -1
    bloque = content[idx_fn : idx_fn + 1500]
    assert "prompt(" not in bloque
    assert "actualizarBotonesDeProveedor" in content


# -----------------------------------------------------------------------------
# 056-T5: app.js sin enServidor, con seTiene, Mis notas y modal webhook
# -----------------------------------------------------------------------------


def test_056_t5_app_js_limpio_de_en_servidor_y_vault():
    content = js_del_front()

    # No debe tener enServidor ni aplicarModoDeDespliegue
    assert "function enServidor()" not in content
    assert "HOSTS_DE_ESTA_MAQUINA" not in content
    assert "function aplicarModoDeDespliegue()" not in content
    assert "window.location.hostname" not in content

    # No debe decir 'Vault de Obsidian' ni 'tu Vault'
    assert "Vault de Obsidian" not in content
    assert "vault de obsidian" not in content.lower()
    assert "tu vault" not in content.lower()

    # showCourseWebhookModal no debe usar alert
    idx_webhook = content.find("function showCourseWebhookModal")
    assert idx_webhook != -1
    bloque_webhook = content[idx_webhook : idx_webhook + 1200]
    assert "alert(" not in bloque_webhook
    assert "modal-course-webhook" in bloque_webhook


def test_r4_busqueda_semantica_real_separa_similitud_del_curso(monkeypatch):
    """R4: el camino real del tutor no pone el porcentaje de similitud como curso."""
    from aulento.mcp import agent as modulo_agente

    class RagFalso:
        def __init__(self, user_id):
            pass

        def is_ready(self):
            return True

        def search(self, **_):
            return [{"source_type": "curso", "source_id": "x", "source_title": "Ficha", "chunk_text": "t", "similarity": 0.88}]

    monkeypatch.setattr(modulo_agente, "KnowledgeRAGService", RagFalso)
    tutor = modulo_agente.TutorDeMateriales.__new__(modulo_agente.TutorDeMateriales)
    tutor.user_id = 1
    fragmentos = tutor._busqueda_semantica("consulta", modulo_agente.ORIGEN_VECTORIAL, 5)
    assert fragmentos and fragmentos[0].similitud == pytest.approx(0.88)
    assert "Similitud" not in (fragmentos[0].pista or "")


def test_056_r7_cada_bloque_mcp_depende_de_su_capacidad():
    """056 R7 y 058 R6: la config de escritorio y la remota se muestran solo con su capacidad."""
    html = (RAIZ / "src/aulento/web/static/index.html").read_text(encoding="utf-8")
    assert re.search(r'<div id="mcp-connect-body"[^>]*data-requiere="mcp_escritorio"', html)
    assert re.search(r'<div id="mcp-remoto-body"[^>]*data-requiere="mcp_web"', html)
    assert ":8100" not in html


def test_056_r5_app_js_no_muestra_vault_en_textos_visibles():
    """056 R5: los textos que ve la persona en app.js dicen 'Mis notas', no 'Vault'."""
    js = js_del_front()
    visibles = [
        linea for linea in js.splitlines()
        if re.search(r"\bVault\b", linea) and re.search(r"alert\(|textContent|placeholder|innerHTML|<option", linea)
    ]
    assert visibles == []


def test_056_r8_boton_google_libros_de_biblioteca_vacia_respeta_capacidad():
    """056 R8: el botón de Google Libros que dibuja app.js se muestra solo con la capacidad."""
    js = js_del_front()
    posiciones = [m.start() for m in re.finditer(r"accion:\s*['\"]sincronizar-google-libros['\"]", js)]
    assert len(posiciones) > 0, "debe encontrar el botón de sincronización de Google Libros"
    for posicion in posiciones:
        assert "seTiene('google_libros')" in js[posicion - 200 : posicion]
