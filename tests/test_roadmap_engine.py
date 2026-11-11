"""Pruebas unitarias para las plantillas y el motor de Rutas de Aprendizaje."""

import json

import pytest
from unittest.mock import patch

from conftest import cuenta_en
from ia_falsa import ia_sustituida, respuesta_de
from aulento.core.ia.tipos import Respuesta
from aulento.db.connection import get_connection
from aulento.db.schema import create_schema
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.roadmap.templates import get_curated_templates, get_template_by_title
from aulento.roadmap.engine import IANoDisponibleError, RoadmapEngine
from aulento.roadmap.system_prompt_manager import DEFAULT_ROADMAP_SYSTEM_PROMPT
from aulento.models.roadmap import EstadoTema, RoadmapCreate, RoadmapModuleCreate, RoadmapTopicCreate

DATA_ENGINEER_TEMPLATE = "Data Engineer Senior (Cloud, Streaming & Lakehouse)"


@pytest.fixture
def repo_and_engine(tmp_path):
    db_file = tmp_path / "test_engine.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()
    repo = RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))
    engine = RoadmapEngine(repo=repo)
    return repo, engine


def test_curated_templates():
    templates = get_curated_templates()
    assert len(templates) >= 4
    titles = [t.titulo for t in templates]
    assert any("Data Engineer" in t for t in titles)
    assert any("AI Solutions Architect" in t for t in titles)

    tmpl = get_template_by_title(DATA_ENGINEER_TEMPLATE)
    assert tmpl is not None
    assert len(tmpl.modulos) >= 4


def test_template_solo_por_titulo_completo():
    for tmpl in get_curated_templates():
        assert get_template_by_title(tmpl.titulo).titulo == tmpl.titulo

    encontrado = get_template_by_title("  data engineer senior (cloud, streaming & lakehouse)  ")
    assert encontrado is not None
    assert encontrado.titulo == DATA_ENGINEER_TEMPLATE


@pytest.mark.parametrize(
    "texto",
    ["", "   ", None, "ai", "Data Engineer", "Data Engineer Senior", f"Quiero ser {DATA_ENGINEER_TEMPLATE}"],
)
def test_template_no_coincide_con_vacio_ni_parcial(texto):
    assert get_template_by_title(texto) is None


def test_generate_roadmap_with_template_match(repo_and_engine):
    _, engine = repo_and_engine
    with ia_sustituida() as mock_gen:
        roadmap = engine.generate_roadmap_with_ai(
            prompt=DATA_ENGINEER_TEMPLATE,
            target_role=DATA_ENGINEER_TEMPLATE,
            experience_level="Senior",
        )
    mock_gen.assert_not_called()
    assert roadmap.titulo == DATA_ENGINEER_TEMPLATE
    assert len(roadmap.modulos) >= 4


def test_generate_roadmap_partial_title_does_not_use_template(repo_and_engine):
    _, engine = repo_and_engine
    with ia_sustituida(sin_clave=True):
        roadmap = engine.generate_roadmap_with_ai(
            prompt="Quiero prepararme para Data Engineer Senior",
            target_role="Data Engineer Senior",
            experience_level="Senior",
        )
    assert roadmap.titulo != DATA_ENGINEER_TEMPLATE
    assert roadmap.metadata_json["origen"] == "domain_fallback"


def test_generate_roadmap_fallback(repo_and_engine):
    _, engine = repo_and_engine
    with ia_sustituida(sin_clave=True):
        roadmap = engine.generate_roadmap_with_ai(
            prompt="Especialización en Rust para High Frequency Trading",
            target_role="Rust HFT Engineer",
            experience_level="Staff",
        )
        assert "Rust HFT Engineer" in roadmap.titulo
        assert len(roadmap.modulos) == 3
        assert len(roadmap.modulos[0].temas) == 3


