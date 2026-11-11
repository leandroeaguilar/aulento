"""Tests para PrerequisiteGraphEngine (DAG, Topological Sort, Ciclos, Ruta Crítica y Mermaid)."""

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
    EstadoTema,
)
from aulento.roadmap.graph_engine import PrerequisiteGraphEngine, detecta_ciclo


@pytest.fixture
def repo_and_graph(tmp_path):
    db_file = tmp_path / "test_graph.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()

    repo = RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))
    graph_engine = PrerequisiteGraphEngine(repo=repo)

    # Crear una ruta de prueba con 2 módulos y varios temas
    data = RoadmapCreate(
        titulo="Ruta DAG Test",
        modulos=[
            RoadmapModuleCreate(
                titulo="Módulo 1: Fundamentos",
                orden=1,
                temas=[
                    RoadmapTopicCreate(titulo="Tema 1A", orden=1),
                    RoadmapTopicCreate(titulo="Tema 1B", orden=2),
                ],
            ),
            RoadmapModuleCreate(
                titulo="Módulo 2: Avanzado",
                orden=2,
                temas=[
                    RoadmapTopicCreate(titulo="Tema 2A", orden=1),
                    RoadmapTopicCreate(titulo="Tema 2B", orden=2),
                ],
            ),
        ],
    )
    roadmap = repo.create_roadmap(data)
    return repo, graph_engine, roadmap


def _guardar_arista_sin_validar(repo, ruta_id, origen_id, destino_id, tipo="estricta"):
    """Inserta la arista directo en la tabla: simula datos previos a la validación de ciclos."""
    conn = get_connection(repo.db_path)
    try:
        conn.execute(
            "INSERT INTO ruta_prelaciones (ruta_id, tema_origen_id, tema_destino_id, tipo) VALUES (?, ?, ?, ?);",
            (ruta_id, origen_id, destino_id, tipo),
        )
        conn.commit()
    finally:
        conn.close()


def _desactivar_secuencia_implicita(repo, ruta_id):
    assert repo.update_roadmap_metadata(ruta_id, {"grafo": {"secuencia_implicita": False}}) is True


def _ids(roadmap):
    return [t.id for m in roadmap.modulos for t in m.temas]


def _pares(graph_data, inferida=None):
    return [
        (e.tema_origen_id, e.tema_destino_id)
        for e in graph_data.edges
        if inferida is None or e.inferida is inferida
    ]


