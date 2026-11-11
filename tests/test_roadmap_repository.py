"""Pruebas unitarias para el repositorio de Rutas de Aprendizaje."""

import pytest
from conftest import cuenta_en
from aulento.db.connection import get_connection
from aulento.db.schema import create_schema
from aulento.db.roadmap_repository import PrerequisiteCycleError, RoadmapRepository
from aulento.models.roadmap import (
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    RoadmapLessonCreate,
    EstadoTema,
    GapTopicItem,
    PrerequisiteCreate,
)
from aulento.roadmap.graph_engine import PrerequisiteGraphEngine


@pytest.fixture
def test_repo(tmp_path):
    db_file = tmp_path / "test_roadmap.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()
    return RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))


def test_create_and_get_roadmap(test_repo):
    data = RoadmapCreate(
        titulo="Data Engineer Senior",
        descripcion="Ruta de ingeniería de datos cloud",
        categoria="data_ai",
        nivel_objetivo="Senior",
        modulos=[
            RoadmapModuleCreate(
                titulo="1. Arquitecturas de Streaming",
                descripcion="Kafka, Flink y procesamiento en tiempo real",
                temas=[
                    RoadmapTopicCreate(titulo="Kafka Brokers y Particiones"),
                    RoadmapTopicCreate(titulo="Productores Idempotentes"),
                ],
            ),
            RoadmapModuleCreate(
                titulo="2. Lakehouse & Storage",
                temas=[
                    RoadmapTopicCreate(titulo="Apache Iceberg internals"),
                ],
            ),
        ],
    )
    detail = test_repo.create_roadmap(data)
    assert detail.id is not None
    assert detail.total_temas == 3
    assert detail.temas_completados == 0
    assert detail.progreso_pct == 0.0
    assert len(detail.modulos) == 2
    assert len(detail.modulos[0].temas) == 2

    # Recuperar por ID
    fetched = test_repo.get_roadmap(detail.id)
    assert fetched is not None
    assert fetched.titulo == "Data Engineer Senior"
    assert len(fetched.modulos) == 2

    # Listar
    all_roadmaps = test_repo.get_roadmaps()
    assert len(all_roadmaps) == 1
    assert all_roadmaps[0].total_temas == 3


def test_update_topic_status_and_progress_recalculation(test_repo):
    data = RoadmapCreate(
        titulo="Cloud FinOps",
        modulos=[
            RoadmapModuleCreate(
                titulo="Cost Optimization",
                temas=[
                    RoadmapTopicCreate(titulo="GCP CUDs & Reservations"),
                    RoadmapTopicCreate(titulo="BigQuery Slot Commitment"),
                ],
            )
        ],
    )
    created = test_repo.create_roadmap(data)
    t1_id = created.modulos[0].temas[0].id
    t2_id = created.modulos[0].temas[1].id

    # Actualizar t1 a completado
    updated_t1 = test_repo.update_topic_status(t1_id, EstadoTema.COMPLETADO)
    assert updated_t1.estado == EstadoTema.COMPLETADO

    r_updated = test_repo.get_roadmap(created.id)
    assert r_updated.temas_completados == 1
    assert r_updated.progreso_pct == 50.0

    # Actualizar t2 a completado
    test_repo.update_topic_status(t2_id, EstadoTema.COMPLETADO)
    r_updated2 = test_repo.get_roadmap(created.id)
    assert r_updated2.temas_completados == 2
    assert r_updated2.progreso_pct == 100.0


def test_save_and_retrieve_lesson(test_repo):
    data = RoadmapCreate(
        titulo="AI Architecture",
        modulos=[
            RoadmapModuleCreate(
                titulo="RAG",
                temas=[RoadmapTopicCreate(titulo="Vector Search")],
            )
        ],
    )
    created = test_repo.create_roadmap(data)
    tema_id = created.modulos[0].temas[0].id

    lesson_data = RoadmapLessonCreate(
        tema_id=tema_id,
        titulo="Clase de Vector Search",
        contenido_markdown="# Vector Search\nExplicación técnica...",
        diagramas_mermaid=["graph TD; A-->B;"],
        flashcards_json=[{"pregunta": "¿Qué es HNSW?", "respuesta": "Hierarchical Navigable Small World"}],
        vault_path="04 Knowledge/Cursos/AI/Vector Search.md",
    )
    saved_lesson = test_repo.save_lesson(lesson_data)
    assert saved_lesson.id is not None
    assert len(saved_lesson.diagramas_mermaid) == 1
    assert len(saved_lesson.flashcards_json) == 1

    # Al guardar clase, el tema pasa a completado automáticamente
    r_detail = test_repo.get_roadmap(created.id)
    assert r_detail.temas_completados == 1
    assert r_detail.progreso_pct == 100.0


