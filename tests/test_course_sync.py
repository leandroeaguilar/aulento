"""Tests para el subsistema de sincronización automática de cursos (Feature 043)."""


import pytest

from aulento.db.connection import get_connection
from aulento.db.repository import CursoRepository, PlataformaRepository
from aulento.db.schema import create_schema, seed_plataformas
from aulento.models.curso import (
    CursoCreate,
    EstadoCurso,
    PrioridadCurso,
)


@pytest.fixture
def db_conn():
    conn = get_connection(":memory:")
    create_schema(conn)
    conn.execute("INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, creado_en) VALUES (1, 'ana', 'hash', '2026-01-01');")
    conn.commit()
    seed_plataformas(conn, 1)
    yield conn
    conn.close()


def test_migracion_6_columnas_en_cursos_externos(db_conn):
    """Verifica que la migración 6 haya agregado las columnas de sincronización a cursos_externos."""
    cursor = db_conn.execute("PRAGMA table_info(cursos_externos);")
    columnas = {row["name"] for row in cursor.fetchall()}
    assert "external_id" in columnas
    assert "fuente_sincronizacion" in columnas
    assert "ultima_sincronizacion" in columnas
    assert "sync_config_json" in columnas


def test_curso_repo_create_with_sync_fields(db_conn):
    """Verifica la creación y recuperación de un curso con campos de sincronización."""
    repo = CursoRepository(db_conn, user_id=1)
    p_repo = PlataformaRepository(db_conn, user_id=1)
    plataformas = p_repo.list_all()
    assert len(plataformas) > 0
    plat = plataformas[0]

    curso = repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="GCP Professional Cloud Architect",
            url_aula="https://www.cloudskillsboost.google/quests/123",
            progreso_pct=25.0,
            estado=EstadoCurso.EN_CURSO,
            prioridad=PrioridadCurso.ALTA,
            external_id="quest-gcp-pca-123",
            fuente_sincronizacion="google_cloud_skills",
            sync_config_json='{"badge_id": "badge-123"}',
        )
    )
    assert curso.id > 0
    assert curso.external_id == "quest-gcp-pca-123"
    assert curso.fuente_sincronizacion == "google_cloud_skills"
    assert curso.sync_config_json == '{"badge_id": "badge-123"}'

    # Búsqueda por external_id
    encontrado = repo.find_by_external_id("quest-gcp-pca-123")
    assert encontrado is not None
    assert encontrado.id == curso.id

    # Búsqueda por nombre
    por_nombre = repo.find_by_name("GCP Professional Cloud Architect")
    assert por_nombre is not None
    assert por_nombre.id == curso.id


def test_curso_repo_update_sync_progress(db_conn):
    """Verifica la actualización de progreso por sincronización."""
    repo = CursoRepository(db_conn, user_id=1)
    p_repo = PlataformaRepository(db_conn, user_id=1)
    plat = p_repo.list_all()[0]

    curso = repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Deep Learning Specialization",
            url_aula="https://www.coursera.org/specializations/deep-learning",
            progreso_pct=10.0,
            estado=EstadoCurso.EN_CURSO,
        )
    )

    actualizado = repo.update_sync_progress(
        id=curso.id,
        nuevo_progreso=100.0,
        nuevo_estado=EstadoCurso.COMPLETADO,
        fuente="coursera",
        external_id="coursera-deep-learning-1",
        sync_config_json='{"cert_id": "CERT-99"}',
    )
    assert actualizado is not None
    assert actualizado.progreso_pct == 100.0
    assert actualizado.estado == EstadoCurso.COMPLETADO
    assert actualizado.fuente_sincronizacion == "coursera"
    assert actualizado.ultima_sincronizacion is not None
    assert actualizado.external_id == "coursera-deep-learning-1"

    status = repo.get_sync_status()
    assert status["total_cursos"] >= 1
    assert status["cursos_sincronizados"] >= 1
    assert status["ultima_sincronizacion"] is not None


from aulento.connectors.course_sync import (
    CourseraConnector,
    CourseSyncManager,
    DigitalHouseConnector,
    GoogleCloudSkillsConnector,
    HumaiConnector,
)