def test_generate_roadmap_fallback_language(repo_and_engine):
    _, engine = repo_and_engine
    with ia_sustituida(sin_clave=True):
        roadmap = engine.generate_roadmap_with_ai(
            prompt="ingles A2",
            target_role="ingles A2",
            experience_level="Junior",
        )
        assert "ingles A2" in roadmap.titulo
        assert roadmap.categoria == "english_communication"
        # Verify it has real language topics, not software engineering
        all_module_titles = [m.titulo for m in roadmap.modulos]
        assert any("Gramática" in t or "Vocabulario" in t or "Fonética" in t for t in all_module_titles)
        assert not any("Arquitectura" in t or "Protocolos" in t for t in all_module_titles)


def test_suggest_next_topics(repo_and_engine):
    repo, engine = repo_and_engine
    # Crear ruta
    tmpl = get_template_by_title(DATA_ENGINEER_TEMPLATE)
    created = repo.create_roadmap(tmpl)
    
    # Marcar un par de temas como completados
    t1_id = created.modulos[0].temas[0].id
    repo.update_topic_status(t1_id, EstadoTema.COMPLETADO)

    with ia_sustituida(sin_clave=True):
        response = engine.suggest_next_topics(created.id)
        assert response.completed_topics_count == 1
        assert len(response.suggested_topics) >= 2
        assert "Data Mesh" in response.suggested_topics[0].titulo or "Arquitectura" in response.suggested_topics[0].titulo


# --- R3 / R4 / R5 / R9: generación con perfil, alcance y fallback visible ---

PERFIL_IA = {
    "disciplina": "Psicología cognitiva",
    "arquetipo": "ciencias_sociales_salud",
    "rol_docente": "Docente e investigadora en psicología cognitiva",
    "secciones": [
        {"titulo": "Fenómeno", "instruccion": "Describe el fenómeno."},
        {"titulo": "Modelos", "instruccion": "Compara los modelos teóricos."},
        {"titulo": "Experimentos", "instruccion": "Resume los experimentos clave."},
    ],
    "usa_codigo": False,
    "usa_diagramas": False,
    "tipo_fuentes": "manuales y artículos revisados por pares",
    "flashcards_ejemplo": [{"pregunta": "¿Qué mide la tarea Stroop?", "respuesta": "El control inhibitorio."}],
}

MODULOS_IA = [
    {
        "titulo": "1. Atención",
        "descripcion": "Procesos atencionales",
        "temas": [
            {"titulo": "Atención selectiva", "descripcion": "Filtro temprano y tardío"},
            {"titulo": "Atención dividida", "prerrequisitos": ["atención selectiva", "No existe"]},
        ],
    },
    {"titulo": "2. Memoria", "temas": [{"titulo": "Memoria de trabajo", "prerrequisitos": ["Atención dividida"]}]},
]


def _gateway_result(body) -> Respuesta:
    text = body if isinstance(body, str) else json.dumps(body)
    return respuesta_de(text)


def _generar_con_ia(engine, respuesta, **kwargs):
    """Ejecuta la generación con Gemini mockeado y devuelve (ruta, user_prompt enviado)."""
    params = {"prompt": "Psicología cognitiva", "target_role": "Psicología cognitiva", "category": "psicologia"}
    params.update(kwargs)
    with ia_sustituida(siempre=respuesta) as mock_gen:
        roadmap = engine.generate_roadmap_with_ai(**params)
    pedido, endpoint_tipo, _ = mock_gen.call_args.args
    assert endpoint_tipo == "roadmap_gen"
    assert (pedido.json, pedido.temperatura) == (True, 0.2)
    return roadmap, pedido.usuario


