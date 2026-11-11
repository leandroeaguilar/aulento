"""Almacén de vectores local sobre SQLite con la extensión sqlite-vec."""

import contextlib
import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aulento.core.ia.tipos import DIMENSIONES_DE_EMBEDDING
from aulento.db.cuenta import exigir_cuenta

logger = logging.getLogger(__name__)

DIMENSIONES_POR_DEFECTO = DIMENSIONES_DE_EMBEDDING
# Archivos ya verificados (integridad y esquema) en este proceso: la verificación completa corre una sola vez
_VERIFICADAS: set[str] = set()


def _es_corrupcion(err: sqlite3.DatabaseError) -> bool:
    """Un error que indica archivo dañado; una base ocupada o bloqueada no lo es."""
    if isinstance(err, sqlite3.OperationalError):
        return False
    texto = str(err).lower()
    return "locked" not in texto and "busy" not in texto


def _abrir_conexion_sqlite_vec(ruta: Path) -> sqlite3.Connection:
    """Abre una conexión SQLite y carga la extensión sqlite-vec."""
    conn = sqlite3.connect(str(ruta), timeout=10.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        if not hasattr(conn, "enable_load_extension"):
            raise RuntimeError("Python no tiene habilitado enable_load_extension para SQLite.")
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as err:
            raise RuntimeError(f"No se pudo cargar la extensión sqlite-vec: {err}") from err
        return conn
    except Exception:
        conn.close()
        raise


def _asegurar_esquema(conn: sqlite3.Connection, dimensiones: int = DIMENSIONES_POR_DEFECTO) -> None:
    """Crea la tabla de fragmentos y la tabla virtual vec0 para búsqueda semántica."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fragmentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_title TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            embedding_model TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fragmentos_user_model ON fragmentos(user_id, embedding_model);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fragmentos_user_source ON fragmentos(user_id, source_type, source_id);")

    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_fragmentos USING vec0(
            user_id integer partition key,
            embedding_model text partition key,
            source_type text,
            embedding float[{dimensiones}] distance_metric=cosine
        );
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_delete_vec AFTER DELETE ON fragmentos BEGIN
            DELETE FROM vec_fragmentos WHERE user_id = OLD.user_id AND rowid = OLD.id;
        END;
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS fragmentos_fts USING fts5(
            source_title,
            chunk_text,
            content='fragmentos',
            content_rowid='id',
            tokenize="unicode61 remove_diacritics 2"
        );
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_insert_fragmentos_fts AFTER INSERT ON fragmentos BEGIN
            INSERT INTO fragmentos_fts(rowid, source_title, chunk_text) VALUES (NEW.id, NEW.source_title, NEW.chunk_text);
        END;
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_delete_fragmentos_fts AFTER DELETE ON fragmentos BEGIN
            INSERT INTO fragmentos_fts(fragmentos_fts, rowid, source_title, chunk_text) VALUES ('delete', OLD.id, OLD.source_title, OLD.chunk_text);
        END;
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_update_fragmentos_fts AFTER UPDATE ON fragmentos BEGIN
            INSERT INTO fragmentos_fts(fragmentos_fts, rowid, source_title, chunk_text) VALUES ('delete', OLD.id, OLD.source_title, OLD.chunk_text);
            INSERT INTO fragmentos_fts(rowid, source_title, chunk_text) VALUES (NEW.id, NEW.source_title, NEW.chunk_text);
        END;
        """
    )

    try:
        n_frag = conn.execute("SELECT COUNT(*) FROM fragmentos;").fetchone()[0]
        n_fts = conn.execute("SELECT COUNT(*) FROM fragmentos_fts_docsize;").fetchone()[0]
        if n_frag > 0 and n_fts == 0:
            conn.execute("INSERT INTO fragmentos_fts(fragmentos_fts) VALUES('rebuild');")
    except Exception as err:  # noqa: BLE001
        logger.debug("No se pudo verificar o reconstruir fragmentos_fts: %s", err)

    conn.commit()


