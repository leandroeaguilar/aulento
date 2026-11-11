"""Modelos de dominio para Tarjetas de Estudio FSRS y Logs de Repaso."""

from datetime import datetime
from enum import IntEnum
from pydantic import BaseModel, Field


class FSRSRating(IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class FSRSState(IntEnum):
    NEW = 0
    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


class FSRSCardBase(BaseModel):
    categoria: str = Field(default="ingles_tecnico", description="Categoría temática de la tarjeta")
    item_pregunta: str = Field(..., min_length=1, description="Pregunta, hueco (cloze) o contexto de la tarjeta")
    respuesta_esperada: str = Field(..., min_length=1, description="Respuesta técnica exacta esperada")
    contexto_uso: str | None = Field(default=None, description="Ejemplo de uso en reunión, PR o ticket")


class FSRSCardCreate(FSRSCardBase):
    pass


class FSRSCard(FSRSCardBase):
    id: int
    state: int = Field(default=1, description="0: New, 1: Learning, 2: Review, 3: Relearning")
    step: int | None = Field(default=0, description="Paso dentro del estado actual")
    stability: float | None = Field(default=None, description="Estabilidad en días calculada por FSRS")
    difficulty: float | None = Field(default=None, description="Dificultad (1-10) calculada por FSRS")
    due: datetime | str | None = Field(default=None, description="Fecha/hora programada para el próximo repaso en UTC")
    last_review: datetime | str | None = Field(default=None, description="Fecha/hora del último repaso")
    reps: int = Field(default=0, description="Cantidad de repasos realizados")
    lapses: int = Field(default=0, description="Cantidad de olvidos (Again en Review)")
    fecha_creacion: datetime | str | None = None


class FSRSReviewLog(BaseModel):
    id: int
    card_id: int
    rating: int
    review_datetime: datetime | str
    elapsed_days: float = 0.0
    scheduled_days: float = 0.0
    state: int