def test_generate_with_ai_guarda_perfil_de_la_ia(repo_and_engine):
    _, engine = repo_and_engine
    respuesta = _gateway_result({"titulo": "Psicología Cognitiva", "perfil_pedagogico": PERFIL_IA, "modulos": MODULOS_IA})
    roadmap, _ = _generar_con_ia(engine, respuesta)

    perfil = roadmap.metadata_json["perfil_pedagogico"]
    assert perfil["origen"] == "ia"
    assert perfil["disciplina"] == "Psicología cognitiva"
    assert [s["titulo"] for s in perfil["secciones"]] == ["Fenómeno", "Modelos", "Experimentos"]
    assert roadmap.metadata_json["origen"] == "ia"
    assert roadmap.metadata_json["alcance"] == "curso"
    assert "aviso" not in roadmap.metadata_json
    assert [m.titulo for m in roadmap.modulos] == ["1. Atención", "2. Memoria"]


def test_generate_with_ai_perfil_declarado_por_ia_no_puede_fingir_origen(repo_and_engine):
    _, engine = repo_and_engine
    perfil = dict(PERFIL_IA, origen="editado")
    roadmap, _ = _generar_con_ia(engine, _gateway_result({"perfil_pedagogico": perfil, "modulos": MODULOS_IA}))
    assert roadmap.metadata_json["perfil_pedagogico"]["origen"] == "ia"


@pytest.mark.parametrize(
    "perfil_recibido",
    [None, "texto", {**PERFIL_IA, "secciones": PERFIL_IA["secciones"][:2]}],
)
def test_generate_with_ai_perfil_ausente_o_invalido_cae_al_arquetipo(repo_and_engine, perfil_recibido):
    _, engine = repo_and_engine
    cuerpo = {"titulo": "Psicología Cognitiva", "modulos": MODULOS_IA}
    if perfil_recibido is not None:
        cuerpo["perfil_pedagogico"] = perfil_recibido
    roadmap, _ = _generar_con_ia(engine, _gateway_result(cuerpo), category="data_ai")

    perfil = roadmap.metadata_json["perfil_pedagogico"]
    assert perfil["origen"] == "arquetipo"
    assert perfil["arquetipo"] == "ciencias_sociales_salud"
    # Los módulos y temas recibidos se conservan: no es un fallback.
    assert [m.titulo for m in roadmap.modulos] == ["1. Atención", "2. Memoria"]
    assert [t.titulo for t in roadmap.modulos[0].temas] == ["Atención selectiva", "Atención dividida"]
    assert roadmap.metadata_json["origen"] == "ia"


def test_generate_with_ai_persiste_prerrequisitos(repo_and_engine):
    repo, engine = repo_and_engine
    roadmap, _ = _generar_con_ia(engine, _gateway_result({"perfil_pedagogico": PERFIL_IA, "modulos": MODULOS_IA}))
    assert roadmap.modulos[0].temas[1].prerrequisitos == ["atención selectiva", "No existe"]

    created = repo.create_roadmap(roadmap)
    aristas = {(e.origen_titulo, e.destino_titulo) for e in repo.get_prerequisites(created.id)}
    assert aristas == {("Atención selectiva", "Atención dividida"), ("Atención dividida", "Memoria de trabajo")}


@pytest.mark.parametrize(
    "respuesta",
    [
        _gateway_result({"titulo": "Vacía", "perfil_pedagogico": PERFIL_IA, "modulos": []}),
        _gateway_result({"titulo": "Sin temas", "modulos": [{"titulo": "M1", "temas": []}, {"titulo": "M2"}]}),
        _gateway_result({"titulo": "Sin clave modulos"}),
        _gateway_result("esto no es JSON"),
        _gateway_result(["lista", "inesperada"]),
        None,
    ],
)
def test_generate_with_ai_respuesta_inutilizable_aplica_fallback_con_aviso(repo_and_engine, respuesta):
    _, engine = repo_and_engine
    roadmap, _ = _generar_con_ia(engine, respuesta)

    assert roadmap.metadata_json["origen"] == "domain_fallback"
    assert "sin IA" in roadmap.metadata_json["aviso"]
    assert roadmap.metadata_json["perfil_pedagogico"]["origen"] == "arquetipo"
    assert roadmap.metadata_json["perfil_pedagogico"]["arquetipo"] == "ciencias_sociales_salud"
    assert len(roadmap.modulos) >= 3
    assert all(m.temas for m in roadmap.modulos)


