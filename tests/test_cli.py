"""Pruebas end-to-end de los comandos CLI con CliRunner."""

import pytest
from typer.testing import CliRunner

from conftest import cuenta_de_prueba
from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.db.schema import init_db

runner = CliRunner()


@pytest.fixture(autouse=True)
def configure_test_db(tmp_path, monkeypatch):
    """Configura una base de datos temporal limpia, con una sola cuenta, para cada test del CLI."""
    db_file = tmp_path / "cli_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    cuenta_de_prueba(conn)
    conn.close()
    return db_file


def test_cli_db_init_and_status():
    # Inicializar
    res_init = runner.invoke(cli, ["db", "init", "--seed"])
    assert res_init.exit_code == 0
    assert "Base de datos inicializada" in res_init.stdout
    assert "Plataformas iniciales sembradas" in res_init.stdout

    # Status
    res_status = runner.invoke(cli, ["db", "status"])
    assert res_status.exit_code == 0
    assert "Plataformas Académicas" in res_status.stdout
    assert "5" in res_status.stdout


def test_cli_hub_flow():
    # Inicializar con semilla
    runner.invoke(cli, ["db", "init", "--seed"])

    # Listar inicial (debe mostrar las 5 plataformas)
    res_list = runner.invoke(cli, ["hub", "list"])
    assert res_list.exit_code == 0
    assert "Digital House" in res_list.stdout
    assert "Humai" in res_list.stdout

    # Registrar nueva plataforma
    res_plat = runner.invoke(cli, ["hub", "add-platform", "Platzi", "--url", "https://platzi.com", "--color", "emerald"])
    assert res_plat.exit_code == 0
    assert "Platzi" in res_plat.stdout

    # Agregar curso
    res_add = runner.invoke(
        cli,
        [
            "hub",
            "add-course",
            "--plataforma", "1",
            "--nombre", "Data Science Intensive",
            "--url", "https://digitalhouse.com/aula",
            "--progreso", "15.0",
            "--prioridad", "alta",
        ],
    )
    assert res_add.exit_code == 0
    assert "Curso registrado" in res_add.stdout

    # Actualizar progreso
    res_up = runner.invoke(cli, ["hub", "update-progress", "1", "100.0"])
    assert res_up.exit_code == 0
    assert "100.0%" in res_up.stdout
    assert "completado" in res_up.stdout


def test_cli_books_flow():
    runner.invoke(cli, ["db", "init", "--seed"])

    # Agregar libro
    res_add = runner.invoke(
        cli,
        [
            "books",
            "add",
            "--titulo", "AI Engineering",
            "--total", "10",
            "--actual", "1",
            "--vault", "06 Raw/Libros/ai.pdf",
        ],
    )
    assert res_add.exit_code == 0
    assert "AI Engineering" in res_add.stdout

    # Listar libros
    res_list = runner.invoke(cli, ["books", "list"])
    assert res_list.exit_code == 0
    assert "AI Engineering" in res_list.stdout
    assert "1 / 10" in res_list.stdout

    # Avanzar capítulo
    res_adv = runner.invoke(cli, ["books", "advance", "1", "--capitulos", "2"])
    assert res_adv.exit_code == 0
    assert "3/10" in res_adv.stdout
    assert "30.0%" in res_adv.stdout


def test_cli_schedule_flow():
    runner.invoke(cli, ["db", "init", "--seed"])

    # Agregar horario
    res_add = runner.invoke(
        cli,
        [
            "schedule",
            "add",
            "--dia", "1",
            "--inicio", "10:30",
            "--fin", "12:30",
            "--tipo", "curso",
            "--desc", "Digital House Cursada",
            "--url", "https://meet.google.com/test",
        ],
    )
    assert res_add.exit_code == 0
    assert "Lunes 10:30-12:30" in res_add.stdout

    # Listar horarios
    res_list = runner.invoke(cli, ["schedule", "list"])
    assert res_list.exit_code == 0
    assert "Digital House" in res_list.stdout
    assert "Cursada" in res_list.stdout
    assert "10:30 - 12:30" in res_list.stdout
