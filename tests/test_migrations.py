"""Pruebas de las migraciones numeradas (032 R1), la del dueño por fila (033 R1, R2) y la de secretos (034 R2)."""

import hashlib
import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from aulento.db import migrations
from aulento.db.connection import get_connection
from aulento.db.migrations import (
    MIGRACIONES,
    ErrorDeMigracion,
    migrar,
    version_actual,
)
from aulento.db.schema import (
    PLATAFORMAS_SEMILLA,
    aplicar_esquema_base,
    create_schema,
    init_db,
)

ULTIMA_VERSION = MIGRACIONES[-1][0]
TABLAS_DE_CUENTAS_DEL_CORE = {"usuarios"}
# Las creaba la migración 2 hasta la 051; ahora son de la extensión de las cuentas y las bases de antes las conservan
TABLAS_DE_CUENTAS_ANTERIORES = {"sesiones", "invitaciones", "intentos_login"}
# Cómo quedaban las cuentas en una base de la 032
TABLAS_DE_CUENTAS = TABLAS_DE_CUENTAS_DEL_CORE | TABLAS_DE_CUENTAS_ANTERIORES
TABLAS_DE_LA_MIGRACION_4 = {"secretos_usuario", "ajustes_usuario"}
TABLAS_DE_LA_MIGRACION_7 = {"materiales"}
TABLAS_DE_LA_MIGRACION_9: set[str] = set()  # reservada desde la 051: la siembra de la demo es de la nube
TABLAS_DE_LA_MIGRACION_10 = {"hashes_indexados"}
TABLAS_DE_LA_MIGRACION_11 = {"tokens_de_alcance"}
TABLAS_POSTERIORES_AL_ESQUEMA_BASE = (
    TABLAS_DE_CUENTAS_DEL_CORE | {"mcp_tokens"} | TABLAS_DE_LA_MIGRACION_4 | TABLAS_DE_LA_MIGRACION_7 | TABLAS_DE_LA_MIGRACION_9 | TABLAS_DE_LA_MIGRACION_10 | TABLAS_DE_LA_MIGRACION_11
)
TABLAS_CON_DUENO = {
    "plataformas",
    "libros_lectura",
    "bloques_horarios",
    "fsrs_items",
    "sesiones_estudio",
    "rutas_aprendizaje",
    "api_usage_logs",
    "mcp_audit_logs",
}
TABLAS_DE_ESTUDIO = TABLAS_CON_DUENO | {
    "cursos_externos",
    "fsrs_review_logs",
    "ruta_modulos",
    "ruta_temas",
    "ruta_clases",
    "ruta_clases_versiones",
    "ruta_prelaciones",
    "roadmap_topic_retention",
    "roadmap_topic_reviews",
}


def _tablas(conn: sqlite3.Connection) -> set[str]:
    filas = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%';")
    return {fila[0] for fila in filas.fetchall()}


def _contenido(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Todas las filas de todas las tablas, columna por columna, para comparar antes y después.

    La cuenta dueña queda afuera: es la columna que agrega la migración 3 y se comprueba aparte.
    """
    contenido = {}
    for tabla in sorted(_tablas(conn)):
        # Por `rowid` y no por `id`: las tablas de la migración 4 tienen clave compuesta, sin `id`
        cursor = conn.execute(f"SELECT * FROM {tabla} ORDER BY rowid;")
        columnas = [columna[0] for columna in cursor.description]
        contenido[tabla] = [
            {columna: valor for columna, valor in zip(columnas, fila, strict=True) if columna not in ("user_id", "google_books_id", "fuente_sincronizacion", "ultima_sincronizacion", "external_id", "sync_config_json")}
            for fila in cursor.fetchall()
        ]
    return contenido


def _duenos(conn: sqlite3.Connection) -> dict[str, set]:
    """La cuenta dueña de las filas de cada tabla raíz."""
    return {
        tabla: {fila[0] for fila in conn.execute(f"SELECT user_id FROM {tabla};").fetchall()}
        for tabla in sorted(TABLAS_CON_DUENO)
    }


DDL_SESIONES_DE_LA_032 = """
CREATE TABLE sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    creada_en TEXT NOT NULL,
    ultimo_uso TEXT NOT NULL,
    expira_en TEXT NOT NULL,
    ip TEXT,
    agente TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);
"""

DDL_INVITACIONES_DE_LA_032 = """
CREATE TABLE invitaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_hash TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL CHECK(tipo IN ('registro', 'restablecer')),
    rol TEXT CHECK(rol IS NULL OR rol IN ('admin', 'usuario')),
    usuario_id INTEGER,
    creado_por INTEGER,
    creada_en TEXT NOT NULL,
    expira_en TEXT NOT NULL,
    usada_en TEXT,
    inicial INTEGER NOT NULL DEFAULT 0 CHECK(inicial IN (0, 1)),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL
);
"""

DDL_INTENTOS_LOGIN_DE_LA_032 = """
CREATE TABLE intentos_login (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario TEXT NOT NULL COLLATE NOCASE,
    ip TEXT,
    momento TEXT NOT NULL,
    exito INTEGER NOT NULL CHECK(exito IN (0, 1))
);
"""


def _crear_las_tablas_de_cuentas_anteriores(conn: sqlite3.Connection) -> None:
    """Lo que la migración 2 creaba además de `usuarios` hasta la 051, con su DDL de entonces."""
    conn.execute(DDL_SESIONES_DE_LA_032)
    conn.execute(DDL_INVITACIONES_DE_LA_032)
    conn.execute(DDL_INTENTOS_LOGIN_DE_LA_032)
    conn.execute("CREATE INDEX idx_sesiones_usuario ON sesiones(usuario_id);")
    conn.execute("CREATE INDEX idx_invitaciones_usuario ON invitaciones(usuario_id);")
    conn.execute("CREATE INDEX idx_intentos_login_nombre ON intentos_login(nombre_usuario, momento);")
    conn.execute("CREATE INDEX idx_intentos_login_ip ON intentos_login(ip, momento);")
    conn.commit()


def _migrar_hasta(conn: sqlite3.Connection, version: int) -> None:
    """Aplica solo las primeras `version` migraciones, como las aplicaba el sistema en esa versión."""
    for numero, nombre, funcion, *opciones in MIGRACIONES[:version]:
        migrations._aplicar(conn, numero, nombre, funcion, sin_claves_foraneas=bool(opciones and opciones[0]))
    assert version_actual(conn) == version


def _sembrar_plataformas(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO plataformas (nombre, url_acceso, icono_color) VALUES (:nombre, :url_acceso, :icono_color);",
        PLATAFORMAS_SEMILLA,
    )
    conn.commit()


DATOS_DE_ESTUDIO = """
INSERT INTO plataformas (id, nombre, url_acceso, icono_color) VALUES
    (1, 'Coursera', 'https://www.coursera.org', 'cyan'), (2, 'Humai', 'https://humai.com.ar', 'green');
