"""Herramientas MCP para consulta y actualización de cursos en el Hub de Plataformas."""

import logging
from pathlib import Path
from typing import Any

from aulento.connectors.course_sync import (
    CourseSyncManager,
    GoogleCloudSkillsConnector,
)
from aulento.core import permisos
from aulento.db.connection import get_connection
from aulento.db.repository import CursoRepository, PlataformaRepository
from aulento.mcp.security import (
    cuenta_mcp_actual,
    herramienta_auditada,
    log_mcp_tool_execution,
)
from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
from aulento.models.plataforma import PlataformaCreate

logger = logging.getLogger(__name__)


def register_course_tools(server: Any, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Registra las herramientas de gestión de cursos en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_list_courses(platform: str = "", status: str = "all") -> str:
        """Lista los cursos del Hub de Plataformas Educativas (Digital House, Coursera, Google Skills, etc.).
        
        Args:
            platform: Filtrar por nombre de plataforma (opcional).
            status: Filtrar por estado: 'all', 'en_curso', 'pausado', o 'completado'.
        """
        try:
            conn = get_connection(db_path)
            try:
                repo = CursoRepository(conn, cuenta_mcp_actual())
                st_filter = EstadoCurso(status) if status in ("en_curso", "pausado", "completado") else None
                courses = repo.list_all(estado=st_filter)

                if platform:
                    courses = [c for c in courses if platform.lower() in (c.nombre_plataforma or "").lower()]

                if not courses:
                    return "No se encontraron cursos registrados con los criterios solicitados."

                lines = ["### 🎓 Cursos en el Hub de Plataformas:"]
                for c in courses:
                    plat = c.nombre_plataforma or "Plataforma"
                    lines.append(
                        f"- **[{c.id}] {c.nombre_curso}** ({plat})\n"
                        f"  • Avance: **{c.progreso_pct:.1f}%** | Estado: {c.estado.value} | Prioridad: {c.prioridad.value}\n"
                        f"  • Link Aula: {c.url_aula}"
                    )
                log_mcp_tool_execution("study_list_courses", {"platform": platform, "status": status}, status="success", db_path=db_path)
                return "\n".join(lines)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            log_mcp_tool_execution("study_list_courses", {"platform": platform, "status": status}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al listar cursos: {e}"

    @tool()
    def study_get_course_sync_status() -> str:
        """Obtiene un resumen del estado de sincronización de cursos de la cuenta (total de cursos, sincronizados y última fecha)."""
        try:
            conn = get_connection(db_path)
            try:
                repo = CursoRepository(conn, cuenta_mcp_actual())
                status = repo.get_sync_status()
                log_mcp_tool_execution("study_get_course_sync_status", {}, status="success", db_path=db_path)
                return (
                    f"### 🔄 Estado de Sincronización de Cursos:\n"
                    f"- **Total de Cursos:** {status['total_cursos']}\n"
                    f"- **Cursos Sincronizados:** {status['cursos_sincronizados']}\n"
                    f"- **Última Sincronización:** {status['ultima_sincronizacion'] or 'Nunca'}"
                )
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            log_mcp_tool_execution("study_get_course_sync_status", {}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al consultar estado de sincronización: {e}"

    if not read_only:
        @tool()
        def study_update_course_progress(
            course_identifier: str,
            progreso_pct: float,
            status: str = "",
        ) -> str:
            """Actualiza el porcentaje de avance y estado de un curso en Aulento.
            
            course_identifier puede ser el ID numérico, la URL directa del aula (o parte de ella)
            o el nombre del curso.
            
            Args:
                course_identifier: ID numérico, link de aula virtual o título del curso.
                progreso_pct: Nuevo porcentaje de avance (entre 0.0 y 100.0).
                status: 'en_curso', 'pausado', 'completado' (opcional, se auto-completa al 100%).
            """
            try:
                if progreso_pct < 0.0 or progreso_pct > 100.0:
                    return "Error: progreso_pct debe ser un valor numérico entre 0.0 y 100.0."

                conn = get_connection(db_path)
                try:
                    repo = CursoRepository(conn, cuenta_mcp_actual())
                    curso = repo.find_by_url_or_name(course_identifier)
                    if not curso:
                        return f"Error: No se encontró ningún curso que coincida con '{course_identifier}'."

                    nuevo_estado = None
                    estado_pedido = status.strip().lower()
                    if estado_pedido:
                        if estado_pedido not in ("en_curso", "pausado", "completado"):
                            return f"Error: status '{status}' no es válido. Usá 'en_curso', 'pausado' o 'completado'."
                        nuevo_estado = EstadoCurso(estado_pedido)

                    updated = repo.update_progress(curso.id, nuevo_progreso=progreso_pct, nuevo_estado=nuevo_estado)
                    if not updated:
                        return f"Error: No se pudo actualizar el curso ID {curso.id}."

                    result = (
                        f"✅ **Curso actualizado exitosamente:**\n"
                        f"- **Curso:** {updated.nombre_curso} [ID: {updated.id}]\n"
                        f"- **Plataforma:** {updated.nombre_plataforma or 'General'}\n"
                        f"- **Nuevo Avance:** {updated.progreso_pct:.1f}%\n"
                        f"- **Estado:** {updated.estado.value}\n"
                        f"- **Aula:** {updated.url_aula}"
                    )
                    log_mcp_tool_execution(
                        "study_update_course_progress",
                        {"identifier": course_identifier, "progreso_pct": progreso_pct, "status": status},
                        status="success",
                        db_path=db_path,
                    )
                    return result
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution(
                    "study_update_course_progress",
                    {"identifier": course_identifier, "progreso_pct": progreso_pct},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al actualizar progreso del curso '{course_identifier}': {e}"

        @tool()
        def study_add_course(
            platform_name: str,
            course_name: str,
            url_aula: str,
            progreso_pct: float = 0.0,
            prioridad: str = "alta",
            url_drive: str | None = None,
            ruta_local: str | None = None,
            url_notion: str | None = None,
            ruta_obsidian: str | None = None,
        ) -> str:
            """Registra un nuevo curso en el Hub de Plataformas.
            
            Si la plataforma no existe, se crea automáticamente.
            
            Args:
                platform_name: Nombre de la plataforma (ej. 'Digital House', 'Coursera', 'Humai').
                course_name: Título del curso.
                url_aula: URL de acceso al aula virtual o material.
                progreso_pct: Porcentaje inicial de avance (0.0 por defecto).
                prioridad: 'alta', 'media', o 'baja'.
                url_drive: URL opcional a la carpeta de Google Drive / Nube.
                ruta_local: Ruta opcional a la carpeta local en el disco (PC).
                url_notion: URL opcional a la página/base de apuntes en Notion.
                ruta_obsidian: Ruta relativa opcional o URI de la nota en Obsidian.
            """
            try:
                conn = get_connection(db_path)
                try:
                    plat_repo = PlataformaRepository(conn, cuenta_mcp_actual())
                    curso_repo = CursoRepository(conn, cuenta_mcp_actual())

                    # Antes de crear la plataforma: si la cuenta no puede crear otro curso, no queda una vacía (062)
                    decision = permisos.puede(curso_repo.user_id, permisos.CREAR_CURSO, conn)
                    if not decision.permitido:
                        return f"⛔ No se registró el curso: {decision.motivo}"

                    plat = plat_repo.get_by_name(platform_name)
                    if not plat:
                        plat = plat_repo.create(PlataformaCreate(
                            nombre=platform_name.strip(),
                            url_acceso=url_aula,
                            icono_color="blue",
                        ))

                    prio_enum = PrioridadCurso.ALTA
                    if prioridad.lower() in ("media", "baja", "alta"):
                        prio_enum = PrioridadCurso(prioridad.lower())

                    nuevo_curso = curso_repo.create(CursoCreate(
                        plataforma_id=plat.id,
                        nombre_curso=course_name.strip(),
                        url_aula=url_aula.strip(),
                        progreso_pct=progreso_pct,
                        estado=EstadoCurso.EN_CURSO,
                        prioridad=prio_enum,
                        url_drive=url_drive,
                        ruta_local=ruta_local,
                        url_notion=url_notion,
                        ruta_obsidian=ruta_obsidian,
                    ))

                    result = (
                        f"🎉 **Curso registrado en Aulento:**\n"
                        f"- **ID:** {nuevo_curso.id}\n"
                        f"- **Curso:** {nuevo_curso.nombre_curso}\n"
                        f"- **Plataforma:** {plat.nombre}\n"
                        f"- **Link:** {nuevo_curso.url_aula}\n"
                        f"- **Progreso:** {nuevo_curso.progreso_pct:.1f}%"
                    )
                    if nuevo_curso.url_drive:
                        result += f"\n- **Drive:** {nuevo_curso.url_drive}"
                    if nuevo_curso.ruta_local:
                        result += f"\n- **Local:** {nuevo_curso.ruta_local}"
                    if nuevo_curso.url_notion:
                        result += f"\n- **Notion:** {nuevo_curso.url_notion}"
                    if nuevo_curso.ruta_obsidian:
                        result += f"\n- **Obsidian:** {nuevo_curso.ruta_obsidian}"
                    log_mcp_tool_execution(
                        "study_add_course",
                        {"course_name": course_name, "platform": platform_name},
                        status="success",
                        db_path=db_path,
                    )
                    return result
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution(
                    "study_add_course",
                    {"course_name": course_name, "platform": platform_name},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al registrar curso: {e}"

        @tool()
        def study_sync_course_progress(
            course_identifier: str,
            progreso_pct: float,
            status: str = "",
            fuente: str = "mcp",
            external_id: str | None = None,
        ) -> str:
            """Sincroniza el avance de un curso externo por identificador, recalculando progreso y racha.

            Args:
                course_identifier: ID numérico, URL o nombre del curso a sincronizar.
                progreso_pct: Porcentaje nuevo de avance (0.0 a 100.0).
                status: 'en_curso', 'pausado', o 'completado'.
                fuente: Nombre de la fuente de sincronización (por defecto 'mcp').
                external_id: Identificador o slug externo opcional.
            """
            try:
                if progreso_pct < 0.0 or progreso_pct > 100.0:
                    return "Error: progreso_pct debe estar entre 0.0 y 100.0."
                conn = get_connection(db_path)
                try:
                    user_id = cuenta_mcp_actual()
                    c_repo = CursoRepository(conn, user_id)
                    curso = c_repo.find_by_url_or_name(course_identifier)
                    if not curso:
                        return f"Error: No se encontró ningún curso que coincida con '{course_identifier}'."

                    manager = CourseSyncManager(conn, user_id)
                    payload = {
                        "progreso_pct": progreso_pct,
                        "fuente": fuente,
                    }
                    if status.strip():
                        payload["estado"] = status.strip()
                    if external_id:
                        payload["external_id"] = external_id.strip()

                    res = manager.sync_course(curso.id, payload=payload)
                    log_mcp_tool_execution(
                        "study_sync_course_progress",
                        {"course_identifier": course_identifier, "progreso_pct": progreso_pct},
                        status="success" if res.success else "error",
                        db_path=db_path,
                    )
                    return (
                        f"🔄 **Sincronización de curso exitosa:**\n"
                        f"- **Curso:** {res.nombre_curso} [ID: {res.curso_id}]\n"
                        f"- **Progreso:** {res.progreso_anterior:.1f}% ➔ **{res.progreso_pct:.1f}%**\n"
                        f"- **Estado:** {res.estado}\n"
                        f"- **Fuente:** {res.fuente}\n"
                        f"- **Mensaje:** {res.mensaje}"
                    )
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution(
                    "study_sync_course_progress",
                    {"course_identifier": course_identifier, "progreso_pct": progreso_pct},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al sincronizar curso '{course_identifier}': {e}"

        @tool()
        def study_sync_google_skills(
            profile_url_or_id: str,
            auto_import: bool = False,
        ) -> str:
            """Sincroniza todos los cursos de Google Cloud Skills Boost a partir de un perfil público.

            Args:
                profile_url_or_id: URL completa o ID/UUID del perfil público de Google Cloud Skills Boost.
                auto_import: Si es True, importa insignias completadas como cursos nuevos en el Hub.
            """
            try:
                # Validar la URL o perfil antes de abrir la base o realizar peticiones
                GoogleCloudSkillsConnector.normalizar_url_o_id(profile_url_or_id.strip())

                conn = get_connection(db_path)
                try:
                    user_id = cuenta_mcp_actual()
                    manager = CourseSyncManager(conn, user_id)
                    results = manager.sync_google_skills_profile(
                        profile_url_or_id=profile_url_or_id.strip(),
                        auto_import=auto_import,
                    )
                    log_mcp_tool_execution(
                        "study_sync_google_skills",
                        {"profile": profile_url_or_id, "auto_import": auto_import},
                        status="success",
                        db_path=db_path,
                    )
                    lines = [f"✅ **Sincronización con Google Cloud Skills Boost finalizada ({len(results)} procesados):**"]
                    for r in results:
                        lines.append(f"- **{r.nombre_curso}**: {r.progreso_pct:.1f}% ({r.estado}) - {r.mensaje}")
                    return "\n".join(lines)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                log_mcp_tool_execution(
                    "study_sync_google_skills",
                    {"profile": profile_url_or_id},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al sincronizar perfil de Google Cloud Skills Boost: {e}"