HTML_SAMPLE_SKILLS_BOOST = """
<html>
<body>
  <div class="ql-title-large">User Public Profile</div>
  <div class="profile-badge">
    <span class="ql-title-medium l-mbl">Baseline: Data, ML, AI</span>
    <span>Earned Sep 15, 2026</span>
  </div>
  <div class="profile-badge">
    <span class="badge-title">Google Cloud Computing Foundations: Cloud Basics</span>
    <span>Completed Oct 10, 2026</span>
  </div>
</body>
</html>
"""


def test_google_cloud_skills_connector_parser():
    badges = GoogleCloudSkillsConnector.parse_profile_badges(HTML_SAMPLE_SKILLS_BOOST)
    assert len(badges) >= 2
    titulos = [b["titulo"] for b in badges]
    assert "Baseline: Data, ML, AI" in titulos
    assert "Google Cloud Computing Foundations: Cloud Basics" in titulos


def test_coursera_connector_parse_progress():
    pct, st = CourseraConnector.parse_progress({"completed_modules": 3, "total_modules": 4})
    assert pct == 75.0
    assert st == "en_curso"

    pct2, st2 = CourseraConnector.parse_progress({"progreso_pct": 100.0})
    assert pct2 == 100.0
    assert st2 == "completado"


def test_humai_and_digital_house_connectors():
    pct_h, st_h = HumaiConnector.parse_progress({"modulos_completados": 6, "total_modulos": 8})
    assert pct_h == 75.0
    assert st_h == "en_curso"

    pct_dh, st_dh = DigitalHouseConnector.parse_progress({"checkpoints_aprobados": 5, "total_checkpoints": 5})
    assert pct_dh == 100.0
    assert st_dh == "completado"


def test_sync_manager_sync_course_google_skills(db_conn):
    p_repo = PlataformaRepository(db_conn, user_id=1)
    plat = next(p for p in p_repo.list_all() if "google" in p.nombre.lower() or "skills" in p.nombre.lower())

    c_repo = CursoRepository(db_conn, user_id=1)
    curso = c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Baseline: Data, ML, AI",
            url_aula="https://www.cloudskillsboost.google/quests/11",
            progreso_pct=20.0,
            estado=EstadoCurso.EN_CURSO,
        )
    )

    manager = CourseSyncManager(db_conn, user_id=1)
    res = manager.sync_course(
        curso.id,
        payload={"profile_html": HTML_SAMPLE_SKILLS_BOOST, "profile_id": "test-user-123"},
    )

    assert res.success is True
    assert res.progreso_pct == 100.0
    assert res.estado == "completado"
    assert "Insignia completada detectada" in res.mensaje

    # Verificar que se actualizó en base de datos
    actualizado = c_repo.get_by_id(curso.id)
    assert actualizado.progreso_pct == 100.0
    assert actualizado.estado == EstadoCurso.COMPLETADO
    assert actualizado.fuente_sincronizacion == "google_cloud_skills"
    assert actualizado.ultima_sincronizacion is not None


def test_sync_manager_process_webhook(db_conn):
    p_repo = PlataformaRepository(db_conn, user_id=1)
    plat = p_repo.list_all()[0]

    c_repo = CursoRepository(db_conn, user_id=1)
    curso = c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Curso Webhook Test",
            url_aula="https://example.com/aula",
            progreso_pct=0.0,
            estado=EstadoCurso.EN_CURSO,
        )
    )

    manager = CourseSyncManager(db_conn, user_id=1)
    res = manager.process_webhook({
        "course_id": curso.id,
        "progreso_pct": 88.5,
        "fuente": "tampermonkey_script",
    })

    assert res.success is True
    assert res.progreso_pct == 88.5
    assert res.fuente == "tampermonkey_script"

    actualizado = c_repo.get_by_id(curso.id)
    assert actualizado.progreso_pct == 88.5
    assert actualizado.fuente_sincronizacion == "tampermonkey_script"


def test_sync_manager_profile_sync_auto_import(db_conn):
    manager = CourseSyncManager(db_conn, user_id=1)
    res_list = manager.sync_google_skills_profile(
        profile_url_or_id="user-uuid-123",
        profile_html=HTML_SAMPLE_SKILLS_BOOST,
        auto_import=True,
    )
    assert len(res_list) > 0
    # Al menos una insignia auto-importada
    c_repo = CursoRepository(db_conn, user_id=1)
    cursos = c_repo.list_all()
    titulos = [c.nombre_curso for c in cursos]
    assert any("Google Cloud Computing Foundations" in t for t in titulos)