class AlmacenVectoresSqlite:
    """Almacén de vectores para la versión local de Aulento sobre SQLite con sqlite-vec.

    Guarda los fragmentos en `vectores.db`, separado de la base principal para no atar las migraciones
    a la extensión de vectores. Si el archivo está dañado, se renombra y se crea uno vacío para poder
    reindexar sin perder los datos principales.
    """

    def __init__(
        self,
        user_id: int,
        conn: sqlite3.Connection | None = None,
        db_path: Path | None = None,
        dimensiones: int = DIMENSIONES_POR_DEFECTO,
    ):
        self.user_id = exigir_cuenta(user_id)
        self._external_conn = conn
        self._db_path = db_path
        self._dimensiones = dimensiones
        self._ultimo_error: str | None = None

    @property
    def nombre(self) -> str:
        return "sqlite-vec"

    @property
    def db_path(self) -> Path:
        if self._db_path is not None:
            return self._db_path
        from aulento.config import get_data_dir

        return get_data_dir() / "vectores.db"

    def _get_conn(self) -> sqlite3.Connection:
        if self._external_conn is not None:
            _asegurar_esquema(self._external_conn, self._dimensiones)
            return self._external_conn

        ruta = self.db_path
        ruta.parent.mkdir(parents=True, exist_ok=True)
        clave = str(ruta.resolve())
        if clave in _VERIFICADAS and ruta.exists():
            return _abrir_conexion_sqlite_vec(ruta)

        conn: sqlite3.Connection | None = None
        try:
            conn = _abrir_conexion_sqlite_vec(ruta)
            verificacion = conn.execute("PRAGMA quick_check;").fetchone()
            if not verificacion or verificacion[0] != "ok":
                raise sqlite3.DatabaseError(f"Verificación de integridad falló: {verificacion}")
            _asegurar_esquema(conn, self._dimensiones)
            _VERIFICADAS.add(clave)
            return conn
        except sqlite3.DatabaseError as err:
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.close()
            if not _es_corrupcion(err):
                raise
            logger.warning(
                "La base de datos de vectores %s está dañada: %s. Se renombra a copia dañada y se recrea vacía.",
                ruta,
                err,
            )
            fecha = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            # El archivo y sus acompañantes de WAL: dejar el -wal viejo junto a una base nueva la volvería a dañar
            for sufijo in ("", "-wal", "-shm"):
                original = ruta.parent / f"{ruta.name}{sufijo}"
                if not original.exists():
                    continue
                try:
                    original.rename(ruta.parent / f"{ruta.name}.danado-{fecha}{sufijo}")
                except OSError as ren_err:
                    logger.error("No se pudo renombrar el archivo dañado %s: %s", original, ren_err)
                    raise RuntimeError(
                        f"No se pudo respaldar el archivo de vectores dañado {original}: {ren_err}"
                    ) from ren_err
            conn = _abrir_conexion_sqlite_vec(ruta)
            _asegurar_esquema(conn, self._dimensiones)
            _VERIFICADAS.add(clave)
            return conn

    def disponible(self) -> bool:
        """Indica si la extensión sqlite-vec y la base de datos de vectores están funcionales."""
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("SELECT 1 FROM fragmentos LIMIT 1;")
            if self._external_conn is None:
                conn.close()
            self._ultimo_error = None
            return True
        except Exception as e:  # noqa: BLE001
            self._ultimo_error = str(e)
            return False

    def inicializar(self) -> dict[str, Any]:
        """En SQLite local no hace falta inicialización manual."""
        return {"ok": True, "message": "El índice local no necesita inicialización."}

    @property
    def motivo_no_disponible(self) -> str | None:
        """Explica por qué el almacén no está disponible, o None si está listo."""
        if self.disponible():
            return None
        return self._ultimo_error or "La extensión sqlite-vec no está disponible en este entorno."

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
        """Inserta un fragmento de conocimiento con su vector en SQLite."""
        if not embedding_model or not embedding_model.strip():
            raise ValueError("Un fragmento se guarda con el modelo que calculó su vector.")
        import sqlite_vec

        conn = self._get_conn()
        close_after = self._external_conn is None
        meta_json = json.dumps(metadata or {})
        vec_bytes = sqlite_vec.serialize_float32(embedding)

        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO fragmentos (
                        user_id, source_type, source_id, source_title, chunk_text, metadata, embedding_model
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (self.user_id, source_type, source_id, source_title, chunk_text, meta_json, embedding_model),
                )
                frag_id = cur.lastrowid
                cur.execute(
                    """
                    INSERT INTO vec_fragmentos (rowid, user_id, embedding_model, source_type, embedding)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (frag_id, self.user_id, embedding_model, source_type, vec_bytes),
                )
                return frag_id or 0
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
        """Realiza una búsqueda semántica de vecinos más cercanos usando distancia coseno."""
        if not embedding_model or not embedding_model.strip():
            raise ValueError("La búsqueda necesita el modelo con que se calculó el vector de la consulta.")
        import sqlite_vec

        conn = self._get_conn()
        close_after = self._external_conn is None
        vec_bytes = sqlite_vec.serialize_float32(query_embedding)

        query = """
        SELECT 
            f.id,
            f.source_type,
            f.source_id,
            f.source_title,
            f.chunk_text,
            f.metadata,
            (1.0 - v.distance) AS similarity
        FROM vec_fragmentos v
        JOIN fragmentos f ON f.id = v.rowid
        WHERE v.user_id = ?
          AND v.embedding_model = ?
        """
        params: list[Any] = [self.user_id, embedding_model]

        if source_type:
            query += " AND v.source_type = ?"
            params.append(source_type)

        query += """
          AND v.embedding MATCH ?
          AND v.k = ?
        ORDER BY v.distance ASC;
        """
        params.extend([vec_bytes, limit])

        try:
            cur = conn.cursor()
            cur.execute(query, params)
            results = []
            for row in cur.fetchall():
                similarity = float(row[6])
                # Limitar similitud coseno al rango [0.0, 1.0]
                similarity = max(0.0, min(1.0, similarity))
                if similarity >= min_similarity:
                    meta = row[5]
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta or "{}")
                        except (json.JSONDecodeError, TypeError):
                            meta = {}
                    results.append({
                        "id": row[0],
                        "source_type": row[1],
                        "source_id": row[2],
                        "source_title": row[3],
                        "chunk_text": row[4],
                        "metadata": meta if isinstance(meta, dict) else {},
                        "similarity": round(similarity, 4),
                    })
                    if len(results) >= limit:
                        break
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
        """Búsqueda por palabras usando BM25 con SQLite FTS5 (sin acentos, filtrando user_id)."""
        palabras = [p for p in re.findall(r"\w+", query) if len(p) >= 2]
        if not palabras:
            return []

        # Escapar comillas dobles y armar consulta FTS con operador OR
        terminos_escapados = ['"' + p.replace('"', '""') + '"' for p in palabras]
        match_query = " OR ".join(terminos_escapados)

        conn = self._get_conn()
        close_after = self._external_conn is None

        sql = """
        SELECT 
            f.id,
            f.source_type,
            f.source_id,
            f.source_title,
            f.chunk_text,
            f.metadata,
            bm25(fragmentos_fts) AS bm25_score
        FROM fragmentos_fts
        JOIN fragmentos f ON f.id = fragmentos_fts.rowid
        WHERE f.user_id = ?
          AND fragmentos_fts MATCH ?
        """
        params: list[Any] = [self.user_id, match_query]

        if source_type:
            sql += " AND f.source_type = ?"
            params.append(source_type)

        sql += " ORDER BY bm25(fragmentos_fts) ASC LIMIT ?;"
        params.append(limit)

        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            results = []
            for row in cur.fetchall():
                meta = row[5]
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta or "{}")
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                results.append({
                    "id": row[0],
                    "source_type": row[1],
                    "source_id": row[2],
                    "source_title": row[3],
                    "chunk_text": row[4],
                    "metadata": meta if isinstance(meta, dict) else {},
                    "score": float(row[6]),
                })
            return results
        except sqlite3.OperationalError as err:
            logger.debug("Error en consulta FTS5 MATCH: %s", err)
            return []
        finally:
            if close_after:
                conn.close()

    def delete_by_source(self, source_type: str, source_id: str) -> int:
        """Elimina los fragmentos de la cuenta asociados a una fuente dada."""
        conn = self._get_conn()
        close_after = self._external_conn is None
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM fragmentos WHERE user_id = ? AND source_type = ? AND source_id = ?;",
                    (self.user_id, source_type, source_id),
                )
                ids = [r[0] for r in cur.fetchall()]
                if not ids:
                    return 0
                for chunk_id in ids:
                    cur.execute(
                        "DELETE FROM vec_fragmentos WHERE user_id = ? AND rowid = ?;",
                        (self.user_id, chunk_id),
                    )
                cur.execute(
                    f"DELETE FROM fragmentos WHERE id IN ({','.join('?' for _ in ids)});",
                    tuple(ids),
                )
                return len(ids)
        finally:
            if close_after:
                conn.close()

    def count_embeddings(
        self,
        source_type: str | None = None,
        source_id: str | None = None,
        embedding_model: str | None = None,
    ) -> int:
        """Retorna el número de fragmentos indexados de la cuenta; opcionalmente de un tipo, fuente o modelo."""
        conn = self._get_conn()
        close_after = self._external_conn is None
        condiciones = ["user_id = ?"]
        params: list[Any] = [self.user_id]
        for col, val in (("source_type", source_type), ("source_id", source_id), ("embedding_model", embedding_model)):
            if val:
                condiciones.append(f"{col} = ?")
                params.append(val)
        query = f"SELECT COUNT(*) FROM fragmentos WHERE {' AND '.join(condiciones)};"
        try:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
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
            cur = conn.cursor()
            cur.execute(
                "SELECT embedding_model, COUNT(*) FROM fragmentos WHERE user_id = ? GROUP BY embedding_model;",
                (self.user_id,),
            )
            por_modelo: dict[str, int] = {}
            for modelo, cantidad in cur.fetchall():
                nombre = str(modelo) if modelo else "desconocido"
                por_modelo[nombre] = por_modelo.get(nombre, 0) + int(cantidad)
            return por_modelo
        finally:
            if close_after:
                conn.close()
