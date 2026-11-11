"""Parser seguro y sin dependencias externas para notas de Obsidian en Markdown."""

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from aulento.vault.models import VaultNote, WikiLink


def parse_simple_yaml(yaml_str: str) -> Dict[str, Any]:
    """Parsea frontmatter YAML común de Obsidian sin requerir dependencias de terceros."""
    data: Dict[str, Any] = {}
    current_list_key = None

    for line in yaml_str.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue

        # Si es un item de lista de una clave anterior
        if trimmed.startswith("- ") and current_list_key:
            item_val = trimmed[2:].strip().strip("\"'")
            if isinstance(data.get(current_list_key), list):
                data[current_list_key].append(item_val)
            continue

        # Par clave: valor
        if ":" in trimmed:
            key, val = trimmed.split(":", 1)
            key = key.strip()
            val = val.strip()

            if not val:
                # Comienza una lista indentada
                current_list_key = key
                data[key] = []
                continue

            current_list_key = None

            # Lista en formato [a, b, c]
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                if not inner:
                    data[key] = []
                else:
                    data[key] = [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
            elif val.lower() in ("true", "yes"):
                data[key] = True
            elif val.lower() in ("false", "no"):
                data[key] = False
            elif val.isdigit():
                data[key] = int(val)
            else:
                data[key] = val.strip("\"'")

    return data


def extract_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Extrae el frontmatter YAML delimitado por '---' y retorna (metadatos, texto_limpio)."""
    stripped = content.strip()
    if not stripped.startswith("---"):
        return {}, content

    parts = stripped.split("---", 2)
    if len(parts) >= 3:
        yaml_text = parts[1]
        body = parts[2].lstrip("\r\n")
        return parse_simple_yaml(yaml_text), body

    return {}, content


def extract_wikilinks(text: str) -> List[WikiLink]:
    """Extrae enlaces tipo [[Destino]] y [[Destino|Alias]] estándar de Obsidian."""
    pattern = r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"
    matches = re.finditer(pattern, text)
    links: List[WikiLink] = []

    for m in matches:
        target = m.group(1).strip()
        alias = m.group(2).strip() if m.group(2) else None
        links.append(
            WikiLink(
                target=target,
                alias=alias,
                full_text=m.group(0),
            )
        )
    return links


def extract_tags(text: str, frontmatter: Dict[str, Any]) -> List[str]:
    """Extrae tags tanto del texto (#tag) como del frontmatter."""
    tags_set = set()

    # Del frontmatter
    fm_tags = frontmatter.get("tags", [])
    if isinstance(fm_tags, list):
        for t in fm_tags:
            t_clean = str(t).lstrip("#").strip()
            if t_clean:
                tags_set.add(t_clean)
    elif isinstance(fm_tags, str):
        for t in fm_tags.split(","):
            t_clean = t.lstrip("#").strip()
            if t_clean:
                tags_set.add(t_clean)

    # Del cuerpo de texto
    pattern = r"(?:^|\s)#([a-zA-Z0-9_\-/]+)"
    for m in re.finditer(pattern, text):
        tag_val = m.group(1).strip()
        # Ignorar si es un encabezado markdown '# '
        if tag_val and not tag_val.startswith(" "):
            tags_set.add(tag_val)

    return sorted(list(tags_set))


def extract_headings(text: str) -> List[str]:
    """Extrae encabezados Markdown (# Encabezado, ## Subencabezado)."""
    headings: List[str] = []
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if m:
            headings.append(m.group(2).strip())
    return headings


def parse_note(file_path: Path, relative_to: Path | None = None) -> VaultNote:
    """Lee y parsea un archivo Markdown transformándolo en un VaultNote indexado."""
    raw_content = file_path.read_text(encoding="utf-8", errors="replace")
    fm, clean_text = extract_frontmatter(raw_content)
    wikilinks = extract_wikilinks(clean_text)
    tags = extract_tags(clean_text, fm)
    headings = extract_headings(clean_text)

    # Título: desde frontmatter o primer heading o nombre del archivo
    title = fm.get("title")
    if not title and headings:
        title = headings[0]
    if not title:
        title = file_path.stem

    # Carpeta contenedora y ruta dentro del vault: de la nota no se informa dónde está el vault en el disco
    folder = file_path.parent.name
    note_path = file_path.name
    note_id = file_path.stem
    if relative_to:
        try:
            rel = file_path.relative_to(relative_to)
            folder = rel.parts[0] if len(rel.parts) > 1 else "Root"
            note_id = str(rel.with_suffix("")).replace("\\", "/")
            note_path = rel.as_posix()
        except ValueError:
            pass

    # Generar un resumen a partir de las primeras oraciones del texto limpio
    clean_lines = [line.strip() for line in clean_text.splitlines() if line.strip() and not line.strip().startswith("#")]
    summary = clean_lines[0] if clean_lines else "Nota sin contenido de texto descriptivo."

    return VaultNote(
        id=note_id,
        path=note_path,
        folder=folder,
        title=str(title),
        content=raw_content,
        clean_text=clean_text,
        frontmatter=fm,
        tags=tags,
        wikilinks=wikilinks,
        headings=headings,
        summary=summary[:280],
    )