def test_merge_gap_topics(test_repo):
    data = RoadmapCreate(
        titulo="Kafka Mastery",
        modulos=[
            RoadmapModuleCreate(
                titulo="Core",
                temas=[RoadmapTopicCreate(titulo="Partitions")],
            )
        ],
    )
    created = test_repo.create_roadmap(data)
    assert created.total_temas == 1

    gap_items = [
        GapTopicItem(titulo="Kafka Connect & Debezium", descripcion="CDC capture"),
        GapTopicItem(titulo="Schema Registry Avro", descripcion="Schema governance"),
    ]
    inserted = test_repo.merge_gap_topics(created.id, gap_items)
    assert inserted == 2

    # Verificar que se expandió la ruta
    expanded = test_repo.get_roadmap(created.id)
    assert expanded.total_temas == 3
    assert len(expanded.modulos) == 2
    assert expanded.modulos[1].titulo == "Especialización & Brechas Detectadas"
    assert len(expanded.modulos[1].temas) == 2


# --- R4: prerrequisitos por título persistidos como prelaciones ---

def _ruta_con_prerrequisitos(titulo_ruta="Psicología Cognitiva", **prerrequisitos_por_titulo):
    def tema(titulo, orden):
        return RoadmapTopicCreate(titulo=titulo, orden=orden, prerrequisitos=prerrequisitos_por_titulo.get(titulo, []))

    return RoadmapCreate(
        titulo=titulo_ruta,
        categoria="psicologia",
        enfoque_estudio="academico",
        metadata_json={"alcance": "curso"},
        modulos=[
            RoadmapModuleCreate(titulo="Bases", orden=1, temas=[tema("A", 1), tema("B", 2)]),
            RoadmapModuleCreate(titulo="Procesos", orden=2, temas=[tema("C", 1)]),
        ],
    )


def _aristas(repo, ruta_id):
    return {(e.origen_titulo, e.destino_titulo) for e in repo.get_prerequisites(ruta_id)}


def test_create_roadmap_persiste_prerrequisitos_por_titulo(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos(B=["a"], C=["  A ", "B"]))
    assert _aristas(test_repo, created.id) == {("A", "B"), ("A", "C"), ("B", "C")}
    assert all(e.ruta_id == created.id for e in test_repo.get_prerequisites(created.id))


def test_create_roadmap_ignora_titulo_inexistente_y_autorreferencia(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos(B=["No existe", "B", "A"]))
    aristas = _aristas(test_repo, created.id)
    assert ("A", "B") in aristas
    assert not any("No existe" in arista or arista == ("B", "B") for arista in aristas)


def test_create_roadmap_ignora_arista_que_cierra_ciclo(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos(A=["B"], B=["A"]))
    aristas = _aristas(test_repo, created.id)
    assert ("B", "A") in aristas
    assert ("A", "B") not in aristas

    indirecto = test_repo.create_roadmap(_ruta_con_prerrequisitos("Ciclo indirecto", B=["A"], C=["B"], A=["C"]))
    assert _aristas(test_repo, indirecto.id) == {("C", "A"), ("A", "B")}


def test_create_roadmap_no_duplica_arista_repetida(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos(B=["A", "a", "A"]))
    pares = [(e.origen_titulo, e.destino_titulo) for e in test_repo.get_prerequisites(created.id)]
    assert pares.count(("A", "B")) == 1


