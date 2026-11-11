"""Pruebas unitarias e integrales para generador de exámenes, evaluador Feynman, API y CLI."""

import pytest
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from conftest import vault_de_prueba
from aulento.vault.reader import VaultReader, sembrar_notas_de_muestra
from aulento.exams.generator import ExamGenerator
from aulento.exams.feynman import FeynmanEvaluator
from aulento.exams.models import FeynmanSubmission, QuestionType
from aulento.web.app import app
from aulento.cli.app import cli

runner = CliRunner()
client = TestClient(app)


@pytest.fixture
def temp_vault_dir():
    """Vault de la cuenta de prueba, con las notas de muestra ya copiadas."""
    vault = vault_de_prueba()
    sembrar_notas_de_muestra(vault)
    return vault


def test_exam_generator(temp_vault_dir):
    """Verifica que el generador cree preguntas válidas para los diferentes tipos."""
    reader = VaultReader(temp_vault_dir)
    generator = ExamGenerator(reader)

    note = reader.get_note("Star Schema y Modelado Dimensional")
    assert note is not None

    exam = generator.generate_exam_for_note(note, count=3)
    assert exam.total_questions == 3
    assert len(exam.questions) == 3

    # Verificar preguntas
    q_types = [q.question_type for q in exam.questions]
    assert QuestionType.MULTIPLE_CHOICE in q_types
    assert QuestionType.CLOZE in q_types
    assert QuestionType.OPEN_REASONING in q_types

    mc_q = [q for q in exam.questions if q.question_type == QuestionType.MULTIPLE_CHOICE][0]
    assert len(mc_q.options) == 4
    assert mc_q.correct_answer in mc_q.options
    assert len(mc_q.explanation) > 10


def test_feynman_evaluator_short_input(temp_vault_dir):
    evaluator = FeynmanEvaluator(VaultReader(temp_vault_dir))
    res = evaluator.evaluate(FeynmanSubmission(concept="SQL", explanation="Es una base"))
    assert res.score < 30
    assert res.mastery_level == "Principiante"
    assert len(res.knowledge_gaps) > 0


def test_feynman_sin_ia_no_premia_una_analogia_vacia(temp_vault_dir):
    """060 R5: sin IA, «imagina» más 30 palabras genéricas no da un puntaje alto (antes daba ~77/100)."""
    evaluator = FeynmanEvaluator(VaultReader(temp_vault_dir))
    relleno = "Imagina que esto funciona de una forma muy simple y que cualquiera lo puede entender si presta "         "atención a lo que pasa todos los días en la casa con las cosas comunes que usamos siempre."
    for concepto in ("Star Schema", "Un concepto sin nota"):
        res = evaluator.evaluate(FeynmanSubmission(concept=concepto, explanation=relleno))
        assert res.sin_ia is True and res.rotulo == "sin IA"
        assert res.score < 50 and res.mastery_level == "Principiante", (concepto, res.score)
    sin_nota = evaluator.evaluate(FeynmanSubmission(concept="Un concepto sin nota", explanation=relleno))
    assert any("no se puede medir la precisión" in g for g in sin_nota.knowledge_gaps)


def test_feynman_sin_ia_premia_usar_la_nota_y_senala_terminos_sin_explicar(temp_vault_dir):
    """060 R5: sube si usa términos de la nota, y señala los términos de la nota usados sin explicar."""
    evaluator = FeynmanEvaluator(VaultReader(temp_vault_dir))
    sin_aclarar = (
        "El Star Schema guarda las métricas en las tablas de hechos. Las dimensiones están desnormalizadas. "
        "Las claves artificiales desacoplan el almacén analítico. Es como un ticket de supermercado."
    )
    aclarado = (
        "El Star Schema guarda las métricas (los números del negocio) en las tablas de hechos. Las dimensiones "
        "están desnormalizadas, es decir, repiten datos para leer más rápido. Es como un ticket de supermercado."
    )
    relleno = "Imagina que esto funciona de una forma muy simple y que cualquiera lo puede entender."
    puntaje_relleno = evaluator.evaluate(FeynmanSubmission(concept="Star Schema", explanation=relleno)).score
    res = evaluator.evaluate(FeynmanSubmission(concept="Star Schema", explanation=sin_aclarar))
    assert res.score > puntaje_relleno
    assert "desnormalizadas" in res.jargon_used
    assert "desnormalizadas" in res.criterios["jerga"]["tecnicismos"]
    res_aclarado = evaluator.evaluate(FeynmanSubmission(concept="Star Schema", explanation=aclarado))
    assert "desnormalizadas" not in res_aclarado.jargon_used
    assert "métricas" not in res_aclarado.jargon_used


