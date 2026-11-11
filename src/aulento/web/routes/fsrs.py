"""Router para la gestión del motor FSRS v5 e inglés técnico profesional."""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from aulento.vault.carpetas import carpetas_del_tutor
from aulento.vault.rutas import vault_de_la_cuenta
from aulento.web.dependencies import (
    SinCuentaCompartida,
    ClavesDeGemini,
    Conexion,
    Cuenta,
    IADeLaCuenta,
    MotorFsrs,
    RepoFsrs,
    TutorDeVoz,
    no_encontrado,
)
from aulento.db.fsrs_repository import FSRSRepository, MazoDeRutaNoEncontradoError
from aulento.fsrs.stats import get_full_fsrs_stats
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.models.fsrs_card import FSRSCard, FSRSRating

router = APIRouter(prefix="/api/fsrs", tags=["FSRS"])


class ReviewRequest(BaseModel):
    card_id: int
    rating: int = Field(..., ge=1, le=4, description="Calificación FSRS: 1=Again, 2=Hard, 3=Good, 4=Easy")


class ReviewResponse(BaseModel):
    card_id: int
    rating_name: str
    estabilidad_anterior: Optional[float] = None
    estabilidad_nueva: Optional[float] = None
    dificultad_nueva: Optional[float] = None
    proximo_repaso: Optional[str] = None
    repasos_totales: int
    lapsos: int


def exigir_mazo(repo: FSRSRepository, categoria: Optional[str]) -> None:
    """Responde 404 si la categoría es un mazo de ruta que no es de la cuenta, con la regla del repositorio."""
    try:
        repo.exigir_mazo_de_la_cuenta(categoria)
    except MazoDeRutaNoEncontradoError as e:
        raise no_encontrado("Ruta", e.roadmap_id) from None


@router.get("/status")
def get_fsrs_status(usuario: Cuenta, conn: Conexion) -> Dict[str, Any]:
    """Retorna las estadísticas del mazo FSRS de la cuenta: racha, retención y tarjetas pendientes."""
    stats = get_full_fsrs_stats(conn, usuario.id)
    return {
        "tarjetas_totales": stats["total_cards"],
        "vencidas_hoy": stats["due_today"],
        "retencion_pct": stats["retention_rate"],
        "racha_dias": stats["streak_days"],
        "estado_cognitivo": {
            "new": stats["new"],
            "learning": stats["learning"],
            "review": stats["review"],
            "relearning": stats["relearning"],
        },
        "repasos_historicos": stats["total_reviews"],
        "por_categoria": stats["categories"],
    }


@router.get("/due", response_model=List[FSRSCard])
def get_due_cards(
    repo: RepoFsrs,
    engine: MotorFsrs,
    limit: int = Query(15, ge=1, le=100),
    level: Optional[str] = Query(None, description="Filtro: nivel (a1, a2, b1, b2, c1, all, adaptive) o mazo de una ruta (roadmap_<id>)"),
    force: bool = Query(False, description="Forzar entrega de tarjetas para práctica extra/cram incluso si no vencieron"),
):
    """Obtiene las tarjetas que vencieron y deben repasarse en la sesión actual, filtrando opcionalmente por nivel."""
    exigir_mazo(repo, level)
    return engine.get_session_cards(limit=limit, level=level, force=force)


@router.get("/decks")
def get_roadmap_decks(repo: RepoFsrs) -> List[Dict[str, Any]]:
    """Lista los mazos de rutas de la cuenta que tienen tarjetas, para repasar una ruta por separado."""
    return repo.get_roadmap_decks()


@router.post("/review", response_model=ReviewResponse)
def review_card(data: ReviewRequest, repo: RepoFsrs, engine: MotorFsrs):
    """Aplica el algoritmo FSRS v5 al calificar una tarjeta de la cuenta."""
    card = repo.get_card_by_id(data.card_id)
    if not card:
        raise no_encontrado("Tarjeta", data.card_id)

    try:
        rating_enum = FSRSRating(data.rating)
    except ValueError:
        raise HTTPException(status_code=400, detail="Rating debe ser entre 1 y 4.")

    estabilidad_ant = card.stability
    updated_card, log = engine.review(card.id, rating_enum)

    return ReviewResponse(
        card_id=updated_card.id,
        rating_name=rating_enum.name,
        estabilidad_anterior=estabilidad_ant,
        estabilidad_nueva=updated_card.stability,
        dificultad_nueva=updated_card.difficulty,
        proximo_repaso=str(updated_card.due) if updated_card.due else None,
        repasos_totales=updated_card.reps,
        lapsos=updated_card.lapses,
    )


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_deck(usuario: Cuenta, conn: Conexion):
    """Siembra, solo para la cuenta, el mazo de 100 colocaciones iniciales de inglés técnico si está vacío."""
    total = seed_fsrs_deck(conn, usuario.id)
    return {"status": "ok", "colocaciones_sembradas": total}


