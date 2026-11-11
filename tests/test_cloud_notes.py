"""Generador de apuntes SOP desde los materiales subidos (014, pasado a materiales en la 048, T3: R11)."""

import pytest
from conftest import administrador_de_prueba, cuenta_en, vault_de_prueba
from fastapi.testclient import TestClient
from materiales_de_prueba import texto_largo
from typer.testing import CliRunner

from aulento.cli.app import cli
from aulento.core.materiales import AlmacenDeMateriales
from aulento.db.connection import get_connection
from aulento.db.repository import CursoRepository
from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
from aulento.vault.cloud_notes import (
    MAX_CARACTERES_EN_EL_APUNTE,
    MaterialNoteGenerator,
)
from aulento.web.app import create_app

runner = CliRunner()

BIGQUERY = (
    "Tema: BigQuery\n"
    "1. Separación de Cómputo y Almacenamiento (Dremel & Colossus)\n"
    "2. Slots: unidades de cómputo virtual"
)
ARBOLES = "Tema: Árboles de decisión\n1. Bagging: promedia árboles entrenados con muestras bootstrap\n2. Random Forest"


def _subir(nombre: str, texto: str, user_id: int | None = None) -> dict:
    return AlmacenDeMateriales.con_conexion_propia(user_id or cuenta_en()).guardar(nombre, texto.encode("utf-8"))


@pytest.fixture
def test_env(cuenta):
    """Cursos de Digital House y Google Cloud Skills y dos materiales en la cuenta de prueba."""
    conn = get_connection()
    curso_repo = CursoRepository(conn, administrador_de_prueba(conn).id)
    course_dh = curso_repo.create(
        CursoCreate(
            plataforma_id=1,  # Digital House
            nombre_curso="Data Science Intensive",
            url_aula="https://playground.digitalhouse.com/course/101",
            estado=EstadoCurso.EN_CURSO,
            prioridad=PrioridadCurso.ALTA,
            progreso_pct=25.0,
        )
    )
    course_gcp = curso_repo.create(
        CursoCreate(
            plataforma_id=2,  # Google Cloud Skills Boost
            nombre_curso="Data Engineering on Google Cloud",
            url_aula="https://www.cloudskillsboost.google/paths/16",
            estado=EstadoCurso.EN_CURSO,
            prioridad=PrioridadCurso.ALTA,
            progreso_pct=40.0,
        )
    )
    conn.close()
    return {
        "vault_dir": vault_de_prueba(),
        "course_dh_id": course_dh.id,
        "course_gcp_id": course_gcp.id,
        "bigquery_id": _subir("Google Cloud Skills - BigQuery Data Engineering Architecture.md", BIGQUERY)["id"],
        "arboles_id": _subir("Arboles de Decision y Random Forest.md", ARBOLES)["id"],
    }


def _generador(test_env) -> MaterialNoteGenerator:
    return MaterialNoteGenerator(cuenta_en(), vault_path=test_env["vault_dir"])


def test_apunte_desde_un_material(test_env):
    """Un apunte SOP completo a partir del texto de un material de la cuenta."""
    note_data = _generador(test_env).generate_note(material_id=test_env["bigquery_id"], course_id=test_env["course_gcp_id"])

    assert note_data["title"] == "BigQuery Data Engineering Architecture"
    assert note_data["course"] == "Data Engineering on Google Cloud"
    assert note_data["platform"] == "Google Cloud Skills Boost"
    assert note_data["material_id"] == test_env["bigquery_id"]
    assert note_data["relative_path"].startswith("04 Knowledge/Cursos/")

    content = note_data["content"]
    assert "type: Curso" in content
    assert 'curso: "Data Engineering on Google Cloud"' in content
    assert f"material:\n  id: {test_env['bigquery_id']}\n" in content
    assert "> **Curso:** [[Data Engineering on Google Cloud]]" in content
    assert "> **Plataforma:** Google Cloud Skills Boost" in content
    assert "> **Material Origen:** Google Cloud Skills - BigQuery" in content
    assert "[[Separación de Cómputo y Almacenamiento]]" in content
    assert "```mermaid" in content and "Dremel" in content
    for seccion in ("## 1. Resumen Ejecutivo (TL;DR)", "## 4. Preguntas de Active Recall (Feynman / FSRS)", "## 5. Conexiones con MOCs"):
        assert seccion in content


def test_sin_curso_lo_resuelve_por_el_nombre_del_material(test_env):
    """El nombre del material nombra la plataforma: el apunte va a un curso de ella."""
    note_data = _generador(test_env).generate_note(material_id=test_env["bigquery_id"])

    assert note_data["platform"] == "Google Cloud Skills Boost"


