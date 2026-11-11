"""Tests completos para la API REST y servidor web de Aulento (FastAPI)."""

import re

import pytest
from conftest import administrador_de_prueba
from fastapi.testclient import TestClient

from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.web.app import create_app


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Inicializa una base de datos temporal con plataformas y mazo FSRS."""
    db_file = tmp_path / "web_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    seed_fsrs_deck(conn, administrador_de_prueba(conn).id)
    conn.close()
    return db_file


@pytest.fixture
def client(test_db):
    """Cliente de pruebas FastAPI conectado a la base temporal."""
    app = create_app()
    return TestClient(app)


def test_root_and_health(client):
    """Verifica que el root devuelva HTML y el endpoint de salud responda OK."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "text/html" in res_root.headers["content-type"]
    assert "Aulento" in res_root.text

    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"


def test_docs_and_swagger_csp(client):
    """Verifica que /docs y /openapi.json carguen y tengan cabecera CSP compatible con Swagger UI."""
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
    assert "swagger-ui" in res_docs.text.lower()
    csp = res_docs.headers.get("content-security-policy", "")
    assert "cdn.jsdelivr.net" in csp
    assert "script-src" in csp

    res_openapi = client.get("/openapi.json")
    assert res_openapi.status_code == 200
    assert res_openapi.json()["info"]["title"] == "Aulento API & Web Dashboard"


def test_hub_platforms_and_courses(client):
    """Verifica listado de plataformas, creación de curso y actualización de progreso."""
    # Listar plataformas sembradas
    res = client.get("/api/hub/platforms")
    assert res.status_code == 200
    platforms = res.json()
    assert len(platforms) >= 5
    first_plat = platforms[0]

    # Crear curso en primera plataforma
    create_payload = {
        "plataforma_id": first_plat["id"],
        "nombre_curso": "Data Engineering Avanzado",
        "url_aula": "https://example.com/aula/de",
        "prioridad": "alta",
        "progreso_pct": 25.0,
    }
    res_create = client.post("/api/hub/courses", json=create_payload)
    assert res_create.status_code == 201
    course = res_create.json()
    assert course["id"] is not None
    assert course["nombre_curso"] == "Data Engineering Avanzado"
    assert course["progreso_pct"] == 25.0

    # Actualizar progreso
    course_id = course["id"]
    res_prog = client.post(
        f"/api/hub/courses/{course_id}/progress",
        json={"progreso_pct": 80.0},
    )
    assert res_prog.status_code == 200
    assert res_prog.json()["progreso_pct"] == 80.0

    # Completar curso
    res_complete = client.post(
        f"/api/hub/courses/{course_id}/progress",
        json={"progreso_pct": 100.0},
    )
    assert res_complete.status_code == 200
    assert res_complete.json()["estado"] == "completado"


def test_books_tracker(client):
    """Verifica registro de libro técnico y avance por capítulos y páginas."""
    payload = {
        "titulo": "Designing Data-Intensive Applications",
        "autor": "Martin Kleppmann",
        "capitulo_actual": 2,
        "total_capitulos": 12,
        "pagina_actual": 50,
        "total_paginas": 500,
    }
    res = client.post("/api/books", json=payload)
    assert res.status_code == 201
    book = res.json()
    assert book["titulo"] == "Designing Data-Intensive Applications"
    assert book["pagina_actual"] == 50
    assert book["total_paginas"] == 500
    assert book["porcentaje_leido"] == 10.0  # 50/500 * 100 = 10%

    book_id = book["id"]

    # Avanzar 1 capítulo
    res_adv = client.post(f"/api/books/{book_id}/advance")
    assert res_adv.status_code == 200
    updated = res_adv.json()
    assert updated["capitulo_actual"] == 3

    # Avanzar 20 páginas
    res_pages = client.post(f"/api/books/{book_id}/advance-pages?pages=20")
    assert res_pages.status_code == 200
    updated_pages = res_pages.json()
    assert updated_pages["pagina_actual"] == 70
    assert updated_pages["porcentaje_leido"] == 14.0  # 70/500 * 100 = 14%

    # Actualizar progreso por PATCH
    res_patch = client.patch(f"/api/books/{book_id}/progress", json={"pagina_actual": 100})
    assert res_patch.status_code == 200
    assert res_patch.json()["pagina_actual"] == 100
    assert res_patch.json()["porcentaje_leido"] == 20.0

    # Listar libros
    res_list = client.get("/api/books")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1


