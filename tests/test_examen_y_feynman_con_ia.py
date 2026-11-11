"""Pruebas para Feature 060: Examen y Simulador Feynman con IA (R1 a R7).

Verifica la generación con IA, la degradación sin IA rotulada, la evaluación de respuestas
abiertas, los cinco criterios Feynman y la ausencia de temas personales fijos.
"""

import json

from conftest import vault_de_prueba
from fastapi.testclient import TestClient
from front import js_del_front
from ia_falsa import ia_sustituida, respuesta_de

from aulento.core.materiales import AlmacenDeMateriales
from aulento.exams.feynman import ejemplos_feynman
from aulento.exams.generator import ExamGenerator
from aulento.vault.reader import VaultReader, sembrar_notas_de_muestra
from aulento.web.app import app

client = TestClient(app)


def test_r1_examen_con_ia_genera_preguntas_con_explicacion_y_fragmento(isolated_cloud_env, cuenta):
    """R1: Con clave de IA, genera preguntas a partir del texto con explicación y fragmento."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)

    ia_mock_json = {
        "questions": [
            {
                "topic": "Sistemas Distribuidos",
                "question_type": "multiple_choice",
                "prompt": "¿Qué garantiza el teorema CAP según el material?",
                "options": [
                    "No se pueden garantizar Consistencia, Disponibilidad y Tolerancia a particiones a la vez",
                    "Que todo nodo procesa en paralelo sin bloqueo",
                    "Que la red nunca pierde paquetes",
                    "Que la latencia siempre es constante",
                ],
                "correct_answer": "No se pueden garantizar Consistencia, Disponibilidad y Tolerancia a particiones a la vez",
                "explanation": "El teorema demuestra la imposibilidad de satisfacer los tres atributos simultáneamente en presencia de particiones.",
                "fragmento": "En un sistema distribuido, solo es posible garantizar dos de las tres propiedades del teorema CAP.",
            },
            {
                "topic": "Particionado",
                "question_type": "open_reasoning",
                "prompt": "Explica la ventaja de podar particiones.",
                "options": [],
                "correct_answer": "Reduce drásticamente el volumen de datos escaneados.",
                "explanation": "Al podar particiones se leen solo los fragmentos relevantes para la consulta.",
                "fragmento": "El podado de particiones descarta los bloques que no cumplen los filtros de fecha.",
            },
        ]
    }

    with ia_sustituida(siempre=respuesta_de(json.dumps(ia_mock_json))):
        res = client.post(
            "/api/exams/generate",
            json={"note_id": "Star Schema y Modelado Dimensional", "question_type": "all", "count": 2},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["sin_ia"] is False
    assert data["rotulo"] is None
    assert data["total_questions"] == 2
    assert len(data["questions"]) == 2

    q1 = data["questions"][0]
    assert q1["explanation"] != ""
    assert q1["fragmento"] is not None
    assert len(q1["options"]) == 4

    q2 = data["questions"][1]
    assert q2["question_type"] == "open_reasoning"
    # Lo que devolvió la IA llega tal cual: explicación y fragmento de cada pregunta
    for q, esperada in zip(data["questions"], ia_mock_json["questions"], strict=True):
        assert q["explanation"] == esperada["explanation"]
        assert q["fragmento"] == esperada["fragmento"]
        assert q["prompt"] == esperada["prompt"]


def test_r1_examen_con_ia_desde_material_subido(isolated_cloud_env, cuenta):
    """R1: El examen se puede generar también a partir de un material subido desde la PC."""
    almacen = AlmacenDeMateriales.con_conexion_propia(cuenta)
    texto_material = "La arquitectura limpia desacopla las reglas de negocio de la infraestructura y frameworks."
    mat = almacen.guardar("arquitectura_limpia.txt", texto_material.encode("utf-8"))

    ia_mock_json = {
        "questions": [
            {
                "topic": "Arquitectura Limpia",
                "question_type": "multiple_choice",
                "prompt": "¿Qué desacopla la arquitectura limpia?",
                "options": ["Reglas de negocio de la infraestructura", "Base de datos de la red", "Frontend del backend", "Memoria de disco"],
                "correct_answer": "Reglas de negocio de la infraestructura",
                "explanation": "Las entidades y casos de uso no deben depender de herramientas externas.",
                "fragmento": "La arquitectura limpia desacopla las reglas de negocio de la infraestructura y frameworks.",
            }
        ]
    }

    with ia_sustituida(siempre=respuesta_de(json.dumps(ia_mock_json))) as modelo:
        res = client.post(
            "/api/exams/generate",
            json={"note_id": f"material:{mat['id']}", "count": 1},
        )
    # El texto del material elegido es el que llega a la IA
    assert texto_material in modelo.call_args.args[0].usuario

    assert res.status_code == 200
    data = res.json()
    assert data["sin_ia"] is False
    assert len(data["questions"]) == 1
    assert "material" in data["questions"][0]["note_id"]


def test_r2_examen_sin_clave_arma_preguntas_del_texto_con_rotulo_sin_ia(isolated_cloud_env, cuenta):
    """R2: Sin clave de IA, el examen se arma con frases del propio texto (completar palabra) y rotulado 'sin IA'."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)

    with ia_sustituida(sin_clave=True):
        res = client.post(
            "/api/exams/generate",
            json={"note_id": "Star Schema y Modelado Dimensional", "question_type": "cloze", "count": 2},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["sin_ia"] is True
    assert data["rotulo"] == "sin IA"
    assert data["total_questions"] >= 1
    for q in data["questions"]:
        assert "[_______]" in q["prompt"]
        assert len(q["correct_answer"]) >= 4
        # Fragmento del texto original
        assert q["fragmento"] is not None
        assert q["correct_answer"].lower() in q["fragmento"].lower()


def test_r2_no_quedan_preguntas_fijas_de_ejemplo():
    """R2: Las preguntas fijas de las 4 notas de ejemplo deben haber desaparecido del código."""
    vault = vault_de_prueba()
    reader = VaultReader(vault)
    generator = ExamGenerator(reader)

    # Creamos un texto completamente nuevo y arbitrario
    nota_arbitraria = type("Nota", (), {
        "title": "Biología Celular",
        "content": "La mitocondria produce trifosfato de adenosina mediante respiración aeróbica celular. Los ribosomas sintetizan proteínas.",
        "id": "bio-1",
        "path": "bio-1.md",
    })()

    exam = generator.generate_exam_for_note(nota_arbitraria, count=2)
    assert exam.sin_ia is True
    assert exam.rotulo == "sin IA"
    # Las preguntas deben ser sobre mitocondrias o ribosomas, no Star Schema ni BigQuery
    for q in exam.questions:
        assert "bigquery" not in q.prompt.lower()
        assert "star schema" not in q.prompt.lower()
        assert "transformer" not in q.prompt.lower()
        assert "webhook" not in q.prompt.lower()
        assert any(palabra in q.fragmento.lower() for palabra in ["mitocondria", "respiración", "ribosomas", "proteínas"])


def test_r3_evaluacion_de_respuesta_abierta_con_ia(isolated_cloud_env, cuenta):
    """R3: Evalúa respuesta abierta con la IA contra el texto y devuelve si es correcta, qué faltó y por qué."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)

    ia_mock_eval = {
        "is_correct": True,
        "score": 90,
        "feedback": "Excelente comprensión del concepto de desnormalización analítica.",
        "what_was_missing": "Faltó contrastarlo con el impacto en operaciones transaccionales.",
    }

    with ia_sustituida(siempre=respuesta_de(json.dumps(ia_mock_eval))):
        res = client.post(
            "/api/exams/evaluate-answer",
            json={
                "note_id": "Star Schema y Modelado Dimensional",
                "question_prompt": "¿Por qué se desnormalizan las dimensiones en un modelo analítico?",
                "user_answer": "Para acelerar las lecturas y reducir la cantidad de JOINs en consultas complejas.",
                "expected_answer": "Reducir JOINs y optimizar consultas analíticas masivas.",
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["is_correct"] is True
    assert data["score"] == 90
    assert "Excelente comprensión" in data["feedback"]
    assert "Faltó contrastarlo" in data["what_was_missing"]
    assert data["sin_ia"] is False
    assert data["rotulo"] is None


def test_r3_evaluacion_de_respuesta_abierta_sin_clave_rotulada(isolated_cloud_env, cuenta):
    """R3 / R2: Sin clave de IA, la respuesta abierta se evalúa con heurística rotulada 'sin IA'."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)

    with ia_sustituida(sin_clave=True):
        res = client.post(
            "/api/exams/evaluate-answer",
            json={
                "note_id": "Star Schema y Modelado Dimensional",
                "question_prompt": "¿Por qué se desnormalizan las dimensiones?",
                "user_answer": "Para acelerar las lecturas analíticas y evitar joins costosos.",
                "expected_answer": "Reducir JOINs y optimizar consultas.",
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["sin_ia"] is True
    assert data["rotulo"] == "sin IA"
    assert isinstance(data["is_correct"], bool)
    assert len(data["feedback"]) > 5


def test_r4_feynman_con_ia_cinco_criterios_con_puntaje_justificado(isolated_cloud_env, cuenta):
    """R4: Con clave de IA evalúa los 5 criterios (precisión, simplicidad, jerga, analogía y huecos) con puntaje justificado."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)

    ia_mock_feynman = {
        "score": 88,
        "mastery_level": "Avanzado",
        "clarity_score": 92,
        "precision_score": 85,
        "jargon_used": ["latencia"],
        "knowledge_gaps": ["No detalló el costo computacional."],
        "strengths": ["Analogía del cartero muy acertada.", "Lenguaje directo y simple."],
        "feedback_summary": "Demuestra un sólido dominio pedagógico de la idea.",
        "suggested_simplification": "Imaginate que en vez de consultar a la cocina cada minuto, suena una campanilla.",
        "criterios": {
            "precision": {"puntaje": 85, "justificacion": "Precisión técnica correcta contrastada con la nota."},
            "simplicidad": {"puntaje": 92, "justificacion": "Lenguaje accesible para principiantes."},
            "jerga": {"puntaje": 80, "justificacion": "Aparición aislada del término 'latencia' sin explicar.", "tecnicismos": ["latencia"]},
            "analogia": {"puntaje": 95, "justificacion": "Uso brillante de la metáfora del cartero."},
            "huecos": {"puntaje": 75, "justificacion": "Faltó comentar el costo de reintentos.", "lagunas": ["Costo de reintentos"]},
        },
    }

    with ia_sustituida(siempre=respuesta_de(json.dumps(ia_mock_feynman))):
        res = client.post(
            "/api/exams/evaluate-feynman",
            json={
                "concept": "Transformers y Atención",
                "explanation": "Es como un reflector que ilumina las palabras que se conectan entre sí en una oración.",
                "target_audience": "principiante",
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["score"] == 88
    assert data["sin_ia"] is False
    assert data["rotulo"] is None
    assert "criterios" in data and data["criterios"] is not None

    criterios = data["criterios"]
    for crit in ["precision", "simplicidad", "jerga", "analogia", "huecos"]:
        assert crit in criterios
        assert "puntaje" in criterios[crit]
        assert "justificacion" in criterios[crit]
        assert isinstance(criterios[crit]["puntaje"], int)


def test_r5_feynman_sin_clave_rotulo_sin_ia_y_explica_que_mide(isolated_cloud_env, cuenta):
    """R5: Sin clave de IA, Feynman da evaluación básica rotulada 'sin IA', explicando qué mide."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)

    with ia_sustituida(sin_clave=True):
        res = client.post(
            "/api/exams/evaluate-feynman",
            json={
                "concept": "Star Schema y Modelado Dimensional",
                "explanation": "Es como un ticket de supermercado donde los números van en el centro y los datos del comprador a los lados.",
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["sin_ia"] is True
    assert data["rotulo"] == "sin IA"
    assert data["que_mide"] is not None
    assert "largo de las frases" in data["que_mide"].lower()
    assert "palabras técnicas" in data["que_mide"].lower()
    assert "sin IA" in data["feedback_summary"]
    assert "criterios" in data and data["criterios"] is not None


def test_r6_feynman_ejemplos_rapidos_sin_temas_personales_fijos(isolated_cloud_env, cuenta):
    """R6: Los ejemplos rápidos salen de las notas de la cuenta o son genéricos, nunca temas fijos personales."""
    vault = vault_de_prueba()
    reader = VaultReader(vault)

    # 1. Sin notas en el vault: debe devolver conceptos académicos genéricos neutrales
    ejemplos_vacio = ejemplos_feynman(reader)
    assert len(ejemplos_vacio) >= 3
    conceptos_vacio = [e.concept for e in ejemplos_vacio]
    # No deben figurar los temas personales de Leandro
    for tema_prohibido in ["BigQuery", "Modelo Estrella", "FSRS", "Snowflake"]:
        assert not any(tema_prohibido.lower() in c.lower() for c in conceptos_vacio)
    assert any("fotosíntesis" in c.lower() or "gravedad" in c.lower() for c in conceptos_vacio)

    # 2. Con notas en el vault: toma los títulos de las notas de la cuenta
    sembrar_notas_de_muestra(vault)
    ejemplos_con_notas = ejemplos_feynman(reader)
    conceptos_con_notas = [e.concept for e in ejemplos_con_notas]
    assert len(conceptos_con_notas) >= 3
    # Comprobar por la ruta API
    res_api = client.get("/api/exams/feynman-examples")
    assert res_api.status_code == 200
    api_conceptos = [e["concept"] for e in res_api.json()]
    assert any(c in api_conceptos for c in conceptos_con_notas)


def test_r7_ia_devuelve_formato_invalido_ofrece_version_sin_ia_sin_error_500(isolated_cloud_env, cuenta):
    """R7: Si la IA devuelve algo que no respeta el formato esperado o falla, responde versión 'sin IA' con aviso, nunca 500."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)

    # 1. En generate exam
    with ia_sustituida(siempre=respuesta_de("RESPUESTA_INVALIDA_NO_ES_JSON")):
        res_exam = client.post(
            "/api/exams/generate",
            json={"note_id": "Star Schema y Modelado Dimensional", "count": 2},
        )
    assert res_exam.status_code == 200
    data_exam = res_exam.json()
    assert data_exam["sin_ia"] is True
    assert data_exam["rotulo"] == "sin IA"
    assert data_exam["aviso"] is not None
    assert "IA" in data_exam["aviso"]

    # 2. En evaluate open answer
    with ia_sustituida(siempre=respuesta_de("{ 'broken': json }")):
        res_ans = client.post(
            "/api/exams/evaluate-answer",
            json={
                "note_id": "Star Schema y Modelado Dimensional",
                "question_prompt": "¿Por qué desnormalizar?",
                "user_answer": "Para acelerar las lecturas analíticas y reducir joins.",
            },
        )
    assert res_ans.status_code == 200
    data_ans = res_ans.json()
    assert data_ans["sin_ia"] is True
    assert data_ans["rotulo"] == "sin IA"
    assert data_ans["aviso"] is not None

    # 3. En evaluate feynman
    with ia_sustituida(siempre=respuesta_de("ERROR_DEL_PROVEEDOR_HTTP_500")):
        res_feyn = client.post(
            "/api/exams/evaluate-feynman",
            json={
                "concept": "Star Schema y Modelado Dimensional",
                "explanation": "Es como un ticket de supermercado con datos al centro y detalles al costado.",
            },
        )
    assert res_feyn.status_code == 200
    data_feyn = res_feyn.json()
    assert data_feyn["sin_ia"] is True
    assert data_feyn["rotulo"] == "sin IA"
    assert data_feyn["aviso"] is not None


def test_r3_respuesta_abierta_de_un_examen_de_material_vuelve_a_su_material(isolated_cloud_env, cuenta):
    """R3: la pregunta abierta de un examen hecho sobre un material se evalúa contra ese material (no 404)."""
    almacen = AlmacenDeMateriales.con_conexion_propia(cuenta)
    texto = "El registro de transacciones guarda cada cambio antes de aplicarlo para poder recuperarse de una caída."
    mat = almacen.guardar("registro.txt", texto.encode("utf-8"))

    with ia_sustituida(sin_clave=True):
        examen = client.post("/api/exams/generate", json={"material_id": mat["id"], "question_type": "open", "count": 1})
    assert examen.status_code == 200
    pregunta = examen.json()["questions"][0]
    assert pregunta["note_id"] == f"material:{mat['id']}"
    assert pregunta["source_reference"] == "registro.txt"

    evaluacion = {"is_correct": True, "score": 80, "feedback": "Bien.", "what_was_missing": None}
    with ia_sustituida(siempre=respuesta_de(evaluacion)) as modelo:
        res = client.post(
            "/api/exams/evaluate-answer",
            json={"note_id": pregunta["note_id"], "question_prompt": pregunta["prompt"], "user_answer": "Para recuperarse de una caída."},
        )
    assert res.status_code == 200 and res.json()["sin_ia"] is False
    assert "registro de transacciones guarda cada cambio" in modelo.call_args.args[0].usuario

    # La forma vieja del identificador también llega al material
    with ia_sustituida(siempre=respuesta_de(evaluacion)):
        vieja = client.post(
            "/api/exams/evaluate-answer",
            json={"note_id": f"material-{mat['id']}", "question_prompt": "x", "user_answer": "Para recuperarse de una caída."},
        )
    assert vieja.status_code == 200


def test_r1_cada_pregunta_cita_la_nota_sin_ruta_del_servidor(isolated_cloud_env, cuenta):
    """R1: `source_reference` es la nota (ruta relativa al vault) y el pasaje va aparte en `fragmento`."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)
    with ia_sustituida(sin_clave=True):
        res = client.post("/api/exams/generate", json={"note_id": "Star Schema y Modelado Dimensional", "count": 2})
    for q in res.json()["questions"]:
        assert q["source_reference"].endswith("Star Schema y Modelado Dimensional.md")
        assert str(vault) not in q["source_reference"]
        assert q["fragmento"] != q["source_reference"]


_FEYNMAN_VALIDO = {
    "score": 80,
    "mastery_level": "Avanzado",
    "clarity_score": 80,
    "precision_score": 80,
    "feedback_summary": "Bien.",
    "suggested_simplification": "Más simple.",
    "criterios": {c: {"puntaje": 80, "justificacion": "ok"} for c in ("precision", "simplicidad", "jerga", "analogia", "huecos")},
}


def _feynman_con(respuesta):
    with ia_sustituida(siempre=respuesta):
        return client.post(
            "/api/exams/evaluate-feynman",
            json={"concept": "Star Schema y Modelado Dimensional", "explanation": "Es como un ticket con datos al centro."},
        )


def test_r7_feynman_con_esquema_incompleto_no_se_presenta_como_ia(isolated_cloud_env, cuenta):
    """R7: JSON válido con esquema malo (puntaje fuera de rango, criterio faltante o no numérico) → «sin IA» con aviso."""
    sembrar_notas_de_muestra(vault_de_prueba())
    sin_huecos = {**_FEYNMAN_VALIDO, "criterios": {k: v for k, v in _FEYNMAN_VALIDO["criterios"].items() if k != "huecos"}}
    puntaje_texto = {**_FEYNMAN_VALIDO, "criterios": {**_FEYNMAN_VALIDO["criterios"], "jerga": {"puntaje": "alto", "justificacion": "x"}}}
    for malo in (
        {**_FEYNMAN_VALIDO, "score": 150},
        sin_huecos,
        puntaje_texto,
        {**_FEYNMAN_VALIDO, "criterios": {**_FEYNMAN_VALIDO["criterios"], "precision": {"puntaje": 101, "justificacion": "x"}}},
        [1, 2, 3],
    ):
        res = _feynman_con(respuesta_de(malo))
        assert res.status_code == 200, malo
        assert res.json()["sin_ia"] is True and res.json()["rotulo"] == "sin IA" and res.json()["aviso"], malo

    valido = _feynman_con(respuesta_de(_FEYNMAN_VALIDO))
    assert valido.json()["sin_ia"] is False


def test_r7_proveedor_que_falla_da_version_sin_ia_en_las_tres_rutas(isolated_cloud_env, cuenta):
    """R7: un proveedor que no responde (o responde esquemas malos) nunca da 500."""
    sembrar_notas_de_muestra(vault_de_prueba())
    assert _feynman_con(None).json()["sin_ia"] is True

    for malo in (None, respuesta_de({"questions": ["no soy un objeto", 3]})):
        with ia_sustituida(siempre=malo):
            res = client.post("/api/exams/generate", json={"note_id": "Star Schema y Modelado Dimensional", "count": 2})
        assert res.status_code == 200 and res.json()["sin_ia"] is True and res.json()["aviso"]

    for malo in (
        None,
        respuesta_de({"is_correct": True, "score": 150, "feedback": "x"}),
        respuesta_de({"is_correct": "false", "score": 50, "feedback": "x"}),
    ):
        with ia_sustituida(siempre=malo):
            res = client.post(
                "/api/exams/evaluate-answer",
                json={"note_id": "Star Schema y Modelado Dimensional", "question_prompt": "¿Por qué?", "user_answer": "Para reducir JOINs en consultas."},
            )
        assert res.status_code == 200 and res.json()["sin_ia"] is True and res.json()["aviso"]


def test_r4_feynman_con_ia_contrasta_con_la_nota_elegida(isolated_cloud_env, cuenta):
    """R4: con `note_id`, el texto de esa nota (y no otra) es el que llega a la IA para evaluar."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)
    nota = VaultReader(vault).get_note("Star Schema y Modelado Dimensional")
    with ia_sustituida(siempre=respuesta_de(_FEYNMAN_VALIDO)) as modelo:
        res = client.post(
            "/api/exams/evaluate-feynman",
            json={"concept": "Un nombre que no es el de la nota", "explanation": "Es como un ticket.", "note_id": nota.id},
        )
    assert res.status_code == 200 and res.json()["sin_ia"] is False
    prompt = modelo.call_args.args[0].usuario
    assert "Surrogate Keys" in prompt and "Webhook" not in prompt


def test_r4_r6_pantalla_feynman_explica_y_deja_elegir_la_nota():
    """R4/R6: la pantalla explica en una o dos frases qué hace y deja elegir la nota contra la que se evalúa."""
    from pathlib import Path

    html = Path("src/aulento/web/static/index.html").read_text(encoding="utf-8")
    app_js = js_del_front()
    vista = html[html.index('id="view-exam-feynman"') :][:4000]
    assert "Explicá un concepto complejo en tus propias palabras" in vista
    assert 'id="feynman-note-select"' in vista
    envio = app_js[app_js.index("async function submitFeynmanEvaluation") :][:2000]
    assert "feynman-note-select" in envio and "note_id" in envio
