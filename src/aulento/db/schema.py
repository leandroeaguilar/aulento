"""Esquema de base de datos relacional SQLite y funciones de inicialización/semillado."""

import sqlite3
from typing import Sequence

DDL_PLATAFORMAS = """
CREATE TABLE IF NOT EXISTS plataformas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    url_acceso TEXT NOT NULL,
    icono_color TEXT DEFAULT 'blue',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CURSOS_EXTERNOS = """
CREATE TABLE IF NOT EXISTS cursos_externos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plataforma_id INTEGER NOT NULL,
    nombre_curso TEXT NOT NULL,
    url_aula TEXT NOT NULL,
    progreso_pct REAL DEFAULT 0.0 CHECK(progreso_pct >= 0.0 AND progreso_pct <= 100.0),
    estado TEXT CHECK(estado IN ('en_curso', 'pausado', 'completado')) DEFAULT 'en_curso',
    prioridad TEXT CHECK(prioridad IN ('alta', 'media', 'baja')) DEFAULT 'alta',
    url_drive TEXT DEFAULT NULL,
    ruta_local TEXT DEFAULT NULL,
    url_notion TEXT DEFAULT NULL,
    ruta_obsidian TEXT DEFAULT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plataforma_id) REFERENCES plataformas(id) ON DELETE CASCADE
);
"""

DDL_LIBROS_LECTURA = """
CREATE TABLE IF NOT EXISTS libros_lectura (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    capitulo_actual INTEGER DEFAULT 1 CHECK(capitulo_actual >= 0),
    total_capitulos INTEGER NOT NULL CHECK(total_capitulos > 0),
    pagina_actual INTEGER DEFAULT 0 CHECK(pagina_actual >= 0),
    total_paginas INTEGER DEFAULT NULL,
    ruta_vault TEXT,
    estado TEXT CHECK(estado IN ('leyendo', 'pausado', 'completado')) DEFAULT 'leyendo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (capitulo_actual <= total_capitulos)
);
"""

DDL_MCP_AUDIT_LOGS = """
CREATE TABLE IF NOT EXISTS mcp_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    params_json TEXT DEFAULT '{}',
    transport TEXT DEFAULT 'stdio',
    client_ip TEXT,
    status TEXT CHECK(status IN ('success', 'error', 'denied')),
    error_message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_BLOQUES_HORARIOS = """
CREATE TABLE IF NOT EXISTS bloques_horarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dia_semana INTEGER NOT NULL CHECK(dia_semana BETWEEN 1 AND 7),
    hora_inicio TEXT NOT NULL,
    hora_fin TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK(tipo IN ('curso', 'lectura', 'ingles', 'repaso', 'otro')),
    descripcion TEXT NOT NULL,
    url_acceso TEXT
);
"""

DDL_FSRS_ITEMS = """
CREATE TABLE IF NOT EXISTS fsrs_items (
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
    UNIQUE(categoria, item_pregunta)
);
"""

DDL_FSRS_REVIEW_LOGS = """
CREATE TABLE IF NOT EXISTS fsrs_review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 4),
    review_datetime TIMESTAMP NOT NULL,
    elapsed_days REAL DEFAULT 0.0,
    scheduled_days REAL DEFAULT 0.0,
    state INTEGER NOT NULL,
    FOREIGN KEY (card_id) REFERENCES fsrs_items(id) ON DELETE CASCADE
);
"""

DDL_SESIONES_ESTUDIO = """
CREATE TABLE IF NOT EXISTS sesiones_estudio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bloque_id INTEGER REFERENCES bloques_horarios(id) ON DELETE SET NULL,
    duracion_minutos INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
);
"""

DDL_RUTAS_APRENDIZAJE = """
CREATE TABLE IF NOT EXISTS rutas_aprendizaje (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    categoria TEXT DEFAULT 'data_ai',
    nivel_objetivo TEXT DEFAULT 'Senior',
    enfoque_estudio TEXT DEFAULT 'profesional',
    progreso_pct REAL DEFAULT 0.0 CHECK(progreso_pct >= 0.0 AND progreso_pct <= 100.0),
    metadata_json TEXT DEFAULT '{}',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_RUTA_MODULOS = """
