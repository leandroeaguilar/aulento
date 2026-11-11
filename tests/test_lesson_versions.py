"""Tests de la feature 030: versiones anteriores de las clases y respaldo de notas del vault por huella."""

import sqlite3
from pathlib import Path

import pytest
from conftest import cuenta_en, vault_de_prueba
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from aulento.cli.app import cli
from aulento.db.roadmap_repository import MAX_VERSIONES_POR_TEMA, RoadmapRepository
from aulento.mcp.server import create_study_mcp_server
from aulento.models.roadmap import (
    EstadoTema,
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
)
from aulento.roadmap.lesson_studio import LessonStudio
from aulento.web.app import create_app

runner = CliRunner()


def clase(n: int) -> str:
    return f"# Clase {n}\n\nContenido de la versión {n}.\n\n```cards-fsrs\nQ: Pregunta {n}\nA: Respuesta {n}\n```\n"


@pytest.fixture
def ruta(tmp_path, monkeypatch):
    """Ruta con un tema, en la base configurada de la suite, y un vault temporal."""
    vault = vault_de_prueba()
    repo = RoadmapRepository(cuenta_en())
    creada = repo.create_roadmap(
        RoadmapCreate(
            titulo=f"Ruta de versiones {tmp_path.name}",
            descripcion="d",
            nivel_objetivo="Inicial",
            categoria="general",
            modulos=[RoadmapModuleCreate(titulo="M", orden=1, temas=[RoadmapTopicCreate(titulo="Tema con versiones", orden=1)])],
        )
    )
    return repo, creada.modulos[0].temas[0].id, vault


def notas(vault: Path) -> list[Path]:
    return sorted(vault.rglob("*.md"))


def respaldos(vault: Path) -> list[Path]:
    return [p for p in notas(vault) if "(respaldo " in p.name]


# ---------------------------------------------------------------- R1: versiones


def test_r1_reemplazar_una_clase_conserva_la_anterior(ruta):
    repo, tema_id, _ = ruta
    studio = LessonStudio(repo=repo)
    studio.import_external_lesson(tema_id, clase(1))
    assert repo.get_lesson_versions(tema_id) == []

    studio.import_external_lesson(tema_id, clase(2))

    versiones = repo.get_lesson_versions(tema_id)
    assert len(versiones) == 1
    assert versiones[0].titulo == "Clase 1"
    assert "Contenido de la versión 1." in versiones[0].contenido_markdown
    assert versiones[0].flashcards_json == [{"pregunta": "Pregunta 1", "respuesta": "Respuesta 1"}]
    assert versiones[0].origen.value == "notebooklm"
    assert versiones[0].fecha_version
    assert "Contenido de la versión 2." in repo.get_lesson_by_topic_id(tema_id).contenido_markdown


def test_r1_contenido_identico_no_crea_version(ruta):
    repo, tema_id, _ = ruta
    studio = LessonStudio(repo=repo)
    studio.import_external_lesson(tema_id, clase(1))
    studio.import_external_lesson(tema_id, clase(1))
    assert repo.get_lesson_versions(tema_id) == []


def test_r1_se_conservan_las_diez_mas_recientes(ruta):
    repo, tema_id, _ = ruta
    studio = LessonStudio(repo=repo)
    for n in range(1, MAX_VERSIONES_POR_TEMA + 5):
        studio.import_external_lesson(tema_id, clase(n))
    versiones = repo.get_lesson_versions(tema_id)
    assert len(versiones) == MAX_VERSIONES_POR_TEMA == 10
    # La vigente es la 14: quedan como versiones de la 13 a la 4
    assert [v.titulo for v in versiones] == [f"Clase {n}" for n in range(13, 3, -1)]


@pytest.mark.anyio
async def test_r1_el_reemplazo_por_mcp_tambien_deja_version(ruta, cuenta_mcp):
    repo, tema_id, _ = ruta
    server = create_study_mcp_server()
    await server.call_tool("study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": clase(1)})
    sin_overwrite = await server.call_tool("study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": clase(2)})
    assert "versión anterior" in sin_overwrite.content[0].text
    assert repo.get_lesson_versions(tema_id) == []
    await server.call_tool("study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": clase(2), "overwrite": True})
    assert [v.titulo for v in repo.get_lesson_versions(tema_id)] == ["Clase 1"]


