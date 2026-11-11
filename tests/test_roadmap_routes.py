"""Tests para los endpoints REST de Rutas de Aprendizaje, Gap Analysis y Lesson Studio."""

import json

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from ia_falsa import ia_sustituida, respuesta_de
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "web_roadmap_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))

    conn = get_connection(db_file)
    init_db(conn)
    conn.close()

    app = create_app()
    return TestClient(app)


def test_roadmap_templates_and_create(client):
    # 1. Templates
    r_tmpl = client.get("/api/roadmap/templates")
    assert r_tmpl.status_code == 200
    templates = r_tmpl.json()
    assert len(templates) >= 4

    # 2. Create from template
    first_tmpl = templates[0]
    r_create = client.post("/api/roadmap", json=first_tmpl)
    assert r_create.status_code == 200
    created = r_create.json()
    assert created["id"] is not None
    assert len(created["modulos"]) >= 3

    # 3. List
    r_list = client.get("/api/roadmap")
    assert r_list.status_code == 200
    roadmaps = r_list.json()
    assert len(roadmaps) == 1
    assert roadmaps[0]["id"] == created["id"]


def test_roadmap_topic_status_and_prompt(client):
    # Crear ruta simple
    payload = {
        "titulo": "Lakehouse Architect",
        "modulos": [
            {
                "titulo": "Storage Layer",
                "temas": [
                    {"titulo": "Apache Iceberg Specs"},
                    {"titulo": "Delta Lake Protocols"},
                ],
            }
        ],
    }
    r = client.post("/api/roadmap", json=payload)
    created = r.json()
    topic_id = created["modulos"][0]["temas"][0]["id"]

    # 1. Build Master Prompt
    r_prompt = client.post(
        f"/api/roadmap/topics/{topic_id}/build-prompt",
        json={"include_materials": True, "target_llm": "notebooklm"},
    )
    assert r_prompt.status_code == 200
    res_prompt = r_prompt.json()
    assert "Apache Iceberg Specs" in res_prompt["master_prompt"]
    assert "Tus materiales en Aulento" in res_prompt["master_prompt"]

    # 2. Update status
    r_status = client.post(
        f"/api/roadmap/topics/{topic_id}/status",
        json={"estado": "completado"},
    )
    assert r_status.status_code == 200
    assert r_status.json()["estado"] == "completado"

    # Verificar progreso de la ruta
    r_get = client.get(f"/api/roadmap/{created['id']}")
    assert r_get.status_code == 200
    assert r_get.json()["progreso_pct"] == 50.0


def test_generate_and_import_lesson(client):
    payload = {
        "titulo": "FastAPI Master",
        "modulos": [
            {
                "titulo": "Routing",
                "temas": [{"titulo": "Pydantic Models Validation"}],
            }
        ],
    }
    r = client.post("/api/roadmap", json=payload)
    topic_id = r.json()["modulos"][0]["temas"][0]["id"]

    # 1. Generate lesson in-app
    with ia_sustituida(sin_clave=True):
        r_gen = client.post(f"/api/roadmap/topics/{topic_id}/generate-lesson")
        assert r_gen.status_code == 200
        lesson = r_gen.json()
        assert lesson["tema_id"] == topic_id
        assert len(lesson["diagramas_mermaid"]) >= 1

        # 2. Export to FSRS
        lesson_id = lesson["id"]
        r_fsrs = client.post(f"/api/roadmap/lessons/{lesson_id}/export-fsrs")
        assert r_fsrs.status_code == 200
        assert r_fsrs.json()["cards_exported"] >= 1

        # 3. Export to Vault
        r_vault = client.post(f"/api/roadmap/lessons/{lesson_id}/export-vault")
        assert r_vault.status_code == 200
        assert "vault_path" in r_vault.json()