def test_auto_inferred_dag(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph

    graph_data = graph_engine.get_graph_data(roadmap.id)
    assert not graph_data.has_cycle
    assert len(graph_data.nodes) == 4
    # 4 temas conectados secuencialmente = 3 aristas
    assert len(graph_data.edges) == 3
    assert len(graph_data.topological_order) == 4
    assert len(graph_data.critical_path) == 4
    assert "graph TD" in graph_data.mermaid_code


def test_blocked_status_and_unlocking(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    t1a_id = roadmap.modulos[0].temas[0].id
    t1b_id = roadmap.modulos[0].temas[1].id

    # Inicialmente, Tema 1A está PENDIENTE, por ende Tema 1B debe estar bloqueado
    data_initial = graph_engine.get_graph_data(roadmap.id)
    node_1b = next(n for n in data_initial.nodes if n.id == t1b_id)
    assert node_1b.is_blocked is True

    # Completar Tema 1A
    repo.update_topic_status(t1a_id, EstadoTema.COMPLETADO)

    # Ahora Tema 1B ya no debe estar bloqueado
    data_updated = graph_engine.get_graph_data(roadmap.id)
    node_1b_unlocked = next(n for n in data_updated.nodes if n.id == t1b_id)
    assert node_1b_unlocked.is_blocked is False


def test_custom_prerequisites_and_cycle_detection(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    t1a_id = roadmap.modulos[0].temas[0].id
    t1b_id = roadmap.modulos[0].temas[1].id

    # Ciclo guardado antes de que existiera la validación: 1A -> 1B y 1B -> 1A
    _guardar_arista_sin_validar(repo, roadmap.id, t1a_id, t1b_id)
    _guardar_arista_sin_validar(repo, roadmap.id, t1b_id, t1a_id)

    graph_data = graph_engine.get_graph_data(roadmap.id)
    assert graph_data.has_cycle is True


def test_mermaid_generation_content(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    graph_data = graph_engine.get_graph_data(roadmap.id)

    mermaid = graph_data.mermaid_code
    assert "classDef completed" in mermaid
    assert "classDef blocked" in mermaid
    assert "subgraph M_" in mermaid
    assert "-->" in mermaid


# --- 024 · R1: orden topológico estable con desempate curricular ---

def test_ruta_sin_prelaciones_queda_en_orden_curricular_y_solo_el_primero_disponible(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)

    data = graph_engine.get_graph_data(roadmap.id)

    assert data.topological_order == [a, b, c, d]
    assert [n.id for n in data.nodes] == [a, b, c, d]
    assert data.disponibles == [a]
    assert data.secuencia_implicita is True
    assert _pares(data, inferida=True) == [(a, b), (b, c), (c, d)]
    assert all(e.id is None and e.tipo == "estricta" for e in data.edges)
    # Las aristas inferidas no se persisten.
    assert repo.get_prerequisites(roadmap.id) == []


def test_orden_topologico_desempata_por_posicion_curricular_y_es_estable(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    _desactivar_secuencia_implicita(repo, roadmap.id)
    # Única restricción: 2B va antes que 1A. El resto no tiene relación entre sí.
    repo.add_prerequisite(roadmap.id, d, a)

    primera = graph_engine.get_graph_data(roadmap.id)
    segunda = graph_engine.get_graph_data(roadmap.id)

    # 1B y 2A no dependen de nadie: salen en su orden curricular; 1A espera a 2B.
    assert primera.topological_order == [b, c, d, a]
    assert segunda.topological_order == primera.topological_order
    assert [n.orden for n in primera.nodes] == [1, 2, 3, 4]


def test_con_ciclo_guardado_el_orden_es_el_curricular(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    _guardar_arista_sin_validar(repo, roadmap.id, d, c)
    _guardar_arista_sin_validar(repo, roadmap.id, c, d)

    data = graph_engine.get_graph_data(roadmap.id)

    assert data.has_cycle is True
    assert data.topological_order == [a, b, c, d]
    assert data.critical_path == []


# --- 024 · R2: secuencia implícita por tema ---

def test_una_prelacion_guardada_no_borra_la_secuencia_del_resto(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    repo.add_prerequisite(roadmap.id, a, c)

    data = graph_engine.get_graph_data(roadmap.id)

    assert _pares(data, inferida=False) == [(a, c)]
    # 2A ya tiene una prelación guardada: no recibe la inferida desde 1B. Los demás la conservan.
    assert _pares(data, inferida=True) == [(a, b), (c, d)]
    nodos = {n.id: n for n in data.nodes}
    assert [nodos[t].is_blocked for t in (a, b, c, d)] == [False, True, True, True]
    assert data.disponibles == [a]
    assert [e.id for e in data.edges if e.inferida] == [None, None]
    assert all(e.id is not None for e in data.edges if not e.inferida)


def test_arista_inferida_se_omite_si_cerraria_un_ciclo(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    # 2B es prerrequisito de 1A: la secuencia 1A→1B→2A→2B cerraría el ciclo en su último tramo.
    repo.add_prerequisite(roadmap.id, d, a)

    data = graph_engine.get_graph_data(roadmap.id)

    assert data.has_cycle is False
    assert _pares(data, inferida=True) == [(a, b), (b, c)]
    assert (c, d) not in _pares(data)
    assert data.topological_order == [d, a, b, c]
    assert data.disponibles == [d]


def test_secuencia_implicita_desactivada_deja_solo_las_guardadas(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    repo.add_prerequisite(roadmap.id, a, c)
    _desactivar_secuencia_implicita(repo, roadmap.id)

    data = graph_engine.get_graph_data(roadmap.id)

    assert data.secuencia_implicita is False
    assert _pares(data) == [(a, c)]
    assert not any(e.inferida for e in data.edges)
    assert data.disponibles == [a, b, d]


# --- 024 · R3: solo lo estricto bloquea ---

def test_arista_recomendada_no_bloquea_ni_entra_en_la_ruta_critica(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    _desactivar_secuencia_implicita(repo, roadmap.id)
    repo.add_prerequisite(roadmap.id, a, b, tipo="recomendada")
    repo.add_prerequisite(roadmap.id, b, c, tipo="recomendada")
    repo.add_prerequisite(roadmap.id, c, d, tipo="estricta")

    data = graph_engine.get_graph_data(roadmap.id)
    nodos = {n.id: n for n in data.nodes}

    # La recomendada se muestra, pero no bloquea.
    assert (a, b) in _pares(data)
    assert nodos[b].is_blocked is False and nodos[b].disponible is True
    assert nodos[c].is_blocked is False
    # La estricta sí bloquea.
    assert nodos[d].is_blocked is True and nodos[d].disponible is False
    assert data.disponibles == [a, b, c]
    # La cadena más larga contando recomendadas sería de 4 temas; la crítica solo cuenta estrictas.
    assert data.critical_path == [c, d]
    assert [nodos[t].is_critical_path for t in (a, b, c, d)] == [False, False, True, True]
    assert [nodos[t].nivel_topologico for t in (a, b, c, d)] == [0, 0, 0, 1]


def test_sin_aristas_estrictas_no_hay_ruta_critica(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, _, _ = _ids(roadmap)
    _desactivar_secuencia_implicita(repo, roadmap.id)
    repo.add_prerequisite(roadmap.id, a, b, tipo="recomendada")

    data = graph_engine.get_graph_data(roadmap.id)

    assert data.critical_path == []
    assert not any(n.is_critical_path for n in data.nodes)


# --- 024 · R5: datos por nodo y "qué estudiar ahora" ---

def test_prerequisites_y_dependents_coinciden_con_las_aristas(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    repo.add_prerequisite(roadmap.id, a, d, tipo="recomendada")
    repo.add_prerequisite(roadmap.id, b, d)

    data = graph_engine.get_graph_data(roadmap.id)
    nodos = {n.id: n for n in data.nodes}

    for nodo in data.nodes:
        assert set(nodo.prerequisites) == {o for o, dst in _pares(data) if dst == nodo.id}
        assert set(nodo.dependents) == {dst for o, dst in _pares(data) if o == nodo.id}
        assert nodo.in_degree == len(nodo.prerequisites)
        assert nodo.out_degree == len(nodo.dependents)
    # 2B tiene dos guardadas (no recibe la inferida desde 2A), listadas en orden curricular.
    assert nodos[d].prerequisites == [a, b]
    assert nodos[a].dependents == [b, d]
    assert nodos[c].prerequisites == [b]
    assert [nodos[t].nivel_topologico for t in (a, b, c, d)] == [0, 1, 2, 2]


def test_disponibles_en_orden_curricular_y_sin_completados(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    _desactivar_secuencia_implicita(repo, roadmap.id)
    repo.add_prerequisite(roadmap.id, d, a)
    repo.add_prerequisite(roadmap.id, d, b)
    repo.update_topic_status(d, EstadoTema.COMPLETADO)
    repo.update_topic_status(b, EstadoTema.EN_PROGRESO)

    data = graph_engine.get_graph_data(roadmap.id)
    nodos = {n.id: n for n in data.nodes}

    # El orden topológico empieza por 2A y 2B, pero `disponibles` sigue el orden curricular.
    assert data.topological_order == [c, d, a, b]
    assert data.disponibles == [a, b, c]
    assert [nodos[t].disponible for t in (a, b, c, d)] == [True, True, True, False]
    assert nodos[d].is_blocked is False


def test_detecta_ciclo():
    aristas = [(1, 2), (2, 3)]
    assert detecta_ciclo(aristas, 3, 1) is True
    assert detecta_ciclo(aristas, 2, 1) is True
    assert detecta_ciclo(aristas, 1, 3) is False
    assert detecta_ciclo(aristas, 4, 1) is False
    assert detecta_ciclo([], 5, 5) is True


# --- 024 · R6 / R11: código Mermaid escapado y con estilos por tipo de arista ---

TITULO_HOSTIL = 'Uso de "comillas" [y] corchetes <b>'


def _ruta_con_titulos(repo, *titulos, modulo="Módulo"):
    return repo.create_roadmap(
        RoadmapCreate(
            titulo="Ruta Mermaid",
            modulos=[
                RoadmapModuleCreate(
                    titulo=modulo,
                    temas=[RoadmapTopicCreate(titulo=t, orden=i) for i, t in enumerate(titulos, start=1)],
                )
            ],
        )
    )


def _lineas(mermaid):
    return [linea.strip() for linea in mermaid.split("\n")]


def _lineas_de_nodo(mermaid):
    return [linea for linea in _lineas(mermaid) if linea.startswith("T_") and "[" in linea]


def test_mermaid_escapa_comillas_corchetes_y_angulos_en_los_titulos(repo_and_graph):
    repo, graph_engine, _ = repo_and_graph
    ruta = _ruta_con_titulos(repo, TITULO_HOSTIL, "Tema #2", modulo='Módulo "raro" [x]')
    hostil_id, otro_id = _ids(ruta)

    mermaid = graph_engine.get_graph_data(ruta.id).mermaid_code
    lineas = _lineas_de_nodo(mermaid)

    assert len(lineas) == 2
    for linea in lineas:
        forma = re.fullmatch(r'T_(\d+)\["(.*)"\]', linea)
        assert forma, linea
        assert not set(forma.group(2)) & set('"[]<>')
    assert f'T_{hostil_id}["Uso de #quot;comillas#quot; #91;y#93; corchetes #lt;b#gt;"]' in lineas
    # El `#` literal se escapa primero, sin volver a escapar las entidades ya generadas.
    assert f'T_{otro_id}["🔒 Tema #35;2"]' in lineas
    assert f'subgraph M_{ruta.modulos[0].id} ["Módulo #quot;raro#quot; #91;x#93;"]' in _lineas(mermaid)


def test_mermaid_deja_en_una_linea_un_titulo_con_saltos(repo_and_graph):
    repo, graph_engine, _ = repo_and_graph
    ruta = _ruta_con_titulos(repo, 'Línea uno\n  end\r\nT_99["inyectado"]')
    (tema_id,) = _ids(ruta)

    mermaid = graph_engine.get_graph_data(ruta.id).mermaid_code

    assert _lineas_de_nodo(mermaid) == [f'T_{tema_id}["Línea uno end T_99#91;#quot;inyectado#quot;#93;"]']
    assert _lineas(mermaid).count("end") == 1


def test_mermaid_distingue_aristas_estrictas_recomendadas_e_inferidas(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    repo.add_prerequisite(roadmap.id, a, c, tipo="recomendada")
    repo.add_prerequisite(roadmap.id, a, d, tipo="estricta")

    data = graph_engine.get_graph_data(roadmap.id)
    lineas = _lineas(data.mermaid_code)

    # Orden de emisión: las guardadas (1A⇢2A, 1A→2B) y luego las inferidas 1A→1B y 1B→2A.
    # 2A conserva su arista inferida porque la que tiene guardada es solo recomendada.
    assert _pares(data) == [(a, c), (a, d), (a, b), (b, c)]
    aristas = [linea for linea in lineas if "-->" in linea or "-.->" in linea]
    assert aristas == [f"T_{a} -.-> T_{c}", f"T_{a} --> T_{d}", f"T_{a} --> T_{b}", f"T_{b} --> T_{c}"]
    assert [linea for linea in lineas if linea.startswith("linkStyle")] == [
        "linkStyle 2 stroke:#475569,stroke-dasharray:4 3",
        "linkStyle 3 stroke:#475569,stroke-dasharray:4 3",
    ]


def test_mermaid_tiene_un_linkstyle_por_arista_inferida(repo_and_graph):
    _, graph_engine, roadmap = repo_and_graph
    data = graph_engine.get_graph_data(roadmap.id)

    estilos = [linea for linea in _lineas(data.mermaid_code) if linea.startswith("linkStyle")]
    assert estilos == [f"linkStyle {i} stroke:#475569,stroke-dasharray:4 3" for i in range(3)]


def test_mermaid_marca_disponibles_y_ruta_critica(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, d = _ids(roadmap)
    repo.update_topic_status(a, EstadoTema.COMPLETADO)

    mermaid = graph_engine.get_graph_data(roadmap.id).mermaid_code

    assert "classDef available" in mermaid
    assert f"class T_{a} completed;" in mermaid
    assert f"class T_{b} available;" in mermaid
    assert f"class T_{c} blocked;" in mermaid
    assert f"class T_{a} available;" not in mermaid
    assert f"class T_{c} available;" not in mermaid
    for tema_id in (a, b, c, d):
        assert f"class T_{tema_id} critical;" in mermaid


# --- Correcciones posteriores a la revisión ---

@pytest.fixture
def ruta_con_ids_invertidos(tmp_path):
    """Ruta cuyo orden curricular NO coincide con el orden de ids: detecta un desempate por id."""
    db_file = tmp_path / "test_graph_orden.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()
    repo = RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))
    roadmap = repo.create_roadmap(
        RoadmapCreate(
            titulo="Ruta con orden invertido",
            metadata_json={"grafo": {"secuencia_implicita": False}},
            modulos=[
                RoadmapModuleCreate(titulo="Segundo", orden=2, temas=[RoadmapTopicCreate(titulo="S2", orden=2), RoadmapTopicCreate(titulo="S1", orden=1)]),
                RoadmapModuleCreate(titulo="Primero", orden=1, temas=[RoadmapTopicCreate(titulo="P2", orden=2), RoadmapTopicCreate(titulo="P1", orden=1)]),
            ],
        )
    )
    detalle = repo.get_roadmap(roadmap.id)
    curricular = [t.id for m in detalle.modulos for t in m.temas]
    assert [t.titulo for m in detalle.modulos for t in m.temas] == ["P1", "P2", "S1", "S2"]
    assert curricular != sorted(curricular)
    return repo, PrerequisiteGraphEngine(repo=repo), roadmap.id, curricular


def test_orden_topologico_usa_la_posicion_curricular_y_no_el_id(ruta_con_ids_invertidos):
    _, graph_engine, ruta_id, curricular = ruta_con_ids_invertidos
    data = graph_engine.get_graph_data(ruta_id)
    assert data.edges == []
    assert data.topological_order == curricular
    assert data.disponibles == curricular


def test_con_ciclo_el_orden_es_el_curricular_y_no_el_de_ids(ruta_con_ids_invertidos):
    repo, graph_engine, ruta_id, curricular = ruta_con_ids_invertidos
    _guardar_arista_sin_validar(repo, ruta_id, curricular[0], curricular[1])
    _guardar_arista_sin_validar(repo, ruta_id, curricular[1], curricular[0])
    data = graph_engine.get_graph_data(ruta_id)
    assert data.has_cycle is True
    assert data.topological_order == curricular


def test_una_recomendada_no_reemplaza_la_secuencia_implicita(repo_and_graph):
    # Marcar una prelación como recomendada no debe dejar al tema disponible antes de tiempo.
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, _ = _ids(roadmap)
    repo.add_prerequisite(roadmap.id, a, c, tipo="recomendada")

    data = graph_engine.get_graph_data(roadmap.id)
    assert (b, c) in [(e.tema_origen_id, e.tema_destino_id) for e in data.edges if e.inferida]
    assert data.disponibles == [a]

    repo.add_prerequisite(roadmap.id, a, c, tipo="estricta")
    data = graph_engine.get_graph_data(roadmap.id)
    assert (b, c) not in [(e.tema_origen_id, e.tema_destino_id) for e in data.edges]


def test_un_tema_en_progreso_no_figura_como_bloqueado(repo_and_graph):
    repo, graph_engine, roadmap = repo_and_graph
    a, b, c, _ = _ids(roadmap)
    repo.update_topic_status(c, EstadoTema.EN_PROGRESO)

    data = graph_engine.get_graph_data(roadmap.id)
    nodos = {n.id: n for n in data.nodes}
    assert nodos[c].is_blocked is False and nodos[c].disponible is True
    assert nodos[b].is_blocked is True
    assert data.disponibles == [a, c]
    lineas = _lineas(data.mermaid_code)
    assert f"class T_{c} in_progress;" in lineas
    assert not any(linea.startswith(f'T_{c}["🔒') for linea in lineas)


@pytest.mark.parametrize(
    "titulo",
    [
        "Costos %%{init: {'theme':'forest'}}%% fin",
        "100%%{descuento",
        "Llaves %%{x: {abiertas",
    ],
)
def test_mermaid_no_deja_pasar_directivas_en_los_titulos(tmp_path, titulo):
    db_file = tmp_path / "test_graph_directiva.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()
    repo = RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))
    roadmap = repo.create_roadmap(
        RoadmapCreate(
            titulo="Ruta hostil",
            modulos=[RoadmapModuleCreate(titulo=titulo, temas=[RoadmapTopicCreate(titulo=titulo), RoadmapTopicCreate(titulo="Otro")])],
        )
    )
    codigo = PrerequisiteGraphEngine(repo=repo).get_graph_data(roadmap.id).mermaid_code
    cuerpo = codigo.replace("%% Estilos", "").replace("%% Conexiones", "").replace("%% Asignación", "")
    assert "%%" not in cuerpo
    assert "{" not in cuerpo and "}" not in cuerpo
    assert "'" not in cuerpo
    assert re.search(r'T_\d+\["(🔒 )?Otro"\]', codigo)


def test_mermaid_etiqueta_un_titulo_en_blanco(tmp_path):
    db_file = tmp_path / "test_graph_blanco.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()
    repo = RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))
    roadmap = repo.create_roadmap(
        RoadmapCreate(titulo="Ruta en blanco", modulos=[RoadmapModuleCreate(titulo="   ", temas=[RoadmapTopicCreate(titulo="  ")])])
    )
    codigo = PrerequisiteGraphEngine(repo=repo).get_graph_data(roadmap.id).mermaid_code
    assert '[""]' not in codigo
    assert codigo.count('"(sin título)"') == 2
