"""Pruebas del servicio y endpoints de Lectura Activa con IA y Cosecha FSRS (Feature 042)."""

import json
from unittest.mock import patch

import pytest

from aulento.core.book_active_recall import BookActiveRecallService
from aulento.core.ia.tipos import Respuesta
from aulento.db.connection import get_connection
from aulento.db.migrations import migrar
from aulento.db.repository import LibroRepository
from aulento.models.book_active_recall import (
    ActiveRecallEvaluateRequest,
    ActiveRecallGenerateRequest,
    BookHarvestCommitRequest,
    BookHarvestPreviewRequest,
    UserAnswerItem,
)
from aulento.models.libro import LibroCreate


@pytest.fixture
def conn():
    c = get_connection(":memory:")
    migrar(c)
    # Crear usuario de prueba
    c.execute(
        "INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, creado_en) "
        "VALUES (1, 'ana', 'hash', '2026-01-01');"
    )
    c.execute(
        "INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, creado_en) "
        "VALUES (2, 'beto', 'hash', '2026-01-01');"
    )
    c.commit()
    yield c
    c.close()


@pytest.fixture
def libro_ana(conn):
    repo = LibroRepository(conn, 1)
    return repo.create(
        LibroCreate(
            titulo="Designing Data-Intensive Applications",
            capitulo_actual=3,
            total_capitulos=12,
            pagina_actual=75,
            total_paginas=600,
        )
    )


def test_servicio_generar_preguntas(conn, libro_ana):
    service = BookActiveRecallService(conn, user_id=1)

    mock_resp = {
        "preguntas": [
            {
                "id": 1,
                "pregunta": "¿Qué diferencia fundamental existe entre B-Trees y LSM-Trees?",
                "objetivo_conceptual": "Comprender estructuras de almacenamiento e índices",
                "criterio_evaluacion": "Debe mencionar el costo de escrituras aleatorias vs secuenciales",
            },
            {
                "id": 2,
                "pregunta": "¿Por qué un commit log ayuda en la recuperación ante fallos?",
                "objetivo_conceptual": "Durabilidad y recuperación ante caídas",
                "criterio_evaluacion": "Debe mencionar WAL y secuencialidad",
            },
        ]
    }

    with patch.object(
        service.pasarela,
        "generar",
        return_value=Respuesta(
            texto=json.dumps(mock_resp),
            proveedor="gemini",
            modelo="gemini-1.5-flash",
            tokens_entrada=100,
            tokens_salida=50,
            costo_usd=0.001,
            latencia_ms=200,
        ),
    ):
        res = service.generar_preguntas(
            libro_ana.id,
            ActiveRecallGenerateRequest(cantidad=2),
        )

        assert res.book_id == libro_ana.id
        assert res.titulo == "Designing Data-Intensive Applications"
        assert len(res.preguntas) == 2
        assert "B-Trees" in res.preguntas[0].pregunta
        assert "Capítulo 3" in res.tramo_evaluado


def test_servicio_evaluar_respuestas(conn, libro_ana):
    service = BookActiveRecallService(conn, user_id=1)

    mock_eval = {
        "score_global": 90,
        "veredicto": "excelente",
        "resumen_pedagogico": "Excelente comprensión del capítulo sobre almacenamiento.",
        "evaluaciones": [
            {
                "question_id": 1,
                "puntaje": 90,
                "aciertos": "Explicaste claramente el costo de I/O aleatorio.",
                "mejoras": "Podrías citar SSTables como estructura inmutable.",
                "explicacion_optima": "LSM-Trees aprovechan escrituras secuenciales en disco...",
            }
        ],
    }

    with patch.object(
        service.pasarela,
        "generar",
        return_value=Respuesta(
            texto=json.dumps(mock_eval),
            proveedor="gemini",
            modelo="gemini-1.5-flash",
            tokens_entrada=120,
            tokens_salida=60,
            costo_usd=0.001,
            latencia_ms=250,
        ),
    ):
        res = service.evaluar_respuestas(
            libro_ana.id,
            ActiveRecallEvaluateRequest(
                tramo_evaluado="Capítulo 3",
                respuestas=[
                    UserAnswerItem(
                        question_id=1,
                        pregunta="¿Qué diferencia hay entre B-Trees y LSM-Trees?",
                        respuesta_usuario="LSM-Trees escriben secuencialmente mientras B-Trees modifican bloques en su lugar.",
                    )
                ],
            ),
        )

        assert res.score_global == 90
        assert res.veredicto == "excelente"
        assert len(res.evaluaciones) == 1
        assert res.evaluaciones[0].puntaje == 90

        # Verificar que se registró la sesión de estudio
        from aulento.db.focus_repository import FocusRepository
        sesiones = FocusRepository(conn, 1).list_sessions()
        assert len(sesiones) >= 1
        assert "Designing Data-Intensive Applications" in sesiones[0].notas


