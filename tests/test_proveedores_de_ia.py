"""Adaptadores de Anthropic y OpenAI, lista de modelos, prueba de conexión y configuración por cuenta (035).

Los cuerpos y las cabeceras se afirman enteros: lo que un proveedor rechaza (por ejemplo `temperature` en
Anthropic) no puede colarse sin que un test lo vea. La red es `ia_falsa.RedDeIA`.
"""

import base64
import dataclasses

import pytest
from conftest import cuenta_de_prueba
from ia_falsa import ANTHROPIC, GEMINI, OPENAI, TEXTO_CRUDO, RedDeIA, instalar_red_de_ia

from aulento.core.gemini_gateway import GeminiGateway
from aulento.core.ia.anthropic import MODELOS_OFRECIDOS, ProveedorAnthropic
from aulento.core.ia.base import INSTRUCCION_JSON, esquema_estricto
from aulento.core.ia.gemini import ProveedorGemini
from aulento.core.ia.openai import ProveedorOpenAI
from aulento.core.ia.pasarela import ADAPTADORES, PasarelaDeIA
from aulento.core.ia.tipos import (
    Adjunto,
    CapacidadNoSoportada,
    ClaveRechazada,
    FaltaClaveDeIA,
    FaltaElegirModelo,
    IANoDisponibleError,
    ModeloInexistente,
    Pedido,
    RespuestaRechazada,
)
from aulento.db.connection import get_connection

ANTHROPIC_DE_ANA = "sk-ant-" + "centinela-de-ana-0000AAAA"
ANTHROPIC_DE_BETO = "sk-ant-" + "centinela-de-beto-000BBBB"
OPENAI_DE_ANA = "sk-" + "proj-centinela-de-ana-000AAAA"
OPENAI_DE_BETO = "sk-" + "proj-centinela-de-beto-00BBBB"
GEMINI_DE_ANA = "AIzaSy-gratuita-de-ana-0000AAAA"
GEMINI_PAGA_DE_ANA = "AIzaSy-paga-de-ana-00000000PPAA"
MODELO_DE_OPENAI = "modelo-de-chat-a"
PDF = b"%PDF-1.4 un temario de prueba"
PDF_EN_BASE64 = base64.b64encode(PDF).decode("ascii")
ESQUEMA = {
    "type": "object",
    "properties": {"temas": {"type": "array", "items": {"type": "string"}}},
    "required": ["temas"],
    "additionalProperties": False,
}
CABECERAS_DE_ANTHROPIC = {
    "content-type": "application/json",
    "x-api-key": ANTHROPIC_DE_ANA,
    "anthropic-version": "2023-06-01",
}
BETA_DE_REEMPLAZO = {"anthropic-beta": "server-side-fallback-2026-07-01"}
# Lo que los modelos actuales de Anthropic responden con 400 si llega en el pedido
PROHIBIDO_EN_ANTHROPIC = ("temperature", "top_p", "top_k", "thinking", "output_format")
PROHIBIDO_EN_OPENAI = ("temperature", "max_tokens", "top_p")


@pytest.fixture
def red(monkeypatch) -> RedDeIA:
    return instalar_red_de_ia(monkeypatch)


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


def _consumos(cuenta_id: int) -> list[tuple]:
    conexion = get_connection()
    try:
        return [
            tuple(fila)
            for fila in conexion.execute(
                "SELECT provider, model, endpoint_tipo, api_tier, prompt_tokens, completion_tokens, total_tokens, "
                "estimated_cost_usd, status_code FROM api_usage_logs WHERE user_id = ? ORDER BY id;",
                (cuenta_id,),
            )
        ]
    finally:
        conexion.close()


# --- R5: capacidades declaradas ---


def test_r5_cada_proveedor_declara_lo_que_sabe_hacer():
    assert {nombre: sorted(adaptador.capacidades) for nombre, adaptador in ADAPTADORES.items()} == {
        GEMINI: ["audio", "embeddings", "pdf", "texto"],
        ANTHROPIC: ["pdf", "texto"],
        OPENAI: ["embeddings", "pdf", "texto"],
    }
    assert {nombre: adaptador.nombre for nombre, adaptador in ADAPTADORES.items()} == {
        GEMINI: GEMINI,
        ANTHROPIC: ANTHROPIC,
        OPENAI: OPENAI,
    }


def test_r5_la_pasarela_informa_las_capacidades_del_proveedor_activo_de_la_cuenta(conn, ana, beto):
    de_ana, de_beto = PasarelaDeIA(conn, ana), PasarelaDeIA(conn, beto)

    assert de_ana.capacidades() == ["texto", "pdf", "audio", "embeddings"]
    de_ana.fijar_proveedor(ANTHROPIC)
    de_beto.fijar_proveedor(OPENAI)

    assert de_ana.capacidades() == ["texto", "pdf"]
    assert de_beto.capacidades() == ["texto", "pdf", "embeddings"]
    assert de_ana.estado()["capacidades"] == ["texto", "pdf"]


@pytest.mark.parametrize("adaptador", [ProveedorAnthropic(), ProveedorOpenAI()], ids=["anthropic", "openai"])
def test_r5_un_adaptador_no_arma_un_pedido_de_una_capacidad_que_no_tiene(red, adaptador):
    con_audio = Pedido(usuario="Evaluá.", adjuntos=(Adjunto("audio/wav", b"RIFF"),))

    with pytest.raises(CapacidadNoSoportada, match="no puede evaluar audio"):
        adaptador.generar(con_audio, "una-clave-cualquiera", "un-modelo")

    assert red.pedidos == []


