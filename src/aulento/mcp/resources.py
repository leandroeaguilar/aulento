"""Recursos URI MCP que los clientes pueden suscribir o leer directamente."""

import json
from pathlib import Path
from typing import Any

from aulento.db.connection import get_connection
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.db.repository import CursoRepository, LibroRepository, BloqueHorarioRepository
from aulento.mcp.security import cuenta_mcp_actual
from aulento.models.libro import EstadoLibro


def register_mcp_resources(server: Any, db_path: Path | str | None = None) -> None:
    """Registra recursos URIs study:// en el servidor MCP."""

    @server.resource("study://roadmaps/active", name="Active Roadmaps", mime_type="application/json")
    def resource_active_roadmaps() -> str:
        """Información y progreso de las rutas de aprendizaje activas."""
        repo = RoadmapRepository(cuenta_mcp_actual(), db_path)
        roadmaps = repo.get_roadmaps()
        data = [
            {
                "id": r.id,
                "titulo": r.titulo,
                "progreso_pct": r.progreso_pct,
                "nivel": r.nivel_objetivo,
                "enfoque": getattr(r, "enfoque_estudio", "profesional"),
            }
            for r in roadmaps
        ]
        return json.dumps(data, indent=2, ensure_ascii=False)

    @server.resource("study://courses/list", name="Courses Catalog", mime_type="application/json")
    def resource_courses() -> str:
        """Catálogo de cursos del hub con enlaces a sus aulas virtuales."""
        conn = get_connection(db_path)
        try:
            repo = CursoRepository(conn, cuenta_mcp_actual())
            courses = repo.list_all()
            data = [
                {
                    "id": c.id,
                    "curso": c.nombre_curso,
                    "plataforma": c.nombre_plataforma,
                    "url_aula": c.url_aula,
                    "progreso_pct": c.progreso_pct,
                    "estado": c.estado.value,
                }
                for c in courses
            ]
            return json.dumps(data, indent=2, ensure_ascii=False)
        finally:
            conn.close()

    @server.resource("study://books/reading", name="Books in Progress", mime_type="application/json")
    def resource_books_reading() -> str:
        """Libros técnicos en lectura con páginas y capítulos actuales."""
        conn = get_connection(db_path)
        try:
            repo = LibroRepository(conn, cuenta_mcp_actual())
            books = repo.list_all(estado=EstadoLibro.LEYENDO)
            data = [
                {
                    "id": b.id,
                    "titulo": b.titulo,
                    "pagina_actual": b.pagina_actual,
                    "total_paginas": b.total_paginas,
                    "capitulo_actual": b.capitulo_actual,
                    "total_capitulos": b.total_capitulos,
                    "porcentaje_leido": b.porcentaje_leido,
                    "vault": b.ruta_vault,
                }
                for b in books
            ]
            return json.dumps(data, indent=2, ensure_ascii=False)
        finally:
            conn.close()
