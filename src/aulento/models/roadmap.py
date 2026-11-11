"""Modelos de dominio Pydantic para Rutas de Aprendizaje, Módulos, Temas y Clases."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class EstadoTema(str, Enum):
    PENDIENTE = "pendiente"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"


class FuenteTema(str, Enum):
    CURADA = "curada"
    AI_GENERADA = "ai_generada"
    PDF_GAP = "pdf_gap"


class OrigenClase(str, Enum):
    GEMINI_IN_APP = "gemini_in_app"
    NOTEBOOKLM = "notebooklm"
    CLAUDE_MCP = "claude_mcp"
    CHATGPT = "chatgpt"
    EXTERNAL = "external"


class EnfoqueEstudio(str, Enum):
    PROFESIONAL = "profesional"
    ACADEMICO = "academico"
    PRACTICO_PROYECTOS = "practico_proyectos"
    PERSONAL_HOBBY = "personal_hobby"
    CERTIFICACION = "certificacion"


class AlcanceRuta(str, Enum):
    CURSO = "curso"
    ESPECIALIZACION = "especializacion"
    CARRERA = "carrera"


# --- Perfil Pedagógico por Disciplina ---

class SeccionClase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    titulo: str = Field(..., min_length=1, max_length=200)
    instruccion: str = Field(..., min_length=1, max_length=2000)


class FlashcardEjemplo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pregunta: str = Field(..., min_length=1, max_length=500)
    respuesta: str = Field(..., min_length=1, max_length=1000)


class PerfilPedagogico(BaseModel):
    """Cómo se enseña una ruta: cambia por disciplina y se guarda una vez por ruta."""

    model_config = ConfigDict(str_strip_whitespace=True)

    disciplina: str = Field(..., min_length=1, max_length=120)
    arquetipo: str = Field(default="general", min_length=1, max_length=50)
    rol_docente: str = Field(..., min_length=1, max_length=300)
    secciones: list[SeccionClase] = Field(..., min_length=3, max_length=8)
    usa_codigo: bool = False
    usa_diagramas: bool = False
    tipo_fuentes: str = Field(..., min_length=1, max_length=500)
    flashcards_ejemplo: list[FlashcardEjemplo] = Field(default_factory=list, max_length=6)
    origen: Literal["ia", "arquetipo", "editado"] = "arquetipo"


# --- Clases (Lecciones / Apuntes) ---

class RoadmapLessonCreate(BaseModel):
    tema_id: int
    titulo: str = Field(..., min_length=1, max_length=250)
    contenido_markdown: str
    diagramas_mermaid: list[str] = Field(default_factory=list)
    flashcards_json: list[dict[str, str]] = Field(default_factory=list)
    origen: OrigenClase = OrigenClase.GEMINI_IN_APP
    vault_path: str | None = None


class RoadmapLesson(RoadmapLessonCreate):
    id: int
    fecha_creacion: datetime | str | None = None
    fecha_actualizacion: datetime | str | None = None


class RoadmapLessonVersion(BaseModel):
    """Clase anterior de un tema, conservada cuando otra la reemplazó."""

    id: int
    tema_id: int
    titulo: str
    contenido_markdown: str
    diagramas_mermaid: list[str] = Field(default_factory=list)
    flashcards_json: list[dict[str, str]] = Field(default_factory=list)
    origen: OrigenClase = OrigenClase.GEMINI_IN_APP
    fecha_version: datetime | str | None = None


# --- Temas ---

class RoadmapTopicBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    descripcion: str | None = None
    orden: int = Field(default=1, ge=1)
    estado: EstadoTema = EstadoTema.PENDIENTE
    fuente: FuenteTema = FuenteTema.CURADA


class RoadmapTopicCreate(RoadmapTopicBase):
    prerrequisitos: list[str] = Field(default_factory=list)


class RoadmapTopic(RoadmapTopicBase):
    id: int
    modulo_id: int
    clase: RoadmapLesson | None = None
    fecha_creacion: datetime | str | None = None
    fecha_actualizacion: datetime | str | None = None


class TopicStatusUpdate(BaseModel):
    estado: EstadoTema


# --- Módulos ---

class RoadmapModuleBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    descripcion: str | None = None
    orden: int = Field(default=1, ge=1)


class RoadmapModuleCreate(RoadmapModuleBase):
    temas: list[RoadmapTopicCreate] = Field(default_factory=list)


class RoadmapModule(RoadmapModuleBase):
    id: int
    ruta_id: int
    temas: list[RoadmapTopic] = Field(default_factory=list)
    fecha_creacion: datetime | str | None = None


# --- Rutas de Aprendizaje ---

class RoadmapBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    descripcion: str | None = None
    categoria: str = Field(default="data_ai", max_length=50)
    nivel_objetivo: str = Field(default="Senior", max_length=50)
    enfoque_estudio: str = Field(default="profesional", max_length=50)
    progreso_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RoadmapCreate(RoadmapBase):
    modulos: list[RoadmapModuleCreate] = Field(default_factory=list)


class RoadmapUpdate(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    categoria: str | None = None
    nivel_objetivo: str | None = None
    enfoque_estudio: str | None = None
    progreso_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    metadata_json: dict[str, Any] | None = None


class Roadmap(RoadmapBase):
    id: int
    total_temas: int = 0
    temas_completados: int = 0
    fecha_creacion: datetime | str | None = None
    fecha_actualizacion: datetime | str | None = None


class RoadmapDetail(Roadmap):
    modulos: list[RoadmapModule] = Field(default_factory=list)


# --- DTOs Pedagógicos y Operativos ---

class LessonPromptRequest(BaseModel):
    include_materials: bool = True
    include_web_research: bool = True
    sop_style: bool = True
    include_fsrs_cards: bool = True
    target_llm: str = "notebooklm"  # notebooklm | claude | chatgpt | gemini
    # Generación in-app: el modelo no tiene buscador ni acceso a archivos.
    sin_herramientas: bool = False
    # Opciones de contenido: apagadas, el prompt no las menciona.
    include_visuals: bool = False
    include_slides: bool = False
    include_quiz: bool = False
    include_glossary: bool = False
    include_bridge: bool = False
    depth: Literal["breve", "estandar", "exhaustiva"] = "estandar"


class LessonPromptResponse(BaseModel):
    topic_id: int
    topic_title: str
    roadmap_title: str
    master_prompt: str
    instructions: str


class LessonImportRequest(BaseModel):
    markdown_content: str = Field(..., min_length=10)
    origen: OrigenClase = OrigenClase.NOTEBOOKLM


class LessonImportResponse(BaseModel):
    lesson_id: int
    tema_id: int
    titulo: str
    cards_count: int
    mermaid_count: int
    vault_path: str | None = None
    flashcards: list[dict[str, str]] = Field(default_factory=list)


class GapTopicItem(BaseModel):
    titulo: str
    descripcion: str | None = None
    modulo_sugerido: str | None = None


class PDFComparisonResult(BaseModel):
    total_syllabus_topics: int = 0
    matched_topics: list[str] = Field(default_factory=list)
    gap_topics: list[GapTopicItem] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    summary: str
    is_fallback: bool = Field(False, description="True si el resultado se obtuvo sin IA (sin clave, sin cuota o sin respuesta utilizable)")
    motivo_sin_ia: str | None = Field(None, description="Por qué no hubo IA, cuando la causa no es que falte cargar la clave")


class RoadmapMergeRequest(BaseModel):
    gap_topics: list[GapTopicItem]
    default_module_title: str = "Módulo Especialización / Blueprint Externo"


class SuggestNextTopicsResponse(BaseModel):
    completed_topics_count: int
    suggested_topics: list[GapTopicItem]
    reasoning: str
    is_fallback: bool = Field(False, description="True si el resultado se obtuvo sin IA (sin clave, sin cuota o sin respuesta utilizable)")
    motivo_sin_ia: str | None = Field(None, description="Por qué no hubo IA, cuando la causa no es que falte cargar la clave")


# --- Prerrequisitos & Grafo DAG ---

class PrerequisiteEdge(BaseModel):
    id: int | None = None
    ruta_id: int
    tema_origen_id: int
    tema_destino_id: int
    origen_titulo: str | None = None
    destino_titulo: str | None = None
    tipo: str = "estricta"  # "estricta" | "recomendada"
    # True cuando la arista sale de la secuencia implícita de la ruta: no está guardada (`id` es None).
    inferida: bool = False


class PrerequisiteCreate(BaseModel):
    tema_origen_id: int
    tema_destino_id: int
    tipo: Literal["estricta", "recomendada"] = "estricta"


class PrerequisiteBulkCreate(BaseModel):
    prelaciones: list[PrerequisiteCreate] = Field(..., min_length=1, max_length=300)
    secuencia_implicita: bool | None = None


class GraphSettingsUpdate(BaseModel):
    secuencia_implicita: bool


class PrerequisiteSuggestion(BaseModel):
    tema_origen_id: int
    tema_destino_id: int
    origen_titulo: str
    destino_titulo: str
    tipo: Literal["estricta", "recomendada"] = "estricta"
    motivo: str = ""


class PrerequisiteSuggestionResponse(BaseModel):
    sugerencias: list[PrerequisiteSuggestion] = Field(default_factory=list)
    descartadas: int = 0


class RoadmapGraphNode(BaseModel):
    id: int
    modulo_id: int
    modulo_titulo: str
    titulo: str
    descripcion: str | None = None
    orden: int
    estado: str  # pendiente | en_progreso | completado
    nivel_topologico: int = 0
    es_bloqueante: bool = False
    is_blocked: bool = False
    disponible: bool = False
    is_critical_path: bool = False
    in_degree: int = 0
    out_degree: int = 0
    prerequisites: list[int] = Field(default_factory=list)
    dependents: list[int] = Field(default_factory=list)


class RoadmapGraphData(BaseModel):
    ruta_id: int
    ruta_titulo: str
    nodes: list[RoadmapGraphNode] = Field(default_factory=list)
    edges: list[PrerequisiteEdge] = Field(default_factory=list)
    topological_order: list[int] = Field(default_factory=list)
    critical_path: list[int] = Field(default_factory=list)
    has_cycle: bool = False
    mermaid_code: str = ""
    disponibles: list[int] = Field(default_factory=list)
    secuencia_implicita: bool = True


# --- Ingesta de Temarios Multiformato ---

class SyllabusIngestRequest(BaseModel):
    titulo: str = Field(..., min_length=2, max_length=200)
    contenido_texto: str = Field(..., min_length=10)
    formato: str = "texto"  # "pdf" | "markdown" | "texto"
    categoria: str = "data_ai"
    nivel_objetivo: str = "Senior"
    enfoque_estudio: str = "profesional"
    enhance_with_ai: bool = True


class SyllabusParsedPreview(BaseModel):
    titulo: str
    categoria: str
    nivel_objetivo: str
    enfoque_estudio: str
    modulos: list[RoadmapModuleCreate] = Field(default_factory=list)
    sugerencias_ia: list[str] = Field(default_factory=list)
    prerrequisitos_detectados: list[dict[str, str]] = Field(default_factory=list)


# --- Analítica de Tokens y Costos ---

class TokenLogItem(BaseModel):
    id: int
    timestamp: str | datetime
    provider: str = "gemini"
    model: str
    endpoint_tipo: str
    api_tier: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    status_code: int
    latency_ms: float


class TokenUsageSummary(BaseModel):
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    by_model: dict[str, dict[str, Any]] = Field(default_factory=dict)
    by_endpoint: dict[str, dict[str, Any]] = Field(default_factory=dict)
    by_tier: dict[str, dict[str, Any]] = Field(default_factory=dict)
    recent_logs: list[TokenLogItem] = Field(default_factory=list)


class DualKeyConfig(BaseModel):
    key_free: str | None = None
    key_paid: str | None = None
    gemini_free_key: str | None = None
    gemini_paid_key: str | None = None
    active_tier: str = "auto"  # "free" | "paid" | "auto"
    preferred_model: str | None = None

    def get_free_key(self) -> str | None:
        return self.gemini_free_key or self.key_free

    def get_paid_key(self) -> str | None:
        return self.gemini_paid_key or self.key_paid


class DualKeyStatus(BaseModel):
    has_free_key: bool = False
    has_paid_key: bool = False
    active_tier: str = "free"
    free_key_masked: str | None = None
    paid_key_masked: str | None = None
    free_key_error: str | None = None
    paid_key_error: str | None = None
    active_model: str = "gemini-flash-lite-latest"

