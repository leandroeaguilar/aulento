"""Router FastAPI para generación de exámenes Active Recall y evaluación Feynman."""

import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from aulento.core.ia.tipos import FaltaClaveDeIA, IANoDisponibleError, Pedido
from aulento.core.materiales import MaterialNoEncontrado
from aulento.exams.feynman import FeynmanEvaluator, ejemplos_feynman
from aulento.exams.generator import ExamGenerator
from aulento.exams.models import (
    Exam,
    FeynmanEvaluation,
    FeynmanExample,
    FeynmanSubmission,
    OpenAnswerEvaluation,
    QuestionType,
)
from aulento.vault.rutas import MENSAJE_NOTA_NO_ENCONTRADA
from aulento.web.dependencies import IADeLaCuenta, LectorDelVault, Materiales

router = APIRouter(prefix="/api/exams", tags=["Exams"])


class GenerateExamRequest(BaseModel):
    note_id: str | None = Field(None, description="ID o título de la nota del Vault")
    material_id: int | None = Field(None, description="ID del material subido por la cuenta")
    question_type: str | None = Field("all", description="Tipo: multiple_choice, cloze, open_reasoning o all")
    count: int | None = Field(3, ge=1, le=10, description="Cantidad de preguntas a generar")


class EvaluateAnswerRequest(BaseModel):
    note_id: str | None = Field(None, description="ID o título de la nota del Vault")
    material_id: int | None = Field(None, description="ID del material subido")
    question_prompt: str = Field(..., description="Enunciado de la pregunta abierta")
    user_answer: str = Field(..., description="Respuesta dada por el estudiante")
    expected_answer: str | None = Field(None, description="Respuesta esperada o de referencia")


_ID_DE_MATERIAL = re.compile(r"material[:-](\d+)")


def _material(materiales: Materiales, material_id: int) -> tuple[str, str, str, str]:
    try:
        mat = materiales.obtener(material_id, con_texto=True)
    except MaterialNoEncontrado:
        raise HTTPException(status_code=404, detail="Material no encontrado.") from None
    return mat["nombre"], mat["texto"], f"material:{mat['id']}", mat["nombre"]


def _obtener_contenido_origen(
    note_id: str | None,
    material_id: int | None,
    reader: LectorDelVault,
    materiales: Materiales,
) -> tuple[str, str, str, str]:
    """(titulo, contenido, origin_id, referencia) de una nota del vault o de un material de la cuenta.

    El `origin_id` de un material es `material:<id>`, y el `note_id` acepta esa forma (y la vieja
    `material-<id>`) para que la pregunta de un examen vuelva a su material al evaluarla. La referencia es la
    ruta de la nota relativa al vault o el nombre del material: nunca una ruta del servidor.
    """
    if material_id is not None:
        return _material(materiales, material_id)

    if note_id:
        es_material = _ID_DE_MATERIAL.fullmatch(note_id.strip())
        if es_material:
            return _material(materiales, int(es_material.group(1)))

        note = reader.get_note(note_id)
        if not note:
            matched = reader.search_notes(note_id)
            if matched:
                note = matched[0]
            else:
                raise HTTPException(status_code=404, detail=MENSAJE_NOTA_NO_ENCONTRADA)
        return note.title, note.content, note.id, note.path

    raise HTTPException(status_code=400, detail="Debe indicar note_id o material_id.")


@router.post("/generate", response_model=Exam)
def generate_exam(
    req: GenerateExamRequest,
    reader: LectorDelVault,
    ia: IADeLaCuenta,
    materiales: Materiales,
):
    """Genera un examen adaptativo de Active Recall para una nota o material de la cuenta.

    Con clave de IA genera preguntas pedagógicas basadas en el texto; sin clave genera preguntas del propio texto rotuladas 'sin IA'.
    """
    title, content, origin_id, referencia = _obtener_contenido_origen(req.note_id, req.material_id, reader, materiales)

    types_map = {
        "multiple_choice": [QuestionType.MULTIPLE_CHOICE],
        "cloze": [QuestionType.CLOZE],
        "open": [QuestionType.OPEN_REASONING],
        "open_reasoning": [QuestionType.OPEN_REASONING],
        "all": [QuestionType.MULTIPLE_CHOICE, QuestionType.CLOZE, QuestionType.OPEN_REASONING],
    }

    selected_types = types_map.get((req.question_type or "all").lower(), types_map["all"])

    generator = ExamGenerator(reader, ia=ia)
    exam = generator.generate_exam(
        title=title,
        content=content,
        origin_id=origin_id,
        question_types=selected_types,
        count=req.count or 3,
        source_reference=referencia,
    )
    return exam