def test_fallback_de_filosofia_es_neutro_y_visible(repo_and_engine):
    _, engine = repo_and_engine
    with ia_sustituida(sin_clave=True):
        roadmap = engine.generate_roadmap_with_ai(prompt="Filosofía estoica", target_role="Filosofía estoica")

    texto = " ".join(
        [roadmap.titulo, roadmap.descripcion or ""]
        + [f"{m.titulo} {m.descripcion or ''}" for m in roadmap.modulos]
        + [t.titulo for m in roadmap.modulos for t in m.temas]
    )
    for prohibida in ["Producción", "Escalabilidad", "Entrevista Técnica"]:
        assert prohibida not in texto
    assert "Filosofía estoica" in roadmap.titulo
    assert any("Filosofía estoica" in t.titulo for m in roadmap.modulos for t in m.temas)

    meta = roadmap.metadata_json
    assert meta["origen"] == "domain_fallback"
    assert "sin IA" in meta["aviso"] and "humanidades" in meta["aviso"]
    assert meta["alcance"] == "curso"
    assert meta["perfil_pedagogico"]["arquetipo"] == "humanidades"


def test_fallback_tech_conserva_aviso(repo_and_engine):
    _, engine = repo_and_engine
    with ia_sustituida(sin_clave=True):
        roadmap = engine.generate_roadmap_with_ai(prompt="Kubernetes", target_role="Kubernetes")
    assert roadmap.metadata_json["perfil_pedagogico"]["arquetipo"] == "tech"
    assert "sin IA" in roadmap.metadata_json["aviso"]


@pytest.mark.parametrize(
    "alcance, fragmentos",
    [
        ("curso", ["entre 3 y 5 módulos", "3 a 4 temas"]),
        ("especializacion", ["entre 5 y 8 módulos", "4 a 6 temas"]),
        ("carrera", ["entre 8 y 14 módulos", "MATERIA", "correlativas"]),
    ],
)
def test_user_prompt_lleva_el_tamano_del_alcance(repo_and_engine, alcance, fragmentos):
    _, engine = repo_and_engine
    respuesta = _gateway_result({"perfil_pedagogico": PERFIL_IA, "modulos": MODULOS_IA})
    roadmap, user_prompt = _generar_con_ia(engine, respuesta, alcance=alcance)

    for fragmento in fragmentos:
        assert fragmento in user_prompt
    assert roadmap.metadata_json["alcance"] == alcance


def test_alcance_por_defecto_es_curso_y_el_desconocido_tambien(repo_and_engine):
    _, engine = repo_and_engine
    respuesta = _gateway_result({"perfil_pedagogico": PERFIL_IA, "modulos": MODULOS_IA})
    _, prompt_defecto = _generar_con_ia(engine, respuesta)
    roadmap, prompt_raro = _generar_con_ia(engine, respuesta, alcance="doctorado")
    assert "entre 3 y 5 módulos" in prompt_defecto
    assert "entre 3 y 5 módulos" in prompt_raro
    assert roadmap.metadata_json["alcance"] == "curso"


def test_tamano_del_alcance_sobrevive_a_un_system_prompt_personalizado(repo_and_engine, tmp_path, monkeypatch):
    _, engine = repo_and_engine
    engine.prompts.save_roadmap_system_prompt("Eres un mentor personalizado sin esquema de perfil.")
    roadmap, user_prompt = _generar_con_ia(
        engine, _gateway_result({"modulos": MODULOS_IA}), alcance="especializacion"
    )
    assert "entre 5 y 8 módulos" in user_prompt
    assert roadmap.metadata_json["perfil_pedagogico"]["origen"] == "arquetipo"


