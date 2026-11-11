"""Herramientas MCP para búsqueda semántica vectorial sobre PostgreSQL + pgvector."""

import logging
from pathlib import Path
from typing import Any

from aulento.core.knowledge_rag import KnowledgeRAGService
from aulento.mcp.security import (
    cuenta_mcp_actual,
    herramienta_auditada,
    log_mcp_tool_execution,
)

logger = logging.getLogger(__name__)


def register_vector_tools(server: Any, db_path: Path | str | None = None) -> None:
    """Registra la herramienta de búsqueda semántica en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_semantic_search(
        query: str,
        limit: int = 5,
        source_type: str = "",
        min_similarity: float = 0.4,
    ) -> str:
        """Realiza una búsqueda semántica sobre los fragmentos vectoriales de la cuenta (Obsidian, libros, cursos).
        
        Utiliza los embeddings del proveedor de IA de la cuenta y búsqueda por similitud de coseno en
        el almacén de vectores, solo entre los fragmentos indexados con el modelo de la consulta.
        
        Args:
            query: Pregunta o concepto en lenguaje natural (ej. 'técnicas de particionado en BigQuery').
            limit: Número máximo de fragmentos a recuperar (1 a 20).
            source_type: Filtro opcional: 'obsidian_note', 'book_chunk', 'course_topic', o vacío para todos.
            min_similarity: Umbral de similitud mínima (entre 0.0 y 1.0, default 0.4).
        """
        try:
            service = KnowledgeRAGService(cuenta_mcp_actual())
            if not service.is_ready():
                motivo = service.repo.motivo_no_disponible or "no disponible"
                return (
                    f"⚠️ El índice de búsqueda vectorial no está disponible ({motivo}).\n"
                    "Aulento continuará funcionando normalmente con búsqueda por palabras para el resto de herramientas."
                )

            st_filter = source_type.strip() if source_type and source_type.strip() else None
            matches = service.search(
                query=query,
                limit=min(max(1, limit), 20),
                source_type=st_filter,
                min_similarity=min_similarity,
            )

            detalle = service.detalle_del_embedding()
            con_que = f"Modelo de embeddings de la consulta: {detalle.get('embedding_model')}."
            if detalle.get("motivo_sin_ia"):
                con_que += f" Sin embeddings de IA: {detalle['motivo_sin_ia']}"

            if not matches:
                return (
                    f"No se encontraron fragmentos con similitud >= {min_similarity:.2f} para la consulta '{query}'. "
                    f"{con_que} Solo se consideran los fragmentos indexados con ese modelo."
                )

            output = [f"### 🔍 Resultados de Búsqueda Semántica Vectorial para '{query}':", con_que]
            for idx, m in enumerate(matches, 1):
                src_type = m.get("source_type", "recurso")
                title = m.get("source_title", "Sin título")
                sim = m.get("similarity", 0.0)
                text = m.get("chunk_text", "").strip()

                output.append(
                    f"\n**{idx}. {title}** `[{src_type}]` — Similitud: **{sim * 100:.1f}%**\n"
                    f"> {text[:350]}{'...' if len(text) > 350 else ''}"
                )

            log_mcp_tool_execution(
                "study_semantic_search",
                {"query": query, "matches_count": len(matches)},
                status="success",
                db_path=db_path,
            )
            return "\n".join(output)
        except Exception as e:  # noqa: BLE001
            log_mcp_tool_execution(
                "study_semantic_search",
                {"query": query},
                status="error",
                error_message=str(e),
                db_path=db_path,
            )
            return f"Error al ejecutar búsqueda vectorial: {e}"