def test_compare_pdf_and_merge(client):
    payload = {
        "titulo": "DevOps Cloud",
        "modulos": [
            {
                "titulo": "IaC",
                "temas": [{"titulo": "Terraform Core"}],
            }
        ],
    }
    r = client.post("/api/roadmap", json=payload)
    roadmap_id = r.json()["id"]

    # Dummy PDF
    dummy_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Length 80 >> stream\n"
        b"BT\n"
        b"(Terraform State Lock) Tj\n"
        b"(Ansible Playbooks Automation) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"%%EOF"
    )
    files = {"file": ("syllabus.pdf", dummy_pdf, "application/pdf")}
    with ia_sustituida(sin_clave=True):
        r_cmp = client.post(f"/api/roadmap/{roadmap_id}/compare-pdf", files=files)
        assert r_cmp.status_code == 200
        gap_res = r_cmp.json()
        assert len(gap_res["gap_topics"]) >= 1

        # Merge
        r_merge = client.post(
            f"/api/roadmap/{roadmap_id}/merge",
            json={"gap_topics": gap_res["gap_topics"]},
        )
        assert r_merge.status_code == 200
        assert r_merge.json()["inserted_topics"] >= 1

    # Verificar expansión
    r_detail = client.get(f"/api/roadmap/{roadmap_id}")
    assert len(r_detail.json()["modulos"]) == 2


def test_delete_roadmap(client):
    payload = {
        "titulo": "Temporary Route",
        "modulos": [{"titulo": "Mod 1", "temas": [{"titulo": "Topic 1"}]}],
    }
    r = client.post("/api/roadmap", json=payload)
    roadmap_id = r.json()["id"]

    # Delete
    r_del = client.delete(f"/api/roadmap/{roadmap_id}")
    assert r_del.status_code == 200
    assert r_del.json()["status"] == "ok"

    # Confirm it's gone
    r_get = client.get(f"/api/roadmap/{roadmap_id}")
    assert r_get.status_code == 404


# --- R5 / R9 / R10 / R11: perfil pedagógico, alcance y expansión por API ---

def _crear_ruta(client, titulo="Filosofía estoica", metadata=None, temas=("La dicotomía del control",)):
    payload = {
        "titulo": titulo,
        "metadata_json": metadata or {},
        "modulos": [{"titulo": "Ética", "temas": [{"titulo": t} for t in temas]}],
    }
    r = client.post("/api/roadmap", json=payload)
    assert r.status_code == 200
    return r.json()


def _perfil_editado(n_secciones=3):
    return {
        "disciplina": "Estoicismo romano",
        "arquetipo": "humanidades",
        "rol_docente": "Tutor de lectura lenta",
        "secciones": [{"titulo": f"Paso {i}", "instruccion": f"Consigna {i}"} for i in range(1, n_secciones + 1)],
        "usa_codigo": False,
        "usa_diagramas": False,
        "tipo_fuentes": "Epicteto, Séneca y Marco Aurelio",
        "flashcards_ejemplo": [{"pregunta": "¿Qué es la prohairesis?", "respuesta": "La facultad de elección."}],
        "origen": "ia",
    }


def test_get_perfil_resuelve_arquetipo_para_ruta_sin_perfil(client):
    created = _crear_ruta(client)
    assert "perfil_pedagogico" not in created["metadata_json"]

    r = client.get(f"/api/roadmap/{created['id']}/pedagogical-profile")
    assert r.status_code == 200
    perfil = r.json()
    assert perfil["arquetipo"] == "humanidades"
    assert perfil["origen"] == "arquetipo"
    assert perfil["disciplina"] == "Filosofía estoica"
    assert perfil["usa_codigo"] is False
    assert [s["titulo"] for s in perfil["secciones"]][:2] == ["Problema y contexto", "Texto o autor primario"]

    # Consultar no persiste nada.
    assert "perfil_pedagogico" not in client.get(f"/api/roadmap/{created['id']}").json()["metadata_json"]


def test_put_perfil_guarda_y_marca_origen_editado(client):
    created = _crear_ruta(client, metadata={"alcance": "curso", "aviso": "x"})
    roadmap_id = created["id"]

    r_put = client.put(f"/api/roadmap/{roadmap_id}/pedagogical-profile", json=_perfil_editado(4))
    assert r_put.status_code == 200
    assert r_put.json()["origen"] == "editado"

    guardado = client.get(f"/api/roadmap/{roadmap_id}/pedagogical-profile").json()
    assert guardado["origen"] == "editado"
    assert guardado["disciplina"] == "Estoicismo romano"
    assert [s["titulo"] for s in guardado["secciones"]] == ["Paso 1", "Paso 2", "Paso 3", "Paso 4"]

    # El resto del metadata de la ruta se conserva.
    meta = client.get(f"/api/roadmap/{roadmap_id}").json()["metadata_json"]
    assert meta["alcance"] == "curso"
    assert meta["aviso"] == "x"
    assert meta["perfil_pedagogico"]["rol_docente"] == "Tutor de lectura lenta"

    # Y el Prompt Maestro pasa a usar el perfil editado.
    topic_id = created["modulos"][0]["temas"][0]["id"]
    prompt = client.post(f"/api/roadmap/topics/{topic_id}/build-prompt", json={}).json()["master_prompt"]
    assert "### 4. Paso 4" in prompt
    assert "Tutor de lectura lenta" in prompt
    assert "Problema y contexto" not in prompt


