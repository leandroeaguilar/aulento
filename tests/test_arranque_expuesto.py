"""Comandos de arranque de la web y de MCP fuera de la máquina: clave maestra y cifrado (039, R1, R2, R3)."""

import pytest
from identidad_de_prueba import modo_saas
from typer.testing import CliRunner

from aulento.cli import web_commands
from aulento.cli.app import cli
from aulento.config import get_data_dir
from aulento.core.exposicion import VARIABLE_DE_PROXIES_DE_CONFIANZA
from aulento.core.secretos import (
    ARCHIVO_DE_LA_CLAVE_MAESTRA,
    VARIABLE_DE_LA_CLAVE_MAESTRA,
)

runner = CliRunner()
ANCHO = {"COLUMNS": "400"}
# `web` sin subcomando, `web start` y el alias `serve` arrancan igual
COMANDOS_WEB = [["web"], ["web", "start"], ["serve"]]


@pytest.fixture(autouse=True)
def modo_expuesto(monkeypatch):
    """Exponer el servidor es del modo saas; el comando lo decide por la variable, sin cargar la app."""
    modo_saas(monkeypatch)


@pytest.fixture(autouse=True)
def sin_proxies(monkeypatch):
    monkeypatch.delenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, raising=False)
    monkeypatch.delenv("AULENTO_ALLOWED_HOSTS", raising=False)


@pytest.fixture
def uvicorn_falso(monkeypatch):
    """Reemplaza `uvicorn.run` del comando web; devuelve la lista de (aplicación, opciones) con que se lo llamó."""
    llamadas = []
    monkeypatch.setattr(web_commands.uvicorn, "run", lambda aplicacion, **opciones: llamadas.append((aplicacion, opciones)))
    return llamadas


@pytest.fixture
def navegador(monkeypatch):
    abiertos = []
    monkeypatch.setattr(web_commands.webbrowser, "open", lambda url: abiertos.append(url))
    return abiertos


@pytest.fixture
def sin_clave(monkeypatch):
    monkeypatch.delenv(VARIABLE_DE_LA_CLAVE_MAESTRA, raising=False)


@pytest.fixture
def certificado(tmp_path):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    return str(cert), str(key)


def _web(comando, *argumentos):
    return runner.invoke(cli, [*comando, *argumentos, "--no-open-browser"], env=ANCHO)


def _archivo_de_clave():
    return get_data_dir() / ARCHIVO_DE_LA_CLAVE_MAESTRA


# --- Clave maestra (R1) ---


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
def test_expuesto_sin_clave_sale_con_1_sin_llamar_a_uvicorn(uvicorn_falso, sin_clave, comando):
    resultado = _web(comando, "--host", "0.0.0.0", "--insecure-http")

    assert resultado.exit_code == 1
    assert uvicorn_falso == []
    assert VARIABLE_DE_LA_CLAVE_MAESTRA in resultado.stdout
    assert not _archivo_de_clave().exists()


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
def test_en_bucle_local_arranca_sin_clave_como_antes(uvicorn_falso, sin_clave, comando):
    resultado = _web(comando)

    assert resultado.exit_code == 0, resultado.output
    assert [aplicacion for aplicacion, _ in uvicorn_falso] == ["aulento.web.app:app"]
    assert uvicorn_falso[0][1]["host"] == "127.0.0.1"


# --- Cifrado (R2) ---


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::"])
def test_expuesto_con_clave_y_sin_cifrado_sale_con_1(uvicorn_falso, comando, host):
    resultado = _web(comando, "--host", host)

    assert resultado.exit_code == 1
    assert uvicorn_falso == []
    assert "--ssl-certfile" in resultado.stdout and "--insecure-http" in resultado.stdout
    assert VARIABLE_DE_PROXIES_DE_CONFIANZA in resultado.stdout


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
def test_con_insecure_http_arranca_y_avisa_que_va_sin_cifrar(uvicorn_falso, comando):
    resultado = _web(comando, "--host", "0.0.0.0", "--insecure-http")

    assert resultado.exit_code == 0, resultado.output
    assert uvicorn_falso[0][1]["host"] == "0.0.0.0"
    assert "sin cifrar" in resultado.stdout
    assert "ssl_certfile" not in uvicorn_falso[0][1]


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
def test_con_proxies_declarados_arranca_sin_aviso_de_http(uvicorn_falso, monkeypatch, comando):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "172.30.0.2")

    resultado = _web(comando, "--host", "0.0.0.0")

    assert resultado.exit_code == 0, resultado.output
    assert uvicorn_falso[0][1]["host"] == "0.0.0.0"
    assert "sin cifrar" not in resultado.stdout


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
def test_con_certificado_pasa_los_archivos_a_uvicorn(uvicorn_falso, certificado, comando):
    cert, key = certificado

    resultado = _web(comando, "--host", "0.0.0.0", "--ssl-certfile", cert, "--ssl-keyfile", key)

    assert resultado.exit_code == 0, resultado.output
    opciones = uvicorn_falso[0][1]
    assert (opciones["ssl_certfile"], opciones["ssl_keyfile"]) == (cert, key)
    assert "https://0.0.0.0" in resultado.stdout
    assert "sin cifrar" not in resultado.stdout


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
@pytest.mark.parametrize("cual", ["--ssl-certfile", "--ssl-keyfile"])
def test_un_solo_archivo_tls_es_error(uvicorn_falso, certificado, comando, cual):
    resultado = _web(comando, "--host", "0.0.0.0", cual, certificado[0])

    assert resultado.exit_code == 1
    assert uvicorn_falso == []
    assert "van juntos" in resultado.stdout


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
def test_un_archivo_tls_inexistente_es_error(uvicorn_falso, certificado, tmp_path, comando):
    faltante = str(tmp_path / "no-existe.pem")

    resultado = _web(comando, "--host", "0.0.0.0", "--ssl-certfile", faltante, "--ssl-keyfile", certificado[1])

    assert resultado.exit_code == 1
    assert uvicorn_falso == []
    assert "No existe el archivo TLS" in resultado.stdout


