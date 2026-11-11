"""Pruebas de la Feature 041: Sincronización de libros con Google Play Libros y Apple Libros."""
from conftest import administrador_de_prueba, cuenta_de_prueba

from aulento.db.repository import LibroRepository
from aulento.models.libro import LibroCreate, LibroUpdate


def test_modelo_libro_campos_sincronizacion():
    l_create = LibroCreate(
        titulo="Designing Data-Intensive Applications",
        total_paginas=600,
        google_books_id="g123xyz",
        fuente_sincronizacion="google_books",
    )
    assert l_create.google_books_id == "g123xyz"
    assert l_create.fuente_sincronizacion == "google_books"
    assert l_create.ultima_sincronizacion is None
    assert l_create.total_capitulos == 1

    l_up = LibroUpdate(
        pagina_actual=50,
        google_books_id="g456abc",
        fuente_sincronizacion="apple_books",
    )
    assert l_up.google_books_id == "g456abc"
    assert l_up.fuente_sincronizacion == "apple_books"


def test_repositorio_libro_creacion_y_busqueda_google_books(memory_db):
    user_id = cuenta_de_prueba(memory_db).id
    repo = LibroRepository(memory_db, user_id=user_id)

    libro = repo.create(
        LibroCreate(
            titulo="Refactoring",
            total_paginas=400,
            google_books_id="refactor_volume_1",
            fuente_sincronizacion="google_books",
        )
    )
    assert libro.id is not None
    assert libro.google_books_id == "refactor_volume_1"
    assert libro.fuente_sincronizacion == "google_books"

    # Buscar por Google Books ID
    encontrado = repo.find_by_google_books_id("refactor_volume_1")
    assert encontrado is not None
    assert encontrado.id == libro.id
    assert encontrado.titulo == "Refactoring"

    # Buscar inexistente
    assert repo.find_by_google_books_id("inexistente") is None
    assert repo.find_by_google_books_id("") is None

    # Aislamiento por usuario
    repo_otro_user = LibroRepository(memory_db, user_id=user_id + 999)
    assert repo_otro_user.find_by_google_books_id("refactor_volume_1") is None


def test_repositorio_libro_vincular_google_books(memory_db):
    user_id = cuenta_de_prueba(memory_db).id
    repo = LibroRepository(memory_db, user_id=user_id)

    libro = repo.create(
        LibroCreate(
            titulo="Domain-Driven Design",
            total_paginas=500,
        )
    )
    assert libro.google_books_id is None
    assert libro.fuente_sincronizacion == "manual"

    vinculado = repo.vincular_google_books(libro.id, "ddd_volume_99")
    assert vinculado is not None
    assert vinculado.google_books_id == "ddd_volume_99"
    assert vinculado.fuente_sincronizacion == "google_books"

    # Actualizar progreso con fuente y timestamp
    actualizado = repo.update_progress(
        libro.id,
        pagina_actual=150,
        fuente_sincronizacion="google_books",
        ultima_sincronizacion="2026-10-21T12:00:00Z",
    )
    assert actualizado is not None
    assert actualizado.pagina_actual == 150
    assert actualizado.fuente_sincronizacion == "google_books"
    assert actualizado.ultima_sincronizacion == "2026-10-21T12:00:00Z"


import json
from unittest.mock import MagicMock

import httpx
import pytest

from aulento.connectors.google_books import (
    SECRETO_GOOGLE_BOOKS_CLIENTE,
    FaltaClienteGoogleBooks,
    GoogleBooksConnector,
)
from aulento.core.secretos import AlmacenDeSecretos


def test_google_books_connector_sin_cliente(memory_db):
    user_id = cuenta_de_prueba(memory_db).id
    connector = GoogleBooksConnector(memory_db, user_id=user_id)
    assert not connector.esta_autorizado()
    assert connector.obtener_cliente_oauth() is None

    with pytest.raises(FaltaClienteGoogleBooks):
        connector.generar_url_autorizacion("http://localhost/callback", "state123")


