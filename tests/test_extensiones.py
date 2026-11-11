"""Puntos de extensión del core: rutas, estáticos, etiquetas en la página y migraciones propias (050: R4, R5, R6)."""

import sqlite3
from pathlib import Path

import pytest
from conftest import administrador_de_prueba
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from identidad_de_prueba import extension_de_identidad, modo_saas, sin_sesion

from aulento.core.eventos import bus
from aulento.core.extensiones import (
    Extension,
    ExtensionInvalida,
    MigracionDeExtension,
    aplicar_migraciones_de_extension,
    versiones_aplicadas,
)
from aulento.db.connection import get_connection
from aulento.db.migrations import ErrorDeMigracion, migrar, version_actual
from aulento.web.app import create_app
from aulento.web.dependencies import Cuenta

CON_SESION = extension_de_identidad(administrador_de_prueba)
SIN_SESION = extension_de_identidad(sin_sesion)


def _router_de_prueba() -> APIRouter:
    router = APIRouter(prefix="/api/ext-prueba")

    @router.get("/quien")
    def quien(usuario: Cuenta) -> dict:
        return {"usuario": usuario.nombre_usuario}

    return router


@pytest.fixture
def estaticos(tmp_path) -> Path:
    carpeta = tmp_path / "estaticos"
    carpeta.mkdir()
    (carpeta / "widget.js").write_text("window.widgetDePrueba = true;", encoding="utf-8")
    (carpeta / "widget.css").write_text(".widget{}", encoding="utf-8")
    return carpeta