# --- AUDIO TTS & FONÉTICA ---
from aulento.audio.tts import (
    TTSEngine,
    SpeechRequest,
    SpeechResponse,
    PronunciationRequest,
    PronunciationEvaluation,
)


@router.get("/audio/config")
def get_audio_config() -> Dict[str, Any]:
    """Retorna los acentos, velocidades y capacidades soportadas por el motor TTS."""
    engine = TTSEngine()
    return engine.get_config()


@router.post("/audio/speak", response_model=SpeechResponse)
def speak_technical_term(data: SpeechRequest) -> SpeechResponse:
    """Genera la respuesta con guía fonética IPA y metadatos para reproducción vocal."""
    engine = TTSEngine()
    return engine.synthesize(data)


@router.post("/audio/evaluate-pronunciation", response_model=PronunciationEvaluation)
def evaluate_pronunciation(data: PronunciationRequest) -> PronunciationEvaluation:
    """Evalúa la precisión fonética y léxica de lo pronunciado frente a la colocación esperada."""
    engine = TTSEngine()
    return engine.evaluate_pronunciation(data)


# --- GEMINI 1.5 FLASH VOICE TUTOR (MULTIMODAL & PEDAGOGICAL) ---
from aulento.audio.gemini_tutor import (
    GeminiEvaluationRequest,
    GeminiVoiceEvaluation,
)


class GeminiKeyRequest(BaseModel):
    key: Optional[str] = Field(None, description="Google AI Studio API Key")
    model: Optional[str] = Field(None, description="Preferred Gemini Model")


@router.get("/audio/gemini-status")
def get_gemini_tutor_status(gemini: ClavesDeGemini) -> Dict[str, Any]:
    """Retorna si la cuenta tiene Gemini configurado con API key y qué modelo de Gemini tiene activo."""
    configurado = bool(gemini.get_active_api_key())
    return {
        "configured": configurado,
        "model": gemini.resolve_model(),
        "free_tier": True,
        "mode": "gemini-1.5-flash" if configurado else "local-fallback",
    }


@router.post("/audio/gemini-key", dependencies=[SinCuentaCompartida])
def set_gemini_api_key(req: GeminiKeyRequest, pasarela: ClavesDeGemini) -> Dict[str, Any]:
    """Guarda, para la cuenta, la API key (cifrada) y/o el modelo de Google AI Studio. No devuelve la clave."""
    if req.key and req.key.strip():
        pasarela.save_keys_config(free_key=req.key)
    res: Dict[str, Any] = {"status": "saved", "configured": bool(pasarela.get_active_api_key())}
    if req.model and req.model.strip():
        pasarela.save_model(req.model)
        res["model"] = req.model.strip()
    return res


@router.post("/audio/gemini-test")
def test_gemini_api_connection(client: TutorDeVoz) -> Dict[str, Any]:
    """Prueba la conexión con el proveedor de IA activo de la cuenta, con su clave y su modelo."""
    return client.test_connection()


@router.post("/audio/gemini-evaluate", response_model=GeminiVoiceEvaluation)
def evaluate_with_gemini_tutor(data: GeminiEvaluationRequest, client: TutorDeVoz) -> GeminiVoiceEvaluation:
    """Evalúa dicción, entonación y estilo de consultoría con la IA de la cuenta o, sin ella, el motor local."""
    return client.evaluate(data)


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Texto en inglés a traducir")
    target_lang: str = Field("es", description="Idioma destino")


class TranslateResponse(BaseModel):
    original_text: str
    translated_text: str
    model_used: str
    provider_used: Optional[str] = None
    motivo_sin_ia: Optional[str] = None