def test_google_books_connector_flujo_oauth_y_sync(memory_db, monkeypatch):
    user_id = cuenta_de_prueba(memory_db).id
    secretos = AlmacenDeSecretos(memory_db, user_id)
    secretos.guardar(
        SECRETO_GOOGLE_BOOKS_CLIENTE,
        json.dumps({"client_id": "google_test_client_id", "client_secret": "google_test_secret"}),
    )

    connector = GoogleBooksConnector(memory_db, user_id=user_id)
    url = connector.generar_url_autorizacion("http://localhost/callback", "state123")
    assert "google_test_client_id" in url
    assert "state123" in url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fbooks" in url

    # Mock token exchange
    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "mock_access_token_123",
            "refresh_token": "mock_refresh_token_456",
            "expires_in": 3600,
        }
        return resp

    monkeypatch.setattr(httpx, "post", mock_post)
    tokens = connector.canjear_codigo("test_code", "http://localhost/callback")
    assert tokens["access_token"] == "mock_access_token_123"
    assert connector.esta_autorizado()

    # Mock shelf and position requests
    shelf_reading = {
        "items": [
            {
                "id": "vol_clean_code",
                "volumeInfo": {
                    "title": "Clean Code",
                    "pageCount": 450,
                },
            }
        ]
    }
    shelf_read = {
        "items": [
            {
                "id": "vol_pragmatic",
                "volumeInfo": {
                    "title": "The Pragmatic Programmer",
                    "pageCount": 350,
                },
            }
        ]
    }

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "bookshelves/3/volumes" in url:
            resp.json.return_value = shelf_reading
        elif "bookshelves/4/volumes" in url:
            resp.json.return_value = shelf_read
        elif "readingpositions/vol_clean_code" in url:
            resp.json.return_value = {
                "kind": "books#readingPosition",
                "volumeId": "vol_clean_code",
                "percentage": 0.5,
            }
        else:
            resp.status_code = 404
        return resp

    monkeypatch.setattr(httpx, "get", mock_get)

    resultado = connector.sincronizar()
    assert resultado["sincronizados"] >= 1
    assert resultado["creados"] >= 1

    # Verificar que el libro fue creado e importado
    libro = connector.libro_repo.find_by_google_books_id("vol_clean_code")
    assert libro is not None
    assert libro.titulo == "Clean Code"
    assert libro.pagina_actual == 225  # 50% de 450
    assert libro.fuente_sincronizacion == "google_books"

    # Segunda sincronización actualiza sin duplicar
    resultado2 = connector.sincronizar()
    assert resultado2["creados"] == 0
    assert resultado2["actualizados"] >= 1

    # Desconectar
    assert connector.desconectar() is True
    assert not connector.esta_autorizado()


# ----------------------------------------------------------------------
# Fixtures para pruebas de API Web
@pytest.fixture
def test_db(tmp_path, monkeypatch):
    from aulento.db.schema import init_db
    db_file = tmp_path / "books_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    administrador_de_prueba(conn)
    conn.close()
    return db_file


@pytest.fixture
def client(test_db):
    app = create_app()
    return TestClient(app)


# Tests de Webhook para Apple Libros y Atajos (T3)
# ----------------------------------------------------------------------

from fastapi.testclient import TestClient
from identidad_de_prueba import extension_de_identidad, modo_saas, sin_sesion

from aulento.auth import servicio as auth_servicio
from aulento.db.connection import get_connection
from aulento.web.app import create_app


def test_webhook_info_endpoint(client):
    res = client.get("/api/books/sync/webhook-info")
    assert res.status_code == 200
    datos = res.json()
    assert "/api/books/sync/webhook" in datos["webhook_url"]
    assert datos["metodo"] == "POST"
    assert "apple_books" in datos["ejemplo_payload"]["fuente"]


def test_webhook_sin_autenticacion_rechaza_401(test_db, monkeypatch):
    modo_saas(monkeypatch)
    cliente = TestClient(create_app(extensiones=[extension_de_identidad(sin_sesion)]))
    res = cliente.post("/api/books/sync/webhook", json={"titulo": "Libro de prueba", "pagina_actual": 10})
    assert res.status_code == 401
    assert "Se requiere sesión activa o token válido" in res.json()["detail"]