def test_r1_las_versiones_se_borran_con_la_ruta(ruta):
    repo, tema_id, _ = ruta
    studio = LessonStudio(repo=repo)
    studio.import_external_lesson(tema_id, clase(1))
    studio.import_external_lesson(tema_id, clase(2))
    ruta_id = repo.get_topic_with_context(tema_id)["roadmap_id"]
    assert repo.delete_roadmap(ruta_id)
    assert repo.get_lesson_versions(tema_id) == []


# ---------------------------------------------------------------- R2: restaurar


def test_r2_restaurar_deja_la_vigente_como_version_y_conserva_el_estado(ruta):
    repo, tema_id, _ = ruta
    studio = LessonStudio(repo=repo)
    studio.import_external_lesson(tema_id, clase(1))
    studio.import_external_lesson(tema_id, clase(2))
    repo.update_topic_status(tema_id, EstadoTema.EN_PROGRESO)
    version = repo.get_lesson_versions(tema_id)[0]

    restaurada = repo.restore_lesson_version(version.id)

    assert restaurada.titulo == "Clase 1"
    assert "Contenido de la versión 1." in repo.get_lesson_by_topic_id(tema_id).contenido_markdown
    assert [v.titulo for v in repo.get_lesson_versions(tema_id)] == ["Clase 2"]
    assert repo.get_topic_with_context(tema_id)["topic_status"] == "en_progreso"
    assert repo.restore_lesson_version(999999) is None


def test_r2_api_lista_y_restaura(ruta):
    repo, tema_id, _ = ruta
    client = TestClient(create_app())
    studio = LessonStudio(repo=repo)
    studio.import_external_lesson(tema_id, clase(1))
    assert client.get(f"/api/roadmap/topics/{tema_id}/lesson-versions").json() == []

    importada = client.post(f"/api/roadmap/topics/{tema_id}/import-lesson", json={"markdown_content": clase(2), "origen": "chatgpt"})
    assert importada.status_code == 200, importada.text

    versiones = client.get(f"/api/roadmap/topics/{tema_id}/lesson-versions").json()
    assert [v["titulo"] for v in versiones] == ["Clase 1"]
    # La versión conserva el origen de la clase reemplazada, no el de la nueva
    assert versiones[0]["origen"] == "notebooklm"
    assert client.get(f"/api/roadmap/{repo.get_topic_with_context(tema_id)['roadmap_id']}").json()["modulos"][0]["temas"][0]["clase"]["origen"] == "chatgpt"

    res = client.post(f"/api/roadmap/lesson-versions/{versiones[0]['id']}/restore")
    assert res.status_code == 200
    assert res.json()["titulo"] == "Clase 1"
    assert [v["titulo"] for v in client.get(f"/api/roadmap/topics/{tema_id}/lesson-versions").json()] == ["Clase 2"]
    assert client.post("/api/roadmap/lesson-versions/999999/restore").status_code == 404


def test_r2_cli_lista_y_restaura(ruta):
    repo, tema_id, _ = ruta
    studio = LessonStudio(repo=repo)
    studio.import_external_lesson(tema_id, clase(1))

    vacio = runner.invoke(cli, ["roadmap", "versions", "--topic-id", str(tema_id)])
    assert vacio.exit_code == 0 and "no tiene versiones" in vacio.stdout

    studio.import_external_lesson(tema_id, clase(2))
    listado = runner.invoke(cli, ["roadmap", "versions", "--topic-id", str(tema_id)], env={"COLUMNS": "200"})
    assert "Clase 1" in listado.stdout
    version_id = repo.get_lesson_versions(tema_id)[0].id

    res = runner.invoke(cli, ["roadmap", "restore", "--version-id", str(version_id)])
    assert res.exit_code == 0 and "Clase restaurada" in res.stdout
    assert repo.get_lesson_by_topic_id(tema_id).titulo == "Clase 1"
    assert runner.invoke(cli, ["roadmap", "restore", "--version-id", "999999"]).exit_code == 1


# ---------------------------------------------------------------- R3: confirmación


