"""Ingestor y analizador pedagógico de sílabos y temarios (PDF, Markdown y Texto Plano).

Soporta extracción nativa sin dependencias binarias externas pesadas,
detección heurística de módulos y temas, y enriquecimiento curricular con IA
(Gap Analysis, scaffolding y progresión de Bloom según el enfoque de estudio).
"""

from __future__ import annotations

import json
import logging
import re
import zlib
from typing import TYPE_CHECKING

from aulento.core.ia.lectura import leer_json
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import FaltaClaveDeIA, IANoDisponibleError, Pedido
from aulento.db.cuenta import exigir_repositorio_de_cuenta
from aulento.models.roadmap import (
    EnfoqueEstudio,
    EstadoTema,
    FuenteTema,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
)

if TYPE_CHECKING:
    from aulento.db.roadmap_repository import RoadmapRepository

logger = logging.getLogger(__name__)


class SyllabusIngestor:
    """Motor de ingesta, parsing heurístico y curaduría pedagógica de programas de estudio."""

    @staticmethod
    def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
        """Extrae texto de un archivo PDF usando el lector acotado y seguro de pdf_text."""
        from aulento.mcp.pdf_text import (
            PdfRechazado,
            PdfSinTextoError,
            extraer_texto_pdf,
        )

        try:
            texto = extraer_texto_pdf(pdf_bytes, max_caracteres=500_000)
            if texto.strip():
                return texto.strip()
        except PdfRechazado:
            raise
        except PdfSinTextoError:
            pass

        return SyllabusIngestor._extraer_texto_lineal_acotado(pdf_bytes)

    @staticmethod
    def _extraer_texto_lineal_acotado(pdf_bytes: bytes) -> str:
        """Fallback acotado y lineal O(N) sin regex cuadrática ni descompresión sin límite."""
        extracted_chunks: list[str] = []
        max_streams = 100
        max_bytes_descomprimidos = 10 * 1024 * 1024
        bytes_descomprimidos_totales = 0
        pos = 0
        streams_leidos = 0

        while streams_leidos < max_streams:
            stream_idx = pdf_bytes.find(b"stream", pos)
            if stream_idx == -1:
                break
            inicio_datos = stream_idx + 6
            if pdf_bytes[inicio_datos : inicio_datos + 2] == b"\r\n":
                inicio_datos += 2
            elif pdf_bytes[inicio_datos : inicio_datos + 1] in (b"\n", b"\r"):
                inicio_datos += 1

            fin_idx = pdf_bytes.find(b"endstream", inicio_datos)
            if fin_idx == -1:
                break

            stream_data = pdf_bytes[inicio_datos:fin_idx]
            pos = fin_idx + 9
            streams_leidos += 1

            raw_text = b""
            try:
                dec = zlib.decompressobj()
                limite = min(1_000_000, max_bytes_descomprimidos - bytes_descomprimidos_totales)
                if limite <= 0:
                    break
                raw_text = dec.decompress(stream_data, max_length=limite)
                bytes_descomprimidos_totales += len(raw_text)
            except zlib.error:
                try:
                    dec = zlib.decompressobj(-15)
                    raw_text = dec.decompress(stream_data, max_length=1_000_000)
                    bytes_descomprimidos_totales += len(raw_text)
                except zlib.error:
                    raw_text = stream_data[:1_000_000]

            tj_matches = re.findall(rb"\((.*?)\)\s*Tj", raw_text)
            for m in tj_matches:
                decoded = SyllabusIngestor._decode_pdf_string(m)
                if decoded.strip():
                    extracted_chunks.append(decoded)

            bracket_matches = re.findall(rb"\[(.*?)\]\s*TJ", raw_text)
            for bm in bracket_matches:
                inner_strings = re.findall(rb"\((.*?)\)", bm)
                line = "".join(SyllabusIngestor._decode_pdf_string(s) for s in inner_strings)
                if line.strip():
                    extracted_chunks.append(line)

        if len(" ".join(extracted_chunks).strip()) < 30:
            readable_chunks = re.findall(rb"\(([\x20-\x7E\xA0-\xFF]{3,})\)", pdf_bytes[:500_000])
            for rc in readable_chunks:
                decoded = SyllabusIngestor._decode_pdf_string(rc)
                if decoded.strip():
                    extracted_chunks.append(decoded)

        full_text = "\n".join(extracted_chunks)
        cleaned = re.sub(r"[ \t]+", " ", full_text)
        return cleaned.strip()

    @staticmethod
    def _decode_pdf_string(b: bytes) -> str:
        """Decodifica secuencias de escape estándar en cadenas PDF."""
        # Reemplazar escapes habituales
        b = b.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
        b = b.replace(b"\\r", b"\n").replace(b"\\n", b"\n").replace(b"\\t", b"\t")

        # Escapes octales \ddd
        def replace_octal(match):
            try:
                return bytes([int(match.group(1), 8)])
            except (ValueError, IndexError):
                return match.group(0)

        b = re.sub(rb"\\([0-7]{1,3})", replace_octal, b)

        # Intentar UTF-8, luego Latin-1 / CP1252
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
        return b.decode("utf-8", errors="ignore")

    @staticmethod
    def parse_text_to_modules(content: str) -> list[RoadmapModuleCreate]:
        """Parsea texto plano o Markdown y extrae módulos jerárquicos y temas."""
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return []

        modules: list[RoadmapModuleCreate] = []
        current_module: RoadmapModuleCreate | None = None
        current_topics: list[RoadmapTopicCreate] = []

        # Patrones para detectar encabezados de módulos / unidades / semanas
        module_regex = re.compile(
            r"^(?:#+\s*|\*{1,2})?(?:M[oó]dulo|Unidad|Bloque|Semana|Cap[ií]tulo|Secci[oó]n|Parte|Module|Unit|Chapter|Week)\s*([0-9IVXLCDM]+)?[:\s\-\.]*(.*?)(?:\*{1,2})?$",
            re.IGNORECASE,
        )
        # Patrón para detectar encabezados Markdown de nivel 1 o 2 (# o ##) como módulos
        md_header_regex = re.compile(r"^#{1,2}\s+(.*)$")

        # Patrón para viñetas o listas numeradas de temas
        bullet_regex = re.compile(r"^(?:[\*\-\+•]\s+|\d+[\.\)]\s+)(.*)$")
        # Detección de duración: (2h), (45 min), [3 horas], etc.
        duration_regex = re.compile(
            r"[\(\[]\s*(\d+(?:\.\d+)?)\s*(h|hrs?|horas?|min|minutos?|semanas?)\s*[\)\]]",
            re.IGNORECASE,
        )

        for line in lines:
            # 1. Comprobar si la línea es un módulo explícito
            mod_match = module_regex.match(line)
            md_match = md_header_regex.match(line)

            is_module_header = False
            mod_title = ""

            if mod_match:
                prefix_num = mod_match.group(1) or str(len(modules) + 1)
                title_rest = mod_match.group(2).strip()
                mod_title = f"Módulo {prefix_num}: {title_rest}" if title_rest else f"Módulo {prefix_num}"
                is_module_header = True
            elif md_match and not bullet_regex.match(line):
                mod_title = md_match.group(1).strip()
                is_module_header = True

            if is_module_header:
                # Guardar módulo anterior si existía
                if current_module:
                    current_module.temas = current_topics
                    modules.append(current_module)

                current_topics = []
                current_module = RoadmapModuleCreate(
                    titulo=mod_title,
                    descripcion="",
                    orden=len(modules) + 1,
                    temas=[],
                )
                continue

            # 2. Si no es cabecera de módulo, verificar si es tema (bullet o texto relevante)
            bullet_match = bullet_regex.match(line)
            topic_raw = bullet_match.group(1).strip() if bullet_match else line

            # Evitar líneas que sean meramente separadores o ruido
            if len(topic_raw) < 3 or topic_raw.startswith(("---", "===")):
                continue

            # Extraer duración si está especificada
            dur_info = ""
            dur_match = duration_regex.search(topic_raw)
            if dur_match:
                qty = float(dur_match.group(1))
                unit = dur_match.group(2).lower()
                dur_info = f" ({int(qty)} {unit})"
                topic_title = duration_regex.sub("", topic_raw).strip()
            else:
                topic_title = topic_raw

            # Crear tema
            if not current_module:
                current_module = RoadmapModuleCreate(
                    titulo="Módulo 1: Fundamentos y Contenido Inicial",
                    descripcion="Contenidos extraídos del sílabo",
                    orden=1,
                    temas=[],
                )

            desc = f"Estimado:{dur_info}" if dur_info else None
            topic = RoadmapTopicCreate(
                titulo=topic_title,
                descripcion=desc,
                orden=len(current_topics) + 1,
                estado=EstadoTema.PENDIENTE,
                fuente=FuenteTema.PDF_GAP,
            )
            current_topics.append(topic)

        # Cerrar el último módulo
        if current_module:
            current_module.temas = current_topics
            modules.append(current_module)

        return modules

    @staticmethod
    def enhance_with_ai(
        modules: list[RoadmapModuleCreate],
        title: str,
        target_role: str,
        category: str = "data_ai",
        enfoque_estudio: EnfoqueEstudio = EnfoqueEstudio.PROFESIONAL,
        nivel_objetivo: str = "Junior",
        *,
        repo: RoadmapRepository,
    ) -> tuple[list[RoadmapModuleCreate], list[str]]:
        """Aplica Gap Analysis y Backward Design con la IA de la cuenta para enriquecer el temario original.

        `repo` es el repositorio de la cuenta que lo pide: se usa su clave y a ella se le anota el consumo de IA.
        Sin IA utilizable devuelve el temario original y, en la lista de sugerencias, por qué.
        """
        exigir_repositorio_de_cuenta(repo)

        # Serializar temario actual para enviarlo al modelo
        syllabus_dict = [
            {
                "modulo": m.titulo,
                "temas": [t.titulo for t in m.temas],
            }
            for m in modules
        ]

        system_instruction = (
            "Eres un Diseñador Curricular Senior y Pedagogo Experto en Metodología Backward Design "
            "(Understanding by Design - UbD) y Taxonomía de Bloom revisada.\n\n"
            "Tu misión es analizar el temario/sílabo importado por el estudiante y realizar un "
            "'Curriculum Gap Analysis' y enriquecimiento pedagógico:\n"
            "1. ANDAMIAJE COGNITIVO (Scaffolding): Si hay saltos bruscos entre conceptos básicos y avanzados, "
            "inserta los temas puente necesarios para evitar vacíos conceptuales.\n"
            "2. PROGRESIÓN DE BLOOM: Garantiza una secuencia lógica: Recordar/Comprender -> Aplicar -> Analizar/Crear.\n"
            f"3. ENFOQUE DE ESTUDIO ({enfoque_estudio.value}):\n"
            "   - profesional: Enfatiza aplicaciones reales, casos de la industria, debugging y arquitectura.\n"
            "   - academico: Enfatiza rigor formal, pruebas, algoritmos y lectura de papers.\n"
            "   - practico_proyectos: 80% construcción hands-on, repositorios de código y prototipos.\n"
            "   - personal_hobby: Ritmo amigable, proyectos lúdicos y ejemplos intuitivos.\n"
            "   - certificacion: Cobertura exhaustiva de dominios de examen y simulaciones.\n"
            "4. REGLA FUNDAMENTAL: Conserva todos los temas clave aportados por el usuario; tu trabajo es "
            "completar lo que falte, reordenar si hay mala cronología y optimizar los nombres para que sean accionables.\n\n"
            "Responde ÚNICAMENTE un JSON con este esquema:\n"
            "{\n"
            '  "enhancements": [\n'
            '    "Explicación breve de la mejora 1 (ej: \'Se insertó tema de andamiaje: X en el Módulo 1\')",\n'
            '    "Explicación breve de la mejora 2"\n'
            '  ],\n'
            '  "modulos": [\n'
            '    {\n'
            '      "title": "Nombre del módulo",\n'
            '      "description": "Objetivo pedagógico del módulo",\n'
            '      "topics": [\n'
            '        {\n'
            '          "title": "Título del tema pedagógicamente formulado",\n'
            '          "description": "Breve descripción o resultado de aprendizaje"\n'
            '        }\n'
            '      ]\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        user_prompt = (
            f"Programa de Estudio: '{title}'. Rol/Área Objetivo: '{target_role}'. Nivel: '{nivel_objetivo}'.\n"
            f"Categoría: '{category}'. Enfoque Seleccionado: '{enfoque_estudio.value}'.\n\n"
            f"Temario en bruto extraído:\n{json.dumps(syllabus_dict, ensure_ascii=False, indent=2)}\n\n"
            "Analiza vacíos curriculares, aplica scaffolding pedagógico y devuelve la versión enriquecida en JSON."
        )

        try:
            respuesta = PasarelaDeIA.de_repositorio(repo).generar(
                Pedido(sistema=system_instruction, usuario=user_prompt, json=True, temperatura=0.25),
                "syllabus_enhancement",
                repo,
            )
        except FaltaClaveDeIA:
            return modules, [
                "Se preservó el temario original tal como fue importado (Modo local sin conexión o cuota de IA)."
            ]
        except IANoDisponibleError as error:
            return modules, [f"{error} Se preservó el temario original."]

        try:
            parsed = leer_json(respuesta.texto)
            enhanced_modules: list[RoadmapModuleCreate] = []
            for m_idx, m_data in enumerate(parsed.get("modulos", []), start=1):
                mod_topics: list[RoadmapTopicCreate] = []
                for t_idx, t_data in enumerate(m_data.get("topics", []), start=1):
                    mod_topics.append(
                        RoadmapTopicCreate(
                            titulo=t_data.get("title", f"Tema {t_idx}"),
                            descripcion=t_data.get("description", ""),
                            orden=t_idx,
                            estado=EstadoTema.PENDIENTE,
                            fuente=FuenteTema.AI_GENERADA,
                        )
                    )
                enhanced_modules.append(
                    RoadmapModuleCreate(
                        titulo=m_data.get("title", f"Módulo {m_idx}"),
                        descripcion=m_data.get("description", ""),
                        orden=m_idx,
                        temas=mod_topics,
                    )
                )

            enhancements = parsed.get("enhancements", [
                "Se optimizó la estructura curricular según la Taxonomía de Bloom y el enfoque elegido."
            ])
            return enhanced_modules, enhancements
        except Exception as err:  # noqa: BLE001
            logger.warning("Error parseando respuesta de enriquecimiento de sílabo: %s", err)
            return modules, [
                f"Error al procesar respuesta de IA ({err}). Se preservó el temario original."
            ]
