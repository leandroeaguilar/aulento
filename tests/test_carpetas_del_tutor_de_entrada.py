"""Pruebas de la feature 064: Carpetas del tutor de entrada en el vault y paso en el asistente.

Cubre requisitos R1 a R6 y correcciones de revisión:
- R1: Vault propio nace con carpetas por defecto y marca; carpetas borradas no se recrean tras la primera apertura.
      Fuente única para CARPETAS_POR_DEFECTO derivada de ALLOWED_FOLDERS.
      Marca oculta no aparece en listar_carpetas ni en export.zip.
- R2: Vault externo no se toca automáticamente; botón y ruta para crear las que faltan.
- R3, R4, R5, R6: Paso Carpetas en el asistente (4 pasos coherentes), omitir paso no altera nada,
      guardar carpetas se refleja en GET /api/vault/folders («Mis notas»),
      renderizado escapa descripciones con escapeHtml, sin datos en onclick, sin código muerto.
- 063 en UI: checkVectorStatus muestra «Índice local» o «Índice del servidor» y escapa motivo_no_disponible.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from front import js_del_front

from aulento.config import dir_de_cuenta
from aulento.db.connection import get_connection
from aulento.vault.carpetas import (
    DESCRIPCION_DE_CARPETAS,
    carpetas_del_vault,
    crear_carpetas_faltantes,
    listar_carpetas,
)
from aulento.vault.reader import ALLOWED_FOLDERS
from aulento.vault.rutas import (
    CARPETA_DEL_VAULT,
    MARCA_CARPETAS_DEL_TUTOR,
    carpetas_por_defecto,
    escribir_zip_del_vault,
    fijar_vault_externo,
    quitar_vault_externo,
    vault_de_la_cuenta,
    vault_propio,
)
from aulento.web.app import create_app

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "aulento" / "web" / "static"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# --- R1: Carpetas por defecto en vault propio y persistencia ---


def test_r1_cuenta_nueva_nace_con_carpetas_del_tutor_y_marca(cuenta):
    """R1: El vault propio de una cuenta tiene creadas las carpetas por defecto y la marca desde que se crea."""
    vault = vault_propio(cuenta)
    assert vault.is_dir()
    for nombre in carpetas_por_defecto():
        sub = vault / nombre
        assert sub.is_dir(), f"Falta la carpeta por defecto {nombre}"
    marca = vault / MARCA_CARPETAS_DEL_TUTOR
    assert marca.is_file(), "La marca .carpetas-del-tutor-creadas debe existir tras la creación inicial"


def test_r1_carpeta_borrada_por_usuario_no_vuelve_a_crearse(cuenta):
    """R1 (corrección): Si la persona borra una carpeta por defecto, no debe recrearse en aperturas posteriores."""
    vault = vault_propio(cuenta)
    carpeta_borrar = vault / "06 Raw"
    assert carpeta_borrar.is_dir()

    # Usuario borra la carpeta
    carpeta_borrar.rmdir()
    assert not carpeta_borrar.exists()

    # Al volver a abrir o resolver el vault propio, la marca impide que se vuelva a crear
    abierto = vault_propio(cuenta)
    assert not (abierto / "06 Raw").exists(), "Una carpeta borrada por el usuario no debe volver a aparecer"


def test_r1_cuenta_existente_sin_marca_crea_las_faltantes_una_vez(cuenta):
    """R1: Cuenta previa a 064 (sin marca) recibe las carpetas por defecto que falten una única vez."""
    vault = dir_de_cuenta(cuenta) / CARPETA_DEL_VAULT
    vault.mkdir(parents=True, exist_ok=True)
    marca = vault / MARCA_CARPETAS_DEL_TUTOR
    if marca.exists():
        marca.unlink()

    # Nota previa existente
    apunte = vault / "04 Knowledge" / "mi_apunte.md"
    apunte.parent.mkdir(parents=True, exist_ok=True)
    apunte.write_text("# Concepto previo", encoding="utf-8")
    assert not (vault / "06 Raw").exists()
    assert not marca.exists()

    # Primera apertura: se crean las carpetas que falten y se escribe la marca
    abierto = vault_propio(cuenta)
    assert (abierto / "06 Raw").is_dir()
    assert marca.is_file()
    assert apunte.read_text(encoding="utf-8") == "# Concepto previo"

    # Si luego borra una carpeta, ya no se recrea
    (abierto / "06 Raw").rmdir()
    abierto_nuevamente = vault_propio(cuenta)
    assert not (abierto_nuevamente / "06 Raw").exists()


def test_r1_marca_oculta_no_aparece_en_listado_ni_en_export(cuenta, tmp_path):
    """R1: La marca oculta no aparece en listar_carpetas ni se incluye en el zip exportado."""
    vault = vault_propio(cuenta)
    assert (vault / MARCA_CARPETAS_DEL_TUTOR).exists()

    # No aparece en el listado de carpetas
    carpetas = listar_carpetas(vault)
    rutas_carpetas = [c["ruta"] for c in carpetas]
    assert MARCA_CARPETAS_DEL_TUTOR not in rutas_carpetas
    assert not any(MARCA_CARPETAS_DEL_TUTOR in r for r in rutas_carpetas)

    # Export con vault sin notas: debe contener solo LEEME.md y excluir la marca
    zip_vacio = tmp_path / "vacio.zip"
    total = escribir_zip_del_vault(vault, zip_vacio)
    assert total == 0, "No debe contar la marca como archivo de notas"
    with zipfile.ZipFile(zip_vacio) as zf:
        nombres = zf.namelist()
        assert MARCA_CARPETAS_DEL_TUTOR not in nombres
        assert "LEEME.md" in nombres

    # Export con notas: debe incluir la nota y excluir la marca
    (vault / "04 Knowledge" / "apunte.md").write_text("# Apunte", encoding="utf-8")
    zip_con_notas = tmp_path / "con_notas.zip"
    total_con_notas = escribir_zip_del_vault(vault, zip_con_notas)
    assert total_con_notas == 1
    with zipfile.ZipFile(zip_con_notas) as zf:
        nombres = zf.namelist()
        assert MARCA_CARPETAS_DEL_TUTOR not in nombres
        assert "04 Knowledge/apunte.md" in nombres


def test_r1_fuente_unica_de_carpetas_por_defecto():
    """R1: CARPETAS_POR_DEFECTO se deriva de ALLOWED_FOLDERS y coincide exactamente con DESCRIPCION_DE_CARPETAS."""
    assert carpetas_por_defecto() == tuple(ALLOWED_FOLDERS)
    assert carpetas_por_defecto() == tuple(ALLOWED_FOLDERS)
    assert set(DESCRIPCION_DE_CARPETAS.keys()) == set(ALLOWED_FOLDERS)
    assert list(DESCRIPCION_DE_CARPETAS.keys()) == ALLOWED_FOLDERS


def test_r1_descripciones_de_carpetas_por_defecto(cuenta):
    """R1: Las carpetas por defecto tienen descripciones claras sobre su propósito."""
    assert "04 Knowledge" in DESCRIPCION_DE_CARPETAS
    assert "06 Raw" in DESCRIPCION_DE_CARPETAS
    assert "02 MOCs" in DESCRIPCION_DE_CARPETAS

    with get_connection() as conn:
        vault = vault_propio(cuenta)
        info = carpetas_del_vault(conn, cuenta, vault)
        assert info["descripciones"] == DESCRIPCION_DE_CARPETAS
        for c in info["carpetas"]:
            if c["ruta"] in DESCRIPCION_DE_CARPETAS:
                assert c["descripcion"] == DESCRIPCION_DE_CARPETAS[c["ruta"]]


# --- R2: Vault externo y creación de faltantes ---


def test_r2_vault_externo_no_crea_carpetas_por_su_cuenta(cuenta, tmp_path):
    """R2: Con vault externo el sistema NO crea carpetas por su cuenta; se reportan en faltan."""
    externo = tmp_path / "obsidian_externo"
    externo.mkdir()

    with get_connection() as conn:
        fijar_vault_externo(conn, cuenta, externo)
        try:
            vault = vault_de_la_cuenta(conn, cuenta)
            assert vault == externo.resolve()
            # Ninguna carpeta por defecto fue creada automáticamente
            for nombre in carpetas_por_defecto():
                assert not (externo / nombre).exists(), f"No debía crearse {nombre} sola en vault externo"

            info = carpetas_del_vault(conn, cuenta, vault)
            assert set(info["faltan"]) >= set(carpetas_por_defecto())
        finally:
            quitar_vault_externo(conn, cuenta)


def test_r2_crear_carpetas_faltantes_en_vault_externo(cuenta, tmp_path):
    """R2: crear_carpetas_faltantes crea las carpetas en el vault externo."""
    externo = tmp_path / "obsidian_externo_crear"
    externo.mkdir()

    with get_connection() as conn:
        fijar_vault_externo(conn, cuenta, externo)
        try:
            creadas = crear_carpetas_faltantes(conn, cuenta, externo)
            assert set(creadas) >= set(carpetas_por_defecto())
            for nombre in carpetas_por_defecto():
                assert (externo / nombre).is_dir()

            info = carpetas_del_vault(conn, cuenta, externo)
            assert info["faltan"] == []
        finally:
            quitar_vault_externo(conn, cuenta)


def test_r2_ruta_api_create_missing_folders(client, cuenta, tmp_path):
    """R2: POST /api/vault/folders/create-missing crea las carpetas del tutor faltantes."""
    externo = tmp_path / "obsidian_api_missing"
    externo.mkdir()

    with get_connection() as conn:
        fijar_vault_externo(conn, cuenta, externo)

    try:
        # Inicialmente faltan
        res = client.get("/api/vault/folders")
        assert res.status_code == 200
        assert set(res.json()["faltan"]) >= set(carpetas_por_defecto())

        # Se llama a la ruta para crearlas
        post_res = client.post("/api/vault/folders/create-missing")
        assert post_res.status_code == 200, post_res.text
        data = post_res.json()
        assert data["faltan"] == []
        for nombre in carpetas_por_defecto():
            assert (externo / nombre).is_dir()
    finally:
        with get_connection() as conn:
            quitar_vault_externo(conn, cuenta)


# --- R3, R4, R5, R6: Asistente de inicio, omitir paso y escapeHtml ---


def test_r3_r5_estaticos_del_asistente_cuatro_pasos():
    """R3 y R5: El asistente tiene 4 pasos en el subtítulo, en la barra de progreso y en el DOM."""
    html_file = STATIC_DIR / "index.html"
    assert html_file.is_file()
    html = html_file.read_text(encoding="utf-8")

    # Subtítulo 4 pasos
    assert "4 pasos rápidos" in html

    # Indicadores del stepper (1 a 4)
    assert 'id="wizard-step-ind-1"' in html
    assert 'id="wizard-step-ind-2"' in html
    assert 'id="wizard-step-ind-3"' in html
    assert 'id="wizard-step-ind-4"' in html

    # Contenedores de cada paso (1 a 4)
    assert 'id="wizard-step-1"' in html
    assert 'id="wizard-step-2"' in html
    assert 'id="wizard-step-3"' in html
    assert 'id="wizard-step-4"' in html

    # Elementos requeridos del paso Carpetas (R3)
    assert 'id="wizard-vault-folders-list"' in html
    assert 'id="wizard-folder-form"' in html
    assert 'id="wizard-new-folder"' in html
    assert 'id="wizard-btn-create-folder"' in html
    assert 'id="wizard-btn-save-folders"' in html
    assert 'id="wizard-vault-folders-count"' in html


def test_r5_r6_controlador_javascript_seguro_y_cuatro_pasos():
    """R5 y R6: WIZARD_PASOS = 4, sin datos en onclick, con data-ruta y escapeHtml."""
    js = js_del_front()

    # Constante de 4 pasos
    assert "const WIZARD_PASOS = 4;" in js

    # Paso Carpetas reusa y define las funciones
    assert "function renderFolderItems(" in js
    assert "function bindWizardFolderEvents(" in js
    assert "function setWizardFoldersMessage(" in js

    # R6: Checkbox usa data-ruta con listener, no interpolación de nombres en onclick
    assert 'data-ruta="${escapeHtml(c.ruta)}"' in js
    assert 'onclick="toggleTutorFolder(' not in js

    # Botón 'Crear las que faltan'
    assert "Crear las que faltan" in js


def test_r3_render_carpetas_escapa_descripcion_con_escape_html():
    """R3: El render de carpetas debe pasar la descripción de cada carpeta por escapeHtml."""
    js = js_del_front()

    assert "${escapeHtml(desc)}" in js


def test_r4_omitir_paso_carpetas_no_invoca_rutas_de_carpetas():
    """R4: Omitir el paso Carpetas o avanzar con Siguiente no invoca POST ni PUT de carpetas."""
    js = js_del_front()

    # wizardSkipStep simplemente avanza el paso sin llamadas fetch
    assert "function wizardSkipStep() {\n  if (state.wizard.currentStep < WIZARD_PASOS) {\n    setWizardStep(state.wizard.currentStep + 1);\n  }\n}" in js

    # wizardNext solo hace guardado automático en el paso 1 (IA)
    assert "if (state.wizard.currentStep === 1) {" in js
    assert "if (state.wizard.currentStep === 3) {" not in js


def test_r4_guardar_carpetas_del_tutor_se_refleja_en_get_folders_y_mis_notas(client, cuenta):
    """R4: Lo guardado en el paso Carpetas se refleja exactamente en GET /api/vault/folders («Mis notas»)."""
    vault = vault_propio(cuenta)
    assert vault.is_dir()

    # Guardar selección de carpetas del tutor
    seleccion = ["04 Knowledge", "02 MOCs"]
    put_res = client.put("/api/vault/tutor-folders", json={"carpetas": seleccion})
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["del_tutor"] == seleccion

    # Comprobar que GET posterior («Mis notas») muestra la misma selección
    get_res = client.get("/api/vault/folders")
    assert get_res.status_code == 200, get_res.text
    datos = get_res.json()
    assert datos["del_tutor"] == seleccion

    # En backend, carpetas_del_vault refleja la misma selección
    with get_connection() as conn:
        info = carpetas_del_vault(conn, cuenta, vault)
        assert info["del_tutor"] == seleccion


def test_063_check_vector_status_muestra_almacen_amigable_y_motivo_escapado():
    """063 en UI (R5/R7): checkVectorStatus muestra «Índice local» o «Índice del servidor» y escapa motivo_no_disponible."""
    js = js_del_front()

    # Nombres amigables sin jerga técnica en badges o KPI
    assert "Índice local" in js
    assert "Índice del servidor" in js

    # Motivo escapado con escapeHtml cuando está apagado
    assert "escapeHtml(motivoTexto)" in js or "escapeHtml(data.motivo_no_disponible)" in js


def test_codigo_muerto_removido_de_app_js():
    """Punto 7: toggleTutorFolder y updateTutorFoldersCount fueron eliminados de app.js."""
    js = js_del_front()

    assert "function toggleTutorFolder" not in js
    assert "function updateTutorFoldersCount" not in js
