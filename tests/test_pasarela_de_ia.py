"""La pasarela de IA por cuenta (035): proveedor, clave y modelo de quien pide, capacidades, errores y consumo.

La red está sustituida por `ia_falsa.RedDeIA`: cada test inspecciona el pedido que habría llegado al proveedor.
"""

import base64
import itertools
import logging
from types import SimpleNamespace

import httpx
import pytest
from conftest import cuenta_de_prueba
from ia_falsa import ANTHROPIC, GEMINI, OPENAI, TEXTO_CRUDO, RedDeIA, instalar_red_de_ia

from aulento.core.gemini_gateway import GeminiGateway
from aulento.core.ia import base
from aulento.core.ia import gemini as adaptador_de_gemini
from aulento.core.ia.base import codigo_sano
from aulento.core.ia.pasarela import ORDEN_DE_REEMPLAZO, PasarelaDeIA
from aulento.core.ia.tarifas import costo_estimado
from aulento.core.ia.tipos import (
    MENSAJE_FALTA_CLAVE,
    Adjunto,
    CapacidadNoSoportada,
    ClaveRechazada,
    CuotaAgotada,
    FaltaClaveDeIA,
    IANoDisponibleError,
    ModeloInexistente,
    Pedido,
    PedidoInvalido,
)
from aulento.db.connection import get_connection
from aulento.db.roadmap_repository import RoadmapRepository

GRATUITA_DE_ANA = "AIzaSy-gratuita-de-ana-0000AAAA"
PAGA_DE_ANA = "AIzaSy-paga-de-ana-00000000PPAA"
GRATUITA_DE_BETO = "AIzaSy-gratuita-de-beto-000BBBB"
ANTHROPIC_DE_ANA = "sk-ant-" + "centinela-de-ana-0000AAAA"
OPENAI_DE_ANA = "sk-" + "proj-centinela-de-ana-000AAAA"
CLAVE_DE = {GEMINI: GRATUITA_DE_ANA, ANTHROPIC: ANTHROPIC_DE_ANA, OPENAI: OPENAI_DE_ANA}
NOMBRE = {GEMINI: "Gemini", ANTHROPIC: "Anthropic", OPENAI: "OpenAI"}
MODELO_DE_OPENAI = "modelo-de-chat-a"
MODELO_ELEGIDO = {GEMINI: "gemini-flash-lite-latest", ANTHROPIC: "claude-opus-5-5", OPENAI: MODELO_DE_OPENAI}
SEGUNDOS = {GEMINI: 45, ANTHROPIC: 180, OPENAI: 45}
URL_DE_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"
PDF = b"%PDF-1.4 un temario de prueba"
AUDIO = b"RIFF un audio de prueba"
# Cuánto «tarda» cada pedido con el reloj de prueba
MILISEGUNDOS_POR_PEDIDO = 250.0

COLUMNAS = (
    "provider, model, endpoint_tipo, api_tier, prompt_tokens, completion_tokens, total_tokens, "
    "estimated_cost_usd, status_code, latency_ms"
)


@pytest.fixture
def red(monkeypatch) -> RedDeIA:
    return instalar_red_de_ia(monkeypatch)


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    """Cada pedido a un proveedor tarda exactamente `MILISEGUNDOS_POR_PEDIDO`."""
    marcas = itertools.count()
    reloj_falso = SimpleNamespace(perf_counter=lambda: next(marcas) * MILISEGUNDOS_POR_PEDIDO / 1000.0)
    monkeypatch.setattr(base, "time", reloj_falso)


@pytest.fixture
def conn():
    conexion = get_connection()
    yield conexion
    conexion.close()


@pytest.fixture
def ana(conn) -> int:
    return cuenta_de_prueba(conn, "ana").id


@pytest.fixture
def beto(conn) -> int:
    return cuenta_de_prueba(conn, "beto").id


def _consumos(cuenta_id: int) -> list[dict]:
    conexion = get_connection()
    try:
        filas = conexion.execute(
            f"SELECT {COLUMNAS} FROM api_usage_logs WHERE user_id = ? ORDER BY id;", (cuenta_id,)
        ).fetchall()
        return [dict(fila) for fila in filas]
    finally:
        conexion.close()


