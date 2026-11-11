"""Herramientas MCP para consulta de Agenda Semanal y Registro de Tiempo de Estudio."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

from aulento.db.connection import get_connection
from aulento.db.repository import BloqueHorarioRepository
from aulento.db.focus_repository import FocusRepository
from aulento.models.focus_session import FocusSessionCreate
from aulento.mcp.security import cuenta_mcp_actual, herramienta_auditada, log_mcp_tool_execution

logger = logging.getLogger(__name__)


def register_schedule_tools(server: Any, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Registra las herramientas de agenda y tracking de tiempo en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_get_today_schedule() -> str:
        """Obtiene los bloques de estudio y actividades planificadas para el día de hoy según la agenda."""
        try:
            conn = get_connection(db_path)
            try:
                repo = BloqueHorarioRepository(conn, cuenta_mcp_actual())
                now = datetime.now()
                # Python weekday(): Lunes es 0, Domingo es 6.
                # En la BD: 1 = Lunes, 7 = Domingo.
                dia_bd = now.weekday() + 1
                bloques = repo.list_all(dia_semana=dia_bd)

                nombres_dias = {
                    1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
                    5: "Viernes", 6: "Sábado", 7: "Domingo"
                }
                dia_nombre = nombres_dias.get(dia_bd, "Hoy")

                if not bloques:
                    return f"No hay bloques de estudio programados en la agenda para hoy ({dia_nombre})."

                lines = [f"### 📅 Agenda de Estudio de Hoy ({dia_nombre}):"]
                for b in bloques:
                    lines.append(
                        f"- ⏰ **{b.hora_inicio} - {b.hora_fin}** [{b.tipo.value.upper()}]\n"
                        f"  • {b.descripcion}\n"
                        f"  • Acceso: {b.url_acceso or 'Sin enlace directo'}"
                    )
                log_mcp_tool_execution("study_get_today_schedule", {"dia": dia_bd}, status="success", db_path=db_path)
                return "\n".join(lines)
            finally:
                conn.close()
        except Exception as e:
            log_mcp_tool_execution("study_get_today_schedule", {}, status="error", error_message=str(e), db_path=db_path)
            return f"Error al consultar agenda: {e}"

    if not read_only:
        @tool()
        def study_log_study_session(
            activity_type: str,
            duration_minutes: int,
            notes: str = "",
        ) -> str:
            """Registra una sesión real de estudio completada (alimenta Weekly Digest y métricas de estudio).
            
            Args:
                activity_type: Tipo de actividad ('curso', 'lectura', 'ingles', 'repaso', 'otro').
                duration_minutes: Duración en minutos de la sesión de estudio.
                notes: Notas breves de lo estudiado o temas abordados.
            """
            try:
                if duration_minutes <= 0:
                    return "Error: duration_minutes debe ser mayor a 0."

                conn = get_connection(db_path)
                try:
                    repo = FocusRepository(conn, cuenta_mcp_actual())
                    tipo_val = activity_type.lower() if activity_type.lower() in ("curso", "lectura", "ingles", "repaso", "otro") else "otro"
                    session = repo.record_session(FocusSessionCreate(
                        duracion_minutos=duration_minutes,
                        tipo=tipo_val,
                        notas=notes.strip() or None,
                    ))

                    result = (
                        f"⏱️ **Sesión de estudio registrada exitosamente:**\n"
                        f"- **ID:** {session.id}\n"
                        f"- **Actividad:** {session.tipo.upper()}\n"
                        f"- **Duración:** {session.duracion_minutos} minutos\n"
                        f"- **Notas:** {session.notas or 'Sin notas'}\n"
                        f"- **Fecha:** {session.fecha_hora}"
                    )
                    log_mcp_tool_execution(
                        "study_log_study_session",
                        {"activity_type": activity_type, "duration": duration_minutes},
                        status="success",
                        db_path=db_path,
                    )
                    return result
                finally:
                    conn.close()
            except Exception as e:
                log_mcp_tool_execution(
                    "study_log_study_session",
                    {"activity_type": activity_type, "duration": duration_minutes},
                    status="error",
                    error_message=str(e),
                    db_path=db_path,
                )
                return f"Error al registrar sesión de estudio: {e}"
