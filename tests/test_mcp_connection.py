"""Tests de la feature 030: cifrado, hosts permitidos e IP del cliente en el transporte SSE del servidor MCP."""

import sqlite3

import pytest
from conftest import token_mcp_de_prueba
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from typer.testing import CliRunner

from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.db.schema import create_schema
from aulento.mcp import security
from aulento.mcp import server as mcp_server
from aulento.mcp.server import (
    BearerAuthMiddleware,
    create_study_mcp_server,
    transport_security_for,
)

runner = CliRunner()
ANCHO = {"COLUMNS": "400"}


@pytest.fixture
def servir(monkeypatch):
    """Reemplaza el arranque real del servidor SSE y captura sus parámetros."""
    llamadas = []
    monkeypatch.setattr("aulento.cli.mcp_commands.run_sse_server", lambda **kw: llamadas.append(kw))
    return llamadas


@pytest.fixture
def certificado(tmp_path):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    return str(cert), str(key)


# ---------------------------------------------------------------- R5: cifrado


def test_r5_allow_remote_sin_certificado_no_arranca(servir):
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse", "--allow-remote"], env=ANCHO)
    assert res.exit_code == 1
    assert servir == []
    assert "--ssl-certfile" in res.stdout and "--insecure-http" in res.stdout


def test_r5_allow_remote_con_insecure_http_arranca_y_advierte(servir):
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse", "--allow-remote", "--insecure-http"], env=ANCHO)
    assert res.exit_code == 0
    assert servir[0]["host"] == "0.0.0.0"
    assert servir[0]["ssl_certfile"] is None
    assert "sin cifrar" in res.stdout


def test_r5_con_certificado_sirve_por_https_sin_advertencia(servir, certificado):
    cert, key = certificado
    res = runner.invoke(
        cli, ["mcp", "serve", "--transport", "sse", "--allow-remote", "--ssl-certfile", cert, "--ssl-keyfile", key], env=ANCHO
    )
    assert res.exit_code == 0
    assert (servir[0]["ssl_certfile"], servir[0]["ssl_keyfile"]) == (cert, key)
    assert "https://0.0.0.0" in res.stdout
    assert "sin cifrar" not in res.stdout


@pytest.mark.parametrize("cual", ["--ssl-certfile", "--ssl-keyfile"])
def test_r5_certificado_incompleto_no_arranca(servir, certificado, cual):
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse", cual, certificado[0]], env=ANCHO)
    assert res.exit_code == 1
    assert servir == []
    assert "van juntos" in res.stdout


def test_r5_archivo_de_certificado_inexistente_no_arranca(servir, certificado, tmp_path):
    res = runner.invoke(
        cli,
        ["mcp", "serve", "--transport", "sse", "--ssl-certfile", str(tmp_path / "no-existe.pem"), "--ssl-keyfile", certificado[1]],
        env=ANCHO,
    )
    assert res.exit_code == 1
    assert servir == []
    assert "No existe el archivo TLS" in res.stdout


def test_r5_local_sin_certificado_sigue_arrancando(servir):
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse"], env=ANCHO)
    assert res.exit_code == 0
    assert servir[0]["host"] == "127.0.0.1"
    assert servir[0]["allowed_hosts"] is None


def test_r5_el_certificado_llega_a_uvicorn(monkeypatch, capsys):
    capturado = {}
    monkeypatch.setattr(mcp_server.uvicorn, "run", lambda app, **kw: capturado.update(kw))
    try:
        mcp_server.run_sse_server(port=8125, ssl_certfile="c.pem", ssl_keyfile="k.pem")
        assert (capturado["ssl_certfile"], capturado["ssl_keyfile"]) == ("c.pem", "k.pem")
        assert "https://127.0.0.1:8125/sse" in capsys.readouterr().out

        capturado.clear()
        mcp_server.run_sse_server(port=8126)
        assert "ssl_certfile" not in capturado and "ssl_keyfile" not in capturado
        assert "http://127.0.0.1:8126/sse" in capsys.readouterr().out
    finally:
        security.set_audit_transport("stdio")


# ---------------------------------------------------------------- R6: hosts permitidos


