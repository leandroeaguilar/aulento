"""Módulo de conexión y gestión para PostgreSQL con soporte nativo de pgvector."""

import logging
import os
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_POSTGRES_URL = "postgresql://postgres:postgres@127.0.0.1:5432/study_engine"

TABLA_DE_VECTORES = "knowledge_embeddings"
ALTA_DE_LA_COLUMNA_DE_DUENO = "ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS user_id INTEGER;"
ALTA_DEL_INDICE_DE_DUENO = "CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_user_id ON knowledge_embeddings(user_id);"
ALTA_DE_LA_COLUMNA_DE_MODELO = "ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100);"
ALTA_DEL_INDICE_DE_MODELO = (
    "CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_embedding_model ON knowledge_embeddings(embedding_model);"
)
# Los fragmentos indexados antes de que se guardara el modelo (columna vacía) se calcularon con el de Gemini
MODELO_DE_LOS_FRAGMENTOS_SIN_MODELO = "gemini-embedding-001"


def get_postgres_url() -> str:
    """Retorna la URL de conexión a PostgreSQL desde variables de entorno."""
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.strip():
        return db_url.strip()

    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    dbname = os.getenv("POSTGRES_DB", "study_engine")

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def get_postgres_connection(connect_timeout: int = 2):
    """Retorna una conexión abierta a PostgreSQL con soporte para pgvector registrado.
    
    Requiere que psycopg y pgvector estén instalados.
    """
    try:
        import psycopg
        from pgvector.psycopg import register_vector
    except ImportError as e:
        raise ImportError(
            "Los módulos 'psycopg' y 'pgvector' son requeridos para usar PostgreSQL. "
            "Instálalos con: uv pip install 'psycopg[binary]' 'pgvector'"
        ) from e

    url = get_postgres_url()
    conn = psycopg.connect(url, autocommit=True, connect_timeout=connect_timeout)
    register_vector(conn)
    return conn


def is_postgres_available(timeout_seconds: int = 2) -> bool:
    """Verifica si PostgreSQL está accesible y la extensión pgvector está lista."""
    try:
        conn = get_postgres_connection(connect_timeout=timeout_seconds)
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            row = cur.fetchone()
            if not row or row[0] != 1:
                return False
        conn.close()
        return True
    except Exception as e:
        logger.debug("PostgreSQL no está disponible actualmente: %s", e)
        return False


# Las altas de columnas en un almacén anterior se hacen una vez por proceso, antes del primer uso
_dueno_asegurado = False
_modelo_asegurado = False


def _dar_de_alta_en_un_almacen_anterior(sentencias: tuple[str, ...]) -> bool:
    """Ejecuta las altas (idempotentes) sobre `knowledge_embeddings`; si la tabla todavía no existe devuelve False."""
    conn = get_postgres_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s;",
                (TABLA_DE_VECTORES,),
            )
            if not cur.fetchall():
                return False
            for sentencia in sentencias:
                cur.execute(sentencia)
    finally:
        conn.close()
    return True


def asegurar_columna_de_dueno() -> bool:
    """Deja `knowledge_embeddings.user_id` y su índice en un almacén creado antes de que los fragmentos tuvieran dueño.

    Es idempotente y, una vez hecha, no vuelve a consultar en todo el proceso. Si la tabla todavía no existe
    no hace nada y devuelve False: la crea `init_postgres_db`, ya con la columna.
    """
    global _dueno_asegurado
    if not _dueno_asegurado:
        _dueno_asegurado = _dar_de_alta_en_un_almacen_anterior((ALTA_DE_LA_COLUMNA_DE_DUENO, ALTA_DEL_INDICE_DE_DUENO))
    return _dueno_asegurado


def asegurar_columna_de_modelo() -> bool:
    """Deja `knowledge_embeddings.embedding_model` y su índice en un almacén creado antes de que se guardara el modelo.

    Igual que `asegurar_columna_de_dueno`: idempotente, una vez por proceso, y sin efecto si la tabla no existe.
    Los fragmentos anteriores quedan con la columna vacía y se toman como de `MODELO_DE_LOS_FRAGMENTOS_SIN_MODELO`.
    """
    global _modelo_asegurado
    if not _modelo_asegurado:
        _modelo_asegurado = _dar_de_alta_en_un_almacen_anterior((ALTA_DE_LA_COLUMNA_DE_MODELO, ALTA_DEL_INDICE_DE_MODELO))
    return _modelo_asegurado


def init_postgres_db(conn=None) -> bool:
    """Inicializa la extensión vector y las tablas vectoriales en PostgreSQL de forma idempotente."""
    close_after = False
    if conn is None:
        try:
            conn = get_postgres_connection()
            close_after = True
        except Exception as e:
            logger.error("No se pudo conectar a PostgreSQL para inicializar: %s", e)
            return False

    try:
        with conn.cursor() as cur:
            # 1. Habilitar extensión pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # 2. Crear tabla de embeddings vectoriales
            cur.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                id SERIAL PRIMARY KEY,
                source_type VARCHAR(50) NOT NULL, -- 'obsidian_note', 'book_chunk', 'fsrs_card', 'course_topic'
                source_id VARCHAR(255) NOT NULL,
                source_title TEXT NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding vector(768) NOT NULL, -- 768 dimensiones, del modelo que dice `embedding_model`
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 3. Índice HNSW para búsqueda coseno
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_cosine 
            ON knowledge_embeddings USING hnsw (embedding vector_cosine_ops);
            """)

            # 4. Índice por tipo y fuente
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_source_type 
            ON knowledge_embeddings(source_type);
            """)
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_source_id 
            ON knowledge_embeddings(source_id);
            """)

            # 5. Dueño de cada fragmento: los anteriores quedan sin dueño e invisibles hasta reindexarlos
            cur.execute(ALTA_DE_LA_COLUMNA_DE_DUENO)
            cur.execute(ALTA_DEL_INDICE_DE_DUENO)

            # 6. Modelo con que se calculó cada vector: la búsqueda solo compara vectores del mismo modelo
            cur.execute(ALTA_DE_LA_COLUMNA_DE_MODELO)
            cur.execute(ALTA_DEL_INDICE_DE_MODELO)

        logger.info("Base de datos PostgreSQL con pgvector inicializada con éxito.")
        return True
    except Exception as e:
        logger.error("Error al inicializar tablas en PostgreSQL: %s", e)
        raise
    finally:
        if close_after and conn:
            conn.close()