@pytest.mark.parametrize("n_secciones", [0, 2, 9])
def test_put_perfil_con_cantidad_invalida_de_secciones_devuelve_422(client, n_secciones):
    created = _crear_ruta(client)
    r = client.put(f"/api/roadmap/{created['id']}/pedagogical-profile", json=_perfil_editado(n_secciones))
    assert r.status_code == 422
    assert "perfil_pedagogico" not in client.get(f"/api/roadmap/{created['id']}").json()["metadata_json"]


def test_put_perfil_con_texto_en_blanco_devuelve_422(client):
    created = _crear_ruta(client)
    perfil = _perfil_editado()
    perfil["secciones"][0]["titulo"] = "   "
    r = client.put(f"/api/roadmap/{created['id']}/pedagogical-profile", json=perfil)
    assert r.status_code == 422
    assert "perfil_pedagogico" not in client.get(f"/api/roadmap/{created['id']}").json()["metadata_json"]


def test_generate_sin_categoria_usa_el_valor_neutro(client):
    with ia_sustituida(sin_clave=True):
        r = client.post("/api/roadmap/generate", json={"prompt": "Apicultura urbana", "target_role": "Apicultura urbana"})
    assert r.status_code == 200
    created = r.json()
    assert created["categoria"] == "general"
    assert created["metadata_json"]["perfil_pedagogico"]["arquetipo"] == "general"


def test_perfil_de_ruta_inexistente_devuelve_404(client):
    assert client.get("/api/roadmap/9999/pedagogical-profile").status_code == 404
    assert client.put("/api/roadmap/9999/pedagogical-profile", json=_perfil_editado()).status_code == 404


def test_generate_sin_ia_devuelve_aviso_y_alcance(client):
    with ia_sustituida(sin_clave=True):
        r = client.post(
            "/api/roadmap/generate",
            json={"prompt": "Filosofía estoica", "target_role": "Filosofía estoica", "categoria": "general", "alcance": "especializacion"},
        )
    assert r.status_code == 200
    created = r.json()
    meta = created["metadata_json"]
    assert meta["origen"] == "domain_fallback"
    assert "sin IA" in meta["aviso"]
    assert meta["alcance"] == "especializacion"
    assert meta["perfil_pedagogico"]["arquetipo"] == "humanidades"

    # El aviso queda persistido, no solo en la respuesta de creación.
    assert client.get(f"/api/roadmap/{created['id']}").json()["metadata_json"]["aviso"] == meta["aviso"]


def test_generate_rechaza_alcance_desconocido(client):
    r = client.post("/api/roadmap/generate", json={"prompt": "Álgebra", "alcance": "doctorado"})
    assert r.status_code == 422


def test_expand_sin_ia_devuelve_503_y_no_inserta(client):
    created = _crear_ruta(client, temas=())
    module_id = created["modulos"][0]["id"]

    with ia_sustituida(sin_clave=True):
        r = client.post(f"/api/roadmap/modules/{module_id}/expand")

    assert r.status_code == 503
    assert "Gemini" in r.json()["detail"]
    assert client.get(f"/api/roadmap/{created['id']}").json()["modulos"][0]["temas"] == []


def test_expand_modulo_inexistente_devuelve_404(client):
    assert client.post("/api/roadmap/modules/9999/expand").status_code == 404


def test_expand_con_ia_agrega_temas(client):
    created = _crear_ruta(client, temas=("Virtud",))
    module_id = created["modulos"][0]["id"]
    temas = [{"titulo": t} for t in ["virtud", "Pasiones", "Deber", "Cosmopolitismo", "Destino"]]
    respuesta = respuesta_de(json.dumps({"temas": temas}))
    with ia_sustituida(siempre=respuesta):
        r = client.post(f"/api/roadmap/modules/{module_id}/expand")

    assert r.status_code == 200
    assert [t["titulo"] for t in r.json()] == ["Pasiones", "Deber", "Cosmopolitismo", "Destino"]
    modulo = client.get(f"/api/roadmap/{created['id']}").json()["modulos"][0]
    assert [t["titulo"] for t in modulo["temas"]] == ["Virtud", "Pasiones", "Deber", "Cosmopolitismo", "Destino"]


