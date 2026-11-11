"""Router FastAPI para Rutas de Aprendizaje, Comparación de PDFs, DAG y Lesson Studio."""

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from aulento.db.roadmap_repository import (
    PrerequisiteCycleError,
    RoadmapNotFoundError,
)
from aulento.mcp.pdf_text import PdfSinTextoError
from aulento.models.roadmap import (
    AlcanceRuta,
    EnfoqueEstudio,
    GraphSettingsUpdate,
    LessonImportRequest,
    LessonImportResponse,
    LessonPromptRequest,
    LessonPromptResponse,
    PDFComparisonResult,
    PerfilPedagogico,
    PrerequisiteBulkCreate,
    PrerequisiteCreate,
    PrerequisiteSuggestionResponse,
    Roadmap,
    RoadmapCreate,
    RoadmapDetail,
    RoadmapGraphData,
    RoadmapLesson,
    RoadmapLessonVersion,
    RoadmapMergeRequest,
    RoadmapTopic,
    SuggestNextTopicsResponse,
    SyllabusIngestRequest,
    SyllabusParsedPreview,
    TopicStatusUpdate,
)
from aulento.roadmap.graph_engine import PrerequisiteGraphEngine
from aulento.roadmap.lesson_studio import ClaseNoGeneradaError
from aulento.roadmap.pedagogical_profiles import CLAVE_PERFIL, perfil_de_ruta
from aulento.roadmap.prerequisite_advisor import PrerequisiteAdvisor
from aulento.roadmap.prompt_builder import LessonPromptBuilder
from aulento.roadmap.syllabus_ingestor import SyllabusIngestor
from aulento.vault.rutas import RutaFueraDelVaultError, VaultNoDisponibleError
from aulento.web.dependencies import (
    ComparadorDeTemarios,
    EstudioDeClases,
    MotorDeRutas,
    PromptsDeLaCuenta,
    RepoRutas,
    SinCuentaCompartida,
    no_encontrado,
)

router = APIRouter(prefix="/api/roadmap", tags=["Roadmaps"])


class GenerateRoadmapRequest(BaseModel):
    prompt: str = Field(..., description="Objetivo profesional o tecnología a dominar")
    target_role: str = Field("Data Engineer", description="Rol profesional objetivo")
    experience_level: str = Field("Senior", description="Nivel: Junior, Semi-Senior, Senior, Staff")
    categoria: str = Field("general", description="Categoría temática o personalizada de la ruta")
    enfoque_estudio: str = Field("profesional", description="profesional, academico, practico_proyectos, personal_hobby, certificacion")
    alcance: AlcanceRuta = Field(AlcanceRuta.CURSO, description="Tamaño de la ruta: curso, especializacion o carrera")


class SystemPromptUpdateRequest(BaseModel):
    prompt_type: str = Field(..., description="'roadmap' o 'lesson'")
    content: str = Field(..., min_length=10)


class SystemPromptResetRequest(BaseModel):
    prompt_type: str = Field("all", description="'roadmap', 'lesson' o 'all'")


@router.get("", response_model=list[Roadmap])
def list_roadmaps(repo: RepoRutas):
    """Lista todas las rutas de aprendizaje con conteos y porcentajes de progreso."""
    return repo.get_roadmaps()


@router.get("/templates", response_model=list[RoadmapCreate])
def list_templates(engine: MotorDeRutas):
    """Retorna las plantillas curadas de la industria listas para crear."""
    return engine.get_templates()


@router.post("/templates/seed", response_model=list[RoadmapDetail])
def seed_templates(repo: RepoRutas, solo_la_primera_vez: bool = False):
    """Carga, solo para la cuenta, las plantillas canónicas que todavía no tenga.

    Con `solo_la_primera_vez` (la siembra automática de la pantalla) corre una sola vez por cuenta.
    """
    return repo.ensure_curated_templates(solo_la_primera_vez=solo_la_primera_vez)


@router.post("", response_model=RoadmapDetail)
def create_roadmap(data: RoadmapCreate, repo: RepoRutas):
    """Crea manualmente o desde plantilla una ruta con sus módulos y temas."""
    return repo.create_roadmap(data)