def test_create_roadmap_guarda_solo_los_prerrequisitos_declarados_y_el_grafo_infiere_el_resto(test_repo):
    # Una lista parcial de la IA no debe dejar sin predecesor (desbloqueados desde el primer día) a los
    # temas que omitió: la secuencia de esos temas la infiere el grafo al leer, sin guardarla (024 · R2).
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos(B=["A"]))
    assert _aristas(test_repo, created.id) == {("A", "B")}

    grafo = PrerequisiteGraphEngine(test_repo).get_graph_data(created.id)
    assert [(e.origen_titulo, e.destino_titulo, e.inferida) for e in grafo.edges] == [("A", "B", False), ("B", "C", True)]
    nodos = {n.titulo: n for n in grafo.nodes}
    assert nodos["A"].is_blocked is False
    assert nodos["B"].is_blocked is True
    assert nodos["C"].is_blocked is True
    # Leer el grafo no persiste la arista inferida.
    assert _aristas(test_repo, created.id) == {("A", "B")}


def test_create_roadmap_no_infiere_la_arista_secuencial_que_cerraria_un_ciclo(test_repo):
    # La IA declara que A y B dependen de C (el último tema): la arista secuencial B→C cerraría
    # un ciclo con C→B, así que el grafo no la infiere.
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos(A=["C"], B=["C"]))
    assert _aristas(test_repo, created.id) == {("C", "A"), ("C", "B")}

    grafo = PrerequisiteGraphEngine(test_repo).get_graph_data(created.id)
    assert grafo.has_cycle is False
    assert not any(e.inferida for e in grafo.edges)


def test_create_roadmap_sin_prerrequisitos_no_crea_aristas(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos())
    assert test_repo.get_prerequisites(created.id) == []


# --- R7: contexto del tema ---

def test_get_topic_with_context_incluye_enfoque_metadata_y_vecinos(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos())
    a, b = created.modulos[0].temas
    c = created.modulos[1].temas[0]

    ctx_a = test_repo.get_topic_with_context(a.id)
    assert ctx_a["enfoque_estudio"] == "academico"
    assert ctx_a["metadata_json"] == {"alcance": "curso"}
    assert ctx_a["prev_topic_title"] is None
    assert ctx_a["next_topic_title"] == "B"

    ctx_b = test_repo.get_topic_with_context(b.id)
    assert ctx_b["prev_topic_title"] == "A"
    assert ctx_b["next_topic_title"] == "C"

    ctx_c = test_repo.get_topic_with_context(c.id)
    assert ctx_c["prev_topic_title"] == "B"
    assert ctx_c["next_topic_title"] is None

    assert test_repo.get_topic_with_context(9999) is None


def test_get_topic_with_context_no_mezcla_temas_de_otra_ruta(test_repo):
    test_repo.create_roadmap(_ruta_con_prerrequisitos())
    otra = test_repo.create_roadmap(
        RoadmapCreate(titulo="Otra", modulos=[RoadmapModuleCreate(titulo="M", temas=[RoadmapTopicCreate(titulo="Único")])])
    )
    ctx = test_repo.get_topic_with_context(otra.modulos[0].temas[0].id)
    assert ctx["prev_topic_title"] is None
    assert ctx["next_topic_title"] is None


# --- R10 / R11: helpers de módulo y metadata ---

def test_get_module_with_context(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos())
    ctx = test_repo.get_module_with_context(created.modulos[0].id)
    assert ctx["module_title"] == "Bases"
    assert ctx["roadmap_title"] == "Psicología Cognitiva"
    assert ctx["categoria"] == "psicologia"
    assert ctx["topic_titles"] == ["A", "B"]
    assert ctx["other_module_titles"] == ["Procesos"]
    assert ctx["metadata_json"] == {"alcance": "curso"}
    assert test_repo.get_module_with_context(9999) is None


