"""Concatenación y lista de los archivos JavaScript del front-end de Aulento en orden de carga."""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
STATIC = RAIZ / "src" / "aulento" / "web" / "static"
INDEX_HTML = STATIC / "index.html"


def archivos_del_front() -> list[Path]:
    """Archivos JS del front en el orden en que los carga index.html: los que van después de capacidades.js, hasta app.js inclusive.

    Un `src` que apunta a un archivo que no existe es un error: la página lo pediría y fallaría.
    """
    html = INDEX_HTML.read_text(encoding="utf-8")
    srcs = re.findall(r'<script\s+src="([^"]+)"', html)
    rutas: list[Path] = []
    in_range = False
    for src in srcs:
        limpio = src.split("?")[0]
        if limpio == "/static/capacidades.js":
            in_range = True
            continue
        if in_range:
            if limpio.startswith("/static/"):
                rel = limpio[len("/static/") :]
                ruta = STATIC / rel
                if not ruta.exists():
                    raise FileNotFoundError(f"index.html carga {limpio}, que no existe")
                rutas.append(ruta)
            if limpio == "/static/app.js":
                break
    return rutas


def js_del_front() -> str:
    """Contenido concatenado de todos los archivos de JS del front en orden de carga."""
    archivos = archivos_del_front()
    trozos = [arch.read_text(encoding="utf-8") for arch in archivos]
    return "\n".join(trozos)