# --- 023: opciones del Prompt Maestro en build-prompt y generate-lesson ---

def test_build_prompt_acepta_las_opciones_de_contenido(client):
    topic_id = _crear_ruta(client, temas=("Virtud", "Pasiones"))["modulos"][0]["temas"][1]["id"]

    r = client.post(
        f"/api/roadmap/topics/{topic_id}/build-prompt",
        json={
            "include_visuals": True,
            "include_slides": True,
            "include_quiz": True,
            "include_glossary": True,
            "include_bridge": True,
            "depth": "exhaustiva",
        },
    )

    assert r.status_code == 200
    prompt = r.json()["master_prompt"]
    for esperado in [
        "```svg",
        "```slides",
        "Autoevaluación",
        "Glosario y lecturas recomendadas",
        "tema anterior, «Virtud»",
        "3500 palabras o más",
    ]:
        assert esperado in prompt


@pytest.mark.parametrize("endpoint", ["build-prompt", "generate-lesson"])
def test_profundidad_desconocida_devuelve_422(client, endpoint):
    created = _crear_ruta(client)
    topic_id = created["modulos"][0]["temas"][0]["id"]

    with ia_sustituida(sin_clave=True):
        r = client.post(f"/api/roadmap/topics/{topic_id}/{endpoint}", json={"depth": "enciclopedica"})

    assert r.status_code == 422
    tema = client.get(f"/api/roadmap/{created['id']}").json()["modulos"][0]["temas"][0]
    assert tema["clase"] is None


def test_generate_lesson_envia_a_gemini_las_opciones_del_cuerpo_sin_busquedas(client):
    topic_id = _crear_ruta(client)["modulos"][0]["temas"][0]["id"]
    respuesta = respuesta_de("# La dicotomía del control\n\nClase.\n\n```cards-fsrs\nQ: ¿Qué depende de nosotros?\nA: Nuestros juicios.\n```")
    with ia_sustituida(siempre=respuesta) as mock_gen:
        r = client.post(
            f"/api/roadmap/topics/{topic_id}/generate-lesson",
            json={
                "include_materials": True,
                "include_web_research": True,
                "target_llm": "claude",
                "include_visuals": True,
                "include_slides": True,
                "depth": "breve",
            },
        )

    assert r.status_code == 200
    enviado = mock_gen.call_args.args[0].usuario
    assert "```svg" in enviado
    assert "```slides" in enviado
    assert "entre 600 y 900 palabras" in enviado
    assert "materials_search" not in enviado
    assert "Investigación Web" not in enviado
    assert "no inventes citas" in enviado


def test_generate_lesson_devuelve_503_y_conserva_la_clase_existente(client):
    created = _crear_ruta(client)
    topic_id = created["modulos"][0]["temas"][0]["id"]
    importada = client.post(
        f"/api/roadmap/topics/{topic_id}/import-lesson",
        json={"markdown_content": "# Clase previa\n\nContenido que no debe perderse.", "origen": "external"},
    )
    assert importada.status_code == 200

    with ia_sustituida(sin_clave=True):
        r = client.post(f"/api/roadmap/topics/{topic_id}/generate-lesson")

    assert r.status_code == 503
    assert "Se conservó la clase" in r.json()["detail"]
    tema = client.get(f"/api/roadmap/{created['id']}").json()["modulos"][0]["temas"][0]
    assert "Contenido que no debe perderse." in tema["clase"]["contenido_markdown"]


# --- 024 · R4 / R7 / R10: validación de prelaciones, alta en bloque y ajustes del grafo por API ---

def _ruta_abc(client, titulo="Lógica", metadata=None):
    created = _crear_ruta(client, titulo=titulo, metadata=metadata, temas=("A", "B", "C"))
    return created["id"], *[t["id"] for t in created["modulos"][0]["temas"]]


def _prelacion(origen, destino, tipo="estricta"):
    return {"tema_origen_id": origen, "tema_destino_id": destino, "tipo": tipo}