def _todo_el_consumo() -> str:
    conexion = get_connection()
    try:
        return "\n".join(str(tuple(fila)) for fila in conexion.execute("SELECT * FROM api_usage_logs;"))
    finally:
        conexion.close()


def _con(conn, cuenta_id: int, proveedor: str) -> PasarelaDeIA:
    """La pasarela de la cuenta con ese proveedor activo, su clave y su modelo."""
    pasarela = PasarelaDeIA(conn, cuenta_id)
    pasarela.guardar_clave(proveedor, CLAVE_DE[proveedor])
    pasarela.fijar_modelo(proveedor, MODELO_ELEGIDO[proveedor])
    pasarela.fijar_proveedor(proveedor)
    return pasarela


# --- R3: el pedido sale con la clave y el modelo de la cuenta ---


def test_r3_un_pedido_con_gemini_sale_con_la_clave_y_el_modelo_de_la_cuenta(red, conn, ana, beto):
    de_ana, de_beto = PasarelaDeIA(conn, ana), PasarelaDeIA(conn, beto)
    de_ana.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    de_ana.fijar_modelo(GEMINI, "gemini-3.5-flash-lite")
    de_beto.guardar_clave(GEMINI, GRATUITA_DE_BETO)
    red.texto = "Hola, Ana."

    respuesta = de_ana.generar(Pedido(usuario="Saludame.", sistema="Sos un tutor."), "saludo")

    (pedido,) = red.pedidos
    assert (pedido.metodo, pedido.url) == ("POST", f"{URL_DE_GEMINI}/gemini-3.5-flash-lite:generateContent")
    assert pedido.cabeceras == {"x-goog-api-key": GRATUITA_DE_ANA}
    assert pedido.cuerpo == {
        "contents": [{"role": "user", "parts": [{"text": "Saludame."}]}],
        "systemInstruction": {"parts": [{"text": "Sos un tutor."}]},
    }
    assert GRATUITA_DE_ANA not in pedido.url
    assert (respuesta.texto, respuesta.proveedor, respuesta.modelo, respuesta.nivel) == (
        "Hola, Ana.",
        GEMINI,
        "gemini-3.5-flash-lite",
        "free",
    )
    assert (respuesta.tokens_entrada, respuesta.tokens_salida) == (7, 5)
    assert (respuesta.por_capacidad, respuesta.truncada) == (False, False)

    red.vaciar()
    de_beto.generar(Pedido(usuario="Saludame."), "saludo")

    (pedido,) = red.pedidos
    assert pedido.clave == GRATUITA_DE_BETO
    assert pedido.url == f"{URL_DE_GEMINI}/gemini-flash-lite-latest:generateContent"


def test_el_cuerpo_de_gemini_lleva_json_tope_y_adjuntos_como_los_pide_google():
    pedido = Pedido(
        usuario="Resumí el temario.",
        sistema="Sos un tutor.",
        adjuntos=(Adjunto("application/pdf", PDF), Adjunto("audio/wav", AUDIO)),
        json=True,
        esquema={"type": "object", "properties": {"temas": {"type": "array"}}},
        max_tokens=300,
    )

    assert adaptador_de_gemini.ProveedorGemini.cuerpo(pedido) == {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"inlineData": {"mimeType": "application/pdf", "data": base64.b64encode(PDF).decode("ascii")}},
                    {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(AUDIO).decode("ascii")}},
                    {"text": "Resumí el temario."},
                ],
            }
        ],
        "systemInstruction": {"parts": [{"text": "Sos un tutor."}]},
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 300},
    }


def test_un_adjunto_que_no_es_pdf_ni_audio_no_arma_un_pedido():
    with pytest.raises(ValueError, match="image/png"):
        Pedido(usuario="Mirá esto.", adjuntos=(Adjunto("image/png", b"\x89PNG"),))


# --- R4: Gemini conserva la conmutación gratuita → paga y la rotación de modelos ---