@router.post("/generate", response_model=RoadmapDetail)
def generate_roadmap(req: GenerateRoadmapRequest, repo: RepoRutas, engine: MotorDeRutas):
    """Genera una nueva ruta con Gemini 1.5 Flash (o plantillas) y la guarda de inmediato."""
    # Antes de llamar a la IA: si la cuenta no puede crear otra ruta, no se gasta la llamada (062)
    repo.exigir_poder_crear_una_ruta()
    created_data = engine.generate_roadmap_with_ai(
        prompt=req.prompt,
        target_role=req.target_role,
        experience_level=req.experience_level,
        category=req.categoria,
        enfoque_estudio=req.enfoque_estudio,
        alcance=req.alcance,
    )
    # Persistir en base de datos
    return repo.create_roadmap(created_data)


@router.post("/modules/{module_id}/expand", response_model=list[RoadmapTopic])
def expand_module(module_id: int, engine: MotorDeRutas):
    """Genera con IA los temas de un módulo o materia y los agrega sin duplicar títulos."""
    if not engine.repo.get_module_with_context(module_id):
        raise no_encontrado("Módulo", module_id)
    try:
        return engine.expand_module(module_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==========================================
# SYSTEM PROMPTS CONFIGURABLES
# ==========================================

@router.get("/system-prompts")
def get_system_prompts(prompts: PromptsDeLaCuenta):
    """Retorna los System Prompts de la cuenta y los predeterminados para Rutas y Clases."""
    return {
        "roadmap_prompt": prompts.get_roadmap_system_prompt(),
        "lesson_prompt": prompts.get_lesson_system_prompt(),
        "roadmap_default": prompts.DEFAULT_ROADMAP_SYSTEM_PROMPT,
        "lesson_default": prompts.DEFAULT_LESSON_SYSTEM_PROMPT,
    }


@router.post("/system-prompts", dependencies=[SinCuentaCompartida])
def update_system_prompt(req: SystemPromptUpdateRequest, prompts: PromptsDeLaCuenta):
    """Guarda, para la cuenta, una personalización del System Prompt para rutas o clases."""
    if req.prompt_type == "roadmap":
        prompts.save_custom_roadmap_prompt(req.content)
    elif req.prompt_type == "lesson":
        prompts.save_custom_lesson_prompt(req.content)
    else:
        raise HTTPException(status_code=400, detail="prompt_type debe ser 'roadmap' o 'lesson'.")

    return {
        "status": "ok",
        "prompt_type": req.prompt_type,
        "message": "System prompt actualizado exitosamente.",
    }


@router.post("/system-prompts/reset", dependencies=[SinCuentaCompartida])
def reset_system_prompts(req: SystemPromptResetRequest, prompts: PromptsDeLaCuenta):
    """Vuelve los System Prompts de la cuenta a los predeterminados."""
    prompts.reset_to_default(req.prompt_type)
    return {
        "status": "ok",
        "prompt_type": req.prompt_type,
        "message": "System prompts restablecidos a los valores por defecto.",
    }


# ==========================================
# INGESTA DE SÍLABOS / TEMARIOS (PDF / TEXT)
# ==========================================

@router.post("/import-syllabus")
def import_syllabus_json(
    req: SyllabusIngestRequest,
    repo: RepoRutas,
    create_direct: bool = False,
):
    """Parsea un temario en texto plano o Markdown con Gap Analysis opcional con IA."""
    if create_direct:
        repo.exigir_poder_crear_una_ruta()
    modules = SyllabusIngestor.parse_text_to_modules(req.contenido_texto)
    enhancements: list[str] = []

    if req.enhance_with_ai:
        try:
            enfoque_enum = EnfoqueEstudio(req.enfoque_estudio)
        except ValueError:
            enfoque_enum = EnfoqueEstudio.PROFESIONAL

        modules, enhancements = SyllabusIngestor.enhance_with_ai(
            modules=modules,
            title=req.titulo,
            target_role=req.titulo,
            category=req.categoria,
            enfoque_estudio=enfoque_enum,
            nivel_objetivo=req.nivel_objetivo,
            repo=repo,
        )

    if create_direct:
        new_roadmap = RoadmapCreate(
            titulo=req.titulo,
            descripcion=f"Ruta importada de sílabo para {req.titulo}",
            categoria=req.categoria,
            nivel_objetivo=req.nivel_objetivo,
            enfoque_estudio=req.enfoque_estudio,
            modulos=modules,
        )
        created = repo.create_roadmap(new_roadmap)
        return {"mode": "created", "roadmap": created, "sugerencias_ia": enhancements}

    return SyllabusParsedPreview(
        titulo=req.titulo,
        categoria=req.categoria,
        nivel_objetivo=req.nivel_objetivo,
        enfoque_estudio=req.enfoque_estudio,
        modulos=modules,
        sugerencias_ia=enhancements,
    )


MAX_BYTES_POR_ARCHIVO_SYLLABUS = 25 * 1024 * 1024  # 25 MB
MARGEN_DEL_FORMULARIO_SYLLABUS = 64 * 1024
BYTES_POR_LECTURA_SYLLABUS = 64 * 1024


async def _comprobar_tamano_syllabus(request: Request):
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > MAX_BYTES_POR_ARCHIVO_SYLLABUS + MARGEN_DEL_FORMULARIO_SYLLABUS:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="El cuerpo del pedido supera el límite de 25 MB.",
        )


