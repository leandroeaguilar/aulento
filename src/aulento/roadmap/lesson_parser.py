"""Parser de clases y apuntes Markdown externos con extracción de diagramas Mermaid y Flashcards FSRS."""

import re
from datetime import datetime, timezone
from typing import Any


class LessonParser:
    """Extrae metadatos, diagramas Mermaid y tarjetas de active recall a partir de texto Markdown."""

    @staticmethod
    def parse_markdown(markdown_text: str, default_title: str = "Clase Magistral") -> dict[str, Any]:
        """Procesa el contenido Markdown y extrae componentes estructurados."""
        text = markdown_text.strip()

        # 1. Extraer título principal (# Título)
        title = default_title
        # Los encabezados de las diapositivas (bloque ```slides) no son el título de la clase.
        sin_diapositivas = re.sub(r"```slides[\r\n]+.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)
        title_match = re.search(r"^#\s+(.+)$", sin_diapositivas, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        # 2. Extraer diagramas Mermaid
        mermaid_blocks = re.findall(r"```mermaid[\r\n]+(.*?)```", text, re.DOTALL | re.IGNORECASE)
        mermaid_diagrams = [b.strip() for b in mermaid_blocks if b.strip()]

        # 3. Extraer Flashcards de Active Recall
        flashcards: list[dict[str, str]] = []

        # Intentar bloque delimitado ```cards-fsrs ... ```
        fsrs_match = re.search(r"```cards-fsrs[\r\n]+(.*?)```", text, re.DOTALL | re.IGNORECASE)
        card_source = fsrs_match.group(1) if fsrs_match else text

        # Buscar pares Q: y A:
        # Formato: Q: pregunta \n A: respuesta
        pattern = re.compile(
            r"(?:^|\n)\s*(?:Q|Pregunta|P):\s*(.+?)\s*\n\s*(?:A|Respuesta|R):\s*(.+?)(?=(?:\n\s*(?:Q|Pregunta|P):)|\Z)",
            re.DOTALL | re.IGNORECASE,
        )
        for q_match in pattern.finditer(card_source):
            q_text = q_match.group(1).strip()
            a_text = q_match.group(2).strip()
            # Limpiar saltos de línea excesivos en la respuesta
            a_clean = " ".join(line.strip() for line in a_text.splitlines() if line.strip())
            if q_text and a_clean:
                flashcards.append({"pregunta": q_text, "respuesta": a_clean})

        return {
            "title": title,
            "markdown_content": text,
            "diagramas_mermaid": mermaid_diagrams,
            "flashcards": flashcards,
        }

    @staticmethod
    def build_vault_note_content(
        title: str,
        topic_title: str,
        module_title: str,
        roadmap_title: str,
        markdown_body: str,
        created_at: datetime | None = None,
    ) -> str:
        """Construye el contenido de la nota para el Vault de Obsidian respetando el frontmatter OKF v0.2."""
        dt = created_at or datetime.now(timezone.utc)
        iso_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        frontmatter = (
            f"---\n"
            f"type: ApunteCurso\n"
            f"title: \"{title}\"\n"
            f"description: \"Apunte canónico de la clase {topic_title} perteneciente a {roadmap_title}\"\n"
            f"roadmap: \"{roadmap_title}\"\n"
            f"module: \"{module_title}\"\n"
            f"topic: \"{topic_title}\"\n"
            f"generated:\n"
            f"  by: process:aulento\n"
            f"  at: {iso_date}\n"
            f"---\n\n"
        )
        return frontmatter + markdown_body
