"""Tests unitarios y de integración para Macro-FSRS y Micro-Quizzes Feynman."""

import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from conftest import cuenta_en
from aulento.db.schema import init_db
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import (
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    EstadoTema,
)
from aulento.roadmap.macro_fsrs import (
    MacroFSRSRepository,
    MacroFSRSEngine,
    calibrate_bloom_difficulty,
)
from aulento.web.app import create_app


@pytest.fixture
def macro_fsrs_db(tmp_path):
    db_file = tmp_path / "test_macro_fsrs.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.close()

    # Crear ruta con temas
    repo = RoadmapRepository(cuenta_en(str(db_file)), str(db_file))
    rm = repo.create_roadmap(RoadmapCreate(
        titulo="Ruta Data Architecture",
        descripcion="Arquitectura de Datos y BigQuery",
        nivel_objetivo="Senior",
        categoria="data_ai",
        modulos=[
            RoadmapModuleCreate(
                titulo="Módulo 1: Diseño",
                orden=1,
                temas=[
                    RoadmapTopicCreate(
                        titulo="Arquitectura y Optimización de BigQuery",
                        descripcion="Modelos de almacenamiento columnar y particionado",
                        orden=1,
                        estado=EstadoTema.PENDIENTE,
                    ),
                    RoadmapTopicCreate(
                        titulo="Introducción a SQL Básico",
                        descripcion="Sintaxis básica SELECT y WHERE",
                        orden=2,
                        estado=EstadoTema.PENDIENTE,
                    )
                ]
            )
        ]
    ))
    return db_file, rm.id


def test_bloom_difficulty_calibration():
    # Temas complejos
    diff_arch = calibrate_bloom_difficulty("Arquitectura de Sistemas Distribuidos", "Diseño y tuning")
    assert diff_arch >= 6.5

    # Temas introductorios
    diff_intro = calibrate_bloom_difficulty("Introducción a Python", "Fundamentos y sintaxis básica")
    assert diff_intro <= 4.0

    # Temas intermedios
    diff_etl = calibrate_bloom_difficulty("Pipeline ETL con Apache Beam", "Implementación práctica")
    assert 5.0 <= diff_etl <= 6.0


def test_macro_fsrs_topic_completion_hook(macro_fsrs_db):
    db_file, rm_id = macro_fsrs_db
    repo = RoadmapRepository(cuenta_en(str(db_file)), str(db_file))
    rm = repo.get_roadmap(rm_id)
    topic = rm.modulos[0].temas[0]

    # Al completar el tema, el hook reactivo inicializa su retención macro
    repo.update_topic_status(topic.id, EstadoTema.COMPLETADO)

    macro_repo = MacroFSRSRepository(cuenta_en(str(db_file)), db_path=str(db_file))
    retention = macro_repo.get_by_tema_id(topic.id)
    assert retention is not None
    assert retention.tema_id == topic.id
    assert retention.scheduled_days == 3
    assert retention.difficulty >= 6.5  # Porque el título tiene "Arquitectura y Optimización"


def test_macro_fsrs_review_lifecycle(macro_fsrs_db):
    db_file, rm_id = macro_fsrs_db
    repo = RoadmapRepository(cuenta_en(str(db_file)), str(db_file))
    rm = repo.get_roadmap(rm_id)
    topic = rm.modulos[0].temas[0]
    repo.update_topic_status(topic.id, EstadoTema.COMPLETADO)

    engine = MacroFSRSEngine(cuenta_en(str(db_file)), db_path=str(db_file))

    # 1. Repaso con Calificación 3 (GOOD)
    updated = engine.review_topic(tema_id=topic.id, rating=3, notas="Explicación clara de particionado")
    assert updated.reps == 1
    assert updated.lapses == 0
    assert updated.scheduled_days >= 4
    assert updated.stability > 2.0

    # 2. Repaso con Calificación 1 (AGAIN - Olvido)
    lapsed = engine.review_topic(tema_id=topic.id, rating=1, notas="Duda en los límites de clustering")
    assert lapsed.reps == 2
    assert lapsed.lapses == 1
    assert lapsed.scheduled_days == 1


def test_feynman_microquiz_generation(macro_fsrs_db):
    db_file, rm_id = macro_fsrs_db
    repo = RoadmapRepository(cuenta_en(str(db_file)), str(db_file))
    rm = repo.get_roadmap(rm_id)
    topic = rm.modulos[0].temas[0]

    engine = MacroFSRSEngine(cuenta_en(str(db_file)), db_path=str(db_file))
    quiz = engine.get_feynman_microquiz(topic.id)

    assert quiz.tema_id == topic.id
    assert "Arquitectura y Optimización" in quiz.tema_titulo
    assert "Active Recall" in quiz.pregunta_active_recall or "problema fundamental" in quiz.pregunta_active_recall
    assert "junior" in quiz.desafio_feynman
    assert len(quiz.puntos_clave_evaluacion) >= 3


def test_macro_fsrs_api_endpoints(macro_fsrs_db, monkeypatch):
    db_file, rm_id = macro_fsrs_db
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))

    repo = RoadmapRepository(cuenta_en(str(db_file)), str(db_file))
    rm = repo.get_roadmap(rm_id)
    topic = rm.modulos[0].temas[0]
    repo.update_topic_status(topic.id, EstadoTema.COMPLETADO)

    app = create_app()
    client = TestClient(app)

    # 1. Micro-quiz endpoint
    res_quiz = client.get(f"/api/macro-fsrs/quiz/{topic.id}")
    assert res_quiz.status_code == 200
    data_quiz = res_quiz.json()
    assert data_quiz["tema_id"] == topic.id

    # 2. Review endpoint
    res_rev = client.post(
        "/api/macro-fsrs/review",
        json={"tema_id": topic.id, "rating": 4, "notas": "Dominado con analogía de estantes"},
    )
    assert res_rev.status_code == 200
    data_rev = res_rev.json()
    assert data_rev["reps"] == 1
    assert data_rev["scheduled_days"] >= 7


def test_completar_un_tema_no_falla_si_el_repaso_macro_no_se_puede_inicializar(
    macro_fsrs_db, monkeypatch, caplog
):
    db_file, rm_id = macro_fsrs_db
    repo = RoadmapRepository(cuenta_en(str(db_file)), str(db_file))
    topic = repo.get_roadmap(rm_id).modulos[0].temas[0]

    def falla(self, tema_id):
        raise RuntimeError("sin retención")

    monkeypatch.setattr(MacroFSRSRepository, "init_topic_retention", falla)

    with caplog.at_level("WARNING"):
        repo.update_topic_status(topic.id, EstadoTema.COMPLETADO)

    assert repo.get_roadmap(rm_id).modulos[0].temas[0].estado == EstadoTema.COMPLETADO
    assert "sin retención" in caplog.text