def _guardadas(client, ruta_id):
    aristas = client.get(f"/api/roadmap/{ruta_id}/graph").json()["edges"]
    return [(e["tema_origen_id"], e["tema_destino_id"], e["tipo"]) for e in aristas if not e["inferida"]]


def test_post_prelacion_con_tema_de_otra_ruta_o_autorreferencia_devuelve_400(client):
    ruta_id, a, b, _ = _ruta_abc(client)
    _, ajeno, *_ = _ruta_abc(client, titulo="Otra ruta")

    for origen, destino in [(a, ajeno), (ajeno, b), (a, a)]:
        r = client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(origen, destino))
        assert r.status_code == 400, (origen, destino)
    assert "no pertenece a la ruta" in client.post(
        f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(a, ajeno)
    ).json()["detail"]
    assert _guardadas(client, ruta_id) == []


def test_post_prelacion_que_cierra_ciclo_devuelve_409_y_no_guarda(client):
    ruta_id, a, b, c = _ruta_abc(client)
    assert client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(a, b)).status_code == 200
    assert client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(b, c)).status_code == 200

    directo = client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(b, a))
    indirecto = client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(c, a))

    assert directo.status_code == 409
    assert indirecto.status_code == 409
    assert "ciclo" in indirecto.json()["detail"]
    assert _guardadas(client, ruta_id) == [(a, b, "estricta"), (b, c, "estricta")]


def test_post_prelacion_repetida_actualiza_el_tipo_y_tipo_desconocido_devuelve_422(client):
    ruta_id, a, b, _ = _ruta_abc(client)
    client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(a, b))

    r = client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(a, b, "recomendada"))
    assert r.status_code == 200
    assert _guardadas(client, ruta_id) == [(a, b, "recomendada")]

    assert client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(a, b, "opcional")).status_code == 422
    assert _guardadas(client, ruta_id) == [(a, b, "recomendada")]


def test_bulk_valido_guarda_todas_y_aplica_la_secuencia_implicita(client):
    ruta_id, a, b, c = _ruta_abc(client, metadata={"alcance": "curso"})

    r = client.post(
        f"/api/roadmap/{ruta_id}/prerequisites/bulk",
        json={"prelaciones": [_prelacion(a, c), _prelacion(a, b, "recomendada")], "secuencia_implicita": False},
    )

    assert r.status_code == 200
    assert r.json() == {"status": "ok", "guardadas": 2}
    grafo = client.get(f"/api/roadmap/{ruta_id}/graph").json()
    assert grafo["secuencia_implicita"] is False
    assert [(e["tema_origen_id"], e["tema_destino_id"], e["tipo"], e["inferida"]) for e in grafo["edges"]] == [
        (a, c, "estricta", False),
        (a, b, "recomendada", False),
    ]
    assert client.get(f"/api/roadmap/{ruta_id}").json()["metadata_json"] == {
        "alcance": "curso",
        "grafo": {"secuencia_implicita": False},
    }


def test_bulk_sin_secuencia_implicita_no_toca_el_ajuste(client):
    ruta_id, a, b, _ = _ruta_abc(client)
    r = client.post(f"/api/roadmap/{ruta_id}/prerequisites/bulk", json={"prelaciones": [_prelacion(a, b)]})
    assert r.status_code == 200
    assert "grafo" not in client.get(f"/api/roadmap/{ruta_id}").json()["metadata_json"]
    assert client.get(f"/api/roadmap/{ruta_id}/graph").json()["secuencia_implicita"] is True


@pytest.mark.parametrize(
    "invalida, status",
    [("ciclo", 409), ("ajeno", 400), ("autorreferencia", 400)],
)
def test_bulk_con_una_invalida_no_guarda_ninguna_ni_cambia_el_ajuste(client, invalida, status):
    ruta_id, a, b, c = _ruta_abc(client)
    ultima = {"ciclo": _prelacion(c, a), "ajeno": _prelacion(a, 9999), "autorreferencia": _prelacion(b, b)}[invalida]

    r = client.post(
        f"/api/roadmap/{ruta_id}/prerequisites/bulk",
        json={"prelaciones": [_prelacion(a, b), _prelacion(b, c), ultima], "secuencia_implicita": False},
    )

    assert r.status_code == status
    assert _guardadas(client, ruta_id) == []
    assert client.get(f"/api/roadmap/{ruta_id}/graph").json()["secuencia_implicita"] is True