def test_r4_ante_un_limite_de_cuota_la_gratuita_cede_a_la_paga_sin_probar_mas_modelos(red, conn, ana):
    GeminiGateway(conn, ana).save_keys_config(free_key=GRATUITA_DE_ANA, paid_key=PAGA_DE_ANA, tier="auto")
    red.estado_por_clave = {GRATUITA_DE_ANA: 429}

    respuesta = PasarelaDeIA(conn, ana).generar(Pedido(usuario="Hola"), "saludo")

    assert red.claves() == [GRATUITA_DE_ANA, PAGA_DE_ANA]
    assert red.modelos() == ["gemini-flash-lite-latest", "gemini-flash-lite-latest"]
    assert (respuesta.nivel, respuesta.modelo) == ("paid", "gemini-flash-lite-latest")
    assert [(c["api_tier"], c["status_code"]) for c in _consumos(ana)] == [("free", 429), ("paid", 200)]


@pytest.mark.parametrize("nivel, clave", [("free", GRATUITA_DE_ANA), ("paid", PAGA_DE_ANA)])
def test_r4_con_un_nivel_fijo_solo_sale_esa_clave(red, conn, ana, nivel, clave):
    GeminiGateway(conn, ana).save_keys_config(free_key=GRATUITA_DE_ANA, paid_key=PAGA_DE_ANA, tier=nivel)
    red.estado_por_clave = {clave: 429}

    with pytest.raises(CuotaAgotada):
        PasarelaDeIA(conn, ana).generar(Pedido(usuario="Hola"), "saludo")

    assert set(red.claves()) == {clave}


