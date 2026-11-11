"""Pipeline de generación de apuntes académicos en el Obsidian Vault a partir de los materiales subidos (048)."""

import re
import sqlite3
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, Field

from aulento.core.materiales import AlmacenDeMateriales, MaterialNoEncontrado
from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta
from aulento.db.repository import CursoRepository, PlataformaRepository
from aulento.models.curso import CursoCreate
from aulento.vault.rutas import (
    exigir_nombre_de_nota,
    resolver_en_vault,
    vault_de_la_cuenta,
    vault_de_la_cuenta_con_conexion_propia,
)
from aulento.vault.sop_course import sanitize_filename

# Cuánto texto del material entra en el apunte: los pasajes del tema pedido o, sin tema, el principio
MAX_CARACTERES_EN_EL_APUNTE = 20_000


def clean_slug(text: str) -> str:
    """Genera un slug seguro y limpio para etiquetas y rutas sin acentos ni caracteres especiales."""
    normalized = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
    cleaned = re.sub(r"[^\w\s-]", "", normalized.lower()).strip()
    return re.sub(r"[-\s]+", "-", cleaned)


class MaterialNoteRequest(BaseModel):
    """Parámetros para generar un apunte SOP desde un material subido por la cuenta."""

    material_id: int = Field(..., ge=1, description="ID del material de la cuenta")
    course_id: int | None = Field(None, description="ID del curso destino en la base de datos local")
    topic: str | None = Field(None, description="Tema o título personalizado para el apunte")
    custom_notes: str | None = Field(None, description="Notas personales o comentarios adicionales")
    save_to_vault: bool = Field(False, description="Si es True, escribe físicamente la nota en el Vault")


