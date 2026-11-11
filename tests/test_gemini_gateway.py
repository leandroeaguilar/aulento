"""Pruebas unitarias para GeminiGateway (Doble Clave, Failover y Costos)."""

import logging

import httpx
import pytest
from conftest import cuenta_de_prueba
from ia_falsa import TEXTO_CRUDO, RedDeIA, instalar_red_de_ia
from aulento import core
from aulento.core import gemini_gateway
from aulento.core.gemini_gateway import GeminiGateway
from aulento.core.ia import tipos
from aulento.core.ia.gemini import Intento, ProveedorGemini
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import Pedido
from aulento.db.connection import get_connection
from aulento.db.roadmap_repository import RoadmapRepository


def test_calculate_cost():
    # gemini-flash-lite: $0.10 input / $0.40 output por 1M
    cost = GeminiGateway.calculate_cost("gemini-flash-lite-latest", 1_000_000, 1_000_000)
    assert round(cost, 2) == 0.50

    # gemini-pro-latest: $1.25 input / $10.00 output por 1M
    cost_pro = GeminiGateway.calculate_cost("gemini-pro-latest", 1_000_000, 1_000_000)
    assert round(cost_pro, 2) == 11.25


@pytest.fixture
def pasarela(memory_db) -> GeminiGateway:
    return GeminiGateway(memory_db, cuenta_de_prueba(memory_db).id)


def test_keys_save_and_status(pasarela):
    # Guardar claves y tier
    pasarela.save_keys_config(
        free_key="AIzaSyFreeKeyTest12345678",
        paid_key="AIzaSyPaidKeyTest87654321",
        tier="auto",
    )

    status = pasarela.get_status()
    assert status.has_free_key is True
    assert status.has_paid_key is True
    assert status.active_tier == "auto"
    # R3 (034): de cada clave se muestran, a lo sumo, los últimos cuatro caracteres
    assert status.free_key_masked == "...5678"
    assert status.paid_key_masked == "...4321"


# --- 035: la llamada la hace el adaptador de Gemini de la capa de proveedores, por la pasarela de la cuenta ---

GRATUITA = "AIzaSy-gratuita-de-prueba-00FFFF"
PAGA = "AIzaSy-paga-de-prueba-000000PPPP"
URL_DE_MODELOS = "https://generativelanguage.googleapis.com/v1beta/models"
PEDIDO_DE_GOOGLE = {
    "contents": [{"parts": [{"text": "Hola"}]}],
    "system_instruction": {"parts": [{"text": "Sos un tutor."}]},
    "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"},
}
PEDIDO = Pedido(usuario="Hola", sistema="Sos un tutor.", json=True, temperatura=0.2)


@pytest.fixture
def red(monkeypatch) -> RedDeIA:
    return instalar_red_de_ia(monkeypatch)


@pytest.fixture
def cuenta_y_repo(isolated_cloud_env):
    """Las claves de Gemini de una cuenta, con conexión propia sobre la base aislada, y su repositorio de rutas."""
    conn = get_connection()
    try:
        cuenta_id = cuenta_de_prueba(conn).id
    finally:
        conn.close()
    return GeminiGateway.con_conexion_propia(cuenta_id), RoadmapRepository(cuenta_id)


def _consumos(cuenta_id: int) -> list[tuple]:
    conn = get_connection()
    try:
        return [
            tuple(fila)
            for fila in conn.execute(
                "SELECT provider, model, api_tier, status_code, total_tokens, estimated_cost_usd FROM api_usage_logs "
                "WHERE user_id = ? ORDER BY id;",
                (cuenta_id,),
            )
        ]
    finally:
        conn.close()


def test_el_gateway_ya_no_llama_al_modelo_solo_guarda_las_claves_el_nivel_y_el_modelo():
    """La entrada con el pedido en el formato de Google se retiró: todo pedido pasa por la pasarela de IA."""
    assert not hasattr(GeminiGateway, "generate_content")
    assert not hasattr(gemini_gateway, "GeminiGatewayResult")
    assert core.__all__ == ["GeminiGateway"]


