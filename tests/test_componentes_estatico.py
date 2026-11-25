"""072 R10: los componentes se cargan bien y las pantallas migradas no vuelven al marcado copiado.

Al migrar una pantalla se agrega a `PANTALLAS_MIGRADAS`; desde ahí su sección de `index.html` y su `pantalla-<tab>.js`
no pueden volver a armar a mano los patrones del catálogo (docs/COMPONENTES.md).
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
ESTATICO = RAIZ / "src" / "aulento" / "web" / "static"
INDEX = ESTATICO / "index.html"

# Se agrega cada pestaña al terminar su migración (tasks.md de la 072)
PANTALLAS_MIGRADAS: set[str] = {"dashboard", "fsrs", "schedule", "brain", "exams", "courses", "books", "notes", "config", "roadmap"}

# Marcado copiado que en una pantalla migrada tiene que ser un componente
PATRONES_COPIADOS = {
    "manejador en línea, onclick/onchange/... (usar data-accion)": re.compile(r"\bon[a-z]+="),
    "tarjeta a mano (usar au-tarjeta)": re.compile(r"\brounded-3xl\b"),
    "botón primario a mano (usar au-boton--primario)": re.compile(r"\bbg-sky-600 hover:bg-sky-500\b"),
    "insignia a mano (usar au-insignia)": re.compile(r"\bpx-2(?:\.5)? py-0\.5 rounded-full\b"),
    "texto chico a mano (los componentes ya lo resuelven)": re.compile(r"text-\[(?:[0-9]|1[01])px\]"),
    # El relleno de un componente sale de sus tokens y modificadores: un p-3 suelto lo desalinea del resto
    "relleno de Tailwind sobre un componente (usar un modificador)": re.compile(
        r'class="[^"]*\bau-(?:tarjeta|boton|campo__control|insignia|kpi|aviso|fila)\b[^"]*\bp[xytrbl]?-[0-9][^"]*"'
        r'|class="[^"]*\bp[xytrbl]?-[0-9][^"]*\bau-(?:tarjeta|boton|campo__control|insignia|kpi|aviso|fila)\b[^"]*"'
    ),
}


def _seccion_de_index(pestana: str) -> str:
    html = INDEX.read_text(encoding="utf-8")
    inicio = html.index(f'<section id="tab-{pestana}"')
    fin = html.find("<section id=\"tab-", inicio + 10)
    # La última pestaña termina en </main>: los modales y la barra inferior se controlan aparte
    return html[inicio : fin if fin != -1 else html.index("</main>", inicio)]


def _js_de_pantalla(pestana: str) -> str:
    ruta = ESTATICO / "js" / f"pantalla-{pestana}.js"
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def test_los_componentes_se_cargan_en_orden():
    html = INDEX.read_text(encoding="utf-8")
    # Hojas: Tailwind, después componentes, después movil (los componentes ganan por orden, no por !important)
    # Componentes, después Tailwind (sus utilidades, como hidden, pisan al componente) y al final movil.css
    assert html.index("/static/componentes.css") < html.index("/static/css/tailwind.css") < html.index("/static/movil.css")
    assert "cdn.tailwindcss.com" not in html
    # componentes.js antes que todo el JS de la app, que lo usa
    assert html.index("/static/componentes.js") < html.index("/static/capacidades.js") < html.index("/static/app.js")


def test_r11_el_catalogo_esta_documentado():
    doc = (RAIZ / "docs" / "COMPONENTES.md").read_text(encoding="utf-8")
    js = (ESTATICO / "componentes.js").read_text(encoding="utf-8")
    exportadas = re.search(r"window\.Au = Object\.freeze\(\{(.*?)\}\);", js, re.DOTALL).group(1)
    nombres = [n.strip() for n in exportadas.replace("\n", " ").split(",") if n.strip()]
    sin_documentar = [n for n in nombres if f"Au.{n}" not in doc]
    assert not sin_documentar, f"funciones de Au sin documentar en docs/COMPONENTES.md: {sin_documentar}"


def test_r3_toda_accion_usada_esta_registrada():
    """Un data-accion sin registrar no hace nada al tocarlo: se frena acá y no en el navegador."""
    # Solo el core: los archivos de la nube los revisa su propio test cuando migren (T10)
    front = [INDEX, *ESTATICO.glob("*.js"), *(ESTATICO / "js").glob("*.js")]
    texto = "\n".join(p.read_text(encoding="utf-8") for p in front)
    # componentes.js registra (au-cerrar-modal), pero sus comentarios traen ejemplos de uso que no son acciones reales
    uso = "\n".join(p.read_text(encoding="utf-8") for p in front if p.name != "componentes.js")
    usadas = set(re.findall(r'data-accion="([a-z0-9-]+)"', uso)) | set(re.findall(r"accion: '([a-z0-9-]+)'", uso))
    registradas = set(re.findall(r"acciones\.registrar\('([a-z0-9-]+)'", texto))
    # También las tablas de acciones de cada pantalla: [['nombre', fn], ...].forEach(... Au.acciones.registrar(...))
    for tabla in re.findall(r"\[\s*(\[\s*'[a-z0-9-]+',.*?)\]\.forEach\(\(\[nombre, fn\]\) => Au\.acciones\.registrar", texto, re.DOTALL):
        registradas |= set(re.findall(r"^\s*\['([a-z0-9-]+)',", tabla, re.MULTILINE))
    assert usadas <= registradas, f"acciones usadas y no registradas: {sorted(usadas - registradas)}"


@pytest.mark.parametrize("pestana", sorted(PANTALLAS_MIGRADAS) or ["(ninguna todavía)"])
def test_r10_las_pantallas_migradas_no_vuelven_al_marcado_copiado(pestana: str):
    if pestana not in PANTALLAS_MIGRADAS:
        pytest.skip("todavía no hay pantallas migradas")
    texto = _seccion_de_index(pestana) + "\n" + _js_de_pantalla(pestana)
    hallados = {nombre: len(p.findall(texto)) for nombre, p in PATRONES_COPIADOS.items() if p.search(texto)}
    assert not hallados, f"{pestana} volvió al marcado copiado: {hallados}"


def test_el_service_worker_precachea_todo_lo_que_carga_la_pagina():
    """Sin conexión, la PWA cae a la caché: si falta un script o una hoja, la página queda sin estilos o sin Au."""
    html = INDEX.read_text(encoding="utf-8")
    sw = (ESTATICO / "sw.js").read_text(encoding="utf-8")
    cargados = set(re.findall(r'(?:src|href)="(/static/[^"?]+\.(?:js|css))(?=["?])', html))
    precacheados = set(re.findall(r"'(/static/[^']+)'", sw))
    assert cargados <= precacheados, f"sin precachear: {sorted(cargados - precacheados)}"
    # Se piden con ?v=… y se guardan sin él
    assert "ignoreSearch: true" in sw


def test_r6_sin_important_en_las_hojas_propias():
    """Con Tailwind compilado y cargado antes, los componentes y movil.css ganan por orden (R6)."""
    for hoja in ("componentes.css", "movil.css"):
        texto = re.sub(r"/\*.*?\*/", "", (ESTATICO / hoja).read_text(encoding="utf-8"), flags=re.DOTALL)
        assert "!important" not in texto, f"{hoja} usa !important"


def test_r2_los_colores_de_los_componentes_salen_de_los_tokens():
    """Fuera de :root, componentes.css no define colores sueltos (salvo el blanco del texto sobre fondo de color)."""
    texto = re.sub(r"/\*.*?\*/", "", (ESTATICO / "componentes.css").read_text(encoding="utf-8"), flags=re.DOTALL)
    reglas = texto[texto.index("}", texto.index(":root")) + 1 :]
    sueltos = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", reglas)) - {"#fff"})
    assert not sueltos, f"colores sueltos en componentes.css: {sueltos}"


def test_r6_la_version_de_tailwind_queda_fijada():
    script = RAIZ / "scripts" / "compilar_css.py"
    if not script.exists():
        pytest.skip("el repo abierto no trae scripts/")
    texto = script.read_text(encoding="utf-8")
    assert re.search(r'^VERSION\s*=\s*"v3\.4\.17"', texto, re.MULTILINE), "la versión de Tailwind tiene que ser v3.4.17"


# Prefijos de utilidades de Tailwind: una clase con uno de estos que no está compilada es una utilidad nueva
UTILIDAD_TAILWIND = re.compile(
    r"^(?:[a-z-]+:)*-?(?:w|h|min-w|max-w|min-h|max-h|p[xytrbl]?|m[xytrbl]?|top|right|bottom|left|inset|gap|"
    r"space-[xy]|text|bg|border|rounded|shadow|font|leading|tracking|z|opacity|grid-cols|col-span|ring|"
    r"translate-[xy]|scale|rotate|duration|line-clamp|aspect)-"
)


def test_r6_toda_utilidad_de_index_html_esta_compilada():
    """El verify de CI recompila tailwind.css y falla si cambia: esto lo ve antes del push (T12 usó w-auto sin compilar)."""
    css = (ESTATICO / "css" / "tailwind.css").read_text(encoding="utf-8")
    compiladas = {re.sub(r"\\(.)", r"\1", c) for c in re.findall(r"\.((?:\\.|[A-Za-z0-9_-])+)", css)}
    usadas = {c for clases in re.findall(r'\bclass="([^"]*)"', INDEX.read_text(encoding="utf-8")) for c in clases.split()}
    faltan = sorted(c for c in usadas if UTILIDAD_TAILWIND.match(c) and c not in compiladas)
    assert not faltan, f"utilidades sin compilar (correr scripts/compilar_css.py o usar un componente): {faltan}"


def test_el_servidor_sirve_todo_el_js_del_front():
    """Los tests leen el JS del disco (tests/front.py): esto asegura además que la app sirve cada archivo."""
    from fastapi.testclient import TestClient
    from front import archivos_del_front

    from aulento.web.app import create_app

    cliente = TestClient(create_app())
    for ruta in archivos_del_front():
        url = "/static/" + ruta.relative_to(ESTATICO).as_posix()
        assert cliente.get(url).status_code == 200, url


def _clases_del_catalogo() -> set[str]:
    css = re.sub(r"/\*.*?\*/", "", (ESTATICO / "componentes.css").read_text(encoding="utf-8"), flags=re.DOTALL)
    return set(re.findall(r"\.(au-[a-z0-9_-]+)", css))


def test_r1_toda_clase_au_usada_existe_en_el_catalogo():
    """Una clase au-* inventada (au-aviso--info, au-aviso--error…) no tiene estilo y nadie lo nota a simple vista."""
    catalogo = _clases_del_catalogo()
    usadas: dict[str, set[str]] = {}
    for archivo in [INDEX, *(ESTATICO / "js").glob("*.js"), ESTATICO / "app.js"]:
        texto = archivo.read_text(encoding="utf-8")
        # Solo dentro de class="…", className = '…' o clases('…') y de los nombres de modificador que arma JS
        for bloque in re.findall(r"""class(?:Name)?\s*=\s*["'`]([^"'`]*)["'`]|Au\.clases\(([^)]*)\)""", texto):
            for token in re.findall(r"\bau-[a-z0-9_-]+", " ".join(bloque)):
                if "${" not in token:
                    usadas.setdefault(token.rstrip("-"), set()).add(archivo.name)
    faltan = {c: sorted(a) for c, a in usadas.items() if c not in catalogo and not c.endswith("--")}
    assert not faltan, f"clases au-* que no existen en componentes.css: {faltan}"


def test_r1_las_utilidades_de_color_no_pintan_componentes():
    """Un componente toma su color de un tono del catálogo: un bg-*/text-* suelto encima rompe la unificación."""
    patron = re.compile(
        r'class="[^"]*\bau-(?:progreso|boton|insignia|aviso)\b[^"]*\b(?:bg|text|border)-(?:sky|emerald|amber|rose|red|indigo|cyan|purple|green|blue)-[0-9]{2,3}\b[^"]*"'
    )
    hallados = []
    for archivo in [INDEX, *(ESTATICO / "js").glob("*.js")]:
        hallados += [f"{archivo.name}: {m.group(0)[:110]}" for m in patron.finditer(archivo.read_text(encoding="utf-8"))]
    assert not hallados, "colores de Tailwind sobre componentes:\n" + "\n".join(hallados[:15])


def _js_del_core() -> list[Path]:
    """El JS del core. Los revisores de abajo reciben la lista: test_nube_componentes los corre sobre el JS de la nube (R9)."""
    return [*(ESTATICO / "js").glob("*.js"), *sorted(ESTATICO.glob("*.js"))]


def _llamadas_au_invalidas(archivos: list[Path]) -> list[str]:
    variantes = {"primario", "secundario", "peligro", "fantasma"}
    tonos = {"primario", "exito", "alerta", "peligro"}
    catalogo = _clases_del_catalogo()
    malos = []
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        for m in re.finditer(r"\bAu\.(?!escapar|atributos|clases|urlSegura|acciones|modal|icono)([a-z]+)\(\s*([^{\s)])", texto):
            malos.append(f"{archivo.name}: Au.{m.group(1)}( sin objeto")
        for v in re.findall(r"\bvariante:\s*'([a-z-]+)'", texto):
            if v not in variantes:
                malos.append(f"{archivo.name}: variante '{v}'")
        for t in re.findall(r"\btono:\s*'([a-z-]+)'", texto):
            if t not in tonos:
                malos.append(f"{archivo.name}: tono '{t}'")
        # Cada componente tiene sus tonos: au-insignia--primario existe, au-aviso--primario no
        for componente, t in re.findall(r"\bAu\.([a-z]+)\(\{[^}]*?\btono:\s*'([a-z-]+)'", texto):
            if f"au-{componente}--{t}" not in catalogo:
                malos.append(f"{archivo.name}: Au.{componente} con tono '{t}' (no existe au-{componente}--{t})")
    return malos


def test_r3_las_funciones_au_reciben_un_objeto_y_valores_del_catalogo():
    """Au.boton({variante: 'exito'}) lanza un error y no se dibuja nada; Au.aviso('texto') queda vacío."""
    malos = _llamadas_au_invalidas(_js_del_core())
    assert not malos, "llamadas a Au.* inválidas:\n" + "\n".join(malos)


def _clases_au_inexistentes(archivos: list[Path]) -> list[str]:
    # au-cerrar-modal es el nombre de la acción de Au.modal, no una clase
    catalogo = _clases_del_catalogo() | {"au-boton--secundario", "au-cerrar-modal"}
    faltan = set()
    for archivo in archivos:
        for token in re.findall(r"['\"`](au-[a-z0-9_-]+)['\"`]", archivo.read_text(encoding="utf-8")):
            if token not in catalogo and not token.endswith("-"):
                faltan.add(f"{archivo.name}: {token}")
    return sorted(faltan)


def test_r1_las_clases_au_armadas_en_js_tambien_existen():
    """Las que se eligen con un ternario ('au-insignia--error') no pasan por el control de class="…"."""
    faltan = _clases_au_inexistentes(_js_del_core())
    assert not faltan, f"clases au-* que no existen: {faltan}"


# Los campos que antes de la 072 filtraban con oninput (index.html en 3e9adc1)
CAMPOS_QUE_FILTRAN_AL_ESCRIBIR = ("course-search-input", "book-search-input", "materiales-filtro", "notes-search-input", "manual-search-input")


@pytest.mark.parametrize("id_campo", CAMPOS_QUE_FILTRAN_AL_ESCRIBIR)
def test_r8_los_buscadores_siguen_filtrando_al_escribir(id_campo: str):
    """Un buscador migrado sin data-al-escribir filtra recién al salir del campo, no mientras se escribe."""
    html = INDEX.read_text(encoding="utf-8")
    etiqueta = re.search(rf'<input[^>]*\bid="{id_campo}"[^>]*>', html).group(0)
    assert "oninput=" in etiqueta or ("data-accion=" in etiqueta and "data-al-escribir" in etiqueta), etiqueta


def test_r1_sin_space_y_sobre_componentes_con_gap():
    """La tarjeta, el aviso y el campo ya separan sus hijos con gap: un space-y-* encima duplica el espacio."""
    patron = re.compile(r'class="([^"]*\bau-(?:tarjeta|aviso|campo)\b[^"]*)"')
    hallados = []
    for archivo in [INDEX, *(ESTATICO / "js").glob("*.js")]:
        for clases in patron.findall(archivo.read_text(encoding="utf-8")):
            if re.search(r"\bspace-y-[0-9.]+\b", clases):
                hallados.append(f"{archivo.name}: {clases[:90]}")
    assert not hallados, "\n".join(hallados[:10])


def _selectores_vacios(archivos: list[Path]) -> list[str]:
    malos = []
    for archivo in archivos:
        # Vacío, o con un [] / [data-] que dejó la limpieza en cualquier parte: 'button[]', '[], .x', '[data-]'
        selector = r"""(?:closest|querySelector(?:All)?|matches)\(\s*(['"`])(?:\s*|[^'"`]*\[\s*(?:data-)?\s*\][^'"`]*)\1\s*\)"""
        for m in re.finditer(selector, archivo.read_text(encoding="utf-8")):
            malos.append(f"{archivo.name}: {m.group(0)}")
    return malos


def test_sin_selectores_vacios_en_el_js():
    """Un closest('[]') o querySelector('[]') lanza SyntaxError en cada llamada (pasó al limpiar un atributo legado)."""
    malos = _selectores_vacios(_js_del_core())
    assert not malos, malos


# ---------- Modales (tanda 3) ----------
# Un modal migrado es un .au-modal; el contrato lo controla esto por descubrimiento, sin lista a mano.


def _modales_au(texto: str) -> list[tuple[str, str]]:
    """(id, marcado de la capa completo) de cada <div … class="au-modal …"> del texto."""
    hallados = []
    for m in re.finditer(r'<div\b[^>]*\bclass="(?:[^"]*\s)?au-modal(?:\s[^"]*)?"[^>]*>', texto):
        ident = re.search(r'\bid="([^"]+)"', m.group(0))
        # El cierre: contar <div y </div> desde la apertura
        nivel, fin = 0, len(texto)
        for t in re.finditer(r"<div\b|</div>", texto[m.start():]):
            nivel += 1 if t.group(0) != "</div>" else -1
            if nivel == 0:
                fin = m.start() + t.end()
                break
        hallados.append((ident.group(1) if ident else "(sin id)", texto[m.start():fin]))
    return hallados


def test_r4_cada_au_modal_cumple_el_contrato():
    """role, aria-modal, título enlazado, oculto con el atributo, ✕ con etiqueta y sin manejadores en línea."""
    malos = []
    for ident, marcado in _modales_au(INDEX.read_text(encoding="utf-8")):
        apertura = marcado[: marcado.index(">") + 1]
        titulo = re.search(r'aria-labelledby="([^"]+)"', apertura)
        cerrar = re.findall(r'<button\b[^>]*data-accion="au-cerrar-modal"[^>]*>', marcado)
        chequeos = {
            'role="dialog"': 'role="dialog"' in apertura,
            'aria-modal="true"': 'aria-modal="true"' in apertura,
            "título enlazado": bool(titulo) and f'id="{titulo.group(1) if titulo else ""}"' in marcado,
            "oculto con el atributo hidden, no con la clase": bool(re.search(r"\shidden(?=[\s>=])", apertura))
            and not re.search(r'class="[^"]*\bhidden\b', apertura),
            "sin modal-capa/modal-caja": "modal-capa" not in marcado and "modal-caja" not in marcado,
            "✕ con data-accion y aria-label": any("aria-label=" in b for b in cerrar),
            "sin on*= en línea": not re.search(r"\son[a-z]+=", marcado),
        }
        problemas = [nombre for nombre, ok in chequeos.items() if not ok]
        if problemas:
            malos.append(f"#{ident}: {problemas}")
    assert not malos, "\n".join(malos)


def test_r4_el_js_no_abre_ni_cierra_un_au_modal_con_la_clase_hidden():
    """Un au-modal se oculta con el atributo hidden y se maneja con Au.modal: con classList quedan la pila y el foco mal."""
    ids = [i for i, _ in _modales_au(INDEX.read_text(encoding="utf-8"))]
    assert len(ids) >= 42, ids
    malos = _modales_manejados_con_la_clase_hidden(_js_del_core(), ids)
    assert not malos, "\n".join(malos)


def _modales_manejados_con_la_clase_hidden(archivos: list[Path], ids: list[str]) -> list[str]:
    clase_hidden = r"""\??\.classList\.(?:add|remove|toggle)\(\s*['"]hidden['"]"""
    malos = set()
    for archivo in archivos:
        js = archivo.read_text(encoding="utf-8")
        for ident in ids:
            cita = rf"""getElementById\(\s*['"]{re.escape(ident)}['"]\s*\)"""
            if re.search(cita + clase_hidden, js):
                malos.add(f"{archivo.name}: #{ident}")
            # Por variable: const m = document.getElementById('x'); … m.classList.remove('hidden') en la misma función
            for v in re.finditer(rf"(\w+)\s*=\s*document\.{cita}", js):
                tramo = js[v.end(): v.end() + 1500].split("\n}")[0]
                if re.search(rf"\b{re.escape(v.group(1))}{clase_hidden}", tramo):
                    malos.add(f"{archivo.name}: #{ident} (variable {v.group(1)})")
    return sorted(malos)


def test_r5_index_html_sin_manejadores_en_linea_ni_modales_viejos():
    """072 T11: todo index.html y mcp-remoto.js migrados; un onclick nuevo o un modal-capa es marcado que volvió."""
    html = INDEX.read_text(encoding="utf-8")
    mcp = (ESTATICO / "mcp-remoto.js").read_text(encoding="utf-8")
    manejadores = re.findall(r"<[^>]*\son[a-z]+=\"[^\"]*\"", html)
    manejadores += [f"mcp-remoto.js: {m}" for m in re.findall(r"\bon[a-z]+=", mcp)]
    assert not manejadores, manejadores[:5]
    assert "modal-capa" not in html and "modal-caja" not in html


# Botones que son un enlace dentro de una línea de texto: un au-boton los sacaría del renglón
BOTONES_EN_LINEA = {"limpiar-foco-material", "abrir-carpetas-tutor"}


@pytest.mark.parametrize("pestana", sorted(PANTALLAS_MIGRADAS))
def test_r7_en_una_pantalla_migrada_botones_y_campos_son_componentes(pestana: str):
    """R7: «migrada» quiere decir que sus botones y campos son au-*, no que no tiene onclick (pasó con config).

    Mira la sección de index.html y también lo que arma su pantalla-<pestana>.js (pasó con roadmap)."""
    seccion = _seccion_de_index(pestana) + "\n" + _js_de_pantalla(pestana)
    sueltos = _controles_a_mano(seccion)
    assert not sueltos, f"{len(sueltos)} controles a mano en {pestana}:\n" + "\n".join(sueltos[:8])


# Un className con relleno y fondo escritos a mano: un botón o una insignia armados a mano, o un
# conmutador que le pisa la clase a un componente (el dictado del simulador volvía a sus clases viejas)
CLASE_A_MANO = re.compile(r"""\.className\s*=\s*(['"`])((?:(?!\1).)*\b(?:px|py|p)-[0-9.]+\b(?:(?!\1).)*\bbg-(?:(?!\1).)*)\1""")


def _controles_a_mano(texto: str) -> list[str]:
    sueltos = []
    for m in CLASE_A_MANO.finditer(texto):
        if "au-" not in m.group(2):
            sueltos.append(m.group(0)[:110])
    for boton in re.findall(r"<button\b[^>]*>", texto):
        accion = re.search(r'data-accion="([^"]+)"', boton)
        if not re.search(r'class="[^"]*\bau-', boton) and not (accion and accion.group(1) in BOTONES_EN_LINEA):
            sueltos.append(boton[:110])
    for campo in re.findall(r"<(?:input|select|textarea)\b[^>]*>", texto):
        if re.search(r'type="(?:checkbox|radio|file|hidden|range|color)"', campo):
            continue
        if "au-campo__control" not in campo:
            sueltos.append(campo[:110])
    return sueltos


# ---------- Contenido de los modales (tanda 4, T12) ----------
# Al migrar el contenido de un modal se agrega a su grupo; desde ahí no puede tener controles a mano.
# Un set por grupo, cada uno en su línea, para que los tres agentes no se pisen al integrar.
MODALES_MIGRADOS_A: set[str] = {
    "selective-index-modal", "material-texto-modal", "duolingo-modal",
    "onboarding-wizard-modal",
    "add-platform-modal", "edit-platform-modal",
    "add-course-modal", "edit-course-modal",
    "add-book-modal", "edit-book-modal",
}  # líneas 2881-3624: asistente inicial, plataformas, cursos y libros
MODALES_MIGRADOS_B: set[str] = {
    "add-schedule-modal", "delete-schedule-modal", "edit-schedule-modal", "schedule-card-detail-modal",
    "weekly-digest-modal", "course-note-modal", "consulting-sim-modal", "fsrs-harvester-modal",
    "material-note-modal", "google-calendar-modal", "fsrs-evolution-modal",
}  # líneas 3625-4577: agenda, notas, simulador, cosecha y calendario
MODALES_MIGRADOS_C: set[str] = {
    "modal-roadmap-catalog", "modal-add-prerequisite", "modal-prerequisite-suggestions", "modal-new-roadmap",
    "modal-pedagogical-profile", "modal-topic-prompt", "modal-import-lesson", "modal-view-lesson",
    "modal-pdf-gap", "modal-feynman-quiz", "modal-course-webhook", "modal-apple-shortcuts",
    "modal-book-active-recall", "modal-book-harvest", "modal-study-planner", "modal-system-confirm",
    "modal-system-prompt", "modal-user-manual", "modal-diagnostics", "modal-keyboard-shortcuts",
    "modal-guided-study-session",
}  # desde 4578: rutas y modales generales
MODALES_MIGRADOS = MODALES_MIGRADOS_A | MODALES_MIGRADOS_B | MODALES_MIGRADOS_C


def _modal_de_index(ident: str) -> str:
    for i, marcado in _modales_au(INDEX.read_text(encoding="utf-8")):
        if i == ident:
            return marcado
    raise AssertionError(f"#{ident} no es un au-modal de index.html")


@pytest.mark.parametrize("modal", sorted(MODALES_MIGRADOS))
def test_r7_en_un_modal_migrado_botones_y_campos_son_componentes(modal: str):
    """T12: el contenido de un modal migrado usa au-*, como una pantalla migrada."""
    sueltos = _controles_a_mano(_modal_de_index(modal))
    assert not sueltos, f"{len(sueltos)} controles a mano en #{modal}:\n" + "\n".join(sueltos[:8])


def test_r7_todos_los_modales_estan_migrados():
    """T12 cerrada: cada au-modal de index.html está en MODALES_MIGRADOS (un modal nuevo entra ya migrado)."""
    ids = {i for i, _ in _modales_au(INDEX.read_text(encoding="utf-8"))}
    assert ids == MODALES_MIGRADOS, {"sin migrar": sorted(ids - MODALES_MIGRADOS), "de más": sorted(MODALES_MIGRADOS - ids)}


def test_r7_los_grupos_de_modales_no_se_repiten():
    assert not (MODALES_MIGRADOS_A & MODALES_MIGRADOS_B or MODALES_MIGRADOS_A & MODALES_MIGRADOS_C
                or MODALES_MIGRADOS_B & MODALES_MIGRADOS_C)


def test_r10_todas_las_pestanas_estan_migradas():
    """T11: las 10 pestañas de index.html están en PANTALLAS_MIGRADAS (y no hay una de más)."""
    pestanas = set(re.findall(r'<section id="tab-([a-z]+)"', INDEX.read_text(encoding="utf-8")))
    assert pestanas == PANTALLAS_MIGRADAS


def test_r7_lo_que_el_js_prende_con_aria_pressed_es_un_au_boton():
    """aria-pressed solo se ve sobre au-boton: la agenda cambiaba el atributo y sus días seguían pintados a mano."""
    html = INDEX.read_text(encoding="utf-8")
    ganchos = set()
    for archivo in _js_del_core():
        js = archivo.read_text(encoding="utf-8")
        for m in re.finditer(r"""querySelectorAll\(\s*['"]\.([a-z0-9_-]+)['"]\s*\)""", js):
            if "aria-pressed" in js[m.end(): m.end() + 400]:
                ganchos.add(m.group(1))
    assert ganchos, "no se encontró ningún conmutador con aria-pressed"
    sueltos = []
    for gancho in sorted(ganchos):
        botones = re.findall(rf'<button\b[^>]*class="(?:[^"]*\s)?{re.escape(gancho)}(?:\s[^"]*)?"[^>]*>', html)
        sueltos += [f"{gancho}: {b[:100]}" for b in botones if not re.search(r'class="[^"]*\bau-boton\b', b) or "aria-pressed=" not in b]
    assert not sueltos, "\n".join(sueltos)