def test_r5_anthropic_no_calcula_embeddings(red):
    with pytest.raises(CapacidadNoSoportada, match="Anthropic no puede calcular embeddings"):
        ProveedorAnthropic().embeber("Kubernetes", ANTHROPIC_DE_ANA)

    assert red.pedidos == []


# --- Anthropic: el cuerpo y las cabeceras exactas ---


def test_anthropic_pedido_de_texto_con_el_modelo_por_defecto(red):
    red.texto = "Hola."

    respuesta = ProveedorAnthropic().generar(Pedido(usuario="Saludame.", sistema="Sos un tutor."), ANTHROPIC_DE_ANA, None)

    (pedido,) = red.pedidos
    assert (pedido.metodo, pedido.url) == ("POST", "https://api.anthropic.com/v1/messages")
    assert pedido.cabeceras == {**CABECERAS_DE_ANTHROPIC, **BETA_DE_REEMPLAZO}
    assert pedido.cuerpo == {
        "model": "claude-opus-5-5",
        "max_tokens": 16000,
        "system": "Sos un tutor.",
        "messages": [{"role": "user", "content": "Saludame."}],
        "fallbacks": "default",
    }
    assert ANTHROPIC_DE_ANA not in pedido.url
    assert (respuesta.texto, respuesta.proveedor, respuesta.modelo, respuesta.nivel) == (
        "Hola.",
        ANTHROPIC,
        "claude-opus-5-5",
        None,
    )


def test_anthropic_sin_instruccion_de_sistema_no_manda_el_campo(red):
    ProveedorAnthropic().generar(Pedido(usuario="Hola", sistema="  ", max_tokens=500), ANTHROPIC_DE_ANA, "claude-haiku-5-5")

    assert red.pedidos[0].cuerpo == {
        "model": "claude-haiku-5-5",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": "Hola"}],
    }


def test_anthropic_json_sin_esquema_lo_pide_en_la_instruccion_de_sistema(red):
    ProveedorAnthropic().generar(Pedido(usuario="Dame los temas.", sistema="Sos un tutor.", json=True), ANTHROPIC_DE_ANA, None)
    ProveedorAnthropic().generar(Pedido(usuario="Dame los temas.", json=True), ANTHROPIC_DE_ANA, None)

    con_sistema, sin_sistema = (pedido.cuerpo for pedido in red.pedidos)
    assert con_sistema == {
        "model": "claude-opus-5-5",
        "max_tokens": 16000,
        "system": f"Sos un tutor.\n\n{INSTRUCCION_JSON}",
        "messages": [{"role": "user", "content": "Dame los temas."}],
        "fallbacks": "default",
    }
    assert sin_sistema["system"] == INSTRUCCION_JSON
    assert "JSON" in INSTRUCCION_JSON


def test_anthropic_json_con_esquema_usa_output_config_y_no_toca_la_instruccion(red):
    pedido = Pedido(usuario="Dame los temas.", sistema="Sos un tutor.", esquema=ESQUEMA)

    ProveedorAnthropic().generar(pedido, ANTHROPIC_DE_ANA, "claude-sonnet-5-5")

    assert red.pedidos[0].cuerpo == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 16000,
        "output_config": {"format": {"type": "json_schema", "schema": ESQUEMA}},
        "system": "Sos un tutor.",
        "messages": [{"role": "user", "content": "Dame los temas."}],
        "fallbacks": "default",
    }


def test_anthropic_el_pdf_va_como_documento_en_base64_antes_del_texto(red):
    pedido = Pedido(usuario="Resumí el temario.", adjuntos=(Adjunto("application/pdf", PDF),))

    ProveedorAnthropic().generar(pedido, ANTHROPIC_DE_ANA, "claude-haiku-5-5")

    assert red.pedidos[0].cuerpo == {
        "model": "claude-haiku-5-5",
        "max_tokens": 16000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": PDF_EN_BASE64},
                    },
                    {"type": "text", "text": "Resumí el temario."},
                ],
            }
        ],
    }
    assert "\n" not in PDF_EN_BASE64


