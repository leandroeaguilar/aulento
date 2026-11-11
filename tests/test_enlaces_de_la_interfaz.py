"""Los enlaces directos de la interfaz a la API apuntan a rutas GET que existen (descargas, exportaciones)."""

import re
from pathlib import Path

from aulento.web.app import create_app

INDEX = Path(__file__).resolve().parent.parent / "src" / "aulento" / "web" / "static" / "index.html"


def _rutas_get() -> list[re.Pattern]:
    patrones = []
    for ruta, operaciones in create_app().openapi()["paths"].items():
        if "get" in operaciones:
            patrones.append(re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", ruta) + "$"))
    return patrones


def test_cada_enlace_a_la_api_del_index_es_una_ruta_get_existente():
    enlaces = set(re.findall(r'href="(/api/[^"?#]+)', INDEX.read_text(encoding="utf-8")))
    assert enlaces, "el index no tiene enlaces directos a la API: revisar el patrón del test"
    patrones = _rutas_get()
    rotos = sorted(e for e in enlaces if not any(p.match(e) for p in patrones))
    assert rotos == [], f"enlaces del index que no son rutas GET de la API: {rotos}"
