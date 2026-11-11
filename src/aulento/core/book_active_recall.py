"""Servicio de dominio para Lectura Activa con IA y Cosecha FSRS de Libros Técnicos."""

import logging
import sqlite3
from typing import Any

from aulento.core.activity_tracker import ActivityTracker
from aulento.core.ia.lectura import leer_json
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import Pedido
from aulento.db.focus_repository import FocusRepository
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.repository import LibroRepository
from aulento.models.book_active_recall import (
    ActiveRecallEvaluateRequest,
    ActiveRecallEvaluateResponse,
    ActiveRecallGenerateRequest,
    ActiveRecallGenerateResponse,
    ActiveRecallQuestion,
    BookHarvestCommitRequest,
    BookHarvestCommitResponse,
    BookHarvestPreviewRequest,
    BookHarvestPreviewResponse,
    HarvestedCardItem,
    QuestionEvaluation,
)
from aulento.models.focus_session import FocusSessionCreate
from aulento.models.fsrs_card import FSRSCardCreate

logger = logging.getLogger(__name__)


PROMPT_GENERAR_ACTIVE_RECALL = """
Actuá como un mentor y profesor de ingeniería senior especializado en libros técnicos.
Tu objetivo es evaluar la comprensión conceptual profunda y el razonamiento crítico del estudiante sobre el siguiente libro y tramo de lectura.

Libro: {titulo}
Tramo de lectura: {tramo}
Cantidad de preguntas: {cantidad}

INSTRUCCIONES PEDAGÓGICAS:
1. Generá exactamente {cantidad} preguntas de Active Recall orientadas a:
   - Decisiones de diseño, arquitectura y compromisos (trade-offs).
   - Mecanismos y funcionamiento interno de los conceptos tratados en este tramo.
   - Escenarios prácticos de resolución de problemas basados en la teoría del libro.
2. EVITÁ preguntas de memorización superficial (números de página, fechas o nombres irrelevantes).
3. Cada pregunta debe formularse con claridad en español.

Respondé ÚNICAMENTE con un JSON válido con esta estructura exacta:
{{
  "preguntas": [
    {{
      "id": 1,
      "pregunta": "¿Por qué el autor argumenta que...?",
      "objetivo_conceptual": "Comprobar comprensión sobre aislamiento de transacciones",
      "criterio_evaluacion": "Debe mencionar el trade-off entre consistencia y rendimiento"
    }}
  ]
}}
"""

PROMPT_EVALUAR_ACTIVE_RECALL = """
Actuá como un mentor y evaluador pedagógico senior en ingeniería de software y sistemas distribuidos.
El estudiante leyó el siguiente libro y tramo técnico y respondió al cuestionario de Active Recall.

Libro: {titulo}
Tramo evaluado: {tramo}

Cuestionario y respuestas del estudiante:
{respuestas_texto}

INSTRUCCIONES DE EVALUACIÓN:
1. Analizá objetivamente cada respuesta provista por el estudiante.
2. Asigná un puntaje de 0 a 100 a cada respuesta en base a su precisión conceptual y completitud.
3. Indicá los aciertos destacados y las oportunidades de mejora o corrección de malentendidos.
4. Redactá una explicación óptima y concisa de referencia para cada concepto.
5. Calculá el score global (promedio de 0 a 100), determiná el veredicto ("excelente" si score >= 80, "bueno" si score >= 60, o "a_repasar" si < 60) y un resumen pedagógico general para motivar y orientar al estudiante.

Respondé ÚNICAMENTE con un JSON válido con esta estructura:
{{
  "score_global": 85,
  "veredicto": "excelente",
  "resumen_pedagogico": "Demostrás un dominio sólido de los conceptos de particionado...",
  "evaluaciones": [
    {{
      "question_id": 1,
      "puntaje": 90,
      "aciertos": "Identificaste correctamente el riesgo de desbalance (hotspotting).",
      "mejoras": "Podrías haber mencionado el uso de hashing compuesto como mitigación adicional.",
      "explicacion_optima": "El particionado por clave distribuye equitativamente pero dificulta escaneos por rango..."
    }}
  ]
}}
"""

