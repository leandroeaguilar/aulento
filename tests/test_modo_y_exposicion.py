"""Modo local por defecto y freno a exponerlo sin login (050: R1, R2, R3)."""

import pytest
from conftest import administrador_de_prueba
from fastapi.testclient import TestClient
from identidad_de_prueba import extension_de_identidad
from typer.testing import CliRunner

from aulento.cli import web_commands
from aulento.config import ModoInvalido, get_engine_mode
from aulento.core.exposicion import (
    ExposicionRechazada,
    exigir_modo_compatible_con_la_exposicion,
)
from aulento.web.app import create_app


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, "local"), ("", "local"), ("  ", "local"), ("local", "local"), ("LOCAL", "local"),
     ("saas", "saas"), (" SaaS ", "saas")],
)
def test_modo_segun_la_variable(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("AULENTO_MODE", raising=False)
    else:
        monkeypatch.setenv("AULENTO_MODE", valor)
    assert get_engine_mode() == esperado


@pytest.mark.parametrize("valor", ["xyz", "cloud", "monousuario", "single_user", "true"])
def test_modo_desconocido_se_rechaza_nombrando_los_validos(monkeypatch, valor):
    monkeypatch.setenv("AULENTO_MODE", valor)
    with pytest.raises(ModoInvalido) as error:
        get_engine_mode()
    assert "local" in str(error.value) and "saas" in str(error.value)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::", "estudio.example.com"])
def test_modo_local_no_se_expone_fuera_de_la_maquina(monkeypatch, host):
    monkeypatch.setenv("AULENTO_MODE", "local")
    monkeypatch.delenv("AULENTO_TRUSTED_PROXIES", raising=False)
    with pytest.raises(ExposicionRechazada, match="AULENTO_MODE=saas"):
        exigir_modo_compatible_con_la_exposicion(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", None])
def test_modo_local_en_la_maquina_arranca(monkeypatch, host):
    monkeypatch.setenv("AULENTO_MODE", "local")
    monkeypatch.delenv("AULENTO_TRUSTED_PROXIES", raising=False)
    exigir_modo_compatible_con_la_exposicion(host)


def test_modo_local_con_proxy_de_confianza_no_arranca(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "local")
    monkeypatch.setenv("AULENTO_TRUSTED_PROXIES", "172.30.0.2")
    with pytest.raises(ExposicionRechazada):
        exigir_modo_compatible_con_la_exposicion("127.0.0.1")


def test_modo_saas_no_frena_por_el_modo(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "saas")
    monkeypatch.setenv("AULENTO_TRUSTED_PROXIES", "172.30.0.2")
    exigir_modo_compatible_con_la_exposicion("0.0.0.0")


def test_el_lifespan_en_modo_local_con_proxy_no_arranca(monkeypatch):
    """Cubre a Uvicorn lanzado sin la CLI (por ejemplo, en Docker)."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    monkeypatch.setenv("AULENTO_TRUSTED_PROXIES", "172.30.0.2")
    with pytest.raises(ExposicionRechazada), TestClient(create_app()):
        pass


@pytest.fixture
def uvicorn_falso(monkeypatch):
    llamadas = []
    monkeypatch.setattr(web_commands.uvicorn, "run", lambda app, **opciones: llamadas.append((app, opciones)))
    return llamadas


def test_cli_en_modo_local_hacia_afuera_sale_con_error(monkeypatch, uvicorn_falso):
    monkeypatch.setenv("AULENTO_MODE", "local")
    resultado = CliRunner().invoke(web_commands.web_app, ["start", "--host", "0.0.0.0", "--no-open-browser"])
    assert resultado.exit_code == 1
    assert "AULENTO_MODE=saas" in resultado.output.replace("\n", "")
    assert uvicorn_falso == []


def test_cli_en_modo_saas_hacia_afuera_no_frena_por_el_modo(monkeypatch, uvicorn_falso):
    """En saas el freno es solo el de siempre (clave maestra y cifrado o proxy), no el del modo."""
    monkeypatch.setenv("AULENTO_MODE", "saas")
    monkeypatch.setenv("AULENTO_SECRET_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    monkeypatch.setenv("AULENTO_TRUSTED_PROXIES", "172.30.0.2")
    resultado = CliRunner().invoke(web_commands.web_app, ["start", "--host", "0.0.0.0", "--no-open-browser"])
    assert resultado.exit_code == 0, resultado.output
    assert [app for app, _ in uvicorn_falso] == ["aulento.web.app:app"]


def test_cli_con_modo_invalido_sale_con_error(monkeypatch, uvicorn_falso):
    monkeypatch.setenv("AULENTO_MODE", "xyz")
    resultado = CliRunner().invoke(web_commands.web_app, ["start", "--no-open-browser"])
    assert resultado.exit_code == 1
    assert uvicorn_falso == []


def test_cli_en_local_arranca_el_core_y_con_app_arranca_otra(monkeypatch, uvicorn_falso):
    monkeypatch.setenv("AULENTO_MODE", "local")
    assert CliRunner().invoke(web_commands.web_app, ["start", "--no-open-browser"]).exit_code == 0
    resultado = CliRunner().invoke(
        web_commands.web_app, ["start", "--no-open-browser", "--app", "otro_paquete.app:app"]
    )
    assert resultado.exit_code == 0
    assert [app for app, _ in uvicorn_falso] == ["aulento.web.app:app", "otro_paquete.app:app"]


@pytest.mark.sin_sesion
@pytest.mark.parametrize("cliente", ["192.168.1.20", "10.0.0.7", "2001:db8::1"])
def test_modo_local_rechaza_pedidos_de_otros_equipos(monkeypatch, cliente):
    """Uvicorn lanzado a mano en 0.0.0.0 sin proxy: el pedido de otro equipo no entra como administrador (R2)."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    client = TestClient(create_app(), client=(cliente, 50000))
    respuesta = client.get("/api/materiales")
    assert respuesta.status_code == 403
    assert "AULENTO_MODE=saas" in respuesta.json()["detail"]
    assert client.get("/").status_code == 403


@pytest.mark.sin_sesion
@pytest.mark.parametrize("cliente", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
def test_modo_local_atiende_a_la_propia_maquina(monkeypatch, cliente):
    monkeypatch.setenv("AULENTO_MODE", "local")
    client = TestClient(create_app(), client=(cliente, 50000))
    assert client.get("/api/materiales").status_code == 200


def test_modo_saas_atiende_a_otros_equipos(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "saas")
    app = create_app(extensiones=[extension_de_identidad(administrador_de_prueba)])
    client = TestClient(app, client=("192.168.1.20", 50000))
    assert client.get("/api/materiales").status_code == 200


def test_modo_local_no_imprime_codigo_de_administrador(monkeypatch, capsys):
    """Sin login, el código del primer administrador no sirve: el arranque local no lo emite."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    monkeypatch.delenv("AULENTO_TRUSTED_PROXIES", raising=False)
    with TestClient(create_app()):
        pass
    assert "código de invitación" not in capsys.readouterr().out


