"""Modelos de datos para el generador de exámenes Active Recall y evaluación Feynman."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    CLOZE = "cloze"
    OPEN_REASONING = "open_reasoning"


class Question(BaseModel):
    """Representa una pregunta individual de examen activo."""
    id: str = Field(..., description="Identificador único de la pregunta")
    note_id: str = Field(..., description="ID de la nota del vault o material que origina la pregunta")
    topic: str = Field(..., description="Tema o concepto evaluado")
    question_type: QuestionType = Field(..., description="Tipo: multiple_choice, cloze, open_reasoning")
    prompt: str = Field(..., description="Enunciado de la pregunta")
    options: list[str] = Field(default_factory=list, description="Opciones (para opción múltiple)")
    correct_answer: str = Field(..., description="Respuesta correcta esperada")
    explanation: str = Field(..., description="Fundamento y justificación pedagógica")
    source_reference: str | None = Field(None, description="Cita, fragmento o sección de origen")
    fragmento: str | None = Field(None, description="Fragmento textual del que sale la pregunta")


class Exam(BaseModel):
    """Representa una sesión de examen estructurado con preguntas de Active Recall."""
    id: str = Field(..., description="Identificador único del examen")
    title: str = Field(..., description="Título del examen")
    topic: str = Field(..., description="Tema general evaluado")
    created_at: str = Field(..., description="Marca de tiempo ISO 8601")
    questions: list[Question] = Field(default_factory=list, description="Lista de preguntas")
    total_questions: int = Field(0, description="Cantidad total de preguntas")
    sin_ia: bool = Field(False, description="Indica si se generó en modo sin IA")
    rotulo: str | None = Field(None, description="Rótulo descriptivo (ej. 'sin IA')")
    aviso: str | None = Field(None, description="Aviso o advertencia si la IA no estuvo disponible o falló")


class FeynmanSubmission(BaseModel):
    """Petición del usuario explicando un concepto bajo la técnica Feynman."""
    concept: str = Field(..., description="Nombre del concepto explicado")
    explanation: str = Field(..., description="Explicación en lenguaje propio del usuario")
    target_audience: str | None = Field("principiante", description="Público objetivo (principiante, junior, no-técnico)")
    note_id: str | None = Field(None, description="ID o título de la nota del vault opcional para contrastar")


class FeynmanCriterio(BaseModel):
    """Puntaje y justificación de un criterio específico de la Técnica Feynman."""
    puntaje: int = Field(..., ge=0, le=100, description="Puntuación de 0 a 100")
    justificacion: str = Field(..., description="Justificación pedagógica del puntaje")
    tecnicismos: list[str] | None = Field(None, description="Términos técnicos no explicados detectados")
    lagunas: list[str] | None = Field(None, description="Huecos o puntos clave omitidos")


class FeynmanEvaluation(BaseModel):
    """Resultado estructurado de la evaluación con la Técnica Feynman."""
    concept: str = Field(..., description="Concepto evaluado")
    score: int = Field(..., ge=0, le=100, description="Puntuación global de 0 a 100")
    mastery_level: str = Field(..., description="Nivel: Principiante, Intermedio, Avanzado, Feynman Master")
    clarity_score: int = Field(..., ge=0, le=100, description="Claridad y sencillez del lenguaje")
    precision_score: int = Field(..., ge=0, le=100, description="Exactitud técnica")
    jargon_used: list[str] = Field(default_factory=list, description="Jergas o tecnicismos no explicados")
    knowledge_gaps: list[str] = Field(default_factory=list, description="Lagunas o aspectos clave omitidos")
    strengths: list[str] = Field(default_factory=list, description="Aciertos y explicaciones claras logradas")
    feedback_summary: str = Field(..., description="Veredicto pedagógico constructivo")
    suggested_simplification: str = Field(..., description="Ejemplo de cómo explicarlo de manera aún más simple")
    criterios: dict[str, Any] | None = Field(None, description="Evaluación detallada de los 5 criterios Feynman")
    sin_ia: bool = Field(False, description="Indica si se evaluó en modo básico sin IA")
    rotulo: str | None = Field(None, description="Rótulo 'sin IA' cuando no se usó IA")
    que_mide: str | None = Field(None, description="Explicación de qué mide la evaluación heurística sin IA")
    aviso: str | None = Field(None, description="Aviso explicativo si hubo error en IA")


class OpenAnswerEvaluation(BaseModel):
    """Resultado de la evaluación de una respuesta abierta contra el texto de estudio."""
    is_correct: bool = Field(..., description="Indica si la respuesta se considera conceptualmente correcta")
    score: int = Field(..., ge=0, le=100, description="Puntuación asignada de 0 a 100")
    feedback: str = Field(..., description="Justificación y explicación pedagógica de por qué")
    what_was_missing: str | None = Field(None, description="Qué aspectos o detalles faltaron en la respuesta")
    sin_ia: bool = Field(False, description="Indica si se evaluó en modo sin IA")
    rotulo: str | None = Field(None, description="Rótulo 'sin IA' si no se utilizó IA")
    aviso: str | None = Field(None, description="Aviso explicativo en caso de contingencia")


class FeynmanExample(BaseModel):
    """Ejemplo rápido para inspirar la explicación en el Simulador Feynman."""
    concept: str = Field(..., description="Nombre del concepto o tema")
    explanation: str | None = Field(None, description="Explicación breve de ejemplo")
