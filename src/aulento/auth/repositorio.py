"""Acceso a datos de cuentas, datos sin dueño y tokens del servidor MCP."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

COLUMNAS_USUARIO = "id, nombre_usuario, rol, activo, creado_en, ultimo_ingreso"

# Tablas raíz de los datos de estudio: cada fila lleva en `user_id` la cuenta dueña
TABLAS_CON_DUENO = (
    "plataformas",
    "libros_lectura",
    "bloques_horarios",
    "fsrs_items",
    "sesiones_estudio",
    "rutas_aprendizaje",
    "api_usage_logs",
    "mcp_audit_logs",
)
TABLA_DE_AUDITORIA_MCP = "mcp_audit_logs"
# Nombre con el que la auditoría MCP anota un pedido rechazado por la autenticación: esas filas no son de nadie
REGISTRO_DE_RECHAZO_MCP = "mcp_autenticacion"


class RepositorioAuth:
    """Todo el SQL de autenticación; no confirma por su cuenta salvo dentro de `transaccion()`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _ejecutar(self, sql: str, parametros: tuple = ()) -> sqlite3.Cursor:
        cursor = self.conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute(sql, parametros)
        return cursor

    @contextmanager
    def transaccion(self) -> Iterator[None]:
        """Toma el turno de escritura, confirma al salir y revierte ante cualquier error."""
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN IMMEDIATE;")
        try:
            yield
        except BaseException:
            self.conn.rollback()
            raise
        self.conn.commit()

    # --- Cuentas ---

    def crear_usuario(self, nombre_usuario: str, contrasena_hash: str, rol: str, creado_en: str) -> int:
        """Inserta una cuenta activa y retorna su id; IntegrityError si el nombre ya existe."""
        cursor = self._ejecutar(
            "INSERT INTO usuarios (nombre_usuario, contrasena_hash, rol, activo, creado_en) VALUES (?, ?, ?, 1, ?);",
            (nombre_usuario, contrasena_hash, rol, creado_en),
        )
        return int(cursor.lastrowid)

    def usuario_por_id(self, usuario_id: int) -> sqlite3.Row | None:
        """Retorna la cuenta completa (incluida la derivación) por id."""
        return self._ejecutar("SELECT * FROM usuarios WHERE id = ?;", (usuario_id,)).fetchone()

    def usuario_por_nombre(self, nombre_usuario: str) -> sqlite3.Row | None:
        """Retorna la cuenta completa (incluida la derivación) por nombre, sin distinguir mayúsculas."""
        return self._ejecutar("SELECT * FROM usuarios WHERE nombre_usuario = ?;", (nombre_usuario,)).fetchone()

    def listar_usuarios(self) -> list[sqlite3.Row]:
        """Lista las cuentas sin la derivación de la contraseña."""
        return self._ejecutar(f"SELECT {COLUMNAS_USUARIO} FROM usuarios ORDER BY id;").fetchall()

    def contar_usuarios(self) -> int:
        """Cuenta todas las cuentas, activas o no."""
        return int(self._ejecutar("SELECT COUNT(*) FROM usuarios;").fetchone()[0])

    def contar_admins_activos(self) -> int:
        """Cuenta los administradores activos."""
        return int(self._ejecutar("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND activo = 1;").fetchone()[0])


    def reclamar_datos_sin_dueno(self, usuario_id: int) -> int:
        """Pone a nombre de la cuenta todas las filas sin dueño de las tablas raíz y retorna cuántas fueron.

        Los rechazos de autenticación del servidor MCP no se reclaman: quedan sin cuenta para siempre.
        """
        reclamadas = 0
        for tabla in TABLAS_CON_DUENO:
            if tabla == TABLA_DE_AUDITORIA_MCP:
                continue
            reclamadas += self._ejecutar(
                f"UPDATE {tabla} SET user_id = ? WHERE user_id IS NULL;", (usuario_id,)
            ).rowcount
        reclamadas += self._ejecutar(
            "UPDATE mcp_audit_logs SET user_id = ? WHERE user_id IS NULL AND tool_name <> ?;",
            (usuario_id, REGISTRO_DE_RECHAZO_MCP),
        ).rowcount
        return reclamadas

    # --- Tokens del servidor MCP ---

    def crear_token_mcp(self, usuario_id: int, token_hash: str, nombre: str | None, creado_en: str) -> int:
        """Inserta un token MCP de la cuenta guardando solo su huella; retorna su id."""
        cursor = self._ejecutar(
            "INSERT INTO mcp_tokens (usuario_id, token_hash, nombre, creado_en) VALUES (?, ?, ?, ?);",
            (usuario_id, token_hash, nombre, creado_en),
        )
        return int(cursor.lastrowid)

    def listar_tokens_mcp(self, usuario_id: int | None = None) -> list[sqlite3.Row]:
        """Lista los tokens MCP de una cuenta (o de todas, con `usuario_id=None`) sin la huella."""
        consulta = (
            "SELECT t.id, t.usuario_id, u.nombre_usuario, t.nombre, t.creado_en, t.ultimo_uso, t.revocado_en "
            "FROM mcp_tokens t JOIN usuarios u ON u.id = t.usuario_id"
        )
        if usuario_id is None:
            return self._ejecutar(f"{consulta} ORDER BY t.id;").fetchall()
        return self._ejecutar(f"{consulta} WHERE t.usuario_id = ? ORDER BY t.id;", (usuario_id,)).fetchall()

    def revocar_token_mcp(self, token_id: int, momento: str, usuario_id: int | None = None) -> bool:
        """Revoca un token vigente, de esa cuenta si se indica; False si no existe, es de otra o ya estaba revocado."""
        if usuario_id is None:
            cursor = self._ejecutar(
                "UPDATE mcp_tokens SET revocado_en = ? WHERE id = ? AND revocado_en IS NULL;", (momento, token_id)
            )
        else:
            cursor = self._ejecutar(
                "UPDATE mcp_tokens SET revocado_en = ? WHERE id = ? AND usuario_id = ? AND revocado_en IS NULL;",
                (momento, token_id, usuario_id),
            )
        return cursor.rowcount == 1

    def token_mcp_por_huella(self, token_hash: str) -> sqlite3.Row | None:
        """Retorna el token con los datos de su cuenta (`token_id`, `token_hash`, `ultimo_uso`, `revocado_en`, `id`, …)."""
        return self._ejecutar(
            "SELECT t.id AS token_id, t.token_hash, t.ultimo_uso, t.revocado_en, "
            "u.id, u.nombre_usuario, u.rol, u.activo "
            "FROM mcp_tokens t JOIN usuarios u ON u.id = t.usuario_id WHERE t.token_hash = ?;",
            (token_hash,),
        ).fetchone()

    def anotar_uso_de_token_mcp(self, token_id: int, momento: str) -> None:
        """Anota el momento del último uso de un token MCP."""
        self._ejecutar("UPDATE mcp_tokens SET ultimo_uso = ? WHERE id = ?;", (momento, token_id))

    # --- Intentos de ingreso ---


