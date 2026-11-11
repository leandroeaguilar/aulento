"""Pruebas unitarias de validación en modelos Pydantic."""

import pytest
from pydantic import ValidationError
from aulento.models.plataforma import PlataformaCreate
from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
from aulento.models.libro import LibroCreate, Libro, EstadoLibro
from aulento.models.horario import BloqueHorarioCreate, TipoBloque


def test_plataforma_valid():
    p = PlataformaCreate(nombre="Humai", url_acceso="https://humai.com.ar", icono_color="green")
    assert p.nombre == "Humai"
    assert p.url_acceso == "https://humai.com.ar"


def test_plataforma_invalid_url():
    with pytest.raises(ValidationError):
        PlataformaCreate(nombre="Humai", url_acceso="ftp://humai.com.ar")


def test_curso_valid():
    c = CursoCreate(
        plataforma_id=1,
        nombre_curso="Data Science Intensive",
        url_aula="https://digitalhouse.com/aula",
        progreso_pct=45.5,
        estado=EstadoCurso.EN_CURSO,
        prioridad=PrioridadCurso.ALTA,
    )
    assert c.progreso_pct == 45.5


def test_curso_invalid_progress():
    with pytest.raises(ValidationError):
        CursoCreate(
            plataforma_id=1,
            nombre_curso="Test",
            url_aula="https://example.com",
            progreso_pct=110.0,
        )


def test_libro_valid_and_percentage():
    l = Libro(id=1, titulo="AI Engineering", capitulo_actual=5, total_capitulos=10)
    assert l.porcentaje_leido == 50.0


def test_libro_invalid_chapters():
    with pytest.raises(ValidationError):
        LibroCreate(titulo="AI Engineering", capitulo_actual=12, total_capitulos=10)


def test_horario_valid():
    h = BloqueHorarioCreate(
        dia_semana=1,
        hora_inicio="10:30",
        hora_fin="12:30",
        tipo=TipoBloque.CURSO,
        descripcion="Bloque de estudio",
    )
    assert h.dia_semana == 1


def test_horario_invalid_order():
    with pytest.raises(ValidationError):
        BloqueHorarioCreate(
            dia_semana=1,
            hora_inicio="14:00",
            hora_fin="13:00",
            tipo=TipoBloque.CURSO,
            descripcion="Invalido",
        )


def test_horario_invalid_format():
    with pytest.raises(ValidationError):
        BloqueHorarioCreate(
            dia_semana=1,
            hora_inicio="25:99",
            hora_fin="26:00",
            tipo=TipoBloque.CURSO,
            descripcion="Invalido",
        )