def test_servicio_cosecha_fsrs_preview_y_commit(conn, libro_ana):
    service = BookActiveRecallService(conn, user_id=1)

    mock_harvest = {
        "cards": [
            {
                "categoria": "ingles_tecnico",
                "item_pregunta": "Write Amplification",
                "respuesta_esperada": "Ratio de bytes escritos en disco respecto a los datos enviados.",
                "contexto_uso": "LSM-Trees balance write amplification against read performance.",
            },
            {
                "categoria": "ingles_tecnico",
                "item_pregunta": "Compaction",
                "respuesta_esperada": "Proceso de fusionar SSTables y descartar versiones obsoletas.",
                "contexto_uso": "Background compaction prevents segment accumulation.",
            },
        ]
    }

    with patch.object(
        service.pasarela,
        "generar",
        return_value=Respuesta(
            texto=json.dumps(mock_harvest),
            proveedor="gemini",
            modelo="gemini-1.5-flash",
            tokens_entrada=100,
            tokens_salida=50,
            costo_usd=0.001,
            latencia_ms=180,
        ),
    ):
        prev = service.previsualizar_cosecha(libro_ana.id, BookHarvestPreviewRequest(cantidad=2))
        assert len(prev.cards) == 2
        assert prev.cards[0].item_pregunta == "Write Amplification"

        # Commit de las tarjetas
        com = service.confirmar_cosecha(
            libro_ana.id,
            BookHarvestCommitRequest(cards=prev.cards),
        )
        assert com.guardadas == 2
        assert com.omitidas_duplicadas == 0

        # Re-commit con las mismas tarjetas debe omitir duplicados
        com2 = service.confirmar_cosecha(
            libro_ana.id,
            BookHarvestCommitRequest(cards=prev.cards),
        )
        assert com2.guardadas == 0
        assert com2.omitidas_duplicadas == 2


def test_libro_de_otra_cuenta_falla(conn, libro_ana):
    # Beto (user 2) no puede acceder al libro de Ana (user 1)
    service_beto = BookActiveRecallService(conn, user_id=2)
    with pytest.raises(ValueError, match="no encontrado en la cuenta"):
        service_beto.generar_preguntas(libro_ana.id)


from conftest import administrador_de_prueba
from fastapi.testclient import TestClient

from aulento.db.schema import init_db
from aulento.web.app import create_app


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "web_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    administrador_de_prueba(conn)
    conn.close()
    return db_file


@pytest.fixture
def client(test_db):
    app = create_app()
    return TestClient(app)


def test_endpoints_active_recall_y_harvest(test_db):
    app = create_app()
    client = TestClient(app)

    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id)
    libro = repo.create(
        LibroCreate(
            titulo="Clean Architecture",
            capitulo_actual=2,
            total_capitulos=8,
            pagina_actual=50,
            total_paginas=300,
        )
    )
    conn.close()

    mock_questions = {
        "preguntas": [
            {
                "id": 1,
                "pregunta": "¿Por qué las dependencias deben apuntar hacia adentro?",
                "objetivo_conceptual": "Dependency Inversion Principle",
                "criterio_evaluacion": "Mencionar desacoplamiento de frameworks",
            }
        ]
    }

    with patch(
        "aulento.core.ia.pasarela.PasarelaDeIA.generar",
        return_value=Respuesta(
            texto=json.dumps(mock_questions),
            proveedor="gemini",
            modelo="gemini-1.5-flash",
            tokens_entrada=80,
            tokens_salida=40,
        ),
    ):
        # 1. Generate Active Recall
        r_gen = client.post(f"/api/books/{libro.id}/active-recall/generate", json={"cantidad": 1})
        assert r_gen.status_code == 200, r_gen.text
        data_gen = r_gen.json()
        assert data_gen["book_id"] == libro.id
        assert len(data_gen["preguntas"]) == 1

    mock_eval = {
        "score_global": 95,
        "veredicto": "excelente",
        "resumen_pedagogico": "Dominio claro de la regla de dependencias.",
        "evaluaciones": [
            {
                "question_id": 1,
                "puntaje": 95,
                "aciertos": "Excelente explicación de inversión de dependencias.",
                "mejoras": "Ninguna.",
                "explicacion_optima": "Las políticas de alto nivel no deben depender de los detalles.",
            }
        ],
    }

    with patch(
        "aulento.core.ia.pasarela.PasarelaDeIA.generar",
        return_value=Respuesta(
            texto=json.dumps(mock_eval),
            proveedor="gemini",
            modelo="gemini-1.5-flash",
            tokens_entrada=90,
            tokens_salida=45,
        ),
    ):
        # 2. Evaluate Active Recall
        r_ev = client.post(
            f"/api/books/{libro.id}/active-recall/evaluate",
            json={
                "tramo_evaluado": "Capítulo 2",
                "respuestas": [
                    {
                        "question_id": 1,
                        "pregunta": "¿Por qué las dependencias deben apuntar hacia adentro?",
                        "respuesta_usuario": "Porque las reglas de negocio no deben depender de detalles como la base de datos o frameworks.",
                    }
                ],
            },
        )
        assert r_ev.status_code == 200, r_ev.text
        data_ev = r_ev.json()
        assert data_ev["score_global"] == 95
        assert data_ev["veredicto"] == "excelente"

    mock_cards = {
        "cards": [
            {
                "categoria": "ingles_tecnico",
                "item_pregunta": "Dependency Rule",
                "respuesta_esperada": "Source code dependencies must point only inward, toward higher-level policies.",
                "contexto_uso": "In Clean Architecture, nothing in an inner circle can know anything about an outer circle.",
            }
        ]
    }

    with patch(
        "aulento.core.ia.pasarela.PasarelaDeIA.generar",
        return_value=Respuesta(
            texto=json.dumps(mock_cards),
            proveedor="gemini",
            modelo="gemini-1.5-flash",
            tokens_entrada=85,
            tokens_salida=35,
        ),
    ):
        # 3. Harvest Preview
        r_prev = client.post(f"/api/books/{libro.id}/harvest/preview", json={"cantidad": 1})
        assert r_prev.status_code == 200, r_prev.text
        data_prev = r_prev.json()
        assert len(data_prev["cards"]) == 1

        # 4. Harvest Commit
        r_comm = client.post(
            f"/api/books/{libro.id}/harvest/commit",
            json={"cards": data_prev["cards"]},
        )
        assert r_comm.status_code == 200, r_comm.text
        data_comm = r_comm.json()
        assert data_comm["guardadas"] == 1
        assert data_comm["omitidas_duplicadas"] == 0