async def _leer_upload_syllabus_acotado(file: UploadFile) -> bytes:
    datos = bytearray()
    while bloque := await file.read(BYTES_POR_LECTURA_SYLLABUS):
        datos += bloque
        if len(datos) > MAX_BYTES_POR_ARCHIVO_SYLLABUS:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="El archivo supera el tamaño máximo permitido (25 MB).",
            )
    return bytes(datos)


@router.post("/import-syllabus-file", dependencies=[Depends(_comprobar_tamano_syllabus)])
async def import_syllabus_file(
    repo: RepoRutas,
    file: UploadFile = File(...),  # noqa: B008
    titulo: str = Form(...),
    target_role: str = Form(""),
    categoria: str = Form("data_ai"),
    nivel_objetivo: str = Form("Senior"),
    enfoque_estudio: str = Form("profesional"),
    enhance_with_ai: bool = Form(True),
    create_direct: bool = Form(False),
):
    """Sube un archivo PDF, Markdown o TXT para extracción y estructuración curricular."""
    if create_direct:
        repo.exigir_poder_crear_una_ruta()
    file_bytes = await _leer_upload_syllabus_acotado(file)
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        try:
            raw_text = await run_in_threadpool(SyllabusIngestor.extract_text_from_pdf_bytes, file_bytes)
        except PdfSinTextoError as error:
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo extraer texto legible del archivo adjunto: {error}.",
            )
    else:
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1", errors="ignore")

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No se pudo extraer texto legible del archivo adjunto. Asegúrate de que no esté protegido por contraseña.",
        )

    role_title = target_role or titulo
    modules = await run_in_threadpool(SyllabusIngestor.parse_text_to_modules, raw_text)
    enhancements: list[str] = []

    if enhance_with_ai:
        try:
            enfoque_enum = EnfoqueEstudio(enfoque_estudio)
        except ValueError:
            enfoque_enum = EnfoqueEstudio.PROFESIONAL

        modules, enhancements = SyllabusIngestor.enhance_with_ai(
            modules=modules,
            title=titulo,
            target_role=role_title,
            category=categoria,
            enfoque_estudio=enfoque_enum,
            nivel_objetivo=nivel_objetivo,
            repo=repo,
        )

    if create_direct:
        new_roadmap = RoadmapCreate(
            titulo=titulo,
            descripcion=f"Ruta importada de archivo {file.filename}",
            categoria=categoria,
            nivel_objetivo=nivel_objetivo,
            enfoque_estudio=enfoque_estudio,
            modulos=modules,
        )
        created = repo.create_roadmap(new_roadmap)
        return {"mode": "created", "roadmap": created, "sugerencias_ia": enhancements}

    return SyllabusParsedPreview(
        titulo=titulo,
        categoria=categoria,
        nivel_objetivo=nivel_objetivo,
        enfoque_estudio=enfoque_estudio,
        modulos=modules,
        sugerencias_ia=enhancements,
    )


