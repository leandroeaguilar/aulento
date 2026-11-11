"""Rutas REST para el Motor de Recomendación y Planificador Adaptativo de Estudio."""

from fastapi import APIRouter

from aulento.models.study_planner import (
    AdaptivePlanRequest,
    AdaptivePlanResponse,
    ApplyPlanRequest,
    ApplyPlanResponse,
    DailyBriefing,
)
from aulento.web.dependencies import MotorPlanificador

router = APIRouter(prefix="/api/planner", tags=["Planificador Adaptativo"])


@router.get("/daily-briefing", response_model=DailyBriefing)
def get_daily_briefing(engine: MotorPlanificador) -> DailyBriefing:
    """Retorna el resumen ejecutivo matutino y estado de urgencia de estudio de la cuenta."""
    return engine.obtener_daily_briefing()


@router.post("/recommendations", response_model=AdaptivePlanResponse)
def get_study_recommendations(req: AdaptivePlanRequest, engine: MotorPlanificador) -> AdaptivePlanResponse:
    """Genera un plan de estudio adaptativo estructurado en fases pedagógicas según los minutos disponibles."""
    return engine.generar_plan_adaptativo(req)


@router.post("/apply-today", response_model=ApplyPlanResponse)
def apply_study_plan_to_schedule(req: ApplyPlanRequest, engine: MotorPlanificador) -> ApplyPlanResponse:
    """Aplica e inserta directamente los bloques del plan adaptativo en la agenda de la cuenta."""
    return engine.aplicar_plan_a_agenda(req)
