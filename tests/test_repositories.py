"""Pruebas de integración de repositorios de persistencia."""

import pytest
import sqlite3
from conftest import cuenta_de_prueba
from aulento.db.repository import (
    PlataformaRepository,
    CursoRepository,
    LibroRepository,
    BloqueHorarioRepository,
)
from aulento.models.plataforma import PlataformaCreate
from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
from aulento.models.libro import LibroCreate, EstadoLibro
from aulento.models.horario import BloqueHorarioCreate, TipoBloque


def test_plataforma_crud(memory_db):
    repo = PlataformaRepository(memory_db, cuenta_de_prueba(memory_db).id)
    # Create
    p = repo.create(PlataformaCreate(nombre="Test Plat", url_acceso="https://test.com", icono_color="red"))
    assert p.id > 0
    assert p.nombre == "Test Plat"

    # Get by ID
    p_get = repo.get_by_id(p.id)
    assert p_get is not None
    assert p_get.nombre == "Test Plat"

    # Get by Name
    p_name = repo.get_by_name("test plat")
    assert p_name is not None
    assert p_name.id == p.id

    # List all
    all_plats = repo.list_all()
    assert len(all_plats) == 1

    # Delete
    assert repo.delete(p.id) is True
    assert repo.get_by_id(p.id) is None


def test_curso_crud_and_cascade(seeded_memory_db):
    plat_repo = PlataformaRepository(seeded_memory_db, cuenta_de_prueba(seeded_memory_db).id)
    curso_repo = CursoRepository(seeded_memory_db, cuenta_de_prueba(seeded_memory_db).id)

    # Plataforma existente (Digital House)
    dh = plat_repo.get_by_name("Digital House")
    assert dh is not None

    curso = curso_repo.create(
        CursoCreate(
            plataforma_id=dh.id,
            nombre_curso="Data Science Intensive",
            url_aula="https://digitalhouse.com/aula/ds",
            progreso_pct=25.0,
            estado=EstadoCurso.EN_CURSO,
            prioridad=PrioridadCurso.ALTA,
        )
    )
    assert curso.id > 0
    assert curso.nombre_plataforma == "Digital House"

    # Update progress
    updated = curso_repo.update_progress(curso.id, 100.0)
    assert updated.progreso_pct == 100.0
    assert updated.estado == EstadoCurso.COMPLETADO

    # Delete platform cascades to courses
    plat_repo.delete(dh.id)
    assert curso_repo.get_by_id(curso.id) is None


def test_libro_crud_and_advance(memory_db):
    repo = LibroRepository(memory_db, cuenta_de_prueba(memory_db).id)
    libro = repo.create(
        LibroCreate(
            titulo="AI Engineering",
            capitulo_actual=1,
            total_capitulos=10,
            ruta_vault="06 Raw/Libros/ai_engineering.pdf",
        )
    )
    assert libro.id > 0
    assert libro.porcentaje_leido == 10.0

    # Advance chapter
    adv = repo.advance_chapter(libro.id, 2)
    assert adv.capitulo_actual == 3
    assert adv.porcentaje_leido == 30.0
    assert adv.estado == EstadoLibro.LEYENDO

    # Advance to end
    final = repo.advance_chapter(libro.id, 10)
    assert final.capitulo_actual == 10
    assert final.porcentaje_leido == 100.0
    assert final.estado == EstadoLibro.COMPLETADO


def test_bloques_horarios_crud(memory_db):
    repo = BloqueHorarioRepository(memory_db, cuenta_de_prueba(memory_db).id)
    bloque = repo.create(
        BloqueHorarioCreate(
            dia_semana=1,
            hora_inicio="10:30",
            hora_fin="12:30",
            tipo=TipoBloque.CURSO,
            descripcion="Machine Learning Cursada",
            url_acceso="https://meet.google.com/xyz",
        )
    )
    assert bloque.id > 0

    bloques_lunes = repo.list_all(dia_semana=1)
    assert len(bloques_lunes) == 1
    assert bloques_lunes[0].descripcion == "Machine Learning Cursada"

    bloques_martes = repo.list_all(dia_semana=2)
    assert len(bloques_martes) == 0