INSERT INTO cursos_externos (id, plataforma_id, nombre_curso, url_aula, progreso_pct, estado, ruta_local) VALUES
    (1, 1, 'ML Specialization', 'https://example.com/ml', 42.5, 'en_curso', 'C:/cursos/ml'),
    (2, 2, 'Deep Learning', 'https://example.com/dl', 100.0, 'completado', NULL);
INSERT INTO libros_lectura (id, titulo, capitulo_actual, total_capitulos, pagina_actual, total_paginas) VALUES
    (1, 'AI Engineering', 3, 10, 120, 500);
INSERT INTO bloques_horarios (id, dia_semana, hora_inicio, hora_fin, tipo, descripcion) VALUES
    (1, 1, '09:00', '10:30', 'curso', 'Bloque de la mañana');
INSERT INTO sesiones_estudio (id, bloque_id, duracion_minutos, tipo, notas) VALUES
    (1, 1, 50, 'curso', 'con bloque'), (2, NULL, 25, 'lectura', 'suelta');
INSERT INTO fsrs_items
    (id, categoria, item_pregunta, respuesta_esperada, contexto_uso, state, step, stability, difficulty,
     due, last_review, reps, lapses) VALUES
    (1, 'ingles_tecnico', 'throughput', 'caudal de procesamiento', 'en una revisión', 2, 0, 3.25, 5.5,
     '2026-02-01T00:00:00+00:00', '2026-01-20T00:00:00+00:00', 4, 1),
    (2, 'roadmap_1', 'backpressure', 'contrapresión', NULL, 1, 0, NULL, NULL, NULL, NULL, 0, 0);
INSERT INTO fsrs_review_logs (id, card_id, rating, review_datetime, elapsed_days, scheduled_days, state) VALUES
    (1, 1, 3, '2026-01-20T00:00:00+00:00', 2.0, 4.0, 2), (2, 1, 1, '2026-01-10T00:00:00+00:00', 0.0, 1.0, 1),
    (3, 2, 4, '2026-01-21T00:00:00+00:00', 0.0, 3.0, 1);
INSERT INTO rutas_aprendizaje
    (id, titulo, descripcion, categoria, nivel_objetivo, enfoque_estudio, progreso_pct, metadata_json) VALUES
    (1, 'Data Engineering', 'de cero a senior', 'data_ai', 'Senior', 'academico', 33.3, '{"origen": "plantilla"}'),
    (2, 'MLOps', NULL, 'cloud', 'Mid', 'profesional', 0.0, '{}');
INSERT INTO ruta_modulos (id, ruta_id, titulo, orden) VALUES (1, 1, 'Fundamentos', 1), (2, 2, 'Despliegue', 1);
INSERT INTO ruta_temas (id, modulo_id, titulo, orden, estado) VALUES
    (1, 1, 'SQL', 1, 'completado'), (2, 1, 'Modelado', 2, 'en_progreso'),
    (3, 2, 'Contenedores', 1, 'pendiente'), (4, 2, 'CI/CD', 2, 'pendiente');
INSERT INTO ruta_clases (id, tema_id, titulo, contenido_markdown, vault_path, vault_hash) VALUES
    (1, 1, 'Clase de SQL', '# SQL', 'rutas/sql.md', 'abc123'), (2, 3, 'Clase de contenedores', '# Docker', NULL, NULL);
INSERT INTO ruta_clases_versiones (id, tema_id, titulo, contenido_markdown) VALUES
    (1, 1, 'Clase de SQL (v1)', '# SQL viejo'), (2, 3, 'Clase de contenedores (v1)', '# Docker viejo');
INSERT INTO ruta_prelaciones (id, ruta_id, tema_origen_id, tema_destino_id, tipo) VALUES
    (1, 1, 1, 2, 'estricta'), (2, 2, 3, 4, 'recomendada');
INSERT INTO roadmap_topic_retention (id, tema_id, due_date, stability, reps) VALUES
    (1, 1, '2026-02-01T00:00:00+00:00', 4.5, 2), (2, 3, '2026-02-03T00:00:00+00:00', 2.0, 0);
INSERT INTO roadmap_topic_reviews (id, retention_id, rating, scheduled_days, elapsed_days, notas) VALUES
    (1, 1, 3, 4, 2, 'bien'), (2, 2, 2, 3, 0, NULL);
INSERT INTO api_usage_logs (id, model, endpoint_tipo, total_tokens, estimated_cost_usd) VALUES
    (1, 'gemini-2.5-flash', 'lesson', 1500, 0.0021);