@pytest.mark.sin_sesion
def test_webhook_con_token_bearer_mcp(test_db):
    conn = get_connection(test_db)
    user = cuenta_de_prueba(conn, "usuario_shortcut")
    token_obj = auth_servicio.crear_token_mcp(conn, user.id, "Token Atajo")
    token = token_obj.token
    conn.close()

    cliente = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Crear libro nuevo via webhook
    payload = {
        "titulo": "Clean Code en Español",
        "pagina_actual": 42,
        "total_paginas": 400,
        "fuente": "apple_books",
    }
    res = cliente.post("/api/books/sync/webhook", json=payload, headers=headers)
    assert res.status_code == 200
    datos = res.json()
    assert datos["status"] == "ok"
    assert datos["accion"] == "creado"
    assert datos["pagina_actual"] == 42
    assert datos["titulo"] == "Clean Code en Español"
    assert datos["fuente"] == "apple_books"

    # 2. Actualizar progreso con porcentaje via encabezado X-MCP-Token (R5)
    payload_pct = {
        "titulo": "Clean Code en Español",
        "porcentaje": 25.0,  # 25% de 400 = 100
        "fuente": "apple_books",
    }
    res_pct = cliente.post("/api/books/sync/webhook", json=payload_pct, headers={"X-MCP-Token": token})
    assert res_pct.status_code == 200
    datos_pct = res_pct.json()
    assert datos_pct["accion"] == "actualizado"
    assert datos_pct["pagina_actual"] == 100

    # 3. Intentar enviar token en la URL (?token=) debe ser rechazado con 401 (R5)
    res_err = cliente.post(f"/api/books/sync/webhook?token={token}", json=payload_pct)
    assert res_err.status_code == 401
    assert "no se acepta en la URL" in res_err.json()["detail"]


def test_webhook_con_sesion_activa(client, test_db):
    payload = {
        "titulo": "Site Reliability Engineering",
        "pagina_actual": 50,
        "total_paginas": 500,
        "fuente": "apple_books",
    }
    res = client.post("/api/books/sync/webhook", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["pagina_actual"] == 50


# ----------------------------------------------------------------------
# Tests de Endpoints REST de Google Books (T4)
# ----------------------------------------------------------------------


def test_google_books_endpoints_estado_y_flujo(client, test_db, monkeypatch):
    # 1. Estado inicial
    res_st = client.get("/api/books/google/status")
    assert res_st.status_code == 200
    assert res_st.json()["conectado"] is False

    # 2. Sin cliente, authorize falla con 400
    res_no_client = client.post("/api/books/google/authorize")
    assert res_no_client.status_code == 400

    # 3. Guardar cliente en secretos de la cuenta de prueba
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    secretos = AlmacenDeSecretos(conn, user_id)
    secretos.guardar(
        SECRETO_GOOGLE_BOOKS_CLIENTE,
        json.dumps({"client_id": "google_web_client_id", "client_secret": "google_web_secret"}),
    )
    conn.close()

    # 4. Iniciar autorización
    res_auth = client.post("/api/books/google/authorize")
    assert res_auth.status_code == 200
    datos_auth = res_auth.json()
    assert "google_web_client_id" in datos_auth["auth_url"]
    state = datos_auth["state"]

    # 5. Callback de Google OAuth con error
    res_cb_err = client.get("/api/books/google/oauth-callback", params={"error": "access_denied"})
    assert res_cb_err.status_code == 400
    assert "denegó la autorización" in res_cb_err.text

    # 6. Callback de Google OAuth exitoso
    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "mock_google_books_token",
            "refresh_token": "mock_google_books_refresh",
            "expires_in": 3600,
        }
        return resp

    monkeypatch.setattr(httpx, "post", mock_post)

    res_cb_ok = client.get("/api/books/google/oauth-callback", params={"code": "auth_code_123", "state": state})
    assert res_cb_ok.status_code == 200
    assert "Google Play Libros Conectado" in res_cb_ok.text

    # 7. Estado ahora es conectado
    res_st_ok = client.get("/api/books/google/status")
    assert res_st_ok.status_code == 200
    assert res_st_ok.json()["conectado"] is True

    # 8. Sincronización
    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"items": []}
        return resp

    monkeypatch.setattr(httpx, "get", mock_get)

    res_sync = client.post("/api/books/google/sync")
    assert res_sync.status_code == 200
    assert res_sync.json()["status"] == "ok"

    # 9. Desconectar
    res_disc = client.delete("/api/books/google/authorize")
    assert res_disc.status_code == 200
    assert res_disc.json()["status"] == "desconectado"

    # 10. Estado vuelve a desconectado
    res_st_after = client.get("/api/books/google/status")
    assert res_st_after.json()["conectado"] is False
