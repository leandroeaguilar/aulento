"""Evaluador pedagógico basado en la Técnica Feynman (explicación simple y detección de lagunas)."""

import json
import re
from typing import Any

from pydantic import ValidationError

from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import FaltaClaveDeIA, IANoDisponibleError, Pedido
from aulento.exams.models import (
    FeynmanCriterio,
    FeynmanEvaluation,
    FeynmanExample,
    FeynmanSubmission,
)
from aulento.vault.models import VaultNote
from aulento.vault.reader import VaultReader
from aulento.vault.rutas import RutaFueraDelVaultError

COMMON_JARGON = [
    "paradigma", "holístico", "sinergia", "heurística", "polimorfismo",
    "idempotencia", "desnormalización", "vectorial", "estocástico",
    "computación serverless", "abstracción", "shuffling", "hiperparámetro"
]

CRITERIOS_FEYNMAN = ("precision", "simplicidad", "jerga", "analogia", "huecos")

QUE_MIDE_SIN_IA = (
    "Evaluación básica rotulada 'sin IA': mide el largo de las frases, cuántos términos clave de la nota usás "
    "y qué palabras técnicas de la nota usás sin explicarlas. No juzga si la explicación es correcta: para eso "
    "hace falta una clave de IA."
)

AVISO_IA_FALLIDA = (
    "La IA no devolvió el formato esperado o no estuvo disponible; se ofrece la evaluación básica sin IA."
)

# Lo que suele seguir a un término cuando quien explica lo aclara
_ACLARACION = re.compile(
    r"^\W{0,3}(\(|:|—|-|,?\s*(es decir|o sea|que es|que son|significa|quiere decir|se refiere|"
    r"es como|son como|es una?|son)\b)",
    re.IGNORECASE,
)

_PALABRAS_COMUNES = frozenset({
    "también", "tambien", "siempre", "entonces", "mientras", "nuestro", "nuestra", "cualquier", "ejemplo",
    "través", "traves", "diferencia", "general", "importante", "información", "informacion", "personas",
    "solamente", "manera", "momento", "realmente", "aunque", "después", "despues", "durante", "tenemos",
    "sistema", "sistemas", "permite", "pueden", "cuando", "dentro", "contra", "porque", "además", "ademas",
})

ANALOGY_MARKERS = [
    "como un", "como una", "imagina", "es como", "similar a",
    "por ejemplo", "en la vida real", "piensa en", "como si fuera"
]

EJEMPLOS_GENERICOS = [
    FeynmanExample(
        concept="Fotosíntesis",
        explanation="Las plantas usan la luz del sol, agua y aire para fabricar su propio alimento y liberar oxígeno.",
    ),
    FeynmanExample(
        concept="Gravedad",
        explanation="Es la fuerza invisible que atrae a los objetos entre sí, como la Tierra que nos mantiene en el suelo.",
    ),
    FeynmanExample(
        concept="Búsqueda binaria",
        explanation="Es buscar una palabra en un diccionario abriéndolo siempre al medio y descartando la mitad donde seguro no está.",
    ),
]


def ejemplos_feynman(reader: VaultReader | None = None) -> list[FeynmanExample]:
    """Retorna ejemplos rápidos tomados de las notas del vault de la cuenta, o genéricos si no hay notas."""
    if reader is not None:
        try:
            notas = reader.list_notes()
            if notas:
                return [
                    FeynmanExample(
                        concept=n.title,
                        explanation=f"Explica con tus propias palabras y una analogía sencilla qué es y cómo funciona {n.title}.",
                    )
                    for n in notas[:3]
                ]
        except (RutaFueraDelVaultError, OSError):
            pass
    return list(EJEMPLOS_GENERICOS)