@pytest.mark.parametrize(
    "pedido",
    [
        Pedido(usuario="Hola"),
        Pedido(usuario="Hola", sistema="Sos un tutor.", json=True, max_tokens=100),
        Pedido(usuario="Hola", esquema=ESQUEMA),
        Pedido(usuario="Hola", adjuntos=(Adjunto("application/pdf", PDF),), json=True),
    ],
    ids=["texto", "json", "esquema", "pdf"],
)
@pytest.mark.parametrize("modelo", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-de-otra-generacion"])
def test_anthropic_nunca_manda_lo_que_los_modelos_actuales_rechazan(red, pedido, modelo):
    ProveedorAnthropic().generar(pedido, ANTHROPIC_DE_ANA, modelo)

    cuerpo = red.pedidos[0].cuerpo
    assert [campo for campo in PROHIBIDO_EN_ANTHROPIC if campo in cuerpo] == []
    assert set(cuerpo) <= {"model", "max_tokens", "system", "messages", "output_config", "fallbacks"}
    # Un solo turno, del usuario: sin respuesta precargada del asistente
    assert [mensaje["role"] for mensaje in cuerpo["messages"]] == ["user"]


@pytest.mark.parametrize(
    "modelo, lleva",
    [
        ("claude-opus-5-5", True),
        ("claude-sonnet-5-5", True),
        ("claude-haiku-5-5", False),
        ("claude-de-otra-generacion", False),
    ],
)
def test_anthropic_agrega_el_reemplazo_solo_en_los_modelos_que_lo_admiten(red, modelo, lleva):
    ProveedorAnthropic().generar(Pedido(usuario="Hola"), ANTHROPIC_DE_ANA, modelo)

    (pedido,) = red.pedidos
    assert pedido.cuerpo.get("fallbacks") == ("default" if lleva else None)
    assert ("fallbacks" in pedido.cuerpo) is lleva
    assert pedido.cabeceras == ({**CABECERAS_DE_ANTHROPIC, **BETA_DE_REEMPLAZO} if lleva else CABECERAS_DE_ANTHROPIC)


def test_anthropic_une_los_bloques_de_texto_e_ignora_los_demas(red):
    red.cuerpos[ANTHROPIC] = {
        "model": "claude-opus-5-5",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "firma"},
            {"type": "text", "text": '{"temas": '},
            {"type": "tool_use", "id": "x", "name": "y", "input": {"text": "no es texto"}},
            # Un bloque de otro tipo no es parte de la respuesta aunque traiga un campo `text`
            {"type": "bloque_de_otro_tipo", "text": " ESTO NO VA "},
            {"type": "text", "text": '["uno"]}'},
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1000, "output_tokens": 500},
    }

    respuesta = ProveedorAnthropic().generar(Pedido(usuario="Hola"), ANTHROPIC_DE_ANA, None)

    assert respuesta.texto == '{"temas": ["uno"]}'
    assert (respuesta.tokens_entrada, respuesta.tokens_salida) == (1000, 500)
    # 1000 tokens a 4 USD el millón y 500 a 20
    assert respuesta.costo_usd == pytest.approx(0.014)
    assert respuesta.truncada is False


def test_anthropic_una_negativa_es_un_error_propio_aunque_llegue_con_http_200(red):
    red.cuerpos[ANTHROPIC] = {
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": TEXTO_CRUDO}],
        "stop_reason": "refusal",
        "usage": {"input_tokens": 30, "output_tokens": 2},
    }

    with pytest.raises(RespuestaRechazada) as error:
        ProveedorAnthropic().generar(Pedido(usuario="Hola"), ANTHROPIC_DE_ANA, None)

    assert str(error.value) == "El modelo de Anthropic se negó a responder este pedido."
    assert (error.value.estado, error.value.tokens_entrada, error.value.tokens_salida) == (200, 30, 2)


def test_anthropic_informa_la_respuesta_truncada_por_el_tope_de_tokens(red):
    red.cuerpos[ANTHROPIC] = {
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": '{"temas": ["uno", '}],
        "stop_reason": "max_tokens",
        "usage": {"input_tokens": 30, "output_tokens": 16000},
    }

    respuesta = ProveedorAnthropic().generar(Pedido(usuario="Hola"), ANTHROPIC_DE_ANA, None)

    assert (respuesta.texto, respuesta.truncada) == ('{"temas": ["uno", ', True)


def test_anthropic_informa_y_cobra_el_modelo_que_respondio(red):
    red.cuerpos[ANTHROPIC] = {
        "model": "claude-sonnet-5-5",
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
    }

    respuesta = ProveedorAnthropic().generar(Pedido(usuario="Hola"), ANTHROPIC_DE_ANA, "claude-opus-5-5")

    assert (respuesta.modelo, respuesta.costo_usd) == ("claude-sonnet-5-5", 2.0)


def test_anthropic_un_modelo_sin_tarifa_deja_el_costo_vacio(red):
    respuesta = ProveedorAnthropic().generar(Pedido(usuario="Hola"), ANTHROPIC_DE_ANA, "claude-de-otra-generacion")

    assert (respuesta.tokens_entrada, respuesta.tokens_salida, respuesta.costo_usd) == (11, 9, None)


def test_anthropic_espera_mas_que_los_demas_porque_sus_modelos_razonan_siempre():
    assert ProveedorAnthropic().segundos_por_defecto == 180.0
    assert ProveedorGemini().segundos_por_defecto == ProveedorOpenAI().segundos_por_defecto == 45.0


def test_el_esquema_estricto_completa_lo_que_falta_sin_tocar_el_original():
    suelto = {
        "type": "object",
        "properties": {
            "temas": {"type": "array", "items": {"type": "object", "properties": {"titulo": {"type": "string"}}}},
            "nivel": {"type": "string"},
        },
        "required": ["temas"],
    }

    estricto = esquema_estricto(suelto)

    assert estricto == {
        "type": "object",
        "properties": {
            "temas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"titulo": {"type": "string"}},
                    "additionalProperties": False,
                    "required": ["titulo"],
                },
            },
            "nivel": {"type": "string"},
        },
        # Lo que el esquema ya declaraba se respeta
        "required": ["temas"],
        "additionalProperties": False,
    }
    assert "additionalProperties" not in suelto and "required" not in suelto["properties"]["temas"]["items"]
    assert esquema_estricto(ESQUEMA) == ESQUEMA


# --- OpenAI: el cuerpo y las cabeceras exactas ---


