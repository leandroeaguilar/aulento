"""Herramientas MCP para consulta de Rutas de Aprendizaje, Temas y Generación de Clases Magistrales."""

import json
import logging
from pathlib import Path
from typing import Any

from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import OrigenClase, EstadoTema, LessonPromptRequest
from aulento.roadmap.lesson_studio import LessonStudio
from aulento.roadmap.prompt_builder import LessonPromptBuilder
from aulento.mcp.security import cuenta_mcp_actual, herramienta_auditada, log_mcp_tool_execution

logger = logging.getLogger(__name__)


def register_lesson_tools(server: Any, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Registra las herramientas de rutas, temas y clases en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_list_roadmaps(category: str = "") -> str:
        """Lista todas las Rutas de Aprendizaje registradas en Aulento.
        
        Args:
            category: Filtrar por categoría (opcional, ej. 'data_ai', 'cloud', 'software_arch', 'ingles_tecnico').
        """
        try:
            repo = RoadmapRepository(cuenta_mcp_actual(), db_path)
            roadmaps = repo.get_roadmaps()
            if category:
                roadmaps = [r for r in roadmaps if r.categoria.lower() == category.lower()]

            if not roadmaps:
                return f"No se encontraron rutas de aprendizaje{' para la categoría ' + category if category else ''}."

            lines = ["### 🗺️ Rutas de Aprendizaje en Aulento:"]
            for r in roadmaps:
                enfoque = getattr(r, "enfoque_estudio", "profesional")
                lines.append(
                    f"- **[{r.id}] {r.titulo}**\n"
                    f"  • Nivel: {r.nivel_objetivo} | Enfoque: {enfoque} | Categoría: {r.categoria}\n"
                    f"  • Progreso: {r.progreso_pct:.1f}%"
                )
            log_mcp_tool_execution("study_list_roadmaps", {"category": category}, status="success", db_path=db_path)
            return "\n".join(lines)
        except Exception as e:
            log_mcp_tool_execution("study_list_roadmaps", {"category": category}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al listar rutas de aprendizaje: {e}"

    @tool()
    def study_get_roadmap_topics(roadmap_id: int | None = None, status: str = "all") -> str:
        """Obtiene la lista de módulos y temas de una ruta de aprendizaje.
        
        Args:
            roadmap_id: ID de la ruta (si se omite, se usa la primera ruta activa encontrada).
            status: Filtrar temas por estado: 'all', 'pendiente', 'en_progreso', o 'completado'.
        """
        try:
            repo = RoadmapRepository(cuenta_mcp_actual(), db_path)
            if roadmap_id is None:
                roadmaps = repo.get_roadmaps()
                if not roadmaps:
                    return "No existen rutas de aprendizaje registradas."
                roadmap_id = roadmaps[0].id
            target_roadmap = repo.get_roadmap(roadmap_id)
            if not target_roadmap:
                return f"Error: No existe una ruta con ID {roadmap_id}."

            modules = target_roadmap.modulos
            if not modules:
                return f"La ruta '{target_roadmap.titulo}' [ID {roadmap_id}] aún no contiene módulos."

            lines = [f"### 📚 Temario de '{target_roadmap.titulo}' (Progreso: {target_roadmap.progreso_pct:.1f}%):"]
            for m in modules:
                topics = m.temas
                if status != "all":
                    topics = [t for t in topics if t.estado.value == status]

                lines.append(f"\n📂 **Módulo {m.orden}: {m.titulo}**")
                if not topics:
                    lines.append("  *(Sin temas que coincidan con el filtro)*")
                    continue

                for t in topics:
                    has_lesson_str = f" [Tiene clase ID {t.clase.id}]" if t.clase else " [Sin clase generada]"
                    icon = "✅" if t.estado == EstadoTema.COMPLETADO else ("🟡" if t.estado == EstadoTema.EN_PROGRESO else "⚪")
                    lines.append(f"  {icon} [ID {t.id}] **{t.titulo}** ({t.estado.value}){has_lesson_str}")

            log_mcp_tool_execution("study_get_roadmap_topics", {"roadmap_id": roadmap_id, "status": status}, status="success", db_path=db_path)
            return "\n".join(lines)
        except Exception as e:
            log_mcp_tool_execution("study_get_roadmap_topics", {"roadmap_id": roadmap_id, "status": status}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al obtener temario de la ruta: {e}"

    @tool()
    def study_get_topic_master_prompt(topic_id: int, include_materials: bool = True, target_llm: str = "claude") -> str:
        """Construye y retorna el Master Prompt pedagógico adaptativo para generar la clase de un tema.
        
        El prompt devuelto se arma con el perfil pedagógico de la ruta (rol docente, secciones y tipo de
        fuentes propios de su disciplina), el contexto del tema y, si se pide, la directiva para consultar
        los materiales subidos por la cuenta. Termina con el bloque de tarjetas Anki/FSRS.
        
        Args:
            topic_id: ID del tema en la ruta de aprendizaje.
            include_materials: Si es True, incluye la directiva de buscar en los materiales subidos (`materials_search`).
            target_llm: 'claude', 'notebooklm', o 'chatgpt'.
        """
        try:
            repo = RoadmapRepository(cuenta_mcp_actual(), db_path)
            ctx = repo.get_topic_with_context(topic_id)
            if not ctx:
                return f"Error: Tema con ID {topic_id} no encontrado en la base de datos."

            builder = LessonPromptBuilder(repo=repo)
            req = LessonPromptRequest(
                include_materials=include_materials,
                target_llm=target_llm,
            )
            resp = builder.build_prompt(topic_id=topic_id, options=req)
            log_mcp_tool_execution("study_get_topic_master_prompt", {"topic_id": topic_id, "target_llm": target_llm}, status="success", db_path=db_path)
            return resp.master_prompt
        except Exception as e:
            log_mcp_tool_execution("study_get_topic_master_prompt", {"topic_id": topic_id}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al generar master prompt para el tema {topic_id}: {e}"

    @tool()
    def study_get_topic_lesson(topic_id: int) -> str:
        """Consulta el contenido Markdown de una clase magistral existente para un tema dado.
        
        Args:
            topic_id: ID del tema cuya clase se desea consultar.
        """
        try:
            repo = RoadmapRepository(cuenta_mcp_actual(), db_path)
            lesson = repo.get_lesson_by_topic_id(topic_id)
            if not lesson:
                return f"El tema con ID {topic_id} no posee aún ninguna clase generada."

            output = [
                f"# {lesson.titulo} (Clase ID: {lesson.id})",
                f"**Origen:** {lesson.origen.value} | **Vault Path:** {lesson.vault_path or 'No sincronizado'}",
                "\n---\n",
                lesson.contenido_markdown,
            ]
            log_mcp_tool_execution("study_get_topic_lesson", {"topic_id": topic_id}, status="success", db_path=db_path)
            return "\n".join(output)
        except Exception as e:
            log_mcp_tool_execution("study_get_topic_lesson", {"topic_id": topic_id}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al consultar clase del tema {topic_id}: {e}"

    if not read_only:
        @tool()
        def study_create_or_update_lesson(
            topic_id: int,
            markdown_content: str,
            sync_vault: bool = True,
            extract_flashcards: bool = True,
            mark_completed: bool = True,
            overwrite: bool = False,
        ) -> str:
            """Crea la clase magistral de un tema con el contenido generado por el LLM, o la reemplaza si se pide.

            Guarda la lección en SQLite, extrae tarjetas para repetición espaciada FSRS v5,
            sincroniza el apunte canónico al Obsidian Vault y marca el tema como completado.
            Si el tema ya tiene una clase, no la toca salvo que `overwrite` sea True; al reemplazar,
            una nota del vault con apuntes hechos a mano se conserva en una copia de respaldo.

            Args:
                topic_id: ID del tema de la ruta.
                markdown_content: Contenido completo de la lección en formato Markdown.
                sync_vault: Si es True, exporta el apunte al Vault de Obsidian ('04 Knowledge/Cursos/...').
                extract_flashcards: Si es True, inyecta las flashcards (bloque ```cards-fsrs) en FSRS v5.
                mark_completed: Si es True, marca el tema como 'completado'; si es False, conserva su estado.
                overwrite: Si es True, reemplaza la clase que el tema ya tenga. Por defecto no la reemplaza.
            """
            try:
                repo = RoadmapRepository(cuenta_mcp_actual(), db_path)
                ctx = repo.get_topic_with_context(topic_id)
                if not ctx:
                    return f"Error: No existe el tema con ID {topic_id}."

                if not markdown_content or not markdown_content.strip():
                    return "Error: markdown_content está vacío; no se guardó nada."

                existente = repo.get_lesson_by_topic_id(topic_id)
                if existente and not overwrite:
                    log_mcp_tool_execution(
                        "study_create_or_update_lesson",
                        {"topic_id": topic_id, "overwrite": False},
                        status="error",
                        error_message="el tema ya tiene una clase",
                        db_path=db_path,
                    )
                    return (
                        f"⚠️ El tema '{ctx['topic_title']}' [ID: {topic_id}] ya tiene una clase guardada "
                        f"(ID {existente.id}, {len(existente.contenido_markdown or '')} caracteres, origen {existente.origen.value}). "
                        "No se modificó nada. Para reemplazarla, confirmá con el usuario y volvé a llamar con overwrite=true "
                        "(la clase actual quedará guardada como versión anterior y se podrá restaurar); "
                        "podés leer la actual con study_get_topic_lesson."
                    )

                studio = LessonStudio(repo=repo)
                estado_previo = ctx.get("topic_status")

                def nota_ajena(lesson_id: int) -> bool:
                    try:
                        return studio.vault_note_was_edited(lesson_id)
                    except Exception as e:
                        # Ante la duda se respalda: si el vault no está disponible, la exportación lo informará
                        logger.warning("No se pudo comparar la nota del vault de la clase %s: %s", lesson_id, e)
                        return True

                # Con clase previa, la nota se compara con esa clase antes de reemplazarla
                respaldar = bool(existente and sync_vault and nota_ajena(existente.id))

                # 1. Guardar la lección con origen CLAUDE_MCP
                lesson = studio.import_external_lesson(
                    topic_id=topic_id,
                    markdown_text=markdown_content,
                    origen=OrigenClase.CLAUDE_MCP,
                )

                cards_count = 0
                cards_error = None
                if extract_flashcards:
                    try:
                        cards_count = studio.export_flashcards_to_fsrs(lesson.id)
                    except Exception as e:
                        cards_error = str(e)

                # 2. El vault va aparte: si falla, la clase y las tarjetas ya quedaron guardadas
                vault_msg = "No solicitada"
                vault_error = None
                if sync_vault:
                    try:
                        # Sin clase previa lo decide la exportación: un archivo ya presente no lo escribió esta clase
                        studio.export_lesson_to_vault(lesson.id, backup_existing=respaldar if existente else None)
                        vault_msg = studio.last_relative_path
                    except Exception as e:
                        vault_error = str(e)
                        vault_msg = f"FALLÓ ({e})"

                # 3. Guardar una clase marca el tema como completado: se respeta lo pedido
                if mark_completed:
                    repo.update_topic_status(topic_id, EstadoTema.COMPLETADO)
                    estado_msg = "Completado ✅"
                elif estado_previo:
                    repo.update_topic_status(topic_id, estado_previo)
                    estado_msg = f"Sin cambios ({estado_previo})"
                else:
                    estado_msg = "Sin cambios"

                titulo = "⚠️ **Clase guardada, pero no se pudo sincronizar con el Vault**" if vault_error else (
                    "🎉 **Clase magistral reemplazada exitosamente**" if existente else "🎉 **Clase magistral guardada exitosamente**"
                )
                result_msg = [
                    titulo,
                    f"- **Tema:** {ctx['topic_title']} [ID: {topic_id}]",
                    f"- **Ruta:** {ctx['roadmap_title']}",
                    f"- **ID de Clase guardada:** {lesson.id}",
                    f"- **Tarjetas FSRS v5 extraídas:** {cards_count}" + (f" — FALLÓ ({cards_error})" if cards_error else ""),
                    f"- **Sincronización Vault:** {vault_msg}",
                    f"- **Estado del Tema:** {estado_msg}",
                ]
                if studio.last_backup_relative_path:
                    result_msg.append(
                        f"- **Respaldo:** en el vault había una nota distinta de la que generó el sistema (apuntes a mano u otro tema con el mismo nombre); se guardó una copia en {studio.last_backup_relative_path}"
                    )
                log_mcp_tool_execution(
                    "study_create_or_update_lesson",
                    {
                        "topic_id": topic_id,
                        "cards_extracted": cards_count,
                        "sync_vault": sync_vault,
                        "overwrite": bool(existente),
                        "vault_error": vault_error,
                    },
                    status="success",
                    db_path=db_path,
                )
                return "\n".join(result_msg)
            except Exception as e:
                log_mcp_tool_execution(
                    "study_create_or_update_lesson",
                    {"topic_id": topic_id},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al guardar clase para el tema {topic_id}: {e}"