@router.get("/{roadmap_id}", response_model=RoadmapDetail)
def get_roadmap(roadmap_id: int, repo: RepoRutas):
    """Obtiene el árbol jerárquico completo de una ruta con sus módulos, temas y clases."""
    detail = repo.get_roadmap(roadmap_id)
    if not detail:
        raise no_encontrado("Ruta", roadmap_id)
    return detail


@router.get("/{roadmap_id}/pedagogical-profile", response_model=PerfilPedagogico)
def get_pedagogical_profile(roadmap_id: int, repo: RepoRutas):
    """Devuelve el perfil pedagógico de la ruta (el guardado o el resuelto al vuelo por arquetipo)."""
    detail = repo.get_roadmap(roadmap_id)
    if not detail:
        raise no_encontrado("Ruta", roadmap_id)
    return perfil_de_ruta(detail.metadata_json, detail.categoria, detail.titulo)


@router.put("/{roadmap_id}/pedagogical-profile", response_model=PerfilPedagogico)
def update_pedagogical_profile(
    roadmap_id: int,
    perfil: PerfilPedagogico,
    repo: RepoRutas,
):
    """Guarda el perfil pedagógico editado por el usuario; su origen pasa a `editado`."""
    detail = repo.get_roadmap(roadmap_id)
    if not detail:
        raise no_encontrado("Ruta", roadmap_id)

    perfil.origen = "editado"
    metadata = dict(detail.metadata_json or {})
    metadata[CLAVE_PERFIL] = perfil.model_dump()
    repo.update_roadmap_metadata(roadmap_id, metadata)
    return perfil


@router.delete("/{roadmap_id}", dependencies=[SinCuentaCompartida])
def delete_roadmap(roadmap_id: int, repo: RepoRutas):
    """Elimina una ruta y todos sus elementos en cascada."""
    deleted = repo.delete_roadmap(roadmap_id)
    if not deleted:
        raise no_encontrado("Ruta", roadmap_id)
    return {"status": "ok", "deleted_id": roadmap_id}


@router.post(
    "/{roadmap_id}/compare-pdf",
    response_model=PDFComparisonResult,
    dependencies=[Depends(_comprobar_tamano_syllabus)],
)
async def compare_pdf_syllabus(
    roadmap_id: int,
    repo: RepoRutas,
    comparator: ComparadorDeTemarios,
    file: UploadFile = File(...),  # noqa: B008
):
    """Sube un PDF de temario y realiza un Gap Analysis comparativo contra la ruta activa."""
    detail = repo.get_roadmap(roadmap_id)
    if not detail:
        raise no_encontrado("Ruta", roadmap_id)

    pdf_bytes = await _leer_upload_syllabus_acotado(file)
    return await run_in_threadpool(
        comparator.compare_syllabus,
        detail,
        pdf_bytes,
        filename=file.filename or "syllabus.pdf",
    )


@router.post("/{roadmap_id}/merge")
def merge_gap_topics(
    roadmap_id: int,
    req: RoadmapMergeRequest,
    repo: RepoRutas,
):
    """Incorpora los temas faltantes detectados en un PDF a la ruta activa."""
    detail = repo.get_roadmap(roadmap_id)
    if not detail:
        raise no_encontrado("Ruta", roadmap_id)

    inserted_count = repo.merge_gap_topics(
        roadmap_id=roadmap_id,
        gap_topics=req.gap_topics,
        default_module_title=req.default_module_title,
    )
    return {"status": "ok", "inserted_topics": inserted_count}


@router.post("/{roadmap_id}/suggest-next", response_model=SuggestNextTopicsResponse)
def suggest_next_topics(roadmap_id: int, repo: RepoRutas, engine: MotorDeRutas):
    """Sugiere dinámicamente nuevos temas avanzados ($i+1$) basándose en los temas completados."""
    if not repo.get_roadmap(roadmap_id):
        raise no_encontrado("Ruta", roadmap_id)
    return engine.suggest_next_topics(roadmap_id)


