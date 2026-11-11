"""Router REST para el temporizador Focus / Pomodoro y registro de sesiones de estudio."""

from typing import List, Dict, Any
from fastapi import APIRouter, Query

from aulento.web.dependencies import RepoBloques, RepoFocus, no_encontrado
from aulento.models.focus_session import FocusSession, FocusSessionCreate

router = APIRouter(prefix="/api/focus", tags=["Focus Timer"])


@router.post("/sessions", response_model=FocusSession)
def record_focus_session(data: FocusSessionCreate, repo: RepoFocus, bloques: RepoBloques) -> FocusSession:
    """Registra una sesión de estudio completada vinculada a un bloque de la cuenta o en modo libre."""
    if data.bloque_id is not None and not bloques.get(data.bloque_id):
        raise no_encontrado("Bloque", data.bloque_id)
    return repo.record_session(data)


@router.get("/sessions", response_model=List[FocusSession])
def list_focus_sessions(repo: RepoFocus, limit: int = Query(30, ge=1, le=100)) -> List[FocusSession]:
    """Obtiene las sesiones de estudio más recientes de la cuenta."""
    return repo.list_sessions(limit=limit)


@router.get("/stats")
def get_focus_stats(repo: RepoFocus) -> Dict[str, Any]:
    """Retorna las estadísticas de minutos y horas reales estudiadas hoy y en la semana por la cuenta."""
    return repo.get_weekly_stats()