PROMPT_COSECHAR_FSRS = """
Actuá como un especialista en aprendizaje de inglés técnico profesional y memorización espaciada (FSRS v5).
A partir del siguiente libro técnico y tramo de lectura, extraé términos técnicos clave en inglés, patrones de diseño y conceptos esenciales que un ingeniero debe dominar y memorizar.

Libro: {titulo}
Tramo: {tramo}
Cantidad de tarjetas: {cantidad}

INSTRUCCIONES PARA LAS TARJETAS:
1. El foco principal es inglés técnico y precisión conceptual de ingeniería.
2. Cada tarjeta debe tener:
   - "categoria": "ingles_tecnico" (o el tema técnico del libro, ej. "data_engineering", "distributed_systems").
   - "item_pregunta": Término técnico o pregunta conceptual en inglés (ej. "What is Write Amplification in LSM-Trees?").
   - "respuesta_esperada": Explicación concisa y clara en español o bilingüe.
   - "contexto_uso": Breve oración de ejemplo en inglés técnico usada en la industria.

Respondé ÚNICAMENTE con un JSON válido con esta estructura:
{{
  "cards": [
    {{
      "categoria": "ingles_tecnico",
      "item_pregunta": "Write Amplification",
      "respuesta_esperada": "La relación entre la cantidad de bytes escritos en almacenamiento versus los bytes enviados por la aplicación.",
      "contexto_uso": "LSM-Trees typically trade off higher write amplification to reduce random I/O."
    }}
  ]
}}
"""