def test_con_tema_el_apunte_trae_los_pasajes_de_todo_el_material(cuenta):
    material = _subir("Tratado.md", texto_largo(MAX_CARACTERES_EN_EL_APUNTE * 2, al_final="Pasaje final sobre zookeeper."))
    conn = get_connection()
    CursoRepository(conn, cuenta).create(
        CursoCreate(plataforma_id=1, nombre_curso="Sistemas", url_aula="https://x.test", estado="en_curso", prioridad="alta")
    )
    conn.close()

    generador = MaterialNoteGenerator(cuenta, vault_path=vault_de_prueba())
    con_tema = generador.generate_note(material_id=material["id"], topic="zookeeper")["content"]
    sin_tema = generador.generate_note(material_id=material["id"])["content"]

    assert "Pasaje final sobre zookeeper." in con_tema
    assert "Pasaje final sobre zookeeper." not in sin_tema
    assert len(sin_tema) < MAX_CARACTERES_EN_EL_APUNTE + 5_000


def test_un_material_de_otra_cuenta_no_se_encuentra(test_env, otra_cuenta):
    ajeno = _subir("Ajeno.md", "Texto de otra cuenta", user_id=otra_cuenta)
    with pytest.raises(ValueError, match="No se encontró el material"):
        _generador(test_env).generate_note(material_id=ajeno["id"])


def test_guardar_el_apunte_en_el_vault(test_env):
    target_path = _generador(test_env).save_note_to_vault(
        material_id=test_env["arboles_id"],
        course_id=test_env["course_dh_id"],
        topic="Machine Learning Foundations & Cost Function",
    )

    assert target_path.is_file()
    assert "04 Knowledge" in str(target_path)
    assert target_path.name == "Machine Learning Foundations & Cost Function.md"
    saved_text = target_path.read_text(encoding="utf-8")
    assert 'title: "Machine Learning Foundations & Cost Function"' in saved_text
    assert "Digital House" in saved_text
    assert "```mermaid" in saved_text


def test_web_api_lista_los_materiales_de_la_cuenta(test_env, otra_cuenta):
    _subir("Ajeno.md", "Texto de otra cuenta", user_id=otra_cuenta)
    client = TestClient(create_app())

    response = client.get("/api/vault/notes/materials")

    assert response.status_code == 200
    assert sorted(m["id"] for m in response.json()) == sorted([test_env["bigquery_id"], test_env["arboles_id"]])
    assert client.get("/api/vault/notes/cloud-materials").status_code == 404


def test_web_api_genera_y_guarda_desde_un_material(test_env, otra_cuenta):
    client = TestClient(create_app())
    payload = {"material_id": test_env["arboles_id"], "course_id": test_env["course_dh_id"]}

    res_preview = client.post("/api/vault/notes/from-material", json=payload)
    assert res_preview.status_code == 200
    data_prev = res_preview.json()
    assert data_prev["status"] == "preview"
    assert "Random Forest" in data_prev["title"]
    assert "Bagging" in data_prev["content"]
    assert "saved_path" not in data_prev

    res_save = client.post("/api/vault/notes/from-material?save_to_vault=true", json=payload)
    assert res_save.status_code == 200
    data_save = res_save.json()
    assert data_save["status"] == "saved"
    assert (vault_de_prueba() / data_save["saved_path"]).exists()

    ajeno = _subir("Ajeno.md", "Texto de otra cuenta", user_id=otra_cuenta)
    res_ajeno = client.post("/api/vault/notes/from-material", json={"material_id": ajeno["id"]})
    assert res_ajeno.status_code == 404
    assert "Texto de otra cuenta" not in res_ajeno.text


def test_cli_list_materials_y_note_from_material(test_env):
    res_list = runner.invoke(cli, ["vault", "list-materials"], env={"COLUMNS": "200"})
    assert res_list.exit_code == 0
    assert "Arboles de Decision y Random Forest.md" in res_list.output

    args = ["vault", "note-from-material", "--material-id", str(test_env["bigquery_id"]), "--course-id", str(test_env["course_gcp_id"])]
    res_preview = runner.invoke(cli, args, env={"COLUMNS": "200"})
    assert res_preview.exit_code == 0
    assert "BigQuery Data Engineering Architecture" in res_preview.output
    assert "Ruta Destino:" in res_preview.output

    res_save = runner.invoke(cli, [*args, "--save"], env={"COLUMNS": "200"})
    assert res_save.exit_code == 0
    assert "guardado en:" in res_save.output
