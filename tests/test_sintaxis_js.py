"""Tests de verificación sintáctica para archivos JavaScript del core (064).

Verifica que todos los archivos .js estáticos de la aplicación compilen sin errores
de sintaxis usando `node --check`. Se saltea si Node.js no está instalado.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
STATIC_DIRS = [RAIZ / "src" / "aulento" / "web" / "static"]

JS_FILES = [
    p for d in STATIC_DIRS if d.is_dir() for p in sorted(d.rglob("*.js"))
]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está instalado en este entorno")
@pytest.mark.parametrize("js_file", JS_FILES, ids=lambda p: p.name)
def test_sintaxis_javascript(js_file: Path) -> None:
    """Verifica con node --check que el archivo JavaScript tenga sintaxis válida."""
    node_bin = shutil.which("node")
    assert node_bin is not None
    res = subprocess.run(
        [node_bin, "--check", str(js_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Error de sintaxis en {js_file}:\n{res.stderr}"
