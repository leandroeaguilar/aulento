"""Pruebas de capacidades y textos por versión (Feature 056: R1 a R9)."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from aulento.core.extensiones import Extension
from aulento.core.secretos import AlmacenDeSecretos
from aulento.db.connection import get_connection
from aulento.web.app import create_app

RAIZ = Path(__file__).resolve().parent.parent
STATIC_DIR = RAIZ / "src" / "aulento" / "web" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
CAPACIDADES_JS = STATIC_DIR / "capacidades.js"


# =====================================================================
# T1: Punto de extensión y GET /api/capacidades (R2, R8)
# =====================================================================


def test_capacidades_en_modo_local_por_defecto(monkeypatch):
    """En local: carpeta_local y mcp_escritorio son true, mcp_web es false y el modo es local."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/api/capacidades")
        assert res.status_code == 200
        datos = res.json()
        assert datos["modo"] == "local"
        assert datos["capacidades"]["carpeta_local"] is True
        assert datos["capacidades"]["mcp_escritorio"] is True
        assert datos["capacidades"]["mcp_web"] is False
        assert isinstance(datos["textos"], dict)


def test_extension_suma_y_modifica_capacidades_y_textos(monkeypatch):
    """Una extensión de prueba puede sumar capacidades, sobreescribir existentes y aportar textos."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    ext_prueba = Extension(
        nombre="prueba_cap",
        capacidades={"nueva_capacidad": True, "mcp_escritorio": False},
        textos={"mi_texto": "Texto personalizado de prueba"},
    )
    app = create_app(extensiones=[ext_prueba])
    with TestClient(app) as client:
        res = client.get("/api/capacidades")
        assert res.status_code == 200
        datos = res.json()
        assert datos["capacidades"]["nueva_capacidad"] is True
        assert datos["capacidades"]["mcp_escritorio"] is False
        assert datos["textos"]["mi_texto"] == "Texto personalizado de prueba"


def test_google_libros_sigue_al_cliente_configurado(monkeypatch):
    """google_libros es false sin credenciales y true si hay cliente compartido o propio (R8)."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    # 1. Sin cliente
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/api/capacidades")
        assert res.status_code == 200
        assert res.json()["capacidades"]["google_libros"] is False

    # 2. Con cliente compartido simulado
    cliente_mock = {"web": {"client_id": "mock_id", "client_secret": "mock_sec"}}
    monkeypatch.setattr(
        "aulento.core.cliente_google_compartido.obtener_cliente_compartido",
        lambda: cliente_mock,
    )
    app2 = create_app()
    with TestClient(app2) as client:
        res = client.get("/api/capacidades")
        assert res.status_code == 200
        assert res.json()["capacidades"]["google_libros"] is True

    # 3. Con cliente propio en la cuenta
    monkeypatch.setattr(
        "aulento.core.cliente_google_compartido.obtener_cliente_compartido",
        lambda: None,
    )
    conn = get_connection()
    try:
        secretos = AlmacenDeSecretos(conn, 1)
        secretos.guardar("google_books_cliente", json.dumps(cliente_mock))
        conn.commit()
    finally:
        conn.close()

    app3 = create_app()
    with TestClient(app3) as client:
        res = client.get("/api/capacidades")
        assert res.status_code == 200
        assert res.json()["capacidades"]["google_libros"] is True


# =====================================================================
# T2: capacidades.js y marcas en index.html (R1, R3, R4, R7)
# =====================================================================


def test_index_html_carga_capacidades_js_antes_de_app_js():
    """index.html debe incluir capacidades.js antes de app.js."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '<script src="/static/capacidades.js" defer></script>' in html
    pos_cap = html.index("/static/capacidades.js")
    pos_app = html.index("/static/app.js")
    assert pos_cap < pos_app


def test_index_html_tiene_marcas_data_requiere():
    """index.html marca con data-requiere el bloque MCP, Google Libros y carpeta local."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'data-requiere="google_libros"' in html
    assert 'data-requiere="carpeta_local"' in html
    assert 'data-requiere="mcp_escritorio"' in html


def test_capacidades_js_expone_contrato_y_dispara_evento():
    """capacidades.js define window.SE_CAPACIDADES, window.seTiene y evento capacidades-listas."""
    js = CAPACIDADES_JS.read_text(encoding="utf-8")
    assert "window.SE_CAPACIDADES" in js
    assert "window.seTiene" in js
    assert "capacidades-listas" in js
    assert "data-texto" in js
    assert "data-requiere" in js


# =====================================================================
# T3: Textos de la nube y portada (R6)
# =====================================================================


# =====================================================================
# T4: Mis notas, Calendar y Sincronización automática (R5, R9)
# =====================================================================


def test_index_html_no_dice_vault_de_obsidian_ni_tu_vault():
    """index.html no debe contener 'Vault de Obsidian' ni 'tu Vault' en ningún lugar."""
    html = INDEX_HTML.read_text(encoding="utf-8").lower()
    assert "vault de obsidian" not in html
    assert "tu vault" not in html
    assert "obsidian vault" not in html


def test_boton_google_calendar_dice_exportar():
    """El botón de Google Calendar debe decir que exporta eventos, no que sincroniza (R9)."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "Exportar a Google Calendar" in html


def test_modal_sincronizacion_automatica_de_cursos_presente():
    """Existe el modal legible que explica qué hace la sincronización de cursos (R9)."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "modal-course-webhook" in html
    assert "Recibe el avance que manda otra herramienta" in html