from conftest import administrador_de_prueba
from fastapi.testclient import TestClient

from aulento.web.app import create_app


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_api.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    create_schema(conn)
    admin = administrador_de_prueba(conn)
    seed_plataformas(conn, admin.id)
    # Crear token MCP
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mcp_tokens (usuario_id, token_hash, nombre, creado_en) VALUES (?, ?, ?, ?);",
        (admin.id, "test_token_hash_123", "test_token", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    app = create_app()
    client = TestClient(app)
    client.cookies.set("session_token", "token_de_prueba")
    return client, db_file, admin.id


def test_endpoint_sync_course(api_client):
    client, db_file, user_id = api_client
    conn = get_connection(db_file)
    p_repo = PlataformaRepository(conn, user_id)
    c_repo = CursoRepository(conn, user_id)
    plat = p_repo.list_all()[0]
    curso = c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Deep Learning Coursera",
            url_aula="https://coursera.org/learn/dl",
            progreso_pct=10.0,
            estado=EstadoCurso.EN_CURSO,
        )
    )
    conn.close()

    resp = client.post(
        f"/api/hub/courses/{curso.id}/sync",
        json={"completed_modules": 4, "total_modules": 4, "progreso_pct": 100.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["progreso_pct"] == 100.0
    assert data["estado"] == "completado"


def test_endpoint_webhook_course_sync_authenticated(api_client):
    client, _db_file, _user_id = api_client
    # Test via session cookie
    resp = client.post(
        "/api/hub/sync/webhook",
        json={
            "curso": "Curso Nuevo Webhook",
            "plataforma": "Digital House",
            "progreso_pct": 60.0,
            "fuente": "tampermonkey",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["nombre_curso"] == "Curso Nuevo Webhook"
    assert data["progreso_pct"] == 60.0


def test_endpoint_webhook_info(api_client):
    client, _, _ = api_client
    resp = client.get("/api/hub/sync/webhook-info")
    assert resp.status_code == 200
    data = resp.json()
    assert "webhook_url" in data
    assert "/api/hub/sync/webhook" in data["webhook_url"]
    assert "instrucciones" in data


def test_endpoint_sync_status(api_client):
    client, _, _ = api_client
    resp = client.get("/api/hub/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_cursos" in data
    assert "cursos_sincronizados" in data


from typer.testing import CliRunner

from aulento.cli.app import cli
from aulento.mcp.security import fijar_cuenta_mcp, restablecer_cuenta_mcp
from aulento.mcp.server import create_study_mcp_server


def test_cli_hub_sync_commands(api_client):
    _, _db_file, _ = api_client
    runner = CliRunner()
    # 1. sync-status
    res = runner.invoke(cli, ["hub", "sync-status"])
    assert res.exit_code == 0
    assert "Estado de Sincronización" in res.output

    # 2. webhook-info
    res2 = runner.invoke(cli, ["hub", "webhook-info"])
    assert res2.exit_code == 0
    assert "Webhook Universal" in res2.output


def test_mcp_course_sync_tools(api_client):
    import anyio
    _, db_file, _ = api_client
    conn = get_connection(db_file)
    admin = administrador_de_prueba(conn)
    plat = PlataformaRepository(conn, admin.id).list_all()[0]
    c_repo = CursoRepository(conn, admin.id)
    curso = c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="GCP MCP Sync Test",
            url_aula="https://cloudskillsboost.google/course-test",
            progreso_pct=10.0,
            estado=EstadoCurso.EN_CURSO,
        )
    )
    conn.close()

    server = create_study_mcp_server(db_path=db_file)

    async def _run_mcp():
        token = fijar_cuenta_mcp(admin.id)
        try:
            # 1. study_get_course_sync_status
            status_out = await server.call_tool("study_get_course_sync_status", {})
            assert "Estado de Sincronización" in status_out.content[0].text

            # 2. study_sync_course_progress
            sync_out = await server.call_tool(
                "study_sync_course_progress",
                {"course_identifier": str(curso.id), "progreso_pct": 95.0, "status": "en_curso"},
            )
            assert "Sincronización de curso exitosa" in sync_out.content[0].text
            assert "95.0%" in sync_out.content[0].text
        finally:
            restablecer_cuenta_mcp(token)

    anyio.run(_run_mcp)
