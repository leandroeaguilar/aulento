"""Herramientas MCP para Repetición Espaciada (FSRS v5) y Práctica de Inglés / Conceptos Técnicos."""

import logging
from pathlib import Path
from typing import Any

from aulento.db.connection import get_connection
from aulento.db.fsrs_repository import FSRSRepository
from aulento.fsrs.engine import FSRSEngine
from aulento.models.fsrs_card import FSRSCardCreate, FSRSRating
from aulento.mcp.security import cuenta_mcp_actual, herramienta_auditada, log_mcp_tool_execution

logger = logging.getLogger(__name__)


def register_fsrs_tools(server: Any, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Registra las herramientas de repetición espaciada FSRS v5 en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_get_fsrs_due_cards(category: str = "", limit: int = 5) -> str:
        """Obtiene las tarjetas de estudio que vencen hoy según el algoritmo FSRS v5.
        
        Permite al LLM iniciar un drill interactivo de preguntas y respuestas con el usuario.
        
        Args:
            category: Filtrar por categoría (opcional, ej. 'ingles_tecnico', 'roadmap_1').
            limit: Número máximo de tarjetas a recuperar (por defecto 5).
        """
        try:
            conn = get_connection(db_path)
            try:
                repo = FSRSRepository(conn, cuenta_mcp_actual())
                limit = min(max(1, limit), 50)
                categoria = category.strip() or None
                cards = repo.get_due_cards(limit=limit, categoria=categoria)

                if cards:
                    lines = [f"### 🧠 Tarjetas FSRS v5 vencidas para repaso ({len(cards)}):"]
                else:
                    # Sin vencidas: se ofrecen tarjetas para práctica extra, dicho con claridad
                    cards = repo.get_due_cards(limit=limit, categoria=categoria, force=True)
                    donde = f" en la categoría '{categoria}'" if categoria else ""
                    if not cards:
                        return f"No hay tarjetas de memoria registradas{donde} en el banco de FSRS."
                    lines = [
                        f"### 🧠 No hay tarjetas vencidas hoy{donde}. Práctica extra opcional ({len(cards)} tarjetas que todavía no vencen):"
                    ]

                for c in cards:
                    lines.append(
                        f"- **[Card ID: {c.id}]** ({c.categoria})\n"
                        f"  ❓ **Pregunta:** {c.item_pregunta}\n"
                        f"  💡 **Respuesta:** {c.respuesta_esperada}\n"
                        f"  📌 **Contexto:** {c.contexto_uso or 'General'}\n"
                        f"  • Repeticiones: {c.reps} | Estabilidad: {c.stability or 0.0:.1f} | Dificultad: {c.difficulty or 0.0:.1f}"
                    )
                log_mcp_tool_execution("study_get_fsrs_due_cards", {"category": category, "limit": limit}, status="success", db_path=db_path)
                return "\n".join(lines)
            finally:
                conn.close()
        except Exception as e:
            log_mcp_tool_execution("study_get_fsrs_due_cards", {"category": category}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al obtener tarjetas FSRS: {e}"

    if not read_only:
        @tool()
        def study_review_fsrs_card(card_id: int, rating: int) -> str:
            """Registra la calificación de repaso de una tarjeta usando el algoritmo FSRS v5.
            
            Args:
                card_id: ID de la tarjeta en fsrs_items.
                rating: Calificación del usuario: 1 = Again (Olvido total), 2 = Hard (Difícil), 3 = Good (Bien), 4 = Easy (Fácil).
            """
            try:
                if rating not in (1, 2, 3, 4):
                    return "Error: rating debe ser 1 (Again), 2 (Hard), 3 (Good) o 4 (Easy)."

                conn = get_connection(db_path)
                try:
                    repo = FSRSRepository(conn, cuenta_mcp_actual())
                    engine = FSRSEngine(repo)
                    rating_enum = FSRSRating(int(rating))
                    updated_card, review_log = engine.review(card_id=card_id, rating=rating_enum)

                    rating_names = {1: "Again 🔴", 2: "Hard 🟠", 3: "Good 🟢", 4: "Easy 🔵"}
                    result = (
                        f"✅ **Repaso FSRS registrado:**\n"
                        f"- **Card ID:** {updated_card.id}\n"
                        f"- **Calificación:** {rating_names[rating]}\n"
                        f"- **Próximo Repaso (Due):** {updated_card.due}\n"
                        f"- **Nueva Estabilidad:** {updated_card.stability:.2f} días\n"
                        f"- **Dificultad:** {updated_card.difficulty:.2f}"
                    )
                    log_mcp_tool_execution("study_review_fsrs_card", {"card_id": card_id, "rating": rating}, status="success", db_path=db_path)
                    return result
                finally:
                    conn.close()
            except Exception as e:
                log_mcp_tool_execution("study_review_fsrs_card", {"card_id": card_id, "rating": rating}, status="error", error_message=str(e), db_path=db_path)
                return f"Error al procesar calificación FSRS para tarjeta {card_id}: {e}"

        @tool()
        def study_create_flashcard(
            question: str,
            answer: str,
            context: str = "",
            category: str = "general",
        ) -> str:
            """Crea una nueva tarjeta de estudio en el banco de memoria FSRS v5.
            
            Args:
                question: Pregunta o concepto a recordar.
                answer: Respuesta esperada, colocación o traducción.
                context: Contexto de uso, frase de ejemplo o nota pedagógica.
                category: Categoría ('ingles_tecnico', 'software_arch', 'data_ai', etc.).
            """
            try:
                conn = get_connection(db_path)
                try:
                    repo = FSRSRepository(conn, cuenta_mcp_actual())
                    card = repo.create_card(FSRSCardCreate(
                        item_pregunta=question.strip(),
                        respuesta_esperada=answer.strip(),
                        contexto_uso=context.strip() or None,
                        categoria=category.strip(),
                    ))
                    result = (
                        f"🎉 **Tarjeta FSRS creada:**\n"
                        f"- **ID:** {card.id}\n"
                        f"- **Categoría:** {card.categoria}\n"
                        f"- **Pregunta:** {card.item_pregunta}\n"
                        f"- **Respuesta:** {card.respuesta_esperada}"
                    )
                    log_mcp_tool_execution("study_create_flashcard", {"question": question, "category": category}, status="success", db_path=db_path)
                    return result
                finally:
                    conn.close()
            except Exception as e:
                log_mcp_tool_execution("study_create_flashcard", {"question": question}, status="error", error_message=str(e), db_path=db_path)
                return f"Error al crear tarjeta FSRS: {e}"
