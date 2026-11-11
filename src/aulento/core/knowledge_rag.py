"""Servicio de RAG y Búsqueda Semántica sobre el almacén de vectores con los embeddings de la IA de la cuenta."""

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aulento.core.embedding_service import (
    EMBEDDING_DIMENSIONS,
    EmbeddingService,
    VectorDeTexto,
)
from aulento.core.extensiones import obtener_almacen_de_vectores
from aulento.core.fragmentos import fragmentar
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.materiales import AlmacenDeMateriales, MaterialNoEncontrado
from aulento.db.cuenta import exigir_cuenta
from aulento.db.postgres import (
    asegurar_columna_de_dueno,  # noqa: F401
    asegurar_columna_de_modelo,  # noqa: F401
)
from aulento.db.vector_repository import (
    AlmacenDeVectores,
)
from aulento.vault.carpetas import carpetas_del_tutor
from aulento.vault.reader import VaultReader
from aulento.vault.rutas import vault_de_la_cuenta

logger = logging.getLogger(__name__)

# Tipo de fuente de los fragmentos de un material subido desde la PC (048) y notas del vault (059)
TIPO_DE_FUENTE_MATERIAL = "material"
TIPO_DE_FUENTE_NOTA = "note"
VERSION_DE_INDEXADO = "2"


def _huella(modelo: str, texto: str, version: str | None = None) -> str:
    """La huella de una fuente indexada: su modelo, la versión de indexado y su texto."""
    v = version if version is not None else VERSION_DE_INDEXADO
    return hashlib.sha256(f"{modelo}\0{v}\0{texto}".encode()).hexdigest()


def _leer_hash(conn, user_id: int, source_type: str, source_id: str) -> str | None:
    fila = conn.execute(
        "SELECT hash FROM hashes_indexados WHERE user_id = ? AND source_type = ? AND source_id = ?;",
        (user_id, source_type, source_id),
    ).fetchone()
    return fila[0] if fila else None


def _guardar_hash(conn, user_id: int, source_type: str, source_id: str, huella: str) -> None:
    conn.execute(
        """
        INSERT INTO hashes_indexados (user_id, source_type, source_id, hash, indexado_en)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (user_id, source_type, source_id) DO UPDATE SET hash = excluded.hash, indexado_en = excluded.indexado_en;
        """,
        (user_id, source_type, source_id, huella, datetime.now(UTC).isoformat(timespec="seconds")),
    )
    conn.commit()


class FuenteNoEncontrada(ValueError):
    """El libro o el curso pedido no existe para la cuenta: no existe, o es de otra."""

    def __init__(self, que: str, identificador: int):
        super().__init__(f"{que} con ID {identificador} no encontrado.")
        self.que = que
        self.identificador = identificador