def test_gateway_failover_429_to_paid(red, cuenta_y_repo):
    """Con las dos claves en `auto`, la gratuita con cuota agotada cede a la paga y la respuesta dice de cuál salió."""
    gemini, repo = cuenta_y_repo
    gemini.save_keys_config(free_key=GRATUITA, paid_key=PAGA, tier="auto")
    red.estado_por_clave = {GRATUITA: 429}
    red.texto = "Respuesta desde Paid Tier"

    res = PasarelaDeIA.de_repositorio(repo).generar(PEDIDO, "unit_test", repo)

    assert red.claves() == [GRATUITA, PAGA]
    assert (res.nivel, res.texto, res.proveedor) == ("paid", "Respuesta desde Paid Tier", "gemini")
    assert (res.tokens_entrada, res.tokens_salida) == (7, 5)
    assert res.costo_usd > 0


def test_el_adaptador_manda_el_pedido_de_google_tal_cual_con_la_clave_en_la_cabecera(red):
    red.texto = '{"ok": true}'

    respuesta, datos = ProveedorGemini().generar_con_conmutacion(PEDIDO_DE_GOOGLE, [("free", GRATUITA)], ["gemini-3.5-flash"])

    (pedido,) = red.pedidos
    assert (pedido.metodo, pedido.url) == ("POST", f"{URL_DE_MODELOS}/gemini-3.5-flash:generateContent")
    assert pedido.cabeceras == {"x-goog-api-key": GRATUITA}
    assert pedido.cuerpo == PEDIDO_DE_GOOGLE
    assert (respuesta.texto, respuesta.modelo, respuesta.nivel) == ('{"ok": true}', "gemini-3.5-flash", "free")
    assert (respuesta.tokens_entrada, respuesta.tokens_salida) == (7, 5)
    assert datos["candidates"][0]["content"]["parts"][0]["text"] == '{"ok": true}'
    # 7 tokens a 1,50 USD el millón y 5 a 9,00
    assert respuesta.costo_usd == pytest.approx(0.0000555, abs=1e-6)


def test_la_pasarela_rota_los_modelos_y_conmuta_de_clave_como_antes(red, cuenta_y_repo):
    gemini, repo = cuenta_y_repo
    gemini.save_keys_config(free_key=GRATUITA, paid_key=PAGA, tier="auto")
    gemini.save_model("gemini-3.1-pro")
    red.estado_por_modelo = {"gemini-3.1-pro": 500}
    red.estado_por_clave = {GRATUITA: 429}

    respuesta = PasarelaDeIA.de_repositorio(repo).generar(PEDIDO, "unit_test", repo)

    # La gratuita da 429 y cede a la paga sin probar más modelos; la paga rota hasta el primero que responde
    assert [(p.clave, p.modelo) for p in red.pedidos] == [
        (GRATUITA, "gemini-3.1-pro"),
        (PAGA, "gemini-3.1-pro"),
        (PAGA, "gemini-flash-lite-latest"),
    ]
    assert (respuesta.nivel, respuesta.modelo) == ("paid", "gemini-flash-lite-latest")
    # El cuerpo que sale es el del pedido neutral en el formato de Google, igual para cada intento
    assert {str(p.cuerpo) for p in red.pedidos} == {str(ProveedorGemini.cuerpo(PEDIDO))}
    # En el repositorio queda cada intento que llegó a Google: el 429, el 500 intermedio y la respuesta
    assert _consumos(repo.user_id) == [
        ("gemini", "gemini-3.1-pro", "free", 429, 0, 0.0),
        ("gemini", "gemini-3.1-pro", "paid", 500, 0, 0.0),
        ("gemini", "gemini-flash-lite-latest", "paid", 200, 12, pytest.approx(0.000003)),
    ]