def test_r6_sin_hosts_no_se_arma_proteccion_propia():
    assert transport_security_for(None) is None
    assert transport_security_for([]) is None
    assert transport_security_for(["  "]) is None


def test_r6_los_hosts_permitidos_arman_la_proteccion():
    ajustes = transport_security_for(["mi-pc.local", "10.0.0.5:8000"])
    assert ajustes.enable_dns_rebinding_protection is True
    assert ajustes.allowed_hosts[:3] == ["mi-pc.local", "mi-pc.local:*", "10.0.0.5:8000"]
    assert "https://mi-pc.local" in ajustes.allowed_origins
    assert "http://mi-pc.local:*" in ajustes.allowed_origins
    assert "https://10.0.0.5:8000" in ajustes.allowed_origins


def test_r6_cli_pasa_los_hosts_permitidos(servir):
    res = runner.invoke(
        cli,
        ["mcp", "serve", "--transport", "sse", "--allow-remote", "--insecure-http", "--allowed-host", "mi-pc.local", "--allowed-host", "10.0.0.5"],
        env=ANCHO,
    )
    assert res.exit_code == 0
    assert servir[0]["allowed_hosts"] == ["mi-pc.local", "10.0.0.5"]
    assert "no se controla la cabecera Host" not in res.stdout

    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse", "--allow-remote", "--insecure-http"], env=ANCHO)
    assert "no se controla la cabecera Host" in res.stdout


@pytest.mark.parametrize(
    ("cabeceras", "estado"),
    [({"Host": "evil.example"}, 421), ({"Host": "mi-pc.local:8000", "Origin": "https://evil.example"}, 403)],
)
def test_r6_el_servidor_rechaza_host_y_origin_ajenos(cabeceras, estado):
    server = create_study_mcp_server()
    app = server.sse_app(host="0.0.0.0", transport_security=transport_security_for(["mi-pc.local"]))
    app.add_middleware(BearerAuthMiddleware)
    token = token_mcp_de_prueba()
    res = TestClient(app, raise_server_exceptions=False).get("/sse", headers={"Authorization": f"Bearer {token}", **cabeceras})
    assert res.status_code == estado


# ---------------------------------------------------------------- R7: IP del cliente


def _auditoria(db_file):
    conn = sqlite3.connect(str(db_file))
    try:
        return conn.execute("SELECT tool_name, transport, client_ip FROM mcp_audit_logs ORDER BY id").fetchall()
    finally:
        conn.close()


def test_r7_la_auditoria_guarda_la_ip_del_cliente(tmp_path):
    db_file = tmp_path / "audit.db"
    conn = get_connection(db_file)
    create_schema(conn)
    conn.close()

    def herramienta(request):
        security.log_mcp_tool_execution("herramienta_de_prueba", {}, db_path=db_file)
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/sse", herramienta)])
    app.add_middleware(BearerAuthMiddleware, db_path=db_file)
    token = token_mcp_de_prueba(db_file)
    security.set_audit_transport("sse")
    try:
        res = TestClient(app, client=("203.0.113.7", 50000)).get("/sse", headers={"Authorization": f"Bearer {token}"})
    finally:
        security.set_audit_transport("stdio")
    assert res.status_code == 200
    assert _auditoria(db_file) == [("herramienta_de_prueba", "sse", "203.0.113.7")]

    # Fuera de una petición (stdio) no hay IP
    security.log_mcp_tool_execution("herramienta_de_prueba", {}, db_path=db_file)
    assert _auditoria(db_file)[-1] == ("herramienta_de_prueba", "stdio", None)


def test_r7_una_ip_explicita_tiene_prioridad(tmp_path):
    db_file = tmp_path / "audit.db"
    conn = get_connection(db_file)
    create_schema(conn)
    conn.close()
    security.log_mcp_tool_execution("x", {}, client_ip="198.51.100.2", db_path=db_file)
    assert _auditoria(db_file) == [("x", "stdio", "198.51.100.2")]


# ---------------------------------------------------------------- R10: Streamable HTTP