class FeynmanEvaluator:
    """Evalúa explicaciones de conceptos según los principios de la Técnica Feynman.

    Contrasta la explicación con la nota del concepto en el vault que lee `vault_reader`: el de la cuenta que evalúa.
    """

    def __init__(self, vault_reader: VaultReader, ia: PasarelaDeIA | None = None):
        self.vault_reader = vault_reader
        self.ia = ia

    def _nota_de_referencia(self, submission: FeynmanSubmission) -> VaultNote | None:
        concept = submission.concept.strip()
        try:
            note = self.vault_reader.get_note(submission.note_id or concept)
            if note is None:
                matched = self.vault_reader.search_notes(concept)
                note = matched[0] if matched else None
        except (RutaFueraDelVaultError, ValueError, OSError):
            note = None
        return note

    def evaluate(self, submission: FeynmanSubmission) -> FeynmanEvaluation:
        """Analiza la explicación del usuario y retorna un reporte diagnóstico estructurado.

        Con IA, una respuesta que no respete el formato (o un proveedor que falle) cae a la evaluación básica
        rotulada «sin IA», con un aviso: nunca se presenta como evaluación de la IA.
        """
        note = self._nota_de_referencia(submission)

        if self.ia is not None:
            try:
                return self._evaluar_con_ia_con_reintento(submission, note)
            except FaltaClaveDeIA:
                return self._evaluar_sin_ia(submission, note, aviso=None)
            except (IANoDisponibleError, ValueError):
                return self._evaluar_sin_ia(submission, note, aviso=AVISO_IA_FALLIDA)

        return self._evaluar_sin_ia(submission, note, aviso=None)

    def _evaluar_con_ia_con_reintento(
        self,
        submission: FeynmanSubmission,
        note: VaultNote | None,
    ) -> FeynmanEvaluation:
        """Evalúa con la pasarela de IA de la cuenta validando los cinco criterios Feynman.

        Levanta `ValueError` si las dos respuestas no cumplen el esquema.
        """
        concept = submission.concept.strip()
        explanation = submission.explanation.strip()
        audience = submission.target_audience or "principiante"
        note_content = note.content[:6000] if note else "(No se encontró nota específica en el vault; evaluá según el concepto)"

        prompt_usuario = (
            f"Evalúa la siguiente explicación de un estudiante sobre el concepto '{concept}' usando los principios de la Técnica Feynman.\n"
            f"Público objetivo: {audience}.\n\n"
            f"Texto de referencia de la nota de estudio:\n\"\"\"\n{note_content}\n\"\"\"\n\n"
            f"Explicación enviada por el estudiante:\n\"\"\"\n{explanation}\n\"\"\"\n\n"
            "Debes evaluar rigurosamente los siguientes CINCO criterios, asignando un puntaje (0 a 100) y justificación a cada uno:\n"
            "1. precision: Exactitud técnica según la nota de referencia y el concepto.\n"
            "2. simplicidad: Lenguaje claro, accesible y comprensible para el público objetivo, sin jerga innecesaria.\n"
            "3. jerga: Detección de tecnicismos o jergas usados sin explicarlos. Incluye la lista 'tecnicismos'.\n"
            "4. analogia: Uso efectivo de analogías cotidianas, metáforas o ejemplos intuitivos de la vida real.\n"
            "5. huecos: Aspectos centrales o lagunas conceptuales omitidas en la explicación. Incluye la lista 'lagunas'.\n\n"
            "Respondé ÚNICAMENTE con un objeto JSON con este esquema exacto:\n"
            "{\n"
            '  "score": 85,\n'
            '  "mastery_level": "Principiante" o "Intermedio" o "Avanzado" o "Feynman Master",\n'
            '  "clarity_score": 90,\n'
            '  "precision_score": 80,\n'
            '  "jargon_used": ["tecnicismo1", "tecnicismo2"],\n'
            '  "knowledge_gaps": ["aspecto omitido 1", "aspecto omitido 2"],\n'
            '  "strengths": ["punto fuerte 1", "punto fuerte 2"],\n'
            '  "feedback_summary": "veredicto pedagógico constructivo general",\n'
            '  "suggested_simplification": "ejemplo de analogía o simplificación cotidiana recomendada",\n'
            '  "criterios": {\n'
            '    "precision": {"puntaje": 80, "justificacion": "..."},\n'
            '    "simplicidad": {"puntaje": 90, "justificacion": "..."},\n'
            '    "jerga": {"puntaje": 85, "justificacion": "...", "tecnicismos": [...]},\n'
            '    "analogia": {"puntaje": 95, "justificacion": "..."},\n'
            '    "huecos": {"puntaje": 75, "justificacion": "...", "lagunas": [...]}\n'
            "  }\n"
            "}"
        )
        sistema = "Sos un evaluador pedagógico experto en la Técnica Feynman. Calificás explicaciones con precisión, detectás analogías, tecnicismos y lagunas."
        pedido = Pedido(usuario=prompt_usuario, sistema=sistema, json=True)

        ultimo_error: ValueError | None = None
        for _ in range(2):
            res = self.ia.generar(pedido, endpoint_tipo="feynman")
            try:
                return _evaluacion_de_la_ia(concept, json.loads(res.texto))
            except ValueError as error:  # JSON roto o esquema que no cumple
                ultimo_error = error

        raise ultimo_error or ValueError("No se pudo evaluar Feynman con IA.")

    def _evaluar_sin_ia(
        self,
        submission: FeynmanSubmission,
        note: VaultNote | None,
        aviso: str | None = None,
    ) -> FeynmanEvaluation:
        """Evaluación básica rotulada 'sin IA': largo de frases, términos de la nota usados y usados sin explicar.

        No puede juzgar si la explicación es correcta, así que su puntaje tiene techo: sin nota para contrastar no
        pasa de 45, y con nota solo sube si la explicación usa los términos clave de la nota.
        """
        text = submission.explanation.strip()
        concept = submission.concept.strip()

        if len(text) < 15:
            return FeynmanEvaluation(
                concept=concept,
                score=15,
                mastery_level="Principiante",
                clarity_score=20,
                precision_score=10,
                jargon_used=[],
                knowledge_gaps=["La explicación es demasiado breve para evaluar la comprensión real."],
                strengths=[],
                feedback_summary=(
                    "Evaluación básica sin IA: tu explicación es demasiado corta. La técnica Feynman requiere "
                    "desarrollar la idea con tus propias palabras."
                ),
                suggested_simplification=f"Intenta explicar qué es {concept}, qué problema resuelve y cómo funciona con un ejemplo de la vida real.",
                criterios={
                    "precision": {"puntaje": 10, "justificacion": "Texto insuficiente para contrastar con la nota."},
                    "simplicidad": {"puntaje": 20, "justificacion": "Menos de 15 caracteres."},
                    "jerga": {"puntaje": 50, "justificacion": "Sin vocabulario suficiente para medir tecnicismos.", "tecnicismos": []},
                    "analogia": {"puntaje": 10, "justificacion": "No contiene analogía."},
                    "huecos": {"puntaje": 10, "justificacion": "Falta todo el contenido conceptual.", "lagunas": ["Explicación incompleta"]},
                },
                sin_ia=True,
                rotulo="sin IA",
                que_mide=QUE_MIDE_SIN_IA,
                aviso=aviso,
            )

        text_lower = text.casefold()
        strengths: list[str] = []
        gaps: list[str] = []
        lagunas: list[str] = []  # solo huecos de contenido: términos clave de la nota que no aparecen

        # 1. Largo de las frases
        oraciones = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        palabras_por_oracion = len(text.split()) / max(1, len(oraciones))
        if palabras_por_oracion <= 15:
            simplicidad = 90
            strengths.append("Frases cortas y fáciles de seguir.")
        elif palabras_por_oracion <= 22:
            simplicidad = 75
            strengths.append("Frases de largo razonable.")
        elif palabras_por_oracion <= 30:
            simplicidad = 55
            gaps.append("Algunas frases son largas; convendría dividirlas.")
        else:
            simplicidad = 35
            gaps.append("Frases muy largas; dividilas en oraciones más cortas.")

        # 2. Términos clave de la nota: cuáles usa y cuáles usa sin explicar
        terminos = _terminos_clave(note)
        usados = [t for t in terminos if t in text_lower]
        sin_explicar = [t for t in usados if not _esta_explicado(text_lower, t)]
        sin_explicar += [
            j for j in COMMON_JARGON if j in text_lower and j not in sin_explicar and not _esta_explicado(text_lower, j)
        ]
        jerga = max(10, 100 - 20 * len(sin_explicar))
        if sin_explicar:
            gaps.append(f"Usás palabras técnicas sin explicarlas: {', '.join(sin_explicar[:5])}.")
        elif usados:
            strengths.append("Los términos técnicos que usás quedan explicados.")

        if note is not None and terminos:
            cobertura = min(1.0, len(usados) / min(len(terminos), 5))
            precision = round(cobertura * 100)
            if usados:
                strengths.append(f"Usás términos clave de la nota ({', '.join(usados[:3])}).")
            faltan = [t for t in terminos[:5] if t not in usados]
            if faltan and cobertura < 1:
                lagunas.append(f"No aparecen términos clave de la nota: {', '.join(faltan[:3])}.")
            justificacion_precision = (
                f"Medición sin IA: usás {len(usados)} de los términos clave de la nota «{note.title}». "
                "No verifica que la explicación sea correcta."
            )
        else:
            cobertura = 0.0
            precision = 0
            if note is None:
                justificacion_precision = "No se encontró una nota para contrastar: sin IA no se puede medir la precisión."
            else:
                justificacion_precision = (
                    f"La nota «{note.title}» no tiene términos para comparar: sin IA no se puede medir la precisión."
                )
            gaps.append(justificacion_precision)

        # 3. Analogía: solo se detecta un marcador, no se juzga si la analogía es buena
        tiene_analogia = any(marker in text_lower for marker in ANALOGY_MARKERS)
        analogia = 60 if tiene_analogia else 30
        if tiene_analogia:
            strengths.append("Aparece una comparación o ejemplo («es como», «por ejemplo»...).")
        else:
            gaps.append("No aparece una comparación o ejemplo de la vida real.")

        bruto = 0.35 * simplicidad + 0.25 * jerga + 0.30 * precision + 0.10 * analogia
        techo = 45 + cobertura * 35
        final_score = int(min(bruto, techo))

        if final_score >= 75:
            mastery = "Avanzado"
        elif final_score >= 50:
            mastery = "Intermedio"
        else:
            mastery = "Principiante"

        criterios: dict[str, Any] = {
            "precision": {"puntaje": precision, "justificacion": justificacion_precision},
            "simplicidad": {
                "puntaje": simplicidad,
                "justificacion": f"Medición sin IA: promedio de {palabras_por_oracion:.1f} palabras por frase.",
            },
            "jerga": {
                "puntaje": jerga,
                "justificacion": f"Medición sin IA: {len(sin_explicar)} palabras técnicas usadas sin explicar.",
                "tecnicismos": sin_explicar,
            },
            "analogia": {
                "puntaje": analogia,
                "justificacion": (
                    "Medición sin IA: se detectó un marcador de comparación; no se juzga si la analogía es acertada."
                    if tiene_analogia
                    else "Medición sin IA: no se detectaron marcadores de comparación."
                ),
            },
            "huecos": {
                "puntaje": round(cobertura * 100),
                "justificacion": "Medición sin IA: términos clave de la nota que no aparecen en la explicación.",
                "lagunas": lagunas,
            },
        }

        return FeynmanEvaluation(
            concept=concept,
            score=final_score,
            mastery_level=mastery,
            clarity_score=simplicidad,
            precision_score=precision,
            jargon_used=sin_explicar,
            knowledge_gaps=lagunas + gaps,
            strengths=strengths,
            feedback_summary=f"Evaluación básica sin IA ({final_score}/100). {QUE_MIDE_SIN_IA}",
            suggested_simplification=(
                f"Explicá {concept} con frases cortas, aclarando cada término técnico con una comparación cotidiana."
            ),
            criterios=criterios,
            sin_ia=True,
            rotulo="sin IA",
            que_mide=QUE_MIDE_SIN_IA,
            aviso=aviso,
        )


