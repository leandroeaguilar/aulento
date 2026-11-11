"""071 R13: patrones que rompen la versión de celular, frenados sin abrir un navegador.

- R5: una capa de modal (`fixed inset-0` con `items-center`) sin `au-modal` (072), que corta los modales altos.
- R2: una barra `flex` en fila con más de tres botones, sin `flex-wrap` ni desplazamiento (`scroll-x-pista`), que
  se ensancha en vez de bajar de línea.
- R7: un `text-[9px]`, `text-[10px]` o `text-[11px]` (o menor) sin variante para el celular (`text-xs sm:text-[11px]`). Los adornos con
  `aria-hidden="true"` no cuentan.

En `app.js` el HTML vive en plantillas de JS: se extraen y se revisan igual. Los archivos de la nube los revisa
`test_nube_responsive_estatico.py` con las mismas reglas.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVOS = (
    "src/aulento/web/static/index.html",
    "src/aulento/web/static/app.js",
    *(
        p.relative_to(RAIZ).as_posix()
        for p in sorted((RAIZ / "src" / "aulento" / "web" / "static" / "js").glob("*.js"))
    ),
)

VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
TEXTO_CHICO = re.compile(r"(?<![\w:\-\[])text-\[(?:[0-9]|1[01])px\]")
MODAL_EN_JS = re.compile(r"""fixed inset-0[^"'`]*?items-center[^"'`]*""")
SIN_FILA = {"flex-col", "flex-wrap", "flex-col-reverse", "hidden", "overflow-x-auto", "scroll-x-pista"}


class _Revisor(HTMLParser):
    def __init__(self, linea_base: int):
        super().__init__(convert_charrefs=True)
        self.linea_base = linea_base
        self.pila: list[dict] = []
        self.hallazgos: list[tuple[str, int, str]] = []

    def _linea(self) -> int:
        return self.linea_base + self.getpos()[0] - 1

    def handle_starttag(self, tag, attrs):
        datos = dict(attrs)
        clases = (datos.get("class") or "").split()
        linea = self._linea()
        if self.pila and tag in ("button", "a"):
            self.pila[-1]["botones"] += 1
        if "fixed" in clases and "inset-0" in clases and "items-center" in clases and "au-modal" not in clases:
            self.hallazgos.append(("modal", linea, " ".join(clases)[:90]))
        if TEXTO_CHICO.search(" ".join(clases)) and datos.get("aria-hidden") != "true":
            self.hallazgos.append(("texto", linea, " ".join(clases)[:90]))
        if tag in VACIOS:
            return
        fila = "flex" in clases and not SIN_FILA.intersection(clases)
        self.pila.append({"tag": tag, "fila": fila, "botones": 0, "linea": linea, "clases": " ".join(clases)[:90]})

    def handle_endtag(self, tag):
        # Cierra hasta la etiqueta que corresponde; las plantillas cortadas pueden dejar la pila torcida
        for i in range(len(self.pila) - 1, -1, -1):
            if self.pila[i]["tag"] == tag:
                for nodo in self.pila[i:]:
                    if nodo["fila"] and nodo["botones"] > 3:
                        self.hallazgos.append(("barra", nodo["linea"], nodo["clases"]))
                del self.pila[i:]
                return


def _plantillas(texto: str):
    """Plantillas de JS (entre comillas invertidas) con su línea de inicio; las `${…}` se reemplazan por un hueco."""
    i = 0
    while (inicio := texto.find("`", i)) != -1:
        j, profundidad, partes = inicio + 1, 0, []
        while j < len(texto):
            c = texto[j]
            if profundidad == 0 and c == "`":
                break
            if profundidad == 0 and texto.startswith("${", j):
                profundidad, j = 1, j + 2
                partes.append("x")
                continue
            if profundidad:
                profundidad += {"{": 1, "}": -1}.get(c, 0)
            elif c == "\\":
                partes.append(texto[j : j + 2])
                j += 2
                continue
            else:
                partes.append(c)
            j += 1
        yield texto.count("\n", 0, inicio) + 1, "".join(partes)
        i = j + 1


def _hallazgos(ruta: str) -> list[tuple[str, int, str]]:
    texto = (RAIZ / ruta).read_text(encoding="utf-8")
    trozos = [(1, texto)] if ruta.endswith(".html") else list(_plantillas(texto))
    hallazgos = []
    for linea, trozo in trozos:
        revisor = _Revisor(linea)
        revisor.feed(trozo)
        revisor.close()
        hallazgos.extend(revisor.hallazgos)
    if ruta.endswith(".js"):
        # Las clases que se arman en strings sueltos o con `${…}` adentro no pasan por el parser: se miran por línea
        vistos = {(t, linea) for t, linea, _ in hallazgos}
        for numero, linea in enumerate(texto.splitlines(), 1):
            if "aria-hidden" not in linea and TEXTO_CHICO.search(linea) and ("texto", numero) not in vistos:
                hallazgos.append(("texto", numero, linea.strip()[:90]))
            for clase in MODAL_EN_JS.findall(linea):
                if "au-modal" not in clase and ("modal", numero) not in vistos:
                    hallazgos.append(("modal", numero, clase[:90]))
    return hallazgos


@pytest.mark.parametrize("ruta", ARCHIVOS)
@pytest.mark.parametrize("tipo", ("modal", "barra", "texto"))
def test_r13_sin_patrones_que_rompen_el_celular(ruta: str, tipo: str):
    encontrados = [(linea, fragmento) for t, linea, fragmento in _hallazgos(ruta) if t == tipo]
    assert not encontrados, f"{len(encontrados)} {tipo} en {ruta}: " + "; ".join(
        f"L{linea} «{fragmento}»" for linea, fragmento in encontrados[:8]
    )


def test_el_revisor_detecta_los_tres_patrones():
    revisor = _Revisor(1)
    revisor.feed(
        '<div class="fixed inset-0 flex items-center"></div>'
        '<div class="flex gap-2"><button></button><button></button><a></a><button></button></div>'
        '<span class="text-[10px] uppercase">x</span><span class="text-xs sm:text-[10px]">ok</span>'
        '<span class="text-[11px]" aria-hidden="true">·</span>'
        '<div class="flex flex-wrap"><button></button><button></button><button></button><button></button></div>'
        '<div class="fixed inset-0 flex items-center au-modal"></div>'
    )
    assert sorted(t for t, _, _ in revisor.hallazgos) == ["barra", "modal", "texto"]


def test_las_plantillas_de_js_se_revisan():
    js = "const a = 1;\nel.innerHTML = `<div class=\"flex\">${items.map(i => `<b>${i}</b>`).join('')}\n<span class=\"text-[11px]\">x</span></div>`;"
    trozos = list(_plantillas(js))
    assert trozos[0][0] == 2
    revisor = _Revisor(trozos[0][0])
    revisor.feed(trozos[0][1])
    assert [(t, linea) for t, linea, _ in revisor.hallazgos] == [("texto", 3)]
