"""Modelos de dominio Pydantic para Macro-FSRS de Temas, Micro-Quizzes y Heatmap de Actividad."""

from datetime import datetime, date
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class MacroFSRSState(int, Enum):
    NEW = 0
    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


class TopicRetentionBase(BaseModel):
    tema_id: int
    state: MacroFSRSState = MacroFSRSState.NEW
    due_date: datetime | str
    stability: float = 2.0
    difficulty: float = 5.0
    elapsed_days: int = 0
    scheduled_days: int = 3
    reps: int = 0
    lapses: int = 0
    last_review: datetime | str | None = None


class TopicRetentionCreate(TopicRetentionBase):
    pass


class TopicRetention(TopicRetentionBase):
    id: int
    fecha_creacion: datetime | str | None = None
    # Metadatos del tema enriquecidos
    tema_titulo: str | None = None
    ruta_titulo: str | None = None
    ruta_id: int | None = None


class TopicReviewLogCreate(BaseModel):
    retention_id: int
    rating: int = Field(..., ge=1, le=4)  # 1: Again, 2: Hard, 3: Good, 4: Easy
    scheduled_days: int
    elapsed_days: int
    notas: str | None = None


class TopicReviewLog(TopicReviewLogCreate):
    id: int
    review_time: datetime | str | None = None


class MicroQuizFeynman(BaseModel):
    tema_id: int
    tema_titulo: str
    ruta_titulo: str
    concepto_clave: str
    pregunta_active_recall: str
    desafio_feynman: str
    puntos_clave_evaluacion: list[str] = Field(default_factory=list)


# --- Modelos de Actividad y Heatmap ---

class ActivityDay(BaseModel):
    date: str  # YYYY-MM-DD
    study_minutes: int = 0
    pages_read: int = 0
    fsrs_reviews: int = 0
    topics_completed: int = 0
    score: float = 0.0
    level: int = Field(default=0, ge=0, le=4)  # 0: None, 1: Low, 2: Medium, 3: High, 4: Peak


class StreakInfo(BaseModel):
    current_streak: int = 0
    longest_streak: int = 0
    total_active_days: int = 0
    total_study_minutes: int = 0
    total_pages_read: int = 0
    total_fsrs_reviews: int = 0
    total_topics_completed: int = 0


class ActivityHeatmapResponse(BaseModel):
    days: list[ActivityDay]
    streak: StreakInfo
    generated_at: str
