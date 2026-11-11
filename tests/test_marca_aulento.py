"""Study Engine pasa a llamarse Aulento (070, ADR 021): nombres nuevos, compatibilidad con los viejos y datos intactos."""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from aulento import config
from aulento._compat import adoptar_variables_viejas

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
COMPATIBILIDAD = SRC / "study_engine"


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _cli(*argumentos: str) -> subprocess.CompletedProcess:
    """Corre la CLI sin colores: en CI Rich los fuerza y parte el texto con códigos ANSI."""
    entorno = {k: v for k, v in os.environ.items() if k not in {"FORCE_COLOR", "TTY_COMPATIBLE"}}
    entorno.update(NO_COLOR="1", TERM="dumb", COLUMNS="200")
    salida = subprocess.run([sys.executable, *argumentos], capture_output=True, text=True, check=False,
                            encoding="utf-8", errors="replace", timeout=120, env=entorno)
    salida.stdout, salida.stderr = ANSI.sub("", salida.stdout), ANSI.sub("", salida.stderr)
    return salida


def _archivos(carpeta: Path, *sufijos: str) -> list[Path]:
    return [p for p in carpeta.rglob("*") if p.suffix in sufijos and "__pycache__" not in p.parts]


# --- R1: paquetes y CLI ---


def test_ningun_modulo_importa_el_paquete_viejo():
    patron = re.compile(r"^\s*(from|import)\s+study_engine\b", re.MULTILINE)
    culpables = [
        str(p.relative_to(RAIZ))
        for carpeta in (SRC, RAIZ / "tests", RAIZ / "scripts")
        for p in _archivos(carpeta, ".py")
        if not p.is_relative_to(COMPATIBILIDAD) and patron.search(p.read_text(encoding="utf-8"))
    ]
    assert culpables == []


def test_no_queda_ninguna_variable_con_el_prefijo_viejo_en_el_codigo():
    culpables = [
        str(p.relative_to(RAIZ))
        for p in _archivos(SRC, ".py", ".js", ".html")
        if not p.is_relative_to(COMPATIBILIDAD)
        and p.name not in {"_compat.py", "importacion.py"}
        and "STUDY_ENGINE_" in p.read_text(encoding="utf-8")
    ]
    assert culpables == []


def test_python_m_aulento_abre_la_cli():
    salida = _cli("-m", "aulento", "--help")
    assert salida.returncode == 0
    assert "Usage" in salida.stdout


# --- R2: marca visible ---


def test_ningun_texto_del_codigo_dice_study_engine():
    culpables = [
        str(p.relative_to(RAIZ))
        for p in _archivos(SRC, ".py", ".js", ".html", ".json", ".css")
        if not p.is_relative_to(COMPATIBILIDAD)
        and p.name != "_compat.py"
        and p.name != "config.py"
        and "Study Engine" in p.read_text(encoding="utf-8")
    ]
    assert culpables == []


def test_el_manifest_de_la_pwa_se_llama_aulento():
    manifest = json.loads((SRC / "aulento" / "web" / "static" / "manifest.json").read_text(encoding="utf-8"))
    assert "Aulento" in manifest["name"]


def test_el_servidor_mcp_se_anuncia_como_aulento():
    from aulento.mcp.server import create_study_mcp_server

    assert create_study_mcp_server().name == "aulento"


def test_la_configuracion_mcp_que_muestra_la_app_usa_el_nombre_nuevo():
    from tests.front import js_del_front

    mcp_js = (SRC / "aulento" / "web" / "static" / "mcp-remoto.js").read_text(encoding="utf-8")
    for nombre, js in (("front", js_del_front()), ("mcp-remoto.js", mcp_js)):
        assert "'aulento'" in js or "\"aulento\"" in js, nombre
        assert "study-engine" not in js and "study_engine" not in js, nombre
    assert "'-m', 'aulento'" in js_del_front()


# --- R3: el nombre viejo reenvía ---


def test_python_m_study_engine_reenvia_y_avisa_solo_por_stderr():
    salida = _cli("-m", "study_engine", "--help")
    assert salida.returncode == 0
    assert re.search(r"Usage:\s+aulento", salida.stdout), salida.stdout[:300]
    assert "Aulento" in salida.stderr
    assert "ahora se llama" not in salida.stdout, "stdout es el transporte de MCP por stdio"


def test_el_comando_viejo_sigue_instalado_como_alias():
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert 'aulento = "aulento.cli.app:cli"' in texto
    assert 'study-engine = "study_engine:main"' in texto


# --- R5: variables con el nombre anterior ---


def test_una_variable_vieja_sin_la_nueva_se_copia():
    entorno = {"STUDY_ENGINE_MODE": "saas"}
    assert adoptar_variables_viejas(entorno) == ["AULENTO_MODE"]
    assert entorno["AULENTO_MODE"] == "saas"


def test_con_las_dos_gana_la_nueva():
    entorno = {"STUDY_ENGINE_MODE": "saas", "AULENTO_MODE": "local"}
    assert adoptar_variables_viejas(entorno) == []
    assert entorno["AULENTO_MODE"] == "local"


def test_el_aviso_nombra_la_variable_sin_mostrar_el_valor(caplog):
    entorno = {"STUDY_ENGINE_SECRET_KEY": "valor-secreto-que-no-se-muestra"}
    with caplog.at_level(logging.WARNING, logger="aulento"):
        adoptar_variables_viejas(entorno)
    assert "AULENTO_SECRET_KEY" in caplog.text and "STUDY_ENGINE_SECRET_KEY" in caplog.text
    assert "valor-secreto-que-no-se-muestra" not in caplog.text