def _evaluacion_de_la_ia(concept: str, data: Any) -> FeynmanEvaluation:
    """La evaluación que devolvió la IA, validada: los cinco criterios con puntaje en rango y justificación.

    Levanta `ValueError` si no cumple.
    """
    if not isinstance(data, dict):
        raise ValueError("La IA no devolvió un objeto JSON.")  # noqa: TRY004 - el llamador cae a «sin IA» por ValueError
    criterios_raw = data.get("criterios")
    if not isinstance(criterios_raw, dict) or any(c not in criterios_raw for c in CRITERIOS_FEYNMAN):
        raise ValueError("Faltan criterios Feynman en la respuesta de la IA.")
    try:
        criterios = {
            c: FeynmanCriterio.model_validate(criterios_raw[c]).model_dump(exclude_none=True)
            for c in CRITERIOS_FEYNMAN
        }
        return FeynmanEvaluation.model_validate(
            {
                "concept": concept,
                "score": data.get("score"),
                "mastery_level": data.get("mastery_level") or "Intermedio",
                "clarity_score": data.get("clarity_score", criterios["simplicidad"]["puntaje"]),
                "precision_score": data.get("precision_score", criterios["precision"]["puntaje"]),
                "jargon_used": data.get("jargon_used") or [],
                "knowledge_gaps": data.get("knowledge_gaps") or [],
                "strengths": data.get("strengths") or [],
                "feedback_summary": data.get("feedback_summary") or f"Evaluación de {concept} completada.",
                "suggested_simplification": (
                    data.get("suggested_simplification") or f"Explicá {concept} con una analogía simple."
                ),
                "criterios": criterios,
                "sin_ia": False,
            }
        )
    except ValidationError as error:
        raise ValueError(f"La evaluación de la IA no cumple el esquema ({error.error_count()} errores).") from None


def _terminos_clave(note: VaultNote | None, maximo: int = 60) -> list[str]:
    """Las palabras largas más frecuentes de la nota (sin frontmatter ni formato), en minúsculas."""
    if note is None:
        return []
    texto = getattr(note, "clean_text", None) or note.content or ""
    frecuencia: dict[str, int] = {}
    for palabra in re.findall(r"\b[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{7,}\b", texto):
        clave = palabra.casefold()
        if clave in _PALABRAS_COMUNES:
            continue
        frecuencia[clave] = frecuencia.get(clave, 0) + 1
    return [p for p, _ in sorted(frecuencia.items(), key=lambda item: (-item[1], item[0]))[:maximo]]


def _esta_explicado(texto: str, termino: str) -> bool:
    """Si alguna aparición del término va seguida de una aclaración («es decir», paréntesis, dos puntos, «es como»...)."""
    for encontrado in re.finditer(re.escape(termino), texto):
        if _ACLARACION.match(texto[encontrado.end():encontrado.end() + 40]):
            return True
    return False