def test_r3_cli_import_pide_confirmacion_antes_de_reemplazar(ruta, tmp_path):
    repo, tema_id, vault = ruta
    archivo = tmp_path / "clase.md"
    archivo.write_text(clase(1), encoding="utf-8")
    primera = runner.invoke(cli, ["roadmap", "import", "--topic-id", str(tema_id), "--file", str(archivo)])
    assert primera.exit_code == 0 and "Clase importada" in primera.stdout
    nota_antes = notas(vault)[0].read_bytes()

    archivo.write_text(clase(2), encoding="utf-8")
    rechazada = runner.invoke(cli, ["roadmap", "import", "--topic-id", str(tema_id), "--file", str(archivo)], input="n\n")
    assert "ya tiene una clase" in rechazada.stdout and "No se modificó nada" in rechazada.stdout
    assert repo.get_lesson_by_topic_id(tema_id).titulo == "Clase 1"
    assert repo.get_lesson_versions(tema_id) == []
    assert notas(vault)[0].read_bytes() == nota_antes

    aceptada = runner.invoke(cli, ["roadmap", "import", "--topic-id", str(tema_id), "--file", str(archivo)], input="y\n")
    assert aceptada.exit_code == 0
    assert repo.get_lesson_by_topic_id(tema_id).titulo == "Clase 2"
    archivo.write_text(clase(3), encoding="utf-8")
    forzada = runner.invoke(cli, ["roadmap", "import", "--topic-id", str(tema_id), "--file", str(archivo), "--overwrite"])
    assert forzada.exit_code == 0 and "ya tiene una clase" not in forzada.stdout
    assert repo.get_lesson_by_topic_id(tema_id).titulo == "Clase 3"
    assert [v.titulo for v in repo.get_lesson_versions(tema_id)] == ["Clase 2", "Clase 1"]


def test_r3_la_interfaz_confirma_antes_de_reemplazar_y_ofrece_restaurar():
    import aulento.web as web_pkg
    from tests.front import js_del_front

    static = Path(web_pkg.__file__).parent / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    js = js_del_front()

    def cuerpo(nombre):
        inicio = js.index(f"function {nombre}(")
        return js[inicio : js.index("\n}\n", inicio)]

    assert "t.id === topicId && t.clase" in cuerpo("topicHasLesson")
    importar = cuerpo("submitImportLesson")
    confirmacion = "if (topicHasLesson(topicId) && !confirm(`${AVISO_REEMPLAZO_CLASE}"
    assert confirmacion in importar
    # La confirmación va antes de enviar la clase
    assert importar.index(confirmacion) < importar.index("/import-lesson")
    generar = cuerpo("generateLessonInApp")
    assert "topicHasLesson(topicId) ? `\\n\\n⚠ ${AVISO_REEMPLAZO_CLASE}`" in generar
    # El aviso de reemplazo va en el diálogo propio de la app, y se confirma antes de generar
    assert "${reemplazo}`," in generar and "await showConfirmDialog({" in generar
    assert generar.index("if (!confirmado) return;") < generar.index("/generate-lesson")
    assert "queda guardada como versión anterior" in js

    boton = html[html.index('id="btn-restore-lesson-version"') - 80 :]
    boton = boton[: boton.index(">", boton.index('id="btn-restore-lesson-version"'))]
    # 072: el botón dispara la acción delegada que llama a restorePreviousLessonVersion
    assert 'data-accion="ruta-restaurar-version-clase"' in boton and "hidden" in boton
    assert "['ruta-restaurar-version-clase', () => restorePreviousLessonVersion()]" in js
    assert "loadLessonVersions(topicId);" in cuerpo("viewLessonModal")
    versiones = cuerpo("loadLessonVersions")
    assert "fetch(`/api/roadmap/topics/${topicId}/lesson-versions`)" in versiones
    assert "btn.classList.toggle('hidden', n === 0)" in versiones
    assert "innerHTML" not in versiones
    restaurar = cuerpo("restorePreviousLessonVersion")
    assert "fetch(`/api/roadmap/lesson-versions/${version.id}/restore`, { method: 'POST' })" in restaurar
    assert restaurar.index("confirm(") < restaurar.index("/restore")
    assert "if (data.backup_path)" in js or "data.backup_path ?" in js


# ---------------------------------------------------------------- R4: notas del vault