def test_sin_variables_viejas_no_avisa(caplog):
    with caplog.at_level(logging.WARNING, logger="aulento"):
        assert adoptar_variables_viejas({"AULENTO_MODE": "local"}) == []
    assert caplog.text == ""


def test_al_importar_aulento_se_adoptan_las_variables_viejas():
    codigo = "import os, aulento; print(os.environ.get('AULENTO_USER'))"
    entorno = {k: v for k, v in __import__("os").environ.items() if not k.startswith(("AULENTO_", "STUDY_ENGINE_"))}
    entorno["STUDY_ENGINE_USER"] = "cuenta-vieja"
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=entorno, timeout=120, check=False)
    assert salida.stdout.strip() == "cuenta-vieja"


# --- R6: la suite no hereda las variables viejas de quien la corre ---


def test_la_suite_corre_sin_variables_con_el_nombre_anterior():
    import os

    assert [n for n in os.environ if n.startswith("STUDY_ENGINE_")] == []


# --- R7: la carpeta de datos ---


@pytest.fixture
def hogar(monkeypatch, tmp_path):
    """Las dos carpetas por defecto dentro de un hogar de prueba, sin variable del directorio."""
    nueva, anterior = tmp_path / ".aulento", tmp_path / ".study-engine"
    monkeypatch.setattr(config, "DEFAULT_DATA_DIR", nueva)
    monkeypatch.setattr(config, "CARPETA_ANTERIOR", anterior)
    monkeypatch.delenv("AULENTO_DATA_DIR", raising=False)
    monkeypatch.delenv("AULENTO_DB_PATH", raising=False)
    return nueva, anterior


def test_con_solo_la_carpeta_anterior_se_renombra(hogar):
    nueva, anterior = hogar
    anterior.mkdir()
    (anterior / "study_engine.db").write_text("datos", encoding="utf-8")

    assert config.mudar_carpeta_anterior() == nueva
    assert not anterior.exists()
    assert (nueva / "study_engine.db").read_text(encoding="utf-8") == "datos"
    assert config.get_db_path() == nueva / "study_engine.db"


def test_con_las_dos_carpetas_no_toca_nada(hogar):
    nueva, anterior = hogar
    nueva.mkdir()
    anterior.mkdir()

    assert config.mudar_carpeta_anterior() is None
    assert nueva.is_dir() and anterior.is_dir()
    assert config.get_data_dir() == nueva


def test_con_la_variable_del_directorio_no_toca_nada(hogar, monkeypatch, tmp_path):
    _, anterior = hogar
    anterior.mkdir()
    monkeypatch.setenv("AULENTO_DATA_DIR", str(tmp_path / "elegida"))

    assert config.mudar_carpeta_anterior() is None
    assert anterior.is_dir()


def test_si_el_renombre_falla_sigue_con_la_carpeta_anterior_y_avisa(hogar, monkeypatch, caplog):
    nueva, anterior = hogar
    anterior.mkdir()

    def falla(self, destino):
        raise PermissionError("archivo abierto")

    monkeypatch.setattr(Path, "rename", falla)
    with caplog.at_level(logging.WARNING):
        assert config.mudar_carpeta_anterior() is None
    assert "archivo abierto" in caplog.text
    assert not nueva.exists()
    assert config.get_data_dir() == anterior


def test_sin_ninguna_carpeta_se_usa_la_nueva(hogar):
    nueva, _ = hogar
    assert config.mudar_carpeta_anterior() is None
    assert config.get_data_dir() == nueva


def test_la_cli_muda_la_carpeta_al_arrancar(hogar):
    from typer.testing import CliRunner

    from aulento.cli.app import cli

    nueva, anterior = hogar
    anterior.mkdir()
    CliRunner().invoke(cli, ["db", "status"])
    assert nueva.is_dir() and not anterior.exists()


def test_crear_la_carpeta_de_la_base_muda_antes_la_anterior(hogar):
    """Si la carpeta nueva se creara vacía primero, los datos quedarían atrás en la anterior."""
    nueva, anterior = hogar
    anterior.mkdir()
    (anterior / "study_engine.db").write_text("datos", encoding="utf-8")

    assert config.ensure_data_dir() == nueva / "study_engine.db"
    assert (nueva / "study_engine.db").read_text(encoding="utf-8") == "datos"
    assert not anterior.exists()


def test_pedir_el_directorio_de_datos_muda_la_anterior(hogar):
    nueva, anterior = hogar
    anterior.mkdir()
    assert config.get_data_dir() == nueva
    assert not anterior.exists()


def test_una_nota_exportada_con_el_autor_anterior_no_cuenta_como_editada():
    from aulento.roadmap.lesson_studio import _sin_fecha_de_generacion

    vieja = "---\ngenerated:\n  by: process:study-engine\n  at: 2026-10-01T00:00:00Z\n---\n\nCuerpo\n"
    nueva = "---\ngenerated:\n  by: process:aulento\n  at: 2026-11-05T00:00:00Z\n---\n\nCuerpo\n"
    assert _sin_fecha_de_generacion(vieja) == _sin_fecha_de_generacion(nueva)


# --- R8: lo que guarda datos no cambia ---


def test_los_nombres_que_guardan_datos_siguen_iguales():
    """La base local y los UID del calendario (los de la nube y el despliegue: `test_nube_marca_aulento.py`)."""
    assert config.NOMBRE_DE_LA_BASE == "study_engine.db"
    assert config.DEFAULT_DB_PATH.name == "study_engine.db"
    assert "@studyengine.local" in (SRC / "aulento" / "connectors" / "google_calendar.py").read_text(encoding="utf-8")
