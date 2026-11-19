"""Migraciones numeradas del esquema SQLite, con la versión guardada en `PRAGMA user_version`."""

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from aulento.db.schema import aplicar_esquema_base

DDL_USUARIOS = """
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    contrasena_hash TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'usuario' CHECK(rol IN ('admin', 'usuario')),
    activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)),
    creado_en TEXT NOT NULL,
    ultimo_ingreso TEXT
);
"""

DDL_PLATAFORMAS_CON_DUENO = """
CREATE TABLE plataformas_nueva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    url_acceso TEXT NOT NULL,
    icono_color TEXT DEFAULT 'blue',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE(user_id, nombre)
);
"""

DDL_RUTAS_APRENDIZAJE_CON_DUENO = """
CREATE TABLE rutas_aprendizaje_nueva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    categoria TEXT DEFAULT 'data_ai',
    nivel_objetivo TEXT DEFAULT 'Senior',
    enfoque_estudio TEXT DEFAULT 'profesional',
    progreso_pct REAL DEFAULT 0.0 CHECK(progreso_pct >= 0.0 AND progreso_pct <= 100.0),
    metadata_json TEXT DEFAULT '{}',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE(user_id, titulo)
);
"""

DDL_FSRS_ITEMS_CON_DUENO = """
CREATE TABLE fsrs_items_nueva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT DEFAULT 'ingles_tecnico',
    item_pregunta TEXT NOT NULL,
    respuesta_esperada TEXT NOT NULL,
    contexto_uso TEXT,
    state INTEGER DEFAULT 1,
    step INTEGER DEFAULT 0,
    stability REAL,
    difficulty REAL,
    due TIMESTAMP,
    last_review TIMESTAMP,
    reps INTEGER DEFAULT 0,
    lapses INTEGER DEFAULT 0,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE(user_id, categoria, item_pregunta)
);
"""

DDL_MCP_TOKENS = """
CREATE TABLE mcp_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    nombre TEXT,
    creado_en TEXT NOT NULL,
    ultimo_uso TEXT,
    revocado_en TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);
"""

DDL_SECRETOS_USUARIO = """
CREATE TABLE secretos_usuario (
    user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    valor_cifrado BLOB NOT NULL,
    actualizado_en TEXT NOT NULL,
    PRIMARY KEY (user_id, nombre)
);
"""

DDL_MATERIALES = """
CREATE TABLE materiales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    extension TEXT NOT NULL,
    tipo_mime TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    archivo TEXT NOT NULL,
    texto TEXT NOT NULL,
    caracteres INTEGER NOT NULL,
    creado_en TIMESTAMP NOT NULL,
    UNIQUE(user_id, sha256)
);
"""

DDL_AJUSTES_USUARIO = """
CREATE TABLE ajustes_usuario (
    user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    valor TEXT NOT NULL,
    actualizado_en TEXT NOT NULL,
    PRIMARY KEY (user_id, clave)
);
"""

# Tablas que la migración 3 reconstruye: DDL nuevo, columnas que se copian y columnas únicas por cuenta
_RECONSTRUIDAS_EN_LA_3: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
    (
        "plataformas",
        DDL_PLATAFORMAS_CON_DUENO,
        ("id", "nombre", "url_acceso", "icono_color", "fecha_creacion"),
        ("nombre",),
    ),
    (
        "rutas_aprendizaje",
        DDL_RUTAS_APRENDIZAJE_CON_DUENO,
        (
            "id",
            "titulo",
            "descripcion",
            "categoria",
            "nivel_objetivo",
            "enfoque_estudio",
            "progreso_pct",
            "metadata_json",
            "fecha_creacion",
            "fecha_actualizacion",
        ),
        ("titulo",),
    ),
    (
        "fsrs_items",
        DDL_FSRS_ITEMS_CON_DUENO,
        (
            "id",
            "categoria",
            "item_pregunta",
            "respuesta_esperada",
            "contexto_uso",
            "state",
            "step",
            "stability",
            "difficulty",
            "due",
            "last_review",
            "reps",
            "lapses",
            "fecha_creacion",
        ),
        ("categoria", "item_pregunta"),
    ),
]

# Tablas que reciben el dueño por ALTER en la migración 3, con lo que pasa con la fila al borrar la cuenta
_AMPLIADAS_EN_LA_3: list[tuple[str, str]] = [
    ("libros_lectura", "CASCADE"),
    ("bloques_horarios", "CASCADE"),
    ("sesiones_estudio", "CASCADE"),
    ("api_usage_logs", "SET NULL"),
    ("mcp_audit_logs", "SET NULL"),
]