def test_r4_exportar_sin_cambios_no_respalda(ruta):
    repo, tema_id, vault = ruta
    studio = LessonStudio(repo=repo)
    lesson = studio.import_external_lesson(tema_id, clase(1))
    studio.export_lesson_to_vault(lesson.id)
    studio.export_lesson_to_vault(lesson.id)
    assert studio.last_backup_path is None
    assert len(notas(vault)) == 1


def test_r4_reemplazar_la_clase_y_exportar_no_respalda_la_nota_intacta(ruta):
    repo, tema_id, vault = ruta
    studio = LessonStudio(repo=repo)
    lesson = studio.import_external_lesson(tema_id, clase(1))
    studio.export_lesson_to_vault(lesson.id)

    lesson = studio.import_external_lesson(tema_id, clase(2))
    studio.export_lesson_to_vault(lesson.id)

    assert studio.last_backup_path is None
    assert len(notas(vault)) == 1
    assert "Contenido de la versión 2." in notas(vault)[0].read_text(encoding="utf-8")


def test_r4_la_web_respalda_la_nota_editada_a_mano(ruta):
    _, tema_id, vault = ruta
    client = TestClient(create_app())
    lesson_id = client.post(f"/api/roadmap/topics/{tema_id}/import-lesson", json={"markdown_content": clase(1), "origen": "chatgpt"}).json()["lesson_id"]
    primera = client.post(f"/api/roadmap/lessons/{lesson_id}/export-vault").json()
    assert primera["backup_path"] is None
    # Las rutas de la respuesta son relativas al vault de la cuenta
    assert not Path(primera["vault_path"]).is_absolute()
    nota = vault / primera["vault_path"]
    nota.write_text(nota.read_text(encoding="utf-8") + "\n\nMIS APUNTES A MANO\n", encoding="utf-8")

    lesson_id = client.post(f"/api/roadmap/topics/{tema_id}/import-lesson", json={"markdown_content": clase(2), "origen": "chatgpt"}).json()["lesson_id"]
    segunda = client.post(f"/api/roadmap/lessons/{lesson_id}/export-vault").json()

    assert segunda["backup_path"]
    assert not Path(segunda["backup_path"]).is_absolute()
    assert "MIS APUNTES A MANO" in (vault / segunda["backup_path"]).read_text(encoding="utf-8")
    assert (vault / segunda["backup_path"]).parent == nota.parent
    assert "Contenido de la versión 2." in nota.read_text(encoding="utf-8")
    # La nota recién escrita es del sistema: volver a exportar no respalda
    assert client.post(f"/api/roadmap/lessons/{lesson_id}/export-vault").json()["backup_path"] is None
    assert len(respaldos(vault)) == 1


def test_r4_la_cli_respalda_la_nota_editada_a_mano(ruta, tmp_path):
    _, tema_id, vault = ruta
    archivo = tmp_path / "clase.md"
    archivo.write_text(clase(1), encoding="utf-8")
    runner.invoke(cli, ["roadmap", "import", "--topic-id", str(tema_id), "--file", str(archivo)])
    nota = notas(vault)[0]
    nota.write_text(nota.read_text(encoding="utf-8") + "\n\nMIS APUNTES A MANO\n", encoding="utf-8")

    archivo.write_text(clase(2), encoding="utf-8")
    res = runner.invoke(cli, ["roadmap", "import", "--topic-id", str(tema_id), "--file", str(archivo), "--overwrite"], env={"COLUMNS": "400"})

    assert len(respaldos(vault)) == 1
    assert "MIS APUNTES A MANO" in respaldos(vault)[0].read_text(encoding="utf-8")
    assert "se guardó una copia" in res.stdout


