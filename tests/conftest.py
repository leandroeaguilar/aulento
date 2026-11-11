"""Configuración y fixtures compartidas de pytest."""

import base64
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

# Asegurar que los imports de aulento usen el src de este worktree
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

# La suite no hereda las variables con el nombre anterior de quien la corre: `aulento` las adopta al importarse
# (ADR 021) y se colarían en todos los tests (070, R6)
for _variable in [nombre for nombre in os.environ if nombre.startswith("STUDY_ENGINE_")]:
    del os.environ[_variable]

from aulento import config as configuracion
from aulento.auth.modelos import Usuario
from aulento.db.connection import get_connection
from aulento.db.schema import init_db, seed_plataformas

try:
    # Ayudantes de lo multiusuario (cuentas con contraseña y sesión): no se publican con el core (051)
    import nube_cuentas
except ImportError:
    nube_cuentas = None

# Los E2E necesitan los navegadores de Playwright (`playwright install chromium`): corren a pedido y en una
# corrida aparte, `AULENTO_E2E=1 pytest tests/e2e`. Sin la variable `pytest` los saltea (también en
# `verify`, que no instala navegadores). No se mezclan con el resto: la API síncrona de Playwright deja un
# event loop de asyncio corriendo en el hilo principal y los tests asíncronos que vienen después fallan.
collect_ignore_glob = [] if os.getenv("AULENTO_E2E") == "1" else ["e2e/*"]


def pytest_configure(config):
    """Registra las marcas propias de la suite y fija el ancho de las consolas de la CLI."""
    # Las consolas de Rich de la CLI fijan su ancho al importarse si COLUMNS está definida, y entonces ignoran
    # el COLUMNS que cada test pasa al invocarla: las tablas se recortan y los asserts fallan según la terminal
    # (en CI, 80). Un ancho fijo y amplio, antes de recolectar los tests, hace la suite igual en todos lados.
    os.environ["COLUMNS"] = "400"
    config.addinivalue_line(
        "markers", "sin_sesion: el test recorre la autenticación real, sin la sesión de prueba sustituida"
    )
    config.addinivalue_line(
        "markers", "sin_tablas_de_la_nube: un test de la nube que necesita la base sin las tablas de la nube"
    )
    config.addinivalue_line(
        "markers", "multiusuario: el test prueba cuentas multiusuario y corre en modo saas (se muda a la nube, 051)"
    )
    config.addinivalue_line(
        "markers", "scrypt_de_produccion: el test usa los parámetros reales de scrypt, sin abaratarlos"
    )


@pytest.fixture(autouse=True)
def modo_de_la_suite(request, monkeypatch):
    """El core es monousuario (ADR 017): la suite corre en modo local.

    Lo multiusuario corre en modo saas: los tests de la nube (`test_nube_*`) y los marcados `multiusuario`, que
    son los que se mudan a la nube con las cuentas (051).
    """
    multiusuario = request.node.get_closest_marker("multiusuario") or request.node.path.name.startswith("test_nube_")
    if multiusuario and nube_cuentas is None:
        pytest.skip("multiusuario: corre con las cuentas de la nube")
    monkeypatch.setenv("AULENTO_MODE", "saas" if multiusuario else "local")


# Clave Fernet fija de la suite: 32 bytes conocidos, no protege nada real
CLAVE_MAESTRA_DE_PRUEBA = base64.urlsafe_b64encode(b"clave-maestra-de-la-suite-32-byt").decode("ascii")

# Variables de entorno que la importación de archivos anteriores toma como origen (034, R10)
VARIABLES_ANTERIORES_A_LAS_CUENTAS = (
    "AULENTO_VAULT_PATH",
    "OBSIDIAN_VAULT_PATH",
)

NOMBRE_DEL_ADMINISTRADOR_DE_PRUEBA = "admin-de-prueba"
NOMBRE_DE_LA_OTRA_CUENTA = "otra-cuenta-de-prueba"