def test_bulk_vacio_o_con_tipo_desconocido_devuelve_422(client):
    ruta_id, a, b, _ = _ruta_abc(client)
    assert client.post(f"/api/roadmap/{ruta_id}/prerequisites/bulk", json={"prelaciones": []}).status_code == 422
    r = client.post(f"/api/roadmap/{ruta_id}/prerequisites/bulk", json={"prelaciones": [_prelacion(a, b, "opcional")]})
    assert r.status_code == 422
    assert _guardadas(client, ruta_id) == []


def test_put_graph_settings_conserva_el_perfil_pedagogico(client):
    ruta_id, *_ = _ruta_abc(client, metadata={"alcance": "curso", "aviso": "x"})
    assert client.put(f"/api/roadmap/{ruta_id}/pedagogical-profile", json=_perfil_editado()).status_code == 200
    antes = client.get(f"/api/roadmap/{ruta_id}").json()["metadata_json"]

    r = client.put(f"/api/roadmap/{ruta_id}/graph-settings", json={"secuencia_implicita": False})

    assert r.status_code == 200
    assert r.json() == {"status": "ok", "secuencia_implicita": False}
    despues = client.get(f"/api/roadmap/{ruta_id}").json()["metadata_json"]
    assert despues == {**antes, "grafo": {"secuencia_implicita": False}}
    assert despues["perfil_pedagogico"]["rol_docente"] == "Tutor de lectura lenta"
    grafo = client.get(f"/api/roadmap/{ruta_id}/graph").json()
    assert grafo["secuencia_implicita"] is False
    assert grafo["edges"] == []

    assert client.put(f"/api/roadmap/{ruta_id}/graph-settings", json={"secuencia_implicita": True}).status_code == 200
    assert len(client.get(f"/api/roadmap/{ruta_id}/graph").json()["edges"]) == 2


def test_put_graph_settings_de_ruta_inexistente_o_cuerpo_invalido(client):
    assert client.put("/api/roadmap/9999/graph-settings", json={"secuencia_implicita": False}).status_code == 404
    ruta_id, *_ = _ruta_abc(client)
    assert client.put(f"/api/roadmap/{ruta_id}/graph-settings", json={}).status_code == 422


def test_graph_devuelve_datos_por_nodo_y_disponibles(client):
    ruta_id, a, b, c = _ruta_abc(client)
    client.post(f"/api/roadmap/{ruta_id}/prerequisites", json=_prelacion(a, c, "recomendada"))

    grafo = client.get(f"/api/roadmap/{ruta_id}/graph").json()
    nodos = {n["id"]: n for n in grafo["nodes"]}

    assert grafo["topological_order"] == [a, b, c]
    # La recomendada A⇢C no bloquea ni reemplaza la secuencia: C sigue dependiendo de B.
    assert grafo["disponibles"] == [a]
    assert nodos[a]["dependents"] == [b, c] and nodos[a]["prerequisites"] == []
    assert nodos[c]["prerequisites"] == [a, b] and nodos[c]["disponible"] is False
    assert nodos[b]["is_blocked"] is True and nodos[b]["disponible"] is False
    assert nodos[b]["nivel_topologico"] == 1 and nodos[c]["nivel_topologico"] == 2


def test_prelaciones_de_una_ruta_inexistente_devuelven_404(client):
    ruta_id, a, b, _ = _ruta_abc(client)
    assert client.post("/api/roadmap/9999/prerequisites", json=_prelacion(a, b)).status_code == 404
    r = client.post("/api/roadmap/9999/prerequisites/bulk", json={"prelaciones": [_prelacion(a, b)]})
    assert r.status_code == 404
    assert client.get(f"/api/roadmap/{ruta_id}/graph").json()["edges"][0]["inferida"] is True


def test_bulk_guarda_prelaciones_y_ajuste_en_la_misma_transaccion(client):
    ruta_id, a, _, c = _ruta_abc(client)
    r = client.post(
        f"/api/roadmap/{ruta_id}/prerequisites/bulk",
        json={"prelaciones": [_prelacion(a, c)], "secuencia_implicita": False},
    )
    assert r.status_code == 200
    grafo = client.get(f"/api/roadmap/{ruta_id}/graph").json()
    assert grafo["secuencia_implicita"] is False
    assert [(e["tema_origen_id"], e["tema_destino_id"], e["inferida"]) for e in grafo["edges"]] == [(a, c, False)]
