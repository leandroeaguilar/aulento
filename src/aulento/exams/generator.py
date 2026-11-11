"""Generador de exámenes de Active Recall a partir de notas del Vault o materiales."""

import json
import random
import re
import uuid
from datetime import UTC, datetime

from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import FaltaClaveDeIA, Pedido
from aulento.exams.models import Exam, Question, QuestionType
from aulento.vault.models import VaultNote
from aulento.vault.reader import VaultReader

PALABRAS_IGNORAR = frozenset([
    "sobre", "tengo", "tiene", "temas", "tema", "para", "según", "segun", "explicame",
    "explícame", "explica", "como", "cómo", "cual", "cuál", "cuales", "cuáles", "entre",
    "desde", "este", "esta", "estos", "estas", "donde", "dónde", "cuando", "cuándo",
    "quiero", "necesito", "puedes", "podes", "hacer", "haber", "había", "habia", "hecho",
    "mucho", "muchos", "muchas", "mucha", "todos", "todas", "todo", "toda", "otro", "otra",
    "otros", "otras", "mismo", "misma", "mismos", "mismas", "tanto", "tanta", "están",
    "estan", "estaba", "siendo", "sería", "seria", "puede", "pueden", "deben", "deber",
    "porque", "aunque", "mientras", "contra", "hacia", "hasta", "durante", "mediante",
    "además", "ademas", "también", "tambien", "luego", "antes", "después", "despues",
    "primero", "segundo", "tercero", "parte", "partes", "punto", "puntos",
])


def _mezclar_opciones(opciones: list[str]) -> list[str]:
    mezcladas = list(opciones)
    random.shuffle(mezcladas)
    return mezcladas


def _limpiar_texto(texto: str) -> str:
    """Limpia bloques de código, encabezados y formato markdown pesado."""
    # Quitar bloques de código
    t = re.sub(r"```.*?```", "", texto, flags=re.DOTALL)
    # Quitar wikilinks [[nota|alias]] o [[nota]]
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", t)
    # Quitar encabezados markdown
    t = re.sub(r"^#+\s*.*$", "", t, flags=re.MULTILINE)
    # Normalizar espacios
    return re.sub(r"\s+", " ", t).strip()


def _extraer_oraciones(texto: str) -> list[str]:
    """Extrae oraciones candidatas del texto."""
    limpio = _limpiar_texto(texto)
    partes = re.split(r"(?<=[.!?])\s+", limpio)
    oraciones = []
    for p in partes:
        p_strip = p.strip()
        if 30 <= len(p_strip) <= 250:
            oraciones.append(p_strip)
    return oraciones


def _palabras_candidatas(oracion: str) -> list[str]:
    """Halla palabras relevantes para huecos en cloze."""
    palabras = re.findall(r"\b[A-Za-zÁÉÍÓÚáéíóúñÑ]{5,}\b", oracion)
    candidatas = [p for p in palabras if p.lower() not in PALABRAS_IGNORAR]
    return candidatas


