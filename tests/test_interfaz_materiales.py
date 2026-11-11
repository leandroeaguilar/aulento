"""La interfaz de «Mis materiales» y de lo que reemplazó a Google Drive y OneDrive (048, T5: R1, R6, R9, R11 y R12).

Son contratos sobre `index.html` y `app.js`, atados a las rutas reales de la API: si el frontend pide algo que el
servidor ya no tiene, o manda un campo con otro nombre, el test falla.
"""

import re
from functools import cache
from pathlib import Path

import pytest

import aulento.web as web_pkg
from aulento.core.materiales import EXTENSIONES_ADMITIDAS
from aulento.mcp.agent import ORIGEN_MATERIALES, ORIGEN_TODO, normalizar_origen
from aulento.vault.cloud_notes import MaterialNoteRequest
from aulento.web.app import create_app
from aulento.web.routes.fsrs import HarvestPreviewRequest
from aulento.web.routes.materiales import CAMPO_DEL_ARCHIVO
from tests.front import js_del_front

pytestmark = pytest.mark.sin_sesion

ESTATICO = Path(web_pkg.__file__).parent / "static"
HTML = (ESTATICO / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")
JS = js_del_front().replace("\r\n", "\n")


def _funcion_js(nombre: str) -> str:
    inicio = JS.index(f"function {nombre}(")
    return JS[inicio:JS.index("\n}\n", inicio) + 3]


def _bloque_html(desde: str, hasta: str) -> str:
    inicio = HTML.index(desde)
    return HTML[inicio:HTML.index(hasta, inicio)]


@cache
def _rutas_de_la_api() -> tuple[tuple[str, re.Pattern], ...]:
    """Las rutas de la API, sacadas de su OpenAPI, con los parámetros de la ruta como comodines."""
    rutas = []
    for ruta, operaciones in create_app().openapi()["paths"].items():
        patron = re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", ruta) + "$")
        rutas.extend((metodo.upper(), patron) for metodo in operaciones)
    return tuple(rutas)


def _existe(metodo: str, ruta: str) -> bool:
    return any(m == metodo and patron.match(ruta) for m, patron in _rutas_de_la_api())


# --- R1: subir desde la PC ---


def test_r1_el_selector_de_archivos_acepta_los_cuatro_tipos_y_varios_a_la_vez():
    entrada = re.search(r'<input type="file" id="materiales-input"[^>]*>', HTML)
    assert entrada, "falta el selector de archivos de «Mis materiales»"
    etiqueta = entrada.group(0)
    assert " multiple" in etiqueta
    aceptados = set(re.search(r'accept="([^"]*)"', etiqueta).group(1).split(","))
    assert aceptados == set(EXTENSIONES_ADMITIDAS) == {".pdf", ".md", ".markdown", ".txt"}
    assert 'data-accion="subir-materiales-elegidos"' in etiqueta
    # La validación previa del navegador usa los mismos tipos que el servidor
    assert "const EXTENSIONES_DE_MATERIAL = ['.pdf', '.md', '.markdown', '.txt'];" in JS


def test_r1_la_subida_va_de_a_un_archivo_con_su_avance_y_en_el_campo_que_lee_el_servidor():
    assert _existe("POST", "/api/materiales")
    envio = _funcion_js("enviarMaterial")
    assert "xhr.open('POST', '/api/materiales');" in envio
    assert f"formulario.append('{CAMPO_DEL_ARCHIVO}', archivo);" in envio
    assert "xhr.upload.onprogress" in envio and "e.loaded / e.total" in envio

    elegidos = _funcion_js("subirMaterialesElegidos")
    # De a uno: cada subida espera a la anterior, y al final se recarga la lista y el espacio
    assert "for (const archivo of archivos) {\n      await subirUnMaterial(archivo);" in elegidos
    assert elegidos.index("await subirUnMaterial(archivo)") < elegidos.index("await loadMisMateriales();")


def test_r1_los_rechazos_muestran_el_motivo_del_servidor():
    subida = _funcion_js("subirUnMaterial")
    assert "xhr.status === 201" in subida
    assert "avisar(motivoDelRechazo(xhr), xhr.status === 409 ? 'aviso' : 'error');" in subida
    # 413, 415, 422 y 409 traen su explicación en `detail`
    assert "JSON.parse(xhr.responseText).detail" in _funcion_js("motivoDelRechazo")
    # El nombre del archivo es del usuario: va como texto, nunca como HTML
    fila = _funcion_js("filaDeSubida")
    assert "nombreEl.textContent = nombre;" in fila and "innerHTML" not in fila


# --- R6: lista, espacio, texto y borrado ---


def test_r6_la_lista_y_la_barra_de_espacio_salen_de_la_api():
    assert _existe("GET", "/api/materiales")
    assert "fetch('/api/materiales')" in _funcion_js("loadMisMateriales")
    barra = _funcion_js("renderBarraDeEspacio")
    assert "`${describirBytes(uso.usado)} de ${describirBytes(uso.tope)}`" in barra
    assert 'id="materiales-espacio-texto"' in HTML and 'id="materiales-espacio-barra"' in HTML


def test_r6_cada_fila_tiene_sus_acciones_y_el_nombre_escapado():
    filas = _funcion_js("renderMisMateriales")
    for accion in (
        'data-accion="preguntar-material-tutor" data-id="${id}"',
        'data-accion="ver-texto-material" data-id="${id}"',
        'data-accion="borrar-material" data-id="${id}"',
    ):
        assert accion in filas
    # «Indexar» solo aparece con pgvector encendido
    assert '${state.vectorOnline ? `<button type="button" data-accion="indexar-material" data-id="${id}"' in filas
    # El nombre del material lo eligió el usuario: siempre escapado
    assert "${escapeHtml(m.nombre)}" in filas
    assert not re.search(r"\$\{m\.nombre\}", filas)
    # El filtro es local, por nombre
    # Filtra mientras se escribe (antes, oninput), no al salir del campo
    assert 'data-accion="filtrar-materiales" data-al-escribir' in HTML
    assert "m.nombre.toLowerCase().includes(filtro)" in filas


def test_r6_ver_texto_y_borrar_usan_las_rutas_del_material():
    assert _existe("GET", "/api/materiales/1") and _existe("DELETE", "/api/materiales/1")
    ver = _funcion_js("verTextoDeMaterial")
    assert "fetch(`/api/materiales/${Number(id)}`)" in ver
    assert "getElementById('modal-material-content').textContent = data.texto;" in ver
    assert "data.texto_cortado" in ver
    assert 'id="material-texto-modal"' in HTML and 'id="modal-material-cortado"' in HTML

    borrar = _funcion_js("borrarMaterial")
    # Pide confirmación antes de borrar
    assert borrar.index("showConfirmDialog(") < borrar.index("if (!confirmado) return;") < borrar.index("method: 'DELETE'")
    assert "fetch(`/api/materiales/${Number(id)}`, { method: 'DELETE' })" in borrar


def test_r6_indexar_un_material_manda_el_tipo_que_acepta_la_indexacion_selectiva():
    assert _existe("POST", "/api/vectors/index-selection")
    assert "items: [{ type: 'material', id: String(id) }]" in _funcion_js("indexarMaterial")
    seleccion = _funcion_js("openSelectiveIndexModal")
    assert 'data-type="material"' in seleccion and "escapeHtml(m.nombre)" in seleccion
    assert "provider" not in _funcion_js("executeSelectiveIndexing")


def test_r8_la_demo_no_ve_subir_ni_borrar():
    filas = _funcion_js("renderMisMateriales")
    assert "botonSubir.classList.toggle('hidden', demo);" in filas
    assert '${demo ? \'\' : `<button type="button" data-accion="borrar-material" data-id="${id}"' in filas
    assert 'id="materiales-aviso-demo"' in HTML


# --- R9: el tutor sobre los materiales ---


def test_r9_el_tutor_pregunta_por_el_material_elegido_sin_selector_de_nube():
    selector = _bloque_html('<select id="agent-provider-select"', "</select>")
    opciones = re.findall(r'<option value="([^"]*)"', selector)
    assert opciones == [ORIGEN_TODO, ORIGEN_MATERIALES]
    # El servidor entiende cada opción tal cual, sin caer en el valor por defecto
    assert all(normalizar_origen(opcion) == opcion for opcion in opciones)

    pregunta = _funcion_js("askCloudAgent")
    assert "material_id: materialId" in pregunta and "file_id" not in pregunta
    assert "const materialId = state.cloudAgent.selectedMaterialId || null;" in pregunta
    assert "state.cloudAgent.selectedMaterialId = material.id;" in _funcion_js("askAgentAboutMaterial")


# --- R11: cosecha y apuntes desde los materiales ---


def test_r11_la_cosecha_ofrece_mis_materiales_y_manda_el_material_elegido():
    assert HarvestPreviewRequest.model_fields["material_id"]
    selector = _bloque_html('<select id="harvester-source-select"', "</select>")
    assert re.findall(r'<option value="([^"]*)"', selector) == ["vault", "materiales", "ai"]
    assert 'id="harvester-material-select"' in HTML

    payload = _funcion_js("harvestPreviewPayload")
    assert "payload.material_id = Number(materialSelect.value);" in payload
    assert "if (source !== 'materiales') return payload;" in payload
    # El nombre del material va como texto en la lista de opciones
    assert "opt.textContent = m.nombre;" in _funcion_js("loadHarvestMaterialOptions")


def test_r11_el_apunte_sale_de_un_material_con_las_rutas_nuevas():
    assert _existe("GET", "/api/vault/notes/materials") and _existe("POST", "/api/vault/notes/from-material")
    assert "fetch('/api/vault/notes/materials')" in _funcion_js("loadMaterialNoteOptions")
    assert "opt.textContent = m.name;" in _funcion_js("loadMaterialNoteOptions")
    pedido = _funcion_js("materialNotePayload")
    campos = set(re.findall(r"^    (\w+):", pedido, re.MULTILINE))
    assert campos <= set(MaterialNoteRequest.model_fields) and "material_id" in campos
    assert "fetch('/api/vault/notes/from-material'" in _funcion_js("previewMaterialNote")
    assert "fetch('/api/vault/notes/from-material?save_to_vault=true'" in _funcion_js("saveMaterialNoteToVault")


def test_r11_la_guia_de_clase_pide_buscar_en_los_materiales():
    assert "include_materials: isChecked('prompt-toggle-materiales')," in _funcion_js("readPromptOptions")
    # 072: el cambio del tilde dispara la acción delegada que vuelve a armar la guía
    assert re.search(r'<input type="checkbox" id="prompt-toggle-materiales"[^>]*data-accion="ruta-refrescar-prompt-tema"', HTML)
    assert "['ruta-refrescar-prompt-tema', () => refreshTopicPrompt()]" in JS


# --- R12: nada de Google Drive ni OneDrive en la interfaz ---

RUTAS_RETIRADAS = (
    "/api/mcp/gdrive",
    "/api/mcp/onedrive",
    "/api/mcp/search",
    "/api/mcp/config",
    "/api/mcp/toggle",
    "/api/mcp/status",
    "/api/mcp/material/",
    "/api/vectors/index-cloud-file",
    "/api/vault/notes/cloud-materials",
    "/api/vault/notes/from-cloud",
)


@pytest.mark.parametrize("ruta", RUTAS_RETIRADAS)
def test_r12_la_interfaz_no_llama_rutas_de_drive_ni_onedrive(ruta):
    assert ruta not in JS
    assert ruta not in HTML


def test_r12_cada_ruta_de_materiales_que_usa_la_interfaz_existe():
    usadas = set(re.findall(r"""['`](/api/(?:materiales|vault/notes/(?:materials|from-material)|vectors/index-selection)[^'`?]*)""", JS))
    assert usadas, "la interfaz no usa las rutas de materiales"
    for ruta in usadas:
        ejemplo = re.sub(r"\$\{[^}]+\}", "1", ruta)
        assert any(patron.match(ejemplo) for _, patron in _rutas_de_la_api()), ruta


def test_r12_sin_conectores_de_nube_en_configuracion_el_asistente_ni_el_estado():
    for resto in ("config-mcp-providers-list", "mcp-config-modal", "mcp-connectors-wrapper", "mcp-control-panel",
                  "mcp-results-container", "wizard-gdrive-badge", "wizard-onedrive-badge", "wizard-summary-gdrive"):
        assert resto not in HTML and resto not in JS
    for funcion in ("authorizeGdrive", "authorizeOnedrive", "loadMcpStatus", "executeMcpSearch",
                    "toggleConnectorPanel", "indexSingleCloudFile", "loadConfigMcpList", "wizardAuthorizeCloud"):
        assert f"function {funcion}(" not in JS
    # Ni un identificador, id o ruta de los conectores (el texto que explica cómo traer archivos de Drive sí queda)
    assert not re.search(r"gdrive|onedrive", JS)
    assert not re.search(r"gdrive|onedrive", HTML)
    # Google Calendar sigue en su sección de Configuración
    bloque = _bloque_html('id="cfg-sec-cloud"', 'id="cfg-sec-vault"')
    assert 'data-accion="config-abrir-gcal"' in bloque
    assert "['config-abrir-gcal', () => openGoogleCalendarModal()]" in JS
