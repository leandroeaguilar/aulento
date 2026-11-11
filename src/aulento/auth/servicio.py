"""Reglas de negocio de la cuenta local y los tokens del servidor MCP (sin FastAPI).

Lo multiusuario (contraseñas, sesiones, invitaciones) lo aporta la extensión de identidad (051).

Cada función confirma su propia transacción sobre la conexión recibida.
"""

import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from aulento.auth.modelos import (
    ROL_ADMIN,
    NombreDeUsuarioInvalido,
    NombreDeUsuarioReservado,
    TokenMcpEmitido,
    TokenMcpNoEncontrado,
    Usuario,
    UsuarioNoEncontrado,
)
from aulento.auth.repositorio import RepositorioAuth

if TYPE_CHECKING:
    from aulento.core.importacion import Informe

logger = logging.getLogger(__name__)

# Recibe el informe de la importación de archivos anteriores, o None si la importación no pudo correr
AvisoDeImportacion = Callable[["Informe | None"], None]

# Igual que con las sesiones: el último uso de un token MCP no se escribe en cada pedido
ANOTAR_USO_DE_TOKEN_MCP_CADA = timedelta(minutes=5)
LARGO_NOMBRE_DE_TOKEN_MCP = 64


_FORMATO_NOMBRE = re.compile(r"[a-z0-9._-]{3,32}")

NOMBRES_RESERVADOS: set[str] = set()


# NombreDeUsuarioReservado se importa desde aulento.auth.modelos


def registrar_nombres_reservados(*nombres: str) -> None:
    """Registra nombres de usuario que no pueden ser elegidos por los usuarios."""
    NOMBRES_RESERVADOS.update(n.lower() for n in nombres)


def ahora() -> datetime:
    """Momento actual en UTC; los tests lo sustituyen para mover el reloj."""
    return datetime.now(UTC)


def huella(secreto: str) -> str:
    """SHA-256 en hexadecimal de un token o código; es lo único que se guarda de ellos."""
    return hashlib.sha256(secreto.encode("utf-8")).hexdigest()


def normalizar_nombre_usuario(nombre_usuario: str) -> str:
    """Retorna el nombre en minúsculas o levanta NombreDeUsuarioInvalido si no respeta el formato o NombreDeUsuarioReservado si está reservado."""
    nombre = nombre_usuario.lower()
    if not _FORMATO_NOMBRE.fullmatch(nombre):
        raise NombreDeUsuarioInvalido()
    if nombre in NOMBRES_RESERVADOS:
        raise NombreDeUsuarioReservado()
    return nombre


def _iso(momento: datetime) -> str:
    """Fecha UTC en ISO 8601 de ancho fijo, comparable como texto."""
    return momento.astimezone(UTC).isoformat(timespec="microseconds")


def _a_usuario(fila: sqlite3.Row) -> Usuario:
    return Usuario(id=fila["id"], nombre_usuario=fila["nombre_usuario"], rol=fila["rol"], activo=bool(fila["activo"]))


def _usuario_existente(repo: RepositorioAuth, usuario_id: int) -> sqlite3.Row:
    fila = repo.usuario_por_id(usuario_id)
    if fila is None:
        raise UsuarioNoEncontrado()
    return fila


def _heredar_datos_sin_dueno(repo: RepositorioAuth, usuario_id: int, rol: str) -> bool:
    """Dentro de la transacción del alta: decide si la cuenta nueva recibe los datos que no tienen dueño.

    Los recibe la primera cuenta del sistema y también la que pasa a ser el único administrador activo:
    una base que se migró con cuentas pero sin administrador dejó sus filas sin dueño a la espera de uno.
    Devuelve si es la primera cuenta: solo ella importa, además, los archivos anteriores de la instalación.
    Un administrador que llega después podría recibir el vault y los archivos de quien estaba antes: los
    pide a mano con `aulento user import-files`.
    """
    es_la_primera = repo.contar_usuarios() == 1
    es_el_unico_administrador = rol == ROL_ADMIN and repo.contar_admins_activos() == 1
    if es_la_primera or es_el_unico_administrador:
        repo.reclamar_datos_sin_dueno(usuario_id)
    return es_la_primera


def _importar_archivos_anteriores(
    conn: sqlite3.Connection, usuario_id: int, al_importar: AvisoDeImportacion | None
) -> None:
    """Con el alta ya confirmada: carga en la primera cuenta de la instalación sus archivos anteriores.

    Va fuera de la transacción del alta: si la importación falla la cuenta queda creada, el fallo se registra
    (sin secretos) y se puede reintentar con `aulento user import-files`.
    """
    # Se importa acá: la importación arrastra los conectores y el servidor MCP, que importan este módulo
    from aulento.core.importacion import (
        ERRORES_DE_IMPORTACION,
        importar_archivos_anteriores,
    )

    informe = None
    try:
        informe = importar_archivos_anteriores(conn, usuario_id)
    except ERRORES_DE_IMPORTACION as error:
        if conn.in_transaction:
            conn.rollback()
        logger.warning(
            "No se pudieron importar los archivos anteriores a la cuenta %s (%s). "
            "Se puede reintentar con 'aulento user import-files'.",
            usuario_id,
            type(error).__name__,
        )
    else:
        if informe.encontro_algo:
            # Con archivos retirados el resumen avisa que el respaldo guarda secretos en claro: tiene que verse
            hay_que_mirarlo = informe.hubo_fallos or bool(informe.retirados)
            logger.log(logging.WARNING if hay_que_mirarlo else logging.INFO, "%s", informe.resumen())
    if al_importar is not None:
        al_importar(informe)


ID_DE_LA_CUENTA_LOCAL = 1
NOMBRE_DE_LA_CUENTA_LOCAL = "local_user"
# El modo local no tiene ingreso: la cuenta no tiene contraseña con la que entrar
SIN_CONTRASENA = "local_mode_no_password"