def test_api_vault_and_exams(temp_vault_dir):
    """Verifica los endpoints REST de /api/vault y /api/exams."""
    # 1. GET /api/vault/notes
    res_notes = client.get("/api/vault/notes")
    assert res_notes.status_code == 200
    notes = res_notes.json()
    assert len(notes) >= 4

    # 2. GET /api/vault/stats
    res_stats = client.get("/api/vault/stats")
    assert res_stats.status_code == 200
    assert res_stats.json()["total_notes"] >= 4

    # 3. POST /api/exams/generate
    res_exam = client.post(
        "/api/exams/generate",
        json={"note_id": "Star Schema y Modelado Dimensional", "question_type": "multiple_choice", "count": 2}
    )
    assert res_exam.status_code == 200
    exam_data = res_exam.json()
    assert exam_data["total_questions"] == 2
    assert all(q["question_type"] == "multiple_choice" for q in exam_data["questions"])

    # 4. POST /api/exams/evaluate-feynman
    res_feyn = client.post(
        "/api/exams/evaluate-feynman",
        json={
            "concept": "Star Schema y Modelado Dimensional",
            "explanation": "Es como un ticket: las métricas van en las tablas de hechos y los datos del cliente en las dimensiones."
        }
    )
    assert res_feyn.status_code == 200
    assert res_feyn.json()["sin_ia"] is True
    assert 0 < res_feyn.json()["score"] <= 80


def test_cli_vault_and_exams(temp_vault_dir):
    """Verifica los comandos CLI aulento vault, exam y feynman."""
    # aulento vault list
    res = runner.invoke(cli, ["vault", "list"])
    assert res.exit_code == 0
    assert "Star Schema" in res.stdout

    # aulento vault stats
    res_stat = runner.invoke(cli, ["vault", "stats"])
    assert res_stat.exit_code == 0
    assert "Grafo del Vault" in res_stat.stdout

    # aulento exam create
    res_exam = runner.invoke(cli, ["exam", "create", "Transformers", "--type", "multiple_choice", "--num", "1"])
    assert res_exam.exit_code == 0
    assert "Examen de Active Recall" in res_exam.stdout

    # aulento feynman evaluate
    res_feyn = runner.invoke(
        cli,
        ["feynman", "evaluate", "Webhooks", "--explanation", "Es como un timbre en tu casa para que no tengas que mirar a la puerta a ver si llegó el cartero."]
    )
    assert res_feyn.exit_code == 0
    assert "Diagnóstico Feynman" in res_feyn.stdout


def test_feynman_sin_ia_nota_sin_terminos_no_dice_que_falta_la_nota_y_lagunas_son_de_contenido(temp_vault_dir):
    """060 R5: una nota encontrada pero sin términos no se reporta como «no se encontró»; `lagunas` solo trae contenido."""
    (temp_vault_dir / "04 Knowledge" / "Corta.md").write_text("# Corta\nUna idea breve.", encoding="utf-8")
    evaluator = FeynmanEvaluator(VaultReader(temp_vault_dir))
    res = evaluator.evaluate(FeynmanSubmission(concept="Corta", explanation="Es una idea muy breve y simple de contar."))
    assert not any("No se encontró una nota" in g for g in res.knowledge_gaps)
    assert any("no tiene términos" in g for g in res.knowledge_gaps)

    con_nota = evaluator.evaluate(FeynmanSubmission(
        concept="Star Schema",
        explanation="Imagina algo muy simple con frases larguísimas que nunca terminan y siguen y siguen sin parar jamás de verdad nunca",
    ))
    assert con_nota.criterios["huecos"]["lagunas"]
    assert all(l.startswith("No aparecen términos clave") for l in con_nota.criterios["huecos"]["lagunas"])