def test_schedule_endpoints(client):
    """Verifica listado, creación y borrado de bloques de estudio."""
    payload = {
        "dia_semana": 1,
        "hora_inicio": "10:30",
        "hora_fin": "12:30",
        "tipo": "curso",
        "descripcion": "Estudio Digital House ML",
    }
    res = client.post("/api/schedule", json=payload)
    assert res.status_code == 201
    block = res.json()
    block_id = block["id"]

    # Listar agenda
    res_list = client.get("/api/schedule")
    assert res_list.status_code == 200
    assert any(b["id"] == block_id for b in res_list.json())

    # Filtrar por día
    res_dia = client.get("/api/schedule?dia_semana=1")
    assert res_dia.status_code == 200
    assert len(res_dia.json()) >= 1

    # Actualizar bloque (PATCH)
    res_patch = client.patch(f"/api/schedule/{block_id}", json={"descripcion": "Estudio Digital House ML Avanzado", "hora_fin": "13:00"})
    assert res_patch.status_code == 200
    assert res_patch.json()["descripcion"] == "Estudio Digital House ML Avanzado"
    assert res_patch.json()["hora_fin"] == "13:00"

    # Borrar bloque
    res_del = client.delete(f"/api/schedule/{block_id}")
    assert res_del.status_code == 204


def test_fsrs_endpoints(client):
    """Verifica estado cognitivo, obtención de tarjetas vencidas y ciclo de calificación FSRS."""
    # Estado inicial
    res_status = client.get("/api/fsrs/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["tarjetas_totales"] >= 100
    assert data["vencidas_hoy"] >= 1

    # Obtener tarjetas pendientes
    res_due = client.get("/api/fsrs/due?limit=5")
    assert res_due.status_code == 200
    due_cards = res_due.json()
    assert len(due_cards) > 0
    first_card = due_cards[0]

    # Calificar tarjeta con GOOD (3)
    review_payload = {
        "card_id": first_card["id"],
        "rating": 3,
    }
    res_rev = client.post("/api/fsrs/review", json=review_payload)
    assert res_rev.status_code == 200
    rev_data = res_rev.json()
    assert rev_data["card_id"] == first_card["id"]
    assert rev_data["rating_name"] == "GOOD"
    assert rev_data["estabilidad_nueva"] is not None and rev_data["estabilidad_nueva"] > 0
    # Obtener tarjetas pendientes con force=true para práctica extra
    res_extra = client.get("/api/fsrs/due?limit=5&force=true")
    assert res_extra.status_code == 200
    assert len(res_extra.json()) > 0


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("get", "/api/mcp/status"),
        ("get", "/api/mcp/config"),
        ("post", "/api/mcp/config"),
        ("post", "/api/mcp/toggle"),
        ("get", "/api/mcp/search?query=Machine"),
        ("get", "/api/mcp/material/1AbC_dEfGhIjKlMnOpQ"),
        ("post", "/api/mcp/gdrive/authorize"),
        ("get", "/api/mcp/gdrive/oauth-callback"),
        ("delete", "/api/mcp/gdrive/client"),
        ("post", "/api/mcp/gdrive/verify"),
        ("post", "/api/mcp/onedrive/authorize"),
        ("get", "/api/mcp/onedrive/oauth-callback"),
        ("delete", "/api/mcp/onedrive/client"),
    ],
)
def test_las_rutas_de_drive_y_onedrive_ya_no_existen(client, metodo, ruta):
    """048, R12: Drive y OneDrive se retiraron; el tutor y los tokens MCP siguen en /api/mcp."""
    assert getattr(client, metodo)(ruta).status_code in (404, 405)
    assert client.get("/api/mcp/tokens").status_code == 200


