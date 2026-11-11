"""Tests unitarios y de integración para el Motor de Planificación Adaptativa de Estudio (Feature 044)."""

from datetime import date
import pytest

from aulento.core.study_planner import StudyPlannerEngine
from aulento.db.connection import get_connection
from aulento.db.repository import (
    BloqueHorarioRepository,
    CursoRepository,
    LibroRepository,
    PlataformaRepository,
)
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.schema import create_schema
from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
from aulento.models.libro import LibroCreate, EstadoLibro
from aulento.models.plataforma import PlataformaCreate
from aulento.models.study_planner import (
    AdaptivePlanRequest,
    ApplyPlanRequest,
    PedagogicalPhase,
)


@pytest.fixture
def db_conn():
    """Base de datos en memoria para pruebas."""
    conn = get_connection(":memory:")
    create_schema(conn)
    conn.execute("INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, creado_en) VALUES (1, 'ana', 'hash', '2026-01-01');")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def test_user_id():
    return 1


def test_daily_briefing_vacio(db_conn, test_user_id):
    engine = StudyPlannerEngine(db_conn, test_user_id)
    briefing = engine.obtener_daily_briefing()

    assert briefing.fecha == date.today().isoformat()
    assert briefing.fsrs_due_count == 0
    assert briefing.curso_sugerido is None
    assert briefing.libro_sugerido is None
    assert 0 <= briefing.urgency_score <= 100
    assert len(briefing.mensaje_enfoque) > 0


def test_daily_briefing_con_recursos_activos(db_conn, test_user_id):
    p_repo = PlataformaRepository(db_conn, test_user_id)
    plat = p_repo.create(PlataformaCreate(nombre="Google Cloud Skills", url_acceso="https://cloud.google.com"))

    c_repo = CursoRepository(db_conn, test_user_id)
    c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="GCP Data Engineer",
            url_aula="https://cloud.google.com/de",
            progreso_pct=25.0,
            estado=EstadoCurso.EN_CURSO,
            prioridad=PrioridadCurso.ALTA,
        )
    )

    l_repo = LibroRepository(db_conn, test_user_id)
    l_repo.create(
        LibroCreate(
            titulo="Designing Data-Intensive Applications",
            total_capitulos=12,
            pagina_actual=50,
            total_paginas=500,
            estado=EstadoLibro.LEYENDO,
        )
    )

    from aulento.models.fsrs_card import FSRSCardCreate
    # Añadir tarjeta vencida
    fsrs_repo = FSRSRepository(db_conn, test_user_id)
    fsrs_repo.create_card(
        FSRSCardCreate(
            item_pregunta="Idempotency",
            respuesta_esperada="An operation that can be applied multiple times without changing the result.",
        )
    )

    engine = StudyPlannerEngine(db_conn, test_user_id)
    briefing = engine.obtener_daily_briefing()

    assert briefing.fsrs_due_count >= 1
    assert briefing.curso_sugerido is not None
    assert briefing.curso_sugerido["nombre_curso"] == "GCP Data Engineer"
    assert briefing.curso_sugerido["prioridad"] == PrioridadCurso.ALTA.value
    assert briefing.libro_sugerido is not None
    assert briefing.libro_sugerido["titulo"] == "Designing Data-Intensive Applications"
    assert briefing.urgency_score > 30


def test_generar_plan_adaptativo_sesion_corta(db_conn, test_user_id):
    engine = StudyPlannerEngine(db_conn, test_user_id)
    req = AdaptivePlanRequest(available_minutes=25, start_time="09:00")
    plan = engine.generar_plan_adaptativo(req)

    assert plan.total_minutos == 25
    assert len(plan.bloques) >= 1
    assert plan.bloques[0].hora_inicio == "09:00"


