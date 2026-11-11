"""Modelos de dominio Pydantic para sesiones reales de estudio (Focus / Pomodoro)."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class FocusSessionBase(BaseModel):
    bloque_id: Optional[int] = Field(None, description="ID del bloque horario asociado, o null si fue ad-hoc")
    duracion_minutos: int = Field(25, ge=1, le=480, description="Duración real estudiada en minutos")
    tipo: str = Field("pomodoro", description="Tipo: 'pomodoro', 'curso', 'ingles_fsrs', 'lectura_libro', 'libre'")
    notas: Optional[str] = Field(None, description="Notas o resumen de lo avanzado en la sesión")


class FocusSessionCreate(FocusSessionBase):
    pass


class FocusSession(FocusSessionBase):
    id: int
    fecha_hora: str
