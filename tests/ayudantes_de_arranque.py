"""Lo que comparten las pruebas de los scripts de arranque local y las del despliegue (039): se publica con el core,
que trae `start.sh` y `start.bat` (051, R8)."""

import os
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent.parent
START_SH = RAIZ / "start.sh"
START_BAT = RAIZ / "start.bat"


def bash_que_sirve() -> str | None:
    """Un bash que responde (el de Git en Windows primero); None si la máquina no tiene uno."""
    candidatos = []
    git_bash = shutil.which("bash", path=os.environ.get("PROGRAMFILES", "C:\\Program Files") + "\\Git\\bin")
    if git_bash:
        candidatos.append(git_bash)
    candidatos.append(shutil.which("bash"))
    for bash in candidatos:
        if bash is None:
            continue
        try:
            prueba = subprocess.run(
                [bash, "-c", "echo ok"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if prueba.stdout.strip() == "ok":
                return bash
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None