def test_system_prompt_personalizado_recibe_el_contrato_de_salida(repo_and_engine, tmp_path, monkeypatch):
    _, engine = repo_and_engine
    engine.prompts.save_roadmap_system_prompt("Eres un mentor. Diseña entre 3 y 5 módulos, con 3 a 4 temas cada uno.")
    with ia_sustituida(siempre=_gateway_result({"modulos": MODULOS_IA})) as mock_gen:
        engine.generate_roadmap_with_ai(prompt="Psicología cognitiva", target_role="Psicología cognitiva")

    enviado = mock_gen.call_args.args[0].sistema
    assert enviado.startswith("Eres un mentor.")
    assert '"perfil_pedagogico"' in enviado
    assert "prevalece sobre cualquier indicación anterior" in enviado

    engine.prompts.reset_roadmap_system_prompt()
    assert engine.prompts.get_roadmap_system_instruction() == DEFAULT_ROADMAP_SYSTEM_PROMPT


def test_campo_mal_tipado_de_la_ia_no_descarta_la_ruta(repo_and_engine):
    _, engine = repo_and_engine
    modulos = [
        {
            "titulo": "1. Atención",
            "descripcion": ["no", "es", "texto"],
            "temas": [{"titulo": "Atención selectiva", "descripcion": {"x": 1}}, {"titulo": "Atención dividida", "descripcion": None}],
        }
    ]
    respuesta = _gateway_result(
        {"titulo": "Psicología Cognitiva", "descripcion": 7, "nivel_objetivo": None, "perfil_pedagogico": PERFIL_IA, "modulos": modulos}
    )
    roadmap, _ = _generar_con_ia(engine, respuesta, experience_level="Junior")

    assert roadmap.metadata_json["origen"] == "ia"
    assert roadmap.nivel_objetivo == "Junior"
    assert roadmap.modulos[0].descripcion is None
    assert [t.titulo for t in roadmap.modulos[0].temas] == ["Atención selectiva", "Atención dividida"]
    assert roadmap.modulos[0].temas[0].descripcion is None


def test_fallback_de_otro_idioma_no_se_convierte_en_ingles(repo_and_engine):
    _, engine = repo_and_engine
    with ia_sustituida(sin_clave=True):
        roadmap = engine.generate_roadmap_with_ai(prompt="Francés B1", target_role="Francés B1", category="general")

    assert roadmap.titulo == "Idioma: Francés B1"
    assert roadmap.categoria == "general"
    textos = " ".join([roadmap.descripcion, *(m.titulo for m in roadmap.modulos), *(t.titulo for m in roadmap.modulos for t in m.temas)])
    for ingles in ["Inglés", "Simple Past", "Standups", "-ed"]:
        assert ingles not in textos
    assert "Inglés" not in roadmap.metadata_json["perfil_pedagogico"]["rol_docente"]


def test_fallback_sin_categoria_ni_palabras_reconocidas_es_general(repo_and_engine):
    # Mismo camino que `roadmap create --title Carpintería` sin clave: la categoría por defecto no es técnica.
    _, engine = repo_and_engine
    with ia_sustituida(sin_clave=True):
        roadmap = engine.generate_roadmap_with_ai(prompt="Carpintería", target_role="Carpintería")

    assert roadmap.metadata_json["perfil_pedagogico"]["arquetipo"] == "general"
    assert roadmap.metadata_json["perfil_pedagogico"]["usa_codigo"] is False
    titulos = " ".join(t.titulo for m in roadmap.modulos for t in m.temas) + " ".join(m.titulo for m in roadmap.modulos)
    for palabra in ["Producción", "Escalabilidad", "Arquitectura", "Entrevista"]:
        assert palabra not in titulos