CREATE TABLE IF NOT EXISTS ruta_modulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    orden INTEGER NOT NULL DEFAULT 1,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ruta_id) REFERENCES rutas_aprendizaje(id) ON DELETE CASCADE
);
"""

DDL_RUTA_TEMAS = """
CREATE TABLE IF NOT EXISTS ruta_temas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    orden INTEGER NOT NULL DEFAULT 1,
    estado TEXT CHECK(estado IN ('pendiente', 'en_progreso', 'completado')) DEFAULT 'pendiente',
    fuente TEXT DEFAULT 'curada',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (modulo_id) REFERENCES ruta_modulos(id) ON DELETE CASCADE
);
"""

DDL_RUTA_CLASES = """
CREATE TABLE IF NOT EXISTS ruta_clases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_id INTEGER NOT NULL UNIQUE,
    titulo TEXT NOT NULL,
    contenido_markdown TEXT NOT NULL,
    diagramas_mermaid TEXT DEFAULT '[]',
    flashcards_json TEXT DEFAULT '[]',
    origen TEXT DEFAULT 'gemini_in_app',
    vault_path TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tema_id) REFERENCES ruta_temas(id) ON DELETE CASCADE
);
"""

DDL_RUTA_CLASES_VERSIONES = """
CREATE TABLE IF NOT EXISTS ruta_clases_versiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    contenido_markdown TEXT NOT NULL,
    diagramas_mermaid TEXT DEFAULT '[]',
    flashcards_json TEXT DEFAULT '[]',
    origen TEXT DEFAULT 'gemini_in_app',
    fecha_version TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tema_id) REFERENCES ruta_temas(id) ON DELETE CASCADE
);
"""

DDL_RUTA_PRELACIONES = """
CREATE TABLE IF NOT EXISTS ruta_prelaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta_id INTEGER NOT NULL,
    tema_origen_id INTEGER NOT NULL,
    tema_destino_id INTEGER NOT NULL,
    tipo TEXT DEFAULT 'estricta' CHECK(tipo IN ('estricta', 'recomendada')),
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ruta_id) REFERENCES rutas_aprendizaje(id) ON DELETE CASCADE,
    FOREIGN KEY (tema_origen_id) REFERENCES ruta_temas(id) ON DELETE CASCADE,
    FOREIGN KEY (tema_destino_id) REFERENCES ruta_temas(id) ON DELETE CASCADE,
    UNIQUE(tema_origen_id, tema_destino_id)
);
"""

DDL_API_USAGE_LOGS = """
CREATE TABLE IF NOT EXISTS api_usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    provider TEXT DEFAULT 'gemini',
    model TEXT NOT NULL,
    endpoint_tipo TEXT NOT NULL,
    api_tier TEXT DEFAULT 'free',
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    status_code INTEGER DEFAULT 200,
    latency_ms REAL DEFAULT 0.0
);
"""

DDL_ROADMAP_TOPIC_RETENTION = """
CREATE TABLE IF NOT EXISTS roadmap_topic_retention (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_id INTEGER NOT NULL UNIQUE,
    state INTEGER DEFAULT 0,
    due_date TIMESTAMP NOT NULL,
    stability REAL DEFAULT 2.0,
    difficulty REAL DEFAULT 5.0,
    elapsed_days INTEGER DEFAULT 0,
    scheduled_days INTEGER DEFAULT 3,
    reps INTEGER DEFAULT 0,
    lapses INTEGER DEFAULT 0,
    last_review TIMESTAMP,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tema_id) REFERENCES ruta_temas(id) ON DELETE CASCADE
);
"""

DDL_ROADMAP_TOPIC_REVIEWS = """
CREATE TABLE IF NOT EXISTS roadmap_topic_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retention_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    scheduled_days INTEGER NOT NULL,
    elapsed_days INTEGER NOT NULL,
    review_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notas TEXT,
    FOREIGN KEY (retention_id) REFERENCES roadmap_topic_retention(id) ON DELETE CASCADE
);
"""


# Las 5 plataformas académicas reales del usuario
PLATAFORMAS_SEMILLA = [
    {
        "nombre": "Digital House",
        "url_acceso": "https://www.digitalhouse.com",
        "icono_color": "purple",
    },
    {
        "nombre": "Google Cloud Skills Boost",
        "url_acceso": "https://www.cloudskillsboost.google",
        "icono_color": "blue",
    },
    {
        "nombre": "Humai",
        "url_acceso": "https://humai.com.ar",
        "icono_color": "green",
    },
    {
        "nombre": "Coursera",
        "url_acceso": "https://www.coursera.org",
        "icono_color": "cyan",
    },
    {
        "nombre": "Anthropic Academy",
        "url_acceso": "https://anthropic.com",
        "icono_color": "orange",
    },
]


def aplicar_esquema_base(conn: sqlite3.Connection) -> None:
    """Ejecuta los DDL de las tablas relacionales sin confirmar la transacción."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute(DDL_PLATAFORMAS)
    cursor.execute(DDL_CURSOS_EXTERNOS)
    cursor.execute(DDL_LIBROS_LECTURA)
    cursor.execute(DDL_BLOQUES_HORARIOS)
    cursor.execute(DDL_FSRS_ITEMS)
    cursor.execute(DDL_FSRS_REVIEW_LOGS)
    cursor.execute(DDL_SESIONES_ESTUDIO)
    cursor.execute(DDL_RUTAS_APRENDIZAJE)
    cursor.execute(DDL_RUTA_MODULOS)
    cursor.execute(DDL_RUTA_TEMAS)
    cursor.execute(DDL_RUTA_CLASES)
    cursor.execute(DDL_RUTA_CLASES_VERSIONES)
    cursor.execute(DDL_RUTA_PRELACIONES)
    cursor.execute(DDL_API_USAGE_LOGS)
    cursor.execute(DDL_MCP_AUDIT_LOGS)
    cursor.execute(DDL_ROADMAP_TOPIC_RETENTION)
    cursor.execute(DDL_ROADMAP_TOPIC_REVIEWS)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ruta_modulos_ruta ON ruta_modulos(ruta_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ruta_temas_modulo ON ruta_temas(modulo_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ruta_clases_tema ON ruta_clases(tema_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ruta_clases_versiones_tema ON ruta_clases_versiones(tema_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prelaciones_ruta ON ruta_prelaciones(ruta_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prelaciones_origen ON ruta_prelaciones(tema_origen_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prelaciones_destino ON ruta_prelaciones(tema_destino_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp ON api_usage_logs(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mcp_audit_timestamp ON mcp_audit_logs(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mcp_audit_tool ON mcp_audit_logs(tool_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topic_retention_tema ON roadmap_topic_retention(tema_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topic_retention_due ON roadmap_topic_retention(due_date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topic_reviews_retention ON roadmap_topic_reviews(retention_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topic_reviews_time ON roadmap_topic_reviews(review_time);")
    try:
        cursor.execute("ALTER TABLE rutas_aprendizaje ADD COLUMN enfoque_estudio TEXT DEFAULT 'profesional';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE libros_lectura ADD COLUMN pagina_actual INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE libros_lectura ADD COLUMN total_paginas INTEGER DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE cursos_externos ADD COLUMN url_drive TEXT DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE cursos_externos ADD COLUMN ruta_local TEXT DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE cursos_externos ADD COLUMN url_notion TEXT DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE cursos_externos ADD COLUMN ruta_obsidian TEXT DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass
    try:
        # Huella de la última nota que el sistema escribió en el vault para la clase
        cursor.execute("ALTER TABLE ruta_clases ADD COLUMN vault_hash TEXT DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass


def create_schema(conn: sqlite3.Connection) -> None:
    """Deja la base en la última versión del esquema aplicando las migraciones pendientes."""
    from aulento.db.migrations import migrar

    migrar(conn)


def seed_plataformas(conn: sqlite3.Connection, user_id: int) -> int:
    """Inserta de forma idempotente las plataformas semilla iniciales de una cuenta.

    Retorna el número de plataformas insertadas o actualizadas en esta ejecución.
    """
    from aulento.db.cuenta import exigir_cuenta

    exigir_cuenta(user_id)
    cursor = conn.cursor()
    insertados = 0
    query = """
    INSERT INTO plataformas (user_id, nombre, url_acceso, icono_color)
    VALUES (:user_id, :nombre, :url_acceso, :icono_color)
    ON CONFLICT(user_id, nombre) DO UPDATE SET
        url_acceso = excluded.url_acceso,
        icono_color = excluded.icono_color;
    """
    for plat in PLATAFORMAS_SEMILLA:
        cursor.execute(query, {**plat, "user_id": user_id})
        if cursor.rowcount > 0:
            insertados += 1
    conn.commit()
    return insertados


def init_db(conn: sqlite3.Connection) -> None:
    """Lleva la base a la última versión del esquema. No siembra: sembrar es una operación de una cuenta."""
    from aulento.db.migrations import migrar

    migrar(conn)
