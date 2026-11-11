"""La interfaz cuando Aulento corre en un servidor: sin botón gigante de demo, textos que no dicen
"local" y Duolingo y las carpetas del tutor configurables desde la web.

Son contratos sobre `index.html` y `app.js` servidos por la app.
"""


import pytest
from fastapi.testclient import TestClient

from aulento.web.app import create_app
from tests.front import js_del_front


@pytest.fixture
def client(cuenta):
    return TestClient(create_app())


def _html(client) -> str:
    return client.get("/").text.replace("\r\n", "\n")


def _app_js(client=None) -> str:
    return js_del_front().replace("\r\n", "\n")


def _funcion_js(js: str, nombre: str) -> str:
    inicio = js.index(f"function {nombre}(")
    return js[inicio:js.index("\n}\n", inicio) + 3]


def test_la_pagina_del_core_no_ofrece_la_demo(client):
    """La demo es de la nube (051): el core no tiene botón para entrar a ella, ni en la barra ni en el menú."""
    html = _html(client)
    js = _app_js(client)
    for senal in ("sidebar-btn-demo", "btn-demo-switch", "/api/auth/demo"):
        assert senal not in html and senal not in js


def test_cada_texto_local_first_tiene_su_clave_de_texto(client):
    """Los textos que solo valen en local llevan data-texto: la extensión activa puede reemplazarlos (056)."""
    html = _html(client)
    for texto in ["Local-First", "Base local en tu computadora", "fuera de tu equipo", "en tu máquina"]:
        for linea in (linea for linea in html.splitlines() if texto in linea):
            assert "data-texto=" in linea, linea.strip()
    # La interfaz ya no decide por el nombre de host del navegador (056 R1)
    assert "enServidor" not in _app_js(client)


def test_duolingo_tiene_seccion_en_configuracion_y_un_modal_en_vez_de_prompt(client):
    html = _html(client)
    js = _app_js(client)
    assert 'id="cfg-nav-duolingo"' in html and 'id="cfg-sec-duolingo"' in html
    assert 'id="duolingo-modal"' in html and 'id="duolingo-username-input"' in html
    assert "'duolingo'" in _funcion_js(js, "switchConfigSection")
    assert "window.prompt" not in _funcion_js(js, "syncDuolingoFromHeader")
    assert "openDuolingoModal()" in _funcion_js(js, "syncDuolingoFromHeader")
    # Sin perfil del usuario nuevo, la vista previa no muestra la racha del anterior
    assert "preview.classList.toggle('hidden', !state.duolingoProfile)" in _funcion_js(js, "saveDuolingoUsername")


def test_las_carpetas_del_tutor_tienen_seccion_y_se_crean_y_eligen_por_la_api(client):
    html = _html(client)
    js = _app_js(client)
    assert 'id="cfg-nav-vault"' in html and 'id="cfg-sec-vault"' in html
    assert "'vault'" in _funcion_js(js, "switchConfigSection")
    assert "fetch('/api/vault/folders'" in _funcion_js(js, "loadVaultFolders")
    assert "fetch('/api/vault/folders'" in _funcion_js(js, "postVaultFolder")
    guardar = _funcion_js(js, "saveTutorFolders")
    assert "fetch('/api/vault/tutor-folders'" in guardar
    # Al guardar no se pierden las carpetas del tutor que existen pero no entran en el listado
    assert "carpetasElegidasQueExisten()" in guardar
    assert "!faltan.has(r)" in _funcion_js(js, "carpetasElegidasQueExisten")
