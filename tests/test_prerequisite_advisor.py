"""Tests de PrerequisiteAdvisor: sugerencias de prelaciones con IA (024 · R9)."""

import json
from unittest.mock import patch

import pytest
from conftest import cuenta_en
from fastapi.testclient import TestClient

from ia_falsa import ia_sustituida, respuesta_de
from aulento.core.ia.tipos import Respuesta
from aulento.db.connection import get_connection
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.db.schema import create_schema, init_db
from aulento.models.roadmap import (
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
)
from aulento.roadmap.engine import IANoDisponibleError
from aulento.roadmap.prerequisite_advisor import (
    MAX_TEMAS_SUGERENCIA,
    PrerequisiteAdvisor,
)
from aulento.web.app import create_app

PERFIL = {
    "disciplina": "Psicología cognitiva experimental",
    "arquetipo": "ciencias_sociales_salud",
    "rol_docente": "Docente investigador",
    "secciones": [{"titulo": f"Paso {i}", "instruccion": f"Consigna {i}"} for i in range(1, 4)],
    "usa_codigo": False,
    "usa_diagramas": False,
    "tipo_fuentes": "Artículos revisados por pares",
    "origen": "ia",
}


def _ruta(titulos_por_modulo=None, metadata=None, titulo="Psicología Cognitiva"):
    titulos_por_modulo = titulos_por_modulo or {"Bases": ["Percepción", "Atención"], "Procesos": ["Memoria", "Lenguaje"]}
    return RoadmapCreate(
        titulo=titulo,
        categoria="psicologia",
        metadata_json={"perfil_pedagogico": PERFIL} if metadata is None else metadata,
        modulos=[
            RoadmapModuleCreate(
                titulo=modulo,
                orden=i,
                temas=[RoadmapTopicCreate(titulo=t, orden=j) for j, t in enumerate(titulos, start=1)],
            )
            for i, (modulo, titulos) in enumerate(titulos_por_modulo.items(), start=1)
        ],
    )


@pytest.fixture
def repo(tmp_path):
    db_file = tmp_path / "test_advisor.db"
    conn = get_connection(str(db_file))
    create_schema(conn)
    conn.close()
    return RoadmapRepository(cuenta_en(str(db_file)), db_path=str(db_file))


@pytest.fixture
def ruta(repo):
    created = repo.create_roadmap(_ruta())
    return created.id, *[t.id for m in created.modulos for t in m.temas]


def _gateway_result(body) -> Respuesta:
    return respuesta_de(body if isinstance(body, str) else json.dumps(body))


def _sugerir(repo, ruta_id, respuesta, api_key="dummy_key"):
    with ia_sustituida(siempre=respuesta, sin_clave=not api_key) as mock_gen:
        try:
            return PrerequisiteAdvisor(repo=repo).suggest(ruta_id), mock_gen
        except (ValueError, RuntimeError) as exc:
            return exc, mock_gen


def _propuesta(origen, destino, tipo="estricta", motivo="Base conceptual"):
    return {"origen": f"T{origen}", "destino": f"T{destino}", "tipo": tipo, "motivo": motivo}


def _pares(respuesta):
    return [(s.tema_origen_id, s.tema_destino_id) for s in respuesta.sugerencias]


def test_el_prompt_identifica_los_temas_por_codigo_e_incluye_la_disciplina(repo, ruta):
    ruta_id, a, b, c, d = ruta

    _, mock_gen = _sugerir(repo, ruta_id, _gateway_result({"prelaciones": []}))

    pedido, endpoint_tipo, repo_del_consumo = mock_gen.call_args.args
    assert endpoint_tipo == "prerequisite_suggest"
    assert repo_del_consumo is repo
    assert (pedido.temperatura, pedido.json) == (0.1, True)
    prompt = pedido.usuario
    assert prompt.split("\n")[-4:] == [
        f"T{a} | Bases | Percepción",
        f"T{b} | Bases | Atención",
        f"T{c} | Procesos | Memoria",
        f"T{d} | Procesos | Lenguaje",
    ]
    assert "disciplina: Psicología cognitiva experimental" in prompt
    instruccion = pedido.sistema
    assert '"origen": "T12"' in instruccion
    assert "nunca los títulos" in instruccion