def test_add_topics_to_module_no_duplica(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos())
    modulo_id = created.modulos[0].id

    agregados = test_repo.add_topics_to_module(
        modulo_id,
        [
            RoadmapTopicCreate(titulo="a"),
            RoadmapTopicCreate(titulo="Memoria de trabajo", descripcion="Modelo de Baddeley"),
            RoadmapTopicCreate(titulo="  memoria de TRABAJO "),
            RoadmapTopicCreate(titulo="Atención"),
        ],
    )
    assert [t.titulo for t in agregados] == ["Memoria de trabajo", "Atención"]

    modulo = test_repo.get_roadmap(created.id).modulos[0]
    assert [t.titulo for t in modulo.temas] == ["A", "B", "Memoria de trabajo", "Atención"]
    assert [t.orden for t in modulo.temas][-2:] == [3, 4]
    assert modulo.temas[2].descripcion == "Modelo de Baddeley"
    assert test_repo.get_roadmap(created.id).total_temas == 5


def test_add_topics_to_module_inexistente(test_repo):
    with pytest.raises(ValueError):
        test_repo.add_topics_to_module(9999, [RoadmapTopicCreate(titulo="X")])


def test_update_roadmap_metadata(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos())
    assert test_repo.update_roadmap_metadata(created.id, {"alcance": "carrera", "aviso": "x"}) is True
    assert test_repo.get_roadmap(created.id).metadata_json == {"alcance": "carrera", "aviso": "x"}
    assert test_repo.update_roadmap_metadata(9999, {}) is False


# --- 024 · R4 / R7 / R10: validación de prelaciones, alta en bloque y ajustes del grafo ---

@pytest.fixture
def ruta_abc(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos())
    a, b = created.modulos[0].temas
    c = created.modulos[1].temas[0]
    return created.id, a.id, b.id, c.id


def _pares_guardados(repo, ruta_id):
    return [(e.tema_origen_id, e.tema_destino_id, e.tipo) for e in repo.get_prerequisites(ruta_id)]


def test_add_prerequisite_rechaza_tema_de_otra_ruta(test_repo, ruta_abc):
    ruta_id, a, _, _ = ruta_abc
    otra = test_repo.create_roadmap(_ruta_con_prerrequisitos("Otra ruta"))
    ajeno = otra.modulos[0].temas[0].id

    for origen, destino in [(a, ajeno), (ajeno, a), (a, 9999)]:
        with pytest.raises(ValueError, match="no pertenece a la ruta") as exc:
            test_repo.add_prerequisite(ruta_id, origen, destino)
        assert not isinstance(exc.value, PrerequisiteCycleError)

    assert test_repo.get_prerequisites(ruta_id) == []
    assert test_repo.get_prerequisites(otra.id) == []


def test_add_prerequisite_rechaza_autorreferencia_y_tipo_desconocido(test_repo, ruta_abc):
    ruta_id, a, b, _ = ruta_abc
    with pytest.raises(ValueError, match="sí mismo"):
        test_repo.add_prerequisite(ruta_id, a, a)
    with pytest.raises(ValueError, match="Tipo de prelación"):
        test_repo.add_prerequisite(ruta_id, a, b, tipo="opcional")
    assert test_repo.get_prerequisites(ruta_id) == []


def test_add_prerequisite_rechaza_ciclo_directo_e_indirecto(test_repo, ruta_abc):
    ruta_id, a, b, c = ruta_abc
    test_repo.add_prerequisite(ruta_id, a, b)
    test_repo.add_prerequisite(ruta_id, b, c, tipo="recomendada")

    with pytest.raises(PrerequisiteCycleError):
        test_repo.add_prerequisite(ruta_id, b, a)
    with pytest.raises(PrerequisiteCycleError):
        test_repo.add_prerequisite(ruta_id, c, a)

    assert _pares_guardados(test_repo, ruta_id) == [(a, b, "estricta"), (b, c, "recomendada")]


def test_add_prerequisite_repetida_actualiza_el_tipo_sin_duplicar(test_repo, ruta_abc):
    ruta_id, a, b, _ = ruta_abc
    primera = test_repo.add_prerequisite(ruta_id, a, b, tipo="estricta")
    segunda = test_repo.add_prerequisite(ruta_id, a, b, tipo="recomendada")

    assert segunda["id"] == primera["id"]
    assert segunda["tipo"] == "recomendada"
    assert _pares_guardados(test_repo, ruta_id) == [(a, b, "recomendada")]