def test_r10_cli_http_usa_streamable_http_y_sse_avisa(servir):
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "http"], env=ANCHO)
    assert res.exit_code == 0
    assert servir[0]["transport"] == "http"
    assert "Streamable HTTP" in res.stdout and "/mcp" in res.stdout
    assert "mal formada" not in res.stdout

    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse"], env=ANCHO)
    assert servir[1]["transport"] == "sse"
    assert "/sse" in res.stdout
    assert "mal formada" in res.stdout and "--transport http" in res.stdout

    res = runner.invoke(cli, ["mcp", "serve", "--transport", "telepatia"], env=ANCHO)
    assert res.exit_code == 1 and len(servir) == 2


def test_r10_transporte_de_red_desconocido_no_arranca(monkeypatch):
    monkeypatch.setattr(mcp_server.uvicorn, "run", lambda app, **kw: pytest.fail("no debe arrancar"))
    with pytest.raises(ValueError):
        mcp_server.run_sse_server(transport="telepatia")


def _evento(res):
    """Mensaje JSON-RPC de una respuesta de Streamable HTTP (JSON directo o un evento SSE)."""
    import json

    if res.headers.get("content-type", "").startswith("application/json"):
        return res.json()
    datos = [ln[5:].strip() for ln in res.text.splitlines() if ln.startswith("data:")]
    return json.loads(datos[-1])


def test_r10_sesion_completa_por_streamable_http_con_token_e_ip_en_la_auditoria(tmp_path, monkeypatch, capsys):
    db_file = tmp_path / "http.db"
    capturado = {}
    monkeypatch.setattr(mcp_server.uvicorn, "run", lambda app, **kw: capturado.update(app=app, **kw))
    try:
        mcp_server.run_sse_server(port=8127, db_path=db_file, transport="http")
        assert "http://127.0.0.1:8127/mcp" in capsys.readouterr().out
        token = token_mcp_de_prueba(db_file)
        cabeceras = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Host": "127.0.0.1:8127",
        }
        with TestClient(capturado["app"], client=("203.0.113.9", 40000)) as client:
            assert client.post("/mcp", json={}, headers={k: v for k, v in cabeceras.items() if k != "Authorization"}).status_code == 401

            ini = client.post(
                "/mcp",
                headers=cabeceras,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
                },
            )
            assert ini.status_code == 200, ini.text
            assert _evento(ini)["result"]["serverInfo"]["name"] == "aulento"
            sesion = {**cabeceras, "mcp-session-id": ini.headers["mcp-session-id"], "mcp-protocol-version": "2025-06-18"}
            assert client.post("/mcp", headers=sesion, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202

            lista = client.post("/mcp", headers=sesion, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            # Por red se ofrecen las mismas herramientas que registra el servidor local
            import anyio

            registradas = {h.name for h in anyio.run(create_study_mcp_server(db_path=db_file).list_tools)}
            assert {h["name"] for h in _evento(lista)["result"]["tools"]} == registradas

            llamada = client.post(
                "/mcp",
                headers=sesion,
                json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "study_add_book", "arguments": {"title": "Libro por HTTP", "total_pages": 50}}},
            )
            assert "Libro por HTTP" in _evento(llamada)["result"]["content"][0]["text"]
    finally:
        security.set_audit_transport("stdio")

    # El pedido sin token queda registrado como rechazo; después, la herramienta
    assert _auditoria(db_file) == [
        (security.REGISTRO_DE_RECHAZO, "http", "203.0.113.9"),
        ("study_add_book", "http", "203.0.113.9"),
    ]


# ---------------------------------------------------------------- hallazgos de la revisión de código


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::"])
def test_r5_escuchar_fuera_de_la_maquina_con_host_tambien_exige_cifrado(servir, host):
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "http", "--host", host], env=ANCHO)
    assert res.exit_code == 1
    assert servir == []
    assert "--insecure-http" in res.stdout

    res = runner.invoke(cli, ["mcp", "serve", "--transport", "http", "--host", host, "--insecure-http"], env=ANCHO)
    assert res.exit_code == 0
    assert servir[0]["host"] == host
    assert "sin cifrar" in res.stdout and "no se controla la cabecera Host" in res.stdout


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_r5_los_hosts_locales_no_exigen_cifrado(servir, host):
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "http", "--host", host], env=ANCHO)
    assert res.exit_code == 0 and len(servir) == 1
    assert "sin cifrar" not in res.stdout


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("Mi-PC.local", "mi-pc.local"), (" 10.0.0.5:8000 ", "10.0.0.5:8000"), ("::1", "[::1]"), ("[::1]", "[::1]"), ("[fe80::1]:8000", "[fe80::1]:8000")],
)
def test_r6_normaliza_los_hosts_permitidos(valor, esperado):
    assert mcp_server.normalizar_host_permitido(valor) == esperado


