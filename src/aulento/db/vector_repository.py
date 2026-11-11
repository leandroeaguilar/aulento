"""Repositorio para indexación y búsqueda vectorial en PostgreSQL usando pgvector."""

import json
import logging
from typing import Any, Protocol, runtime_checkable

from aulento.db.cuenta import exigir_cuenta
from aulento.db.postgres import (
    MODELO_DE_LOS_FRAGMENTOS_SIN_MODELO,
    get_postgres_connection,
    is_postgres_available,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class AlmacenDeVectores(Protocol):
    """Protocolo común para los almacenes de vectores (SQLite con sqlite-vec y PostgreSQL con pgvector)."""

    user_id: int
    nombre: str
    motivo_no_disponible: str | None

    def disponible(self) -> bool: ...

    def insert_chunk(
        self,
        source_type: str,
        source_id: str,
        source_title: str,
        chunk_text: str,
        embedding: list[float],
        embedding_model: str,
        metadata: dict[str, Any] | None = None,
    ) -> int: ...

    def search_similar(
        self,
        query_embedding: list[float],
        embedding_model: str,
        limit: int = 5,
        source_type: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]: ...

    def search_bm25(
        self,
        query: str,
        limit: int = 20,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def delete_by_source(self, source_type: str, source_id: str) -> int: ...

    def count_embeddings(
        self,
        source_type: str | None = None,
        source_id: str | None = None,
        embedding_model: str | None = None,
    ) -> int: ...

    def count_by_model(self) -> dict[str, int]: ...

    def inicializar(self) -> dict[str, Any]: ...


class AlmacenPgvector:
    """Gestiona la persistencia e indexación de los fragmentos de conocimiento de una cuenta con pgvector.

    Cada fragmento guarda el modelo con que se calculó su vector, y la búsqueda solo compara vectores del
    modelo de la consulta: los de modelos distintos no son comparables.
    """

    def __init__(self, user_id: int, conn=None):
        self.user_id = exigir_cuenta(user_id)
        self._external_conn = conn

    @property
    def nombre(self) -> str:
        return "pgvector"

    def disponible(self) -> bool:
        if not is_postgres_available():
            return False
        from aulento.core import knowledge_rag

        knowledge_rag.asegurar_columna_de_dueno()
        knowledge_rag.asegurar_columna_de_modelo()
        return True

    def inicializar(self) -> dict[str, Any]:
        """Inicializa la extensión pgvector y las tablas en PostgreSQL."""
        from aulento.db.postgres import init_postgres_db

        success = init_postgres_db()
        if success:
            return {"ok": True, "message": "Extensión pgvector y tablas vectoriales inicializadas con éxito en PostgreSQL."}
        raise RuntimeError("No se pudo conectar a PostgreSQL. Verifica que el servicio esté disponible.")

    @property
    def motivo_no_disponible(self) -> str | None:
        if self.disponible():
            return None
        return "PostgreSQL con pgvector no está disponible o no se puede conectar."

    def _get_conn(self):
        if self._external_conn:
            return self._external_conn
        return get_postgres_connection()

    def insert_chunk(
        self,
        source_type: str,
        source_id: str,
        source_title: str,
        chunk_text: str,
        embedding: list[float],
        embedding_model: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Inserta un fragmento de conocimiento con su vector y el modelo que lo calculó."""
        if not embedding_model or not embedding_model.strip():
            raise ValueError("Un fragmento se guarda con el modelo que calculó su vector.")
        conn = self._get_conn()
        close_after = self._external_conn is None
        meta_json = json.dumps(metadata or {})

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge_embeddings (
                        user_id, source_type, source_id, source_title, chunk_text, embedding, embedding_model, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id;
                    """,
                    (self.user_id, source_type, source_id, source_title, chunk_text, embedding, embedding_model, meta_json),
                )
                row = cur.fetchone()
                return row[0] if row else 0
        finally:
            if close_after:
                conn.close()

    def search_similar(
        self,
        query_embedding: list[float],
        embedding_model: str,
        limit: int = 5,
        source_type: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Realiza una búsqueda de vecinos más cercanos usando distancia coseno (1 - cosine_distance).

        `embedding_model` es el modelo con que se calculó `query_embedding`: solo se consideran los fragmentos
        de la cuenta indexados con ese modelo. Los que no tienen modelo guardado (anteriores a la columna)
        se toman como de `MODELO_DE_LOS_FRAGMENTOS_SIN_MODELO`.
        Retorna fragmentos ordenados por mayor similitud semántica.
        """
        if not embedding_model or not embedding_model.strip():
            raise ValueError("La búsqueda necesita el modelo con que se calculó el vector de la consulta.")
        conn = self._get_conn()
        close_after = self._external_conn is None

        query = """
        SELECT 
            id,
            source_type,
            source_id,
            source_title,
            chunk_text,
            metadata,
            (1.0 - (embedding <=> %s::vector)) AS similarity
        FROM knowledge_embeddings
        WHERE user_id = %s
        """
        params: list = [query_embedding, self.user_id]

        if embedding_model == MODELO_DE_LOS_FRAGMENTOS_SIN_MODELO:
            query += " AND (embedding_model = %s OR embedding_model IS NULL)"
        else:
            query += " AND embedding_model = %s"
        params.append(embedding_model)

        if source_type:
            query += " AND source_type = %s"
            params.append(source_type)

        query += " ORDER BY embedding <=> %s::vector ASC LIMIT %s;"
        params.extend([query_embedding, limit])

        def _tx(c):
            if hasattr(c, "transaction"):
                return c.transaction()
            import contextlib
            return contextlib.nullcontext()

        try:
            with _tx(conn):
                try:
                    with _tx(conn), conn.cursor() as cur_set:
                        cur_set.execute("SET LOCAL hnsw.iterative_scan = relaxed_order;")
                except Exception as scan_err:  # noqa: BLE001
                    logger.debug("pgvector hnsw.iterative_scan no disponible o falló: %s", scan_err)

                with conn.cursor() as cur:
                    cur.execute(query, params)
                    results = []
                    for row in cur.fetchall():
                        similarity = float(row[6])
                        if similarity >= min_similarity:
                            results.append({
                                "id": row[0],
                                "source_type": row[1],
                                "source_id": row[2],
                                "source_title": row[3],
                                "chunk_text": row[4],
                                "metadata": row[5] if isinstance(row[5], dict) else json.loads(row[5] or "{}"),
                                "similarity": round(similarity, 4),
                            })
                return results
        finally:
            if close_after:
                conn.close()

    def search_bm25(
        self,
        query: str,
        limit: int = 20,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Búsqueda por palabras en PostgreSQL (delega al fallback por omisión)."""
        return []

    def delete_by_source(self, source_type: str, source_id: str) -> int:
        """Elimina los fragmentos de la cuenta asociados a una fuente dada (ej. nota actualizada)."""
        conn = self._get_conn()
        close_after = self._external_conn is None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM knowledge_embeddings WHERE user_id = %s AND source_type = %s AND source_id = %s;",
                    (self.user_id, source_type, source_id),
                )
                return cur.rowcount
        finally:
            if close_after:
                conn.close()

    def count_embeddings(
        self,
        source_type: str | None = None,
        source_id: str | None = None,
        embedding_model: str | None = None,
    ) -> int:
        """Retorna el número de fragmentos indexados de la cuenta; opcionalmente de un tipo, una fuente y un modelo."""
        condiciones = ["user_id = %s"]
        parametros: list = [self.user_id]
        for columna, valor in (("source_type", source_type), ("source_id", source_id), ("embedding_model", embedding_model)):
            if valor:
                condiciones.append(f"{columna} = %s")
                parametros.append(valor)
        conn = self._get_conn()
        close_after = self._external_conn is None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM knowledge_embeddings WHERE {' AND '.join(condiciones)};",
                    tuple(parametros),
                )
                row = cur.fetchone()
                return row[0] if row else 0
        finally:
            if close_after:
                conn.close()

    def count_by_model(self) -> dict[str, int]:
        """Cuántos fragmentos de la cuenta hay indexados con cada modelo de embeddings."""
        conn = self._get_conn()
        close_after = self._external_conn is None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT embedding_model, COUNT(*) FROM knowledge_embeddings WHERE user_id = %s GROUP BY embedding_model;",
                    (self.user_id,),
                )
                por_modelo: dict[str, int] = {}
                for modelo, cantidad in cur.fetchall():
                    nombre = modelo or MODELO_DE_LOS_FRAGMENTOS_SIN_MODELO
                    por_modelo[nombre] = por_modelo.get(nombre, 0) + int(cantidad)
                return por_modelo
        finally:
            if close_after:
                conn.close()


