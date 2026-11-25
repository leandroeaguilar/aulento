"""072: los componentes de Aulento en un navegador de verdad (R1, R3, R4).

El repo no tiene Node: las funciones de `componentes.js` se prueban con Playwright sobre una página en blanco, sin servidor.
Se corre a pedido: `AULENTO_E2E=1 pytest tests/e2e/test_componentes.py`.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

ESTATICO = Path(__file__).resolve().parents[2] / "src" / "aulento" / "web" / "static"


def _cargar(page: Page, ancho: int = 375, alto: int = 812) -> None:
    page.set_viewport_size({"width": ancho, "height": alto})
    page.set_content(
        "<!doctype html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body><div id='raiz'></div></body></html>"
    )
    page.add_style_tag(path=str(ESTATICO / "css" / "paleta.css"))
    page.add_style_tag(path=str(ESTATICO / "componentes.css"))
    page.add_script_tag(path=str(ESTATICO / "componentes.js"))


@pytest.fixture
def pagina(page: Page) -> Page:
    _cargar(page)
    return page


def _poner(page: Page, expresion: str) -> None:
    page.evaluate(f"document.getElementById('raiz').innerHTML = {expresion}")


# ---------- R3: escapado y marcado ----------


def test_escapa_todo_texto(pagina: Page):
    malo = "<img src=x onerror=alert(1)>\"'&"
    html = pagina.evaluate(
        """malo => [Au.escapar(malo), Au.insignia({texto: malo}), Au.boton({texto: malo}),
                    Au.cabecera({titulo: malo, subtitulo: malo}), Au.kpi({etiqueta: malo, valor: malo}),
                    Au.campo({id: 'c', etiqueta: malo, valor: malo}), Au.aviso({titulo: malo, texto: malo}),
                    Au.vacio({titulo: malo, texto: malo}), Au.fila({titulo: malo, detalle: malo})].join('')""",
        malo,
    )
    assert "<img" not in html and "&lt;img" in html


def test_los_atributos_raros_se_rechazan(pagina: Page):
    with pytest.raises(Exception, match="Atributo inválido"):
        pagina.evaluate("Au.atributos({'onclick=x': 1})")


def test_variantes_del_boton(pagina: Page):
    _poner(
        pagina,
        "[Au.boton({texto: 'A', variante: 'primario'}), Au.boton({texto: 'B'}), Au.boton({texto: 'C', variante: 'peligro', chico: true}),"
        " Au.boton({texto: 'D', variante: 'fantasma', bloque: true}), Au.boton({texto: 'E', href: '/x'})].join('')",
    )
    clases = pagina.evaluate("Array.from(document.querySelectorAll('.au-boton')).map(b => b.className)")
    assert clases == [
        "au-boton au-boton--primario",
        "au-boton",
        "au-boton au-boton--peligro au-boton--chico",
        "au-boton au-boton--fantasma au-boton--bloque",
        "au-boton",
    ]
    assert pagina.evaluate("document.querySelector('button.au-boton').type") == "button"
    assert pagina.evaluate("document.querySelector('a.au-boton').getAttribute('href')") == "/x"
    with pytest.raises(Exception, match="Variante de botón desconocida"):
        pagina.evaluate("Au.boton({texto: 'x', variante: 'verde'})")


def test_r4_el_boton_de_icono_exige_etiqueta(pagina: Page):
    with pytest.raises(Exception, match="aria-label"):
        pagina.evaluate("Au.boton({icono: '✕', soloIcono: true})")
    _poner(pagina, "Au.boton({icono: '✕', soloIcono: true, etiqueta: 'Cerrar'})")
    expect(pagina.get_by_role("button", name="Cerrar")).to_be_visible()


def test_insignias_por_tono(pagina: Page):
    _poner(pagina, "['primario','exito','alerta','peligro','raro'].map(t => Au.insignia({texto: t, tono: t})).join('')")
    clases = pagina.evaluate("Array.from(document.querySelectorAll('.au-insignia')).map(b => b.className)")
    assert clases[:4] == [f"au-insignia au-insignia--{t}" for t in ("primario", "exito", "alerta", "peligro")]
    assert clases[4] == "au-insignia"


def test_campo_enlaza_etiqueta_ayuda_y_error(pagina: Page):
    _poner(
        pagina,
        "Au.campo({id: 'nombre', etiqueta: 'Nombre', ayuda: 'Como te ven'}) +"
        " Au.campo({id: 'clave', etiqueta: 'Clave', tipo: 'password', error: 'Muy corta'}) +"
        " Au.campo({id: 'nivel', etiqueta: 'Nivel', valor: 'b2', opciones: [{valor: 'b1', texto: 'B1'}, {valor: 'b2', texto: 'B2'}]})",
    )
    expect(pagina.get_by_label("Nombre")).to_have_attribute("aria-describedby", "nombre-ayuda")
    expect(pagina.get_by_label("Clave")).to_have_attribute("aria-invalid", "true")
    expect(pagina.get_by_label("Nivel")).to_have_value("b2")


def test_progreso_acota_y_anuncia(pagina: Page):
    _poner(pagina, "Au.progreso({valor: 150, maximo: 100, etiqueta: 'Avance'}) + Au.progreso({valor: -5})")
    valores = pagina.evaluate("Array.from(document.querySelectorAll('progress.au-progreso')).map(p => [p.value, p.max])")
    assert valores == [[100, 100], [0, 100]]
    expect(pagina.get_by_role("progressbar", name="Avance")).to_have_attribute("max", "100")


# ---------- R3: acciones delegadas ----------


def test_las_acciones_delegadas_reciben_sus_datos(pagina: Page):
    pagina.evaluate(
        """() => { window.llamadas = [];
                   Au.acciones.registrar('anotar', (el, datos, ev) => llamadas.push([ev.type, datos.libro || datos.valor || null])); }"""
    )
    _poner(
        pagina,
        "Au.boton({texto: 'Uno', accion: 'anotar', datos: {libro: 7}}) +"
        " Au.pestanas({items: [{valor: 'a', texto: 'A'}, {valor: 'b', texto: 'B'}], activa: 'a', accion: 'anotar'}) +"
        " '<select data-accion=\"anotar\" data-valor=\"s\"><option>1</option><option>2</option></select>' +"
        " '<form data-accion=\"anotar\" data-valor=\"f\"><button type=\"submit\">Enviar</button></form>'",
    )
    pagina.get_by_role("button", name="Uno").click()
    pagina.get_by_role("tab", name="B").click()
    pagina.locator("select").select_option("2")
    pagina.get_by_role("button", name="Enviar").click()
    assert pagina.evaluate("llamadas") == [["click", "7"], ["click", "b"], ["change", "s"], ["submit", "f"]]
    # El submit no navegó
    assert pagina.evaluate("document.getElementById('raiz') !== null")


def test_una_accion_no_se_registra_dos_veces(pagina: Page):
    pagina.evaluate("Au.acciones.registrar('una', () => {})")
    with pytest.raises(Exception, match="ya está registrada"):
        pagina.evaluate("Au.acciones.registrar('una', () => {})")


# ---------- R4: modal ----------

MODAL = """'<button id="abre">Abrir</button>' +
  '<div id="m" class="au-modal" hidden role="dialog" aria-modal="true" aria-labelledby="m-titulo">' +
  '<div class="au-modal__caja"><div class="au-modal__cabecera"><h2 id="m-titulo" class="au-modal__titulo">Título</h2>' +
  Au.boton({icono: '✕', soloIcono: true, etiqueta: 'Cerrar', variante: 'fantasma', accion: 'au-cerrar-modal'}) +
  '</div><div class="au-modal__cuerpo"><input id="dentro" aria-label="Dentro">' + ALTO + '</div></div></div>'"""


def _modal(page: Page, alto_px: int = 100) -> None:
    _poner(page, MODAL.replace("ALTO", f"'<div style=\"height:{alto_px}px\"></div>'"))
    page.evaluate("document.getElementById('abre').addEventListener('click', e => Au.modal.abrir('m', e.currentTarget))")


def test_r4_el_modal_abre_con_foco_y_esc_lo_cierra_devolviendo_el_foco(pagina: Page):
    _modal(pagina)
    pagina.get_by_role("button", name="Abrir").click()
    expect(pagina.get_by_role("dialog", name="Título")).to_be_visible()
    assert pagina.evaluate("document.activeElement.id") == "dentro"
    assert pagina.evaluate("document.body.classList.contains('au-modal-abierto')")
    pagina.keyboard.press("Escape")
    expect(pagina.locator("#m")).to_be_hidden()
    assert pagina.evaluate("document.activeElement.id") == "abre"
    assert not pagina.evaluate("document.body.classList.contains('au-modal-abierto')")


def test_r4_el_modal_aplica_inert_al_fondo_y_lo_restaura_al_cerrar(pagina: Page):
    pagina.evaluate("""() => {
        let t = document.getElementById('toast-container');
        if (!t) {
            t = document.createElement('div');
            t.id = 'toast-container';
            document.body.appendChild(t);
        }
    }""")
    _modal(pagina)
    assert not pagina.evaluate("document.getElementById('abre').inert")
    assert not pagina.evaluate("document.getElementById('toast-container').inert")

    pagina.get_by_role("button", name="Abrir").click()
    expect(pagina.get_by_role("dialog", name="Título")).to_be_visible()
    assert pagina.evaluate("document.getElementById('abre').inert")
    assert not pagina.evaluate("document.getElementById('m').inert")
    assert not pagina.evaluate("document.getElementById('toast-container').inert")
    assert pagina.evaluate("document.activeElement.id") == "dentro"

    # Segundo modal anidado/apilado
    modal_anidado = (
        "<div id='m2' class='au-modal' hidden role='dialog' aria-modal='true' aria-labelledby='m2-t'>"
        "<div class='au-modal__caja'><div class='au-modal__cabecera'><h2 id='m2-t' class='au-modal__titulo'>Segundo</h2>"
        "<button type='button' data-accion='au-cerrar-modal' aria-label='Cerrar'>✕</button></div>"
        "<div class='au-modal__cuerpo'><input id='dentro2' aria-label='Dentro 2'></div></div></div>"
    )
    pagina.evaluate(f"document.getElementById('raiz').insertAdjacentHTML('beforeend', \"{modal_anidado}\")")
    pagina.evaluate("Au.modal.abrir('m2', document.getElementById('dentro'))")
    expect(pagina.get_by_role("dialog", name="Segundo")).to_be_visible()
    assert pagina.evaluate("document.activeElement.id") == "dentro2"
    assert not pagina.evaluate("document.getElementById('m2').inert")
    assert pagina.evaluate("document.getElementById('m').inert")
    assert pagina.evaluate("document.getElementById('abre').inert")
    assert not pagina.evaluate("document.getElementById('toast-container').inert")

    # Al cerrar el modal superior (m2), el inferior (m) deja de estar inert y recupera el foco
    pagina.keyboard.press("Escape")
    expect(pagina.locator("#m2")).to_be_hidden()
    expect(pagina.get_by_role("dialog", name="Título")).to_be_visible()
    assert not pagina.evaluate("document.getElementById('m').inert")
    assert pagina.evaluate("document.activeElement.id") == "dentro"
    assert pagina.evaluate("document.getElementById('abre').inert")
    assert not pagina.evaluate("document.getElementById('toast-container').inert")

    # Al cerrar el último modal, el fondo recupera interactividad y el foco
    pagina.keyboard.press("Escape")
    expect(pagina.locator("#m")).to_be_hidden()
    assert not pagina.evaluate("document.getElementById('abre').inert")
    assert pagina.evaluate("document.activeElement.id") == "abre"


def test_r4_la_x_y_el_fondo_cierran_pero_la_caja_no(pagina: Page):
    _modal(pagina)
    pagina.get_by_role("button", name="Abrir").click()
    pagina.locator(".au-modal__caja").click(position={"x": 20, "y": 80})
    expect(pagina.locator("#m")).to_be_visible()
    pagina.get_by_role("button", name="Cerrar").click()
    expect(pagina.locator("#m")).to_be_hidden()
    pagina.get_by_role("button", name="Abrir").click()
    pagina.mouse.click(5, 5)  # el fondo
    expect(pagina.locator("#m")).to_be_hidden()



def test_r4_cada_forma_de_cerrar_avisa_una_vez_con_au_cerrado(pagina: Page):
    """La limpieza de un modal (resetear un form, cortar un audio) corre igual con Esc, la ✕, el fondo o código."""
    _modal(pagina)
    pagina.evaluate("window.cierres = 0; document.getElementById('m').addEventListener('au:cerrado', () => cierres++)")
    for cerrar in (
        lambda: pagina.keyboard.press("Escape"),
        lambda: pagina.get_by_role("button", name="Cerrar").click(),
        lambda: pagina.mouse.click(5, 5),
        lambda: pagina.evaluate("Au.modal.cerrar('m')"),
    ):
        pagina.get_by_role("button", name="Abrir").click()
        cerrar()
        expect(pagina.locator("#m")).to_be_hidden()
    pagina.evaluate("Au.modal.cerrar('m')")  # ya cerrado: no vuelve a avisar
    assert pagina.evaluate("cierres") == 4


def test_r4_un_modal_abierto_desde_otro_queda_adelante_aunque_este_antes_en_el_dom(pagina: Page):
    """Agregar curso → «+ Nueva plataforma»: la de plataforma está antes en el index y quedaba atrás."""
    modal = (
        "<div id='{id}' class='au-modal' hidden role='dialog' aria-modal='true' aria-labelledby='{id}-t'>"
        "<div class='au-modal__caja'><h2 id='{id}-t' class='au-modal__titulo'>{id}</h2>"
        "<button type='button' id='{id}-b'>Botón {id}</button></div></div>"
    )
    pagina.evaluate(
        "html => document.getElementById('raiz').innerHTML = html",
        modal.format(id="interno") + modal.format(id="externo"),
    )
    pagina.evaluate("Au.modal.abrir('externo')")
    pagina.evaluate("Au.modal.abrir('interno')")
    arriba = "(() => { const c = document.querySelector('#interno .au-modal__caja').getBoundingClientRect();"
    arriba += " return document.elementFromPoint(c.x + c.width / 2, c.y + 10).closest('.au-modal').id; })()"
    assert pagina.evaluate(arriba) == "interno"
    pagina.keyboard.press("Escape")
    expect(pagina.locator("#interno")).to_be_hidden()
    expect(pagina.locator("#externo")).to_be_visible()
    # Cerrado, no guarda su capa: al reabrirse solo vuelve a quedar arriba del que esté abierto
    assert pagina.evaluate("document.getElementById('interno').style.zIndex") == ""


def test_r4_un_modal_sin_cierre_solo_lo_cierra_el_codigo(pagina: Page):
    """data-sin-cierre (un «generando…»): Esc y el fondo no lo cierran; Au.modal.cerrar sí."""
    _modal(pagina)
    pagina.evaluate("document.getElementById('m').setAttribute('data-sin-cierre', '')")
    pagina.get_by_role("button", name="Abrir").click()
    pagina.keyboard.press("Escape")
    pagina.mouse.click(5, 5)
    expect(pagina.locator("#m")).to_be_visible()
    pagina.evaluate("Au.modal.cerrar('m')")
    expect(pagina.locator("#m")).to_be_hidden()

@pytest.mark.parametrize("ancho", (375, 1280))
def test_r1_un_modal_alto_empieza_arriba_y_entra_de_costado(page: Page, ancho: int):
    _cargar(page, ancho, 700)
    _modal(page, 1500)
    page.get_by_role("button", name="Abrir").click()
    caja = page.locator(".au-modal__caja").bounding_box()
    assert caja and caja["y"] >= 0, f"a {ancho} px la caja empieza en {caja}"
    assert caja["x"] >= 0 and caja["x"] + caja["width"] <= ancho
    expect(page.get_by_role("button", name="Cerrar")).to_be_in_viewport()


# ---------- R1: reglas de la 071 incluidas ----------


def test_r1_con_el_dedo_los_controles_miden_40(browser):
    contexto = browser.new_context(viewport={"width": 375, "height": 812}, has_touch=True, is_mobile=True)
    page = contexto.new_page()
    _cargar(page)
    _poner(
        page,
        "Au.boton({texto: 'A', chico: true}) + Au.boton({icono: '✕', soloIcono: true, etiqueta: 'X', chico: true}) +"
        " Au.pestanas({items: [{valor: 1, texto: 'Uno'}], activa: 1}) + Au.campo({id: 'c', etiqueta: 'C'})",
    )
    medidas = page.evaluate(
        "Array.from(document.querySelectorAll('.au-boton, .au-pestanas__boton, .au-campo__control'))"
        ".map(e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; })"
    )
    contexto.close()
    assert all(w >= 39.5 and h >= 39.5 for w, h in medidas), medidas


def test_r1_la_cabecera_baja_de_linea_sin_aplastar_el_titulo(pagina: Page):
    _poner(
        pagina,
        "Au.tarjeta({cabecera: {titulo: 'Consistencia y Hábitos de Estudio', icono: '📅',"
        " insignias: [{texto: '🔥 14 días', tono: 'alerta'}, {texto: 'Récord: 14d'}],"
        " accionesHtml: [Au.boton({texto: 'Actualizar'})]}})",
    )
    titulo = pagina.evaluate("document.querySelector('.au-cabecera__titulo > span').getBoundingClientRect().width")
    assert titulo >= 170, f"el título quedó en {titulo}px"
    assert pagina.evaluate("document.documentElement.scrollWidth") <= 375


def test_r1_texto_minimo_de_12px(pagina: Page):
    _poner(
        pagina,
        "Au.insignia({texto: 'a'}) + Au.kpi({etiqueta: 'b', valor: 1, detalle: 'c'}) + Au.aviso({texto: 'd'}) +"
        " Au.fila({titulo: 'e', detalle: 'f'}) + Au.campo({id: 'g', etiqueta: 'g', ayuda: 'h'})",
    )
    chicos = pagina.evaluate(
        """() => Array.from(document.querySelectorAll('#raiz *')).filter(e => e.childNodes.length && Array.from(e.childNodes).some(n => n.nodeType === 3 && n.textContent.trim()))
              .map(e => parseFloat(getComputedStyle(e).fontSize)).filter(t => t < 12)"""
    )
    assert not chicos


def test_r4_esc_cierra_el_modal_sin_disparar_los_atajos_viejos(pagina: Page):
    """Los atajos de la app (comunes.js, rutas) también escuchan keydown en document: con un au-modal abierto no corren."""
    _modal(pagina)
    pagina.evaluate("window.atajos = 0; document.addEventListener('keydown', e => { if (e.key === 'Escape') atajos++; })")
    pagina.get_by_role("button", name="Abrir").click()
    pagina.keyboard.press("Escape")
    expect(pagina.locator("#m")).to_be_hidden()
    assert pagina.evaluate("atajos") == 0
    # Sin modal abierto, el Esc les llega como siempre
    pagina.keyboard.press("Escape")
    assert pagina.evaluate("atajos") == 1


def test_r4_el_modal_enfoca_primero_el_autofocus(pagina: Page):
    _poner(
        pagina,
        "'<div id=\"a\" class=\"au-modal\" hidden role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"a-t\"><div class=\"au-modal__caja\"><h2 id=\"a-t\">T</h2>"
        "<input id=\"primero\" aria-label=\"Primero\"><input id=\"elegido\" aria-label=\"Elegido\" autofocus></div></div>'",
    )
    pagina.evaluate("Au.modal.abrir('a')")
    assert pagina.evaluate("document.activeElement.id") == "elegido"


def test_la_etiqueta_del_boton_llega_como_title(pagina: Page):
    _poner(pagina, "Au.boton({texto: 'Guardar', etiqueta: 'Guardar el bloque'})")
    expect(pagina.get_by_role("button", name="Guardar")).to_have_attribute("title", "Guardar el bloque")


def test_r3_las_urls_se_escapan_una_sola_vez_y_solo_las_seguras(pagina: Page):
    _poner(
        pagina,
        "Au.boton({texto: 'Aula', href: 'https://aula.example/curso?a=1&b=2'}) +"
        " Au.boton({texto: 'Malo', href: 'javascript:alert(1)'}) + Au.boton({texto: 'Local', href: '/static/x'})",
    )
    hrefs = pagina.evaluate("Array.from(document.querySelectorAll('a.au-boton')).map(a => a.getAttribute('href'))")
    assert hrefs == ["https://aula.example/curso?a=1&b=2", "#", "/static/x"]


def test_r3_los_atributos_no_aceptan_manejadores_en_linea(pagina: Page):
    for nombre in ("onclick", "onerror", "OnMouseOver"):
        with pytest.raises(Exception, match="Atributo inválido"):
            pagina.evaluate(f"Au.atributos({{'{nombre}': 'alert(1)'}})")
    with pytest.raises(Exception, match="Atributo inválido"):
        pagina.evaluate("Au.boton({texto: 'x', attrs: {onclick: 'alert(1)'}})")


def test_r4_el_modal_exige_su_aria(pagina: Page):
    _poner(pagina, "'<div id=\"sin\" class=\"au-modal\" hidden><div class=\"au-modal__caja\"></div></div>'")
    with pytest.raises(Exception, match="aria-labelledby"):
        pagina.evaluate("Au.modal.abrir('sin')")


@pytest.mark.parametrize("como", ("x", "fondo"))
def test_r4_cerrar_con_la_x_o_el_fondo_devuelve_el_foco(pagina: Page, como: str):
    _modal(pagina)
    pagina.get_by_role("button", name="Abrir").click()
    if como == "x":
        pagina.get_by_role("button", name="Cerrar").click()
    else:
        pagina.mouse.click(5, 5)
    expect(pagina.locator("#m")).to_be_hidden()
    assert pagina.evaluate("document.activeElement.id") == "abre"


def test_r2_cambiar_un_token_cambia_los_componentes(pagina: Page):
    _poner(pagina, "Au.boton({texto: 'P', variante: 'primario'}) + Au.tarjeta({cabecera: {titulo: 'T'}})")
    antes = pagina.evaluate(
        "[getComputedStyle(document.querySelector('.au-boton--primario')).backgroundColor,"
        " getComputedStyle(document.querySelector('.au-tarjeta')).borderTopLeftRadius]"
    )
    pagina.evaluate(
        "document.documentElement.style.setProperty('--au-primario', 'rgb(1, 2, 3)');"
        "document.documentElement.style.setProperty('--au-radio-tarjeta', '3px')"
    )
    pagina.wait_for_timeout(400)  # el botón tiene una transición de color de 0,15 s
    despues = pagina.evaluate(
        "[getComputedStyle(document.querySelector('.au-boton--primario')).backgroundColor,"
        " getComputedStyle(document.querySelector('.au-tarjeta')).borderTopLeftRadius]"
    )
    assert antes != despues and despues == ["rgb(1, 2, 3)", "3px"]


def test_r3_un_buscador_dispara_su_accion_al_escribir_y_no_al_salir(pagina: Page):
    pagina.evaluate("window.busquedas = []; Au.acciones.registrar('buscar', (el) => busquedas.push(el.value))")
    _poner(pagina, "'<input id=\"q\" aria-label=\"Buscar\" data-accion=\"buscar\" data-al-escribir><button>otro</button>'")
    pagina.locator("#q").press_sequentially("ab")
    pagina.get_by_role("button", name="otro").click()  # sale del campo: dispara change
    assert pagina.evaluate("busquedas") == ["a", "ab"]


def test_r3_un_enlace_dentro_de_una_tarjeta_clickeable_no_dispara_la_tarjeta(pagina: Page):
    pagina.evaluate("window.tarjeta = 0; Au.acciones.registrar('abrir-tarjeta', () => tarjeta++)")
    _poner(
        pagina,
        "'<div data-accion=\"abrir-tarjeta\" style=\"padding:20px\"><span id=\"texto\">Bloque</span>"
        "<a id=\"enlace\" href=\"#nada\">Acceso</a><div data-sin-accion><span id=\"ajustar\">Ajustar:</span></div></div>'",
    )
    pagina.locator("#texto").click()
    pagina.locator("#enlace").click()
    pagina.locator("#ajustar").click()
    assert pagina.evaluate("tarjeta") == 1


def test_r1_un_boton_prendido_se_distingue_del_apagado(pagina: Page):
    """Los días de la agenda y los minutos del planificador: el JS solo cambia aria-pressed."""
    _poner(
        pagina,
        "'<button type=\"button\" id=\"si\" class=\"au-boton au-boton--chico\" aria-pressed=\"true\">Lu</button>"
        "<button type=\"button\" id=\"no\" class=\"au-boton au-boton--chico\" aria-pressed=\"false\">Ma</button>'",
    )
    fondo = "id => getComputedStyle(document.getElementById(id)).backgroundColor"
    assert pagina.evaluate(fondo, "si") != pagina.evaluate(fondo, "no")
    pagina.evaluate("document.getElementById('no').setAttribute('aria-pressed', 'true')")
    # El botón tiene transición de color: se espera a que llegue
    expect(pagina.locator("#no")).to_have_css("background-color", pagina.evaluate(fondo, "si"))
