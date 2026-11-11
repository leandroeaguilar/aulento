"""Módulo de modelos de dominio de Aulento."""

from aulento.models.plataforma import (
    Plataforma,
    PlataformaCreate,
    PlataformaUpdate,
)
from aulento.models.curso import (
    Curso,
    CursoCreate,
    CursoUpdate,
    EstadoCurso,
    PrioridadCurso,
)
from aulento.models.libro import (
    Libro,
    LibroCreate,
    LibroUpdate,
    EstadoLibro,
)
from aulento.models.horario import (
    BloqueHorario,
    BloqueHorarioCreate,
    TipoBloque,
)
from aulento.models.roadmap import (
    Roadmap,
    RoadmapCreate,
    RoadmapDetail,
    RoadmapModule,
    RoadmapTopic,
    RoadmapLesson,
    EstadoTema,
    FuenteTema,
    OrigenClase,
)

__all__ = [
    "Plataforma",
    "PlataformaCreate",
    "PlataformaUpdate",
    "Curso",
    "CursoCreate",
    "CursoUpdate",
    "EstadoCurso",
    "PrioridadCurso",
    "Libro",
    "LibroCreate",
    "LibroUpdate",
    "EstadoLibro",
    "BloqueHorario",
    "BloqueHorarioCreate",
    "TipoBloque",
    "Roadmap",
    "RoadmapCreate",
    "RoadmapDetail",
    "RoadmapModule",
    "RoadmapTopic",
    "RoadmapLesson",
    "EstadoTema",
    "FuenteTema",
    "OrigenClase",
]