def test_openai_pedido_de_texto(red):
    red.texto = "Hola."

    respuesta = ProveedorOpenAI().generar(Pedido(usuario="Saludame.", sistema="Sos un tutor."), OPENAI_DE_ANA, MODELO_DE_OPENAI)

    (pedido,) = red.pedidos
    assert (pedido.metodo, pedido.url) == ("POST", "https://api.openai.com/v1/chat/completions")
    assert pedido.cabeceras == {"Authorization": f"Bearer {OPENAI_DE_ANA}"}
    assert pedido.cuerpo == {
        "model": MODELO_DE_OPENAI,
        "messages": [{"role": "system", "content": "Sos un tutor."}, {"role": "user", "content": "Saludame."}],
    }
    assert OPENAI_DE_ANA not in pedido.url
    assert (respuesta.texto, respuesta.proveedor, respuesta.modelo) == ("Hola.", OPENAI, MODELO_DE_OPENAI)
    assert (respuesta.tokens_entrada, respuesta.tokens_salida) == (13, 4)
    # Sin tarifas verificadas de OpenAI, el costo queda vacío
    assert (respuesta.costo_usd, respuesta.truncada, respuesta.nivel) == (None, False, None)


def test_openai_json_sin_esquema_pide_un_objeto_y_lo_nombra_en_la_instruccion(red):
    ProveedorOpenAI().generar(Pedido(usuario="Dame los temas.", json=True, max_tokens=800), OPENAI_DE_ANA, MODELO_DE_OPENAI)

    assert red.pedidos[0].cuerpo == {
        "model": MODELO_DE_OPENAI,
        "messages": [{"role": "system", "content": INSTRUCCION_JSON}, {"role": "user", "content": "Dame los temas."}],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 800,
    }


def test_openai_json_con_esquema_usa_json_schema_estricto(red):
    pedido = Pedido(usuario="Dame los temas.", sistema="Sos un tutor.", esquema=ESQUEMA)

    ProveedorOpenAI().generar(pedido, OPENAI_DE_ANA, MODELO_DE_OPENAI)

    assert red.pedidos[0].cuerpo == {
        "model": MODELO_DE_OPENAI,
        "messages": [{"role": "system", "content": "Sos un tutor."}, {"role": "user", "content": "Dame los temas."}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "respuesta", "schema": ESQUEMA, "strict": True}},
    }


def test_openai_el_pdf_va_como_archivo_en_base64_antes_del_texto(red):
    pedido = Pedido(usuario="Resumí el temario.", adjuntos=(Adjunto("application/pdf", PDF),))

    ProveedorOpenAI().generar(pedido, OPENAI_DE_ANA, MODELO_DE_OPENAI)

    assert red.pedidos[0].cuerpo == {
        "model": MODELO_DE_OPENAI,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {"filename": "documento.pdf", "file_data": f"data:application/pdf;base64,{PDF_EN_BASE64}"},
                    },
                    {"type": "text", "text": "Resumí el temario."},
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "pedido",
    [
        Pedido(usuario="Hola"),
        Pedido(usuario="Hola", sistema="Sos un tutor.", json=True, max_tokens=100),
        Pedido(usuario="Hola", esquema=ESQUEMA),
        Pedido(usuario="Hola", adjuntos=(Adjunto("application/pdf", PDF),)),
    ],
    ids=["texto", "json", "esquema", "pdf"],
)
def test_openai_no_fija_temperatura_ni_el_tope_viejo(red, pedido):
    ProveedorOpenAI().generar(pedido, OPENAI_DE_ANA, MODELO_DE_OPENAI)

    cuerpo = red.pedidos[0].cuerpo
    assert [campo for campo in PROHIBIDO_EN_OPENAI if campo in cuerpo] == []
    assert set(cuerpo) <= {"model", "messages", "response_format", "max_completion_tokens"}


# --- La temperatura del pedido es una preferencia: solo Gemini la recibe ---

CON_TEMPERATURA = [
    Pedido(usuario="Hola", temperatura=0.2),
    Pedido(usuario="Hola", sistema="Sos un tutor.", json=True, temperatura=0.1),
    Pedido(usuario="Hola", esquema=ESQUEMA, temperatura=0.3),
    Pedido(usuario="Hola", adjuntos=(Adjunto("application/pdf", PDF),), temperatura=0.25),
    Pedido(usuario="Hola", temperatura=0.0),
]


def _sin_temperatura(pedido: Pedido) -> Pedido:
    return dataclasses.replace(pedido, temperatura=None)


@pytest.mark.parametrize("pedido", CON_TEMPERATURA, ids=lambda pedido: f"t={pedido.temperatura}")
def test_gemini_envia_la_temperatura_del_pedido_tal_cual(red, pedido):
    ProveedorGemini().generar(pedido, GEMINI_DE_ANA, None)
    ProveedorGemini().generar(_sin_temperatura(pedido), GEMINI_DE_ANA, None)

    con, sin = (enviado.cuerpo for enviado in red.pedidos)
    assert con["generationConfig"]["temperature"] == pedido.temperatura
    # Sin temperatura en el pedido no se fija ninguna, y el resto del cuerpo es idéntico
    assert "temperature" not in sin.get("generationConfig", {})
    con["generationConfig"].pop("temperature")
    assert {clave: valor for clave, valor in con.items() if valor != {}} == sin


@pytest.mark.parametrize("pedido", CON_TEMPERATURA, ids=lambda pedido: f"t={pedido.temperatura}")
@pytest.mark.parametrize("modelo", MODELOS_OFRECIDOS)
def test_anthropic_nunca_envia_la_temperatura_aunque_el_pedido_la_traiga(red, pedido, modelo):
    """Los modelos actuales de Anthropic responden 400 a `temperature`: el cuerpo es el mismo con o sin ella."""
    ProveedorAnthropic().generar(pedido, ANTHROPIC_DE_ANA, modelo)
    ProveedorAnthropic().generar(_sin_temperatura(pedido), ANTHROPIC_DE_ANA, modelo)

    con, sin = (enviado.cuerpo for enviado in red.pedidos)
    assert con == sin
    assert [campo for campo in PROHIBIDO_EN_ANTHROPIC if campo in con] == []


