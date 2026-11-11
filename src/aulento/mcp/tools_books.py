"""Herramientas MCP para consulta y actualización del Reading Tracker (Libros Técnicos por Páginas y Capítulos)."""

import logging
from pathlib import Path
from typing import Any

from aulento.db.connection import get_connection
from aulento.db.repository import LibroRepository
from aulento.mcp.security import (
    cuenta_mcp_actual,
    herramienta_auditada,
    log_mcp_tool_execution,
)
from aulento.models.libro import EstadoLibro, LibroCreate

logger = logging.getLogger(__name__)


def register_book_tools(server: Any, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Registra las herramientas de seguimiento de lectura de libros en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_list_books(status: str = "all") -> str:
        """Lista los libros técnicos en seguimiento en Aulento con su avance por páginas y capítulos.
        
        Args:
            status: 'all', 'leyendo', 'pausado', o 'completado'.
        """
        try:
            conn = get_connection(db_path)
            try:
                repo = LibroRepository(conn, cuenta_mcp_actual())
                st_filter = EstadoLibro(status) if status in ("leyendo", "pausado", "completado") else None
                books = repo.list_all(estado=st_filter)

                if not books:
                    return "No se encontraron libros registrados en la base de datos."

                lines = ["### 📖 Libros Técnicos en Reading Tracker:"]
                for b in books:
                    pag_info = f"Pág. {b.pagina_actual}/{b.total_paginas}" if b.total_paginas else f"Pág. {b.pagina_actual}"
                    cap_info = f"Cap. {b.capitulo_actual}/{b.total_capitulos}"
                    lines.append(
                        f"- **[{b.id}] {b.titulo}**\n"
                        f"  • Avance: **{b.porcentaje_leido:.1f}%** ({pag_info} • {cap_info})\n"
                        f"  • Estado: {b.estado.value} | Vault: {b.ruta_vault or 'No asignada'}"
                    )
                log_mcp_tool_execution("study_list_books", {"status": status}, status="success", db_path=db_path)
                return "\n".join(lines)
            finally:
                conn.close()
        except Exception as e:
            log_mcp_tool_execution("study_list_books", {"status": status}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al listar libros: {e}"

    if not read_only:
        @tool()
        def study_update_book_progress(
            book_identifier: str,
            current_page: int | None = None,
            total_pages: int | None = None,
            current_chapter: int | None = None,
            total_chapters: int | None = None,
            status: str = "",
        ) -> str:
            """Actualiza el progreso de lectura de un libro por número de página o capítulo.
            
            book_identifier puede ser el ID numérico del libro o su título aproximado (ej. 'Designing Data-Intensive').
            
            Args:
                book_identifier: ID del libro o título.
                current_page: Página actual leída (opcional).
                total_pages: Total de páginas del libro (opcional).
                current_chapter: Capítulo actual leído (opcional).
                total_chapters: Total de capítulos del libro (opcional).
                status: 'leyendo', 'pausado', o 'completado' (opcional).
            """
            try:
                conn = get_connection(db_path)
                try:
                    repo = LibroRepository(conn, cuenta_mcp_actual())
                    libro = None
                    ident = book_identifier.strip()
                    if ident.isdigit():
                        libro = repo.get_by_id(int(ident))
                    if not libro:
                        libro = repo.find_by_title(ident)

                    if not libro:
                        return f"Error: No se encontró ningún libro que coincida con '{book_identifier}'."

                    estado_pedido = status.strip().lower() if status else ""
                    if estado_pedido and estado_pedido not in ("leyendo", "pausado", "completado"):
                        return f"Error: status '{status}' no es válido. Usá 'leyendo', 'pausado' o 'completado'."
                    st_enum = EstadoLibro(estado_pedido) if estado_pedido else None

                    try:
                        updated = repo.update_progress(
                            id=libro.id,
                            pagina_actual=current_page,
                            total_paginas=total_pages,
                            capitulo_actual=current_chapter,
                            total_capitulos=total_chapters,
                            estado=st_enum,
                        )
                    except ValueError as e:
                        return f"Error: no se actualizó '{libro.titulo}'. {e}"

                    if not updated:
                        return f"Error: no se encontró o no se pudo actualizar el libro '{book_identifier}'."

                    pag_str = f"Pág. {updated.pagina_actual}/{updated.total_paginas}" if updated.total_paginas else f"Pág. {updated.pagina_actual}"
                    cap_str = f"Cap. {updated.capitulo_actual}/{updated.total_capitulos}"
                    result = (
                        f"✅ **Lectura actualizada exitosamente:**\n"
                        f"- **Libro:** {updated.titulo} [ID: {updated.id}]\n"
                        f"- **Progreso Total:** {updated.porcentaje_leido:.1f}%\n"
                        f"- **Detalle:** {pag_str} • {cap_str}\n"
                        f"- **Estado:** {updated.estado.value}"
                    )
                    log_mcp_tool_execution(
                        "study_update_book_progress",
                        {"identifier": book_identifier, "page": current_page, "chapter": current_chapter},
                        status="success",
                        db_path=db_path,
                    )
                    return result
                finally:
                    conn.close()
            except Exception as e:
                log_mcp_tool_execution(
                    "study_update_book_progress",
                    {"identifier": book_identifier},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al actualizar libro '{book_identifier}': {e}"

        @tool()
        def study_add_book(
            title: str,
            total_pages: int | None = None,
            total_chapters: int = 10,
            current_page: int = 0,
            current_chapter: int = 1,
            vault_path: str = "",
        ) -> str:
            """Añade un nuevo libro técnico al Reading Tracker de Aulento.
            
            Args:
                title: Título de la obra o libro técnico.
                total_pages: Cantidad total de páginas (ej. 560).
                total_chapters: Cantidad total de capítulos (por defecto 10).
                current_page: Página actual leída (por defecto 0).
                current_chapter: Capítulo inicial (por defecto 1).
                vault_path: Nombre o ruta del apunte en Obsidian Vault (opcional).
            """
            try:
                conn = get_connection(db_path)
                try:
                    repo = LibroRepository(conn, cuenta_mcp_actual())
                    nuevo = repo.create(LibroCreate(
                        titulo=title.strip(),
                        total_capitulos=total_chapters,
                        capitulo_actual=current_chapter,
                        total_paginas=total_pages,
                        pagina_actual=current_page,
                        ruta_vault=vault_path.strip() or None,
                        estado=EstadoLibro.LEYENDO,
                    ))

                    pag_str = f"Páginas: {nuevo.pagina_actual}/{nuevo.total_paginas}" if nuevo.total_paginas else f"Página actual: {nuevo.pagina_actual}"
                    result = (
                        f"🎉 **Libro añadido al Reading Tracker:**\n"
                        f"- **ID:** {nuevo.id}\n"
                        f"- **Título:** {nuevo.titulo}\n"
                        f"- **Avance:** {nuevo.porcentaje_leido:.1f}% ({pag_str} • Cap. {nuevo.capitulo_actual}/{nuevo.total_capitulos})\n"
                        f"- **Estado:** {nuevo.estado.value}"
                    )
                    log_mcp_tool_execution(
                        "study_add_book",
                        {"title": title, "total_pages": total_pages},
                        status="success",
                        db_path=db_path,
                    )
                    return result
                finally:
                    conn.close()
            except Exception as e:
                log_mcp_tool_execution(
                    "study_add_book",
                    {"title": title},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al registrar libro '{title}': {e}"

        @tool()
        def study_sync_google_books() -> str:
            """Sincroniza las estanterías de lectura y posiciones con Google Play Libros."""
            try:
                conn = get_connection(db_path)
                try:
                    from aulento.connectors.google_books import (
                        GoogleBooksConnector,
                    )
                    connector = GoogleBooksConnector(conn, cuenta_mcp_actual())
                    if not connector.esta_autorizado():
                        return "Google Play Libros no está vinculado a esta cuenta. Autorizalo desde la interfaz web o Configuración."
                    res = connector.sincronizar()
                    lineas = [
                        "### 📚 Sincronización con Google Play Libros completada:",
                        f"- Libros procesados: **{res['sincronizados']}**",
                        f"- Nuevos importados: **{res['creados']}**",
                        f"- Actualizados: **{res['actualizados']}**",
                    ]
                    for d in res.get("detalles", []):
                        lineas.append(f"  • {d['titulo']} ({d['accion']}) -> pág. {d['pagina']}")
                    log_mcp_tool_execution("study_sync_google_books", {}, status="success", db_path=db_path)
                    return "\n".join(lineas)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution("study_sync_google_books", {}, status="error", error_message=str(e), db_path=db_path)
                return f"Error al sincronizar con Google Play Libros: {e}"

        @tool()
        def study_book_active_recall_generate(
            book_identifier: str,
            count: int = 3,
            chapter: int | None = None,
            page: int | None = None,
        ) -> str:
            """Genera preguntas conceptuales de Active Recall sobre el tramo leído de un libro técnico.
            
            Args:
                book_identifier: ID numérico o fragmento del título del libro.
                count: Cantidad de preguntas a generar (por defecto 3).
                chapter: Capítulo específico a evaluar (opcional).
                page: Página específica de referencia (opcional).
            """
            try:
                conn = get_connection(db_path)
                try:
                    repo = LibroRepository(conn, cuenta_mcp_actual())
                    book = None
                    if book_identifier.strip().isdigit():
                        book = repo.get_by_id(int(book_identifier.strip()))
                    if not book:
                        book = repo.find_by_title(book_identifier.strip())

                    if not book:
                        return f"No se encontró ningún libro con el identificador '{book_identifier}'."

                    from aulento.core.book_active_recall import (
                        BookActiveRecallService,
                    )
                    from aulento.models.book_active_recall import (
                        ActiveRecallGenerateRequest,
                    )

                    service = BookActiveRecallService(conn, cuenta_mcp_actual())
                    req = ActiveRecallGenerateRequest(
                        capitulo_desde=chapter,
                        capitulo_hasta=chapter,
                        pagina_desde=page,
                        pagina_hasta=page,
                        cantidad=count,
                    )
                    res = service.generar_preguntas(book.id, req)

                    out = [
                        f"### 🧠 Active Recall: {res.titulo}",
                        f"**Tramo evaluado:** {res.tramo_evaluado}\n",
                    ]
                    for p in res.preguntas:
                        out.append(f"**Pregunta {p.id}:** {p.pregunta}")
                        out.append(f"  *Objetivo:* {p.objetivo_conceptual}\n")

                    log_mcp_tool_execution("study_book_active_recall_generate", {"book_id": book.id}, status="success", db_path=db_path)
                    return "\n".join(out)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution("study_book_active_recall_generate", {"book_identifier": book_identifier}, status="error", error_message=str(e), db_path=db_path)
                return f"Error al generar Active Recall: {e}"

        @tool()
        def study_book_active_recall_evaluate(
            book_identifier: str,
            answers_json: str,
            section_evaluated: str = "",
        ) -> str:
            """Evalúa las respuestas de un estudiante a un cuestionario de Active Recall sobre un libro.
            
            Args:
                book_identifier: ID numérico o título del libro.
                answers_json: JSON con lista de respuestas: [{"question_id": 1, "pregunta": "...", "respuesta_usuario": "..."}].
                section_evaluated: Descripción del tramo evaluado (opcional).
            """
            try:
                conn = get_connection(db_path)
                try:
                    import json
                    repo = LibroRepository(conn, cuenta_mcp_actual())
                    book = None
                    if book_identifier.strip().isdigit():
                        book = repo.get_by_id(int(book_identifier.strip()))
                    if not book:
                        book = repo.find_by_title(book_identifier.strip())

                    if not book:
                        return f"No se encontró ningún libro con el identificador '{book_identifier}'."

                    from aulento.core.book_active_recall import (
                        BookActiveRecallService,
                    )
                    from aulento.models.book_active_recall import (
                        ActiveRecallEvaluateRequest,
                        UserAnswerItem,
                    )

                    raw_answers = json.loads(answers_json)
                    items = [UserAnswerItem(**a) for a in raw_answers]

                    service = BookActiveRecallService(conn, cuenta_mcp_actual())
                    req = ActiveRecallEvaluateRequest(
                        tramo_evaluado=section_evaluated or f"Cap. {book.capitulo_actual}",
                        respuestas=items,
                    )
                    res = service.evaluar_respuestas(book.id, req)

                    out = [
                        f"### 📊 Resultado de Active Recall: {res.titulo}",
                        f"**Calificación global:** {res.score_global}% ({res.veredicto})",
                        f"**Resumen:** {res.resumen_pedagogico}\n",
                    ]
                    for ev in res.evaluaciones:
                        out.append(f"**P{ev.question_id} (Puntaje: {ev.puntaje}/100)**")
                        if ev.aciertos:
                            out.append(f"- ✓ Aciertos: {ev.aciertos}")
                        if ev.mejoras:
                            out.append(f"- ⚠ A profundizar: {ev.mejoras}")
                        if ev.explicacion_optima:
                            out.append(f"- ℹ Explicación óptima: {ev.explicacion_optima}\n")

                    log_mcp_tool_execution("study_book_active_recall_evaluate", {"book_id": book.id}, status="success", db_path=db_path)
                    return "\n".join(out)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution("study_book_active_recall_evaluate", {"book_identifier": book_identifier}, status="error", error_message=str(e), db_path=db_path)
                return f"Error al evaluar Active Recall: {e}"

        @tool()
        def study_book_harvest_cards(
            book_identifier: str,
            count: int = 5,
            chapter: int | None = None,
        ) -> str:
            """Cosecha y guarda automáticamente tarjetas FSRS de inglés y conceptos técnicos desde el libro.
            
            Args:
                book_identifier: ID numérico o título del libro.
                count: Cantidad de tarjetas a extraer (por defecto 5).
                chapter: Capítulo específico a cosechar (opcional).
            """
            try:
                conn = get_connection(db_path)
                try:
                    repo = LibroRepository(conn, cuenta_mcp_actual())
                    book = None
                    if book_identifier.strip().isdigit():
                        book = repo.get_by_id(int(book_identifier.strip()))
                    if not book:
                        book = repo.find_by_title(book_identifier.strip())

                    if not book:
                        return f"No se encontró ningún libro con el identificador '{book_identifier}'."

                    from aulento.core.book_active_recall import (
                        BookActiveRecallService,
                    )
                    from aulento.models.book_active_recall import (
                        BookHarvestCommitRequest,
                        BookHarvestPreviewRequest,
                    )

                    service = BookActiveRecallService(conn, cuenta_mcp_actual())
                    prev = service.previsualizar_cosecha(
                        book.id,
                        BookHarvestPreviewRequest(capitulo=chapter, cantidad=count),
                    )
                    com = service.confirmar_cosecha(book.id, BookHarvestCommitRequest(cards=prev.cards))

                    out = [
                        f"### 🃏 Cosecha FSRS completada para '{prev.titulo}' ({prev.tramo}):",
                        f"- Tarjetas añadidas al mazo FSRS: **{com.guardadas}**",
                        f"- Duplicadas omitidas: **{com.omitidas_duplicadas}**\n",
                        "**Tarjetas generadas:**",
                    ]
                    for c in prev.cards:
                        out.append(f"• **{c.item_pregunta}**: {c.respuesta_esperada}")

                    log_mcp_tool_execution("study_book_harvest_cards", {"book_id": book.id, "guardadas": com.guardadas}, status="success", db_path=db_path)
                    return "\n".join(out)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution("study_book_harvest_cards", {"book_identifier": book_identifier}, status="error", error_message=str(e), db_path=db_path)
                return f"Error al cosechar tarjetas FSRS: {e}"