@router.post("/translate", response_model=TranslateResponse)
def translate_technical_text(req: TranslateRequest, client: TutorDeVoz) -> TranslateResponse:
    """Traduce oraciones de contexto o colocaciones al español con la IA de la cuenta; sin ella devuelve el original."""
    traduccion = client.translate_to_spanish(req.text)
    return TranslateResponse(
        original_text=req.text,
        translated_text=traduccion.texto,
        model_used=traduccion.modelo,
        provider_used=traduccion.proveedor,
        motivo_sin_ia=traduccion.motivo_sin_ia,
    )



# --- EVALUACIÓN EVOLUTIVA & RECOMENDACIÓN ADAPTATIVA CON GEMINI ---
from aulento.fsrs.evolution_advisor import (
    get_student_evolution_metrics,
    diagnose_evolution,
    EvolutionDiagnosis,
)


@router.get("/evolution/status")
def get_evolution_status(usuario: Cuenta, conn: Conexion) -> Dict[str, Any]:
    """Retorna las métricas cuantitativas de dominio por nivel de la cuenta."""
    return get_student_evolution_metrics(conn, usuario.id)


@router.post("/evolution/diagnose", response_model=EvolutionDiagnosis)
def diagnose_student_evolution(usuario: Cuenta, conn: Conexion) -> EvolutionDiagnosis:
    """Ejecuta un diagnóstico evolutivo pedagógico de la cuenta con su IA o, sin ella, el heurístico local."""
    return diagnose_evolution(conn, usuario.id)


# --- NIVELES PROGRESIVOS & SIMULADOR DE CONSULTORÍA IA ---
from aulento.fsrs.consulting_sim import (
    ConsultingSimulator,
    ConsultingSubmission,
    ConsultingFeedback,
    ConsultingScenario,
)
from aulento.fsrs.progressive_deck import LEVEL_METADATA


@router.get("/levels")
def get_progressive_levels() -> Dict[str, Any]:
    """Retorna los metadatos y descriptores de los 5 niveles del programa progresivo."""
    return LEVEL_METADATA


@router.get("/consulting/scenarios", response_model=List[ConsultingScenario])
def get_consulting_scenarios():
    """Retorna la lista de escenarios de negocio para el simulador de consultoría en IA."""
    sim = ConsultingSimulator()
    return sim.list_scenarios()