def test_el_adaptador_respeta_los_modelos_candidatos_que_recibe_y_avisa_cada_intento(red):
    red.estado_por_modelo = {"modelo-uno": 404}
    intentos: list[Intento] = []

    respuesta, _ = ProveedorGemini().generar_con_conmutacion(
        PEDIDO_DE_GOOGLE, [("free", GRATUITA)], ["modelo-uno", "modelo-dos"], al_intentar=intentos.append
    )

    assert red.modelos() == ["modelo-uno", "modelo-dos"]
    assert respuesta.modelo == "modelo-dos"
    # Sin tarifa conocida la respuesta no trae un costo inventado
    assert respuesta.costo_usd is None
    assert [(i.nivel, i.modelo, i.estado, i.ok, i.tokens_totales, i.costo_usd) for i in intentos] == [
        ("free", "modelo-uno", 404, False, 0, 0.0),
        ("free", "modelo-dos", 200, True, 12, None),
    ]


def test_sin_clave_o_si_nada_responde_levanta_su_error_y_no_registra_la_clave_ni_el_texto_crudo(red, cuenta_y_repo, caplog):
    gemini, repo = cuenta_y_repo
    pasarela = PasarelaDeIA.de_repositorio(repo)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(tipos.FaltaClaveDeIA):
            pasarela.generar(PEDIDO, "unit_test", repo)
        assert red.pedidos == []

        gemini.save_keys_config(free_key=GRATUITA)
        red.estado_por_clave = {GRATUITA: 403}
        with pytest.raises(tipos.ClaveRechazada) as rechazada:
            pasarela.generar(PEDIDO, "unit_test", repo)
        red.estado_por_clave = {}
        red.falla = httpx.ConnectError(f"sin ruta con {GRATUITA}")
        with pytest.raises(tipos.IANoDisponibleError, match="No se pudo conectar con Gemini") as caida:
            pasarela.generar(PEDIDO, "unit_test", repo)

    # Cinco modelos con el 403 y cinco con la red caída
    assert len(red.pedidos) == 10
    assert "HTTP 403" in caplog.text and "PERMISSION_DENIED" in caplog.text
    for texto in (caplog.text, str(rechazada.value), str(caida.value)):
        assert GRATUITA not in texto
        assert TEXTO_CRUDO not in texto
    # Lo que no llegó a Google (sin clave, red caída) no se anota; los cinco 403 sí
    assert [fila[3] for fila in _consumos(repo.user_id)] == [403] * 5


def test_los_errores_de_ia_son_los_de_la_capa_de_proveedores():
    assert gemini_gateway.IANoDisponibleError is tipos.IANoDisponibleError
    assert gemini_gateway.FaltaClaveDeIA is tipos.FaltaClaveDeIA
    assert gemini_gateway.MENSAJE_FALTA_CLAVE == str(tipos.FaltaClaveDeIA())
    assert issubclass(tipos.FaltaClaveDeIA, tipos.IANoDisponibleError)
    assert str(tipos.FaltaClaveDeIA("Otro mensaje.")) == "Otro mensaje."


def test_un_modelo_sin_tarifa_no_tiene_un_costo_inventado():
    assert GeminiGateway.calculate_cost("gemini-que-no-tiene-tarifa", 1_000_000, 1_000_000) == 0.0


def test_las_claves_salen_en_el_orden_del_nivel_activo(pasarela):
    assert pasarela.claves_en_orden() == []
    pasarela.save_keys_config(paid_key=PAGA)
    assert pasarela.claves_en_orden() == [("paid", PAGA)]
    pasarela.save_keys_config(free_key=GRATUITA)
    assert pasarela.claves_en_orden() == [("free", GRATUITA), ("paid", PAGA)]
    pasarela.save_keys_config(tier="paid")
    assert pasarela.claves_en_orden() == [("paid", PAGA)]
    pasarela.save_keys_config(tier="free")
    assert pasarela.claves_en_orden() == [("free", GRATUITA)]


def test_el_nivel_elegido_sin_su_clave_usa_la_que_haya(pasarela):
    pasarela.save_keys_config(free_key=GRATUITA, tier="paid")
    assert pasarela.claves_en_orden() == [("free", GRATUITA)]


def test_los_modelos_candidatos_son_el_preferido_y_la_rotacion_sin_repetirlo(pasarela):
    assert pasarela.modelos_candidatos() == [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-pro-latest",
    ]
    pasarela.save_model("gemini-3.8-flash")
    assert pasarela.modelos_candidatos() == [
        "gemini-3.8-flash",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-pro-latest",
    ]
