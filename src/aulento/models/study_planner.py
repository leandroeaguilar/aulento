"""Modelos de dominio Pydantic para el Motor de Recomendación y Planificador Adaptativo de Estudio."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PedagogicalPhase(str, Enum):
    """Fases pedagógicas del ciclo de estudio adaptativo."""
    WARMUP_FSRS = "warmup_fsrs"
    MACRO_FSRS = "macro_fsrs"
    DEEP_WORK_COURSE = "deep_work_course"
    ACTIVE_READING_BOOK = "active_reading_book"
    BREAK = "break"


class PlannedStudyBlock(BaseModel):
    """Bloque individual de estudio planificado dentro de la sesión."""
    fase: PedagogicalPhase = Field(..., description="Fase pedagógica a la que corresponde el bloque.")
    titulo: str = Field(..., description="Título representativo de la actividad.")
    descripcion: str = Field(..., description="Detalle de la tarea u objetivo específico.")
    duracion_minutos: int = Field(..., ge=5, le=180, description="Duración en minutos asignada al bloque.")
    recurso_tipo: str = Field(..., description="Tipo de recurso académico ('fsrs', 'macro_fsrs', 'curso', 'libro', 'descanso').")
    recurso_id: int | None = Field(default=None, description="ID del recurso si corresponde (curso_id, libro_id, tema_id).")
    recurso_nombre: str | None = Field(default=None, description="Nombre legible del recurso.")
    hora_inicio: str | None = Field(default=None, description="Hora estimada de inicio en formato HH:MM.")
    hora_fin: str | None = Field(default=None, description="Hora estimada de fin en formato HH:MM.")
    meta_especifica: str | None = Field(default=None, description="Meta cuantitativa (ej: '15 tarjetas', '10 páginas').")


class AdaptivePlanRequest(BaseModel):
    """Solicitud para la generación de un plan adaptativo de estudio."""
    available_minutes: int = Field(default=60, ge=15, le=360, description="Minutos totales disponibles para estudiar.")
    start_time: str | None = Field(default=None, description="Hora de inicio sugerida en formato HH:MM. Si no se indica, toma el próximo cuarto de hora.")
    focus_areas: list[str] | None = Field(default=None, description="Filtro opcional de áreas de enfoque ('fsrs', 'cursos', 'libros', 'macro_fsrs').")
    include_breaks: bool = Field(default=True, description="Si es True, incluye descansos breves para sesiones de 60 minutos o más.")
    target_date: str | None = Field(default=None, description="Fecha de destino (YYYY-MM-DD), default hoy.")


class AdaptivePlanResponse(BaseModel):
    """Respuesta con el plan de estudio adaptativo estructurado por bloques."""
    fecha: str = Field(..., description="Fecha asignada al plan (YYYY-MM-DD).")
    total_minutos: int = Field(..., description="Minutos totales del plan.")
    bloques: list[PlannedStudyBlock] = Field(..., description="Lista ordenada de bloques recomendados.")
    resumen_pedagogico: str = Field(..., description="Explicación del balance metodológico del plan.")
    score_urgencia: int = Field(..., ge=0, le=100, description="Puntaje de urgencia por deuda mnemotécnica o cursos estancados (0-100).")
    mensaje_enfoque: str = Field(..., description="Heurística motivacional o recomendación pedagógica.")


class DailyBriefing(BaseModel):
    """Resumen matutino y estado holístico de estudio de la cuenta."""
    fecha: str = Field(..., description="Fecha del briefing (YYYY-MM-DD).")
    racha_dias: int = Field(..., ge=0, description="Racha actual de días consecutivos estudiando.")
    record_racha: int = Field(..., ge=0, description="Récord histórico de racha de la cuenta.")
    estudiado_hoy: bool = Field(..., description="Indica si ya se registró actividad de estudio en el día.")
    minutos_hoy: int = Field(..., ge=0, description="Minutos de estudio registrados hoy.")
    fsrs_due_count: int = Field(..., ge=0, description="Tarjetas de inglés técnico FSRS v5 vencidas hoy.")
    macro_fsrs_due_count: int = Field(..., ge=0, description="Temas de rutas de aprendizaje vencidos en Macro-FSRS.")
    curso_sugerido: dict[str, Any] | None = Field(default=None, description="Curso del Hub recomendado para avanzar hoy.")
    libro_sugerido: dict[str, Any] | None = Field(default=None, description="Libro técnico sugerido con páginas pendientes.")
    urgency_score: int = Field(..., ge=0, le=100, description="Puntaje consolidado de urgencia pedagógica.")
    mensaje_enfoque: str = Field(..., description="Mensaje guía para la jornada.")


class ApplyPlanRequest(BaseModel):
    """Solicitud para volcar los bloques del plan a la agenda del usuario."""
    bloques: list[PlannedStudyBlock] = Field(..., description="Lista de bloques a insertar en la agenda.")
    dia_semana: int | None = Field(default=None, ge=1, le=7, description="Día de la semana ISO (1=Lunes..7=Domingo). Por defecto, el día actual.")
    reemplazar_existentes: bool = Field(default=False, description="Si es True, desactiva o reemplaza los bloques previos del mismo día.")


class ApplyPlanResponse(BaseModel):
    """Resultado de aplicar el plan adaptativo a la agenda."""
    success: bool
    dia_semana: int
    bloques_creados: int
    mensaje: str
    bloque_ids: list[int] = Field(default_factory=list)