def test_devuelve_las_propuestas_validas_con_titulos_tipo_y_motivo(repo, ruta):
    ruta_id, a, b, c, d = ruta
    respuesta, _ = _sugerir(
        repo,
        ruta_id,
        _gateway_result(
            {
                "prelaciones": [
                    _propuesta(a, b, motivo="  La atención opera\nsobre lo percibido.  "),
                    {"origen": f" t{b} ", "destino": f"T{c}", "tipo": "recomendada"},
                    _propuesta(c, d, tipo="obligatoria"),
                ]
            }
        ),
    )

    assert respuesta.descartadas == 0
    assert [s.model_dump() for s in respuesta.sugerencias] == [
        {
            "tema_origen_id": a,
            "tema_destino_id": b,
            "origen_titulo": "Percepción",
            "destino_titulo": "Atención",
            "tipo": "estricta",
            "motivo": "La atención opera sobre lo percibido.",
        },
        {
            "tema_origen_id": b,
            "tema_destino_id": c,
            "origen_titulo": "Atención",
            "destino_titulo": "Memoria",
            "tipo": "recomendada",
            "motivo": "",
        },
        # Un tipo desconocido no bloquea: se propone como recomendada.
        {
            "tema_origen_id": c,
            "tema_destino_id": d,
            "origen_titulo": "Memoria",
            "destino_titulo": "Lenguaje",
            "tipo": "recomendada",
            "motivo": "Base conceptual",
        },
    ]


def test_descarta_inexistentes_autorreferencias_repetidas_guardadas_y_ciclos(repo, ruta):
    ruta_id, a, b, c, d = ruta
    otra = repo.create_roadmap(_ruta({"M": ["Ajeno 1", "Ajeno 2"]}, titulo="Otra ruta"))
    ajeno = otra.modulos[0].temas[0].id
    repo.add_prerequisite(ruta_id, a, b)

    respuesta, _ = _sugerir(
        repo,
        ruta_id,
        _gateway_result(
            {
                "prelaciones": [
                    _propuesta(b, c),  # válida
                    _propuesta(a, 9999),  # código inexistente
                    _propuesta(ajeno, c),  # tema de otra ruta
                    {"origen": "Percepción", "destino": f"T{c}", "tipo": "estricta"},  # título en vez de código
                    _propuesta(c, c),  # auto-referencia
                    _propuesta(b, c, tipo="recomendada"),  # repetida
                    _propuesta(a, b, tipo="recomendada"),  # ya guardada
                    _propuesta(b, a),  # ciclo con la guardada
                    _propuesta(c, a),  # ciclo con la guardada y la propuesta anterior
                    _propuesta(c, d),  # válida
                    _propuesta(d, b),  # ciclo solo entre propuestas
                    "texto suelto",
                    {"destino": f"T{d}"},
                ]
            }
        ),
    )

    assert _pares(respuesta) == [(b, c), (c, d)]
    assert respuesta.descartadas == 11
    # No se persiste nada: sigue solo la que ya estaba guardada.
    assert [(e.tema_origen_id, e.tema_destino_id, e.tipo) for e in repo.get_prerequisites(ruta_id)] == [
        (a, b, "estricta")
    ]
    assert repo.get_prerequisites(otra.id) == []


def test_lista_vacia_es_una_respuesta_valida_sin_sugerencias(repo, ruta):
    respuesta, _ = _sugerir(repo, ruta[0], _gateway_result({"prelaciones": []}))
    assert respuesta.sugerencias == []
    assert respuesta.descartadas == 0


@pytest.mark.parametrize("api_key", [None, ""])
def test_sin_clave_no_llama_a_la_ia(repo, ruta, api_key):
    error, mock_gen = _sugerir(repo, ruta[0], _gateway_result({"prelaciones": []}), api_key=api_key)
    assert isinstance(error, IANoDisponibleError)
    mock_gen.assert_not_called()


@pytest.mark.parametrize(
    "respuesta",
    [
        None,
        _gateway_result(""),
        _gateway_result("esto no es JSON"),
        _gateway_result(["lista", "inesperada"]),
        _gateway_result({"otra_clave": []}),
        _gateway_result({"prelaciones": "ninguna"}),
    ],
)
def test_sin_respuesta_o_con_respuesta_no_utilizable_lanza_ia_no_disponible(repo, ruta, respuesta):
    error, mock_gen = _sugerir(repo, ruta[0], respuesta)
    assert isinstance(error, IANoDisponibleError)
    mock_gen.assert_called_once()
    assert repo.get_prerequisites(ruta[0]) == []


