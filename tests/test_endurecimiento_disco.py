"""Pruebas de endurecimiento de disco, cuota configurable y validación de extensiones en autenticación de tokens."""

import shutil
from collections import namedtuple

import pytest
from conftest import token_mcp_de_prueba, vault_de_prueba
from fastapi import HTTPException
from fastapi.testclient import TestClient
from identidad_de_prueba import extension_de_identidad, modo_saas, sin_sesion

from aulento.core.extensiones import Extension
from aulento.core.materiales import (
    AlmacenDeMateriales,
    EspacioEnDiscoInsuficiente,
    MaterialDemasiadoGrande,
    cuota_por_cuenta,
)
from aulento.web.app import create_app

Usage = namedtuple("Usage", ["total", "used", "free"])


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Ajuste 2a: Cuota configurable por AULENTO_CUOTA_MATERIALES_MB
# ---------------------------------------------------------------------------


def test_cuota_por_defecto_es_200_mb(monkeypatch):
    monkeypatch.delenv("AULENTO_CUOTA_MATERIALES_MB", raising=False)
    assert cuota_por_cuenta() == 200 * 1024 * 1024


@pytest.mark.parametrize(
    ("valor", "esperado_mb"),
    [
        ("50", 50),
        ("25", 25),
        ("1", 1),
        (" 100 ", 100),
    ],
)
def test_cuota_desde_variable_de_entorno(monkeypatch, valor, esperado_mb):
    monkeypatch.setenv("AULENTO_CUOTA_MATERIALES_MB", valor)
    assert cuota_por_cuenta() == esperado_mb * 1024 * 1024


@pytest.mark.parametrize(
    "valor_invalido",
    [
        "0",
        "-1",
        "-200",
        "invalido",
        "",
        "   ",
        "abc",
        "50.5",
    ],
)
def test_cuota_invalida_o_no_positiva_usa_por_defecto_200_mb(monkeypatch, valor_invalido):
    monkeypatch.setenv("AULENTO_CUOTA_MATERIALES_MB", valor_invalido)
    assert cuota_por_cuenta() == 200 * 1024 * 1024


def test_almacen_uso_refleja_cuota_configurada(cuenta, monkeypatch):
    monkeypatch.setenv("AULENTO_CUOTA_MATERIALES_MB", "30")
    almacen = AlmacenDeMateriales.con_conexion_propia(cuenta)
    uso = almacen.uso()
    assert uso["tope"] == 30 * 1024 * 1024


def test_subida_respeta_cuota_configurada_menor(cuenta, monkeypatch):
    monkeypatch.setenv("AULENTO_CUOTA_MATERIALES_MB", "1")  # 1 MB
    almacen = AlmacenDeMateriales.con_conexion_propia(cuenta)

    # 600 KB entra en 1 MB
    almacen.guardar("uno.txt", b"x" * (600 * 1024))

    # Otro de 600 KB excede 1 MB (600 + 600 > 1024 KB)
    with pytest.raises(MaterialDemasiadoGrande) as exc_info:
        almacen.guardar("dos.txt", b"y" * (600 * 1024))
    assert exc_info.value.codigo == 413
    assert "1 MB" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Ajuste 2a: Freno de subida con 507 si espacio libre en disco < 2 GiB
# ---------------------------------------------------------------------------


def test_guardar_rechaza_con_507_si_espacio_libre_menor_a_2_gib(cuenta, monkeypatch):
    almacen = AlmacenDeMateriales.con_conexion_propia(cuenta)

    # Simulamos 1 GiB libre en el disco (< 2 GiB)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(100 * 1024**3, 99 * 1024**3, 1 * 1024**3))

    with pytest.raises(EspacioEnDiscoInsuficiente) as exc_info:
        almacen.guardar("apunte.txt", b"Texto de prueba")

    assert exc_info.value.codigo == 507
    assert "2 GiB" in str(exc_info.value)
    # No debe haberse guardado ningún archivo
    assert list(almacen.carpeta().iterdir()) == []


def test_guardar_rechaza_con_507_si_subida_deja_espacio_bajo_2_gib(cuenta, monkeypatch):
    almacen = AlmacenDeMateriales.con_conexion_propia(cuenta)

    # Exactamente 2 GiB libres: al guardar cualquier dato quedaría por debajo
    dos_gib = 2 * 1024 * 1024 * 1024
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(100 * 1024**3, 100 * 1024**3 - dos_gib, dos_gib))

    with pytest.raises(EspacioEnDiscoInsuficiente) as exc_info:
        almacen.guardar("apunte.txt", b"abc")

    assert exc_info.value.codigo == 507


