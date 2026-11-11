"""Rutas API para Repetición Espaciada Macro (FSRS v5) de Temas y Micro-Quizzes Feynman."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aulento.models.macro_fsrs import MicroQuizFeynman, TopicRetention
from aulento.web.dependencies import MotorMacroFsrs, RepoRutas, no_encontrado

router = APIRouter(prefix="/api/macro-fsrs", tags=["Macro-FSRS"])


class TopicReviewRequest(BaseModel):
    tema_id: int
    rating: int = Field(..., ge=1, le=4, description="1: Again, 2: Hard, 3: Good, 4: Easy")
    notas: str = Field(default="", max_length=500)


@router.get("/due", response_model=list[TopicRetention])
def get_due_topics(engine: MotorMacroFsrs):
    """Retorna los temas completados de las rutas de la cuenta que requieren repaso hoy."""
    return engine.repo.get_due_topics()


@router.get("/all", response_model=list[TopicRetention])
def get_all_retention_topics(engine: MotorMacroFsrs):
    """Retorna los temas de la cuenta en seguimiento de retención macro."""
    return engine.repo.list_all_retention()


@router.get("/quiz/{tema_id}", response_model=MicroQuizFeynman)
def get_feynman_microquiz(tema_id: int, engine: MotorMacroFsrs, repo: RepoRutas):
    """Genera el micro-quiz interactivo de 3 minutos para el tema indicado."""
    if not repo.get_topic_with_context(tema_id):
        raise no_encontrado("Tema", tema_id)
    try:
        return engine.get_feynman_microquiz(tema_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/review", response_model=TopicRetention)
def review_topic(payload: TopicReviewRequest, engine: MotorMacroFsrs, repo: RepoRutas):
    """Registra la calificación de estudio FSRS v5 para un tema de la cuenta y actualiza el próximo intervalo."""
    if not repo.get_topic_with_context(payload.tema_id):
        raise no_encontrado("Tema", payload.tema_id)
    try:
        return engine.review_topic(
            tema_id=payload.tema_id,
            rating=payload.rating,
            notas=payload.notas,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