# --- Proxies de confianza (R3) ---


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_una_lista_de_proxies_invalida_no_arranca_y_nombra_el_valor(uvicorn_falso, monkeypatch, comando, host):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "172.30.0.2,proxy.local")

    resultado = _web(comando, "--host", host, "--insecure-http")

    assert resultado.exit_code == 1
    assert uvicorn_falso == []
    assert "proxy.local" in resultado.stdout


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
@pytest.mark.parametrize(
    "argumentos", [[], ["--host", "0.0.0.0", "--insecure-http"]], ids=["bucle-local", "expuesto"]
)
def test_uvicorn_recibe_siempre_proxy_headers_false(uvicorn_falso, comando, argumentos):
    """La confianza en las cabeceras de proxy la decide la aplicación: Uvicorn no cree ni en 127.0.0.1."""
    resultado = _web(comando, *argumentos)

    assert resultado.exit_code == 0, resultado.output
    assert uvicorn_falso[0][1]["proxy_headers"] is False


# --- Navegador ---


@pytest.mark.parametrize("comando", COMANDOS_WEB, ids=" ".join)
def test_no_se_abre_el_navegador_fuera_del_bucle_local(uvicorn_falso, navegador, comando):
    expuesto = runner.invoke(cli, [*comando, "--host", "0.0.0.0", "--insecure-http", "--open-browser"], env=ANCHO)
    local = runner.invoke(cli, [*comando, "--open-browser"], env=ANCHO)

    assert (expuesto.exit_code, local.exit_code) == (0, 0)
    assert len(uvicorn_falso) == 2
    assert navegador == ["http://127.0.0.1:8000/"]


def test_en_ipv6_local_la_url_lleva_corchetes(uvicorn_falso, navegador):
    resultado = runner.invoke(cli, ["web", "start", "--host", "::1", "--open-browser"], env=ANCHO)

    assert resultado.exit_code == 0
    assert navegador == ["http://[::1]:8000/"]


@pytest.mark.parametrize("valor", [None, "", " , ,", ","])
def test_expuesto_sin_hosts_permitidos_utiles_avisa(uvicorn_falso, monkeypatch, valor):
    """Una lista con solo comas o espacios no agrega ningún host (como `get_allowed_hosts`): el aviso sale igual."""
    if valor is not None:
        monkeypatch.setenv("AULENTO_ALLOWED_HOSTS", valor)

    resultado = _web(["web", "start"], "--host", "0.0.0.0", "--insecure-http")

    assert resultado.exit_code == 0
    assert "AULENTO_ALLOWED_HOSTS" in resultado.stdout


def test_expuesto_con_hosts_permitidos_no_avisa(uvicorn_falso, monkeypatch):
    monkeypatch.setenv("AULENTO_ALLOWED_HOSTS", "estudio.example.com")

    resultado = _web(["web", "start"], "--host", "0.0.0.0", "--insecure-http")

    assert resultado.exit_code == 0
    assert "AULENTO_ALLOWED_HOSTS" not in resultado.stdout


def test_el_asistente_arranca_el_servidor_con_la_funcion_compartida(uvicorn_falso, navegador):
    """`onboarding` llama a `run_web_server`: arranca en bucle local, sin volver a abrir el navegador."""
    web_commands.run_web_server(host="127.0.0.1", port=8000, reload=False)

    assert uvicorn_falso == [
        ("aulento.web.app:app", {"host": "127.0.0.1", "port": 8000, "reload": False, "proxy_headers": False})
    ]
    assert navegador == []


# --- MCP por red (R1, R2) ---


@pytest.fixture
def servir_mcp(monkeypatch):
    llamadas = []
    monkeypatch.setattr("aulento.cli.mcp_commands.run_sse_server", lambda **kw: llamadas.append(kw))
    return llamadas


def test_mcp_por_red_sin_clave_sale_con_1(servir_mcp, sin_clave):
    resultado = runner.invoke(
        cli, ["mcp", "serve", "--transport", "http", "--allow-remote", "--insecure-http"], env=ANCHO
    )

    assert resultado.exit_code == 1
    assert servir_mcp == []
    assert VARIABLE_DE_LA_CLAVE_MAESTRA in resultado.stdout
    assert not _archivo_de_clave().exists()


def test_mcp_por_red_con_proxies_declarados_arranca_sin_insecure_http(servir_mcp, monkeypatch):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "172.30.0.2")

    resultado = runner.invoke(cli, ["mcp", "serve", "--transport", "http", "--allow-remote"], env=ANCHO)

    assert resultado.exit_code == 0, resultado.output
    assert servir_mcp[0]["host"] == "0.0.0.0"
    assert "sin cifrar" not in resultado.stdout


def test_mcp_por_red_con_proxies_invalidos_no_arranca(servir_mcp, monkeypatch):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "*")

    resultado = runner.invoke(cli, ["mcp", "serve", "--transport", "http"], env=ANCHO)

    assert resultado.exit_code == 1
    assert servir_mcp == []
    assert "«*»" in resultado.stdout


def test_mcp_en_bucle_local_arranca_sin_clave(servir_mcp, sin_clave):
    resultado = runner.invoke(cli, ["mcp", "serve", "--transport", "http"], env=ANCHO)

    assert resultado.exit_code == 0, resultado.output
    assert servir_mcp[0]["host"] == "127.0.0.1"