class ErrorDeMigracion(RuntimeError):
    """Una migración falló: sus cambios se revirtieron y la versión no avanzó."""

    def __init__(self, version: int, nombre: str) -> None:
        self.version = version
        self.nombre = nombre
        super().__init__(f"Falló la migración {version} ({nombre}); la base quedó en la versión anterior.")


def _migracion_esquema_base(conn: sqlite3.Connection) -> None:
    """Crea (o completa) las tablas anteriores a las migraciones numeradas."""
    aplicar_esquema_base(conn)


def _migracion_cuentas(conn: sqlite3.Connection) -> None:
    """Crea la tabla de cuentas.

    Hasta la 051 creaba también las sesiones, las invitaciones y los intentos de ingreso. Ahora son de la extensión
    que aporta las cuentas multiusuario (ADR 017); las bases que ya las tienen las conservan con sus filas.
    """
    conn.execute(DDL_USUARIOS)


def _reconstruir_con_dueno(
    conn: sqlite3.Connection, tabla: str, ddl_nueva: str, columnas: tuple[str, ...], unicas: tuple[str, ...]
) -> None:
    """Reemplaza una tabla por su versión con dueño conservando filas, ids y el contador de ids.

    Exige las claves foráneas apagadas: con ellas encendidas, borrar la tabla vieja borraría a sus hijas.
    """
    secuencia = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?;", (tabla,)).fetchone()
    lista = ", ".join(columnas)
    conn.execute(ddl_nueva)
    conn.execute(f"INSERT INTO {tabla}_nueva ({lista}) SELECT {lista} FROM {tabla};")
    conn.execute(f"DROP TABLE {tabla};")
    conn.execute(f"ALTER TABLE {tabla}_nueva RENAME TO {tabla};")
    if secuencia is not None:
        # Un id borrado no se vuelve a entregar: los mazos `roadmap_<id>` nombran rutas por su id
        conn.execute("DELETE FROM sqlite_sequence WHERE name = ?;", (tabla,))
        conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?);", (tabla, secuencia[0]))
    # Las filas sin dueño conservan entre sí la unicidad que tenían antes de existir las cuentas
    conn.execute(f"CREATE UNIQUE INDEX idx_{tabla}_sin_dueno ON {tabla}({', '.join(unicas)}) WHERE user_id IS NULL;")


def _migracion_datos_por_usuario(conn: sqlite3.Connection) -> None:
    """Agrega la cuenta dueña a las tablas raíz, vuelve por cuenta sus unicidades y crea los tokens MCP."""
    for tabla, ddl_nueva, columnas, unicas in _RECONSTRUIDAS_EN_LA_3:
        _reconstruir_con_dueno(conn, tabla, ddl_nueva, columnas, unicas)
    for tabla, al_borrar in _AMPLIADAS_EN_LA_3:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN user_id INTEGER REFERENCES usuarios(id) ON DELETE {al_borrar};")
    tablas_raiz = [tabla for tabla, *_ in _RECONSTRUIDAS_EN_LA_3] + [tabla for tabla, _ in _AMPLIADAS_EN_LA_3]
    for tabla in tablas_raiz:
        conn.execute(f"CREATE INDEX idx_{tabla}_user ON {tabla}(user_id);")

    conn.execute(DDL_MCP_TOKENS)
    conn.execute("CREATE INDEX idx_mcp_tokens_usuario ON mcp_tokens(usuario_id);")

    heredero = conn.execute("SELECT MIN(id) FROM usuarios WHERE rol = 'admin' AND activo = 1;").fetchone()[0]
    if heredero is not None:
        for tabla in tablas_raiz:
            conn.execute(f"UPDATE {tabla} SET user_id = ? WHERE user_id IS NULL;", (heredero,))


def _migracion_secretos_y_ajustes(conn: sqlite3.Connection) -> None:
    """Crea el almacén de secretos cifrados y el de ajustes, los dos por cuenta."""
    conn.execute(DDL_SECRETOS_USUARIO)
    conn.execute(DDL_AJUSTES_USUARIO)


_Funcion = Callable[[sqlite3.Connection], None]
# (número, nombre, función) o (número, nombre, función, sin_claves_foraneas)
Migracion = tuple[int, str, _Funcion] | tuple[int, str, _Funcion, bool]

def _migracion_sincronizacion_libros(conn: sqlite3.Connection) -> None:
    """Agrega soporte para Google Play Libros y fuentes de sincronización a libros_lectura."""
    conn.execute("ALTER TABLE libros_lectura ADD COLUMN google_books_id TEXT DEFAULT NULL;")
    conn.execute("ALTER TABLE libros_lectura ADD COLUMN fuente_sincronizacion TEXT DEFAULT 'manual';")
    conn.execute("ALTER TABLE libros_lectura ADD COLUMN ultima_sincronizacion TIMESTAMP DEFAULT NULL;")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_libros_lectura_google_books ON libros_lectura(user_id, google_books_id);")