def test_platforms_and_courses_crud(client):
    """Verifica actualización y eliminación de plataformas y cursos."""
    # 1. Crear plataforma
    p_res = client.post("/api/hub/platforms", json={
        "nombre": "Test Platform Inc",
        "url_acceso": "https://testplatform.com",
        "icono_color": "purple",
    })
    assert p_res.status_code == 201
    p_id = p_res.json()["id"]

    # 2. Actualizar plataforma
    p_upd = client.put(f"/api/hub/platforms/{p_id}", json={
        "nombre": "Updated Platform Inc",
        "url_acceso": "https://updatedplatform.com",
        "icono_color": "indigo",
    })
    assert p_upd.status_code == 200
    assert p_upd.json()["nombre"] == "Updated Platform Inc"
    assert p_upd.json()["icono_color"] == "indigo"

    # 3. Crear curso en la plataforma
    c_res = client.post("/api/hub/courses", json={
        "plataforma_id": p_id,
        "nombre_curso": "Test Course",
        "url_aula": "https://testplatform.com/class",
        "prioridad": "alta",
        "progreso_pct": 10.0,
    })
    assert c_res.status_code == 201
    c_id = c_res.json()["id"]

    # 4. Actualizar curso
    c_upd = client.put(f"/api/hub/courses/{c_id}", json={
        "nombre_curso": "Renamed Course",
        "progreso_pct": 50.0,
        "prioridad": "media",
    })
    assert c_upd.status_code == 200
    assert c_upd.json()["nombre_curso"] == "Renamed Course"
    assert c_upd.json()["progreso_pct"] == 50.0

    # 5. Eliminar curso
    del_c = client.delete(f"/api/hub/courses/{c_id}")
    assert del_c.status_code == 200
    assert del_c.json()["ok"] is True

    # 6. Eliminar plataforma
    del_p = client.delete(f"/api/hub/platforms/{p_id}")
    assert del_p.status_code == 200
    assert del_p.json()["ok"] is True


def test_books_crud_update_delete(client):
    """Verifica actualización completa y eliminación de libros técnicos."""
    # 1. Crear libro
    b_res = client.post("/api/books", json={
        "titulo": "Book to Edit and Delete",
        "capitulo_actual": 1,
        "total_capitulos": 8,
        "pagina_actual": 15,
        "total_paginas": 200,
    })
    assert b_res.status_code == 201
    b_id = b_res.json()["id"]

    # 2. Actualizar libro completo (PUT)
    b_upd = client.put(f"/api/books/{b_id}", json={
        "titulo": "Updated Book Title",
        "total_paginas": 300,
        "pagina_actual": 60,
        "total_capitulos": 10,
        "capitulo_actual": 2,
    })
    assert b_upd.status_code == 200
    assert b_upd.json()["titulo"] == "Updated Book Title"
    assert b_upd.json()["total_paginas"] == 300
    assert b_upd.json()["porcentaje_leido"] == 20.0  # 60/300

    # 3. Eliminar libro
    del_b = client.delete(f"/api/books/{b_id}")
    assert del_b.status_code == 200
    assert del_b.json()["ok"] is True

    # 4. Verificar que no exista
    del_again = client.delete(f"/api/books/{b_id}")
    assert del_again.status_code == 404


