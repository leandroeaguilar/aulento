"""Tema claro/oscuro: la paleta en variables (css/paleta.css) y cómo la usa el front."""

import re
from pathlib import Path

from scripts import generar_paleta

RAIZ = Path(__file__).resolve().parents[1]
ESTATICO = RAIZ / "src" / "aulento" / "web" / "static"
PALETA_CSS = ESTATICO / "css" / "paleta.css"


def _bloques(css: str) -> dict[str, dict[str, str]]:
    """Selector -> {variable: valor} de cada bloque de paleta.css."""
    bloques = {}
    for selector, cuerpo in re.findall(r"(:root[^{]*)\{([^}]*)\}", css):
        bloques[selector.strip()] = dict(re.findall(r"--au-([a-z0-9-]+):\s*([^;]+);", cuerpo))
    return bloques


def test_paleta_css_esta_al_dia_con_el_generador():
    assert generar_paleta.main(["--comprobar"]) == 0, "correr python scripts/generar_paleta.py"


def test_el_tema_oscuro_conserva_los_colores_de_tailwind():
    """Cero cambio visual en el tema por defecto: los valores son los de Tailwind v3.4.17."""
    oscuro = _bloques(PALETA_CSS.read_text(encoding="utf-8"))[":root"]
    assert oscuro["slate-950"] == "2 6 23"
    assert oscuro["slate-900"] == "15 23 42"
    assert oscuro["sky-400"] == "56 189 248"
    assert oscuro["blanco"] == "255 255 255"
    for familia, tonos in generar_paleta.PALETA.items():
        for tono, hexa in tonos.items():
            assert oscuro[f"{familia}-{tono}"] == generar_paleta.triplete(hexa)


def test_el_tema_claro_y_el_de_sistema_definen_las_mismas_variables():
    bloques = _bloques(PALETA_CSS.read_text(encoding="utf-8"))
    oscuro = bloques[":root"]
    claro = bloques[':root[data-tema="claro"]']
    sistema = bloques[':root[data-tema="sistema"]']
    assert set(claro) == set(oscuro)
    assert sistema == claro
    assert claro["slate-950"] != oscuro["slate-950"], "el tema claro tiene que cambiar el fondo"


def test_tailwind_config_usa_las_mismas_familias_que_la_paleta():
    config = (RAIZ / "tailwind.config.js").read_text(encoding="utf-8")
    bloque = re.search(r"const FAMILIAS = \[(.*?)\];", config, re.DOTALL).group(1)
    assert re.findall(r"'([a-z]+)'", bloque) == list(generar_paleta.PALETA)
    assert "rgb(var(--au-${nombre}) / <alpha-value>)" in config


def test_los_tokens_de_color_salen_de_la_paleta():
    """Un token --au-* con hex propio no cambiaría con el tema."""
    css = (ESTATICO / "componentes.css").read_text(encoding="utf-8")
    raiz = css[css.index(":root") : css.index("}", css.index(":root"))]
    con_hex = [linea.strip() for linea in raiz.splitlines() if re.search(r"--au-.*#[0-9a-fA-F]{3,8}\b", linea)]
    assert not con_hex, f"tokens con color fijo: {con_hex}"


def test_index_carga_el_tema_antes_que_los_estilos():
    html = (ESTATICO / "index.html").read_text(encoding="utf-8")
    tema = html.index('src="/static/js/tema.js')
    paleta = html.index('href="/static/css/paleta.css')
    componentes = html.index('href="/static/componentes.css')
    assert tema < paleta < componentes
    etiqueta = re.search(r"<script[^>]*tema\.js[^>]*>", html).group(0)
    assert "defer" not in etiqueta and "async" not in etiqueta, "tema.js tiene que correr antes de pintar"


def test_el_service_worker_guarda_el_tema_y_la_paleta():
    sw = (ESTATICO / "sw.js").read_text(encoding="utf-8")
    assert "'/static/js/tema.js'" in sw
    assert "'/static/css/paleta.css'" in sw


def test_la_configuracion_tiene_el_selector_de_tema():
    html = (ESTATICO / "index.html").read_text(encoding="utf-8")
    selector = re.search(r'<select[^>]*id="config-tema-select"[^>]*>(.*?)</select>', html, re.DOTALL)
    assert selector, "falta el selector de tema en Configuración"
    assert 'data-accion="config-cambiar-tema"' in selector.group(0)
    assert re.findall(r'value="([a-z]+)"', selector.group(1)) == ["oscuro", "claro", "sistema"]
    config_js = (ESTATICO / "js" / "pantalla-config.js").read_text(encoding="utf-8")
    assert "'config-cambiar-tema'" in config_js