def test_alcance_carrera_acepta_materias_sin_temas(repo_and_engine):
    repo, engine = repo_and_engine
    materias = [
        {"titulo": "Introducción a la Psicología", "descripcion": "Panorama de la disciplina.", "temas": []},
        {"titulo": "Psicología del Desarrollo", "descripcion": "Ciclo vital.", "correlativas": ["Introducción a la Psicología"]},
    ]
    respuesta = _gateway_result({"titulo": "Licenciatura en Psicología", "perfil_pedagogico": PERFIL_IA, "modulos": materias})
    roadmap, _ = _generar_con_ia(engine, respuesta, alcance="carrera")

    assert roadmap.metadata_json["origen"] == "ia"
    assert roadmap.metadata_json["alcance"] == "carrera"
    assert [m.titulo for m in roadmap.modulos] == ["Introducción a la Psicología", "Psicología del Desarrollo"]
    assert all(m.temas == [] for m in roadmap.modulos)
    assert "Correlativas: Introducción a la Psicología" in roadmap.modulos[1].descripcion

    created = repo.create_roadmap(roadmap)
    assert created.total_temas == 0
    assert len(created.modulos) == 2


def test_alcance_carrera_sin_modulos_es_fallo(repo_and_engine):
    _, engine = repo_and_engine
    roadmap, _ = _generar_con_ia(engine, _gateway_result({"perfil_pedagogico": PERFIL_IA, "modulos": []}), alcance="carrera")
    assert roadmap.metadata_json["origen"] == "domain_fallback"
    assert roadmap.metadata_json["alcance"] == "carrera"


def test_system_prompt_de_rutas_pide_perfil_y_no_fija_tamano():
    assert '"perfil_pedagogico"' in DEFAULT_ROADMAP_SYSTEM_PROMPT
    for campo in ["disciplina", "arquetipo", "rol_docente", "secciones", "usa_codigo", "usa_diagramas", "tipo_fuentes", "flashcards_ejemplo"]:
        assert f'"{campo}"' in DEFAULT_ROADMAP_SYSTEM_PROMPT
    assert "entre 3 y 5 módulos" not in DEFAULT_ROADMAP_SYSTEM_PROMPT
    assert "INGLÉS" not in DEFAULT_ROADMAP_SYSTEM_PROMPT


# --- R10: expansión de materia a demanda ---

TEMAS_EXPANSION = [
    {"titulo": "Teorías del apego", "descripcion": "Bowlby y Ainsworth"},
    {"titulo": "Desarrollo cognitivo", "descripcion": "Piaget y Vygotsky"},
    {"titulo": "ADOLESCENCIA"},
    {"titulo": "Desarrollo moral"},
    {"titulo": "Envejecimiento"},
]


@pytest.fixture
def carrera(repo_and_engine):
    repo, engine = repo_and_engine
    created = repo.create_roadmap(
        RoadmapCreate(
            titulo="Licenciatura en Psicología",
            categoria="psicologia",
            enfoque_estudio="academico",
            metadata_json={"alcance": "carrera", "perfil_pedagogico": dict(PERFIL_IA, origen="ia")},
            modulos=[
                RoadmapModuleCreate(
                    titulo="Psicología del Desarrollo",
                    descripcion="Ciclo vital",
                    orden=1,
                    temas=[RoadmapTopicCreate(titulo="Adolescencia")],
                ),
                RoadmapModuleCreate(titulo="Psicología Social", orden=2),
            ],
        )
    )
    return repo, engine, created


def _expandir(engine, module_id, respuesta, api_key="dummy_key"):
    with ia_sustituida(siempre=respuesta, sin_clave=not api_key) as mock_gen:
        try:
            return engine.expand_module(module_id), mock_gen
        except Exception as exc:
            return exc, mock_gen


