"""Tests del set propio de íconos de Aulento (sprite SVG, CSS, Au.icono y accesibilidad)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
ESTATICO = RAIZ / "src" / "aulento" / "web" / "static"
ICONS_DIR = ESTATICO / "icons"
SPRITE = ICONS_DIR / "aulento-iconos.svg"
CATALOGO = ICONS_DIR / "catalogo.html"
INDEX = ESTATICO / "index.html"
COMPONENTES_JS = ESTATICO / "componentes.js"
COMPONENTES_CSS = ESTATICO / "componentes.css"

SVG_NS = "http://www.w3.org/2000/svg"

# Lista completa de nombres de la tabla común (incluidos los 3 de tema)
ICONOS_TABLA: tuple[str, ...] = (
    # Navegación y secciones
    "inicio", "cursos", "libros", "lectura", "agenda", "rutas",
    "repaso", "cerebro", "indice", "tarjetas", "notas", "cuaderno",
    "estadisticas", "examen", "objetivo", "ajustes", "cuenta", "cuentas",
    "plataforma", "trabajo", "brujula", "grafo", "modulo",
    # Acciones
    "cerrar", "ok", "agregar", "quitar", "guardar", "borrar", "editar",
    "copiar", "lista", "descargar", "importar", "subir", "buscar",
    "recargar", "ver", "enlace", "externo", "siguiente", "saltar",
    "pausa", "detener", "ordenar", "fijar", "etiqueta", "carpeta",
    "documento", "paquete", "imagen", "video", "menu", "atajos", "ayuda",
    # Estado y avisos
    "alerta", "cargando", "punto", "bloqueado", "desbloqueado", "seguridad",
    "salud", "vacio", "celebrar", "logro", "meta", "idea",
    # IA, tiempo y estudio
    "ia", "generar", "rapido", "empezar", "analizar", "foco", "reloj",
    "pomodoro", "descanso", "racha", "idioma", "crecimiento", "fruto",
    "premium", "pago",
    # Dispositivos y conexiones
    "voz", "audio", "celular", "computadora", "web", "nube",
    "conexion", "integracion", "clave", "apariencia",
    # Tema (barra superior)
    "tema-oscuro", "tema-claro", "tema-sistema",
)

COLORES_FIJOS_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(|"
    r"\b(?:black|white|red|blue|green|yellow|orange|purple|pink|gray|grey|silver|gold|cyan|magenta)\b",
    re.IGNORECASE,
)


def _simbolos_sprite() -> list[ET.Element]:
    raiz = ET.fromstring(SPRITE.read_text(encoding="utf-8"))
    return raiz.findall(f"{{{SVG_NS}}}symbol")


def _nombres_sprite() -> list[str]:
    return [s.attrib["id"].removeprefix("i-") for s in _simbolos_sprite()]


def test_todos_los_nombres_de_la_tabla_estan_en_el_sprite() -> None:
    simbolos = _simbolos_sprite()
    ids = [s.attrib.get("id", "") for s in simbolos]
    assert all(i.startswith("i-") for i in ids), [i for i in ids if not i.startswith("i-")]
    nombres = _nombres_sprite()
    assert len(nombres) == len(set(nombres)), "hay símbolos repetidos en el sprite"
    faltan = sorted(set(ICONOS_TABLA) - set(nombres))
    sobran = sorted(set(nombres) - set(ICONOS_TABLA))
    assert not faltan and not sobran, {"faltan": faltan, "sobran": sobran}


def test_cada_simbolo_tiene_viewbox_y_currentcolor_sin_colores_fijos() -> None:
    simbolos = _simbolos_sprite()
    assert simbolos
    for simbolo in simbolos:
        sid = simbolo.attrib["id"]
        assert simbolo.attrib.get("viewBox") == "0 0 24 24", sid
        atributos_texto = " ".join(
            f"{k}={v}"
            for el in simbolo.iter()
            for k, v in el.attrib.items()
        )
        assert "currentColor" in atributos_texto, f"{sid} no usa currentColor"
        fijos = COLORES_FIJOS_RE.findall(atributos_texto)
        assert not fijos, f"{sid} tiene colores fijos: {fijos}"

    # El punto es un círculo chico (r=4) con fill="currentColor"
    punto = next(s for s in simbolos if s.attrib["id"] == "i-punto")
    circulo = punto.find(f"{{{SVG_NS}}}circle")
    assert circulo is not None
    assert circulo.attrib.get("r") == "4"
    assert circulo.attrib.get("fill") == "currentColor"

    # Motivo de marca (nodos r=2 unidos por líneas) en los 5 íconos clave
    for nombre in ("rutas", "grafo", "indice", "cerebro", "modulo"):
        sim = next(s for s in simbolos if s.attrib["id"] == f"i-{nombre}")
        nodos = [c for c in sim.findall(f"{{{SVG_NS}}}circle") if c.attrib.get("r") == "2"]
        assert len(nodos) >= 2, f"i-{nombre} debería usar nodos r=2 del motivo de marca"


def test_au_iconos_coincide_con_el_sprite() -> None:
    js = COMPONENTES_JS.read_text(encoding="utf-8")
    bloque = re.search(r"const ICONOS = Object\.freeze\(\[(.*?)\]\);", js, re.DOTALL)
    assert bloque is not None, "no se encontró const ICONOS in componentes.js"
    en_js = re.findall(r"'([a-z0-9-]+)'", bloque.group(1))
    assert en_js == _nombres_sprite()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está instalado en este entorno")
def test_au_icono_devuelve_marcado_accesible_y_valida_nombres() -> None:
    node_bin = shutil.which("node")
    assert node_bin is not None
    script = """
    const fs = require('fs');
    const vm = require('vm');
    const code = fs.readFileSync(process.argv[1], 'utf8');
    const sandbox = {
      window: {},
      document: { addEventListener() {}, getElementById() { return null; }, body: { classList: { add() {}, remove() {} } } },
      Element: class {},
      CustomEvent: class {},
      console,
    };
    vm.runInNewContext(code, sandbox);
    const Au = sandbox.window.Au;
    const basico = Au.icono('guardar');
    const conEtiqueta = Au.icono('alerta', { etiqueta: 'Aviso <1>' });
    const conClase = Au.icono('cargando', { clase: 'au-icono--chico au-icono--girando' });
    const vacioHtml = Au.vacio({ titulo: 'Sin datos' });
    const btnNombre = Au.boton({ texto: 'Guardar', icono: 'guardar' });
    const btnSvg = Au.boton({ texto: 'Guardar', icono: Au.icono('guardar') });
    let errorMsg = '';
    try { Au.icono('inexistente-xyz'); } catch (e) { errorMsg = e.message; }
    console.log(JSON.stringify({
      basico, conEtiqueta, conClase, vacioHtml, btnNombre, btnSvg, errorMsg,
      count: Au.ICONOS.length
    }));
    """
    res = subprocess.run(
        [node_bin, "-e", script, str(COMPONENTES_JS)],
        capture_output=True,
        text=True,
        check=True,
    )
    datos = json.loads(res.stdout)
    assert datos["count"] == len(ICONOS_TABLA)
    assert datos["basico"] == (
        '<svg class="au-icono" aria-hidden="true" focusable="false">'
        '<use href="/static/icons/aulento-iconos.svg#i-guardar"></use></svg>'
    )
    assert 'role="img"' in datos["conEtiqueta"]
    assert 'aria-label="Aviso &lt;1&gt;"' in datos["conEtiqueta"]
    assert "aria-hidden" not in datos["conEtiqueta"]
    assert 'class="au-icono au-icono--chico au-icono--girando"' in datos["conClase"]
    assert "#i-vacio" in datos["vacioHtml"] and "📭" not in datos["vacioHtml"]
    assert "#i-guardar" in datos["btnNombre"] and "&lt;svg" not in datos["btnNombre"]
    assert "#i-guardar" in datos["btnSvg"] and "&lt;svg" not in datos["btnSvg"]
    assert "inexistente-xyz" in datos["errorMsg"]


def test_todos_los_iconos_usados_en_el_front_existen_en_el_sprite() -> None:
    sprite_nombres = set(_nombres_sprite())
    archivos = [
        INDEX,
        ESTATICO / "app.js",
        COMPONENTES_JS,
        ESTATICO / "mcp-remoto.js",
        *sorted((ESTATICO / "js").glob("*.js")),
    ]
    desconocidos: list[str] = []
    for archivo in archivos:
        if not archivo.exists():
            continue
        texto = archivo.read_text(encoding="utf-8")
        # Referencias directas #i-nombre (ignora interpolaciones #i-${...})
        for nombre in re.findall(r"#i-([a-z][a-z0-9-]*)", texto):
            if nombre not in sprite_nombres:
                desconocidos.append(f"{archivo.name}: #i-{nombre}")
        # Llamadas Au.icono('nombre') o Au.icono("nombre")
        for _, nombre in re.findall(r"""Au\.icono\(\s*(['"])([a-z0-9-]+)\1""", texto):
            if nombre not in sprite_nombres:
                desconocidos.append(f"{archivo.name}: Au.icono('{nombre}')")
    assert not desconocidos, f"Íconos usados que no existen en el sprite: {desconocidos}"


class _AnalizadorBotones(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pila: list[dict[str, object]] = []
        self.sin_nombre: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "button":
            self.pila.append({"attrs": dict(attrs), "texto": [], "linea": self.getpos()[0], "en_svg": 0})
        elif self.pila and tag == "svg":
            self.pila[-1]["en_svg"] = int(self.pila[-1]["en_svg"]) + 1  # type: ignore[arg-type]

    def handle_data(self, data: str) -> None:
        if self.pila and int(self.pila[-1]["en_svg"]) == 0:  # type: ignore[arg-type]
            self.pila[-1]["texto"].append(data)  # type: ignore[attr-defined]

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg" and self.pila and int(self.pila[-1]["en_svg"]) > 0:  # type: ignore[arg-type]
            self.pila[-1]["en_svg"] = int(self.pila[-1]["en_svg"]) - 1  # type: ignore[arg-type]
        elif tag == "button" and self.pila:
            actual = self.pila.pop()
            attrs: dict[str, str | None] = actual["attrs"]  # type: ignore[assignment]
            texto = "".join(actual["texto"]).strip()  # type: ignore[arg-type]
            tiene_nombre = any(
                (
                    texto,
                    (attrs.get("aria-label") or "").strip(),
                    (attrs.get("aria-labelledby") or "").strip(),
                    (attrs.get("title") or "").strip(),
                )
            )
            if not tiene_nombre:
                ident = attrs.get("id") or attrs.get("data-accion") or "(sin id)"
                self.sin_nombre.append(f"línea {actual['linea']}: {ident}")


def test_ningun_boton_de_index_queda_sin_nombre_accesible() -> None:
    analizador = _AnalizadorBotones()
    analizador.feed(INDEX.read_text(encoding="utf-8"))
    assert not analizador.sin_nombre, f"Botones sin nombre accesible en index.html: {analizador.sin_nombre}"


def test_componentes_css_define_clases_de_icono() -> None:
    css = COMPONENTES_CSS.read_text(encoding="utf-8")
    for clase in (".au-icono", ".au-icono--chico", ".au-icono--grande", ".au-icono--girando"):
        assert clase in css
    assert "prefers-reduced-motion" in css
    assert "--au-duracion-" in css


def test_catalogo_html_muestra_todos_los_iconos_sin_js_externo() -> None:
    html = CATALOGO.read_text(encoding="utf-8")
    assert "../componentes.css" in html
    assert "../css/paleta.css" in html
    assert "<script" not in html.lower()
    assert "data-tema=" not in html
    for nombre in _nombres_sprite():
        assert f"#i-{nombre}" in html