@pytest.mark.parametrize("pedido", CON_TEMPERATURA, ids=lambda pedido: f"t={pedido.temperatura}")
def test_openai_nunca_envia_la_temperatura_aunque_el_pedido_la_traiga(red, pedido):
    """Varios modelos de OpenAI rechazan `temperature`: el cuerpo es el mismo con o sin ella."""
    ProveedorOpenAI().generar(pedido, OPENAI_DE_ANA, MODELO_DE_OPENAI)
    ProveedorOpenAI().generar(_sin_temperatura(pedido), OPENAI_DE_ANA, MODELO_DE_OPENAI)

    con, sin = (enviado.cuerpo for enviado in red.pedidos)
    assert con == sin
    assert [campo for campo in PROHIBIDO_EN_OPENAI if campo in con] == []


def test_la_temperatura_llega_a_gemini_tambien_por_la_pasarela_con_su_rotacion(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(GEMINI, GEMINI_DE_ANA)
    red.estado_por_modelo = {"gemini-flash-lite-latest": 500}

    pasarela.generar(Pedido(usuario="Hola", json=True, temperatura=0.2), "unit_test")

    assert len(red.pedidos) == 2
    for enviado in red.pedidos:
        assert enviado.cuerpo["generationConfig"] == {"responseMimeType": "application/json", "temperature": 0.2}


@pytest.mark.parametrize("modelo", [None, "", "   "])
def test_openai_exige_que_la_cuenta_haya_elegido_un_modelo(red, modelo):
    with pytest.raises(FaltaElegirModelo) as error:
        ProveedorOpenAI().generar(Pedido(usuario="Hola"), OPENAI_DE_ANA, modelo)

    assert str(error.value) == (
        "Todavía no elegiste un modelo de OpenAI. Elegilo de la lista o escribilo en Configuración para usar la IA."
    )
    assert red.pedidos == []


def test_openai_sin_modelo_elegido_la_pasarela_lo_pide_y_con_modelo_sale(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(OPENAI, OPENAI_DE_ANA)
    pasarela.fijar_proveedor(OPENAI)

    assert pasarela.modelo_de(OPENAI) is None
    with pytest.raises(FaltaElegirModelo):
        pasarela.generar(Pedido(usuario="Hola"), "saludo")
    assert red.pedidos == [] and _consumos(ana) == []

    pasarela.fijar_modelo(OPENAI, f"  {MODELO_DE_OPENAI} ")
    pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert red.modelos() == [MODELO_DE_OPENAI]
    assert _consumos(ana) == [(OPENAI, MODELO_DE_OPENAI, "saludo", "paid", 13, 4, 17, None, 200)]


@pytest.mark.parametrize(
    "opcion",
    [
        {"message": {"role": "assistant", "content": None, "refusal": "No puedo ayudar con eso."}, "finish_reason": "stop"},
        {"message": {"role": "assistant", "content": TEXTO_CRUDO}, "finish_reason": "content_filter"},
    ],
    ids=["refusal", "content_filter"],
)
def test_openai_una_negativa_es_un_error_propio(red, opcion):
    red.cuerpos[OPENAI] = {"choices": [opcion], "usage": {"prompt_tokens": 20, "completion_tokens": 1}}

    with pytest.raises(RespuestaRechazada) as error:
        ProveedorOpenAI().generar(Pedido(usuario="Hola"), OPENAI_DE_ANA, MODELO_DE_OPENAI)

    assert str(error.value) == "El modelo de OpenAI se negó a responder este pedido."
    assert (error.value.estado, error.value.tokens_entrada, error.value.tokens_salida) == (200, 20, 1)


def test_openai_informa_la_respuesta_truncada(red):
    red.cuerpos[OPENAI] = {
        "choices": [{"message": {"role": "assistant", "content": '{"temas": ['}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 800},
    }

    respuesta = ProveedorOpenAI().generar(Pedido(usuario="Hola"), OPENAI_DE_ANA, MODELO_DE_OPENAI)

    assert (respuesta.texto, respuesta.truncada, respuesta.tokens_salida) == ('{"temas": [', True, 800)


def test_openai_calcula_embeddings_de_768_dimensiones(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(OPENAI, OPENAI_DE_ANA)
    pasarela.fijar_proveedor(OPENAI)

    embedding = pasarela.embeber("Kubernetes")

    (pedido,) = red.pedidos
    assert (pedido.metodo, pedido.url) == ("POST", "https://api.openai.com/v1/embeddings")
    assert pedido.cabeceras == {"Authorization": f"Bearer {OPENAI_DE_ANA}"}
    assert pedido.cuerpo == {"model": "text-embedding-3-small", "input": "Kubernetes", "dimensions": 768}
    # El doble devuelve (0, 6, 8, 0, ...): vuelve con norma 1
    assert len(embedding.vector) == 768 and embedding.vector[:4] == [0.0, 0.6, 0.8, 0.0]
    assert (embedding.proveedor, embedding.modelo, embedding.por_capacidad) == (OPENAI, "text-embedding-3-small", False)
    assert _consumos(ana) == [(OPENAI, "text-embedding-3-small", "embeddings", "paid", 0, 0, 0, None, 200)]


# --- La pasarela con Anthropic: consumo ---


def test_el_consumo_de_anthropic_queda_a_nombre_de_la_cuenta_con_su_costo(red, conn, ana, beto):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)
    pasarela.fijar_proveedor(ANTHROPIC)

    respuesta = pasarela.generar(Pedido(usuario="Hola"), "clase")

    assert red.claves() == [ANTHROPIC_DE_ANA] and red.modelos() == ["claude-opus-5-5"]
    # 11 tokens a 4 USD el millón y 9 a 20
    assert _consumos(ana) == [(ANTHROPIC, "claude-opus-5-5", "clase", "paid", 11, 9, 20, pytest.approx(0.000224), 200)]
    assert respuesta.costo_usd == pytest.approx(0.000224)
    assert _consumos(beto) == []


def test_una_negativa_queda_anotada_con_los_tokens_que_consumio(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)
    pasarela.fijar_proveedor(ANTHROPIC)
    red.cuerpos[ANTHROPIC] = {
        "model": "claude-opus-5-5",
        "content": [],
        "stop_reason": "refusal",
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
    }

    with pytest.raises(RespuestaRechazada):
        pasarela.generar(Pedido(usuario="Hola"), "clase")

    assert _consumos(ana) == [(ANTHROPIC, "claude-opus-5-5", "clase", "paid", 1_000_000, 0, 1_000_000, 4.0, 200)]


# --- R10: lista de modelos y prueba de conexión ---


def test_r10_la_lista_de_modelos_se_pide_al_proveedor_con_la_clave_de_la_cuenta(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(GEMINI, GEMINI_DE_ANA)
    pasarela.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)
    pasarela.guardar_clave(OPENAI, OPENAI_DE_ANA)

    de_gemini, de_anthropic, de_openai = pasarela.modelos(GEMINI), pasarela.modelos(ANTHROPIC), pasarela.modelos(OPENAI)

    assert [(pedido.metodo, pedido.url, pedido.cabeceras, pedido.cuerpo) for pedido in red.pedidos] == [
        ("GET", "https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": GEMINI_DE_ANA}, None),
        ("GET", "https://api.anthropic.com/v1/models", CABECERAS_DE_ANTHROPIC, None),
        ("GET", "https://api.openai.com/v1/models", {"Authorization": f"Bearer {OPENAI_DE_ANA}"}, None),
    ]
    # De Gemini, solo los que generan contenido; de OpenAI, los que no son de embeddings, audio, imágenes o moderación
    assert de_gemini == ["gemini-3.8-flash", "gemini-flash-lite-latest"]
    assert de_anthropic == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    assert de_openai == ["modelo-de-chat-a", "modelo-de-chat-b"]


@pytest.mark.parametrize("proveedor", [GEMINI, ANTHROPIC, OPENAI])
def test_r10_la_lista_de_modelos_sin_clave_o_con_la_clave_rechazada_da_su_error(red, conn, ana, proveedor):
    pasarela = PasarelaDeIA(conn, ana)

    with pytest.raises(FaltaClaveDeIA):
        pasarela.modelos(proveedor)
    assert red.pedidos == []

    clave = {GEMINI: GEMINI_DE_ANA, ANTHROPIC: ANTHROPIC_DE_ANA, OPENAI: OPENAI_DE_ANA}[proveedor]
    pasarela.guardar_clave(proveedor, clave)
    red.estado_por_clave = {clave: 401}

    with pytest.raises(ClaveRechazada) as error:
        pasarela.modelos(proveedor)
    assert clave not in str(error.value) and TEXTO_CRUDO not in str(error.value)


def test_r10_un_modelo_escrito_a_mano_se_usa_tal_cual_aunque_no_este_en_la_lista(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)
    pasarela.fijar_proveedor(ANTHROPIC)
    pasarela.fijar_modelo(ANTHROPIC, "claude-escrito-a-mano")

    pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert red.modelos() == ["claude-escrito-a-mano"]
    with pytest.raises(ValueError, match="no puede estar vacío"):
        pasarela.fijar_modelo(ANTHROPIC, "  ")
    assert pasarela.modelo_de(ANTHROPIC) == "claude-escrito-a-mano"


@pytest.mark.parametrize(
    "proveedor, clave, modelo",
    [
        (GEMINI, GEMINI_DE_ANA, "gemini-flash-lite-latest"),
        (ANTHROPIC, ANTHROPIC_DE_ANA, "claude-opus-5-5"),
        (OPENAI, OPENAI_DE_ANA, MODELO_DE_OPENAI),
    ],
)
def test_r10_la_prueba_de_conexion_con_clave_buena_y_con_clave_mala(red, conn, ana, proveedor, clave, modelo):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(proveedor, clave)
    pasarela.fijar_modelo(proveedor, modelo)

    buena = pasarela.probar(proveedor)

    (pedido,) = red.pedidos
    assert (pedido.proveedor, pedido.clave, pedido.modelo, pedido.metodo) == (proveedor, clave, modelo, "POST")
    assert (buena["ok"], buena["proveedor"], buena["modelo"]) == (True, proveedor, modelo)
    assert buena["latencia_ms"] is not None and modelo in buena["mensaje"]

    red.estado_por_clave = {clave: 401}
    mala = pasarela.probar(proveedor)

    assert (mala["ok"], mala["proveedor"], mala["modelo"], mala["latencia_ms"]) == (False, proveedor, modelo, None)
    assert "rechazó la clave" in mala["mensaje"]
    assert clave not in str(mala) + str(buena) and TEXTO_CRUDO not in mala["mensaje"]
    # Las dos pruebas llegaron al proveedor: quedan en el consumo de la cuenta
    assert [(c[0], c[2], c[8]) for c in _consumos(ana)] == [
        (proveedor, "prueba_de_conexion", 200),
        (proveedor, "prueba_de_conexion", 401),
    ]


def test_r10_la_prueba_de_un_proveedor_no_necesita_que_sea_el_activo_ni_lo_cambia(red, conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)

    assert pasarela.probar(ANTHROPIC)["ok"] is True
    assert pasarela.probar(OPENAI) == {
        "ok": False,
        "proveedor": OPENAI,
        "modelo": None,
        "mensaje": "No hay una clave de OpenAI configurada para tu cuenta. Cargala en Configuración para usar la IA.",
        "latencia_ms": None,
    }

    assert [pedido.proveedor for pedido in red.pedidos] == [ANTHROPIC]
    assert pasarela.proveedor_activo() == GEMINI


def test_r10_la_prueba_de_gemini_sale_con_la_clave_del_nivel_activo(red, conn, ana):
    GeminiGateway(conn, ana).save_keys_config(free_key=GEMINI_DE_ANA, paid_key=GEMINI_PAGA_DE_ANA, tier="paid")

    assert PasarelaDeIA(conn, ana).probar(GEMINI)["ok"] is True

    assert red.claves() == [GEMINI_PAGA_DE_ANA]
    assert [(c[0], c[3]) for c in _consumos(ana)] == [(GEMINI, "paid")]


@pytest.mark.parametrize("estado, excepcion", [(404, ModeloInexistente), (500, IANoDisponibleError)])
def test_r10_la_prueba_informa_la_falla_sin_levantarla(red, conn, ana, estado, excepcion):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)
    red.estado_por_clave = {ANTHROPIC_DE_ANA: estado}

    resultado = pasarela.probar(ANTHROPIC)

    with pytest.raises(excepcion) as error:
        ProveedorAnthropic().probar(ANTHROPIC_DE_ANA, "claude-opus-5-5")
    assert (resultado["ok"], resultado["mensaje"]) == (False, str(error.value))


# --- R2 y R3: cada cuenta guarda y elige proveedor, clave y modelo sin ver los de otra ---


def test_r2_cada_cuenta_guarda_y_elige_proveedor_clave_y_modelo_sin_ver_los_de_otra(red, conn, ana, beto):
    de_ana, de_beto = PasarelaDeIA(conn, ana), PasarelaDeIA(conn, beto)
    de_ana.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)
    de_ana.fijar_modelo(ANTHROPIC, "claude-haiku-5-5")
    de_ana.fijar_proveedor(ANTHROPIC)
    de_beto.guardar_clave(OPENAI, OPENAI_DE_BETO)
    de_beto.fijar_modelo(OPENAI, MODELO_DE_OPENAI)
    de_beto.fijar_proveedor(OPENAI)

    de_ana.generar(Pedido(usuario="Hola"), "saludo")
    de_beto.generar(Pedido(usuario="Hola"), "saludo")

    assert [(p.proveedor, p.clave, p.modelo) for p in red.pedidos] == [
        (ANTHROPIC, ANTHROPIC_DE_ANA, "claude-haiku-5-5"),
        (OPENAI, OPENAI_DE_BETO, MODELO_DE_OPENAI),
    ]
    assert (de_ana.proveedor_activo(), de_beto.proveedor_activo()) == (ANTHROPIC, OPENAI)
    estado_de_ana, estado_de_beto = de_ana.estado(), de_beto.estado()
    assert estado_de_ana["proveedores"][OPENAI] == {
        "nombre": "OpenAI",
        "activo": False,
        "tiene_clave": False,
        "clave": None,
        "error_de_clave": None,
        "modelo": None,
        "capacidades": ["texto", "pdf", "embeddings"],
        "modelos_sugeridos": [],
    }
    assert estado_de_beto["proveedores"][ANTHROPIC] == {
        "nombre": "Anthropic",
        "activo": False,
        "tiene_clave": False,
        "clave": None,
        "error_de_clave": None,
        "modelo": "claude-opus-5-5",
        "capacidades": ["texto", "pdf"],
        "modelos_sugeridos": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
    }
    # Una cuenta con la clave de Anthropic de otra persona no la usa: beto sigue sin poder pedirle a Anthropic
    de_beto.fijar_proveedor(ANTHROPIC)
    with pytest.raises(FaltaClaveDeIA):
        de_beto.generar(Pedido(usuario="Hola"), "saludo")
    assert de_ana.proveedor_activo() == ANTHROPIC and de_ana.modelo_de(ANTHROPIC) == "claude-haiku-5-5"


