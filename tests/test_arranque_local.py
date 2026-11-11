"""Scripts de arranque local ejecutados de verdad, y la interfaz web dentro del paquete (039, R7, R9)."""

import fnmatch
import os
import re
import subprocess
import tomllib

import pytest
from ayudantes_de_arranque import RAIZ, START_BAT, bash_que_sirve

# --- start.bat: cada comprobación está atada a su rama ---


def test_start_bat_ata_la_version_y_el_puerto_a_sus_ramas():
    texto = START_BAT.read_text(encoding="utf-8")
    # El resultado de cada comprobación de versión corta el script
    for comprobacion in ('python -c "!VERSION_MINIMA!"', '"!VENV_PYTHON!" -c "!VERSION_MINIMA!"'):
        assert re.search(re.escape(comprobacion) + r"\nif errorlevel 1 \(\n(?:.*\n){0,4}?\s*exit /b 1\n", texto)
    # El 8001 se elige solo en la rama en que findstr encontró el 8000 escuchando
    assert re.search(r'findstr [^\n]*:8000[^\n]*\nif !errorlevel! equ 0 \(\n(?:.*\n){0,3}?\s*set "PORT=8001"\n', texto)


# --- start.sh ejecutado con un Python falso ---

PYTHON_DEL_SISTEMA = """#!/usr/bin/env bash
# Python falso del PATH: informa la versión que pide la prueba
if [ "$1" = "-V" ]; then echo "Python $VERSION_FALSA"; exit 0; fi
if [ "$1" = "-c" ]; then [ "$VERSION_OK" = "1" ]; exit $?; fi
exit 0
"""

PYTHON_DEL_ENTORNO = """#!/usr/bin/env bash
# Python falso de .venv: registra lo que se le pide en vez de hacerlo
case "$1 $2" in
  "-c "*socket*) [ "$PUERTO_OCUPADO" = "1" ]; exit $? ;;
  "-c "*) exit 0 ;;
  "-m pip") echo "pip $*" >> "$REGISTRO"; exit 0 ;;
  "-m aulento") echo "arranque $*" >> "$REGISTRO"; exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def bash():
    encontrado = bash_que_sirve()
    if encontrado is None:
        pytest.skip("sin bash que funcione en la máquina")
    return encontrado


@pytest.fixture
def instalacion(tmp_path):
    """Copia de start.sh con sus archivos de dependencias, un Python del sistema falso y un `.venv` falso."""
    for nombre in ("start.sh", "requirements.txt", "pyproject.toml"):
        (tmp_path / nombre).write_bytes((RAIZ / nombre).read_bytes())
    sistema = tmp_path / "bin"
    sistema.mkdir()
    for nombre in ("python3", "python"):
        (sistema / nombre).write_text(PYTHON_DEL_SISTEMA, encoding="utf-8", newline="\n")
    entorno = tmp_path / ".venv" / "bin"
    entorno.mkdir(parents=True)
    (entorno / "python").write_text(PYTHON_DEL_ENTORNO, encoding="utf-8", newline="\n")
    return tmp_path


def _correr(bash, instalacion, **variables):
    registro = instalacion / "registro.txt"
    registro.unlink(missing_ok=True)
    entorno = {**os.environ, "REGISTRO": "registro.txt", **variables}
    # El Python falso va primero en el PATH, delante del real
    entorno["PATH"] = str(instalacion / "bin") + os.pathsep + entorno.get("PATH", "")
    resultado = subprocess.run(
        [bash, "-c", "chmod +x bin/* .venv/bin/python && exec bash start.sh"],
        cwd=instalacion,
        env=entorno,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    lineas = registro.read_text(encoding="utf-8").splitlines() if registro.exists() else []
    return resultado, lineas


VERSION_VALIDA = {"VERSION_FALSA": "3.12.1", "VERSION_OK": "1", "PUERTO_OCUPADO": "0"}


def test_start_sh_con_python_viejo_sale_con_1_y_lo_dice(bash, instalacion):
    resultado, lineas = _correr(bash, instalacion, VERSION_FALSA="3.10.4", VERSION_OK="0")

    assert resultado.returncode == 1, resultado.stdout + resultado.stderr
    assert "3.11" in resultado.stdout and "3.10.4" in resultado.stdout
    assert lineas == []


@pytest.mark.parametrize(("ocupado", "puerto"), [("0", "8000"), ("1", "8001")])
def test_start_sh_arranca_en_127_0_0_1_y_elige_el_puerto_libre(bash, instalacion, ocupado, puerto):
    resultado, lineas = _correr(bash, instalacion, **{**VERSION_VALIDA, "PUERTO_OCUPADO": ocupado})

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    arranques = [linea for linea in lineas if linea.startswith("arranque ")]
    assert arranques == [f"arranque -m aulento web start --host 127.0.0.1 --port {puerto} --open-browser"]


def test_start_sh_reinstala_solo_si_cambian_las_dependencias(bash, instalacion):
    def instalaciones():
        resultado, lineas = _correr(bash, instalacion, **VERSION_VALIDA)
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        return [linea for linea in lineas if linea.startswith("pip ") and "-r requirements.txt" in linea]

    assert len(instalaciones()) == 1
    assert instalaciones() == []
    for nombre in ("requirements.txt", "pyproject.toml"):
        with (instalacion / nombre).open("a", encoding="utf-8") as archivo:
            archivo.write("\n# cambio\n")
        assert len(instalaciones()) == 1
        assert instalaciones() == []


# --- El paquete lleva la interfaz web ---


def _declarado(archivo: str, patrones: list[str]) -> bool:
    """Como setuptools: `*` no cruza carpetas, así que `web/static/*` no alcanza a `web/static/vendor/x`."""
    return any(
        fnmatch.fnmatchcase(archivo, patron) and archivo.count("/") == patron.count("/") for patron in patrones
    )


def test_el_paquete_declara_todos_los_archivos_que_no_son_python():
    """Sin `package-data`, el wheel de la imagen sale sin la interfaz web: `/api/health` responde y la app no se usa."""
    configuracion = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    patrones = configuracion["tool"]["setuptools"]["package-data"]["aulento"]
    paquete = RAIZ / "src" / "aulento"
    archivos = [
        archivo.relative_to(paquete).as_posix()
        for archivo in paquete.rglob("*")
        if archivo.is_file() and archivo.suffix not in {".py", ".pyc"} and "__pycache__" not in archivo.parts
    ]

    assert "web/static/index.html" in archivos and "web/static/vendor/mermaid.min.js" in archivos
    assert [archivo for archivo in archivos if not _declarado(archivo, patrones)] == []