@router.post("/topics/{topic_id}/status", response_model=RoadmapTopic)
def update_topic_status(
    topic_id: int,
    update: TopicStatusUpdate,
    repo: RepoRutas,
):
    """Actualiza el estado de un tema (pendiente | en_progreso | completado) y recalcula el progreso."""
    updated = repo.update_topic_status(topic_id, update.estado)
    if not updated:
        raise no_encontrado("Tema", topic_id)
    return updated


@router.post("/topics/{topic_id}/build-prompt", response_model=LessonPromptResponse)
def build_lesson_prompt(
    topic_id: int,
    req: LessonPromptRequest,
    repo: RepoRutas,
):
    """Construye el Prompt Maestro para NotebookLM, Claude con MCP o ChatGPT."""
    if not repo.get_topic_with_context(topic_id):
        raise no_encontrado("Tema", topic_id)
    builder = LessonPromptBuilder(repo=repo)
    try:
        return builder.build_prompt(topic_id, req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/topics/{topic_id}/generate-lesson", response_model=RoadmapLesson)
def generate_lesson_in_app(
    topic_id: int,
    studio: EstudioDeClases,
    options: LessonPromptRequest | None = Body(default=None),  # noqa: B008
):
    """Genera la clase in-app con Gemini; el cuerpo opcional lleva las opciones del Prompt Maestro."""
    if not studio.repo.get_topic_with_context(topic_id):
        raise no_encontrado("Tema", topic_id)
    try:
        return studio.generate_lesson_in_app(topic_id, options)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ClaseNoGeneradaError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/topics/{topic_id}/import-lesson", response_model=LessonImportResponse)
def import_external_lesson(
    topic_id: int,
    req: LessonImportRequest,
    repo: RepoRutas,
    studio: EstudioDeClases,
):
    """Importa una clase externa copiada desde NotebookLM, Claude o ChatGPT."""
    if not repo.get_topic_with_context(topic_id):
        raise no_encontrado("Tema", topic_id)
    lesson = studio.import_external_lesson(
        topic_id=topic_id,
        markdown_text=req.markdown_content,
        origen=req.origen,
    )
    return LessonImportResponse(
        lesson_id=lesson.id,
        tema_id=lesson.tema_id,
        titulo=lesson.titulo,
        cards_count=len(lesson.flashcards_json),
        mermaid_count=len(lesson.diagramas_mermaid),
        vault_path=lesson.vault_path,
        flashcards=lesson.flashcards_json,
    )


@router.get("/topics/{topic_id}/lesson-versions", response_model=list[RoadmapLessonVersion])
def list_lesson_versions(topic_id: int, repo: RepoRutas):
    """Versiones anteriores de la clase de un tema, de la más reciente a la más antigua."""
    if not repo.get_topic_with_context(topic_id):
        raise no_encontrado("Tema", topic_id)
    return repo.get_lesson_versions(topic_id)


@router.post("/lesson-versions/{version_id}/restore", response_model=RoadmapLesson)
def restore_lesson_version(version_id: int, repo: RepoRutas):
    """Restaura una versión anterior; la clase vigente queda a su vez como versión."""
    restaurada = repo.restore_lesson_version(version_id)
    if not restaurada:
        raise no_encontrado("Versión", version_id)
    return restaurada


@router.post("/lessons/{lesson_id}/export-fsrs")
def export_lesson_to_fsrs(lesson_id: int, studio: EstudioDeClases):
    """Inyecta las flashcards de una clase en el mazo de su ruta, a nombre de la cuenta."""
    if not studio.clase_existe(lesson_id):
        raise no_encontrado("Clase", lesson_id)
    count = studio.export_flashcards_to_fsrs(lesson_id)
    return {"status": "ok", "cards_exported": count}


@router.post("/lessons/{lesson_id}/export-vault")
def export_lesson_to_vault(lesson_id: int, studio: EstudioDeClases):
    """Exporta el apunte canónico de la clase al vault de la cuenta según el SOP oficial."""
    if not studio.clase_existe(lesson_id):
        raise no_encontrado("Clase", lesson_id)
    try:
        studio.export_lesson_to_vault(lesson_id)
        # Rutas relativas al vault de la cuenta: la respuesta no dice dónde está el vault en el servidor
        return {
            "status": "ok",
            "vault_path": studio.last_relative_path,
            "backup_path": studio.last_backup_relative_path,
        }
    except (RutaFueraDelVaultError, VaultNoDisponibleError):
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# GRAFO DE PRELACIONES Y DAG INTERACTIVO
# ==========================================

@router.get("/{roadmap_id}/graph", response_model=RoadmapGraphData)
def get_roadmap_graph(roadmap_id: int, repo: RepoRutas):
    """Calcula y retorna el grafo DAG de prelaciones con orden topológico, ruta crítica y Mermaid."""
    if not repo.get_roadmap(roadmap_id):
        raise no_encontrado("Ruta", roadmap_id)
    graph_engine = PrerequisiteGraphEngine(repo=repo)
    try:
        return graph_engine.get_graph_data(roadmap_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{roadmap_id}/interactive-map", response_class=HTMLResponse)
def get_roadmap_interactive_map(roadmap_id: int, repo: RepoRutas):
    """Renderiza el Mapa Interactivo de Aprendizaje embebido para la ruta."""
    if not repo.get_roadmap(roadmap_id):
        raise no_encontrado("Ruta", roadmap_id)
    graph_engine = PrerequisiteGraphEngine(repo=repo)
    try:
        return HTMLResponse(graph_engine.render_interactive_map_html(roadmap_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{roadmap_id}/prerequisites")
def add_prerequisite(
    roadmap_id: int,
    req: PrerequisiteCreate,
    repo: RepoRutas,
):
    """Registra una prelación entre dos temas de la ruta, o actualiza su tipo si ya existe.

    Responde 400 si algún tema no pertenece a la ruta o si son el mismo, y 409 si cerraría un ciclo.
    """
    try:
        edge = repo.add_prerequisite(
            ruta_id=roadmap_id,
            tema_origen_id=req.tema_origen_id,
            tema_destino_id=req.tema_destino_id,
            tipo=req.tipo,
        )
        return {"status": "ok", "edge": edge}
    except RoadmapNotFoundError:
        raise no_encontrado("Ruta", roadmap_id) from None
    except PrerequisiteCycleError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{roadmap_id}/prerequisites/bulk")
def add_prerequisites_bulk(
    roadmap_id: int,
    req: PrerequisiteBulkCreate,
    repo: RepoRutas,
):
    """Guarda un conjunto de prelaciones de forma atómica: si una es inválida no se guarda ninguna.

    Si viene `secuencia_implicita`, el ajuste se guarda en la misma transacción que las prelaciones.
    """
    try:
        guardadas = repo.add_prerequisites_bulk(roadmap_id, req.prelaciones, req.secuencia_implicita)
    except RoadmapNotFoundError:
        raise no_encontrado("Ruta", roadmap_id) from None
    except PrerequisiteCycleError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "guardadas": guardadas}


@router.post("/{roadmap_id}/prerequisites/suggest", response_model=PrerequisiteSuggestionResponse)
def suggest_prerequisites(roadmap_id: int, repo: RepoRutas):
    """Propone prelaciones con IA para la ruta, ya filtradas, sin guardar ninguna."""
    if not repo.get_roadmap(roadmap_id):
        raise no_encontrado("Ruta", roadmap_id)
    try:
        return PrerequisiteAdvisor(repo=repo).suggest(roadmap_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{roadmap_id}/graph-settings")
def update_graph_settings(
    roadmap_id: int,
    req: GraphSettingsUpdate,
    repo: RepoRutas,
):
    """Activa o desactiva la secuencia implícita del grafo de la ruta."""
    if not repo.update_graph_settings(roadmap_id, req.secuencia_implicita):
        raise no_encontrado("Ruta", roadmap_id)
    return {"status": "ok", "secuencia_implicita": req.secuencia_implicita}


@router.delete("/{roadmap_id}/prerequisites/{orig_id}/{dest_id}", dependencies=[SinCuentaCompartida])
def delete_prerequisite(
    roadmap_id: int,
    orig_id: int,
    dest_id: int,
    repo: RepoRutas,
):
    """Elimina una prelación entre dos temas."""
    deleted = repo.delete_prerequisite(
        ruta_id=roadmap_id,
        tema_origen_id=orig_id,
        tema_destino_id=dest_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Prelación no encontrada.")
    return {"status": "ok"}