class MaterialNoteGenerator:
    """Sintetiza notas completas bajo el SOP del Vault a partir de los materiales que subió una cuenta.

    Lee los materiales de la cuenta `user_id`, resuelve el curso de la nota solo entre sus cursos y escribe en
    el vault de esa cuenta.
    """

    def __init__(
        self,
        user_id: int,
        conn: sqlite3.Connection | None = None,
        vault_path: Path | None = None,
    ):
        self.user_id = exigir_cuenta(user_id)
        self._conn = conn
        self._vault_path = vault_path
        self.materiales = (
            AlmacenDeMateriales(conn, self.user_id) if conn else AlmacenDeMateriales.con_conexion_propia(self.user_id)
        )

    @property
    def vault_path(self) -> Path:
        """Vault de la cuenta: la carpeta recibida al construir o, si no, la que resuelve `vault_de_la_cuenta`."""
        if self._vault_path is not None:
            return self._vault_path
        if self._conn:
            return vault_de_la_cuenta(self._conn, self.user_id)
        return vault_de_la_cuenta_con_conexion_propia(self.user_id)

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn:
            return self._conn
        return get_connection()

    def get_material(self, material_id: int, topic: str | None = None) -> dict[str, Any]:
        """Los datos del material de la cuenta y el texto que va al apunte; uno ajeno levanta `ValueError`."""
        try:
            material = self.materiales.obtener(material_id, con_texto=False)
        except MaterialNoEncontrado:
            raise ValueError(f"No se encontró el material con ID {material_id}.") from None
        material["texto"] = self.materiales.fragmentos_relevantes(material_id, topic or "", MAX_CARACTERES_EN_EL_APUNTE)
        return material

    def list_available_materials(self) -> list[dict[str, Any]]:
        """Los materiales de la cuenta con los que se puede generar un apunte."""
        return [
            {"id": m["id"], "name": m["nombre"], "extension": m["extension"], "bytes": m["bytes"], "creado_en": m["creado_en"]}
            for m in self.materiales.listar()
        ]

    def resolve_course(
        self,
        conn: sqlite3.Connection,
        course_id: int | None = None,
        course_hint: str | None = None,
        crear_si_falta: bool = True,
    ) -> tuple[Any, str]:
        """Resuelve el curso y plataforma asociada por ID explícito o por coincidencia con course_hint."""
        curso_repo = CursoRepository(conn, self.user_id)
        plat_repo = PlataformaRepository(conn, self.user_id)

        if course_id:
            course = curso_repo.get_by_id(course_id)
            if course:
                plat = plat_repo.get_by_id(course.plataforma_id)
                plat_name = plat.nombre if plat else "Plataforma Externa"
                return course, plat_name

        all_courses = curso_repo.list_all()

        if course_hint:
            hint_lower = course_hint.lower()
            # 1. Coincidencia directa con cursos existentes
            for c in all_courses:
                if c.nombre_curso.lower() in hint_lower or hint_lower in c.nombre_curso.lower():
                    plat = plat_repo.get_by_id(c.plataforma_id)
                    plat_name = plat.nombre if plat else "Plataforma Externa"
                    return c, plat_name

            # 2. Coincidencia con plataformas registradas
            all_platforms = plat_repo.list_all()
            for p in all_platforms:
                p_name_lower = p.nombre.lower()
                if p_name_lower in hint_lower or hint_lower in p_name_lower or any(word in hint_lower for word in p_name_lower.split() if len(word) > 4):
                    courses_for_p = [c for c in all_courses if c.plataforma_id == p.id]
                    if courses_for_p:
                        return courses_for_p[0], p.nombre
                    if not crear_si_falta:
                        provisional = SimpleNamespace(
                            id=0,
                            nombre_curso=course_hint or "Curso General",
                            url_aula=p.url_acceso,
                        )
                        return provisional, p.nombre
                    # Si la plataforma existe pero aún no tiene curso, crearlo automáticamente
                    new_course = curso_repo.create(
                        CursoCreate(
                            plataforma_id=p.id,
                            nombre_curso=course_hint,
                            url_aula=p.url_acceso,
                            estado="en_curso",
                            prioridad="alta",
                            progreso_pct=0.0,
                        )
                    )
                    return new_course, p.nombre

        if all_courses:
            first_c = all_courses[0]
            plat = plat_repo.get_by_id(first_c.plataforma_id)
            plat_name = plat.nombre if plat else "Plataforma Externa"
            return first_c, plat_name

        if not crear_si_falta:
            provisional = SimpleNamespace(
                id=0,
                nombre_curso=course_hint or "Curso General",
                url_aula="https://aulento.local",
            )
            return provisional, "General"

        raise ValueError("No hay cursos registrados en la base de datos para asociar el apunte.")

    def extract_topic(self, file_name: str, explicit_topic: str | None = None) -> str:
        """Limpia el nombre de archivo de prefijos y extensiones para obtener el título conceptual."""
        if explicit_topic and explicit_topic.strip():
            return explicit_topic.strip()

        # Quitar extensiones
        name = re.sub(r"\.(pdf|md|markdown|txt)$", "", file_name, flags=re.IGNORECASE)

        # Quitar prefijos comunes (ej. "Digital House - Data Science - 01 - ", "Google Cloud Skills - ")
        cleaned = re.sub(r"^[A-Za-z0-9\s]+-\s*[A-Za-z0-9\s]+-\s*\d+\s*-\s*", "", name)
        cleaned = re.sub(r"^[A-Za-z0-9\s]+-\s*", "", cleaned)
        cleaned = cleaned.strip()

        return cleaned if cleaned else name

    def generate_concepts_and_wikilinks(self, content_text: str, topic: str) -> str:
        """Extrae conceptos clave y los formatea con wikilinks [[...]]."""
        lines = content_text.splitlines()
        concepts: list[str] = []

        for line in lines:
            line_str = line.strip()
            # Patrón "Tema: Algo"
            match_tema = re.match(r"^Tema:\s*(.+)$", line_str, flags=re.IGNORECASE)
            if match_tema:
                t = match_tema.group(1).strip().rstrip(".:")
                concepts.append(f"- [[{t}]]: Eje temático central del módulo.")
                continue

            # Patrón "1. Concepto: Detalle" o "1. Concepto (Detalle)"
            match_numbered = re.match(r"^\d+\.\s+([A-Za-zÁ-Úá-ú0-9\s\-_/]+)(?::|\(|\.)\s*(.*)$", line_str)
            if match_numbered:
                concept_name = match_numbered.group(1).strip().rstrip(".:")
                detail = match_numbered.group(2).strip().rstrip(".:")
                if detail.endswith(")"):
                    detail = detail[:-1].strip()
                concepts.append(f"- [[{concept_name}]]: {detail if detail else 'Concepto clave explorado en el material.'}")
                continue

        if not concepts:
            concepts = [
                f"- [[{topic}]]: Arquitectura y fundamentos técnicos del módulo.",
                "- [[Arquitectura y Buenas Prácticas]]: Implementación en entornos productivos.",
                "- [[Trade-offs de Diseño]]: Consideraciones de costo, latencia y escalabilidad.",
            ]

        return "\n".join(concepts)

    def generate_architecture_or_code(self, topic: str, content_text: str) -> str:
        """Genera un diagrama Mermaid o fragmento de código adaptado a la temática."""
        combined = (topic + " " + content_text).lower()

        if "bigquery" in combined or "dremel" in combined or "cloud storage" in combined:
            return (
                "```mermaid\n"
                "graph LR\n"
                "    subgraph Ingestion [Ingesta & Fuentes]\n"
                "        S[Cloud Storage / Streams] --> BQ[BigQuery Engine]\n"
                "    end\n"
                "    subgraph Architecture [Separación Cómputo & Almacenamiento]\n"
                "        BQ --> Dremel[Dremel Multi-tenant Slots]\n"
                "        Dremel <--> Colossus[Colossus Distributed File System]\n"
                "        Dremel <--> BigLake[BigLake Open Formats / Parquet]\n"
                "    end\n"
                "    subgraph Analytics [Consumo]\n"
                "        Dremel --> Looker[BI & Looker Studio]\n"
                "        Dremel --> ML[Vertex AI / BQML]\n"
                "    end\n"
                "```"
            )

        if "machine learning" in combined or "arbol" in combined or "random forest" in combined:
            return (
                "```mermaid\n"
                "graph TD\n"
                "    Dataset[Dataset de Entrenamiento] --> Boot1[Bootstrap Sample 1]\n"
                "    Dataset --> Boot2[Bootstrap Sample 2]\n"
                "    Dataset --> BootN[Bootstrap Sample N]\n"
                "    Boot1 --> Tree1[Árbol 1 (Subconjunto de Features)]\n"
                "    Boot2 --> Tree2[Árbol 2 (Subconjunto de Features)]\n"
                "    BootN --> TreeN[Árbol N (Subconjunto de Features)]\n"
                "    Tree1 --> Majority[Votación / Promedio Ensamble]\n"
                "    Tree2 --> Majority\n"
                "    TreeN --> Majority\n"
                "    Majority --> Prediction[Predicción Final Robusta]\n"
                "```"
            )

        if "kafka" in combined or "streaming" in combined or "event" in combined:
            return (
                "```mermaid\n"
                "graph LR\n"
                "    P1[Producer Microservice] --> T[(Kafka Topic: Partition 0..N)]\n"
                "    T --> CG1[Consumer Group A: Analytics]\n"
                "    T --> CG2[Consumer Group B: Notification]\n"
                "    CG1 --> Storage[(Lakehouse / DB)]\n"
                "```"
            )

        # Diagrama genérico de arquitectura de flujo de datos
        return (
            "```mermaid\n"
            "graph LR\n"
            "    Raw[Material Origen] --> Pipeline[Procesamiento & Validación]\n"
            "    Pipeline --> Engine[Motor Especializado]\n"
            "    Engine --> Target[Consolidación en Vault & Producción]\n"
            "```"
        )

    def generate_active_recall_questions(self, topic: str, content_text: str) -> list[tuple[str, str]]:
        """Sintetiza preguntas y respuestas de Active Recall según la Técnica Feynman / FSRS."""
        questions: list[tuple[str, str]] = []

        questions.append(
            (
                f"¿Cuál es el propósito central de {topic} y qué problema técnico o de negocio resuelve?",
                f"{topic} optimiza la eficiencia operativa, reduce latencias y asegura consistencia en el procesamiento de información bajo entornos escalables.",
            )
        )

        lines = [l.strip() for l in content_text.splitlines() if l.strip() and not l.lower().startswith("tema:")]
        if lines:
            sample_point = lines[0]
            clean_point = re.sub(r"^\d+\.\s*", "", sample_point)
            questions.append(
                (
                    f"¿Cómo opera internamente '{clean_point}' y qué precauciones deben tomarse al implementarlo?",
                    "Requiere calibrar los parámetros de configuración y considerar los trade-offs de cómputo y almacenamiento para prevenir cuellos de botella.",
                )
            )

        questions.append(
            (
                f"¿Cuáles son los principales trade-offs (costo, complejidad, rendimiento) al implementar {topic}?",
                "El trade-off principal radica en equilibrar la sencillez operativa frente a la necesidad de optimización de recursos y escalabilidad a largo plazo.",
            )
        )

        return questions

    def generate_note(
        self,
        material_id: int,
        course_id: int | None = None,
        topic: str | None = None,
        custom_notes: str | None = None,
        crear_si_falta: bool = False,
    ) -> dict[str, Any]:
        """Sintetiza la nota completa en formato Markdown conforme al SOP Cursos y Apuntes.

        Levanta `RutaFueraDelVaultError` si `topic`, que da nombre a la nota, es en realidad una ruta, y
        `ValueError` si el material no es de la cuenta.
        """
        if topic:
            exigir_nombre_de_nota(topic)
        material = self.get_material(material_id, topic)
        nombre = material["nombre"]
        texto = material["texto"]
        nombre_en_yaml = nombre.replace('"', "'")

        conn = self._get_conn()
        try:
            course, platform_name = self.resolve_course(conn, course_id, Path(nombre).stem, crear_si_falta=crear_si_falta)
        finally:
            if not self._conn:
                conn.close()

        resolved_topic = self.extract_topic(nombre, topic)
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        plat_slug = clean_slug(platform_name)
        topic_slug = clean_slug(resolved_topic)

        tags = ["curso", plat_slug, topic_slug, "material"]

        # Resumen ejecutivo
        tldr_content = (
            f"Apunte sintetizado automáticamente a partir del material '{nombre}'. "
            f"Cubre los fundamentos y decisiones de diseño de {resolved_topic} en el marco de {course.nombre_curso}."
        )

        # Conceptos clave y wikilinks
        concepts_markdown = self.generate_concepts_and_wikilinks(texto, resolved_topic)

        # Diagrama de arquitectura o código
        architecture_markdown = self.generate_architecture_or_code(resolved_topic, texto)

        # Preguntas Active Recall
        recall_questions = self.generate_active_recall_questions(resolved_topic, texto)
        recall_markdown = "\n".join(
            [f"- **{q}**\n  - *Respuesta:* {a}" for q, a in recall_questions]
        )

        # Notas detalladas
        detailed_notes = (
            "### Contenido y Desglose del Material\n"
            f"{texto}\n\n"
            "### Diagrama de Arquitectura / Modelo Técnico\n"
            f"{architecture_markdown}"
        )
        if custom_notes and custom_notes.strip():
            detailed_notes += f"\n\n### Observaciones Personales de Estudio\n{custom_notes.strip()}"

        # MOCs
        mocs_markdown = (
            "- [[02 MOCs/MOC Inteligencia Artificial y Datos]]\n"
            "- [[02 MOCs/MOC Ingeniería de Software]]"
        )

        content = (
            "---\n"
            "type: Curso\n"
            f'title: "{resolved_topic}"\n'
            f'curso: "{course.nombre_curso}"\n'
            f'plataforma: "{platform_name}"\n'
            f'fecha: "{today_str}"\n'
            f"tags: [{', '.join(tags)}]\n"
            f'sources: ["{course.url_aula}"]\n'
            "material:\n"
            f"  id: {material_id}\n"
            f'  name: "{nombre_en_yaml}"\n'
            "---\n\n"
            f"# {resolved_topic}\n\n"
            f"> **Curso:** [[{course.nombre_curso}]]  \n"
            f"> **Plataforma:** {platform_name}  \n"
            f"> **Material Origen:** {nombre}  \n"
            f"> **Aula Virtual:** [{course.nombre_curso}]({course.url_aula})\n\n"
            "## 1. Resumen Ejecutivo (TL;DR)\n"
            f"{tldr_content}\n\n"
            "## 2. Conceptos Clave & Wikilinks\n"
            f"{concepts_markdown}\n\n"
            "## 3. Notas Detalladas y Diapositivas / Arquitectura\n"
            f"{detailed_notes}\n\n"
            "## 4. Preguntas de Active Recall (Feynman / FSRS)\n"
            f"{recall_markdown}\n\n"
            "## 5. Conexiones con MOCs\n"
            f"{mocs_markdown}\n"
        )

        safe_course_folder = sanitize_filename(course.nombre_curso)
        safe_topic_filename = f"{sanitize_filename(resolved_topic)}.md"
        relative_path = f"04 Knowledge/Cursos/{safe_course_folder}/{safe_topic_filename}"

        return {
            "title": resolved_topic,
            "course": course.nombre_curso,
            "platform": platform_name,
            "material_id": material_id,
            "file_name": nombre,
            "relative_path": relative_path,
            "content": content,
        }

    def save_note_to_vault(
        self,
        material_id: int,
        course_id: int | None = None,
        topic: str | None = None,
        custom_notes: str | None = None,
        crear_si_falta: bool = True,
    ) -> Path:
        """Sintetiza y persiste físicamente la nota en el Obsidian Vault."""
        data = self.generate_note(
            material_id=material_id,
            course_id=course_id,
            topic=topic,
            custom_notes=custom_notes,
            crear_si_falta=crear_si_falta,
        )
        target_file = resolver_en_vault(self.vault_path, data["relative_path"])
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(data["content"], encoding="utf-8")
        return target_file
