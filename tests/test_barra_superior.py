"""Pruebas de la barra superior reordenada (Feature feat/barra-superior).

Verifica:
- Limpieza de píldoras: racha, repaso (🃏), foco y retención (2xl).
- Duolingo e índice de apuntes mudados al popover de salud (#salud-duolingo, #salud-vector).
- Botón de tema en la barra superior con ciclo y sincronía bidireccional.
- Atajos de teclado únicos (sin duplicado en la barra; solo en el menú y atajo ?).
- Menú visible en modo local (☰ Menú / Opciones) y con cuenta (👤 / Mi Cuenta).
- Botón de recargar mudado de la barra al menú desplegable.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESTATICO = RAIZ / "src" / "aulento" / "web" / "static"
INDEX = ESTATICO / "index.html"


def _header_html(html: str) -> str:
    inicio = html.index("<header")
    fin = html.index("</header>", inicio) + len("</header>")
    return html[inicio:fin]


def _dropdown_html(header: str) -> str:
    inicio = header.index('id="user-dropdown-menu"')
    fin = header.index("</div>\n          </div>", inicio)
    return header[inicio:fin]


def test_barra_superior_pildoras_metricas_limpias():
    html = INDEX.read_text(encoding="utf-8")
    header = _header_html(html)

    # 1. Repaso usa ícono propio i-repaso
    assert 'id="hdr-due"' in header
    due_match = re.search(r'id="hdr-due"[^>]*>(.*?)</span>', header, re.DOTALL)
    assert due_match and "i-repaso" in due_match.group(1), f"hdr-due no usa i-repaso: {due_match}"
    assert "🧠" not in due_match.group(1)

    # 2. Racha, repaso y foco están en el contenedor principal md:flex
    assert 'id="hdr-streak"' in header
    assert 'id="hdr-focus"' in header
    assert 'id="hdr-retention"' in header

    # Foco está antes de la división 2xl
    idx_streak = header.index('id="hdr-streak"')
    idx_due = header.index('id="hdr-due"')
    idx_focus = header.index('id="hdr-focus"')
    idx_2xl = header.index("2xl:flex")
    idx_retention = header.index('id="hdr-retention"')

    assert idx_streak < idx_due < idx_focus < idx_2xl < idx_retention

    # 3. Duolingo e índice de apuntes salieron de la barra
    assert 'id="hdr-duolingo"' not in header
    assert 'id="hdr-vector"' not in header


def test_barra_superior_sin_atajos_duplicados_y_recargar_en_menu():
    html = INDEX.read_text(encoding="utf-8")
    header = _header_html(html)

    # El botón ⌨️ suelto salió de la barra
    assert 'data-accion="abrir-atajos-teclado"' not in header

    # El botón 🔄 suelto salió de la barra
    # Solo debe existir recargar-pagina dentro del menú desplegable
    assert header.count('data-accion="recargar-pagina"') == 1
    dropdown = _dropdown_html(header)
    assert 'data-accion="recargar-pagina"' in dropdown

    # Entrada de atajos en el header: exactamente una, dentro del dropdown
    assert header.count("Atajos de teclado") == 1
    assert 'data-accion="abrir-atajos-desde-menu"' in dropdown


def test_menu_visible_en_modo_local_con_opciones():
    html = INDEX.read_text(encoding="utf-8")
    header = _header_html(html)

    # #hdr-account NO está oculto por defecto con class="hidden"
    account_wrapper = re.search(r'<div id="hdr-account" class="([^"]+)"', header)
    assert account_wrapper, "No se encontró #hdr-account"
    assert "hidden" not in account_wrapper.group(1).split(), "#hdr-account no debe tener 'hidden'"

    # En modo local muestra ícono de menú y texto Menú
    btn_user_menu = header[header.index('id="btn-user-menu"'):header.index('id="user-dropdown-menu"')]
    assert 'id="hdr-menu-icono"' in btn_user_menu and "i-menu" in btn_user_menu
    assert 'id="hdr-user-label"' in btn_user_menu and "Menú" in btn_user_menu

    # Encabezado del dropdown dice Opciones
    dropdown = _dropdown_html(header)
    assert 'id="menu-cuenta-titulo"' in dropdown
    assert "Opciones" in dropdown

    # Ranuras requeridas intactas
    assert 'id="menu-cuenta-ranura-arriba"' in dropdown
    assert 'id="menu-cuenta-ranura-abajo"' in dropdown


def test_boton_de_tema_en_barra_superior():
    html = INDEX.read_text(encoding="utf-8")
    header = _header_html(html)

    # Botón existe entre indicador de salud y menú
    assert 'id="btn-tema"' in header
    assert 'data-accion="alternar-tema"' in header

    idx_health = header.index('id="btn-system-health"')
    idx_tema = header.index('id="btn-tema"')
    idx_account = header.index('id="hdr-account"')
    assert idx_health < idx_tema < idx_account

    btn_tema = header[idx_tema:idx_account]
    assert 'aria-label="Tema: oscuro. Cambiar a claro"' in btn_tema
    assert 'title="Tema: oscuro. Cambiar a claro"' in btn_tema
    assert "i-tema-oscuro" in btn_tema


def test_logica_tema_ciclo_y_sincronia_con_select():
    tema_js = (ESTATICO / "js" / "tema.js").read_text(encoding="utf-8")

    # Ciclo de temas: alternar y siguienteTema
    assert "siguienteTema" in tema_js
    assert "alternar" in tema_js
    assert "actualizarBotonTema" in tema_js
    assert "aulento:tema" in tema_js

    # Etiquetas de aria-label y title
    assert "Tema: oscuro. Cambiar a claro" in tema_js or "Cambiar a" in tema_js
    assert "según el sistema" in tema_js

    # Acción alternar-tema registrada
    config_js = (ESTATICO / "js" / "pantalla-config.js").read_text(encoding="utf-8")
    assert "'alternar-tema'" in config_js


def test_duolingo_e_indice_en_popover_de_salud():
    comunes_js = (ESTATICO / "js" / "comunes.js").read_text(encoding="utf-8")
    fsrs_js = (ESTATICO / "js" / "pantalla-fsrs.js").read_text(encoding="utf-8")
    brain_js = (ESTATICO / "js" / "pantalla-brain.js").read_text(encoding="utf-8")

    # comunes.js incluye Duolingo e Índice de apuntes con sus acciones
    assert "salud-duolingo" in comunes_js
    assert "salud-vector" in comunes_js
    assert "sincronizar-duolingo-cabecera" in comunes_js
    assert "ir-a-seccion-vectores" in comunes_js
    assert "indice" in comunes_js

    # pantalla-fsrs escribe a las filas nuevas en vez de hdr-duolingo
    assert "salud-duolingo-estado" in fsrs_js
    assert "hdr-duolingo" not in fsrs_js

    # pantalla-brain escribe a las filas nuevas en vez de hdr-vector
    assert "salud-vector-estado" in brain_js
    assert "hdr-vector" not in brain_js


def test_version_bump_recursos_a_2_23():
    html = INDEX.read_text(encoding="utf-8")
    assert "?v=2.22" not in html
    assert "?v=2.23" in html

    sw = (ESTATICO / "sw.js").read_text(encoding="utf-8")
    assert "aulento-v6" in sw
    assert "aulento-v5" not in sw
