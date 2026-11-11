"""Pruebas unitarias e integrales para el generador de apuntes SOP y exportador Weekly Digest."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba, vault_de_prueba
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
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
from aulento.vault.sop_course import CourseNoteGenerator, CourseNoteRequest
from aulento.vault.weekly_digest import WeeklyDigestExporter
from aulento.web.app import create_app
from aulento.cli.app import cli

runner = CliRunner()


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    """Configura base de datos y vault aislados para pruebas."""
    db_file = tmp_path / "sop_test.db"

    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))

    conn = get_connection(db_file)
    init_db(conn)
    vault_dir = vault_de_prueba(db_file)

    # Crear curso de prueba
    curso_repo = CursoRepository(conn, administrador_de_prueba(conn).id)
    course = curso_repo.create(
        CursoCreate(
            plataforma_id=1,  # Digital House
            nombre_curso="Data Engineering Specialist",
            url_aula="https://campus.digitalhouse.com/data-eng",
            progreso_pct=40.0,
            prioridad=PrioridadCurso.ALTA,
            estado=EstadoCurso.EN_CURSO,
        )
    )

    # Crear libro de prueba
    libro_repo = LibroRepository(conn, administrador_de_prueba(conn).id)
    libro_repo.create(
        LibroCreate(
            titulo="Designing Data-Intensive Applications",
            autor="Martin Kleppmann",
            total_capitulos=12,
            capitulo_actual=5,
            estado=EstadoLibro.LEYENDO,
        )
    )

    # Crear bloque de horario
    bloque_repo = BloqueHorarioRepository(conn, administrador_de_prueba(conn).id)
    bloque_repo.create(
        BloqueHorarioCreate(
            dia_semana=1,
            hora_inicio="09:00",
            hora_fin="10:30",
            tipo=TipoBloque.CURSO,
            descripcion="Clase de Data Engineering",
        )
    )

    conn.close()
    return {"db_file": db_file, "vault_dir": vault_dir, "course_id": course.id}


# --- 1. PRUEBAS DE CourseNoteGenerator ---

def test_course_note_generator_markdown_structure(test_env):
    conn = get_connection(test_env["db_file"])
    generator = CourseNoteGenerator(administrador_de_prueba(conn).id, conn=conn, vault_path=test_env["vault_dir"])

    req = CourseNoteRequest(
        course_id=test_env["course_id"],
        topic="Particionado y Clustering en BigQuery",
        tldr="Técnicas avanzadas para minimizar costos y latencia de escaneo de slots.",
        key_concepts=["BigQuery", "Particionado", "Slot Contention"],
        code_example="SELECT * FROM `orders` WHERE order_date >= '2026-01-01';",
    )

    data = generator.generate_note_markdown(req)
    conn.close()

    assert data["title"] == "Particionado y Clustering en BigQuery"
    assert data["course"] == "Data Engineering Specialist"
    assert "Digital House" in data["platform"]
    assert "04 Knowledge/Cursos/Data Engineering Specialist/Particionado y Clustering en BigQuery.md" in data["relative_path"]

    content = data["content"]
    # Frontmatter
    assert "type: Curso" in content
    assert 'title: "Particionado y Clustering en BigQuery"' in content
    assert 'curso: "Data Engineering Specialist"' in content
    assert "tags: [curso, digital-house, particionado-y-clustering-en-bigquery]" in content

    # 5 Secciones SOP
    assert "## 1. Resumen Ejecutivo (TL;DR)" in content
    assert "Técnicas avanzadas para minimizar costos y latencia" in content
    assert "## 2. Conceptos Clave & Wikilinks" in content
    assert "- [[BigQuery]]" in content
    assert "- [[Particionado]]" in content
    assert "- [[Slot Contention]]" in content
    assert "## 3. Notas Detalladas y Código / Arquitectura" in content
    assert "SELECT * FROM `orders`" in content
    assert "## 4. Preguntas de Active Recall (Feynman / FSRS)" in content
    assert "## 5. Conexiones con MOCs" in content
    assert "- [[02 MOCs/MOC Inteligencia Artificial y Datos]]" in content


def test_course_note_generator_save_to_vault(test_env):
    conn = get_connection(test_env["db_file"])
    generator = CourseNoteGenerator(administrador_de_prueba(conn).id, conn=conn, vault_path=test_env["vault_dir"])

    req = CourseNoteRequest(
        course_id=test_env["course_id"],
        topic="Optimizacion de Pipelines",
    )

    saved_file = generator.save_note_to_vault(req)
    conn.close()

    assert saved_file.exists()
    assert saved_file.is_file()
    assert "04 Knowledge" in str(saved_file)
    assert saved_file.name == "Optimizacion de Pipelines.md"

    content = saved_file.read_text(encoding="utf-8")
    assert "# Optimizacion de Pipelines" in content
    assert "type: Curso" in content


def test_course_note_generator_invalid_course(test_env):
    conn = get_connection(test_env["db_file"])
    generator = CourseNoteGenerator(administrador_de_prueba(conn).id, conn=conn, vault_path=test_env["vault_dir"])

    req = CourseNoteRequest(course_id=99999, topic="Tema Inexistente")
    with pytest.raises(ValueError, match="no existe"):
        generator.generate_note_markdown(req)
    conn.close()


# --- 2. PRUEBAS DE WeeklyDigestExporter ---

def test_weekly_digest_exporter_build(test_env):
    conn = get_connection(test_env["db_file"])
    exporter = WeeklyDigestExporter(administrador_de_prueba(conn).id, conn=conn, vault_path=test_env["vault_dir"])

    digest = exporter.build_digest(week_label="2026-W39")
    conn.close()

    assert digest["week_label"] == "2026-W39"
    assert digest["relative_path"] == "02 MOCs/Weekly-Digest-2026-W39.md"
    assert digest["metrics"]["courses_count"] >= 1
    assert digest["metrics"]["books_count"] >= 1

    content = digest["content"]
    assert "type: WeeklyDigest" in content
    assert 'semana: "2026-W39"' in content
    assert "# 📊 Weekly Study Digest — 2026-W39" in content
    assert "## 🧠 1. Memoria Espaciada e Inglés Técnico (FSRS v5)" in content
    assert "## 🏛 2. Progreso de Cursos Académicos" in content
    assert "Data Engineering Specialist" in content
    assert "## 📖 3. Reading Tracker de Libros Técnicos" in content
    assert "Designing Data-Intensive Applications" in content
    assert "## 🗓 4. Compromisos de la Agenda de Estudio" in content
    assert "Clase de Data Engineering" in content
    assert "## ⏱️ 5. Horas Reales Estudiadas (Focus & Pomodoro)" in content
    assert "## 🎯 6. Foco y Compromisos para la Próxima Semana" in content


def test_weekly_digest_exporter_save_to_vault(test_env):
    conn = get_connection(test_env["db_file"])
    exporter = WeeklyDigestExporter(administrador_de_prueba(conn).id, conn=conn, vault_path=test_env["vault_dir"])

    saved_file = exporter.save_digest_to_vault(week_label="2026-W40")
    conn.close()

    assert saved_file.exists()
    assert saved_file.is_file()
    assert "02 MOCs" in str(saved_file)
    assert saved_file.name == "Weekly-Digest-2026-W40.md"

    text = saved_file.read_text(encoding="utf-8")
    assert "Weekly Study Digest — 2026-W40" in text


# --- 3. PRUEBAS DE ENDPOINTS REST API ---

def test_api_course_template_preview_and_save(test_env):
    app = create_app()
    client = TestClient(app)

    payload = {
        "course_id": test_env["course_id"],
        "topic": "Arquitectura Kappa y Lambda",
        "tldr": "Comparativa de streaming y batch processing.",
        "key_concepts": ["Kafka", "Flink", "Speed Layer"],
    }

    # 1. Preview
    res_prev = client.post("/api/vault/notes/course-template", json=payload)
    assert res_prev.status_code == 200
    data_prev = res_prev.json()
    assert data_prev["title"] == "Arquitectura Kappa y Lambda"
    assert "04 Knowledge/Cursos" in data_prev["relative_path"]
    assert "saved_path" not in data_prev or data_prev["saved_path"] is None

    # 2. Save directly
    res_save = client.post("/api/vault/notes/course-template?save_to_vault=true", json=payload)
    assert res_save.status_code == 200
    data_save = res_save.json()
    assert not Path(data_save["saved_path"]).is_absolute()
    assert (vault_de_prueba() / data_save["saved_path"]).exists()

    # 3. Invalid course id
    res_err = client.post("/api/vault/notes/course-template", json={"course_id": 9999, "topic": "Err"})
    assert res_err.status_code == 404


def test_api_weekly_digest_endpoints(test_env):
    app = create_app()
    client = TestClient(app)

    # 1. Get weekly digest preview
    res = client.get("/api/vault/digest/weekly?week_label=2026-W39")
    assert res.status_code == 200
    data = res.json()
    assert data["week_label"] == "2026-W39"
    assert "Weekly Study Digest" in data["content"]

    # 2. Save weekly digest
    res_save = client.post("/api/vault/digest/weekly/save?week_label=2026-W39")
    assert res_save.status_code == 200
    data_save = res_save.json()
    assert not Path(data_save["saved_path"]).is_absolute()
    assert (vault_de_prueba() / data_save["saved_path"]).exists()


# --- 4. PRUEBAS DE COMANDOS CLI ---

def test_cli_vault_note_template(test_env):
    course_id = str(test_env["course_id"])

    # Preview
    res_prev = runner.invoke(
        cli,
        ["vault", "note-template", course_id, "Data Pipelines con Dagster", "--concepts", "Dagster, Asset Materialization"],
    )
    assert res_prev.exit_code == 0
    assert "Plantilla SOP: Data Pipelines con Dagster" in res_prev.stdout

    # Save to vault
    res_save = runner.invoke(
        cli,
        ["vault", "note-template", course_id, "Data Pipelines con Dagster", "--save"],
    )
    assert res_save.exit_code == 0
    assert "Apunte SOP creado y guardado en:" in res_save.stdout


def test_cli_vault_export_weekly(test_env):
    # Preview
    res_prev = runner.invoke(cli, ["vault", "export-weekly", "--week", "2026-W39"])
    assert res_prev.exit_code == 0
    assert "Weekly Digest — 2026-W39" in res_prev.stdout

    # Save
    res_save = runner.invoke(cli, ["vault", "export-weekly", "--week", "2026-W39", "--save-vault"])
    assert res_save.exit_code == 0
    assert "Weekly Digest exportado y guardado en:" in res_save.stdout
