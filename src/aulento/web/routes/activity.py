"""Rutas API para métricas de consistencia diaria y Heatmap de Actividad."""

from fastapi import APIRouter, Query

from aulento.models.macro_fsrs import ActivityHeatmapResponse, StreakInfo
from aulento.web.dependencies import TrackerActividad

router = APIRouter(prefix="/api/activity", tags=["Actividad"])


@router.get("/heatmap", response_model=ActivityHeatmapResponse)
def get_activity_heatmap(tracker: TrackerActividad, days: int = Query(default=90, ge=7, le=365)):
    """Retorna la matriz de actividad diaria (minutos, páginas, tarjetas, temas) y las rachas de la cuenta."""
    return tracker.get_heatmap(days=days)


@router.get("/streak", response_model=StreakInfo)
def get_streak_info(tracker: TrackerActividad):
    """Retorna la información de racha activa y récord histórico de la cuenta."""
    heatmap = tracker.get_heatmap(days=7)
    return heatmap.streak