def test_r4_nota_sin_huella_y_distinta_se_respalda(ruta):
    repo, tema_id, vault = ruta
    studio = LessonStudio(repo=repo)
    lesson = studio.import_external_lesson(tema_id, clase(1))
    studio.export_lesson_to_vault(lesson.id)
    nota = notas(vault)[0]
    # Nota anterior a la huella: sin huella guardada y con contenido propio
    conn = sqlite3.connect(str(repo.db_path) if repo.db_path else __import__("os").environ["AULENTO_DB_PATH"])
    conn.execute("UPDATE ruta_clases SET vault_hash = NULL WHERE id = ?", (lesson.id,))
    conn.commit()
    conn.close()

    studio.export_lesson_to_vault(lesson.id)
    assert studio.last_backup_path is None, "sin huella, una nota igual a la que generaría la clase no se respalda"

    conn = sqlite3.connect(__import__("os").environ["AULENTO_DB_PATH"])
    conn.execute("UPDATE ruta_clases SET vault_hash = NULL WHERE id = ?", (lesson.id,))
    conn.commit()
    conn.close()
    nota.write_text("NOTA PROPIA\n", encoding="utf-8")
    studio.export_lesson_to_vault(lesson.id)
    assert Path(studio.last_backup_path).read_text(encoding="utf-8") == "NOTA PROPIA\n"


# ---------------------------------------------------------------- hallazgos de la revisión de código


def test_guardar_sobre_una_clase_devuelve_el_id_de_la_clase_y_no_el_de_la_version(tmp_path, monkeypatch):
    """Con varios temas, el id de la versión guardada no coincide con el de la clase: no deben confundirse."""
    vault = vault_de_prueba()
    repo = RoadmapRepository(cuenta_en())
    creada = repo.create_roadmap(
        RoadmapCreate(
            titulo=f"Ruta de ids {tmp_path.name}",
            descripcion="d",
            nivel_objetivo="Inicial",
            categoria="general",
            modulos=[RoadmapModuleCreate(titulo="M", orden=1, temas=[RoadmapTopicCreate(titulo=f"Tema {n}", orden=n) for n in range(1, 5)])],
        )
    )
    temas = [t.id for t in creada.modulos[0].temas]
    studio = LessonStudio(repo=repo)
    ids = {tema: studio.import_external_lesson(tema, clase(i)).id for i, tema in enumerate(temas, start=1)}
    assert len(set(ids.values())) == 4

    ultimo = temas[-1]
    reemplazo = studio.import_external_lesson(ultimo, clase(99))

    assert reemplazo.id == ids[ultimo] == repo.get_lesson_by_topic_id(ultimo).id
    exportada = Path(studio.export_lesson_to_vault(reemplazo.id))
    assert exportada.name == "Tema 4.md"
    assert "Contenido de la versión 99." in exportada.read_text(encoding="utf-8")
    assert [p.name for p in notas(vault)] == ["Tema 4.md"]
    # Las tarjetas de la clase nueva van a FSRS, no las de otro tema
    assert studio.export_flashcards_to_fsrs(reemplazo.id) == 1


@pytest.mark.anyio
async def test_reemplazo_por_mcp_con_varios_temas_exporta_la_clase_correcta(tmp_path, monkeypatch, cuenta_mcp):
    vault = vault_de_prueba()
    repo = RoadmapRepository(cuenta_en())
    creada = repo.create_roadmap(
        RoadmapCreate(
            titulo=f"Ruta MCP {tmp_path.name}",
            descripcion="d",
            nivel_objetivo="Inicial",
            categoria="general",
            modulos=[RoadmapModuleCreate(titulo="M", orden=1, temas=[RoadmapTopicCreate(titulo=f"Tema {n}", orden=n) for n in range(1, 4)])],
        )
    )
    temas = [t.id for t in creada.modulos[0].temas]
    server = create_study_mcp_server()
    for i, tema in enumerate(temas, start=1):
        await server.call_tool("study_create_or_update_lesson", {"topic_id": tema, "markdown_content": clase(i)})
    intacta = (vault / "04 Knowledge" / "Cursos" / creada.titulo / "Tema 1.md").read_bytes()

    res = await server.call_tool("study_create_or_update_lesson", {"topic_id": temas[2], "markdown_content": clase(77), "overwrite": True})

    texto = res.content[0].text
    assert f"ID de Clase guardada:** {repo.get_lesson_by_topic_id(temas[2]).id}" in texto
    assert "Contenido de la versión 77." in (vault / "04 Knowledge" / "Cursos" / creada.titulo / "Tema 3.md").read_text(encoding="utf-8")
    assert (vault / "04 Knowledge" / "Cursos" / creada.titulo / "Tema 1.md").read_bytes() == intacta
    assert respaldos(vault) == []