def test_r4_si_el_modelo_preferido_falla_se_rota_al_siguiente_con_la_misma_clave(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    pasarela.fijar_modelo(GEMINI, "gemini-3.1-pro")
    red.estado_por_modelo = {"gemini-3.1-pro": 404, "gemini-flash-lite-latest": 500}

    respuesta = pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert red.modelos() == ["gemini-3.1-pro", "gemini-flash-lite-latest", "gemini-3.5-flash-lite"]
    assert set(red.claves()) == {GRATUITA_DE_ANA}
    assert respuesta.modelo == "gemini-3.5-flash-lite"
    assert [(c["model"], c["status_code"]) for c in _consumos(ana)] == [
        ("gemini-3.1-pro", 404),
        ("gemini-flash-lite-latest", 500),
        ("gemini-3.5-flash-lite", 200),
    ]


def test_r4_con_una_sola_clave_el_limite_de_cuota_recorre_toda_la_rotacion(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    pasarela.fijar_modelo(GEMINI, "gemini-3.8-flash")
    red.estado_por_clave = {GRATUITA_DE_ANA: 429}

    with pytest.raises(CuotaAgotada):
        pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert red.modelos() == [
        "gemini-3.8-flash",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-pro-latest",
    ]


def test_r4_si_nada_responde_el_error_es_el_del_modelo_preferido_con_la_ultima_clave(red, conn, ana):
    GeminiGateway(conn, ana).save_keys_config(free_key=GRATUITA_DE_ANA, paid_key=PAGA_DE_ANA, tier="auto")
    red.estado_por_clave = {GRATUITA_DE_ANA: 429}
    red.estado_por_modelo = {modelo: 500 for modelo in adaptador_de_gemini.MODELOS_DE_ROTACION}
    red.estado_por_modelo["gemini-flash-lite-latest"] = 404

    with pytest.raises(IANoDisponibleError) as error:
        PasarelaDeIA(conn, ana).generar(Pedido(usuario="Hola"), "saludo")

    assert type(error.value) is ModeloInexistente
    assert red.claves() == [GRATUITA_DE_ANA] + [PAGA_DE_ANA] * 5


# --- R8: errores uniformes, sin la clave ni el texto crudo del proveedor ---


@pytest.mark.parametrize("proveedor", [GEMINI, ANTHROPIC, OPENAI])
def test_r8_sin_clave_del_proveedor_activo_falta_configurarla_y_no_sale_ningun_pedido(red, conn, ana, proveedor):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.fijar_proveedor(proveedor)

    with pytest.raises(FaltaClaveDeIA) as error:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert f"No hay una clave de {NOMBRE[proveedor]} configurada para tu cuenta" in str(error.value)
    assert (proveedor != GEMINI) or str(error.value) == MENSAJE_FALTA_CLAVE
    assert red.pedidos == [] and _consumos(ana) == []


def test_r8_la_clave_de_otro_proveedor_no_reemplaza_a_la_del_activo_si_el_activo_tiene_la_capacidad(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    pasarela.guardar_clave(OPENAI, OPENAI_DE_ANA)
    pasarela.fijar_proveedor(ANTHROPIC)

    with pytest.raises(FaltaClaveDeIA, match="Anthropic"):
        pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert red.pedidos == []


ERRORES_HTTP = [
    pytest.param(401, ClaveRechazada, "rechazó la clave", id="clave rechazada"),
    pytest.param(403, ClaveRechazada, "no tiene permiso", id="sin permiso"),
    pytest.param(404, ModeloInexistente, "no reconoce el modelo", id="modelo inexistente"),
    pytest.param(429, CuotaAgotada, "agotó su cuota o superó el límite", id="cuota o ritmo"),
    pytest.param(400, PedidoInvalido, "no es válido", id="pedido inválido"),
    pytest.param(500, IANoDisponibleError, "no está disponible en este momento (HTTP 500)", id="proveedor caído"),
    pytest.param(529, IANoDisponibleError, "no está disponible en este momento (HTTP 529)", id="proveedor saturado"),
]


@pytest.mark.parametrize("proveedor", [GEMINI, ANTHROPIC, OPENAI])
@pytest.mark.parametrize("estado, excepcion, dice", ERRORES_HTTP)
def test_r8_cada_falla_del_proveedor_tiene_su_error_y_su_mensaje_sin_la_clave_ni_el_texto_crudo(
    red, conn, ana, caplog, proveedor, estado, excepcion, dice
):
    pasarela = _con(conn, ana, proveedor)
    red.estado_por_clave = {CLAVE_DE[proveedor]: estado}

    with caplog.at_level(logging.DEBUG), pytest.raises(IANoDisponibleError) as error:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert type(error.value) is excepcion
    mensaje = str(error.value)
    assert dice in mensaje and NOMBRE[proveedor] in mensaje
    assert (error.value.proveedor, error.value.estado) == (proveedor, estado)
    # El doble puso la clave y un texto libre en el cuerpo del error: nada de eso sale de la capa
    assert red.pedidos and all(pedido.clave == CLAVE_DE[proveedor] for pedido in red.pedidos)
    for donde in (mensaje, repr(error.value), str(vars(error.value)), caplog.text, _todo_el_consumo()):
        assert CLAVE_DE[proveedor] not in donde
        assert TEXTO_CRUDO not in donde
    # Y el pedido fallido queda anotado con su estado, sin tokens ni costo
    consumos = _consumos(ana)
    assert len(consumos) == len(red.pedidos) == (5 if proveedor == GEMINI else 1)
    assert {(c["provider"], c["status_code"], c["total_tokens"], c["estimated_cost_usd"]) for c in consumos} == {
        (proveedor, estado, 0, 0.0)
    }


@pytest.mark.parametrize("proveedor", [GEMINI, ANTHROPIC, OPENAI])
def test_r8_los_mensajes_de_cada_caso_son_distintos_entre_si(red, conn, ana, proveedor):
    pasarela = _con(conn, ana, proveedor)
    mensajes = []
    for caso in ERRORES_HTTP:
        red.estado_por_clave = {CLAVE_DE[proveedor]: caso.values[0]}
        with pytest.raises(IANoDisponibleError) as error:
            pasarela.generar(Pedido(usuario="Hola"), "saludo")
        mensajes.append(str(error.value))
    red.estado_por_clave = {}
    for falla in (httpx.ConnectError("sin ruta"), httpx.ReadTimeout("venció")):
        red.falla = falla
        with pytest.raises(IANoDisponibleError) as error:
            pasarela.generar(Pedido(usuario="Hola"), "saludo")
        mensajes.append(str(error.value))

    assert len(set(mensajes)) == len(ERRORES_HTTP) + 2


@pytest.mark.parametrize("proveedor", [GEMINI, ANTHROPIC, OPENAI])
def test_r8_con_la_red_caida_o_vencida_el_error_lo_dice_y_no_se_anota_consumo(red, conn, ana, caplog, proveedor):
    pasarela = _con(conn, ana, proveedor)

    red.falla = httpx.ConnectError(f"sin ruta para el pedido con {CLAVE_DE[proveedor]}")
    with caplog.at_level(logging.DEBUG), pytest.raises(IANoDisponibleError) as caida:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")
    red.falla = httpx.ReadTimeout(f"venció el pedido con {CLAVE_DE[proveedor]}")
    with caplog.at_level(logging.DEBUG), pytest.raises(IANoDisponibleError) as vencida:
        pasarela.generar(Pedido(usuario="Hola", timeout=None), "saludo")

    assert type(caida.value) is type(vencida.value) is IANoDisponibleError
    assert str(caida.value) == f"No se pudo conectar con {NOMBRE[proveedor]}. Revisá la conexión y probá de nuevo."
    assert str(vencida.value) == (
        f"{NOMBRE[proveedor]} tardó más de {SEGUNDOS[proveedor]} segundos en responder. Probá de nuevo."
    )
    assert caida.value.__cause__ is None and caida.value.__suppress_context__
    assert CLAVE_DE[proveedor] not in caplog.text
    assert _consumos(ana) == []


@pytest.mark.parametrize("proveedor", [GEMINI, ANTHROPIC, OPENAI])
def test_r8_una_respuesta_que_no_es_json_no_llega_al_mensaje(red, conn, ana, caplog, proveedor):
    pasarela = _con(conn, ana, proveedor)
    red.cuerpos[proveedor] = f"<html>{TEXTO_CRUDO}</html>"

    with caplog.at_level(logging.DEBUG), pytest.raises(IANoDisponibleError) as error:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert str(error.value) == f"{NOMBRE[proveedor]} devolvió una respuesta que no se pudo leer."
    assert TEXTO_CRUDO not in caplog.text


def test_r8_del_cuerpo_del_error_solo_pasa_un_codigo_corto_y_saneado(red, conn, ana):
    pasarela = _con(conn, ana, ANTHROPIC)
    red.estado_por_clave = {ANTHROPIC_DE_ANA: 400}

    with pytest.raises(PedidoInvalido) as con_codigo:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")
    red.codigos[ANTHROPIC] = f"{TEXTO_CRUDO} con espacios"
    with pytest.raises(PedidoInvalido) as sin_codigo:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert str(con_codigo.value) == "Anthropic rechazó el pedido porque no es válido (invalid_request_error)."
    assert con_codigo.value.codigo == "invalid_request_error"
    assert str(sin_codigo.value) == "Anthropic rechazó el pedido porque no es válido."
    assert sin_codigo.value.codigo is None


def test_el_saneado_de_codigos_descarta_texto_libre_claves_y_lo_que_no_es_un_identificador():
    assert codigo_sano("rate_limit_error") == "rate_limit_error"
    assert codigo_sano("RESOURCE_EXHAUSTED") == "RESOURCE_EXHAUSTED"
    assert codigo_sano(429) == "429"
    assert codigo_sano("un mensaje con espacios") is None
    assert codigo_sano("x" * 49) is None
    assert codigo_sano("") is None
    assert codigo_sano(None) is None
    assert codigo_sano({"type": "x"}) is None
    assert codigo_sano(True) is None
    assert codigo_sano(f"clave-{ANTHROPIC_DE_ANA}"[:48], clave="clave") is None
    assert codigo_sano("sk-ant-1234", clave="sk-ant-1234") is None


def test_r8_openai_distingue_la_cuota_agotada_del_limite_de_ritmo(red, conn, ana):
    pasarela = _con(conn, ana, OPENAI)
    red.estado_por_clave = {OPENAI_DE_ANA: 429}

    with pytest.raises(CuotaAgotada) as por_ritmo:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")
    red.codigos[OPENAI] = "insufficient_quota"
    with pytest.raises(CuotaAgotada) as sin_saldo:
        pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert "superó el límite de pedidos" in str(por_ritmo.value)
    assert "no tiene cuota disponible" in str(sin_saldo.value)
    assert sin_saldo.value.codigo == "insufficient_quota"


# --- R9: el consumo queda a nombre de la cuenta ---


def test_r9_el_consumo_queda_a_nombre_de_la_cuenta_con_proveedor_modelo_tokens_latencia_y_costo(red, conn, ana, beto):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    PasarelaDeIA(conn, beto).guardar_clave(GEMINI, GRATUITA_DE_BETO)

    respuesta = pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert _consumos(ana) == [
        {
            "provider": GEMINI,
            "model": "gemini-flash-lite-latest",
            "endpoint_tipo": "saludo",
            "api_tier": "free",
            "prompt_tokens": 7,
            "completion_tokens": 5,
            "total_tokens": 12,
            # 7 tokens a 0,10 USD el millón y 5 a 0,40
            "estimated_cost_usd": pytest.approx(0.000003),
            "status_code": 200,
            "latency_ms": MILISEGUNDOS_POR_PEDIDO,
        }
    ]
    assert respuesta.costo_usd == pytest.approx(0.000003)
    assert respuesta.latencia_ms == MILISEGUNDOS_POR_PEDIDO
    assert _consumos(beto) == []


def test_r9_un_modelo_sin_tarifa_deja_el_costo_vacio(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    pasarela.fijar_modelo(GEMINI, "gemini-que-todavia-no-tiene-tarifa")

    respuesta = pasarela.generar(Pedido(usuario="Hola"), "saludo")

    (consumo,) = _consumos(ana)
    assert (consumo["model"], consumo["total_tokens"]) == ("gemini-que-todavia-no-tiene-tarifa", 12)
    assert consumo["estimated_cost_usd"] is None
    assert respuesta.costo_usd is None


def test_las_tarifas_conocidas_y_las_que_no():
    assert costo_estimado(GEMINI, "gemini-pro-latest", 1_000_000, 1_000_000) == 11.25
    assert costo_estimado(ANTHROPIC, "claude-opus-5-5", 1_000_000, 1_000_000) == 24.0
    assert costo_estimado(ANTHROPIC, "claude-sonnet-5-5", 1_000_000, 1_000_000) == 12.0
    assert costo_estimado(ANTHROPIC, "claude-haiku-5-5", 1_000_000, 1_000_000) == 0.6
    assert costo_estimado(ANTHROPIC, "claude-opus-5-5", 2_000_000, 0) == 8.0
    assert costo_estimado(ANTHROPIC, "claude-opus-5-5", 0, 500_000) == 10.0
    assert costo_estimado(ANTHROPIC, "claude-de-otra-generacion", 1_000_000, 1_000_000) is None
    assert costo_estimado(OPENAI, MODELO_DE_OPENAI, 1_000_000, 1_000_000) is None
    # La tarifa es del modelo en su proveedor, no del nombre suelto
    assert costo_estimado(GEMINI, "claude-opus-5-5", 1_000_000, 1_000_000) is None


def test_r9_el_repositorio_guarda_el_proveedor_y_admite_el_costo_vacio(ana, beto):
    repo = RoadmapRepository(ana)

    repo.log_api_usage(
        model="modelo-nuevo",
        endpoint_tipo="clase",
        api_tier="paid",
        prompt_tokens=3,
        completion_tokens=2,
        total_tokens=5,
        estimated_cost_usd=None,
        latency_ms=12.5,
        provider=OPENAI,
    )

    (consumo,) = _consumos(ana)
    assert (consumo["provider"], consumo["model"], consumo["estimated_cost_usd"]) == (OPENAI, "modelo-nuevo", None)
    assert _consumos(beto) == []
    # Las lecturas del consumo siguen sumando: un costo vacío no cuenta
    resumen = repo.get_token_usage_summary()
    assert (resumen.total_requests, resumen.total_estimated_cost_usd) == (1, 0.0)


def test_r9_con_el_repositorio_de_la_cuenta_el_consumo_se_anota_ahi(red, conn, ana):
    pasarela = _con(conn, ana, ANTHROPIC)
    anotados = []

    class Repositorio(RoadmapRepository):
        def log_api_usage(self, **fila):
            anotados.append(fila)
            return super().log_api_usage(**fila)

    pasarela.generar(Pedido(usuario="Hola"), "saludo", repo=Repositorio(ana))

    assert [(fila["provider"], fila["model"], fila["endpoint_tipo"]) for fila in anotados] == [
        (ANTHROPIC, "claude-opus-5-5", "saludo")
    ]
    assert len(_consumos(ana)) == 1


def test_r9_el_consumo_no_se_anota_en_el_repositorio_de_otra_cuenta(red, conn, ana, beto):
    pasarela = _con(conn, ana, GEMINI)

    with pytest.raises(ValueError, match="se anota en la cuenta que hace la llamada"):
        pasarela.generar(Pedido(usuario="Hola"), "saludo", repo=RoadmapRepository(beto))

    assert red.pedidos == []
    assert _consumos(ana) == _consumos(beto) == []


def test_r9_una_falla_al_anotar_no_tapa_la_respuesta(red, conn, ana, caplog):
    pasarela = _con(conn, ana, GEMINI)
    red.texto = "La respuesta llegó."

    class RepositorioRoto(RoadmapRepository):
        def log_api_usage(self, **fila):
            raise RuntimeError(f"no se pudo escribir la fila de {GRATUITA_DE_ANA}")

    with caplog.at_level(logging.DEBUG):
        respuesta = pasarela.generar(Pedido(usuario="Hola"), "saludo", repo=RepositorioRoto(ana))

    assert respuesta.texto == "La respuesta llegó."
    assert "No se pudo anotar el consumo de IA" in caplog.text
    assert GRATUITA_DE_ANA not in caplog.text


def test_la_pasarela_con_conexion_propia_usa_la_misma_cuenta_y_la_misma_base(red, conn, ana, beto):
    PasarelaDeIA(conn, ana).guardar_clave(GEMINI, GRATUITA_DE_ANA)
    PasarelaDeIA(conn, beto).guardar_clave(GEMINI, GRATUITA_DE_BETO)

    PasarelaDeIA.con_conexion_propia(ana).generar(Pedido(usuario="Hola"), "propia")
    PasarelaDeIA.de_repositorio(RoadmapRepository(beto)).generar(Pedido(usuario="Hola"), "de_repositorio")

    assert red.claves() == [GRATUITA_DE_ANA, GRATUITA_DE_BETO]
    assert [c["endpoint_tipo"] for c in _consumos(ana)] == ["propia"]
    assert [c["endpoint_tipo"] for c in _consumos(beto)] == ["de_repositorio"]


# --- R6: lo que el proveedor activo no soporta ---


def test_el_orden_de_reemplazo_por_capacidad_es_fijo():
    assert ORDEN_DE_REEMPLAZO == (GEMINI, OPENAI, ANTHROPIC)


@pytest.mark.parametrize("activo", [ANTHROPIC, OPENAI])
def test_r6_el_audio_lo_atiende_gemini_si_la_cuenta_tiene_su_clave_y_la_respuesta_lo_dice(red, conn, ana, activo):
    pasarela = _con(conn, ana, activo)
    pasarela.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    con_audio = Pedido(usuario="Evaluá la pronunciación.", adjuntos=(Adjunto("audio/wav", AUDIO),))

    respuesta = pasarela.generar(con_audio, "audio")

    assert [pedido.proveedor for pedido in red.pedidos] == [GEMINI]
    assert red.claves() == [GRATUITA_DE_ANA]
    assert (respuesta.proveedor, respuesta.por_capacidad) == (GEMINI, True)
    assert [(c["provider"], c["endpoint_tipo"]) for c in _consumos(ana)] == [(GEMINI, "audio")]

    # Lo que el activo sí sabe hacer lo sigue atendiendo el activo
    red.vaciar()
    respuesta = pasarela.generar(Pedido(usuario="Leé esto.", adjuntos=(Adjunto("application/pdf", PDF),)), "pdf")

    assert [pedido.proveedor for pedido in red.pedidos] == [activo]
    assert (respuesta.proveedor, respuesta.por_capacidad) == (activo, False)


@pytest.mark.parametrize("activo", [ANTHROPIC, OPENAI])
def test_r6_sin_un_proveedor_con_la_capacidad_el_error_dice_que_falta_y_quien_la_ofrece(red, conn, ana, activo):
    pasarela = _con(conn, ana, activo)
    con_audio = Pedido(usuario="Evaluá la pronunciación.", adjuntos=(Adjunto("audio/wav", AUDIO),))

    with pytest.raises(CapacidadNoSoportada) as error:
        pasarela.generar(con_audio, "audio")

    assert str(error.value) == (
        f"{NOMBRE[activo]}, tu proveedor de IA activo, no puede evaluar audio. "
        "Esa capacidad la ofrece Gemini: cargá su clave en Configuración para usarla."
    )
    assert (error.value.capacidad, error.value.quienes_la_ofrecen) == ("audio", (GEMINI,))
    assert isinstance(error.value, IANoDisponibleError) and not isinstance(error.value, FaltaClaveDeIA)
    assert red.pedidos == []


def test_r6_los_embeddings_los_calcula_el_primero_del_orden_que_tiene_clave(red, conn, ana):
    pasarela = _con(conn, ana, ANTHROPIC)

    with pytest.raises(CapacidadNoSoportada) as error:
        pasarela.embeber("Kubernetes")
    assert "no puede calcular embeddings" in str(error.value)
    assert "la ofrece Gemini o OpenAI" in str(error.value)
    assert red.pedidos == []

    pasarela.guardar_clave(OPENAI, OPENAI_DE_ANA)
    de_openai = pasarela.embeber("Kubernetes")
    pasarela.guardar_clave(GEMINI, GRATUITA_DE_ANA)
    de_gemini = pasarela.embeber("Kubernetes")

    assert [pedido.proveedor for pedido in red.pedidos] == [OPENAI, GEMINI]
    assert (de_openai.proveedor, de_openai.modelo, de_openai.por_capacidad) == (OPENAI, "text-embedding-3-small", True)
    assert (de_gemini.proveedor, de_gemini.modelo, de_gemini.por_capacidad) == (GEMINI, "gemini-embedding-001", True)


def test_los_embeddings_de_gemini_salen_como_antes_y_quedan_anotados(red, conn, ana):
    GeminiGateway(conn, ana).save_keys_config(free_key=GRATUITA_DE_ANA, paid_key=PAGA_DE_ANA, tier="free")

    embedding = PasarelaDeIA(conn, ana).embeber("x" * 3000)

    (pedido,) = red.pedidos
    assert pedido.url == f"{URL_DE_GEMINI}/gemini-embedding-001:embedContent"
    # Como antes de la capa: la clave paga si está, y si no la gratuita
    assert pedido.cabeceras == {"x-goog-api-key": PAGA_DE_ANA, "Content-Type": "application/json"}
    assert pedido.cuerpo == {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": "x" * 2048}]},
        "outputDimensionality": 768,
        "taskType": "RETRIEVAL_DOCUMENT",
    }
    # El doble devuelve (3, 4, 0, ...): el vector vuelve con norma 1
    assert len(embedding.vector) == 768 and embedding.vector[:3] == [0.6, 0.8, 0.0]
    assert (embedding.proveedor, embedding.modelo, embedding.por_capacidad) == (GEMINI, "gemini-embedding-001", False)
    (consumo,) = _consumos(ana)
    assert (consumo["provider"], consumo["model"], consumo["endpoint_tipo"], consumo["api_tier"]) == (
        GEMINI,
        "gemini-embedding-001",
        "embeddings",
        "paid",
    )
    assert (consumo["status_code"], consumo["estimated_cost_usd"]) == (200, None)


def test_un_embedding_con_otras_dimensiones_no_se_devuelve(red, conn, ana, monkeypatch):
    pasarela = _con(conn, ana, GEMINI)
    monkeypatch.setattr("ia_falsa.DIMENSIONES", 512)

    with pytest.raises(IANoDisponibleError, match="no tiene 768 dimensiones"):
        pasarela.embeber("Kubernetes")


def test_sin_clave_los_embeddings_piden_configurarla(red, conn, ana):
    with pytest.raises(FaltaClaveDeIA):
        PasarelaDeIA(conn, ana).embeber("Kubernetes")

    assert red.pedidos == []
