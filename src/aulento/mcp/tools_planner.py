"""Herramientas MCP para el Motor de Recomendación y Planificación Adaptativa de Estudio."""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from aulento.core.study_planner import StudyPlannerEngine
from aulento.db.connection import get_connection
from aulento.mcp.security import (
    cuenta_mcp_actual,
    herramienta_auditada,
)
from aulento.models.study_planner import (
    AdaptivePlanRequest,
    ApplyPlanRequest,
    PlannedStudyBlock,
)

logger = logging.getLogger(__name__)


def register_planner_tools(server: Any, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Registra las herramientas de planificación adaptativa en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_get_daily_briefing(target_date: str = "") -> str:
        """Obtiene el resumen matutino holístico y puntuación de urgencia pedagógica de la cuenta.

        Args:
            target_date: Fecha de consulta en formato YYYY-MM-DD (opcional, default hoy).
        """
        try:
            conn = get_connection(db_path)
            try:
                engine = StudyPlannerEngine(conn, cuenta_mcp_actual())
                d = None
                if target_date:
                    try:
                        d = date.fromisoformat(target_date.strip())
                    except ValueError:
                        pass
                briefing = engine.obtener_daily_briefing(fecha_objetivo=d)
                return json.dumps(briefing.model_dump(), indent=2, ensure_ascii=False)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            return f"Error al obtener daily briefing: {e}"

    @tool()
    def study_generate_adaptive_study_plan(
        available_minutes: int = 60,
        start_time: str = "",
        focus_areas: str = "",
        include_breaks: bool = True,
    ) -> str:
        """Genera un plan de estudio adaptativo estructurado en fases pedagógicas según los minutos disponibles.

        Args:
            available_minutes: Minutos totales disponibles para estudiar (ej. 30, 45, 60, 90).
            start_time: Hora sugerida de inicio en formato HH:MM (opcional).
            focus_areas: Áreas separadas por coma opcionales: 'fsrs', 'cursos', 'libros', 'macro_fsrs'.
            include_breaks: Si es True, programa descansos breves para sesiones largas.
        """
        try:
            conn = get_connection(db_path)
            try:
                engine = StudyPlannerEngine(conn, cuenta_mcp_actual())
                areas = [a.strip() for a in focus_areas.split(",") if a.strip()] if focus_areas else None
                req = AdaptivePlanRequest(
                    available_minutes=available_minutes,
                    start_time=start_time.strip() if start_time else None,
                    focus_areas=areas,
                    include_breaks=include_breaks,
                )
                plan = engine.generar_plan_adaptativo(req)
                return json.dumps(plan.model_dump(), indent=2, ensure_ascii=False)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            return f"Error al generar plan adaptativo: {e}"

    @tool()
    def study_apply_study_plan_to_schedule(
        blocks_json: str = "[]",
        weekday: int = 0,
        replace_existing: bool = False,
    ) -> str:
        """Vuelca e inserta los bloques de un plan de estudio directamente en la agenda semanal de la cuenta.

        Args:
            blocks_json: Cadena JSON con la lista de bloques planificados a insertar.
            weekday: Día de la semana (1=Lunes..7=Domingo). Si es 0, toma el día de hoy.
            replace_existing: Si es True, elimina o desactiva bloques previos del mismo día.
        """
        if read_only:
            return "Operación rechazada: el servidor MCP se ejecuta en modo de solo lectura."

        try:
            raw_blocks = json.loads(blocks_json)
            if not isinstance(raw_blocks, list):
                return "Error: blocks_json debe contener un array JSON de bloques."

            bloques = [PlannedStudyBlock(**b) for b in raw_blocks]
            conn = get_connection(db_path)
            try:
                engine = StudyPlannerEngine(conn, cuenta_mcp_actual())
                req = ApplyPlanRequest(
                    bloques=bloques,
                    dia_semana=weekday if 1 <= weekday <= 7 else None,
                    reemplazar_existentes=replace_existing,
                )
                resp = engine.aplicar_plan_a_agenda(req)
                return json.dumps(resp.model_dump(), indent=2, ensure_ascii=False)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            return f"Error al aplicar plan a la agenda: {e}"
