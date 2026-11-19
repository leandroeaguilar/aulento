"""Los documentos de la app viajan dentro del paquete (M5 de `docs/PENDIENTES.md`).

Instalada como paquete (wheel o imagen de la nube), la app no tiene `docs/`. Si el build no copia los
documentos, la pestaña de documentación muestra «Documentación en preparación» en lugar del manual.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import administrador_de_prueba
from fastapi.testclient import TestClient

from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.web import app as modulo_app
from aulento.web.app import DOCUMENTOS_DE_LA_APP, create_app

RAIZ = Path(__file__).resolve().parent.parent
NOMBRES = sorted(nombre for _, nombre in DOCUMENTOS_DE_LA_APP.values())


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    db_file = tmp_path / "documentos.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    administrador_de_prueba(conn)
    conn.close()
    return TestClient(create_app())


def _sin_docs_del_repo(monkeypatch, tmp_path: Path, empaquetados: Path) -> None:
    """Como en el wheel o la imagen: ni `docs/` del repo ni en la carpeta de trabajo."""
    monkeypatch.setattr(modulo_app, "DOCUMENTOS_EMPAQUETADOS", empaquetados)
    monkeypatch.setattr(modulo_app, "DOCUMENTOS_DEL_REPO", tmp_path / "sin_repo")
    monkeypatch.chdir(tmp_path)


def test_instalada_como_paquete_la_app_muestra_la_copia_empaquetada(cliente, tmp_path, monkeypatch):
    empaquetados = tmp_path / "paquete" / "documentos"
    empaquetados.mkdir(parents=True)
    for nombre in NOMBRES:
        (empaquetados / nombre).write_text(f"---\ntype: Doc\n---\n# {nombre} empaquetado\n\nTexto real.", encoding="utf-8")
    _sin_docs_del_repo(monkeypatch, tmp_path, empaquetados)

    for clave, (_, nombre) in DOCUMENTOS_DE_LA_APP.items():
        respuesta = cliente.get("/api/docs/manual", params={"doc": clave})
        assert respuesta.status_code == 200
        assert respuesta.json()["content"] == f"# {nombre} empaquetado\n\nTexto real."
    assert "MANUAL_DE_USUARIO.md empaquetado" in cliente.get("/manual").text


def test_sin_ningun_documento_responde_el_texto_de_reemplazo(cliente, tmp_path, monkeypatch):
    _sin_docs_del_repo(monkeypatch, tmp_path, tmp_path / "paquete_vacio")

    contenido = cliente.get("/api/docs/manual", params={"doc": "api"}).json()["content"]

    assert contenido == "# Referencia de la API REST\n\nDocumentación en preparación."


def test_el_wheel_lleva_los_documentos_de_la_app(tmp_path):
    """Construye el wheel de verdad, desde una copia del repo, y busca los documentos adentro."""
    pytest.importorskip("setuptools")
    copia = tmp_path / "repo"
    (copia / "docs").mkdir(parents=True)
    for archivo in ("pyproject.toml", "setup.py", "README.md", "LICENSE"):
        shutil.copy2(RAIZ / archivo, copia / archivo)
    shutil.copytree(RAIZ / "src", copia / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    for nombre in NOMBRES:
        shutil.copy2(RAIZ / "docs" / nombre, copia / "docs" / nombre)
    salida = tmp_path / "wheels"

    corrida = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "--no-index", "-q", "-w", str(salida)],
        cwd=copia,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert corrida.returncode == 0, corrida.stdout[-2000:] + corrida.stderr[-2000:]
    rueda = next(salida.glob("aulento-*.whl"))
    with zipfile.ZipFile(rueda) as contenido:
        for nombre in NOMBRES:
            assert contenido.read(f"aulento/documentos/{nombre}") == (RAIZ / "docs" / nombre).read_bytes()