INSERT INTO mcp_audit_logs (id, tool_name, params_json, transport, client_ip, status) VALUES
    (1, 'list_courses', '{"limit": 5}', 'http', '127.0.0.1', 'success');
"""


def _cuenta(conn: sqlite3.Connection, nombre: str, rol: str = "usuario", activo: int = 1) -> int:
    cursor = conn.execute(
        "INSERT INTO usuarios (nombre_usuario, contrasena_hash, rol, activo, creado_en) "
        "VALUES (?, 'x', ?, ?, '2026-01-01');",
        (nombre, rol, activo),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _cargar_datos_de_cuentas(conn: sqlite3.Connection) -> int:
    """Filas en las cuatro tablas de cuentas; retorna el id del único administrador activo."""
    admin = _cuenta(conn, "jefa", rol="admin")
    conn.execute(
        "INSERT INTO sesiones (usuario_id, token_hash, creada_en, ultimo_uso, expira_en) "
        "VALUES (?, 'huella-sesion', '2026-01-01', '2026-01-01', '2026-01-15');",
        (admin,),
    )
    conn.execute(
        "INSERT INTO invitaciones (codigo_hash, tipo, rol, creado_por, creada_en, expira_en) "
        "VALUES ('huella-codigo', 'registro', 'usuario', ?, '2026-01-01', '2026-01-08');",
        (admin,),
    )
    conn.execute(
        "INSERT INTO intentos_login (nombre_usuario, ip, momento, exito) VALUES ('jefa', '10.0.0.1', '2026-01-01', 1);"
    )
    conn.commit()
    return admin


def _base_en_version_2(ruta, con_cuentas: bool = False) -> sqlite3.Connection:
    """Base como la dejaba la 032: filas en las 17 tablas de estudio y, si se pide, en las cuatro de cuentas.

    Lleva dos rutas con su árbol completo y dos tarjetas con repasos, para ver qué arrastra cada borrado.
    """
    conn = get_connection(ruta)
    _migrar_hasta(conn, 2)
    _crear_las_tablas_de_cuentas_anteriores(conn)
    conn.executescript(DATOS_DE_ESTUDIO)
    conn.commit()
    if con_cuentas:
        _cargar_datos_de_cuentas(conn)
    return conn


def _claves_foraneas(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA foreign_keys;").fetchone()[0]


def _contar(conn: sqlite3.Connection, tabla: str, condicion: str = "1 = 1") -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE {condicion};").fetchone()[0]


def _ids(conn: sqlite3.Connection, tabla: str) -> list[int]:
    return [fila[0] for fila in conn.execute(f"SELECT id FROM {tabla} ORDER BY id;").fetchall()]


def _esquema_anterior(conn: sqlite3.Connection) -> None:
    """Deja la base como la dejaba el sistema antes de las migraciones numeradas: tablas base y versión 0."""
    aplicar_esquema_base(conn)
    conn.commit()


def _huella_del_esquema(conn: sqlite3.Connection) -> str:
    """Huella de todas las definiciones de la base, sin depender de los espacios del DDL."""
    filas = conn.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name;"
    ).fetchall()
    texto = "\n".join(f"{tipo}|{nombre}|{' '.join((sql or '').split())}" for tipo, nombre, sql in filas)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _base_anterior_con_datos(ruta) -> sqlite3.Connection:
    """Base con el esquema previo a las migraciones (versión 0) y filas en varias tablas."""
    conn = get_connection(ruta)
    _esquema_anterior(conn)
    _sembrar_plataformas(conn)
    conn.execute(
        "INSERT INTO cursos_externos (plataforma_id, nombre_curso, url_aula, progreso_pct) "
        "VALUES (1, 'Curso previo', 'https://example.com/aula', 42.5);"
    )
    conn.execute("INSERT INTO libros_lectura (titulo, capitulo_actual, total_capitulos) VALUES ('AI Engineering', 3, 10);")
    conn.execute("INSERT INTO rutas_aprendizaje (titulo, descripcion) VALUES ('Ruta previa', 'antes de migrar');")
    conn.execute("INSERT INTO ruta_modulos (ruta_id, titulo) VALUES (1, 'Módulo previo');")
    conn.execute(
        "INSERT INTO fsrs_items (item_pregunta, respuesta_esperada) VALUES ('throughput', 'caudal de procesamiento');"
    )
    conn.commit()
    return conn


def _respaldos(carpeta) -> list:
    return sorted(carpeta.glob("*.respaldo-*"))


def _migracion_rota(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE tabla_a_medias (id INTEGER PRIMARY KEY);")
    conn.execute("INSERT INTO plataformas (nombre, url_acceso) VALUES ('A medias', 'https://example.com');")
    raise RuntimeError("fallo provocado a mitad de la migración")


@pytest.fixture
def con_migracion_rota(monkeypatch):
    """Agrega una migración posterior a la última que falla después de escribir."""
    numero = ULTIMA_VERSION + 1
    monkeypatch.setattr(migrations, "MIGRACIONES", [*MIGRACIONES, (numero, "rota_a_proposito", _migracion_rota)])
    return numero


def test_base_nueva_queda_en_la_ultima_version():
    conn = get_connection(":memory:")
    assert version_actual(conn) == 0

    init_db(conn)

    assert version_actual(conn) == ULTIMA_VERSION
    assert [m[0] for m in MIGRACIONES] == list(range(1, ULTIMA_VERSION + 1))
    assert TABLAS_DE_CUENTAS_DEL_CORE <= _tablas(conn)
    assert not TABLAS_DE_CUENTAS_ANTERIORES & _tablas(conn)
    assert {"plataformas", "cursos_externos", "ruta_clases"} <= _tablas(conn)
    assert not conn.in_transaction
    assert conn.isolation_level == ""
    conn.close()


def test_base_anterior_migra_conservando_cada_fila(tmp_path):
    conn = _base_anterior_con_datos(tmp_path / "anterior.db")
    assert version_actual(conn) == 0
    antes = _contenido(conn)
    assert sum(len(filas) for filas in antes.values()) >= 9

    init_db(conn)

    despues = _contenido(conn)
    assert version_actual(conn) == ULTIMA_VERSION
    assert {tabla: despues[tabla] for tabla in antes} == antes
    assert set(despues) - set(antes) == TABLAS_POSTERIORES_AL_ESQUEMA_BASE
    conn.close()

    # La versión y los datos quedan en el archivo, no solo en la conexión que migró
    otra = get_connection(tmp_path / "anterior.db")
    assert version_actual(otra) == ULTIMA_VERSION
    assert {tabla: _contenido(otra)[tabla] for tabla in antes} == antes
    otra.close()


def test_volver_a_inicializar_no_reaplica_nada(tmp_path, monkeypatch):
    conn = _base_anterior_con_datos(tmp_path / "repetida.db")
    init_db(conn)
    respaldos = _respaldos(tmp_path)
    conn.execute("INSERT INTO usuarios (nombre_usuario, contrasena_hash, creado_en) VALUES ('ana', 'x', '2026-01-01');")
    conn.commit()
    cambios = conn.total_changes

    def _no_debe_correr(_conn):
        raise AssertionError("una migración ya aplicada volvió a ejecutarse")

    monkeypatch.setattr(migrations, "MIGRACIONES", [(n, nombre, _no_debe_correr) for n, nombre, *_ in MIGRACIONES])

    assert migrar(conn) == ULTIMA_VERSION
    init_db(conn)

    assert conn.total_changes == cambios
    assert _respaldos(tmp_path) == respaldos
    assert conn.execute("SELECT COUNT(*) FROM usuarios;").fetchone()[0] == 1
    conn.close()


def test_base_en_archivo_con_datos_deja_respaldo_con_los_datos_previos(tmp_path):
    conn = _base_anterior_con_datos(tmp_path / "con_datos.db")
    antes = _contenido(conn)

    init_db(conn)
    conn.close()

    respaldos = _respaldos(tmp_path)
    assert len(respaldos) == 1
    assert respaldos[0].name.startswith("con_datos.db.respaldo-v0-")
    copia = sqlite3.connect(str(respaldos[0]))
    try:
        assert copia.execute("PRAGMA user_version;").fetchone()[0] == 0
        assert _contenido(copia) == antes
        assert not TABLAS_POSTERIORES_AL_ESQUEMA_BASE & _tablas(copia)
    finally:
        copia.close()


def test_base_vacia_o_en_memoria_no_deja_respaldo(tmp_path, monkeypatch):
    vacia = get_connection(tmp_path / "vacia.db")
    init_db(vacia)
    vacia.close()
    assert _respaldos(tmp_path) == []

    monkeypatch.chdir(tmp_path)
    memoria = get_connection(":memory:")
    _esquema_anterior(memoria)
    _sembrar_plataformas(memoria)
    assert migrations._respaldar(memoria, 0) is None
    init_db(memoria)
    memoria.close()
    assert _respaldos(tmp_path) == []


def test_respaldo_desactivado_no_copia(tmp_path):
    conn = _base_anterior_con_datos(tmp_path / "sin_copia.db")
    assert migrar(conn, respaldo=False) == ULTIMA_VERSION
    conn.close()
    assert _respaldos(tmp_path) == []


def test_migracion_que_falla_revierte_y_no_avanza_la_version(tmp_path, con_migracion_rota):
    conn = get_connection(tmp_path / "rota.db")

    with pytest.raises(ErrorDeMigracion) as fallo:
        init_db(conn)

    assert fallo.value.version == con_migracion_rota
    assert fallo.value.nombre == "rota_a_proposito"
    assert "rota_a_proposito" in str(fallo.value)
    assert isinstance(fallo.value.__cause__, RuntimeError)
    # Las anteriores quedaron aplicadas; la rota no dejó nada
    assert version_actual(conn) == ULTIMA_VERSION
    assert "tabla_a_medias" not in _tablas(conn)
    assert conn.execute("SELECT COUNT(*) FROM plataformas WHERE nombre = 'A medias';").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()

    otra = get_connection(tmp_path / "rota.db")
    assert version_actual(otra) == ULTIMA_VERSION
    assert "tabla_a_medias" not in _tablas(otra)
    otra.close()


def test_el_arranque_del_servidor_no_traga_el_error_de_migracion(con_migracion_rota, caplog):
    from aulento.web.app import create_app

    registro = caplog.at_level(logging.CRITICAL, logger="aulento.web.app")
    with registro, pytest.raises(ErrorDeMigracion) as fallo, TestClient(create_app()):
        pass

    assert fallo.value.nombre == "rota_a_proposito"
    assert "rota_a_proposito" in caplog.text


def test_create_schema_deja_la_base_en_la_ultima_version(tmp_path):
    conn = get_connection(tmp_path / "por_create_schema.db")

    create_schema(conn)

    assert version_actual(conn) == ULTIMA_VERSION
    assert "usuarios" in _tablas(conn)
    conn.close()


def test_el_esquema_de_la_migracion_1_esta_congelado():
    """Una base ya migrada no vuelve a pasar por la migración 1: lo nuevo va en una migración nueva."""
    conn = get_connection(":memory:")
    _esquema_anterior(conn)

    assert _huella_del_esquema(conn) == "13fc56df402e7c56b3c9464d50cd18dd5550e51604516a8769e3a00662440ec6", (
        "Cambió el esquema base (db/schema.py). Las bases en uso no reciben ese cambio: "
        "revertilo y agregá una migración nueva en db/migrations.py."
    )
    conn.close()


# --- Dueño por fila (033 R1, R2) ---


def test_base_en_version_2_con_filas_en_todas_las_tablas_migra_conservando_cada_fila(tmp_path):
    conn = _base_en_version_2(tmp_path / "v2.db", con_cuentas=True)
    antes = _contenido(conn)
    assert set(antes) == TABLAS_DE_ESTUDIO | TABLAS_DE_CUENTAS
    assert all(antes.values()), "el test tiene que cargar filas en todas las tablas"

    assert migrar(conn) == ULTIMA_VERSION

    despues = _contenido(conn)
    assert {tabla: despues[tabla] for tabla in antes} == antes
    assert set(despues) - set(antes) == {"mcp_tokens"} | TABLAS_DE_LA_MIGRACION_4 | TABLAS_DE_LA_MIGRACION_7 | TABLAS_DE_LA_MIGRACION_9 | TABLAS_DE_LA_MIGRACION_10 | TABLAS_DE_LA_MIGRACION_11
    assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []
    assert _claves_foraneas(conn) == 1
    assert not conn.in_transaction
    conn.close()

    # Lo migrado quedó en el archivo, no solo en la conexión que migró
    otra = get_connection(tmp_path / "v2.db")
    assert version_actual(otra) == ULTIMA_VERSION
    assert {tabla: _contenido(otra)[tabla] for tabla in antes} == antes
    assert otra.execute("PRAGMA foreign_key_check;").fetchall() == []
    otra.close()


def test_tras_migrar_las_tablas_hijas_siguen_colgando_de_las_reconstruidas(tmp_path):
    conn = _base_en_version_2(tmp_path / "cascada.db")
    migrar(conn)

    for hija, padre in [
        ("cursos_externos", "plataformas"),
        ("ruta_modulos", "rutas_aprendizaje"),
        ("ruta_prelaciones", "rutas_aprendizaje"),
        ("fsrs_review_logs", "fsrs_items"),
    ]:
        assert padre in {fila["table"] for fila in conn.execute(f"PRAGMA foreign_key_list({hija});").fetchall()}

    # Las claves se exigen: nada puede colgar de una fila que no existe
    for alta in (
        "INSERT INTO cursos_externos (plataforma_id, nombre_curso, url_aula) VALUES (99, 'x', 'https://x');",
        "INSERT INTO ruta_modulos (ruta_id, titulo) VALUES (99, 'x');",
        "INSERT INTO fsrs_review_logs (card_id, rating, review_datetime, state) VALUES (99, 3, '2026-01-01', 1);",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(alta)
        conn.rollback()

    # Borrar una ruta se lleva todo su árbol y deja intacto el de la otra
    conn.execute("DELETE FROM rutas_aprendizaje WHERE id = 1;")
    conn.commit()
    assert _ids(conn, "ruta_modulos") == [2]
    assert _ids(conn, "ruta_temas") == [3, 4]
    for tabla in (
        "ruta_clases",
        "ruta_clases_versiones",
        "ruta_prelaciones",
        "roadmap_topic_retention",
        "roadmap_topic_reviews",
    ):
        assert _ids(conn, tabla) == [2], tabla

    # Borrar una tarjeta se lleva sus repasos; borrar una plataforma, sus cursos
    conn.execute("DELETE FROM fsrs_items WHERE id = 1;")
    conn.execute("DELETE FROM plataformas WHERE id = 1;")
    conn.commit()
    assert _ids(conn, "fsrs_review_logs") == [3]
    assert _ids(conn, "cursos_externos") == [2]
    assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []
    conn.close()


def test_los_ids_borrados_antes_de_migrar_no_se_vuelven_a_entregar(tmp_path):
    conn = _base_en_version_2(tmp_path / "secuencia.db")
    # El mazo `roadmap_<id>` nombra a la ruta por su id: reusar un id borrado le daría tarjetas ajenas
    conn.execute("DELETE FROM rutas_aprendizaje WHERE id = 2;")
    conn.execute("DELETE FROM fsrs_items;")
    conn.commit()

    migrar(conn)

    ruta = conn.execute("INSERT INTO rutas_aprendizaje (titulo) VALUES ('Nueva');").lastrowid
    tarjeta = conn.execute("INSERT INTO fsrs_items (item_pregunta, respuesta_esperada) VALUES ('q', 'a');").lastrowid
    plataforma = conn.execute("INSERT INTO plataformas (nombre, url_acceso) VALUES ('Nueva', 'https://x');").lastrowid
    assert (ruta, tarjeta, plataforma) == (3, 3, 3)
    conn.close()


def test_una_base_que_recibio_columnas_por_alter_migra_conservandolas(tmp_path):
    """Las bases más viejas tienen `enfoque_estudio` al final de la tabla: la copia va por nombre de columna."""
    conn = get_connection(tmp_path / "vieja.db")
    conn.execute(
        """
        CREATE TABLE rutas_aprendizaje (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL UNIQUE,
            descripcion TEXT,
            categoria TEXT DEFAULT 'data_ai',
            nivel_objetivo TEXT DEFAULT 'Senior',
            progreso_pct REAL DEFAULT 0.0 CHECK(progreso_pct >= 0.0 AND progreso_pct <= 100.0),
            metadata_json TEXT DEFAULT '{}',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _esquema_anterior(conn)
    conn.execute(
        "INSERT INTO rutas_aprendizaje (titulo, descripcion, enfoque_estudio, progreso_pct) "
        "VALUES ('Ruta vieja', 'd', 'academico', 12.5);"
    )
    conn.commit()
    antes = _contenido(conn)["rutas_aprendizaje"]
    assert list(antes[0])[-1] == "enfoque_estudio"
    assert antes[0]["enfoque_estudio"] == "academico"

    migrar(conn)

    assert _contenido(conn)["rutas_aprendizaje"] == antes
    nueva = get_connection(":memory:")
    migrar(nueva)
    assert _huella_del_esquema(conn) == _huella_del_esquema(nueva)
    nueva.close()
    conn.close()


def test_sin_cuentas_las_filas_quedan_sin_dueno(tmp_path):
    conn = _base_en_version_2(tmp_path / "sin_cuentas.db")

    migrar(conn)

    assert _duenos(conn) == {tabla: {None} for tabla in TABLAS_CON_DUENO}
    conn.close()


def test_con_cuentas_las_filas_pasan_al_administrador_activo_mas_antiguo(tmp_path):
    conn = _base_en_version_2(tmp_path / "con_cuentas.db")
    _cuenta(conn, "comun", rol="usuario")
    _cuenta(conn, "admin-de-baja", rol="admin", activo=0)
    heredera = _cuenta(conn, "admin-vieja", rol="admin")
    _cuenta(conn, "admin-nueva", rol="admin")
    filas = {tabla: _contar(conn, tabla) for tabla in TABLAS_CON_DUENO}

    migrar(conn)

    assert heredera == 3
    assert _duenos(conn) == {tabla: {heredera} for tabla in TABLAS_CON_DUENO}
    assert {tabla: _contar(conn, tabla, f"user_id = {heredera}") for tabla in TABLAS_CON_DUENO} == filas
    conn.close()


def test_con_cuentas_pero_sin_administrador_activo_las_filas_quedan_sin_dueno(tmp_path):
    conn = _base_en_version_2(tmp_path / "sin_admin.db")
    _cuenta(conn, "comun", rol="usuario")
    _cuenta(conn, "admin-de-baja", rol="admin", activo=0)

    migrar(conn)

    assert _duenos(conn) == {tabla: {None} for tabla in TABLAS_CON_DUENO}
    conn.close()


def test_dos_cuentas_pueden_repetir_plataforma_ruta_y_tarjeta_y_una_misma_cuenta_no(tmp_path):
    conn = _base_en_version_2(tmp_path / "unicidad.db")
    migrar(conn)
    ana = _cuenta(conn, "ana")
    beto = _cuenta(conn, "beto")
    altas = [
        "INSERT INTO plataformas (nombre, url_acceso, user_id) VALUES ('Coursera', 'https://www.coursera.org', ?);",
        "INSERT INTO rutas_aprendizaje (titulo, user_id) VALUES ('Data Engineering', ?);",
        ("INSERT INTO fsrs_items (categoria, item_pregunta, respuesta_esperada, user_id) "
        "VALUES ('ingles_tecnico', 'throughput', 'otra respuesta', ?);"),
    ]

    # Los mismos nombres que ya tienen las filas sin dueño, en dos cuentas distintas
    for alta in altas:
        conn.execute(alta, (ana,))
        conn.execute(alta, (beto,))
    conn.commit()
    assert _contar(conn, "plataformas", "nombre = 'Coursera'") == 3
    assert _contar(conn, "rutas_aprendizaje", "titulo = 'Data Engineering'") == 3
    assert _contar(conn, "fsrs_items", "item_pregunta = 'throughput'") == 3

    for alta in altas:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(alta, (ana,))
        conn.rollback()

    # La misma pregunta en otro mazo de la misma cuenta sigue siendo otra tarjeta
    conn.execute(
        "INSERT INTO fsrs_items (categoria, item_pregunta, respuesta_esperada, user_id) "
        "VALUES ('otro_mazo', 'throughput', 'r', ?);",
        (ana,),
    )
    conn.commit()
    conn.close()


def test_las_filas_sin_dueno_conservan_entre_si_la_unicidad_anterior(tmp_path):
    conn = _base_en_version_2(tmp_path / "sin_dueno.db")
    migrar(conn)

    for alta in (
        "INSERT INTO plataformas (nombre, url_acceso) VALUES ('Coursera', 'https://otra');",
        "INSERT INTO rutas_aprendizaje (titulo) VALUES ('Data Engineering');",
        ("INSERT INTO fsrs_items (categoria, item_pregunta, respuesta_esperada) "
        "VALUES ('ingles_tecnico', 'throughput', 'r');"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(alta)
        conn.rollback()
    conn.close()


def test_borrar_una_cuenta_borra_sus_datos_y_deja_sin_cuenta_sus_registros(tmp_path):
    conn = _base_en_version_2(tmp_path / "baja.db", con_cuentas=True)
    migrar(conn)
    admin = conn.execute("SELECT id FROM usuarios;").fetchone()[0]
    assert _duenos(conn) == {tabla: {admin} for tabla in TABLAS_CON_DUENO}
    registros = {"api_usage_logs", "mcp_audit_logs"}

    conn.execute("DELETE FROM usuarios WHERE id = ?;", (admin,))
    conn.commit()

    for tabla in TABLAS_CON_DUENO - registros:
        assert _contar(conn, tabla) == 0, tabla
    for tabla in registros:
        assert _contar(conn, tabla) == 1, tabla
        assert _duenos(conn)[tabla] == {None}, tabla
    assert _contar(conn, "cursos_externos") == 0
    assert _contar(conn, "ruta_temas") == 0
    conn.close()


def test_la_cuenta_duena_tiene_que_existir(tmp_path):
    conn = _base_en_version_2(tmp_path / "dueno.db")
    migrar(conn)

    for alta in (
        "INSERT INTO plataformas (nombre, url_acceso, user_id) VALUES ('X', 'https://x', 99);",
        "INSERT INTO rutas_aprendizaje (titulo, user_id) VALUES ('X', 99);",
        "INSERT INTO fsrs_items (item_pregunta, respuesta_esperada, user_id) VALUES ('q', 'a', 99);",
        "INSERT INTO libros_lectura (titulo, total_capitulos, user_id) VALUES ('X', 3, 99);",
        ("INSERT INTO bloques_horarios (dia_semana, hora_inicio, hora_fin, tipo, descripcion, user_id) "
        "VALUES (1, '09:00', '10:00', 'curso', 'x', 99);"),
        "INSERT INTO sesiones_estudio (duracion_minutos, tipo, user_id) VALUES (25, 'curso', 99);",
        "INSERT INTO api_usage_logs (model, endpoint_tipo, user_id) VALUES ('m', 'e', 99);",
        "INSERT INTO mcp_audit_logs (tool_name, status, user_id) VALUES ('t', 'success', 99);",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(alta)
        conn.rollback()
    conn.close()


def test_cada_tabla_raiz_tiene_su_columna_anulable_y_su_indice_por_cuenta():
    conn = get_connection(":memory:")
    migrar(conn)

    for tabla in TABLAS_CON_DUENO:
        columnas = {fila["name"]: fila for fila in conn.execute(f"PRAGMA table_info({tabla});").fetchall()}
        assert columnas["user_id"]["notnull"] == 0, tabla
        indice = conn.execute(f"PRAGMA index_info(idx_{tabla}_user);").fetchall()
        assert [fila["name"] for fila in indice] == ["user_id"], tabla
    conn.close()


def test_existe_la_tabla_de_tokens_mcp(tmp_path):
    conn = _base_en_version_2(tmp_path / "tokens.db")
    migrar(conn)
    ana = _cuenta(conn, "ana")

    columnas = {fila["name"]: fila["notnull"] for fila in conn.execute("PRAGMA table_info(mcp_tokens);").fetchall()}
    assert columnas == {
        "id": 0,
        "usuario_id": 1,
        "token_hash": 1,
        "nombre": 0,
        "creado_en": 1,
        "ultimo_uso": 0,
        "revocado_en": 0,
    }
    indice = conn.execute("PRAGMA index_info(idx_mcp_tokens_usuario);").fetchall()
    assert [fila["name"] for fila in indice] == ["usuario_id"]

    alta = "INSERT INTO mcp_tokens (usuario_id, token_hash, nombre, creado_en) VALUES (?, ?, 'portátil', '2026-01-01');"
    conn.execute(alta, (ana, "huella-1"))
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(alta, (ana, "huella-1"))
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(alta, (99, "huella-2"))
    conn.rollback()

    conn.execute("DELETE FROM usuarios WHERE id = ?;", (ana,))
    conn.commit()
    assert _contar(conn, "mcp_tokens") == 0
    conn.close()


def test_solo_las_migraciones_marcadas_corren_con_las_claves_foraneas_apagadas(tmp_path, monkeypatch):
    vistas = {}

    def _anotar(nombre):
        def _migracion(conn):
            vistas[nombre] = (_claves_foraneas(conn), conn.in_transaction)

        return _migracion

    monkeypatch.setattr(
        migrations,
        "MIGRACIONES",
        [
            *MIGRACIONES,
            (ULTIMA_VERSION + 1, "comun", _anotar("comun")),
            (ULTIMA_VERSION + 2, "comun_explicita", _anotar("comun_explicita"), False),
            (ULTIMA_VERSION + 3, "sin_claves", _anotar("sin_claves"), True),
        ],
    )
    conn = get_connection(tmp_path / "apagadas.db")

    assert migrar(conn) == ULTIMA_VERSION + 3

    assert vistas == {"comun": (1, True), "comun_explicita": (1, True), "sin_claves": (0, True)}
    assert _claves_foraneas(conn) == 1
    conn.close()


def _migracion_que_deja_una_referencia_rota(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE tabla_a_medias (id INTEGER PRIMARY KEY);")
    conn.execute("DELETE FROM plataformas WHERE id = 1;")


def _migracion_sin_claves_que_explota(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE plataformas;")
    raise RuntimeError("fallo provocado con las claves apagadas")


@pytest.mark.parametrize(
    ("funcion", "causa"),
    [
        (_migracion_que_deja_una_referencia_rota, "cursos_externos"),
        (_migracion_sin_claves_que_explota, "fallo provocado"),
    ],
)
def test_una_migracion_sin_claves_foraneas_que_falla_se_revierte_y_las_deja_encendidas(
    tmp_path, monkeypatch, funcion, causa
):
    conn = _base_en_version_2(tmp_path / "rota.db", con_cuentas=True)
    migrar(conn)
    antes = _contenido(conn)
    huella = _huella_del_esquema(conn)
    numero = ULTIMA_VERSION + 1
    monkeypatch.setattr(migrations, "MIGRACIONES", [*MIGRACIONES, (numero, "rota_sin_claves", funcion, True)])

    with pytest.raises(ErrorDeMigracion) as fallo:
        migrar(conn)

    assert fallo.value.version == numero
    assert causa in str(fallo.value.__cause__)
    assert version_actual(conn) == ULTIMA_VERSION
    assert not conn.in_transaction
    assert _contenido(conn) == antes
    assert _huella_del_esquema(conn) == huella
    assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []
    # Encendidas de verdad: la base vuelve a rechazar una referencia rota y a borrar en cascada
    assert _claves_foraneas(conn) == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO cursos_externos (plataforma_id, nombre_curso, url_aula) VALUES (99, 'x', 'https://x');")
    conn.rollback()
    conn.execute("DELETE FROM plataformas WHERE id = 1;")
    conn.commit()
    assert _ids(conn, "cursos_externos") == [2]
    conn.close()


def test_el_esquema_de_la_migracion_3_esta_congelado():
    """Una base ya migrada no vuelve a pasar por la migración 3: lo nuevo va en una migración nueva."""
    conn = get_connection(":memory:")
    _migrar_hasta(conn, 3)
    # La 051 sacó de la migración 2 las tablas que pasaron a la nube: con ellas, el esquema es el de siempre
    _crear_las_tablas_de_cuentas_anteriores(conn)

    assert _huella_del_esquema(conn) == "919d23ffa17e047df7f4952aa929be715d1aeea85aa9b4baa41891c850a41369", (
        "Cambió el esquema que dejan las migraciones 1 a 3. Las bases en uso no reciben ese cambio: "
        "revertilo y agregá una migración nueva en db/migrations.py."
    )
    conn.close()


# --- Secretos y ajustes por cuenta (034 R2) ---


def _base_en_version_3(ruta) -> sqlite3.Connection:
    """Base como la dejaba la 033: filas en todas las tablas, con dueño, y un token MCP."""
    conn = _base_en_version_2(ruta, con_cuentas=True)
    _migrar_hasta(conn, 3)
    conn.execute(
        "INSERT INTO mcp_tokens (usuario_id, token_hash, nombre, creado_en) VALUES (1, 'huella-token', 'pc', '2026-01-02');"
    )
    conn.commit()
    return conn


def test_la_migracion_4_conserva_cada_fila_y_su_dueno(tmp_path):
    conn = _base_en_version_3(tmp_path / "v3.db")
    antes, duenos = _contenido(conn), _duenos(conn)
    assert set(antes) == TABLAS_DE_ESTUDIO | TABLAS_DE_CUENTAS | {"mcp_tokens"}
    assert all(antes.values()), "el test tiene que cargar filas en todas las tablas"

    assert migrar(conn) == ULTIMA_VERSION == 11

    despues = _contenido(conn)
    assert {tabla: despues[tabla] for tabla in antes} == antes
    assert _duenos(conn) == duenos
    assert set(despues) - set(antes) == TABLAS_DE_LA_MIGRACION_4 | TABLAS_DE_LA_MIGRACION_7 | TABLAS_DE_LA_MIGRACION_9 | TABLAS_DE_LA_MIGRACION_10 | TABLAS_DE_LA_MIGRACION_11
    assert all(despues[tabla] == [] for tabla in TABLAS_DE_LA_MIGRACION_4 | TABLAS_DE_LA_MIGRACION_7 | TABLAS_DE_LA_MIGRACION_9 | TABLAS_DE_LA_MIGRACION_10 | TABLAS_DE_LA_MIGRACION_11)
    assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []
    assert _claves_foraneas(conn) == 1
    assert len(_respaldos(tmp_path)) == 1
    conn.close()

    # Lo migrado quedó en el archivo, no solo en la conexión que migró
    otra = get_connection(tmp_path / "v3.db")
    assert version_actual(otra) == ULTIMA_VERSION
    assert {tabla: _contenido(otra)[tabla] for tabla in antes} == antes
    otra.close()


@pytest.mark.parametrize(
    ("tabla", "alta"),
    [
        (
            "secretos_usuario",
            "INSERT INTO secretos_usuario (user_id, nombre, valor_cifrado, actualizado_en) VALUES (?, ?, X'00', '2026');",
        ),
        (
            "ajustes_usuario",
            "INSERT INTO ajustes_usuario (user_id, clave, valor, actualizado_en) VALUES (?, ?, '1', '2026');",
        ),
    ],
)
def test_secretos_y_ajustes_son_por_cuenta_y_se_van_con_ella(tmp_path, tabla, alta):
    conn = get_connection(tmp_path / "almacenes.db")
    migrar(conn)
    ana, beto = _cuenta(conn, "ana"), _cuenta(conn, "beto")

    # El mismo nombre en dos cuentas son dos filas; repetido en una misma cuenta, no entra
    conn.execute(alta, (ana, "comun"))
    conn.execute(alta, (beto, "comun"))
    conn.execute(alta, (beto, "otro"))
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(alta, (ana, "comun"))
    conn.rollback()

    # La cuenta tiene que existir, y la fila no puede quedar sin cuenta
    for cuenta in (99, None):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(alta, (cuenta, "comun"))
        conn.rollback()

    conn.execute("DELETE FROM usuarios WHERE id = ?;", (beto,))
    conn.commit()
    assert [fila[0] for fila in conn.execute(f"SELECT user_id FROM {tabla};").fetchall()] == [ana]
    conn.close()


def test_el_esquema_de_la_migracion_4_esta_congelado():
    """Una base ya migrada no vuelve a pasar por la migración 4: lo nuevo va en una migración nueva."""
    conn = get_connection(":memory:")
    _migrar_hasta(conn, 4)
    # La 051 sacó de la migración 2 las tablas que pasaron a la nube: con ellas, el esquema es el de siempre
    _crear_las_tablas_de_cuentas_anteriores(conn)

    assert _huella_del_esquema(conn) == "1f3328f2becf35eafc6b3465e302c867b6fecf1077b2f9e4d63d08f08a8048dd", (
        "Cambió el esquema que dejan las migraciones 1 a 4. Las bases en uso no reciben ese cambio: "
        "revertilo y agregá una migración nueva en db/migrations.py."
    )
    conn.close()
