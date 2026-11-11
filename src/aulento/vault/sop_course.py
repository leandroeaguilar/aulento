"""Generador automático de apuntes de cursos según el SOP oficial del Vault de Obsidian."""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta
from aulento.db.repository import CursoRepository, PlataformaRepository
from aulento.vault.rutas import (
    exigir_nombre_de_nota,
    resolver_en_vault,
    vault_de_la_cuenta,
    vault_de_la_cuenta_con_conexion_propia,
)


class CourseNoteRequest(BaseModel):
    """Parámetros para la creación de una nota de apunte de curso."""
    course_id: int = Field(..., description="ID del curso en la base de datos local")
    topic: str = Field(..., description="Tema central o título de la clase/módulo")
    tldr: Optional[str] = Field(None, description="Resumen ejecutivo corto (TL;DR)")
    key_concepts: Optional[List[str]] = Field(default_factory=list, description="Lista de conceptos para wikilinks")
    code_example: Optional[str] = Field(None, description="Fragmento de código, comandos SQL/Python o notas técnicas")
    mocs: Optional[List[str]] = Field(default_factory=list, description="MOCs de conexión")


def slugify(text: str) -> str:
    """Convierte texto en un slug seguro para nombres de archivo y tags."""
    clean = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", clean)


def sanitize_filename(name: str) -> str:
    """Elimina caracteres inválidos para el sistema de archivos y neutraliza path traversal."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    clean = re.sub(r"\.{2,}", "", clean)
    clean = clean.strip(". ")
    return clean or "unnamed_note"


class CourseNoteGenerator:
    """Construye apuntes estructurados de los cursos de una cuenta y los guarda en 04 Knowledge/Cursos/ de su vault."""

    def __init__(self, user_id: int, conn: Optional[sqlite3.Connection] = None, vault_path: Optional[Path] = None):
        self.user_id = exigir_cuenta(user_id)
        self._conn = conn
        self._vault_path = vault_path

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

    def generate_note_markdown(self, req: CourseNoteRequest) -> Dict[str, Any]:
        """Sintetiza el contenido Markdown estandarizado de acuerdo al SOP del Vault.

        Levanta `RutaFueraDelVaultError` si el tema, que da nombre a la nota, es en realidad una ruta.
        """
        exigir_nombre_de_nota(req.topic)
        conn = self._get_conn()
        try:
            curso_repo = CursoRepository(conn, self.user_id)
            plat_repo = PlataformaRepository(conn, self.user_id)

            course = curso_repo.get_by_id(req.course_id)
            if not course:
                raise ValueError(f"Curso con ID {req.course_id} no existe en la base de datos.")

            platform = plat_repo.get_by_id(course.plataforma_id)
            platform_name = platform.nombre if platform else "Academia Externa"
        finally:
            if not self._conn:
                conn.close()

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plat_slug = slugify(platform_name)
        topic_slug = slugify(req.topic)

        # Tags
        tags = ["curso", plat_slug, topic_slug]

        # Conceptos con wikilinks
        concepts_list = req.key_concepts or []
        if not concepts_list:
            concepts_text = (
                f"- [[{req.topic}]]: Concepto rector explorado en esta clase.\n"
                f"- [[Arquitectura y Buenas Prácticas]]: Implementación en entornos productivos."
            )
        else:
            concepts_text = "\n".join([f"- [[{c.strip()}]]" for c in concepts_list if c.strip()])

        # Código o notas técnicas
        code_section = req.code_example or (
            "```sql\n"
            "-- Ejemplo de consulta analítica o implementación práctica\n"
            "SELECT\n"
            "    date,\n"
            "    COUNT(DISTINCT user_id) AS active_users\n"
            "FROM `project.dataset.events`\n"
            "GROUP BY 1;\n"
            "```"
        )

        # MOCs
        mocs_list = req.mocs or ["02 MOCs/MOC Inteligencia Artificial y Datos.md"]
        mocs_text = "\n".join([f"- [[{m.strip().replace('.md', '')}]]" for m in mocs_list])

        # TL;DR
        tldr_text = req.tldr or f"Sesión enfocada en {req.topic} dentro del programa {course.nombre_curso}. Claves para la toma de decisiones y diseño técnico."

        content = (
            "---\n"
            "type: Curso\n"
            f"title: \"{req.topic}\"\n"
            f"curso: \"{course.nombre_curso}\"\n"
            f"plataforma: \"{platform_name}\"\n"
            f"fecha: \"{today_str}\"\n"
            f"tags: [{', '.join(tags)}]\n"
            f"sources: [\"{course.url_aula}\"]\n"
            "---\n\n"
            f"# {req.topic}\n\n"
            f"> **Curso:** [[{course.nombre_curso}]]  \n"
            f"> **Plataforma:** {platform_name}  \n"
            f"> **Fecha de Estudio:** {today_str}  \n"
            f"> **Aula Virtual:** [{course.nombre_curso}]({course.url_aula})\n\n"
            "## 1. Resumen Ejecutivo (TL;DR)\n"
            f"{tldr_text}\n\n"
            "## 2. Conceptos Clave & Wikilinks\n"
            f"{concepts_text}\n\n"
            "## 3. Notas Detalladas y Código / Arquitectura\n"
            f"{code_section}\n\n"
            "## 4. Preguntas de Active Recall (Feynman / FSRS)\n"
            f"- **¿Cuál es el problema principal que resuelve {req.topic}?**\n"
            f"  - *Respuesta:* Permite optimizar el rendimiento y escalabilidad en pipelines de datos y modelos analíticos.\n"
            f"- **¿Cuáles son los principales trade-offs a considerar?**\n"
            f"  - *Respuesta:* Latencia vs costo de cómputo, y complejidad de mantenimiento.\n\n"
            "## 5. Conexiones con MOCs\n"
            f"{mocs_text}\n"
        )

        safe_course_folder = sanitize_filename(course.nombre_curso)
        safe_topic_filename = f"{sanitize_filename(req.topic)}.md"
        relative_path = f"04 Knowledge/Cursos/{safe_course_folder}/{safe_topic_filename}"

        return {
            "title": req.topic,
            "course": course.nombre_curso,
            "platform": platform_name,
            "relative_path": relative_path,
            "content": content,
        }

    def save_note_to_vault(self, req: CourseNoteRequest) -> Path:
        """Genera y guarda físicamente la nota Markdown en el Vault de Obsidian."""
        data = self.generate_note_markdown(req)
        target_file = resolver_en_vault(self.vault_path, data["relative_path"])
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(data["content"], encoding="utf-8")
        return target_file