def cuenta_de_prueba(conn: sqlite3.Connection, nombre: str = "cuenta-de-prueba", rol: str = "usuario") -> Usuario:
    """Devuelve la cuenta con ese nombre en la base de `conn`, creándola si falta.

    La crea por SQL directo: no hereda las filas sin dueño ni tiene una contraseña con la que ingresar.
    """
    consulta = "SELECT id, nombre_usuario, rol, activo FROM usuarios WHERE nombre_usuario = ?;"
    fila = conn.execute(consulta, (nombre,)).fetchone()
    if fila is None:
        conn.execute(
            "INSERT INTO usuarios (nombre_usuario, contrasena_hash, rol, activo, creado_en) VALUES (?, ?, ?, 1, ?);",
            (nombre, "sin-contrasena", rol, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        fila = conn.execute(consulta, (nombre,)).fetchone()
    return Usuario(id=fila[0], nombre_usuario=fila[1], rol=fila[2], activo=bool(fila[3]))


def administrador_de_prueba(conn: sqlite3.Connection) -> Usuario:
    """Cuenta con la que la suite hace sus pedidos web; al crearla recibe las plataformas semilla."""
    existia = conn.execute(
        "SELECT 1 FROM usuarios WHERE nombre_usuario = ?;", (NOMBRE_DEL_ADMINISTRADOR_DE_PRUEBA,)
    ).fetchone()
    usuario = cuenta_de_prueba(conn, NOMBRE_DEL_ADMINISTRADOR_DE_PRUEBA, rol="admin")
    if not existia:
        seed_plataformas(conn, usuario.id)
    return usuario


@pytest.fixture(autouse=True)
def sesion_de_prueba(request, monkeypatch):
    """En lo multiusuario, da a todo pedido la sesión de un administrador que existe en la base del pedido.

    `@pytest.mark.sin_sesion` deja el camino real y no crea ninguna cuenta. En local no hace falta: todo pedido es
    de la cuenta local.
    """
    if request.node.get_closest_marker("sin_sesion") or nube_cuentas is None:
        return
    nube_cuentas.sustituir_sesion(monkeypatch, administrador_de_prueba)


def cuenta_en(db_path: Path | str | None = None) -> int:
    """Id del administrador de prueba en la base de esa ruta, que migra si hace falta; sin ruta, la base aislada."""
    conn = get_connection(db_path)
    try:
        init_db(conn)
        return administrador_de_prueba(conn).id
    finally:
        conn.close()


def vault_de_prueba(db_path: Path | str | None = None, user_id: int | None = None) -> Path:
    """Vault de una cuenta de la base de esa ruta (o la aislada); sin `user_id`, el del administrador de prueba."""
    from aulento.vault.rutas import vault_de_la_cuenta_con_conexion_propia

    return vault_de_la_cuenta_con_conexion_propia(user_id if user_id is not None else cuenta_en(db_path), db_path)


@pytest.fixture
def cuenta(isolated_cloud_env) -> int:
    """Id de la cuenta de la base aislada del test: la misma con la que se hacen los pedidos web."""
    return cuenta_en()


@pytest.fixture
def otra_cuenta(isolated_cloud_env) -> int:
    """Id de una segunda cuenta, sin datos, en la base aislada del test."""
    conn = get_connection()
    try:
        return cuenta_de_prueba(conn, NOMBRE_DE_LA_OTRA_CUENTA).id
    finally:
        conn.close()


@pytest.fixture
def operar_por_mcp():
    """Función que fija la cuenta como la que opera el servidor MCP (igual que un token o stdio) hasta el fin del test."""
    from aulento.mcp import security

    marcas = []

    def fijar(user_id: int) -> int:
        marcas.append(security.fijar_cuenta_mcp(user_id))
        return user_id

    yield fijar
    for marca in reversed(marcas):
        try:
            security.restablecer_cuenta_mcp(marca)
        except ValueError:
            # Se fijó dentro de un test asíncrono: su contexto terminó con el test y no hay nada que deshacer
            pass


@pytest.fixture
def cuenta_mcp(operar_por_mcp) -> int:
    """El servidor MCP del test opera como el administrador de prueba de la base aislada; devuelve su id."""
    return operar_por_mcp(cuenta_en())


def token_mcp_de_prueba(db_path: Path | str | None = None) -> str:
    """Token MCP en claro, recién creado, del administrador de prueba de la base de esa ruta (o la aislada)."""
    from aulento.auth import servicio

    cuenta_id = cuenta_en(db_path)
    conn = get_connection(db_path)
    try:
        return servicio.crear_token_mcp(conn, cuenta_id, "de prueba").token
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def scrypt_de_prueba(request, monkeypatch):
    """Abarata scrypt en toda la suite; `@pytest.mark.scrypt_de_produccion` conserva el costo real."""
    if request.node.get_closest_marker("scrypt_de_produccion") or nube_cuentas is None:
        return
    nube_cuentas.abaratar_scrypt(monkeypatch)


@pytest.fixture
def memory_db():
    """Conexión a una base SQLite en memoria con el esquema y una cuenta: `cuenta_de_prueba(memory_db)`."""
    conn = get_connection(":memory:")
    init_db(conn)
    cuenta_de_prueba(conn)
    yield conn
    conn.close()


@pytest.fixture
def seeded_memory_db():
    """Como `memory_db`, con las plataformas semilla sembradas para su cuenta."""
    conn = get_connection(":memory:")
    init_db(conn)
    seed_plataformas(conn, cuenta_de_prueba(conn).id)
    yield conn
    conn.close()


@pytest.fixture
def temp_db_path(tmp_path: Path):
    """Ruta temporal en disco para pruebas de persistencia."""
    db_file = tmp_path / "test_study.db"
    return db_file


@pytest.fixture(autouse=True)
def directorio_y_clave_de_prueba(monkeypatch, tmp_path_factory) -> Path:
    """Ningún test lee ni escribe el directorio de datos real: cada uno tiene el suyo, y una clave maestra de prueba."""
    directorio = tmp_path_factory.mktemp("datos_de_prueba")
    monkeypatch.setenv("AULENTO_DATA_DIR", str(directorio))
    monkeypatch.setenv("AULENTO_SECRET_KEY", CLAVE_MAESTRA_DE_PRUEBA)
    # Ni la carpeta anterior real (~/.study-engine) se muda ni se elige por defecto en un test (070, R7)
    monkeypatch.setattr(configuracion, "CARPETA_ANTERIOR", directorio.parent / "carpeta-anterior-inexistente")
    # Al crear la primera cuenta se importan los archivos y variables anteriores: las de quien corre la suite no cuentan
    for variable in VARIABLES_ANTERIORES_A_LAS_CUENTAS:
        monkeypatch.delenv(variable, raising=False)
    # Los proxies de confianza y la cookie segura de quien corre la suite tampoco: cambiarían la app de cada test
    monkeypatch.delenv("AULENTO_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("AULENTO_COOKIE_SECURE", raising=False)
    return directorio


@pytest.fixture(autouse=True)
def isolated_cloud_env(monkeypatch, tmp_path_factory, directorio_y_clave_de_prueba):
    """Aísla la suite: base propia y sin cuentas."""
    test_db_dir = tmp_path_factory.mktemp("default_test_db")
    test_db_file = test_db_dir / "isolated_test_study.db"
    conn = get_connection(str(test_db_file))
    init_db(conn)
    conn.close()
    monkeypatch.setenv("AULENTO_DB_PATH", str(test_db_file))
    # Ningún test lee el token MCP del usuario; los vaults viven en el directorio de datos de prueba
    monkeypatch.setenv("AULENTO_HOME", str(tmp_path_factory.mktemp("default_home")))


@pytest.fixture(autouse=True)
def tablas_de_la_nube(request, isolated_cloud_env):
    """En los tests de la nube, la base aislada trae sus tablas aunque la app no pase por el arranque."""
    if request.node.get_closest_marker("sin_tablas_de_la_nube"):
        return
    if nube_cuentas is not None and request.node.path.name.startswith("test_nube_"):
        nube_cuentas.migrar_la_base_del_test()


@pytest.fixture(autouse=True)
def sin_postgres_real(monkeypatch):
    """Ningún test abre una conexión a un PostgreSQL de verdad: para la suite, el almacén de vectores está apagado."""
    from aulento.db import postgres, vector_repository

    def rechazar(*args, **kwargs):
        raise ConnectionError("La suite no se conecta a PostgreSQL: usá la fixture `pgvector_falso`.")

    monkeypatch.setattr(postgres, "get_postgres_connection", rechazar)
    monkeypatch.setattr(vector_repository, "get_postgres_connection", rechazar)


@pytest.fixture
def pgvector_falso(monkeypatch, sin_postgres_real):
    """El almacén de vectores conectado a un doble en memoria (`pgvector_fake.PgvectorFalso`)."""
    import pgvector_fake

    yield pgvector_fake.instalar(monkeypatch)
    pgvector_fake.desinstalar()


def find_free_port() -> int:
    """Encuentra un puerto TCP libre efímero."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def _entorno_temporal(valores: dict[str, str]):
    """Fija variables de entorno mientras dura el bloque y deja las anteriores al salir."""
    import os

    anteriores = {nombre: os.environ.get(nombre) for nombre in valores}
    os.environ.update(valores)
    try:
        yield
    finally:
        for nombre, valor in anteriores.items():
            if valor is None:
                os.environ.pop(nombre, None)
            else:
                os.environ[nombre] = valor


def _servidor_vivo(modo: str, fabrica, datos: Path):
    """Levanta Uvicorn en segundo plano con la app de `fabrica()` en `modo`; rinde la URL base.

    Arranca con la base y el directorio de datos en `datos`: el arranque migra y siembra, y nunca debe
    tocar la base real de quien corre la suite.
    """
    import threading
    import time

    import uvicorn

    port = find_free_port()
    with _entorno_temporal(
        {
            "AULENTO_DATA_DIR": str(datos),
            "AULENTO_DB_PATH": str(datos / "study_engine.db"),
            "AULENTO_HOME": str(datos / "home"),
            "AULENTO_MODE": modo,
            "AULENTO_ALLOWED_ORIGINS": f"http://127.0.0.1:{port}",
            "AULENTO_ALLOWED_HOSTS": f"127.0.0.1,localhost,127.0.0.1:{port}",
        }
    ):
        app = fabrica()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=5)


# Por módulo: al terminar se apaga y su app suelta las suscripciones del bus de eventos del proceso
@pytest.fixture(scope="module")
def live_local_server(tmp_path_factory):
    """Servidor del core en modo local."""
    from aulento.web.app import create_app

    yield from _servidor_vivo("local", create_app, tmp_path_factory.mktemp("servidor_local"))