def test_add_prerequisites_bulk_guarda_todas(test_repo, ruta_abc):
    ruta_id, a, b, c = ruta_abc
    test_repo.add_prerequisite(ruta_id, a, b, tipo="recomendada")

    guardadas = test_repo.add_prerequisites_bulk(
        ruta_id,
        [
            PrerequisiteCreate(tema_origen_id=a, tema_destino_id=b, tipo="estricta"),
            PrerequisiteCreate(tema_origen_id=b, tema_destino_id=c, tipo="recomendada"),
            PrerequisiteCreate(tema_origen_id=a, tema_destino_id=c),
        ],
    )

    assert guardadas == 3
    # La que ya existía cambia de tipo; las otras dos se agregan.
    assert _pares_guardados(test_repo, ruta_id) == [(a, b, "estricta"), (b, c, "recomendada"), (a, c, "estricta")]


@pytest.mark.parametrize("invalida", ["ciclo_con_guardadas", "ciclo_dentro_del_lote", "tema_ajeno", "autorreferencia"])
def test_add_prerequisites_bulk_con_una_invalida_no_guarda_ninguna(test_repo, ruta_abc, invalida):
    ruta_id, a, b, c = ruta_abc
    test_repo.add_prerequisite(ruta_id, a, b)
    ultima, error = {
        "ciclo_con_guardadas": ((b, a), PrerequisiteCycleError),
        "ciclo_dentro_del_lote": ((c, b), PrerequisiteCycleError),
        "tema_ajeno": ((a, 9999), ValueError),
        "autorreferencia": ((c, c), ValueError),
    }[invalida]

    with pytest.raises(error) as exc:
        test_repo.add_prerequisites_bulk(
            ruta_id,
            [
                PrerequisiteCreate(tema_origen_id=b, tema_destino_id=c),
                PrerequisiteCreate(tema_origen_id=a, tema_destino_id=b, tipo="recomendada"),
                PrerequisiteCreate(tema_origen_id=ultima[0], tema_destino_id=ultima[1]),
            ],
        )

    assert isinstance(exc.value, PrerequisiteCycleError) is (error is PrerequisiteCycleError)
    # Ni la primera del lote (válida) ni el cambio de tipo de la segunda quedaron guardados.
    assert _pares_guardados(test_repo, ruta_id) == [(a, b, "estricta")]


def test_update_graph_settings_conserva_el_resto_del_metadata(test_repo, ruta_abc):
    ruta_id, *_ = ruta_abc
    perfil = {"disciplina": "Psicología", "secciones": ["x"]}
    test_repo.update_roadmap_metadata(ruta_id, {"alcance": "curso", "perfil_pedagogico": perfil, "grafo": {"otro": 1}})

    assert test_repo.update_graph_settings(ruta_id, secuencia_implicita=False) is True
    assert test_repo.get_roadmap(ruta_id).metadata_json == {
        "alcance": "curso",
        "perfil_pedagogico": perfil,
        "grafo": {"otro": 1, "secuencia_implicita": False},
    }

    assert test_repo.update_graph_settings(ruta_id, secuencia_implicita=True) is True
    assert test_repo.get_roadmap(ruta_id).metadata_json["grafo"] == {"otro": 1, "secuencia_implicita": True}
    assert test_repo.update_graph_settings(9999, secuencia_implicita=False) is False


def test_update_graph_settings_tolera_un_metadata_que_no_es_un_objeto(test_repo):
    created = test_repo.create_roadmap(_ruta_con_prerrequisitos())
    conn = get_connection(test_repo.db_path)
    try:
        conn.execute("UPDATE rutas_aprendizaje SET metadata_json = ? WHERE id = ?;", ("[]", created.id))
        conn.commit()
    finally:
        conn.close()

    assert test_repo.update_graph_settings(created.id, False) is True
    conn = get_connection(test_repo.db_path)
    try:
        guardado = conn.execute("SELECT metadata_json FROM rutas_aprendizaje WHERE id = ?;", (created.id,)).fetchone()[0]
    finally:
        conn.close()
    assert '"secuencia_implicita": false' in guardado
    assert test_repo.update_graph_settings(9999, True) is False