class KnowledgeRAGService:
    """Orquestador de RAG de una cuenta: genera embeddings y recupera solo los fragmentos de esa cuenta.

    Cada fragmento se guarda con el modelo que calculó su vector y la búsqueda solo considera los del modelo
    de la consulta. `ultimo_embedding` es el último que calculó el servicio: con qué modelo y proveedor, y por
    qué fue el respaldo local si lo fue.
    """

    def __init__(
        self,
        user_id: int,
        embedding_service: EmbeddingService | None = None,
        repository: AlmacenDeVectores | None = None,
    ):
        self.user_id = exigir_cuenta(user_id)
        if repository is not None and getattr(repository, "user_id", None) != self.user_id:
            raise ValueError("El repositorio de vectores tiene que ser de la misma cuenta que el servicio.")
        self.embedder = embedding_service or EmbeddingService(
            pasarela=PasarelaDeIA.con_conexion_propia(self.user_id)
        )
        self.repo: AlmacenDeVectores = repository or obtener_almacen_de_vectores(self.user_id)
        self.ultimo_embedding: VectorDeTexto | None = None

    def is_ready(self) -> bool:
        """Indica si el almacén de vectores está disponible."""
        return self.repo.disponible()

    def initialize(self) -> bool:
        """Crea la extensión y tablas si el almacén lo requiere."""
        res = self.repo.inicializar()
        return bool(res.get("ok", True))

    def index_document(
        self,
        source_type: str,
        source_id: str,
        source_title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
    ) -> int:
        """Divide el documento en chunks de texto, genera sus embeddings y los persiste en pgvector."""
        if not self.is_ready():
            motivo = self.repo.motivo_no_disponible or "no disponible"
            raise RuntimeError(f"El índice de búsqueda no está disponible: {motivo}")

        # Limpiar versiones previas de esta misma fuente
        self.repo.delete_by_source(source_type, source_id)

        # Fragmentador por estructura Markdown (R1)
        fragmentos = fragmentar(content, titulo=source_title, tamano=chunk_size, solapamiento=chunk_overlap)
        inserted_count = 0

        for idx, frag in enumerate(fragmentos):
            chunk_clean = frag.texto.strip()
            if not chunk_clean:
                continue

            # El embedding se calcula sobre encabezado + texto; el almacén guarda texto limpio y metadata
            texto_para_embedding = f"{frag.encabezado}\n\n{chunk_clean}" if frag.encabezado else chunk_clean
            try:
                calculado = self.ultimo_embedding = self.embedder.embeber(texto_para_embedding, tarea="documento")
            except TypeError:
                calculado = self.ultimo_embedding = self.embedder.embeber(texto_para_embedding)
            chunk_meta = dict(metadata or {})
            chunk_meta["chunk_index"] = idx
            chunk_meta["total_chunks"] = len(fragmentos)
            chunk_meta["encabezado"] = frag.encabezado
            chunk_meta["inicio"] = frag.inicio
            chunk_meta["fin"] = frag.fin

            self.repo.insert_chunk(
                source_type=source_type,
                source_id=source_id,
                source_title=source_title,
                chunk_text=chunk_clean,
                embedding=calculado.vector,
                embedding_model=calculado.modelo,
                metadata=chunk_meta,
            )
            inserted_count += 1

        logger.info("Indexados %d chunks para '%s' (%s).", inserted_count, source_title, source_type)
        return inserted_count

    def search(
        self,
        query: str,
        limit: int = 5,
        source_type: str | None = None,
        min_similarity: float = 0.4,
    ) -> list[dict[str, Any]]:
        """Busca fragmentos semánticamente cercanos a la consulta en lenguaje natural.

        Solo entre los fragmentos de la cuenta indexados con el mismo modelo con que se calcula la consulta.
        """
        if not self.is_ready():
            return []

        try:
            consulta = self.ultimo_embedding = self.embedder.embeber(query, tarea="consulta")
        except TypeError:
            consulta = self.ultimo_embedding = self.embedder.embeber(query)
        return self.repo.search_similar(
            query_embedding=consulta.vector,
            embedding_model=consulta.modelo,
            limit=limit,
            source_type=source_type,
            min_similarity=min_similarity,
        )

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadísticas de la base vectorial; con el almacén apagado el total es 0, y un error al contar se propaga.

        `embedding_model` es el modelo con que hoy se calcularían los embeddings de la cuenta y
        `embeddings_por_modelo` cuántos fragmentos hay de cada uno. `reindexar` avisa que hay fragmentos de otro
        modelo: la búsqueda no los considera hasta que se vuelvan a indexar.
        """
        available = self.is_ready()
        total = self.repo.count_embeddings() if available else 0
        por_modelo = self.repo.count_by_model() if available else {}
        modelo = self.embedder.modelo_actual()
        de_otro_modelo = sum(cantidad for nombre, cantidad in por_modelo.items() if nombre != modelo)
        almacen_nombre = getattr(self.repo, "nombre", "desconocido")
        stats = {
            "almacen": almacen_nombre,
            "indice_disponible": available,
            "vector_extension": almacen_nombre if available else "disconnected",
            "motivo_no_disponible": self.repo.motivo_no_disponible if not available else None,
            "total_embeddings": total,
            "embedding_model": modelo,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "embeddings_por_modelo": por_modelo,
            "reindexar": de_otro_modelo > 0,
            "aviso": (
                f"Hay {de_otro_modelo} fragmentos indexados con otro modelo de embeddings: la búsqueda no los "
                f"considera. Volvé a indexarlos para buscarlos con «{modelo}»."
                if de_otro_modelo
                else None
            ),
        }
        if almacen_nombre == "pgvector":
            stats["postgres_connected"] = available
        return stats

    def detalle_del_embedding(self) -> dict[str, Any]:
        """Con qué se calculó el último embedding del servicio, para decirlo junto al resultado."""
        ultimo = self.ultimo_embedding
        if ultimo is None:
            return {}
        return {
            "embedding_model": ultimo.modelo,
            "provider_used": ultimo.proveedor,
            "motivo_sin_ia": ultimo.motivo_sin_ia,
        }

    def _ya_indexado(self, db_conn, source_type: str, source_id: str, huella: str, modelo: str) -> bool:
        """Si la fuente no cambió desde la última vez y sus fragmentos con este modelo siguen en el almacén en uso."""
        if _leer_hash(db_conn, self.user_id, source_type, source_id) != huella:
            return False
        return self.repo.count_embeddings(source_type=source_type, source_id=source_id, embedding_model=modelo) > 0

    def sync_catalog(self, db_conn) -> dict[str, Any]:
        """Indexa todos los materiales y notas de la cuenta hacia el almacén de vectores activo, salteando lo que no cambió.

        La huella de cada fuente es su texto más el modelo de embeddings: cambiar de modelo vuelve a indexar todo.
        Una fuente con la misma huella se vuelve a indexar igual si sus fragmentos ya no están en el almacén (se
        vació el almacén o se borraron).
        """
        if not self.is_ready():
            motivo = self.repo.motivo_no_disponible or "no disponible"
            raise RuntimeError(f"El índice de búsqueda no está disponible: {motivo}")

        # El modelo con que de verdad se calcula hoy (si el proveedor de la cuenta falla, cae al local); con el
        # nombre que da `modelo_actual` nada se saltearía mientras el proveedor siga fallando
        try:
            modelo = self.embedder.embeber("indexar todo").modelo
        except Exception as err:  # noqa: BLE001 - sin sondeo se usa el nombre del modelo; cada fuente cuenta su falla
            logger.warning("No se pudo sondear el modelo de embeddings: %s", err)
            modelo = self.embedder.modelo_actual()
        conteo = {"materiales_indexados": 0, "notas_indexadas": 0, "salteados": 0, "fallidos": 0, "total_chunks": 0}

        def indexar(source_type: str, source_id: str, titulo: str, texto: str, metadata: dict, clave: str) -> None:
            if not texto.strip():
                return
            huella = _huella(modelo, texto)
            try:
                if self._ya_indexado(db_conn, source_type, source_id, huella, modelo):
                    conteo["salteados"] += 1
                    return
                conteo["total_chunks"] += self.index_document(
                    source_type=source_type, source_id=source_id, source_title=titulo, content=texto, metadata=metadata
                )
                # El modelo con que se calcularon de verdad (la IA de la cuenta puede caer al respaldo local)
                usado = self.ultimo_embedding.modelo if self.ultimo_embedding else modelo
                if usado != modelo:
                    huella = _huella(usado, texto)
                _guardar_hash(db_conn, self.user_id, source_type, source_id, huella)
                conteo[clave] += 1
            except Exception as err:  # noqa: BLE001 - una fuente que falla no frena las demás; se cuenta
                logger.warning("Error al indexar %s %s: %s", source_type, source_id, err)
                conteo["fallidos"] += 1

        # 1. Materiales de la cuenta
        almacen = AlmacenDeMateriales(db_conn, self.user_id)
        for m in almacen.listar():
            try:
                texto = almacen.obtener(m["id"], con_texto=True).get("texto", "")
            except MaterialNoEncontrado:
                continue
            indexar(
                TIPO_DE_FUENTE_MATERIAL, str(m["id"]), m["nombre"], texto, {"extension": m.get("extension")},
                "materiales_indexados",
            )

        # 2. Notas de las carpetas elegidas para el tutor ("Mis notas")
        carpetas = carpetas_del_tutor(db_conn, self.user_id)
        reader = VaultReader(vault_de_la_cuenta(db_conn, self.user_id), carpetas=carpetas)
        for nota in reader.list_notes():
            indexar(
                TIPO_DE_FUENTE_NOTA, nota.path or nota.id, nota.title, nota.content or "",
                {"folder": nota.folder, "path": nota.path}, "notas_indexadas",
            )

        return {
            "indexados": conteo["materiales_indexados"] + conteo["notas_indexadas"],
            **conteo,
        }

    def _libro_de_la_cuenta(self, db_conn, book_id: int):
        from aulento.db.repository import LibroRepository

        book = LibroRepository(db_conn, self.user_id).get_by_id(book_id)
        if not book:
            raise FuenteNoEncontrada("Libro", book_id)
        return book

    def _curso_de_la_cuenta(self, db_conn, course_id: int):
        from aulento.db.repository import CursoRepository

        curso = CursoRepository(db_conn, self.user_id).get_by_id(course_id)
        if not curso:
            raise FuenteNoEncontrada("Curso", course_id)
        return curso

    def _indexar_libro(self, book) -> dict[str, Any]:
        content = f"Libro: {book.titulo}\nCapítulos: {book.capitulo_actual}/{book.total_capitulos}\nPáginas: {book.pagina_actual}/{book.total_paginas}\nEstado: {book.estado.value if hasattr(book.estado, 'value') else book.estado}"
        if book.ruta_vault:
            content += f"\nObsidian Vault: {book.ruta_vault}"

        chunks = self.index_document(
            source_type="book",
            source_id=str(book.id),
            source_title=book.titulo,
            content=content,
            metadata={"capitulo_actual": book.capitulo_actual, "total_capitulos": book.total_capitulos},
        )
        return {"source_id": str(book.id), "title": book.titulo, "type": "book", "chunks": chunks}

    def _indexar_curso(self, c) -> dict[str, Any]:
        content = f"Curso: {c.nombre_curso}\nPlataforma: {c.nombre_plataforma or 'Externa'}\nProgreso: {c.progreso_pct}%\nEstado: {c.estado.value if hasattr(c.estado, 'value') else c.estado}\nPrioridad: {c.prioridad.value if hasattr(c.prioridad, 'value') else c.prioridad}\nAula: {c.url_aula}"
        if c.url_drive:
            content += f"\nGoogle Drive: {c.url_drive}"
        if c.ruta_local:
            content += f"\nCarpeta Local: {c.ruta_local}"
        if c.url_notion:
            content += f"\nNotion: {c.url_notion}"
        if c.ruta_obsidian:
            content += f"\nObsidian: {c.ruta_obsidian}"

        chunks = self.index_document(
            source_type="course",
            source_id=str(c.id),
            source_title=c.nombre_curso,
            content=content,
            metadata={"plataforma": c.nombre_plataforma, "progreso": c.progreso_pct},
        )
        return {"source_id": str(c.id), "title": c.nombre_curso, "type": "course", "chunks": chunks}

    def index_single_book(self, db_conn, book_id: int) -> dict[str, Any]:
        """Indexa un libro de la cuenta hacia PostgreSQL pgvector; uno ajeno o inexistente levanta `FuenteNoEncontrada`."""
        if not self.is_ready():
            motivo = self.repo.motivo_no_disponible or "no disponible"
            raise RuntimeError(f"El índice de búsqueda no está disponible: {motivo}")
        return self._indexar_libro(self._libro_de_la_cuenta(db_conn, book_id))

    def index_single_course(self, db_conn, course_id: int) -> dict[str, Any]:
        """Indexa un curso de la cuenta hacia PostgreSQL pgvector; uno ajeno o inexistente levanta `FuenteNoEncontrada`."""
        if not self.is_ready():
            motivo = self.repo.motivo_no_disponible or "no disponible"
            raise RuntimeError(f"El índice de búsqueda no está disponible: {motivo}")
        return self._indexar_curso(self._curso_de_la_cuenta(db_conn, course_id))

    def index_single_material(self, material_id: int, almacen: AlmacenDeMateriales | None = None) -> dict[str, Any]:
        """Indexa en pgvector el texto completo de un material de la cuenta; uno ajeno levanta `FuenteNoEncontrada`.

        `almacen` es el `AlmacenDeMateriales` de la cuenta; sin él se arma uno con conexión propia.
        """
        if not self.is_ready():
            motivo = self.repo.motivo_no_disponible or "no disponible"
            raise RuntimeError(f"El índice de búsqueda no está disponible: {motivo}")
        return self._indexar_material(self._material_de_la_cuenta(material_id, almacen))

    def _material_de_la_cuenta(self, material_id: int, almacen: AlmacenDeMateriales | None) -> dict[str, Any]:
        almacen = almacen or AlmacenDeMateriales.con_conexion_propia(self.user_id)
        if almacen.user_id != self.user_id:
            raise ValueError("El almacén de materiales tiene que ser de la misma cuenta que el servicio.")
        try:
            return almacen.obtener(material_id)
        except MaterialNoEncontrado:
            raise FuenteNoEncontrada("Material", material_id) from None

    def _indexar_material(self, material: dict[str, Any]) -> dict[str, Any]:
        chunks = self.index_document(
            source_type=TIPO_DE_FUENTE_MATERIAL,
            source_id=str(material["id"]),
            source_title=material["nombre"],
            content=material["texto"],
            metadata={"extension": material["extension"]},
        )
        return {"source_id": str(material["id"]), "title": material["nombre"], "type": TIPO_DE_FUENTE_MATERIAL, "chunks": chunks}

    def index_selection(self, db_conn, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Indexa un lote de items seleccionados por el usuario (libros, cursos y materiales subidos).

        Todos se resuelven antes de indexar: si uno no es de la cuenta, no se indexa ninguno.
        """
        if not self.is_ready():
            motivo = self.repo.motivo_no_disponible or "no disponible"
            raise RuntimeError(f"El índice de búsqueda no está disponible: {motivo}")

        pendientes: list[Callable[[], dict[str, Any]]] = []
        for it in items:
            itype = it.get("type")
            iid = it.get("id")
            if itype == "book":
                try:
                    num_id = int(iid)
                except (ValueError, TypeError):
                    raise ValueError(f"Identificador de libro inválido: '{iid}'. Debe ser un número entero.")
                libro = self._libro_de_la_cuenta(db_conn, num_id)
                pendientes.append(lambda libro=libro: self._indexar_libro(libro))
            elif itype == "course":
                try:
                    num_id = int(iid)
                except (ValueError, TypeError):
                    raise ValueError(f"Identificador de curso inválido: '{iid}'. Debe ser un número entero.")
                curso = self._curso_de_la_cuenta(db_conn, num_id)
                pendientes.append(lambda curso=curso: self._indexar_curso(curso))
            elif itype == TIPO_DE_FUENTE_MATERIAL:
                try:
                    num_id = int(iid)
                except (ValueError, TypeError):
                    raise ValueError(f"Identificador de material inválido: '{iid}'. Debe ser un número entero.")
                material = self._material_de_la_cuenta(num_id, AlmacenDeMateriales(db_conn, self.user_id))
                pendientes.append(lambda material=material: self._indexar_material(material))
            else:
                raise ValueError(f"Tipo de ítem no reconocido para indexación: '{itype}'")

        indexed_items = [indexar() for indexar in pendientes]
        total_chunks = sum(res["chunks"] for res in indexed_items)
        return {"total_indexed": len(indexed_items), "total_chunks": total_chunks, "items": indexed_items}


    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> list[str]:
        """Divide texto en fragmentos con solapamiento respetando su estructura."""
        return [f.texto for f in fragmentar(text, "", tamano=chunk_size, solapamiento=chunk_overlap)]