def test_endpoints_libro_inexistente_responde_404(client):
    r1 = client.post("/api/books/99999/active-recall/generate", json={})
    assert r1.status_code == 404

    r2 = client.post("/api/books/99999/active-recall/evaluate", json={"tramo_evaluado": "x", "respuestas": [{"question_id": 1, "pregunta": "pregunta", "respuesta_usuario": "respuesta valida"}]})
    assert r2.status_code == 404

    r3 = client.post("/api/books/99999/harvest/preview", json={})
    assert r3.status_code == 404

    r4 = client.post("/api/books/99999/harvest/commit", json={"cards": [{"categoria": "c", "item_pregunta": "p", "respuesta_esperada": "r"}]})
    assert r4.status_code == 404


from typer.testing import CliRunner

from aulento.cli.app import cli


def test_cli_books_quiz_y_harvest(test_db):
    runner = CliRunner()

    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id)
    libro = repo.create(
        LibroCreate(
            titulo="Designing Data-Intensive Applications",
            capitulo_actual=1,
            total_capitulos=10,
            pagina_actual=25,
            total_paginas=500,
        )
    )
    conn.close()

    mock_q = {
        "preguntas": [
            {
                "id": 1,
                "pregunta": "¿Qué es confiabilidad según el autor?",
                "objetivo_conceptual": "Reliability",
                "criterio_evaluacion": "Tolerancia a fallos vs fallas",
            }
        ]
    }
    mock_ev = {
        "score_global": 92,
        "veredicto": "excelente",
        "resumen_pedagogico": "Muy buen concepto.",
        "evaluaciones": [
            {
                "question_id": 1,
                "puntaje": 92,
                "aciertos": "Diferenciaste falla de fallo.",
                "mejoras": "Ninguna.",
                "explicacion_optima": "Confiabilidad es seguir funcionando correctamente ante fallas.",
            }
        ],
    }

    with patch(
        "aulento.core.ia.pasarela.PasarelaDeIA.generar",
        side_effect=[
            Respuesta(texto=json.dumps(mock_q), proveedor="gemini", modelo="gemini-1.5-flash"),
            Respuesta(texto=json.dumps(mock_ev), proveedor="gemini", modelo="gemini-1.5-flash"),
        ],
    ):
        result_quiz = runner.invoke(cli, ["books", "quiz", str(libro.id), "-n", "1"], input="El sistema tolera fallas de componentes sin colapsar\n")
        assert result_quiz.exit_code == 0
        assert "Confiabilidad" in result_quiz.output or "92%" in result_quiz.output

    mock_cards = {
        "cards": [
            {
                "categoria": "ingles_tecnico",
                "item_pregunta": "Fault Tolerance",
                "respuesta_esperada": "Capacidad de un sistema de seguir operando ante fallas de componentes.",
                "contexto_uso": "Fault-tolerant systems anticipate component failures.",
            }
        ]
    }

    with patch(
        "aulento.core.ia.pasarela.PasarelaDeIA.generar",
        return_value=Respuesta(texto=json.dumps(mock_cards), proveedor="gemini", modelo="gemini-1.5-flash"),
    ):
        result_harvest = runner.invoke(cli, ["books", "harvest", str(libro.id), "-n", "1", "--commit"])
        assert result_harvest.exit_code == 0
        assert "tarjetas añadidas al mazo FSRS" in result_harvest.output