def test_ruta_inexistente_con_un_solo_tema_o_demasiado_grande_lanza_value_error(repo):
    error, mock_gen = _sugerir(repo, 9999, _gateway_result({"prelaciones": []}))
    assert isinstance(error, ValueError) and "no encontrada" in str(error)

    chica = repo.create_roadmap(_ruta({"M": ["Único"]}, titulo="Ruta chica"))
    error, _ = _sugerir(repo, chica.id, _gateway_result({"prelaciones": []}))
    assert isinstance(error, ValueError) and "al menos dos temas" in str(error)

    grande = repo.create_roadmap(_ruta({"M": [f"Tema {i}" for i in range(MAX_TEMAS_SUGERENCIA + 1)]}, titulo="Ruta grande"))
    error, _ = _sugerir(repo, grande.id, _gateway_result({"prelaciones": []}))
    assert isinstance(error, ValueError) and str(MAX_TEMAS_SUGERENCIA) in str(error)
    assert not isinstance(error, IANoDisponibleError)
    mock_gen.assert_not_called()


# --- Endpoint POST /api/roadmap/{id}/prerequisites/suggest ---

@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "web_advisor_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    conn.close()
    return TestClient(create_app())


def _crear_por_api(client, temas=("Percepción", "Atención", "Memoria")):
    created = client.post(
        "/api/roadmap",
        json={"titulo": "Psicología Cognitiva", "modulos": [{"titulo": "Bases", "temas": [{"titulo": t} for t in temas]}]},
    ).json()
    return created["id"], *[t["id"] for t in created["modulos"][0]["temas"]]


def test_endpoint_sin_ia_devuelve_503_y_no_guarda(client):
    ruta_id, *_ = _crear_por_api(client)

    with ia_sustituida(sin_clave=True):
        r = client.post(f"/api/roadmap/{ruta_id}/prerequisites/suggest")

    assert r.status_code == 503
    assert "Gemini" in r.json()["detail"]
    assert all(e["inferida"] for e in client.get(f"/api/roadmap/{ruta_id}/graph").json()["edges"])


def test_endpoint_con_respuesta_no_utilizable_devuelve_503(client):
    ruta_id, *_ = _crear_por_api(client)
    with ia_sustituida(siempre=_gateway_result("no es JSON")):
        r = client.post(f"/api/roadmap/{ruta_id}/prerequisites/suggest")
    assert r.status_code == 503


def test_endpoint_de_ruta_inexistente_devuelve_404(client):
    with ia_sustituida() as mock_gen:
        r = client.post("/api/roadmap/9999/prerequisites/suggest")
    assert r.status_code == 404
    mock_gen.assert_not_called()


def test_endpoint_de_ruta_con_un_solo_tema_devuelve_400(client):
    ruta_id, _ = _crear_por_api(client, temas=("Único",))
    assert client.post(f"/api/roadmap/{ruta_id}/prerequisites/suggest").status_code == 400


def test_endpoint_devuelve_sugerencias_filtradas_sin_persistir(client):
    ruta_id, a, b, c = _crear_por_api(client)
    respuesta = _gateway_result({"prelaciones": [_propuesta(a, c), _propuesta(c, a), _propuesta(b, b)]})
    with ia_sustituida(siempre=respuesta):
        r = client.post(f"/api/roadmap/{ruta_id}/prerequisites/suggest")

    assert r.status_code == 200
    assert r.json() == {
        "sugerencias": [
            {
                "tema_origen_id": a,
                "tema_destino_id": c,
                "origen_titulo": "Percepción",
                "destino_titulo": "Memoria",
                "tipo": "estricta",
                "motivo": "Base conceptual",
            }
        ],
        "descartadas": 2,
    }
    assert all(e["inferida"] for e in client.get(f"/api/roadmap/{ruta_id}/graph").json()["edges"])


def test_no_propone_mas_prelaciones_de_las_que_admite_el_alta_en_bloque():
    from aulento.roadmap.prerequisite_advisor import (
        MAX_SUGERENCIAS,
        PrerequisiteAdvisor,
    )

    titulos = {i: f"Tema {i}" for i in range(1, 41)}
    propuestas = [
        {"origen": f"T{i}", "destino": f"T{j}", "tipo": "recomendada", "motivo": "m"}
        for i in range(1, 41)
        for j in range(i + 1, 41)
    ]
    assert len(propuestas) > MAX_SUGERENCIAS

    respuesta = PrerequisiteAdvisor._filtrar(propuestas, titulos, [])
    assert len(respuesta.sugerencias) == MAX_SUGERENCIAS
    assert respuesta.descartadas == len(propuestas) - MAX_SUGERENCIAS
