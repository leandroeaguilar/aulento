"""Pruebas E2E con Playwright: Experiencia en Modo Local (R9)."""

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture(autouse=True)
def modo_saas_por_defecto(monkeypatch):
    """Reemplaza al fixture de la suite: el servidor vive en este proceso y lee el modo en cada pedido."""
    monkeypatch.setenv("AULENTO_MODE", "local")


def test_local_experience_sin_login(page: Page, live_local_server: str):
    """En modo Local, el usuario abre la aplicación y entra directo al dashboard sin login."""
    # 1. Navegar a la raíz
    page.goto(live_local_server)

    # 2. No debe haber redirigido a /login
    assert "/login" not in page.url

    # 3. El título de la página debe ser el de Aulento (con guion o raya em-dash)
    expect(page).to_have_title(re.compile(r"Aulento.*Sistema Maestro de Estudio"))

    # 5. La navegación entre secciones funciona y el usuario identificado es local_user
    expect(page.locator("body")).to_be_visible()
    expect(page.locator("body")).to_contain_text("local_user")

    # 6. Comprobar que el depurador y diagnóstico local se abre desde la interfaz
    page.evaluate("openDiagnosticsModal()")
    diag_modal = page.locator("#modal-diagnostics")
    expect(diag_modal).to_be_visible()
    expect(page.locator("#diag-modo")).to_contain_text("LOCAL")