def test_generar_plan_adaptativo_sesion_estandar(db_conn, test_user_id):
    p_repo = PlataformaRepository(db_conn, test_user_id)
    plat = p_repo.create(PlataformaCreate(nombre="Humai", url_acceso="https://humai.com.ar"))
    c_repo = CursoRepository(db_conn, test_user_id)
    c_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Machine Learning Avanzado",
            url_aula="https://humai.com.ar/aula",
            progreso_pct=40.0,
            estado=EstadoCurso.EN_CURSO,
            prioridad=PrioridadCurso.ALTA,
        )
    )

    l_repo = LibroRepository(db_conn, test_user_id)
    l_repo.create(
        LibroCreate(
            titulo="Python for Data Analysis",
            total_capitulos=10,
            pagina_actual=30,
            total_paginas=400,
            estado=EstadoLibro.LEYENDO,
        )
    )

    engine = StudyPlannerEngine(db_conn, test_user_id)
    req = AdaptivePlanRequest(available_minutes=60, start_time="10:00", include_breaks=True)
    plan = engine.generar_plan_adaptativo(req)

    assert plan.total_minutos == 60
    fases = [b.fase for b in plan.bloques]
    # Debe contemplar fases pedagógicas (warmup, deep work, break, active reading)
    assert PedagogicalPhase.DEEP_WORK_COURSE in fases
    assert PedagogicalPhase.ACTIVE_READING_BOOK in fases


def test_aplicar_plan_a_agenda(db_conn, test_user_id):
    engine = StudyPlannerEngine(db_conn, test_user_id)
    plan = engine.generar_plan_adaptativo(AdaptivePlanRequest(available_minutes=60, start_time="18:00"))

    apply_req = ApplyPlanRequest(bloques=plan.bloques, dia_semana=2, reemplazar_existentes=True)
    resp = engine.aplicar_plan_a_agenda(apply_req)

    assert resp.success is True
    assert resp.dia_semana == 2
    assert resp.bloques_creados == len(plan.bloques)
    assert len(resp.bloque_ids) == len(plan.bloques)

    # Verificar que existan en BloqueHorarioRepository
    h_repo = BloqueHorarioRepository(db_conn, test_user_id)
    bloques_db = h_repo.list_all(dia_semana=2)
    assert len(bloques_db) == len(plan.bloques)


def test_endpoints_planner_con_cliente(db_conn, test_user_id):
    from fastapi.testclient import TestClient
    from aulento.web.app import create_app
    from aulento.web.dependencies import usuario_actual, get_db_connection
    from aulento.auth.modelos import Usuario

    app = create_app()
    app.dependency_overrides[usuario_actual] = lambda: Usuario(id=test_user_id, nombre_usuario="test", rol="estudiante", activo=True)
    app.dependency_overrides[get_db_connection] = lambda: db_conn

    client = TestClient(app)

    # 1. Briefing
    res_b = client.get("/api/planner/daily-briefing")
    assert res_b.status_code == 200
    briefing = res_b.json()
    assert "urgency_score" in briefing
    assert "racha_dias" in briefing

    # 2. Recommendations
    res_p = client.post("/api/planner/recommendations", json={"available_minutes": 45, "start_time": "14:00"})
    assert res_p.status_code == 200
    plan = res_p.json()
    assert plan["total_minutos"] == 45
    assert len(plan["bloques"]) >= 1

    # 3. Apply today
    res_a = client.post("/api/planner/apply-today", json={"bloques": plan["bloques"], "dia_semana": 1})
    assert res_a.status_code == 200
    applied = res_a.json()
    assert applied["success"] is True
    assert applied["bloques_creados"] == len(plan["bloques"])


def test_un_libro_sin_total_de_paginas_no_le_gana_al_mas_avanzado(db_conn, test_user_id):
    """Sin total no hay avance: la página actual sola no puede compararse con un porcentaje."""
    libros = LibroRepository(db_conn, test_user_id)
    libros.create(LibroCreate(titulo="Sin total", pagina_actual=150, total_paginas=None, estado=EstadoLibro.LEYENDO))
    libros.create(LibroCreate(titulo="Casi terminado", pagina_actual=270, total_paginas=300, estado=EstadoLibro.LEYENDO))

    sugerido = StudyPlannerEngine(db_conn, test_user_id).obtener_daily_briefing().libro_sugerido

    assert sugerido["titulo"] == "Casi terminado" and sugerido["paginas_restantes"] == 30


def test_un_libro_sin_total_no_figura_como_terminado(db_conn, test_user_id):
    LibroRepository(db_conn, test_user_id).create(
        LibroCreate(titulo="Sin total", pagina_actual=150, total_paginas=None, estado=EstadoLibro.LEYENDO)
    )

    sugerido = StudyPlannerEngine(db_conn, test_user_id).obtener_daily_briefing().libro_sugerido

    assert sugerido["titulo"] == "Sin total" and sugerido["paginas_restantes"] is None
