"""Bus de eventos del core y emisión de ia.consumo desde la pasarela de IA (050: R7)."""

import logging

from conftest import cuenta_de_prueba

from aulento.core.eventos import IA_CONSUMO, BusDeEventos, bus
from aulento.core.ia.pasarela import ADAPTADORES, PasarelaDeIA
from aulento.core.ia.tipos import ANTHROPIC, Pedido, Respuesta
from aulento.db.connection import get_connection


def test_suscribir_emitir_y_desuscribir():
    eventos = BusDeEventos()
    recibidos = []

    def anotar(**datos):
        recibidos.append(datos)

    eventos.suscribir("algo.paso", anotar)
    eventos.emitir("algo.paso", cuenta=7, valor="x")
    eventos.emitir("otro.evento", cuenta=8)
    assert recibidos == [{"cuenta": 7, "valor": "x"}]

    eventos.desuscribir("algo.paso", anotar)
    eventos.desuscribir("algo.paso", anotar)  # quitar dos veces no falla
    eventos.emitir("algo.paso", cuenta=9)
    assert len(recibidos) == 1


def test_un_suscriptor_que_falla_no_frena_a_los_demas_ni_a_quien_emite(caplog):
    eventos = BusDeEventos()
    recibidos = []

    def roto(**_datos):
        raise RuntimeError("se rompió el suscriptor")

    eventos.suscribir("algo.paso", roto)
    eventos.suscribir("algo.paso", lambda **datos: recibidos.append(datos))

    with caplog.at_level(logging.ERROR, logger="aulento.core.eventos"):
        eventos.emitir("algo.paso", cuenta=1)

    assert recibidos == [{"cuenta": 1}]
    assert "algo.paso" in caplog.text


def _anotar(pasarela: PasarelaDeIA, repo) -> None:
    pasarela._anotar(
        repo,
        proveedor="gemini",
        modelo="gemini-test",
        endpoint_tipo="tutor",
        nivel="flash",
        tokens_entrada=120,
        tokens_salida=45,
        tokens_totales=165,
        costo_usd=None,
        estado=200,
        latencia_ms=12.5,
    )


def test_la_pasarela_emite_ia_consumo_al_anotar(isolated_cloud_env):
    recibidos = []

    def escuchar(**datos):
        recibidos.append(datos)

    conn = get_connection()
    bus.suscribir(IA_CONSUMO, escuchar)
    try:
        cuenta = cuenta_de_prueba(conn, "cuenta-del-evento")
        _anotar(PasarelaDeIA(conn, cuenta.id), repo=None)
    finally:
        bus.desuscribir(IA_CONSUMO, escuchar)
        conn.close()

    assert recibidos == [
        {
            "user_id": cuenta.id,
            "proveedor": "gemini",
            "modelo": "gemini-test",
            "endpoint_tipo": "tutor",
            "tokens_entrada": 120,
            "tokens_salida": 45,
            "tokens_totales": 165,
            "estado": 200,
        }
    ]


def test_la_pasarela_emite_aunque_falle_la_anotacion(isolated_cloud_env):
    """Si el registro local falla, quien escucha igual se entera del consumo."""

    class RepoRoto:
        def log_api_usage(self, **_fila):
            raise RuntimeError("la base no está")

    recibidos = []

    def escuchar(**datos):
        recibidos.append(datos)

    def suscriptor_roto(**_datos):
        raise RuntimeError("la extensión falló")

    conn = get_connection()
    bus.suscribir(IA_CONSUMO, suscriptor_roto)
    bus.suscribir(IA_CONSUMO, escuchar)
    try:
        cuenta = cuenta_de_prueba(conn, "cuenta-del-repo-roto")
        _anotar(PasarelaDeIA(conn, cuenta.id), repo=RepoRoto())  # no levanta
    finally:
        bus.desuscribir(IA_CONSUMO, suscriptor_roto)
        bus.desuscribir(IA_CONSUMO, escuchar)
        conn.close()

    assert [d["tokens_entrada"] for d in recibidos] == [120]


def test_generar_por_la_pasarela_emite_ia_consumo(isolated_cloud_env, monkeypatch):
    """Por el camino público: `generar` con un proveedor falso anota y emite el evento con sus tokens."""
    respuesta = Respuesta(texto="hola", proveedor=ANTHROPIC, modelo="claude-falso", tokens_entrada=33, tokens_salida=7)
    monkeypatch.setattr(ADAPTADORES[ANTHROPIC], "generar", lambda pedido, clave, modelo: respuesta)
    recibidos = []

    def escuchar(**datos):
        recibidos.append(datos)

    conn = get_connection()
    bus.suscribir(IA_CONSUMO, escuchar)
    try:
        cuenta = cuenta_de_prueba(conn, "cuenta-por-generar")
        pasarela = PasarelaDeIA(conn, cuenta.id)
        pasarela.guardar_clave(ANTHROPIC, "sk-ant-" + "centinela-del-evento-0000AAAA")
        pasarela.fijar_proveedor(ANTHROPIC)
        assert pasarela.generar(Pedido(usuario="Hola"), "tutor").texto == "hola"
    finally:
        bus.desuscribir(IA_CONSUMO, escuchar)
        conn.close()

    assert len(recibidos) == 1
    assert recibidos[0]["user_id"] == cuenta.id
    assert recibidos[0]["proveedor"] == ANTHROPIC
    assert recibidos[0]["endpoint_tipo"] == "tutor"
    assert (recibidos[0]["tokens_entrada"], recibidos[0]["tokens_salida"]) == (33, 7)


def test_una_funcion_registrada_dos_veces_se_llama_una_vez_hasta_quitar_ambas():
    """Dos apps con la misma extensión en un proceso: el débito no se duplica, y cerrar una no corta a la otra."""
    eventos = BusDeEventos()
    llamadas = []

    def debitar(**datos):
        llamadas.append(datos)

    eventos.suscribir("ia.consumo", debitar)
    eventos.suscribir("ia.consumo", debitar)
    eventos.emitir("ia.consumo", n=1)
    assert llamadas == [{"n": 1}]

    eventos.desuscribir("ia.consumo", debitar)
    eventos.emitir("ia.consumo", n=2)
    assert llamadas == [{"n": 1}, {"n": 2}]

    eventos.desuscribir("ia.consumo", debitar)
    eventos.emitir("ia.consumo", n=3)
    assert llamadas == [{"n": 1}, {"n": 2}]