class ExamGenerator:
    """Sintetiza preguntas de Active Recall (Opción Múltiple, Cloze y Razonamiento Abierto)."""

    def __init__(self, vault_reader: VaultReader, ia: PasarelaDeIA | None = None):
        self.vault_reader = vault_reader
        self.ia = ia

    def generate_exam_for_note(
        self,
        note: VaultNote,
        question_types: list[QuestionType] | None = None,
        count: int = 3,
    ) -> Exam:
        """Genera un examen completo para una nota específica del vault."""
        return self.generate_exam(
            title=note.title,
            content=note.content,
            origin_id=note.id,
            question_types=question_types,
            count=count,
            source_reference=note.path,
        )

    def generate_exam(
        self,
        title: str,
        content: str,
        origin_id: str,
        question_types: list[QuestionType] | None = None,
        count: int = 3,
        source_reference: str | None = None,
    ) -> Exam:
        """Genera un examen activo a partir de cualquier texto (nota de vault o material subido).

        `source_reference` nombra de dónde sale el texto (la ruta de la nota relativa al vault o el nombre del
        material); cada pregunta lo lleva, y el pasaje exacto va aparte en `fragmento`.
        """
        referencia = source_reference or title
        types_to_use = question_types or [
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.CLOZE,
            QuestionType.OPEN_REASONING,
        ]

        if self.ia is not None:
            try:
                return self._generar_con_ia_con_reintento(title, content, origin_id, types_to_use, count, referencia)
            except FaltaClaveDeIA:
                return self._generar_sin_ia(title, content, origin_id, types_to_use, count, referencia, aviso=None)
            except Exception:  # noqa: BLE001
                aviso = "La IA no devolvió el formato esperado o no estuvo disponible; se generó el examen en modo sin IA."
                return self._generar_sin_ia(title, content, origin_id, types_to_use, count, referencia, aviso=aviso)

        return self._generar_sin_ia(title, content, origin_id, types_to_use, count, referencia, aviso=None)

    def _generar_con_ia_con_reintento(
        self,
        title: str,
        content: str,
        origin_id: str,
        question_types: list[QuestionType],
        count: int,
        referencia: str,
    ) -> Exam:
        """Intenta generar con la IA de la cuenta con reintento único si el formato es inválido."""
        tipos_nombres = [t.value for t in question_types]
        prompt_usuario = (
            f"Generá un examen de Active Recall de {count} preguntas sobre el siguiente texto de estudio titulado '{title}'.\n\n"
            f"Texto de estudio:\n\"\"\"\n{content[:8000]}\n\"\"\"\n\n"
            f"Tipos de pregunta solicitados: {', '.join(tipos_nombres)}.\n"
            "Requisitos estrictos:\n"
            "1. Cada pregunta DEBE basarse exclusivamente en el texto provisto.\n"
            "2. En 'fragmento', copiá la cita o pasaje textual exacto del texto de estudio del que surge la pregunta.\n"
            "3. En 'explanation', explicá el fundamento pedagógico de la respuesta correcta.\n"
            "4. Para 'multiple_choice', incluí 4 opciones (1 correcta y 3 distractores plausibles extraídos del contexto).\n"
            "5. Para 'open_reasoning' o 'cloze', 'options' debe ser una lista vacía.\n\n"
            "Respondé ÚNICAMENTE con un JSON válido con este esquema:\n"
            "{\n"
            '  "questions": [\n'
            "    {\n"
            '      "topic": "subtema o concepto específico",\n'
            '      "question_type": "multiple_choice" o "open_reasoning" o "cloze",\n'
            '      "prompt": "enunciado de la pregunta",\n'
            '      "options": ["opcion1", "opcion2", "opcion3", "opcion4"],\n'
            '      "correct_answer": "respuesta correcta esperada",\n'
            '      "explanation": "explicación justificada",\n'
            '      "fragmento": "cita textual exacta del texto"\n'
            "    }\n"
            "  ]\n"
            "}"
        )
        sistema = "Sos un evaluador pedagógico experto. Generás preguntas de Active Recall basadas estrictamente en textos reales de estudio en formato JSON."
        pedido = Pedido(usuario=prompt_usuario, sistema=sistema, json=True)

        ultimo_error: Exception | None = None
        for _ in range(2):
            try:
                res = self.ia.generar(pedido, endpoint_tipo="exam_generator")
                data = json.loads(res.texto)
                if not isinstance(data, dict) or "questions" not in data or not isinstance(data["questions"], list):
                    raise ValueError("El JSON generado no contiene la lista 'questions'.")

                questions: list[Question] = []
                for idx, raw_q in enumerate(data["questions"][:count]):
                    q_type_str = raw_q.get("question_type", "multiple_choice")
                    try:
                        q_type = QuestionType(q_type_str)
                    except ValueError:
                        q_type = QuestionType.MULTIPLE_CHOICE

                    fragmento = raw_q.get("fragmento") or raw_q.get("source_reference") or title
                    explanation = raw_q.get("explanation") or f"Fundamento según el texto '{title}'."
                    options = raw_q.get("options") or []
                    if q_type == QuestionType.MULTIPLE_CHOICE and len(options) < 2:
                        options = [raw_q.get("correct_answer", ""), "Opción distractora A", "Opción distractora B", "Opción distractora C"]

                    questions.append(
                        Question(
                            id=f"{origin_id}-q{idx + 1}",
                            note_id=origin_id,
                            topic=raw_q.get("topic") or title,
                            question_type=q_type,
                            prompt=raw_q.get("prompt") or f"Pregunta sobre {title}",
                            options=options,
                            correct_answer=raw_q.get("correct_answer") or "",
                            explanation=explanation,
                            source_reference=referencia,
                            fragmento=fragmento,
                        )
                    )

                if questions:
                    exam_id = f"exam-{uuid.uuid4().hex[:8]}"
                    return Exam(
                        id=exam_id,
                        title=f"Examen de Active Recall: {title}",
                        topic=title,
                        created_at=datetime.now(UTC).isoformat(),
                        questions=questions,
                        total_questions=len(questions),
                        sin_ia=False,
                        rotulo=None,
                        aviso=None,
                    )
            except FaltaClaveDeIA:
                raise
            except Exception as e:  # noqa: BLE001
                ultimo_error = e

        raise ultimo_error or RuntimeError("No se pudo generar examen con IA.")

    def _generar_sin_ia(
        self,
        title: str,
        content: str,
        origin_id: str,
        question_types: list[QuestionType],
        count: int,
        referencia: str,
        aviso: str | None = None,
    ) -> Exam:
        """Genera examen básico a partir de oraciones del texto (completar la palabra que falta) rotulado 'sin IA'."""
        oraciones = _extraer_oraciones(content)
        if not oraciones:
            # Fallback a líneas si no hubo oraciones con puntuación
            oraciones = [line.strip() for line in content.splitlines() if len(line.strip()) >= 25]
        if not oraciones:
            oraciones = [f"Contenido del documento {title}."]

        # Extraer palabras del texto para posibles distractores
        todas_las_palabras = list({p for orac in oraciones for p in _palabras_candidatas(orac)})

        questions: list[Question] = []
        q_idx = 0

        while len(questions) < count and q_idx < len(oraciones) * 2:
            current_oracion = oraciones[q_idx % len(oraciones)]
            candidatas = _palabras_candidatas(current_oracion)
            target_type = question_types[len(questions) % len(question_types)]

            if candidatas:
                # Elegir la palabra más larga o significativa
                candidatas_ordenadas = sorted(candidatas, key=len, reverse=True)
                palabra = candidatas_ordenadas[0]
                patron = re.compile(rf"\b{re.escape(palabra)}\b", flags=re.IGNORECASE)
                prompt_cloze = patron.sub("[_______]", current_oracion, count=1)
                num = len(questions) + 1
                q_id = f"{origin_id}-q{num}"

                if target_type == QuestionType.MULTIPLE_CHOICE:
                    distractores = [p for p in todas_las_palabras if p.lower() != palabra.lower()]
                    distractores_muestra = random.sample(distractores, min(3, len(distractores)))
                    while len(distractores_muestra) < 3:
                        distractores_muestra.append(f"Término-{len(distractores_muestra) + 1}")
                    opciones = _mezclar_opciones([palabra] + distractores_muestra)

                    questions.append(
                        Question(
                            id=q_id,
                            note_id=origin_id,
                            topic=title,
                            question_type=QuestionType.MULTIPLE_CHOICE,
                            prompt=f"Completa la palabra que falta en la siguiente afirmación del texto: «{prompt_cloze}»",
                            options=opciones,
                            correct_answer=palabra,
                            explanation=f"Frase textual del material de estudio: «{current_oracion}»",
                            source_reference=referencia,
                            fragmento=current_oracion,
                        )
                    )
                elif target_type == QuestionType.OPEN_REASONING:
                    questions.append(
                        Question(
                            id=q_id,
                            note_id=origin_id,
                            topic=title,
                            question_type=QuestionType.OPEN_REASONING,
                            prompt=f"A partir del texto sobre '{title}', explica el significado y contexto del siguiente pasaje: «{current_oracion}»",
                            options=[],
                            correct_answer=current_oracion,
                            explanation=f"Fundamento extraído del texto original: «{current_oracion}»",
                            source_reference=referencia,
                            fragmento=current_oracion,
                        )
                    )
                else:  # CLOZE
                    questions.append(
                        Question(
                            id=q_id,
                            note_id=origin_id,
                            topic=title,
                            question_type=QuestionType.CLOZE,
                            prompt=f"Completa la palabra que falta según el texto: «{prompt_cloze}»",
                            options=[],
                            correct_answer=palabra,
                            explanation=f"Frase textual del material de estudio: «{current_oracion}»",
                            source_reference=referencia,
                            fragmento=current_oracion,
                        )
                    )

            q_idx += 1

        # Si aún no llegamos a count, rellenar con lo que haya
        if not questions:
            num = 1
            questions.append(
                Question(
                    id=f"{origin_id}-q{num}",
                    note_id=origin_id,
                    topic=title,
                    question_type=QuestionType.CLOZE,
                    prompt=f"En relación a {title}, completa el concepto fundamental: [_______]",
                    options=[],
                    correct_answer=title,
                    explanation=f"Concepto extraído del documento {title}.",
                    source_reference=referencia,
                    fragmento=title,
                )
            )

        exam_id = f"exam-{uuid.uuid4().hex[:8]}"
        return Exam(
            id=exam_id,
            title=f"Examen de Active Recall: {title}",
            topic=title,
            created_at=datetime.now(UTC).isoformat(),
            questions=questions,
            total_questions=len(questions),
            sin_ia=True,
            rotulo="sin IA",
            aviso=aviso,
        )