def test_api_materiales_post_responde_507_si_disco_insuficiente(monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(100 * 1024**3, 99 * 1024**3, 500 * 1024 * 1024))

    client = TestClient(create_app())
    resp = client.post(
        "/api/materiales",
        files={"archivo": ("apunte.txt", b"Contenido de prueba", "text/plain")},
    )
    assert resp.status_code == 507
    assert "2 GiB" in resp.json()["detail"]


def test_api_materiales_post_exitosa_si_espacio_suficiente(monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(100 * 1024**3, 90 * 1024**3, 10 * 1024**3))

    client = TestClient(create_app())
    resp = client.post(
        "/api/materiales",
        files={"archivo": ("apunte.txt", b"Contenido de prueba", "text/plain")},
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Ajuste 2b: POST /api/mcp/agent/save-note con SinCuentaCompartida y content max_length 200000
# ---------------------------------------------------------------------------


def test_save_note_bloqueado_para_una_cuenta_compartida():
    compartida = Extension(nombre="cuenta_compartida_de_prueba", cuenta_compartida=lambda usuario: True)
    client = TestClient(create_app(extensiones=[compartida]))

    resp = client.post(
        "/api/mcp/agent/save-note",
        json={"title": "Nota Prohibida", "content": "Contenido", "folder": "Test"},
    )
    assert resp.status_code == 403
    assert resp.headers.get("X-Cuenta-Compartida") == "1"


def test_save_note_rechaza_content_mayor_a_200000_caracteres(client):
    payload = {
        "title": "Nota Gigante",
        "content": "a" * 200_001,
        "folder": "Test",
    }
    resp = client.post("/api/mcp/agent/save-note", json=payload)
    assert resp.status_code == 422


def test_save_note_acepta_content_hasta_200000_caracteres(client):
    vault_dir = vault_de_prueba()
    payload = {
        "title": "Nota Limite",
        "content": "b" * 200_000,
        "folder": "Test",
    }
    resp = client.post("/api/mcp/agent/save-note", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    guardado = vault_dir / "04 Knowledge" / "Cursos" / "Test" / "Nota Limite.md"
    assert guardado.exists()
    assert len(guardado.read_text(encoding="utf-8")) == 200_000


# ---------------------------------------------------------------------------
# Ajuste 4: usuario_de_sesion_o_token corre validadores_de_cuenta de extensiones
# ---------------------------------------------------------------------------


def test_webhook_con_token_rechazado_por_validador_de_cuenta_en_saas(monkeypatch):
    modo_saas(monkeypatch)
    def frena_cuenta(usuario, conn):
        raise HTTPException(status_code=403, detail="Prueba de cuenta vencida.")

    ext = Extension(nombre="control_cuentas", validadores_de_cuenta=(frena_cuenta,))
    token = token_mcp_de_prueba()
    client = TestClient(create_app(extensiones=[extension_de_identidad(sin_sesion), ext]))

    # 1. Webhook de libros con Bearer token
    payload_libro = {"titulo": "Libro de Prueba", "pagina_actual": 42}
    resp_bearer = client.post(
        "/api/books/sync/webhook",
        headers={"Authorization": f"Bearer {token}"},
        json=payload_libro,
    )
    assert resp_bearer.status_code == 403
    assert resp_bearer.json()["detail"] == "Prueba de cuenta vencida."

    # 2. Webhook de libros con encabezado X-MCP-Token
    resp_x_token = client.post(
        "/api/books/sync/webhook",
        headers={"X-MCP-Token": token},
        json=payload_libro,
    )
    assert resp_x_token.status_code == 403
    assert resp_x_token.json()["detail"] == "Prueba de cuenta vencida."

    # Webhook con ?token= en query params se rechaza con 401 (R5)
    resp_query = client.post(
        f"/api/books/sync/webhook?token={token}",
        json=payload_libro,
    )
    assert resp_query.status_code == 401

    # 3. Webhook de hub académico con Bearer token
    payload_hub = {"plataforma": "Coursera", "curso": "Cloud Architecture", "progreso_pct": 80.0}
    resp_hub = client.post(
        "/api/hub/sync/webhook",
        headers={"Authorization": f"Bearer {token}"},
        json=payload_hub,
    )
    assert resp_hub.status_code == 403
    assert resp_hub.json()["detail"] == "Prueba de cuenta vencida."


@pytest.mark.sin_sesion
def test_webhook_con_token_no_corre_validador_en_modo_local(monkeypatch):
    def frena_cuenta(usuario, conn):
        raise HTTPException(status_code=403, detail="No debe correr en local.")

    ext = Extension(nombre="control_cuentas", validadores_de_cuenta=(frena_cuenta,))
    monkeypatch.setenv("AULENTO_MODE", "local")
    client = TestClient(create_app(extensiones=[ext]))

    payload_hub = {"plataforma": "Coursera", "curso": "Cloud Architecture", "progreso_pct": 80.0}
    resp = client.post("/api/hub/sync/webhook", json=payload_hub)
    assert resp.status_code == 200