def _migracion_sincronizacion_cursos(conn: sqlite3.Connection) -> None:
    """Agrega soporte para sincronización externa y webhooks a cursos_externos."""
    conn.execute("ALTER TABLE cursos_externos ADD COLUMN external_id TEXT DEFAULT NULL;")
    conn.execute("ALTER TABLE cursos_externos ADD COLUMN fuente_sincronizacion TEXT DEFAULT 'manual';")
    conn.execute("ALTER TABLE cursos_externos ADD COLUMN ultima_sincronizacion TIMESTAMP DEFAULT NULL;")
    conn.execute("ALTER TABLE cursos_externos ADD COLUMN sync_config_json TEXT DEFAULT '{}';")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cursos_externos_sync ON cursos_externos(plataforma_id, external_id);")


# Lo que guardaban los conectores de Google Drive y OneDrive (048): la lista queda fija aunque el código cambie.
# `gdrive_cliente` no está: es el cliente OAuth propio de Google que sigue usando Google Books.
_SECRETOS_DE_LA_NUBE = ("gdrive_autorizacion", "onedrive_cliente", "onedrive_autorizacion")
_AJUSTES_DE_LA_NUBE = (
    "conectores",
    "gdrive_carpeta_raiz",
    "gdrive_autorizacion_rechazada",
    "onedrive_carpeta_raiz",
    "onedrive_autorizacion_rechazada",
)


def _migracion_materiales(conn: sqlite3.Connection) -> None:
    """Crea la tabla de materiales subidos y borra las autorizaciones y ajustes de Drive y OneDrive de cada cuenta."""
    # Se importa acá: `core.secretos` importa `aulento.db`, que carga este módulo
    from aulento.core.secretos import quitar_de_la_cuenta_sin_confirmar

    conn.execute(DDL_MATERIALES)
    conn.execute("CREATE INDEX idx_materiales_user ON materiales(user_id);")
    for (cuenta,) in conn.execute("SELECT id FROM usuarios;").fetchall():
        quitar_de_la_cuenta_sin_confirmar(conn, cuenta, _SECRETOS_DE_LA_NUBE, _AJUSTES_DE_LA_NUBE)



def _migracion_reservada(conn: sqlite3.Connection) -> None:
    """Sin cambios. La 8 la usó un borrador de la 049 para tablas de la nube, que ahora crea su extensión
    (ADR 017); queda reservada para que las bases que ya la aplicaron sigan en la misma numeración."""


def _migracion_reservada_de_la_demo(conn: sqlite3.Connection) -> None:
    """Sin cambios. Creaba la tabla de la siembra de la demo (054), que desde la 051 crea la extensión de las
    cuentas; queda reservada para que las bases que ya la aplicaron sigan en la misma numeración."""


def _migracion_hashes_indexados(conn: sqlite3.Connection) -> None:
    """Crea la tabla con la huella de lo que «Indexar todo» ya indexó de cada cuenta (feature 059, R3)."""
    conn.execute(
        """
        CREATE TABLE hashes_indexados (
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            hash TEXT NOT NULL,
            indexado_en TEXT NOT NULL,
            PRIMARY KEY (user_id, source_type, source_id),
            FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );
        """
    )