@router.post("/evaluate-answer", response_model=OpenAnswerEvaluation)
def evaluate_open_answer(
    req: EvaluateAnswerRequest,
    reader: LectorDelVault,
    ia: IADeLaCuenta,
    materiales: Materiales,
):
    """Evalúa la respuesta de una pregunta abierta contra el texto de la nota o material con la IA de la cuenta."""
    title, content, _, _ = _obtener_contenido_origen(req.note_id, req.material_id, reader, materiales)

    # Evaluación con IA
    prompt_usuario = (
        f"Evalúa la respuesta de un estudiante a una pregunta abierta de Active Recall sobre el texto '{title}'.\n\n"
        f"Texto de estudio de referencia:\n\"\"\"\n{content[:6000]}\n\"\"\"\n\n"
        f"Pregunta formulada: {req.question_prompt}\n"
        f"Respuesta esperada de referencia: {req.expected_answer or '(No especificada, deducir del texto)'}\n"
        f"Respuesta del estudiante: \"\"\"\n{req.user_answer.strip()}\n\"\"\"\n\n"
        "Debes responder en formato JSON estricto indicando:\n"
        "1. is_correct (bool): true si la respuesta demuestra comprensión conceptual correcta y suficiente; false si es errónea o incompleta.\n"
        "2. score (int de 0 a 100): calificación cuantitativa según la precisión.\n"
        "3. feedback (str): justificación pedagógica explicando por qué es correcta o qué falló.\n"
        "4. what_was_missing (str o null): qué aspectos o detalles clave faltaron en la respuesta del estudiante.\n\n"
        "JSON de respuesta:\n"
        "{\n"
        '  "is_correct": true,\n'
        '  "score": 85,\n'
        '  "feedback": "...",\n'
        '  "what_was_missing": "..."\n'
        "}"
    )
    sistema = "Sos un evaluador pedagógico experto. Calificás respuestas abiertas con rigor conceptual según el texto de estudio."
    pedido = Pedido(usuario=prompt_usuario, sistema=sistema, json=True)

    for _ in range(2):
        try:
            res = ia.generar(pedido, endpoint_tipo="exam_evaluate_answer")
        except FaltaClaveDeIA:
            return _evaluar_respuesta_sin_ia(req.user_answer, req.expected_answer, content)
        except IANoDisponibleError:
            break
        try:
            return _evaluacion_abierta_de_la_ia(json.loads(res.texto))
        except ValueError:  # JSON roto o esquema que no cumple: se reintenta una vez
            continue
    return _evaluar_respuesta_sin_ia(
        req.user_answer,
        req.expected_answer,
        content,
        aviso="La IA no devolvió el formato esperado o no estuvo disponible; se evaluó en modo sin IA.",
    )


def _evaluacion_abierta_de_la_ia(data: object) -> OpenAnswerEvaluation:
    """La evaluación de la IA validada: `is_correct` booleano, `score` de 0 a 100 y `feedback`; si no, `ValueError`."""
    if not isinstance(data, dict) or not isinstance(data.get("is_correct"), bool) or not data.get("feedback"):
        raise ValueError("Respuesta de IA sin campos requeridos.")
    try:
        return OpenAnswerEvaluation.model_validate(
            {
                "is_correct": data["is_correct"],
                "score": data.get("score"),
                "feedback": data["feedback"],
                "what_was_missing": data.get("what_was_missing"),
                "sin_ia": False,
            }
        )
    except ValidationError as error:
        raise ValueError("La evaluación de la IA no cumple el esquema.") from error


def _evaluar_respuesta_sin_ia(
    user_answer: str,
    expected_answer: str | None,
    content: str,
    aviso: str | None = None,
) -> OpenAnswerEvaluation:
    """Evaluación heurística básica de respuesta abierta cuando no hay IA."""
    ans = user_answer.strip()
    if len(ans) < 15:
        return OpenAnswerEvaluation(
            is_correct=False,
            score=20,
            feedback="La respuesta es demasiado breve para fundamentar el razonamiento del concepto.",
            what_was_missing="Desarrollar la explicación con las ideas y términos del texto de estudio.",
            sin_ia=True,
            rotulo="sin IA",
            aviso=aviso,
        )

    ans_words = set(re.findall(r"\b[A-Za-zÁÉÍÓÚáéíóúñÑ]{4,}\b", ans.lower()))
    ref_text = f"{expected_answer or ''} {content[:1000]}".lower()
    ref_words = set(re.findall(r"\b[A-Za-zÁÉÍÓÚáéíóúñÑ]{5,}\b", ref_text))

    coincidencias = ans_words.intersection(ref_words)
    if len(coincidencias) >= 2:
        return OpenAnswerEvaluation(
            is_correct=True,
            score=75,
            feedback=f"Respuesta conceptualmente alineada con los términos clave ({', '.join(list(coincidencias)[:3])}).",
            what_was_missing=None,
            sin_ia=True,
            rotulo="sin IA",
            aviso=aviso,
        )

    return OpenAnswerEvaluation(
        is_correct=False,
        score=40,
        feedback="La respuesta no menciona suficientes términos o fundamentos presentes en el texto de estudio.",
        what_was_missing="Se omitieron conceptos clave del texto de estudio.",
        sin_ia=True,
        rotulo="sin IA",
        aviso=aviso,
    )


@router.post("/evaluate-feynman", response_model=FeynmanEvaluation)
def evaluate_feynman(submission: FeynmanSubmission, reader: LectorDelVault, ia: IADeLaCuenta):
    """Evalúa una explicación según la Técnica Feynman, contrastándola con las notas del vault de la cuenta."""
    evaluator = FeynmanEvaluator(reader, ia=ia)
    result = evaluator.evaluate(submission)
    return result


@router.get("/feynman-examples", response_model=list[FeynmanExample])
def get_feynman_examples(reader: LectorDelVault):
    """Retorna ejemplos rápidos para el Simulador Feynman tomados de las notas del vault de la cuenta, o genéricos."""
    return ejemplos_feynman(reader)
