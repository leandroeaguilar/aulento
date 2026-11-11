"""Módulo de conexión e indexación de notas del Vault de Obsidian."""

from aulento.vault.models import VaultNote, WikiLink
from aulento.vault.parser import parse_note
from aulento.vault.reader import VaultReader
from aulento.vault.cloud_notes import MaterialNoteGenerator, MaterialNoteRequest
from aulento.vault.sop_course import CourseNoteGenerator, CourseNoteRequest
from aulento.vault.weekly_digest import WeeklyDigestExporter

__all__ = [
    "VaultNote",
    "WikiLink",
    "VaultReader",
    "parse_note",
    "CourseNoteGenerator",
    "CourseNoteRequest",
    "MaterialNoteGenerator",
    "MaterialNoteRequest",
    "WeeklyDigestExporter",
]