@pytest.mark.parametrize("valor", ["https://mi-pc.local", "mi-pc.local/mcp", "mi pc", "usuario@host", ""])
def test_r6_un_host_permitido_mal_escrito_no_arranca(servir, valor):
    with pytest.raises(ValueError):
        mcp_server.normalizar_host_permitido(valor)
    if valor:
        res = runner.invoke(cli, ["mcp", "serve", "--transport", "http", "--allowed-host", valor], env=ANCHO)
        assert res.exit_code == 1 and servir == []
        assert "Host permitido no válido" in res.stdout


def test_r6_ipv6_y_hosts_locales_quedan_permitidos():
    ajustes = transport_security_for(["::1", "Mi-PC.local"])
    assert "[::1]" in ajustes.allowed_hosts and "[::1]:*" in ajustes.allowed_hosts
    assert "mi-pc.local:*" in ajustes.allowed_hosts
    for local in ("127.0.0.1:*", "localhost:*", "localhost"):
        assert local in ajustes.allowed_hosts
    assert len(ajustes.allowed_hosts) == len(set(ajustes.allowed_hosts))


def test_r6_con_hosts_permitidos_un_cliente_local_sigue_entrando():
    server = create_study_mcp_server()
    app = server.streamable_http_app(host="0.0.0.0", transport_security=transport_security_for(["mi-pc.local"]))
    app.add_middleware(BearerAuthMiddleware)
    token = token_mcp_de_prueba()
    cabeceras = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"}
    cuerpo = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/mcp", json=cuerpo, headers={**cabeceras, "Host": "127.0.0.1:8000"}).status_code == 200
        assert client.post("/mcp", json=cuerpo, headers={**cabeceras, "Host": "mi-pc.local:8000"}).status_code == 200
        assert client.post("/mcp", json=cuerpo, headers={**cabeceras, "Host": "evil.example"}).status_code == 421


@pytest.mark.parametrize("transporte", ["http", "sse"])
def test_r6_r10_el_servidor_que_arranca_aplica_los_hosts_permitidos(monkeypatch, transporte):
    capturado = {}
    monkeypatch.setattr(mcp_server.uvicorn, "run", lambda app, **kw: capturado.update(app=app))
    try:
        mcp_server.run_sse_server(host="0.0.0.0", port=8128, transport=transporte, allowed_hosts=["mi-pc.local"])
    finally:
        security.set_audit_transport("stdio")
    token = token_mcp_de_prueba()
    ruta = "/mcp" if transporte == "http" else "/sse"
    auth = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"}
    with TestClient(capturado["app"], raise_server_exceptions=False) as client:
        assert client.get(ruta, headers={**auth, "Host": "evil.example"}).status_code == 421
        assert client.get(ruta, headers={**auth, "Host": "mi-pc.local:8128", "Origin": "https://evil.example"}).status_code == 403
        if transporte == "http":
            # Un GET sin sesión llega al transporte (400), es decir, pasó el control de Host
            assert client.get(ruta, headers={**auth, "Host": "mi-pc.local:8128"}).status_code == 400


def test_r6_sin_hosts_permitidos_en_todas_las_interfaces_no_hay_control_de_host(monkeypatch):
    capturado = {}
    monkeypatch.setattr(mcp_server.uvicorn, "run", lambda app, **kw: capturado.update(app=app))
    try:
        mcp_server.run_sse_server(host="0.0.0.0", port=8129, transport="http")
    finally:
        security.set_audit_transport("stdio")
    token = token_mcp_de_prueba()
    with TestClient(capturado["app"], raise_server_exceptions=False) as client:
        res = client.get("/mcp", headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream", "Host": "cualquiera.example"})
    assert res.status_code == 400
