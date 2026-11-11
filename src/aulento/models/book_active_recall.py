"""Modelos de dominio para el subsistema de Lectura Activa con IA y Cosecha FSRS de Libros Técnicos."""

from pydantic import BaseModel, Field


class ActiveRecallQuestion(BaseModel):
    """Pregunta conceptual de Active Recall sobre un tramo del libro."""
    id: int = Field(..., description="Identificador secuencial de la pregunta (1..N)")
    pregunta: str = Field(..., description="Pregunta conceptual de profundidad sobre decisiones de diseño o mecanismos")
    objetivo_conceptual: str = Field(..., description="Concepto o principio técnico que busca comprobar")
    criterio_evaluacion: str = Field(..., description="Qué elementos debe contener una respuesta satisfactoria")


class ActiveRecallGenerateRequest(BaseModel):
    """Solicitud para generar preguntas de Active Recall sobre un libro."""
    capitulo_desde: int | None = Field(None, ge=1, description="Capítulo inicial del tramo a evaluar")
    capitulo_hasta: int | None = Field(None, ge=1, description="Capítulo final del tramo a evaluar")
    pagina_desde: int | None = Field(None, ge=1, description="Página inicial del tramo a evaluar")
    pagina_hasta: int | None = Field(None, ge=1, description="Página final del tramo a evaluar")
    cantidad: int = Field(3, ge=1, le=10, description="Cantidad de preguntas a generar (por defecto 3)")


class ActiveRecallGenerateResponse(BaseModel):
    """Respuesta con el cuestionario de Active Recall generado."""
    book_id: int
    titulo: str
    tramo_evaluado: str = Field(..., description="Descripción del tramo evaluado (ej. 'Cap. 2 / Págs. 40-75')")
    preguntas: list[ActiveRecallQuestion] = Field(..., description="Preguntas generadas")


class UserAnswerItem(BaseModel):
    """Respuesta del estudiante a una pregunta del cuestionario."""
    question_id: int = Field(..., description="ID de la pregunta respondida")
    pregunta: str = Field(..., description="Texto de la pregunta")
    respuesta_usuario: str = Field(..., min_length=2, description="Texto de la respuesta provista por el estudiante")


class ActiveRecallEvaluateRequest(BaseModel):
    """Solicitud para evaluar las respuestas provistas por el estudiante."""
    tramo_evaluado: str = Field(..., description="Tramo evaluado")
    respuestas: list[UserAnswerItem] = Field(..., min_length=1, description="Respuestas del estudiante")


class QuestionEvaluation(BaseModel):
    """Evaluación pedagógica formativa de una respuesta individual."""
    question_id: int
    puntaje: int = Field(..., ge=0, le=100, description="Puntaje de 0 a 100")
    aciertos: str = Field(..., description="Aspectos correctos identificados en la respuesta")
    mejoras: str = Field(..., description="Omisiones o conceptos a profundizar")
    explicacion_optima: str = Field(..., description="Explicación conceptual de referencia")


class ActiveRecallEvaluateResponse(BaseModel):
    """Resultado global de la evaluación de Active Recall."""
    book_id: int
    titulo: str
    score_global: int = Field(..., ge=0, le=100, description="Promedio o calificación global (0 a 100)")
    veredicto: str = Field(..., description="'excelente' (>=80), 'bueno' (>=60), 'a_repasar' (<60)")
    resumen_pedagogico: str = Field(..., description="Feedback constructivo global del tutor de IA")
    evaluaciones: list[QuestionEvaluation] = Field(..., description="Detalle por pregunta")


class BookHarvestPreviewRequest(BaseModel):
    """Solicitud para previsualizar tarjetas FSRS extraídas del libro."""
    capitulo: int | None = Field(None, ge=1, description="Capítulo específico del cual cosechar (opcional)")
    pagina: int | None = Field(None, ge=1, description="Página de referencia (opcional)")
    cantidad: int = Field(5, ge=1, le=15, description="Cantidad de tarjetas a generar (por defecto 5)")


class HarvestedCardItem(BaseModel):
    """Tarjeta candidata FSRS extraída del libro."""
    categoria: str = Field("ingles_tecnico", description="Categoría de la tarjeta")
    item_pregunta: str = Field(..., description="Pregunta en inglés / término técnico a definir o contrastar")
    respuesta_esperada: str = Field(..., description="Respuesta concisa y precisa")
    contexto_uso: str | None = Field(None, description="Ejemplo de uso en ingeniería o contexto técnico")


class BookHarvestPreviewResponse(BaseModel):
    """Resultado de la previsualización de tarjetas FSRS del libro."""
    book_id: int
    titulo: str
    tramo: str
    cards: list[HarvestedCardItem]


class BookHarvestCommitRequest(BaseModel):
    """Solicitud para guardar las tarjetas FSRS seleccionadas en el mazo de la cuenta."""
    cards: list[HarvestedCardItem] = Field(..., min_length=1)


class BookHarvestCommitResponse(BaseModel):
    """Resultado del commit de tarjetas al mazo FSRS."""
    book_id: int
    guardadas: int
    omitidas_duplicadas: int
