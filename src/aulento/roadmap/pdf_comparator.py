"""Comparador de Syllabi en PDF y Auditor de Brechas (Gap Analysis)."""

import logging
import re

from aulento.core.ia.lectura import leer_json, respuesta_inutil
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import (
    MIME_PDF,
    Adjunto,
    IANoDisponibleError,
    Pedido,
    motivo_sin_ia,
)
from aulento.models.roadmap import (
    GapTopicItem,
    PDFComparisonResult,
    RoadmapDetail,
)
from aulento.roadmap.syllabus_ingestor import SyllabusIngestor

logger = logging.getLogger(__name__)


class RoadmapPDFComparator:
    """Extrae temarios desde archivos PDF y realiza análisis comparativo de brechas (Gap Analysis).

    `pasarela` es la de la cuenta que pide la comparación: de ella salen el proveedor, la clave y el modelo.
    """

    def __init__(self, pasarela: PasarelaDeIA) -> None:
        if not isinstance(pasarela, PasarelaDeIA):
            raise TypeError("El comparador necesita la pasarela de IA de la cuenta que pide la comparación.")
        self.pasarela = pasarela

    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes) -> str:
        """Extrae texto de un archivo PDF usando el extractor acotado y seguro de temarios."""
        extracted = SyllabusIngestor.extract_text_from_pdf_bytes(pdf_bytes)
        return extracted or "Syllabus técnico en formato PDF (contenido procesado)."

    def compare_syllabus(
        self,
        current_roadmap: RoadmapDetail,
        pdf_bytes: bytes,
        filename: str = "syllabus.pdf",
    ) -> PDFComparisonResult:
        """Compara el syllabus del PDF contra la ruta activa produciendo un Gap Analysis estructurado."""
        # 1. Recopilar temas existentes en la ruta
        existing_topics: list[str] = []
        for m in current_roadmap.modulos:
            for t in m.temas:
                existing_topics.append(t.titulo)

        # 2. Lectura directa del PDF por el modelo de la cuenta
        motivo: str | None = None
        if len(pdf_bytes) > 0:
            system_instruction = (
                "Eres un Auditor Curricular y Arquitecto Técnico Senior. Tu tarea es analizar el archivo PDF adjunto "
                "(que contiene el syllabus, blueprint de certificación o temario de un curso) y compararlo "
                "contra la lista de temas que el estudiante YA TIENE en su ruta de aprendizaje.\n"
                "Debes realizar un Gap Analysis riguroso y responder EXCLUSIVAMENTE con un JSON:\n"
                "{\n"
                '  "total_syllabus_topics": 12,\n'
                '  "matched_topics": ["Tema del PDF que ya está cubierto en la ruta"],\n'
                '  "gap_topics": [\n'
                '    {\n'
                '      "titulo": "Tema nuevo o brecha detectada",\n'
                '      "descripcion": "Por qué es relevante según el syllabus del PDF",\n'
                '      "modulo_sugerido": "Especialización & Brechas"\n'
                '    }\n'
                '  ],\n'
                '  "recommendations": ["Recomendación pedagógica o tecnológica 1"],\n'
                '  "summary": "Resumen ejecutivo del alineamiento curricular (ej: 75% de cobertura, 4 brechas clave)"\n'
                "}\n"
                "Sé muy preciso con las tecnologías. No inventes temas que no figuren en el PDF."
            )
            prompt_text = (
                f"Ruta actual: '{current_roadmap.titulo}' (Nivel: {current_roadmap.nivel_objetivo}).\n"
                f"Temas que el estudiante YA TIENE en su ruta:\n"
                + "\n".join(f"- {t}" for t in existing_topics)
                + f"\n\nAnaliza el documento PDF adjunto ('{filename}') y determina las coincidencias y brechas."
            )
            try:
                respuesta = self.pasarela.generar(
                    Pedido(
                        sistema=system_instruction,
                        usuario=prompt_text,
                        adjuntos=(Adjunto(mime=MIME_PDF, datos=pdf_bytes),),
                        json=True,
                        temperatura=0.2,
                    ),
                    "pdf_compare",
                )
            except IANoDisponibleError as error:
                motivo = motivo_sin_ia(error)
            else:
                try:
                    parsed = leer_json(respuesta.texto)
                    gaps = [
                        GapTopicItem(
                            titulo=g.get("titulo", "Tema faltante"),
                            descripcion=g.get("descripcion"),
                            modulo_sugerido=g.get("modulo_sugerido", "Especialización & Brechas"),
                        )
                        for g in parsed.get("gap_topics", [])
                    ]
                    return PDFComparisonResult(
                        total_syllabus_topics=parsed.get("total_syllabus_topics", len(gaps) + len(parsed.get("matched_topics", []))),
                        matched_topics=parsed.get("matched_topics", []),
                        gap_topics=gaps,
                        recommendations=parsed.get("recommendations", []),
                        summary=parsed.get("summary", f"Análisis completado exitosamente con {respuesta.modelo}."),
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("No se pudo leer la comparación que devolvió la IA: %s. Se usa el comparador local.", e)
                    motivo = str(respuesta_inutil(respuesta, "devolvió una comparación que no se pudo leer"))

        # 3. Fallback de Análisis Sintáctico / Lexical Local
        extracted_text = self.extract_text_from_pdf(pdf_bytes)
        matched: list[str] = []
        gaps: list[GapTopicItem] = []

        # Extraer líneas de texto significativas del PDF
        raw_lines = [line.strip() for line in extracted_text.splitlines() if len(line.strip()) > 4]
        candidate_topics: list[str] = []
        for line in raw_lines:
            # Filtrar números o encabezados irrelevantes
            cleaned = re.sub(r"^(módulo|capítulo|clase|tema|\d+[\.\)-])\s*", "", line, flags=re.IGNORECASE).strip()
            if 6 <= len(cleaned) <= 80 and not cleaned.isdigit():
                candidate_topics.append(cleaned)

        candidate_topics = list(dict.fromkeys(candidate_topics))[:15]

        # Comparar con temas existentes
        existing_lower = [t.lower() for t in existing_topics]
        for cand in candidate_topics:
            is_matched = any(
                cand.lower() in ext or ext in cand.lower() or any(w in ext for w in cand.lower().split() if len(w) > 4)
                for ext in existing_lower
            )
            if is_matched:
                matched.append(cand)
            else:
                gaps.append(
                    GapTopicItem(
                        titulo=cand,
                        descripcion=f"Identificado en {filename} como tópico relevante no cubierto.",
                        modulo_sugerido="Especialización & Brechas Detectadas",
                    )
                )

        if not gaps and not matched:
            # Fallback seguro con brechas curadas genéricas del PDF
            gaps = [
                GapTopicItem(
                    titulo=f"Conceptos Avanzados de {current_roadmap.titulo} en {filename}",
                    descripcion="Tópicos de especialización extraídos del syllabus externo.",
                    modulo_sugerido="Especialización & Brechas Detectadas",
                )
            ]

        total = len(matched) + len(gaps)
        coverage_pct = round((len(matched) / total * 100), 1) if total > 0 else 0.0

        return PDFComparisonResult(
            total_syllabus_topics=total,
            matched_topics=matched,
            gap_topics=gaps,
            recommendations=[
                "Incorporar las brechas detectadas para alinear la ruta con las certificaciones y exigencias del mercado.",
                "Priorizar los temas que conectan directamente con herramientas en producción.",
            ],
            summary=f"Syllabus analizado ({filename}): Cobertura estimada del {coverage_pct}%. Se identificaron {len(gaps)} brechas para incorporar.",
            is_fallback=True,
            motivo_sin_ia=motivo,
        )