def _migracion_tokens_de_alcance(conn: sqlite3.Connection) -> None:
    """Crea la tabla de tokens de alcance limitado: feed del calendario y webhook de libros (feature 061, R2 y R3)."""
    conn.execute(
        """
        CREATE TABLE tokens_de_alcance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            alcance TEXT NOT NULL CHECK(alcance IN ('calendario', 'libros')),
            token_hash TEXT NOT NULL UNIQUE,
            creado_en TEXT NOT NULL,
            revocado_en TEXT,
            FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX idx_tokens_de_alcance_cuenta ON tokens_de_alcance(user_id, alcance);")


def _migracion_libros_autor_y_avances(conn: sqlite3.Connection) -> None:
    """Repara páginas que superan el total, agrega autor a libros y crea la tabla avances_de_lectura."""
    conn.execute(
        """
        UPDATE libros_lectura
        SET pagina_actual = total_paginas
        WHERE total_paginas IS NOT NULL AND pagina_actual > total_paginas;
        """
    )
    conn.execute("ALTER TABLE libros_lectura ADD COLUMN autor TEXT DEFAULT NULL;")
    conn.execute(
        """
        CREATE TABLE avances_de_lectura (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            libro_id INTEGER REFERENCES libros_lectura(id) ON DELETE SET NULL,
            paginas INTEGER NOT NULL CHECK(paginas > 0),
            registrado_en TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX idx_avances_de_lectura_cuenta ON avances_de_lectura(user_id, registrado_en);")


MIGRACIONES: list[Migracion] = [
    (1, "esquema_base", _migracion_esquema_base),
    (2, "cuentas_y_sesiones", _migracion_cuentas),
    (3, "datos_por_usuario", _migracion_datos_por_usuario, True),
    (4, "secretos_y_ajustes", _migracion_secretos_y_ajustes),
    (5, "sincronizacion_libros", _migracion_sincronizacion_libros),
    (6, "sincronizacion_cursos", _migracion_sincronizacion_cursos),
    (7, "materiales", _migracion_materiales),
    (8, "reservada", _migracion_reservada),
    (9, "demo_siembra", _migracion_reservada_de_la_demo),
    (10, "hashes_indexados", _migracion_hashes_indexados),
    (11, "tokens_de_alcance", _migracion_tokens_de_alcance),
    (12, "libros_autor_y_avances", _migracion_libros_autor_y_avances),
]


def version_actual(conn: sqlite3.Connection) -> int:
    """Retorna la versión del esquema guardada en la base."""
    return int(conn.execute("PRAGMA user_version;").fetchone()[0])


def ultima_version() -> int:
    """Retorna la versión del esquema que espera este código."""
    return MIGRACIONES[-1][0]


def _archivo_de(conn: sqlite3.Connection) -> Path | None:
    """Retorna el archivo de la base principal, o None si vive en memoria."""
    for fila in conn.execute("PRAGMA database_list;").fetchall():
        if fila[1] == "main":
            return Path(fila[2]) if fila[2] else None
    return None


def _tiene_tablas(conn: sqlite3.Connection) -> bool:
    """Indica si la base ya tiene alguna tabla propia."""
    fila = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%';"
    ).fetchone()
    return fila[0] > 0


def _respaldar(conn: sqlite3.Connection, version: int) -> Path | None:
    """Copia la base a un archivo vecino antes de migrarla; None si no corresponde respaldo."""
    archivo = _archivo_de(conn)
    if archivo is None or not _tiene_tablas(conn):
        return None
    marca = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    destino = archivo.with_name(f"{archivo.name}.respaldo-v{version}-{marca}")
    copia = sqlite3.connect(str(destino))
    try:
        conn.backup(copia)
    finally:
        copia.close()
    return destino


def _claves_foraneas_activas(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute("PRAGMA foreign_keys;").fetchone()[0])


def _aplicar(conn: sqlite3.Connection, numero: int, nombre: str, funcion: _Funcion, sin_claves_foraneas: bool) -> None:
    """Aplica una migración en su propia transacción; si falla, la revierte entera.

    Con `sin_claves_foraneas` la migración corre con las claves apagadas (para poder reconstruir una tabla
    sin borrar en cascada a sus hijas), se comprueba que no quede ninguna referencia rota antes de confirmar
    y las claves vuelven a encenderse pase lo que pase.
    """
    apagar = sin_claves_foraneas and _claves_foraneas_activas(conn)
    try:
        if apagar:
            # Dentro de una transacción este PRAGMA no hace nada: por eso va antes del BEGIN y se comprueba
            conn.execute("PRAGMA foreign_keys = OFF;")
            if _claves_foraneas_activas(conn):
                raise RuntimeError("No se pudieron apagar las claves foráneas para migrar.")
        conn.execute("BEGIN IMMEDIATE;")
        # Otro proceso pudo aplicarla mientras se esperaba el turno de escritura
        if version_actual(conn) < numero:
            funcion(conn)
            if sin_claves_foraneas:
                rotas = conn.execute("PRAGMA foreign_key_check;").fetchall()
                if rotas:
                    tablas = ", ".join(sorted({fila[0] for fila in rotas}))
                    raise RuntimeError(f"Quedarían {len(rotas)} referencias rotas en: {tablas}.")
            conn.execute(f"PRAGMA user_version = {int(numero)};")
        conn.commit()
    except Exception as error:
        if conn.in_transaction:
            conn.rollback()
        raise ErrorDeMigracion(numero, nombre) from error
    finally:
        if apagar:
            if conn.in_transaction:
                conn.rollback()
            conn.execute("PRAGMA foreign_keys = ON;")


def migrar(conn: sqlite3.Connection, respaldo: bool = True) -> int:
    """Aplica en orden las migraciones pendientes y retorna la versión en la que quedó la base."""
    version = version_actual(conn)
    pendientes = [m for m in MIGRACIONES if m[0] > version]
    if not pendientes:
        return version

    if conn.in_transaction:
        conn.commit()
    if respaldo:
        _respaldar(conn, version)

    for numero, nombre, funcion, *opciones in pendientes:
        _aplicar(conn, numero, nombre, funcion, sin_claves_foraneas=bool(opciones and opciones[0]))
    return version_actual(conn)
