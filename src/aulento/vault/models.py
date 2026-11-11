"""Modelos de datos para el lector e indexador seguro del Vault de Obsidian."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WikiLink(BaseModel):
    """Representa un enlace de tipo [[Nota]] o [[Nota|Alias]] característico de Obsidian."""
    target: str = Field(..., description="Nombre del archivo o concepto de destino")
    alias: Optional[str] = Field(None, description="Texto visible o alias opcional")
    full_text: str = Field(..., description="Texto completo del enlace original")


class VaultNote(BaseModel):
    """Representa una nota indexada de solo lectura del Vault de Obsidian."""
    id: str = Field(..., description="Identificador único (slug o ruta relativa)")
    path: str = Field(..., description="Ruta del archivo relativa al vault de la cuenta, con barras `/`")
    folder: str = Field(..., description="Carpeta origen ('04 Knowledge', '06 Raw', '02 MOCs')")
    title: str = Field(..., description="Título de la nota (de frontmatter o nombre de archivo)")
    content: str = Field(..., description="Contenido completo en Markdown")
    clean_text: str = Field(..., description="Contenido limpio sin frontmatter YAML")
    frontmatter: Dict[str, Any] = Field(default_factory=dict, description="Metadatos YAML")
    tags: List[str] = Field(default_factory=list, description="Etiquetas de la nota (#tag)")
    wikilinks: List[WikiLink] = Field(default_factory=list, description="Enlaces a otras notas")
    headings: List[str] = Field(default_factory=list, description="Encabezados H1, H2, H3")
    summary: Optional[str] = Field(None, description="Resumen o síntesis corta del concepto")