def crear_cuenta_local(conn: sqlite3.Connection, al_importar: AvisoDeImportacion | None = None) -> Usuario:
    """Crea la cuenta única del modo local (id 1, administrador) por el camino de las cuentas (051, R7).

    Como cualquier primera cuenta, hereda los datos sin dueño y recibe los archivos anteriores de la
    instalación; si la base trae un código de primer administrador de un arranque multiusuario, lo anula.
    """
    repo = RepositorioAuth(conn)
    es_la_primera = False
    with repo.transaccion():
        cursor = conn.execute(
            "INSERT OR IGNORE INTO usuarios (id, nombre_usuario, contrasena_hash, rol, activo, creado_en) "
            "VALUES (?, ?, ?, ?, 1, ?);",
            (ID_DE_LA_CUENTA_LOCAL, NOMBRE_DE_LA_CUENTA_LOCAL, SIN_CONTRASENA, ROL_ADMIN, _iso(ahora())),
        )
        creada = cursor.rowcount == 1
        if creada:
            tiene_invitaciones = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'invitaciones';"
            ).fetchone()
            if tiene_invitaciones:
                # Una base que viene de un arranque multiusuario puede traer un código de primer administrador
                conn.execute("DELETE FROM invitaciones WHERE inicial = 1 AND usada_en IS NULL;")
            es_la_primera = _heredar_datos_sin_dueno(repo, ID_DE_LA_CUENTA_LOCAL, ROL_ADMIN)
    if es_la_primera:
        _importar_archivos_anteriores(conn, ID_DE_LA_CUENTA_LOCAL, al_importar)
    fila = repo.usuario_por_id(ID_DE_LA_CUENTA_LOCAL)
    if fila is None:
        # El INSERT se ignoró por otro choque: una base multiusuario sin la cuenta 1 y con el nombre ya tomado
        raise CuentaLocalImposible()
    return Usuario(id=fila["id"], nombre_usuario=fila["nombre_usuario"], rol=ROL_ADMIN, activo=True)


class CuentaLocalImposible(RuntimeError):
    """La base no tiene la cuenta 1 y otra cuenta ya usa el nombre de la cuenta local."""

    def __init__(self) -> None:
        super().__init__(
            f"No se pudo crear la cuenta local: la base no tiene la cuenta {ID_DE_LA_CUENTA_LOCAL} y otra cuenta ya se "
            f"llama «{NOMBRE_DE_LA_CUENTA_LOCAL}». Es una base de un servidor con varias cuentas: renombrá esa cuenta "
            "o arrancá en modo nube."
        )


def crear_token_mcp(conn: sqlite3.Connection, usuario_id: int, nombre: str | None = None) -> TokenMcpEmitido:
    """Emite un token de 256 bits para que la cuenta use el servidor MCP por red; el token en claro no se guarda."""
    repo = RepositorioAuth(conn)
    _usuario_existente(repo, usuario_id)
    etiqueta = (nombre or "").strip()[:LARGO_NOMBRE_DE_TOKEN_MCP] or None
    token = secrets.token_urlsafe(32)
    creado_en = _iso(ahora())
    with repo.transaccion():
        token_id = repo.crear_token_mcp(usuario_id, huella(token), etiqueta, creado_en)
    return TokenMcpEmitido(id=token_id, token=token, nombre=etiqueta, creado_en=creado_en)


def listar_tokens_mcp(conn: sqlite3.Connection, usuario_id: int | None = None) -> list[sqlite3.Row]:
    """Tokens MCP de una cuenta, o de todas con `usuario_id=None` (administración); nunca llevan la huella."""
    return RepositorioAuth(conn).listar_tokens_mcp(usuario_id)


def revocar_token_mcp(conn: sqlite3.Connection, token_id: int, usuario_id: int | None = None) -> None:
    """Revoca un token MCP; con `usuario_id`, solo si es de esa cuenta.

    Levanta TokenMcpNoEncontrado, sin cambiar nada, si no existe, es de otra cuenta o ya estaba revocado.
    """
    repo = RepositorioAuth(conn)
    with repo.transaccion():
        if not repo.revocar_token_mcp(token_id, _iso(ahora()), usuario_id):
            raise TokenMcpNoEncontrado()


def revocar_todos_los_tokens_mcp(conn: sqlite3.Connection, usuario_id: int) -> int:
    """Revoca todos los tokens MCP vigentes de la cuenta."""
    momento = _iso(ahora())
    cursor = conn.execute(
        "UPDATE mcp_tokens SET revocado_en = ? WHERE usuario_id = ? AND revocado_en IS NULL;",
        (momento, usuario_id),
    )
    return cursor.rowcount


def resolver_token_mcp(conn: sqlite3.Connection, token: str | None) -> Usuario | None:
    """Retorna la cuenta activa dueña de un token MCP vigente y anota su uso; None si el token no vale."""
    if not token:
        return None
    repo = RepositorioAuth(conn)
    token_hash = huella(token)
    fila = repo.token_mcp_por_huella(token_hash)
    if fila is None or not hmac.compare_digest(fila["token_hash"], token_hash):
        return None
    if fila["revocado_en"] is not None or not fila["activo"]:
        return None
    momento = ahora()
    if fila["ultimo_uso"] is None or fila["ultimo_uso"] <= _iso(momento - ANOTAR_USO_DE_TOKEN_MCP_CADA):
        try:
            with repo.transaccion():
                repo.anotar_uso_de_token_mcp(fila["token_id"], _iso(momento))
        except sqlite3.OperationalError:
            # Otro escritor tiene la base tomada: el token vale igual y el uso se anota en un pedido posterior
            pass
    return _a_usuario(fila)
