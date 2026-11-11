"""Pruebas end-to-end de los comandos CLI de FSRS con CliRunner."""

import pytest
from typer.testing import CliRunner

from conftest import cuenta_de_prueba
from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.db.schema import init_db

runner = CliRunner()


@pytest.fixture(autouse=True)
def configure_fsrs_test_db(tmp_path, monkeypatch):
    """Configura una base de datos temporal limpia, con una sola cuenta, para cada test del CLI."""
    db_file = tmp_path / "cli_fsrs_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    cuenta_de_prueba(conn)
    conn.close()
    return db_file


def test_cli_fsrs_seed_and_status():
    runner.invoke(cli, ["db", "init", "--no-seed"])

    # Sembrar mazo FSRS
    res_seed = runner.invoke(cli, ["fsrs", "seed"])
    assert res_seed.exit_code == 0
    assert "colocaciones de inglés técnico" in res_seed.stdout

    # Ver status
    res_status = runner.invoke(cli, ["fsrs", "status"])
    assert res_status.exit_code == 0
    assert "Tarjetas Totales:" in res_status.stdout
    assert "Dashboard de Memoria FSRS" in res_status.stdout


def test_cli_fsrs_list_and_add():
    runner.invoke(cli, ["db", "init", "--seed"])

    # Listar tarjetas
    res_list = runner.invoke(cli, ["fsrs", "list", "--limit", "5"])
    assert res_list.exit_code == 0
    assert "Mazo de Inglés Técnico" in res_list.stdout

    # Agregar tarjeta personalizada
    res_add = runner.invoke(
        cli,
        [
            "fsrs",
            "add",
            "--pregunta", "¿Cómo decir 'despliegue canario'?",
            "--respuesta", "canary deployment",
            "--contexto", "We routed 10% traffic to the canary deployment.",
            "--categoria", "cloud_infrastructure",
        ],
    )
    assert res_add.exit_code == 0
    assert "canary deployment" in res_add.stdout


def test_cli_fsrs_study_session_auto():
    # Inicializar con semillas
    runner.invoke(cli, ["db", "init", "--seed"])

    # Correr sesión de estudio con 3 tarjetas y auto-rating Good (3)
    res_study = runner.invoke(cli, ["fsrs", "study", "--limit", "3", "--auto-rating", "3"])
    assert res_study.exit_code == 0
    assert "Sesión de Estudio FSRS" in res_study.stdout
    assert "Sesión completada con éxito" in res_study.stdout
    assert "Repasaste 3 colocaciones técnicas" in res_study.stdout