@router.post("/consulting/evaluate", response_model=ConsultingFeedback)
def evaluate_consulting_submission(data: ConsultingSubmission):
    """Evalúa la formulación en inglés y la calidad estratégica de una respuesta de consultoría."""
    sim = ConsultingSimulator()
    try:
        return sim.evaluate(data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- HARVESTER OMNICANAL DE FLASHCARDS FSRS ---
from aulento.fsrs.cloud_harvest import (
    SIN_MATERIALES,
    SIN_TEMA,
    CosechaNoDisponibleError,
    RutaDeCosechaNoEncontradaError,
)
from aulento.fsrs.harvester import (
    OmniHarvester,
    HarvestCandidateCard,
)

ESTADO_POR_MOTIVO_DE_COSECHA = {SIN_TEMA: 400, SIN_MATERIALES: 404}
ORIGEN_MATERIALES = "materiales"


class HarvestPreviewRequest(BaseModel):
    source: str = Field("vault", description="Canal: 'vault', 'materiales' o 'ai'")
    topic: Optional[str] = Field(None, description="Término/tecnología para IA o tema a buscar en los materiales")
    level: str = Field("b2_tech_data_ai", description="Nivel objetivo FSRS: a1..c1")
    limit: int = Field(15, ge=1, le=50)
    material_id: Optional[int] = Field(None, ge=1, description="Materiales: cosechar de este material en vez de buscar por tema")
    roadmap_id: Optional[int] = Field(None, description="Materiales: ruta cuyo perfil pedagógico define el estilo y el mazo de las tarjetas")


class HarvestCommitRequest(BaseModel):
    cards: List[HarvestCandidateCard]


class HarvestCommitResponse(BaseModel):
    imported_count: int
    message: str


@router.post("/harvest/preview", response_model=List[HarvestCandidateCard])
def preview_harvest_cards(
    req: HarvestPreviewRequest,
    usuario: Cuenta,
    conn: Conexion,
    repo: RepoFsrs,
    pasarela: IADeLaCuenta,
) -> List[HarvestCandidateCard]:
    """Extrae candidatos a tarjetas desde el vault de la cuenta, sus materiales o IA y marca los duplicados de la cuenta.

    La cosecha desde los materiales exige IA: sin ella responde el error propio del caso (ver el manejador de errores de IA).
    """
    exigir_mazo(repo, req.level)
    harvester = OmniHarvester()
    source_lower = req.source.lower().strip()

    if source_lower == "vault":
        candidates = OmniHarvester(
            vault_de_la_cuenta(conn, usuario.id), carpetas_del_tutor(conn, usuario.id)
        ).harvest_from_vault(
            limit=req.limit, query=req.topic, pasarela=pasarela
        )
    elif source_lower == ORIGEN_MATERIALES:
        try:
            candidates = harvester.harvest_from_materials(
                usuario.id,
                query=req.topic or "",
                limit=req.limit,
                material_id=req.material_id,
                roadmap_id=req.roadmap_id,
                level=req.level,
            )
        except CosechaNoDisponibleError as e:
            raise HTTPException(status_code=ESTADO_POR_MOTIVO_DE_COSECHA.get(e.codigo, 400), detail=str(e))
        except RutaDeCosechaNoEncontradaError:
            raise no_encontrado("Ruta", req.roadmap_id) from None
    elif source_lower == "ai":
        default_topic_by_level = {
            "a1": "Workplace IT Communication",
            "a1_foundations": "Workplace IT Communication",
            "a2": "Daily Standups and Sprints",
            "a2_daily_work": "Daily Standups and Sprints",
            "b1": "Data Storytelling and Metrics",
            "b1_data_storytelling": "Data Storytelling and Metrics",
            "b2": "Cloud Architecture and Data Pipelines",
            "b2_tech_data_ai": "Cloud Architecture and Data Pipelines",
            "c1": "Executive AI Consulting and ROI",
            "c1_consulting_ai": "Executive AI Consulting and ROI",
        }
        topic = req.topic or default_topic_by_level.get(req.level, "Cloud Architecture and Data Pipelines")
        candidates = harvester.harvest_from_ai(
            topic=topic,
            level=req.level,
            count=req.limit,
            pasarela=pasarela,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Origen de cosecha '{req.source}' no válido. Use 'vault', 'materiales' o 'ai'.")

    return harvester.check_duplicates(conn, usuario.id, candidates)


@router.post("/harvest/commit", response_model=HarvestCommitResponse)
def commit_harvest_cards(
    req: HarvestCommitRequest,
    usuario: Cuenta,
    conn: Conexion,
) -> HarvestCommitResponse:
    """Persiste a nombre de la cuenta las tarjetas aprobadas descartando duplicados.

    Si alguna va al mazo de una ruta que no existe o es de otra cuenta responde 404 y no guarda ninguna.
    """
    harvester = OmniHarvester()
    try:
        count = harvester.commit_harvest(conn, usuario.id, req.cards)
    except MazoDeRutaNoEncontradoError as e:
        raise no_encontrado("Ruta", e.roadmap_id) from None
    return HarvestCommitResponse(
        imported_count=count,
        message=f"Se agregaron exitosamente {count} nuevas tarjetas al mazo FSRS v5.",
    )


@router.get("/export/anki")
def export_cards_to_anki(repo: RepoFsrs):
    """Exporta las tarjetas FSRS de la cuenta en formato TSV compatible directamente con Anki Desktop."""
    from fastapi.responses import Response

    cards = repo.list_cards()

    lines = ["#separator:tab", "#html:true", "#tags column:4"]
    for c in cards:
        front = c.item_pregunta.replace("\t", " ").replace("\n", "<br>")
        back = c.respuesta_esperada.replace("\t", " ").replace("\n", "<br>")
        context = (c.contexto_uso or "").replace("\t", " ").replace("\n", "<br>")
        tag = c.categoria
        lines.append(f"{front}\t{back}\t{context}\t{tag}")

    content = "\n".join(lines)
    return Response(
        content=content,
        media_type="text/tab-separated-values",
        headers={"Content-Disposition": "attachment; filename=aulento_anki_deck.tsv"},
    )