def _tabla(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE prueba_ext (id INTEGER PRIMARY KEY, valor TEXT);")


def _columna(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE prueba_ext ADD COLUMN extra TEXT;")


def _extension(estaticos: Path, **cambios) -> Extension:
    datos = {
        "nombre": "prueba",
        "routers": (_router_de_prueba(),),
        "migraciones": (MigracionDeExtension(1, "tabla", _tabla),),
        "estaticos": estaticos,
        "hojas_de_estilo": ("widget.css",),
        "scripts": ("widget.js",),
    }
    datos.update(cambios)
    return Extension(**datos)


def test_la_extension_suma_rutas_estaticos_y_etiquetas(estaticos, monkeypatch):
    modo_saas(monkeypatch)
    with TestClient(create_app(extensiones=[CON_SESION, _extension(estaticos)])) as client:
        assert client.get("/api/ext-prueba/quien").json() == {"usuario": "admin-de-prueba"}

        js = client.get("/static/ext/prueba/widget.js")
        assert js.status_code == 200
        assert "widgetDePrueba" in js.text
        # El estático propio del core sigue sirviéndose
        assert client.get("/static/app.js").status_code == 200

        pagina = client.get("/").text
        assert '<link rel="stylesheet" href="/static/ext/prueba/widget.css">' in pagina
        assert '<script src="/static/ext/prueba/widget.js" defer></script>' in pagina
        assert pagina.index("widget.js") < pagina.rindex("</body>")
        assert pagina.index("widget.css") < pagina.index("</head>")


def test_las_rutas_de_la_extension_exigen_sesion_en_saas(estaticos, monkeypatch):
    modo_saas(monkeypatch)
    client = TestClient(create_app(extensiones=[SIN_SESION, _extension(estaticos)]))
    assert client.get("/api/ext-prueba/quien").status_code == 401


@pytest.mark.sin_sesion
def test_router_publico_responde_sin_sesion_en_saas(estaticos, monkeypatch):
    modo_saas(monkeypatch)
    router_pub = APIRouter(prefix="/api/ext-publico")

    @router_pub.get("/hola")
    def hola():
        return {"publico": True}

    ext = _extension(estaticos, routers_publicos=(router_pub,))
    client = TestClient(create_app(extensiones=[SIN_SESION, ext]))
    resp = client.get("/api/ext-publico/hola")
    assert resp.status_code == 200
    assert resp.json() == {"publico": True}


def test_portada_se_sirve_sin_sesion_en_saas_no_con_sesion_ni_en_local(estaticos, tmp_path, monkeypatch):
    modo_saas(monkeypatch)
    archivo_portada = tmp_path / "portada.html"
    archivo_portada.write_text("<!DOCTYPE html><h1>Portada</h1>", encoding="utf-8")
    ext = _extension(estaticos, portada=archivo_portada)

    # 1. En SaaS sin sesión: sirve la portada con Cache-Control no-cache
    client_sin = TestClient(create_app(extensiones=[SIN_SESION, ext]))
    resp_sin = client_sin.get("/", follow_redirects=False)
    assert resp_sin.status_code == 200
    assert "Portada" in resp_sin.text
    assert "no-cache" in resp_sin.headers.get("cache-control", "")

    # 2. Sin portada declarada (o si el archivo no existe): redirige a /login
    ext_sin = _extension(estaticos, portada=None)
    client_sin_portada = TestClient(create_app(extensiones=[SIN_SESION, ext_sin]))
    resp_redirect = client_sin_portada.get("/", follow_redirects=False)
    assert resp_redirect.status_code == 303
    assert resp_redirect.headers["location"] == "/login"

    ext_inexistente = _extension(estaticos, portada=tmp_path / "no_existe.html")
    client_inexistente = TestClient(create_app(extensiones=[SIN_SESION, ext_inexistente]))
    assert client_inexistente.get("/", follow_redirects=False).status_code == 303

    # 3. En local: pasa directo a la aplicación (no sirve la portada)
    monkeypatch.setenv("AULENTO_MODE", "local")
    client_local = TestClient(create_app(extensiones=[ext]))
    resp_local = client_local.get("/", follow_redirects=False)
    assert resp_local.status_code == 200
    assert "Portada" not in resp_local.text
    assert 'data-modo="local"' in resp_local.text


def test_portada_no_se_sirve_con_sesion_activa(estaticos, tmp_path, monkeypatch):
    modo_saas(monkeypatch)
    archivo_portada = tmp_path / "portada.html"
    archivo_portada.write_text("<!DOCTYPE html><h1>Portada</h1>", encoding="utf-8")
    ext = _extension(estaticos, portada=archivo_portada)

    with TestClient(create_app(extensiones=[CON_SESION, ext])) as client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200
        assert "Portada" not in resp.text
        assert 'data-modo="saas"' in resp.text


def test_validador_de_cuenta_frena_rutas_con_usuario_en_saas(estaticos, monkeypatch):
    modo_saas(monkeypatch)
    def frena_cuenta(usuario, conn):
        raise HTTPException(status_code=403, detail="Cuenta bloqueada por validador.")

    ext = _extension(estaticos, validadores_de_cuenta=(frena_cuenta,))

    with TestClient(create_app(extensiones=[CON_SESION, ext])) as client:
        resp = client.get("/api/ext-prueba/quien")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Cuenta bloqueada por validador."


@pytest.mark.sin_sesion
def test_validador_de_cuenta_no_corre_en_modo_local(estaticos, monkeypatch):
    def frena_cuenta(usuario, conn):
        raise HTTPException(status_code=403, detail="No debería llamarse en local.")

    ext = _extension(estaticos, validadores_de_cuenta=(frena_cuenta,))

    monkeypatch.setenv("AULENTO_MODE", "local")
    with TestClient(create_app(extensiones=[ext])) as client:
        resp = client.get("/api/ext-prueba/quien")
        assert resp.status_code == 200
        assert resp.json() == {"usuario": "local_user"}


@pytest.mark.sin_sesion
def test_en_modo_local_las_rutas_de_la_extension_son_del_usuario_local(estaticos, monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "local")
    client = TestClient(create_app(extensiones=[_extension(estaticos)]))
    assert client.get("/api/ext-prueba/quien").json() == {"usuario": "local_user"}


@pytest.mark.parametrize("nombre", ["", "Prueba", "1ext", "con-guion", "con espacio", "../x"])
def test_nombre_invalido_hace_fallar_create_app(estaticos, nombre):
    with pytest.raises(ExtensionInvalida):
        create_app(extensiones=[_extension(estaticos, nombre=nombre)])


def test_nombres_repetidos_hacen_fallar_create_app(estaticos):
    with pytest.raises(ExtensionInvalida, match="dos extensiones"):
        create_app(extensiones=[_extension(estaticos), _extension(estaticos)])


@pytest.mark.parametrize(
    "recurso", ["../app.js", "/static/app.js", "https://cdn.example.com/x.js", "a//b.js", "C:\\x.js", ""]
)
def test_recursos_ajenos_hacen_fallar_create_app(estaticos, recurso):
    with pytest.raises(ExtensionInvalida):
        create_app(extensiones=[_extension(estaticos, scripts=(recurso,))])


def test_recursos_sin_carpeta_de_estaticos_hacen_fallar(estaticos):
    with pytest.raises(ExtensionInvalida, match="carpeta de estáticos"):
        create_app(extensiones=[_extension(None, scripts=("widget.js",), hojas_de_estilo=())])


def test_migraciones_desordenadas_hacen_fallar(estaticos):
    desordenadas = (MigracionDeExtension(2, "columna", _columna), MigracionDeExtension(1, "tabla", _tabla))
    with pytest.raises(ExtensionInvalida, match="numerarse"):
        create_app(extensiones=[_extension(estaticos, migraciones=desordenadas)])


def test_migraciones_se_aplican_una_vez_y_no_tocan_el_user_version(estaticos, tmp_path):
    conn = get_connection(tmp_path / "ext.db")
    try:
        migrar(conn, respaldo=False)
        version_del_core = version_actual(conn)
        extension = _extension(estaticos)

        assert aplicar_migraciones_de_extension(conn, extension) == [1]
        assert aplicar_migraciones_de_extension(conn, extension) == []
        assert versiones_aplicadas(conn, "prueba") == {1}
        assert version_actual(conn) == version_del_core

        # Una versión nueva se aplica sola, sin repetir la anterior
        con_dos = _extension(
            estaticos,
            migraciones=(MigracionDeExtension(1, "tabla", _tabla), MigracionDeExtension(2, "columna", _columna)),
        )
        assert aplicar_migraciones_de_extension(conn, con_dos) == [2]
        columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(prueba_ext);")}
        assert columnas == {"id", "valor", "extra"}
        nombres = conn.execute(
            "SELECT version, nombre FROM migraciones_de_extension WHERE extension = 'prueba' ORDER BY version;"
        ).fetchall()
        assert [tuple(fila) for fila in nombres] == [(1, "tabla"), (2, "columna")]
    finally:
        conn.close()


def test_una_migracion_que_falla_se_revierte_entera(estaticos, tmp_path):
    def a_medias(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE a_medias (id INTEGER);")
        raise RuntimeError("falla en el medio")

    conn = get_connection(tmp_path / "ext.db")
    try:
        migrar(conn, respaldo=False)
        extension = _extension(
            estaticos,
            migraciones=(MigracionDeExtension(1, "tabla", _tabla), MigracionDeExtension(2, "a_medias", a_medias)),
        )
        with pytest.raises(ErrorDeMigracion, match="prueba.a_medias"):
            aplicar_migraciones_de_extension(conn, extension)

        tablas = {fila[0] for fila in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';")}
        assert "prueba_ext" in tablas  # la 1 quedó
        assert "a_medias" not in tablas  # la 2 se revirtió
        assert versiones_aplicadas(conn, "prueba") == {1}
        assert not conn.in_transaction
    finally:
        conn.close()


def test_si_una_migracion_falla_el_servidor_no_arranca(estaticos):
    def rota(_conn):
        raise RuntimeError("no")

    app = create_app(extensiones=[_extension(estaticos, migraciones=(MigracionDeExtension(1, "rota", rota),))])
    with pytest.raises(ErrorDeMigracion), TestClient(app):
        pass


def test_las_suscripciones_de_la_extension_viven_mientras_vive_la_app(estaticos):
    recibidos = []

    def escuchar(**datos):
        recibidos.append(datos)

    app = create_app(extensiones=[_extension(estaticos, suscripciones={"prueba.evento": (escuchar,)})])
    bus.emitir("prueba.evento", n=0)  # antes de arrancar: nadie escucha
    with TestClient(app):
        bus.emitir("prueba.evento", n=1)
    bus.emitir("prueba.evento", n=2)  # al cerrar se desuscribe
    with TestClient(app):
        bus.emitir("prueba.evento", n=3)  # al volver a arrancar no se duplica
    assert recibidos == [{"n": 1}, {"n": 3}]