class BookActiveRecallService:
    """Gestiona sesiones de Active Recall y extracción de tarjetas FSRS a partir de lecturas."""

    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = user_id
        self.repo_libros = LibroRepository(conn, user_id)
        self.repo_fsrs = FSRSRepository(conn, user_id)
        self.pasarela = PasarelaDeIA(conn, user_id)
        self.tracker = ActivityTracker(user_id, conn=conn)

    def _obtener_libro(self, book_id: int):
        libro = self.repo_libros.get_by_id(book_id)
        if not libro:
            raise ValueError(f"Libro con ID {book_id} no encontrado en la cuenta.")
        return libro

    def _formatear_tramo(
        self,
        libro: Any,
        cap_desde: int | None = None,
        cap_hasta: int | None = None,
        pag_desde: int | None = None,
        pag_hasta: int | None = None,
    ) -> str:
        partes = []
        if cap_desde and cap_hasta and cap_desde != cap_hasta:
            partes.append(f"Capítulos {cap_desde} al {cap_hasta}")
        elif cap_desde or cap_hasta:
            partes.append(f"Capítulo {cap_desde or cap_hasta}")
        elif libro.capitulo_actual:
            partes.append(f"Capítulo {libro.capitulo_actual}")

        if pag_desde and pag_hasta and pag_desde != pag_hasta:
            partes.append(f"Páginas {pag_desde}-{pag_hasta}")
        elif pag_hasta or pag_desde:
            partes.append(f"Página {pag_hasta or pag_desde}")
        elif libro.pagina_actual:
            partes.append(f"Página {libro.pagina_actual}")

        return " • ".join(partes) if partes else "Lectura general de la obra"

    def generar_preguntas(
        self,
        book_id: int,
        req: ActiveRecallGenerateRequest | None = None,
    ) -> ActiveRecallGenerateResponse:
        """Genera preguntas pedagógicas de Active Recall con el LLM de la cuenta."""
        if req is None:
            req = ActiveRecallGenerateRequest()

        libro = self._obtener_libro(book_id)
        tramo = self._formatear_tramo(
            libro,
            cap_desde=req.capitulo_desde,
            cap_hasta=req.capitulo_hasta,
            pag_desde=req.pagina_desde,
            pag_hasta=req.pagina_hasta,
        )

        prompt = PROMPT_GENERAR_ACTIVE_RECALL.format(
            titulo=libro.titulo,
            tramo=tramo,
            cantidad=req.cantidad,
        )

        pedido = Pedido(usuario=prompt, json=True, temperatura=0.3)
        respuesta = self.pasarela.generar(pedido, endpoint_tipo="book_active_recall_generate")
        datos = leer_json(respuesta.texto)

        preguntas_lista = []
        for i, item in enumerate(datos.get("preguntas", []), 1):
            preguntas_lista.append(
                ActiveRecallQuestion(
                    id=item.get("id", i),
                    pregunta=item.get("pregunta", ""),
                    objetivo_conceptual=item.get("objetivo_conceptual", ""),
                    criterio_evaluacion=item.get("criterio_evaluacion", ""),
                )
            )

        return ActiveRecallGenerateResponse(
            book_id=libro.id,
            titulo=libro.titulo,
            tramo_evaluado=tramo,
            preguntas=preguntas_lista,
        )

    def evaluar_respuestas(
        self,
        book_id: int,
        req: ActiveRecallEvaluateRequest,
    ) -> ActiveRecallEvaluateResponse:
        """Evalúa formativamente las respuestas del estudiante y registra la sesión de estudio."""
        libro = self._obtener_libro(book_id)

        bloques_respuestas = []
        for r in req.respuestas:
            bloques_respuestas.append(
                f"[Pregunta {r.question_id}]: {r.pregunta}\n[Respuesta del estudiante]: {r.respuesta_usuario}\n"
            )
        respuestas_texto = "\n---\n".join(bloques_respuestas)

        prompt = PROMPT_EVALUAR_ACTIVE_RECALL.format(
            titulo=libro.titulo,
            tramo=req.tramo_evaluado,
            respuestas_texto=respuestas_texto,
        )

        pedido = Pedido(usuario=prompt, json=True, temperatura=0.2)
        respuesta = self.pasarela.generar(pedido, endpoint_tipo="book_active_recall_evaluate")
        datos = leer_json(respuesta.texto)

        evaluaciones = []
        for ev in datos.get("evaluaciones", []):
            evaluaciones.append(
                QuestionEvaluation(
                    question_id=ev.get("question_id", 1),
                    puntaje=int(ev.get("puntaje", 70)),
                    aciertos=ev.get("aciertos", ""),
                    mejoras=ev.get("mejoras", ""),
                    explicacion_optima=ev.get("explicacion_optima", ""),
                )
            )

        score_global = int(datos.get("score_global", 70))
        veredicto = datos.get("veredicto", "bueno" if score_global >= 60 else "a_repasar")
        resumen = datos.get("resumen_pedagogico", "Sesión de active recall completada.")

        # Registrar sesión de estudio
        try:
            FocusRepository(self.conn, self.user_id).record_session(
                FocusSessionCreate(
                    duracion_minutos=10,
                    tipo="pomodoro",
                    notas=f"Active Recall Libro: '{libro.titulo}' ({req.tramo_evaluado}) - Score: {score_global}%",
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo registrar la sesión de estudio: %s", e)

        return ActiveRecallEvaluateResponse(
            book_id=libro.id,
            titulo=libro.titulo,
            score_global=score_global,
            veredicto=veredicto,
            resumen_pedagogico=resumen,
            evaluaciones=evaluaciones,
        )

    def previsualizar_cosecha(
        self,
        book_id: int,
        req: BookHarvestPreviewRequest | None = None,
    ) -> BookHarvestPreviewResponse:
        """Genera tarjetas candidatas FSRS extraídas del libro."""
        if req is None:
            req = BookHarvestPreviewRequest()

        libro = self._obtener_libro(book_id)
        tramo = self._formatear_tramo(libro, cap_desde=req.capitulo, pag_desde=req.pagina)

        prompt = PROMPT_COSECHAR_FSRS.format(
            titulo=libro.titulo,
            tramo=tramo,
            cantidad=req.cantidad,
        )

        pedido = Pedido(usuario=prompt, json=True, temperatura=0.3)
        respuesta = self.pasarela.generar(pedido, endpoint_tipo="book_harvest_preview")
        datos = leer_json(respuesta.texto)

        cards = []
        for c in datos.get("cards", []):
            cards.append(
                HarvestedCardItem(
                    categoria=c.get("categoria", "ingles_tecnico"),
                    item_pregunta=c.get("item_pregunta", ""),
                    respuesta_esperada=c.get("respuesta_esperada", ""),
                    contexto_uso=c.get("contexto_uso"),
                )
            )

        return BookHarvestPreviewResponse(
            book_id=libro.id,
            titulo=libro.titulo,
            tramo=tramo,
            cards=cards,
        )

    def confirmar_cosecha(
        self,
        book_id: int,
        req: BookHarvestCommitRequest,
    ) -> BookHarvestCommitResponse:
        """Inserta las tarjetas seleccionadas en el mazo FSRS de la cuenta evitando duplicados."""
        libro = self._obtener_libro(book_id)

        # Consultar tarjetas existentes en la cuenta para evitar duplicar
        cursor = self.conn.cursor()
        filas = cursor.execute(
            "SELECT item_pregunta FROM fsrs_items WHERE user_id = ?;",
            (self.user_id,),
        ).fetchall()
        preguntas_existentes = {f[0].strip().lower() for f in filas if f[0]}

        guardadas = 0
        omitidas = 0

        for c in req.cards:
            preg = c.item_pregunta.strip()
            if not preg or preg.lower() in preguntas_existentes:
                omitidas += 1
                continue

            self.repo_fsrs.create_card(
                FSRSCardCreate(
                    categoria=c.categoria or "ingles_tecnico",
                    item_pregunta=preg,
                    respuesta_esperada=c.respuesta_esperada,
                    contexto_uso=c.contexto_uso,
                )
            )
            preguntas_existentes.add(preg.lower())
            guardadas += 1

        return BookHarvestCommitResponse(
            book_id=libro.id,
            guardadas=guardadas,
            omitidas_duplicadas=omitidas,
        )