VectorRepository = AlmacenPgvector


class AlmacenNoConfigurado:
    """Almacén nulo para cuando el servidor corre fuera de modo local sin un almacén configurado."""

    def __init__(self, user_id: int, motivo: str = "El índice del servidor no está configurado en este proceso."):
        self.user_id = user_id
        self._motivo = motivo

    @property
    def nombre(self) -> str:
        return "no_configurado"

    def disponible(self) -> bool:
        return False

    @property
    def motivo_no_disponible(self) -> str | None:
        return self._motivo

    def inicializar(self) -> dict[str, Any]:
        return {"ok": False, "message": self._motivo}

    def insert_chunk(
        self,
        source_type: str,
        source_id: str,
        source_title: str,
        chunk_text: str,
        embedding: list[float],
        embedding_model: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        raise RuntimeError(self._motivo)

    def search_similar(
        self,
        query_embedding: list[float],
        embedding_model: str,
        limit: int = 5,
        source_type: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        return []

    def search_bm25(
        self,
        query: str,
        limit: int = 20,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Búsqueda por palabras en PostgreSQL (delega al fallback por omisión)."""
        return []

    def delete_by_source(self, source_type: str, source_id: str) -> int:
        return 0

    def count_embeddings(
        self,
        source_type: str | None = None,
        source_id: str | None = None,
        embedding_model: str | None = None,
    ) -> int:
        return 0

    def count_by_model(self) -> dict[str, int]:
        return {}