def test_expand_module_agrega_temas_y_omite_duplicados(carrera):
    repo, engine, created = carrera
    modulo_id = created.modulos[0].id

    agregados, mock_gen = _expandir(engine, modulo_id, _gateway_result({"temas": TEMAS_EXPANSION}))

    assert [t.titulo for t in agregados] == ["Teorías del apego", "Desarrollo cognitivo", "Desarrollo moral", "Envejecimiento"]
    modulo = repo.get_roadmap(created.id).modulos[0]
    assert [t.titulo for t in modulo.temas] == [
        "Adolescencia", "Teorías del apego", "Desarrollo cognitivo", "Desarrollo moral", "Envejecimiento",
    ]
    assert modulo.temas[1].descripcion == "Bowlby y Ainsworth"
    assert modulo.temas[1].fuente.value == "ai_generada"

    pedido, endpoint_tipo, repo_del_consumo = mock_gen.call_args.args
    assert endpoint_tipo == "module_expand"
    assert repo_del_consumo is repo
    assert (pedido.json, pedido.temperatura) == (True, 0.2)
    user_prompt = pedido.usuario
    assert "Psicología del Desarrollo" in user_prompt
    assert "Psicología Social" in user_prompt
    assert "Experimentos" in user_prompt
    assert "Psicología cognitiva" in user_prompt
    assert "entre 4 y 8 temas" in user_prompt


def test_expand_module_exige_el_minimo_despues_de_quitar_duplicados(carrera):
    # Cinco temas recibidos, pero solo dos son nuevos y distintos: no alcanza el mínimo y no se inserta nada.
    repo, engine, created = carrera
    repetidos = [
        {"titulo": "Teorías del apego"},
        {"titulo": "teorías del APEGO "},
        {"titulo": "Adolescencia"},
        {"titulo": "ADOLESCENCIA"},
        {"titulo": "Desarrollo moral"},
    ]
    resultado, _ = _expandir(engine, created.modulos[0].id, _gateway_result({"temas": repetidos}))
    assert isinstance(resultado, IANoDisponibleError)
    assert [t.titulo for t in repo.get_roadmap(created.id).modulos[0].temas] == ["Adolescencia"]


def test_expand_module_limita_a_ocho_temas(carrera):
    repo, engine, created = carrera
    muchos = [{"titulo": f"Tema {i}"} for i in range(1, 13)]
    agregados, _ = _expandir(engine, created.modulos[1].id, _gateway_result({"temas": muchos}))
    assert len(agregados) == 8
    assert len(repo.get_roadmap(created.id).modulos[1].temas) == 8


@pytest.mark.parametrize(
    "respuesta",
    [
        None,
        _gateway_result("no es JSON"),
        _gateway_result({"temas": []}),
        _gateway_result({"temas": TEMAS_EXPANSION[:3]}),
        _gateway_result({"temas": [{"titulo": "  "}, {"sin": "titulo"}, "x", {"titulo": 3}]}),
        _gateway_result(["lista"]),
    ],
)
def test_expand_module_respuesta_inutilizable_lanza_error_y_no_inserta(carrera, respuesta):
    repo, engine, created = carrera
    resultado, _ = _expandir(engine, created.modulos[1].id, respuesta)
    assert isinstance(resultado, IANoDisponibleError)
    assert repo.get_roadmap(created.id).modulos[1].temas == []


def test_expand_module_sin_clave_lanza_error_sin_llamar_a_la_ia(carrera):
    repo, engine, created = carrera
    resultado, mock_gen = _expandir(engine, created.modulos[1].id, _gateway_result({"temas": TEMAS_EXPANSION}), api_key=None)
    assert isinstance(resultado, IANoDisponibleError)
    mock_gen.assert_not_called()
    assert repo.get_roadmap(created.id).modulos[1].temas == []


def test_expand_module_inexistente(carrera):
    _, engine, _ = carrera
    resultado, mock_gen = _expandir(engine, 9999, _gateway_result({"temas": TEMAS_EXPANSION}))
    assert isinstance(resultado, ValueError)
    mock_gen.assert_not_called()