def test_courses_hub_360_resources_and_notes(client, tmp_path):
    """Verifica el flujo completo de recursos (Drive, Local, Notion, Obsidian) en cursos externos."""
    # 1. Crear plataforma
    p_res = client.post("/api/hub/platforms", json={
        "nombre": "Coursera 360",
        "url_acceso": "https://coursera.org",
        "icono_color": "cyan",
    })
    assert p_res.status_code == 201
    p_id = p_res.json()["id"]

    # 2. Crear curso con recursos y notas
    c_payload = {
        "plataforma_id": p_id,
        "nombre_curso": "Data Engineering Specialized",
        "url_aula": "https://coursera.org/learn/data-engineering",
        "progreso_pct": 25.0,
        "prioridad": "alta",
        "url_drive": "https://drive.google.com/drive/folders/test12345",
        "ruta_local": str(tmp_path),
        "url_notion": "https://notion.so/my-data-engineering-page",
        "ruta_obsidian": "04 Knowledge/Cursos/Data Engineering.md",
    }
    c_res = client.post("/api/hub/courses", json=c_payload)
    assert c_res.status_code == 201
    c_data = c_res.json()
    assert c_data["url_drive"] == "https://drive.google.com/drive/folders/test12345"
    assert c_data["ruta_local"] == str(tmp_path)
    assert c_data["url_notion"] == "https://notion.so/my-data-engineering-page"
    assert c_data["ruta_obsidian"] == "04 Knowledge/Cursos/Data Engineering.md"
    c_id = c_data["id"]

    # 3. Listar plataformas y verificar que los campos persisten en el anidado
    p_list = client.get("/api/hub/platforms")
    assert p_list.status_code == 200
    matched = next((p for p in p_list.json() if p["id"] == p_id), None)
    assert matched is not None
    assert len(matched["cursos"]) == 1
    assert matched["cursos"][0]["url_drive"] == "https://drive.google.com/drive/folders/test12345"
    assert matched["cursos"][0]["url_notion"] == "https://notion.so/my-data-engineering-page"

    # 4. Probar endpoint open-local para ruta existente (solo un administrador en la misma máquina)
    local = TestClient(client.app, client=("127.0.0.1", 50000))
    open_res = local.post(f"/api/hub/courses/{c_id}/open-local")
    assert open_res.status_code == 200
    assert open_res.json()["ok"] is True

    # 5. Probar endpoint open-local para ruta inexistente
    client.put(f"/api/hub/courses/{c_id}", json={"ruta_local": "/non/existent/path/xyz_123"})
    open_bad = local.post(f"/api/hub/courses/{c_id}/open-local")
    assert open_bad.status_code == 404

    # 6. Actualizar campos de recursos
    upd_res = client.put(f"/api/hub/courses/{c_id}", json={
        "url_drive": "https://drive.google.com/drive/folders/updated_folder",
        "url_notion": None,
        "ruta_obsidian": "obsidian://open?vault=Vault&file=NewNote",
    })
    assert upd_res.status_code == 200
    updated = upd_res.json()
    assert updated["url_drive"] == "https://drive.google.com/drive/folders/updated_folder"
    assert updated["url_notion"] is None
    assert updated["ruta_obsidian"] == "obsidian://open?vault=Vault&file=NewNote"

    # 7. Limpieza
    del_res = client.delete(f"/api/hub/platforms/{p_id}")
    assert del_res.status_code == 200



def test_user_manual_endpoints(client):
    """Verifica que los endpoints del manual de usuario y documentación respondan adecuadamente."""
    # API JSON del manual
    res_api = client.get("/api/docs/manual")
    assert res_api.status_code == 200
    data = res_api.json()
    assert "Manual de Usuario" in data["title"]
    assert len(data["content"]) > 100
    assert "Aulento" in data["content"]

    # Vista standalone del manual
    res_page = client.get("/manual")
    assert res_page.status_code == 200
    assert "text/html" in res_page.headers["content-type"]
    assert "Manual de Usuario" in res_page.text
    assert "marked.parse" in res_page.text


def test_la_vista_del_manual_tiene_estilos_validos_y_sanea_el_markdown(client):
    pagina = client.get("/manual").text

    assert "body { background" in pagina and "{{" not in pagina
    # Los recursos que carga existen en la app
    for recurso in re.findall(r'src="(/static/[^"]+)"', pagina):
        assert client.get(recurso).status_code == 200, recurso
    assert "DOMPurify.sanitize(marked.parse(raw))" in pagina
    # El manual viaja dentro de un <script>: ningún "</" del texto puede cerrarlo antes de tiempo
    datos = pagina.split("const raw = ")[1].split(";\n")[0]
    assert "</" not in datos
