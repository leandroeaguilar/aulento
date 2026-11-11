"""Tests para los comandos CLI de Rutas de Aprendizaje."""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch

from conftest import cuenta_de_prueba
from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.db.schema import init_db
from aulento.core.gemini_gateway import GeminiGateway

runner = CliRunner()

DATA_ENGINEER_TEMPLATE = "Data Engineer Senior (Cloud, Streaming & Lakehouse)"


@pytest.fixture(autouse=True)
def configure_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "cli_roadmap_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    cuenta_de_prueba(conn)
    conn.close()
    return db_file


def test_cli_roadmap_empty_list():
    res = runner.invoke(cli, ["roadmap", "list"])
    assert res.exit_code == 0
    assert "No hay rutas de aprendizaje" in res.stdout


def test_cli_roadmap_create_and_show():
    with patch.object(GeminiGateway, "get_active_api_key", return_value=None):
        res_create = runner.invoke(
            cli,
            ["roadmap", "create", "--title", DATA_ENGINEER_TEMPLATE, "--level", "Senior"],
        )
        assert res_create.exit_code == 0
        assert "Ruta creada con éxito" in res_create.stdout

        # Listar
        res_list = runner.invoke(cli, ["roadmap", "list"])
        assert res_list.exit_code == 0
        assert "Data" in res_list.stdout and "Senior" in res_list.stdout

        # Show
        res_show = runner.invoke(cli, ["roadmap", "show", "1"])
        assert res_show.exit_code == 0
        assert "Data Engineer" in res_show.stdout
        assert "Streaming" in res_show.stdout or "Almacenamiento" in res_show.stdout


def test_cli_roadmap_prompt_and_import(tmp_path):
    with patch.object(GeminiGateway, "get_active_api_key", return_value=None):
        runner.invoke(cli, ["roadmap", "create", "--title", "AI Solutions Architect"])

        # Generar prompt
        res_prompt = runner.invoke(cli, ["roadmap", "prompt", "--topic-id", "1"])
        assert res_prompt.exit_code == 0
        assert "Prompt Maestro" in res_prompt.stdout
        assert "Técnica Feynman" in res_prompt.stdout

        # Crear archivo markdown de prueba
        md_file = tmp_path / "clase.md"
        md_file.write_text(
            "# Arquitectura Transformer\n\nContenido de prueba.\n\n```cards-fsrs\nQ: ¿Qué es Attention?\nA: Mecanismo de ponderación dinámica.\n```",
            encoding="utf-8",
        )

        # Importar clase
        res_import = runner.invoke(cli, ["roadmap", "import", "--topic-id", "1", "--file", str(md_file)])
        assert res_import.exit_code == 0
        assert "Clase importada" in res_import.stdout
        assert "tarjetas inyectadas" in res_import.stdout


# --- R5 / R9: aviso de fallback y alcance en la CLI ---

def _salida_plana(stdout: str) -> str:
    return " ".join(stdout.split())


def test_cli_roadmap_create_sin_ia_imprime_el_aviso(configure_test_db):
    with patch.object(GeminiGateway, "get_active_api_key", return_value=None):
        res = runner.invoke(cli, ["roadmap", "create", "--title", "Filosofía estoica", "--alcance", "especializacion"])

    assert res.exit_code == 0
    salida = _salida_plana(res.stdout)
    assert "Ruta creada con éxito" in salida
    assert "Aviso:" in salida
    assert "Ruta generada sin IA" in salida
    assert "humanidades" in salida

    conn = get_connection(configure_test_db)
    cuenta = cuenta_de_prueba(conn).id
    conn.close()
    creada = RoadmapRepository(cuenta, db_path=str(configure_test_db)).get_roadmaps()[0]
    assert creada.metadata_json["alcance"] == "especializacion"
    assert creada.metadata_json["origen"] == "domain_fallback"


def test_cli_roadmap_create_desde_plantilla_no_imprime_aviso():
    res = runner.invoke(cli, ["roadmap", "create", "--title", DATA_ENGINEER_TEMPLATE])
    assert res.exit_code == 0
    assert "Ruta creada con éxito" in res.stdout
    assert "Aviso:" not in res.stdout


def test_cli_roadmap_create_rechaza_alcance_desconocido():
    res = runner.invoke(cli, ["roadmap", "create", "--title", "Álgebra", "--alcance", "doctorado"])
    assert res.exit_code != 0


def test_cli_roadmap_create_ya_no_acepta_la_opcion_sin_efecto_no_ai():
    res = runner.invoke(cli, ["roadmap", "create", "--title", "Álgebra", "--no-ai"])
    assert res.exit_code != 0