def test_r2_el_estado_muestra_a_lo_sumo_los_ultimos_cuatro_caracteres_de_cada_clave(conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(ANTHROPIC, f"  {ANTHROPIC_DE_ANA}\n")
    pasarela.guardar_clave(OPENAI, OPENAI_DE_ANA)
    pasarela.guardar_clave(GEMINI, GEMINI_DE_ANA)
    pasarela.guardar_clave(GEMINI, GEMINI_PAGA_DE_ANA, nivel="paid")
    pasarela.fijar_proveedor(ANTHROPIC)

    estado = pasarela.estado()

    assert estado["proveedor_activo"] == ANTHROPIC
    assert {nombre: (p["activo"], p["tiene_clave"], p["clave"]) for nombre, p in estado["proveedores"].items()} == {
        GEMINI: (False, True, "...AAAA"),
        ANTHROPIC: (True, True, "...AAAA"),
        OPENAI: (False, True, "...AAAA"),
    }
    assert estado["proveedores"][GEMINI]["clave_paga"] == "...PPAA"
    assert estado["proveedores"][GEMINI]["nivel_activo"] == "auto"
    for clave in (ANTHROPIC_DE_ANA, OPENAI_DE_ANA, GEMINI_DE_ANA, GEMINI_PAGA_DE_ANA):
        assert clave not in str(estado)
    assert repr(pasarela) == f"PasarelaDeIA(user_id={ana})"


def test_r2_las_claves_se_guardan_cifradas_y_son_las_de_gemini_de_siempre(conn, ana):
    pasarela = PasarelaDeIA(conn, ana)
    pasarela.guardar_clave(ANTHROPIC, ANTHROPIC_DE_ANA)
    pasarela.guardar_clave(OPENAI, OPENAI_DE_ANA)
    pasarela.guardar_clave(GEMINI, GEMINI_DE_ANA)
    pasarela.fijar_modelo(GEMINI, "gemini-3.8-flash")

    filas = conn.execute("SELECT nombre, valor_cifrado FROM secretos_usuario WHERE user_id = ? ORDER BY nombre;", (ana,)).fetchall()

    assert [fila[0] for fila in filas] == ["anthropic_clave", "gemini_clave_gratuita", "openai_clave"]
    guardado = b"".join(bytes(fila[1]) if not isinstance(fila[1], str) else fila[1].encode() for fila in filas)
    for clave in (ANTHROPIC_DE_ANA, OPENAI_DE_ANA, GEMINI_DE_ANA):
        assert clave.encode() not in guardado
    # Gemini no tiene un segundo almacén: lo que guarda la pasarela es lo que lee `GeminiGateway`, y al revés
    de_gemini = GeminiGateway(conn, ana)
    assert de_gemini.resolve_free_key() == GEMINI_DE_ANA and de_gemini.resolve_model() == "gemini-3.8-flash"
    de_gemini.save_model("gemini-pro-latest")
    assert pasarela.modelo_de(GEMINI) == "gemini-pro-latest"


def test_r2_quitar_una_clave_la_borra_solo_de_esa_cuenta_y_de_ese_proveedor(red, conn, ana, beto):
    de_ana, de_beto = PasarelaDeIA(conn, ana), PasarelaDeIA(conn, beto)
    for pasarela, de_anthropic, de_openai in ((de_ana, ANTHROPIC_DE_ANA, OPENAI_DE_ANA), (de_beto, ANTHROPIC_DE_BETO, OPENAI_DE_BETO)):
        pasarela.guardar_clave(ANTHROPIC, de_anthropic)
        pasarela.guardar_clave(OPENAI, de_openai)
    de_ana.guardar_clave(GEMINI, GEMINI_DE_ANA)
    de_ana.guardar_clave(GEMINI, GEMINI_PAGA_DE_ANA, nivel="paid")

    assert de_ana.quitar_clave(ANTHROPIC) is True
    assert de_ana.quitar_clave(ANTHROPIC) is False

    def con_clave(pasarela):
        return {nombre: p["tiene_clave"] for nombre, p in pasarela.estado()["proveedores"].items()}

    assert con_clave(de_ana) == {GEMINI: True, ANTHROPIC: False, OPENAI: True}
    assert con_clave(de_beto) == {GEMINI: False, ANTHROPIC: True, OPENAI: True}

    assert de_ana.quitar_clave(GEMINI, nivel="free") is True
    assert (GeminiGateway(conn, ana).resolve_free_key(), GeminiGateway(conn, ana).resolve_paid_key()) == (None, GEMINI_PAGA_DE_ANA)
    assert de_ana.quitar_clave(GEMINI) is True
    assert con_clave(de_ana) == {GEMINI: False, ANTHROPIC: False, OPENAI: True}


def test_r2_un_proveedor_una_clave_o_un_nivel_invalidos_no_se_guardan(conn, ana):
    pasarela = PasarelaDeIA(conn, ana)

    for llamada in (
        lambda: pasarela.fijar_proveedor("mistral"),
        lambda: pasarela.guardar_clave("mistral", "una-clave"),
        lambda: pasarela.quitar_clave("mistral"),
        lambda: pasarela.fijar_modelo("mistral", "un-modelo"),
        lambda: pasarela.modelos("mistral"),
        lambda: pasarela.probar("mistral"),
        lambda: pasarela.guardar_clave(ANTHROPIC, "   "),
        lambda: pasarela.guardar_clave(GEMINI, GEMINI_DE_ANA, nivel="auto"),
        lambda: pasarela.quitar_clave(GEMINI, nivel="auto"),
    ):
        with pytest.raises(ValueError):
            llamada()

    assert pasarela.proveedor_activo() == GEMINI
    assert conn.execute("SELECT COUNT(*) FROM secretos_usuario WHERE user_id = ?;", (ana,)).fetchone()[0] == 0


def test_r11_una_cuenta_que_solo_tiene_clave_de_gemini_funciona_sin_configurar_nada_mas(red, conn, ana):
    GeminiGateway(conn, ana).save_keys_config(free_key=GEMINI_DE_ANA)
    pasarela = PasarelaDeIA(conn, ana)

    respuesta = pasarela.generar(Pedido(usuario="Hola"), "saludo")

    assert (respuesta.proveedor, red.claves()) == (GEMINI, [GEMINI_DE_ANA])
    assert pasarela.estado()["proveedor_activo"] == GEMINI
    assert pasarela.estado()["proveedores"][GEMINI]["activo"] is True
