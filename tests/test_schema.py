"""Pruebas del esquema relacional y semillado inicial."""

import sqlite3
import pytest
from conftest import cuenta_de_prueba
from aulento.db.schema import create_schema, seed_plataformas, init_db, PLATAFORMAS_SEMILLA


def test_schema_tables_exist(memory_db):
    """Verifica que las 4 tablas relacionales principales existan."""
    cursor = memory_db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row["name"] for row in cursor.fetchall()}
    assert "plataformas" in tables
    assert "cursos_externos" in tables
    assert "libros_lectura" in tables
    assert "bloques_horarios" in tables


def test_seed_plataformas_idempotent(memory_db):
    """Verifica que sembrar plataformas dos veces sea idempotente y mantenga las 5 plataformas."""
    cursor = memory_db.cursor()
    cursor.execute("SELECT count(*) as cnt FROM plataformas;")
    assert cursor.fetchone()["cnt"] == 0

    seed_plataformas(memory_db, cuenta_de_prueba(memory_db).id)
    cursor.execute("SELECT count(*) as cnt FROM plataformas;")
    assert cursor.fetchone()["cnt"] == len(PLATAFORMAS_SEMILLA)

    # Segunda siembra (no debe duplicar ni lanzar IntegrityError)
    seed_plataformas(memory_db, cuenta_de_prueba(memory_db).id)
    cursor.execute("SELECT count(*) as cnt FROM plataformas;")
    assert cursor.fetchone()["cnt"] == len(PLATAFORMAS_SEMILLA)


def test_foreign_key_constraint_blocks_orphan_courses(memory_db):
    """Verifica que no se pueda insertar un curso con plataforma_id inexistente."""
    cursor = memory_db.cursor()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO cursos_externos (plataforma_id, nombre_curso, url_aula, progreso_pct)
            VALUES (9999, 'Curso Fantasma', 'https://example.com', 10.0);
            """
        )


def test_progress_check_constraint(seeded_memory_db):
    """Verifica que progreso_pct deba estar en el rango [0.0, 100.0]."""
    cursor = seeded_memory_db.cursor()
    cursor.execute("SELECT id FROM plataformas LIMIT 1;")
    plat_id = cursor.fetchone()["id"]

    # Menor a 0 -> error
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO cursos_externos (plataforma_id, nombre_curso, url_aula, progreso_pct)
            VALUES (?, 'Curso Invalido', 'https://example.com', -5.0);
            """,
            (plat_id,),
        )

    # Mayor a 100 -> error
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO cursos_externos (plataforma_id, nombre_curso, url_aula, progreso_pct)
            VALUES (?, 'Curso Invalido', 'https://example.com', 105.0);
            """,
            (plat_id,),
        )


def test_books_chapter_check_constraint(memory_db):
    """Verifica que capitulo_actual no supere total_capitulos."""
    cursor = memory_db.cursor()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            """
            INSERT INTO libros_lectura (titulo, capitulo_actual, total_capitulos)
            VALUES ('AI Engineering', 15, 10);
            """
        )
