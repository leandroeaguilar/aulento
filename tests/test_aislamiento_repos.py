"""Aislamiento por cuenta en la capa de datos (033, T2): R3, R4, R5, R6 y R7.

Dos cuentas reales comparten una base. La batería tiene tres partes:

- `LECTURAS`: cada método de lectura se llama como la cuenta A antes y después de que la cuenta B
  cargue sus datos. El resultado no puede cambiar: un filtro olvidado en un listado, un total o una
  rama de un `UNION` lo cambiaría.
- `POR_IDENTIFICADOR`: cada método que recibe un identificador (o un nombre) se llama como A con uno
  de B y con uno que no existe. Las dos llamadas tienen que terminar igual, sin devolver nada y sin
  cambiar una sola fila de la base.
- `test_inventario_*`: enumera por introspección los métodos públicos de los repositorios y falla si
  alguno no está en la batería ni en una excepción explícita.
"""

import inspect
import sqlite3
from types import SimpleNamespace

import pytest
from conftest import cuenta_de_prueba, cuenta_en

from aulento.core.activity_tracker import ActivityTracker
from aulento.db.connection import get_connection
from aulento.db.focus_repository import FocusRepository
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.repository import (
    BloqueHorarioRepository,
    CursoRepository,
    LibroRepository,
    MCPAuditRepository,
    PlataformaRepository,
)
from aulento.db.roadmap_repository import RoadmapNotFoundError, RoadmapRepository
from aulento.db.schema import PLATAFORMAS_SEMILLA, seed_plataformas
from aulento.fsrs.cloud_harvest import cosechar, pedir_tarjetas
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.fsrs.evolution_advisor import (
    diagnose_evolution,
    get_student_evolution_metrics,
)
from aulento.fsrs.harvester import HarvestCandidateCard, OmniHarvester
from aulento.fsrs.stats import (
    calculate_retention_rate,
    calculate_streak,
    get_full_fsrs_stats,
)
from aulento.models.curso import CursoCreate, CursoUpdate
from aulento.models.focus_session import FocusSessionCreate
from aulento.models.fsrs_card import FSRSCardCreate
from aulento.models.horario import BloqueHorarioCreate, BloqueHorarioUpdate
from aulento.models.libro import LibroCreate, LibroUpdate
from aulento.models.plataforma import PlataformaCreate, PlataformaUpdate
from aulento.models.roadmap import (
    GapTopicItem,
    LessonPromptRequest,
    PrerequisiteCreate,
    RoadmapCreate,
    RoadmapLessonCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
)
from aulento.roadmap.engine import RoadmapEngine
from aulento.roadmap.graph_engine import PrerequisiteGraphEngine
from aulento.roadmap.lesson_studio import LessonStudio
from aulento.roadmap.macro_fsrs import MacroFSRSEngine, MacroFSRSRepository
from aulento.roadmap.prerequisite_advisor import PrerequisiteAdvisor
from aulento.roadmap.prompt_builder import LessonPromptBuilder
from aulento.roadmap.syllabus_ingestor import SyllabusIngestor
from aulento.vault.cloud_notes import MaterialNoteGenerator
from aulento.vault.sop_course import CourseNoteGenerator, CourseNoteRequest
from aulento.vault.weekly_digest import WeeklyDigestExporter

TABLAS_RAIZ = (
    "plataformas",
    "libros_lectura",
    "bloques_horarios",
    "fsrs_items",
    "sesiones_estudio",
    "rutas_aprendizaje",
    "api_usage_logs",
    "mcp_audit_logs",
)
NIVEL_DE_INGLES = "b2_tech_data_ai"
NO_EXISTE = 987_654


# ------------------------------------------------------------------ armado del mundo de dos cuentas


def _servicios(conn: sqlite3.Connection, user_id: int, vault) -> SimpleNamespace:
    """Todos los repositorios y servicios de la capa de datos, atados a una cuenta."""
    rutas = RoadmapRepository(user_id)
    return SimpleNamespace(
        user=user_id,
        conn=conn,
        vault=vault,
        plataformas=PlataformaRepository(conn, user_id),
        cursos=CursoRepository(conn, user_id),
        libros=LibroRepository(conn, user_id),
        bloques=BloqueHorarioRepository(conn, user_id),
        fsrs=FSRSRepository(conn, user_id),
        focus=FocusRepository(conn, user_id),
        auditoria=MCPAuditRepository(conn),
        rutas=rutas,
        macro=MacroFSRSRepository(user_id),
        motor=MacroFSRSEngine(user_id),
        actividad=ActivityTracker(user_id),
        estudio=LessonStudio(rutas, vault_path=vault),
        grafo=PrerequisiteGraphEngine(rutas),
        prompts=LessonPromptBuilder(rutas),
        motor_de_rutas=RoadmapEngine(rutas),
        asesor=PrerequisiteAdvisor(rutas),
        cosecha=OmniHarvester(),
        apuntes=CourseNoteGenerator(user_id, conn=conn, vault_path=vault),
        apuntes_de_materiales=MaterialNoteGenerator(user_id, conn=conn, vault_path=vault),
        resumen=WeeklyDigestExporter(user_id, conn=conn, vault_path=vault),
    )


def _poblar(s: SimpleNamespace, marca: str, veces: int) -> SimpleNamespace:
    """Carga datos de la cuenta en todas las tablas. `veces` cambia los totales de una cuenta a otra.

    Los nombres "común" se repiten en las dos cuentas a propósito: no tienen que chocar ni mezclarse.
    """
    plataforma = s.plataformas.create(PlataformaCreate(nombre="Plataforma común", url_acceso="https://comun.example"))
    s.plataformas.create(PlataformaCreate(nombre=f"Plataforma de {marca}", url_acceso=f"https://{marca}.example"))
    curso = s.cursos.create(
        CursoCreate(
            plataforma_id=plataforma.id,
            nombre_curso=f"Curso común de {marca}",
            url_aula=f"https://aula.example/{marca}/curso",
            progreso_pct=10.0 * veces,
        )
    )
    if veces > 1:
        # Solo la otra cuenta sincroniza su curso: así el estado de sincronización difiere entre las dos
        s.cursos.update_sync_progress(curso.id, 10.0 * veces, fuente="webhook", external_id=f"ext-{marca}")
    libro = None
    for i in range(veces):
        libro = s.libros.create(
            LibroCreate(
                titulo=f"Libro común {i} de {marca}",
                total_capitulos=10,
                total_paginas=500,
                pagina_actual=40 + i,
                google_books_id=f"gbooks_{marca}_{i}",
            )
        )
    bloque = s.bloques.create(
        BloqueHorarioCreate(dia_semana=1, hora_inicio="09:00", hora_fin="10:00", tipo="curso", descripcion=f"Bloque de {marca}")
    )
    for _ in range(veces):
        s.focus.record_session(FocusSessionCreate(bloque_id=bloque.id, duracion_minutos=25, tipo="pomodoro"))

    tarjeta = s.fsrs.create_card(
        FSRSCardCreate(categoria=NIVEL_DE_INGLES, item_pregunta="¿Pregunta común?", respuesta_esperada=f"Respuesta de {marca}")
    )
    for i in range(veces):
        s.fsrs.create_card(
            FSRSCardCreate(categoria=NIVEL_DE_INGLES, item_pregunta=f"Pregunta {i} de {marca}", respuesta_esperada=f"R{i} {marca}")
        )
    ahora = "2026-10-10T12:00:00+00:00"
    s.fsrs.update_card_fsrs(tarjeta.id, 2, 0, 9.0, 4.0, ahora, ahora, veces, 0)
    for i in range(veces * 2):
        # Otra tasa de aciertos y otra racha en cada cuenta: mezcladas darían un número distinto
        dia = f"2026-10-{10 - (i if veces > 1 else 0):02d}T12:00:00+00:00"
        s.fsrs.add_review_log(tarjeta.id, 3 if (i % 2 or veces > 1) else 1, dia, 0.0, 1.0, 2)

    ruta = s.rutas.create_roadmap(
        RoadmapCreate(
            titulo="Ruta común",
            categoria="data_ai",
            modulos=[
                RoadmapModuleCreate(
                    titulo=f"Módulo uno de {marca}",
                    orden=1,
                    temas=[
                        RoadmapTopicCreate(titulo=f"Tema uno de {marca}", orden=1),
                        RoadmapTopicCreate(titulo=f"Tema dos de {marca}", orden=2),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo=f"Módulo dos de {marca}", orden=2, temas=[RoadmapTopicCreate(titulo=f"Tema tres de {marca}", orden=1)]
                ),
            ],
        )
    )
    modulo = ruta.modulos[0]
    tema, tema2 = modulo.temas
    tema3 = ruta.modulos[1].temas[0]
    tarjetas_de_clase = [{"pregunta": f"¿Clase {i} de {marca}?", "respuesta": f"Sí {i}"} for i in range(veces)]
    for version in ("primera", "segunda"):
        clase = s.rutas.save_lesson(
            RoadmapLessonCreate(
                tema_id=tema.id,
                titulo=f"Clase de {marca}",
                contenido_markdown=f"# Clase {version} de {marca}",
                flashcards_json=tarjetas_de_clase,
            )
        )
    version_id = s.rutas.get_lesson_versions(tema.id)[0].id
    s.estudio.export_flashcards_to_fsrs(clase.id)
    s.rutas.add_prerequisite(ruta.id, tema.id, tema2.id)
    s.rutas.update_topic_status(tema2.id, "completado")
    for _ in range(veces):
        s.motor.review_topic(tema2.id, 3, review_time=None)
    for _ in range(veces):
        s.rutas.log_api_usage(
            model=f"modelo-de-{marca}", endpoint_tipo="lesson_gen", api_tier="free", prompt_tokens=100,
            completion_tokens=50, total_tokens=150, estimated_cost_usd=0.01,
        )
        s.auditoria.log(f"herramienta_de_{marca}", user_id=s.user)

    return SimpleNamespace(
        plat=plataforma.id,
        curso=curso.id,
        libro=libro.id,
        bloque=bloque.id,
        tarjeta=tarjeta.id,
        ruta=ruta.id,
        modulo=modulo.id,
        tema=tema.id,
        tema2=tema2.id,
        tema3=tema3.id,
        clase=clase.id,
        version=version_id,
        mazo=f"roadmap_{ruta.id}",
        nombre_plat=f"Plataforma de {marca}",
        nombre_curso=f"Curso común de {marca}",
        url_curso=f"https://aula.example/{marca}/curso",
        external_id_curso=f"ext-{marca}",
        titulo_libro=f"Libro común 0 de {marca}",
        google_books_id=f"gbooks_{marca}_0",
        titulo_ruta=f"Ruta de {marca}",
    )


INEXISTENTES = SimpleNamespace(
    plat=NO_EXISTE, curso=NO_EXISTE, libro=NO_EXISTE, bloque=NO_EXISTE, tarjeta=NO_EXISTE, ruta=NO_EXISTE,
    modulo=NO_EXISTE, tema=NO_EXISTE, tema2=NO_EXISTE + 1, tema3=NO_EXISTE + 2, clase=NO_EXISTE, version=NO_EXISTE,
    mazo=f"roadmap_{NO_EXISTE}", nombre_plat="Plataforma que no existe", nombre_curso="Curso que no existe",
    url_curso="https://aula.example/nadie/curso", external_id_curso="ext-inexistente", titulo_libro="Libro que no existe", google_books_id="gbooks_inexistente", titulo_ruta="Ruta que no existe",
)  # fmt: skip


@pytest.fixture
def mundo(cuenta, otra_cuenta, tmp_path):
    """Base aislada con dos cuentas: `a` ya tiene datos; `cargar_b()` carga los de la otra."""
    conn = get_connection()
    # La cuenta del fixture nace con las plataformas semilla: acá cada cuenta arranca vacía
    conn.execute("DELETE FROM plataformas;")
    conn.commit()
    a = _servicios(conn, cuenta, tmp_path / "vault_a")
    b = _servicios(conn, otra_cuenta, tmp_path / "vault_b")
    a.ids = _poblar(a, "A", veces=1)
    # La ruta de B lleva además un título que A no tiene, para buscarla por nombre
    estado = SimpleNamespace(conn=conn, a=a, b=b)

    def cargar_b() -> SimpleNamespace:
        b.ids = _poblar(b, "B", veces=3)
        b.rutas.create_roadmap(RoadmapCreate(titulo="Ruta de B", categoria="data_ai", modulos=[]))
        return b.ids

    estado.cargar_b = cargar_b
    yield estado
    conn.close()


def _contenido(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Todas las filas de todas las tablas, para comprobar que una llamada no cambió nada."""
    conn.commit()
    tablas = [
        fila[0]
        for fila in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%';")
    ]
    return {tabla: sorted(map(tuple, conn.execute(f"SELECT * FROM {tabla};")), key=repr) for tabla in tablas}


def _normal(valor):
    """Valor comparable: modelos a diccionarios y sin la marca de tiempo de generación."""
    if hasattr(valor, "model_dump"):
        valor = valor.model_dump()
    if isinstance(valor, dict):
        return {k: _normal(v) for k, v in valor.items() if k != "generated_at"}
    if isinstance(valor, (list, tuple)):
        return [_normal(v) for v in valor]
    return valor


# ------------------------------------------------------------------ R3: lecturas

AHORA = None  # los métodos usan el reloj real; las dos lecturas de cada caso ocurren en el mismo instante lógico

LECTURAS = {
    "PlataformaRepository.list_all": lambda s: s.plataformas.list_all(),
    "PlataformaRepository.get_by_name": lambda s: s.plataformas.get_by_name("plataforma común"),
    "CursoRepository.list_all": lambda s: s.cursos.list_all(),
    "CursoRepository.find_by_url_or_name#url_parcial": lambda s: s.cursos.find_by_url_or_name("aula.example"),
    "CursoRepository.find_by_url_or_name#nombre_parcial": lambda s: s.cursos.find_by_url_or_name("Curso común"),
    "CursoRepository.get_sync_status": lambda s: s.cursos.get_sync_status(),
    "LibroRepository.list_all": lambda s: s.libros.list_all(),
    "LibroRepository.find_by_title": lambda s: s.libros.find_by_title("Libro común"),
    "BloqueHorarioRepository.list_all": lambda s: s.bloques.list_all(),
    "BloqueHorarioRepository.list_all#dia": lambda s: s.bloques.list_all(dia_semana=1),
    "FSRSRepository.list_cards": lambda s: s.fsrs.list_cards(),
    "FSRSRepository.list_cards#categoria": lambda s: s.fsrs.list_cards(categoria=NIVEL_DE_INGLES),
    "FSRSRepository.get_roadmap_decks": lambda s: s.fsrs.get_roadmap_decks(),
    "FSRSRepository.get_due_cards": lambda s: s.fsrs.get_due_cards(limit=100),
    "FSRSRepository.get_due_cards#nivel": lambda s: s.fsrs.get_due_cards(limit=100, level="b2"),
    "FSRSRepository.get_due_cards#forzado": lambda s: s.fsrs.get_due_cards(limit=100, force=True),
    "FSRSRepository.get_due_cards#adaptativo": lambda s: s.fsrs.get_due_cards(limit=100, level="adaptive", force=True),
    "FSRSRepository.get_due_cards#categoria": lambda s: s.fsrs.get_due_cards(limit=100, categoria=NIVEL_DE_INGLES),
    "FSRSRepository.count_stats": lambda s: s.fsrs.count_stats(),
    "FocusRepository.list_sessions": lambda s: s.focus.list_sessions(limit=2),
    "FocusRepository.get_weekly_stats": lambda s: s.focus.get_weekly_stats(),
    "RoadmapRepository.get_roadmaps": lambda s: s.rutas.get_roadmaps(),
    "RoadmapRepository.get_roadmap_by_title": lambda s: s.rutas.get_roadmap_by_title("Ruta común"),
    "RoadmapRepository.get_token_usage_summary": lambda s: s.rutas.get_token_usage_summary(days=30),
    "RoadmapRepository.get_recent_api_logs": lambda s: s.rutas.get_recent_api_logs(limit=2),
    "MacroFSRSRepository.get_due_topics": lambda s: s.macro.get_due_topics(now_utc=_futuro()),
    "MacroFSRSRepository.list_all_retention": lambda s: s.macro.list_all_retention(),
    "ActivityTracker.get_heatmap": lambda s: s.actividad.get_heatmap(days=7),
    "MCPAuditRepository.get_recent_logs": lambda s: s.auditoria.get_recent_logs(s.user, limit=2),
    "stats.calculate_retention_rate": lambda s: calculate_retention_rate(s.conn, s.user),
    "stats.calculate_streak": lambda s: _fechas_de_repaso(s),
    "stats.get_full_fsrs_stats": lambda s: get_full_fsrs_stats(s.conn, s.user),
    "evolution_advisor.get_student_evolution_metrics": lambda s: get_student_evolution_metrics(s.conn, s.user),
    "evolution_advisor.diagnose_evolution": lambda s: diagnose_evolution(s.conn, s.user),
    "WeeklyDigestExporter.build_digest": lambda s: s.resumen.build_digest("2026-W41"),
    "MaterialNoteGenerator.resolve_course": lambda s: s.apuntes_de_materiales.resolve_course(s.conn, None, "curso común"),
    "OmniHarvester.check_duplicates": lambda s: s.cosecha.check_duplicates(
        s.conn,
        s.user,
        [
            HarvestCandidateCard(item_pregunta=p, respuesta_esperada=r, categoria=NIVEL_DE_INGLES, source="prueba")
            for p, r in (("Pregunta 2 de B", "otra"), ("otra", "R1 B"), ("¿Pregunta común?", "x"), ("nueva", "nueva"))
        ],
    ),
}


def _futuro():
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC) + timedelta(days=3650)


def _fechas_de_repaso(s):
    """La racha depende del día en que corre la suite: se fija el reloj en el día de los repasos cargados."""
    from datetime import UTC, datetime

    return calculate_streak(s.conn, s.user, datetime(2026, 10, 10, 18, 0, tzinfo=UTC))


@pytest.mark.parametrize("caso", sorted(LECTURAS))
def test_r3_una_lectura_no_cambia_cuando_otra_cuenta_carga_datos(mundo, caso, monkeypatch):
    """R3: listados, búsquedas, totales, rachas y estadísticas devuelven solo lo propio."""
    leer = LECTURAS[caso]
    antes = _normal(leer(mundo.a))
    assert antes not in (None, [], {}, 0, 0.0), f"{caso}: la lectura de A está vacía y no probaría nada"

    mundo.cargar_b()

    assert _normal(leer(mundo.a)) == antes, f"{caso}: los datos de otra cuenta cambiaron lo que ve A"
    assert _normal(leer(mundo.b)) != antes, f"{caso}: B no ve sus propios datos"


def test_r3_cuenta_sin_datos_no_ve_nada(mundo, tmp_path):
    """R3: una tercera cuenta, sin datos, recibe vacíos y ceros aunque las otras dos tengan de todo."""
    mundo.cargar_b()
    tercera = _servicios(mundo.conn, cuenta_de_prueba(mundo.conn, "tercera-cuenta").id, tmp_path / "vault_c")

    assert tercera.plataformas.list_all() == []
    assert tercera.cursos.list_all() == []
    assert tercera.cursos.get_sync_status() == {"total_cursos": 0, "cursos_sincronizados": 0, "ultima_sincronizacion": None}
    assert tercera.libros.list_all() == []
    assert tercera.bloques.list_all() == []
    assert tercera.fsrs.list_cards() == []
    assert tercera.fsrs.get_due_cards(limit=100, force=True) == []
    assert tercera.fsrs.get_due_cards(limit=100, level="adaptive", force=True) == []
    assert tercera.fsrs.get_roadmap_decks() == []
    assert tercera.fsrs.count_stats() == {
        "total": 0, "due_today": 0, "learning": 0, "review": 0, "relearning": 0, "total_reviews": 0
    }  # fmt: skip
    assert tercera.focus.list_sessions() == []
    semana = tercera.focus.get_weekly_stats()
    assert (semana["minutos_semana"], semana["sesiones_semana"], semana["minutos_hoy"], semana["por_tipo_minutos"]) == (0, 0, 0, {})
    assert tercera.rutas.get_roadmaps() == []
    consumo = tercera.rutas.get_token_usage_summary()
    assert (consumo.total_requests, consumo.total_tokens, consumo.by_model, consumo.recent_logs) == (0, 0, {}, [])
    assert tercera.rutas.get_recent_api_logs() == []
    assert tercera.macro.get_due_topics(now_utc=_futuro()) == []
    assert tercera.macro.list_all_retention() == []
    assert tercera.auditoria.get_recent_logs(tercera.user) == []

    mapa = tercera.actividad.get_heatmap(days=30)
    assert all(d.score == 0 for d in mapa.days)
    racha = mapa.streak.model_dump()
    assert set(racha.values()) == {0}, racha

    estadisticas = get_full_fsrs_stats(mundo.conn, tercera.user)
    assert (estadisticas["total_cards"], estadisticas["total_reviews"], estadisticas["categories"]) == (0, 0, {})
    assert (estadisticas["retention_rate"], estadisticas["streak_days"]) == (0.0, 0)
    assert calculate_retention_rate(mundo.conn, tercera.user) == 0.0
    assert _fechas_de_repaso(tercera) == 0
    evolucion = get_student_evolution_metrics(mundo.conn, tercera.user)
    assert (evolucion["total_cards"], evolucion["total_reviewed"], evolucion["global_mastery"]) == (0, 0, 0)

    resumen = tercera.resumen.build_digest("2026-W41")["content"]
    assert "Sin cursos registrados" in resumen and "Sin libros en lectura" in resumen
    assert "de A" not in resumen and "de B" not in resumen


# ------------------------------------------------------------------ R4: identificadores ajenos

_MD = "# Clase importada\n\nTexto."

POR_IDENTIFICADOR = {
    "PlataformaRepository.get_by_id": lambda s, x: s.plataformas.get_by_id(x.plat),
    "PlataformaRepository.get_by_name": lambda s, x: s.plataformas.get_by_name(x.nombre_plat),
    "PlataformaRepository.delete": lambda s, x: s.plataformas.delete(x.plat),
    "PlataformaRepository.update": lambda s, x: s.plataformas.update(x.plat, PlataformaUpdate(nombre="Tomada")),
    "CursoRepository.create#plataforma": lambda s, x: s.cursos.create(
        CursoCreate(plataforma_id=x.plat, nombre_curso="Colgado", url_aula="https://x.example")
    ),
    "CursoRepository.get_by_id": lambda s, x: s.cursos.get_by_id(x.curso),
    "CursoRepository.list_all#plataforma": lambda s, x: s.cursos.list_all(plataforma_id=x.plat),
    "CursoRepository.update_progress": lambda s, x: s.cursos.update_progress(x.curso, 99.0),
    "CursoRepository.update_progress#estado": lambda s, x: s.cursos.update_progress(x.curso, 50.0, "pausado"),
    "CursoRepository.find_by_url_or_name#id": lambda s, x: s.cursos.find_by_url_or_name(str(x.curso + 10_000_000)),
    "CursoRepository.find_by_url_or_name#url": lambda s, x: s.cursos.find_by_url_or_name(x.url_curso),
    "CursoRepository.find_by_url_or_name#nombre": lambda s, x: s.cursos.find_by_url_or_name(x.nombre_curso),
    "CursoRepository.delete": lambda s, x: s.cursos.delete(x.curso),
    "CursoRepository.find_by_name": lambda s, x: s.cursos.find_by_name(x.nombre_curso),
    "CursoRepository.find_by_external_id": lambda s, x: s.cursos.find_by_external_id(x.external_id_curso),
    "CursoRepository.update_sync_progress": lambda s, x: s.cursos.update_sync_progress(x.curso, 99.0, fuente="webhook"),
    "CursoRepository.update": lambda s, x: s.cursos.update(x.curso, CursoUpdate(nombre_curso="Tomado")),
    "LibroRepository.get_by_id": lambda s, x: s.libros.get_by_id(x.libro),
    "LibroRepository.find_by_title": lambda s, x: s.libros.find_by_title(x.titulo_libro),
    "LibroRepository.buscar_por_titulo": lambda s, x: s.libros.buscar_por_titulo(x.titulo_libro),
    "LibroRepository.update_progress": lambda s, x: s.libros.update_progress(x.libro, pagina_actual=1),
    "LibroRepository.advance_chapter": lambda s, x: s.libros.advance_chapter(x.libro),
    "LibroRepository.delete": lambda s, x: s.libros.delete(x.libro),
    "LibroRepository.update": lambda s, x: s.libros.update(x.libro, LibroUpdate(titulo="Tomado")),
    "LibroRepository.vincular_google_books": lambda s, x: s.libros.vincular_google_books(x.libro, "gbooks_ajeno"),
    "LibroRepository.find_by_google_books_id": lambda s, x: s.libros.find_by_google_books_id(x.google_books_id),
    "BloqueHorarioRepository.get": lambda s, x: s.bloques.get(x.bloque),
    "BloqueHorarioRepository.update": lambda s, x: s.bloques.update(x.bloque, BloqueHorarioUpdate(descripcion="Tomado")),
    "BloqueHorarioRepository.delete": lambda s, x: s.bloques.delete(x.bloque),
    "FSRSRepository.mazo_es_de_la_cuenta": lambda s, x: s.fsrs.mazo_es_de_la_cuenta(x.mazo),
    "FSRSRepository.exigir_mazo_de_la_cuenta": lambda s, x: s.fsrs.exigir_mazo_de_la_cuenta(x.mazo),
    "FSRSRepository.create_card#mazo": lambda s, x: s.fsrs.create_card(
        FSRSCardCreate(categoria=x.mazo, item_pregunta="Colgada", respuesta_esperada="R")
    ),
    "FSRSRepository.get_card_by_id": lambda s, x: s.fsrs.get_card_by_id(x.tarjeta),
    "FSRSRepository.list_cards#mazo": lambda s, x: s.fsrs.list_cards(categoria=x.mazo),
    "FSRSRepository.get_due_cards#mazo": lambda s, x: s.fsrs.get_due_cards(limit=100, level=x.mazo, force=True),
    "FSRSRepository.get_due_cards#categoria": lambda s, x: s.fsrs.get_due_cards(limit=100, categoria=x.mazo, force=True),
    "FSRSRepository.update_card_fsrs": lambda s, x: s.fsrs.update_card_fsrs(x.tarjeta, 3, 1, 1.0, 9.0, "2030-01-01", "2030-01-01", 99, 99),
    "FSRSRepository.add_review_log": lambda s, x: s.fsrs.add_review_log(x.tarjeta, 4, "2030-01-01T00:00:00+00:00", 0.0, 1.0, 2),
    "FSRSRepository.delete_card": lambda s, x: s.fsrs.delete_card(x.tarjeta),
    "FocusRepository.record_session#bloque": lambda s, x: s.focus.record_session(
        FocusSessionCreate(bloque_id=x.bloque, duracion_minutos=30, tipo="pomodoro")
    ),
    "RoadmapRepository.get_roadmap": lambda s, x: s.rutas.get_roadmap(x.ruta),
    "RoadmapRepository.get_roadmap_by_title": lambda s, x: s.rutas.get_roadmap_by_title(x.titulo_ruta),
    "RoadmapRepository.delete_roadmap": lambda s, x: s.rutas.delete_roadmap(x.ruta),
    "RoadmapRepository.update_topic_status": lambda s, x: s.rutas.update_topic_status(x.tema3, "completado"),
    "RoadmapRepository.get_topic_with_context": lambda s, x: s.rutas.get_topic_with_context(x.tema),
    "RoadmapRepository.get_module_with_context": lambda s, x: s.rutas.get_module_with_context(x.modulo),
    "RoadmapRepository.add_topics_to_module": lambda s, x: s.rutas.add_topics_to_module(
        x.modulo, [RoadmapTopicCreate(titulo="Colado", orden=9)]
    ),
    "RoadmapRepository.update_roadmap_metadata": lambda s, x: s.rutas.update_roadmap_metadata(x.ruta, {"tomada": True}),
    "RoadmapRepository.update_graph_settings": lambda s, x: s.rutas.update_graph_settings(x.ruta, False),
    "RoadmapRepository.save_lesson": lambda s, x: s.rutas.save_lesson(
        RoadmapLessonCreate(tema_id=x.tema, titulo="Pisada", contenido_markdown="# Pisada")
    ),
    "RoadmapRepository.save_lesson#tema_sin_clase": lambda s, x: s.rutas.save_lesson(
        RoadmapLessonCreate(tema_id=x.tema3, titulo="Colada", contenido_markdown="# Colada")
    ),
    "RoadmapRepository.get_lesson_versions": lambda s, x: s.rutas.get_lesson_versions(x.tema),
    "RoadmapRepository.restore_lesson_version": lambda s, x: s.rutas.restore_lesson_version(x.version),
    "RoadmapRepository.get_lesson_by_topic_id": lambda s, x: s.rutas.get_lesson_by_topic_id(x.tema),
    "RoadmapRepository.merge_gap_topics": lambda s, x: s.rutas.merge_gap_topics(
        x.ruta, [GapTopicItem(titulo="Colado", descripcion="d")]
    ),
    "RoadmapRepository.add_prerequisite#ruta": lambda s, x: s.rutas.add_prerequisite(x.ruta, x.tema, x.tema3),
    "RoadmapRepository.add_prerequisite#temas": lambda s, x: s.rutas.add_prerequisite(s.ids.ruta, x.tema, x.tema3),
    "RoadmapRepository.add_prerequisite#destino": lambda s, x: s.rutas.add_prerequisite(s.ids.ruta, s.ids.tema, x.tema3),
    "RoadmapRepository.add_prerequisite#origen": lambda s, x: s.rutas.add_prerequisite(s.ids.ruta, x.tema, s.ids.tema3),
    "RoadmapRepository.add_prerequisites_bulk#ruta": lambda s, x: s.rutas.add_prerequisites_bulk(
        x.ruta, [PrerequisiteCreate(tema_origen_id=x.tema, tema_destino_id=x.tema3)], secuencia_implicita=False
    ),
    "RoadmapRepository.add_prerequisites_bulk#temas": lambda s, x: s.rutas.add_prerequisites_bulk(
        s.ids.ruta,
        [
            PrerequisiteCreate(tema_origen_id=s.ids.tema, tema_destino_id=s.ids.tema3),
            PrerequisiteCreate(tema_origen_id=x.tema, tema_destino_id=x.tema3),
        ],
    ),
    "RoadmapRepository.delete_prerequisite": lambda s, x: s.rutas.delete_prerequisite(x.ruta, x.tema, x.tema2),
    "RoadmapRepository.get_prerequisites": lambda s, x: s.rutas.get_prerequisites(x.ruta),
    "MacroFSRSRepository.init_topic_retention": lambda s, x: s.macro.init_topic_retention(x.tema3),
    "MacroFSRSRepository.init_topic_retention#ya_iniciada": lambda s, x: s.macro.init_topic_retention(x.tema2),
    "MacroFSRSRepository.get_by_tema_id": lambda s, x: s.macro.get_by_tema_id(x.tema2),
    "MacroFSRSEngine.review_topic": lambda s, x: s.motor.review_topic(x.tema2, 1),
    "MacroFSRSEngine.review_topic#sin_retencion": lambda s, x: s.motor.review_topic(x.tema3, 4),
    "MacroFSRSEngine.get_feynman_microquiz": lambda s, x: s.motor.get_feynman_microquiz(x.tema),
    "LessonStudio.export_flashcards_to_fsrs": lambda s, x: s.estudio.export_flashcards_to_fsrs(x.clase),
    "LessonStudio.vault_note_was_edited": lambda s, x: s.estudio.vault_note_was_edited(x.clase),
    "LessonStudio.export_lesson_to_vault": lambda s, x: s.estudio.export_lesson_to_vault(x.clase),
    "LessonStudio.import_external_lesson": lambda s, x: s.estudio.import_external_lesson(x.tema, _MD),
    "LessonStudio.generate_lesson_in_app": lambda s, x: s.estudio.generate_lesson_in_app(x.tema),
    "LessonPromptBuilder.build_prompt": lambda s, x: s.prompts.build_prompt(x.tema, LessonPromptRequest()),
    "PrerequisiteGraphEngine.get_graph_data": lambda s, x: s.grafo.get_graph_data(x.ruta),
    "RoadmapEngine.expand_module": lambda s, x: s.motor_de_rutas.expand_module(x.modulo),
    "RoadmapEngine.suggest_next_topics": lambda s, x: s.motor_de_rutas.suggest_next_topics(x.ruta),
    "PrerequisiteAdvisor.suggest": lambda s, x: s.asesor.suggest(x.ruta),
    "CourseNoteGenerator.generate_note_markdown": lambda s, x: s.apuntes.generate_note_markdown(
        CourseNoteRequest(course_id=x.curso, topic="Tema")
    ),
    "OmniHarvester.commit_harvest#mazo": lambda s, x: s.cosecha.commit_harvest(
        s.conn,
        s.user,
        [
            HarvestCandidateCard(item_pregunta="Buena", respuesta_esperada="R", categoria=NIVEL_DE_INGLES, source="p"),
            HarvestCandidateCard(item_pregunta="Colgada", respuesta_esperada="R", categoria=x.mazo, source="p"),
        ],
    ),
    "OmniHarvester.harvest_from_materials#ruta": lambda s, x: s.cosecha.harvest_from_materials(s.user, query="x", roadmap_id=x.ruta),
}

VACIOS = (None, False, [], 0)


def _resultado(llamada):
    try:
        return ("valor", _normal(llamada()))
    except Exception as error:  # noqa: BLE001 - se compara el tipo de la excepción, sea cual sea
        return ("excepción", type(error).__name__)


@pytest.mark.parametrize("caso", sorted(POR_IDENTIFICADOR))
def test_r4_un_identificador_ajeno_es_como_uno_inexistente_y_no_cambia_nada(mundo, caso, monkeypatch):
    """R4: lo de otra cuenta no se lee, no se modifica, no se borra ni se usa como referencia."""
    ajenos = mundo.cargar_b()
    usar = POR_IDENTIFICADOR[caso]
    antes = _contenido(mundo.conn)

    con_ajeno = _resultado(lambda: usar(mundo.a, ajenos))
    assert _contenido(mundo.conn) == antes, f"{caso}: la llamada con un identificador ajeno cambió la base"

    con_inexistente = _resultado(lambda: usar(mundo.a, INEXISTENTES))
    assert _contenido(mundo.conn) == antes, f"{caso}: la llamada con un identificador inexistente cambió la base"

    assert con_ajeno == con_inexistente, f"{caso}: lo ajeno no se comporta como lo inexistente"
    if caso not in RESPONDEN_NO_ENCONTRADO:
        assert con_ajeno[0] == "excepción" or con_ajeno[1] in VACIOS, f"{caso}: devolvió datos de otra cuenta: {con_ajeno}"

    # El dueño, con el mismo identificador, sí obtiene algo: el caso no pasa por estar mal armado
    con_propio = _resultado(lambda: usar(mundo.b, ajenos))
    assert con_propio != con_ajeno or caso in SIN_DIFERENCIA_PARA_EL_DUENO, f"{caso}: el dueño tampoco lo logra"


# Métodos que ante una ruta inexistente devuelven un objeto que lo dice, en vez de None o una excepción
RESPONDEN_NO_ENCONTRADO = {"RoadmapEngine.suggest_next_topics"}

# Casos donde el dueño obtiene lo mismo que un extraño por una razón ajena al aislamiento
SIN_DIFERENCIA_PARA_EL_DUENO = {
    # busca un id numérico corrido a propósito para que no caiga en otra rama de la búsqueda
    "CursoRepository.find_by_url_or_name#id",
    # sin IA configurada en la suite, también fallan para el dueño
    "RoadmapEngine.expand_module",
    "PrerequisiteAdvisor.suggest",
    "OmniHarvester.harvest_from_materials#ruta",
    # la nota todavía no se exportó al vault: tampoco está editada para el dueño
    "LessonStudio.vault_note_was_edited",
}


def test_r4_un_curso_ajeno_no_se_encuentra_por_su_id_en_la_busqueda(mundo):
    ajenos = mundo.cargar_b()
    assert mundo.a.cursos.find_by_url_or_name(str(ajenos.curso)) is None
    assert mundo.b.cursos.find_by_url_or_name(str(ajenos.curso)).id == ajenos.curso


def test_r4_resolver_el_curso_de_una_nota_no_alcanza_los_de_otra_cuenta(mundo):
    """Con un id ajeno o una pista que solo coincide con cursos de B, A recibe uno de los suyos."""
    ajenos = mundo.cargar_b()
    for curso_id, pista in ((ajenos.curso, None), (None, "Curso común de B"), (None, "Plataforma de B")):
        antes = _contenido(mundo.conn)
        curso, plataforma = mundo.a.apuntes_de_materiales.resolve_course(mundo.conn, curso_id, pista)
        assert curso.id == mundo.a.ids.curso and plataforma == "Plataforma común"
        assert _contenido(mundo.conn) == antes


def test_r4_el_mazo_de_una_ruta_ajena_no_muestra_su_titulo(mundo):
    """Una tarjeta vieja de A en el mazo de una ruta de B aparece como de una ruta que A no tiene."""
    ajenos = mundo.cargar_b()
    mundo.conn.execute(
        "INSERT INTO fsrs_items (user_id, categoria, item_pregunta, respuesta_esperada) VALUES (?, ?, 'Vieja', 'R');",
        (mundo.a.user, ajenos.mazo),
    )
    mundo.conn.commit()

    mazos = {m["categoria"]: m for m in mundo.a.fsrs.get_roadmap_decks()}
    assert mazos[ajenos.mazo]["titulo"] == f"Ruta eliminada (#{ajenos.ruta})"
    assert mazos[ajenos.mazo]["ruta_existe"] is False
    assert mazos[ajenos.mazo]["total"] == 1
    assert mazos[mundo.a.ids.mazo]["titulo"] == "Ruta común" and mazos[mundo.a.ids.mazo]["ruta_existe"] is True

    de_b = {m["categoria"]: m for m in mundo.b.fsrs.get_roadmap_decks()}
    assert de_b[ajenos.mazo]["total"] == 3 and de_b[ajenos.mazo]["titulo"] == "Ruta común"


def test_r4_una_cosecha_con_un_mazo_ajeno_no_guarda_ninguna_tarjeta(mundo):
    ajenos = mundo.cargar_b()
    tarjetas = [
        HarvestCandidateCard(item_pregunta="Buena", respuesta_esperada="R", categoria=NIVEL_DE_INGLES, source="p"),
        HarvestCandidateCard(item_pregunta="Colgada", respuesta_esperada="R", categoria=ajenos.mazo, source="p"),
    ]
    antes = _contenido(mundo.conn)
    with pytest.raises(RoadmapNotFoundError):
        mundo.a.cosecha.commit_harvest(mundo.conn, mundo.a.user, tarjetas)
    assert _contenido(mundo.conn) == antes

    tarjetas[1].categoria = mundo.a.ids.mazo
    assert mundo.a.cosecha.commit_harvest(mundo.conn, mundo.a.user, tarjetas) == 2
    assert mundo.conn.execute("SELECT count(*) FROM fsrs_items WHERE user_id IS NOT ?;", (mundo.a.user,)).fetchone()[0] == len(
        mundo.b.fsrs.list_cards()
    )


# ------------------------------------------------------------------ R5: escrituras


def test_r5_todo_lo_que_crea_una_cuenta_queda_a_su_nombre(mundo):
    """Cada alta de `_poblar` (repositorios, clases exportadas, consumo de IA, auditoría) lleva el dueño."""
    for tabla in TABLAS_RAIZ:
        total, propias = mundo.conn.execute(
            f"SELECT count(*), sum(user_id IS ?) FROM {tabla};", (mundo.a.user,)
        ).fetchone()
        assert total > 0, f"{tabla}: _poblar no escribió nada y el test no probaría esa tabla"
        assert propias == total, f"{tabla}: hay filas sin dueño o de otra cuenta"

    mundo.cargar_b()
    for tabla in TABLAS_RAIZ:
        sin_dueno = mundo.conn.execute(f"SELECT count(*) FROM {tabla} WHERE user_id IS NULL;").fetchone()[0]
        assert sin_dueno == 0, tabla


def test_r5_el_mismo_nombre_en_dos_cuentas_no_choca_y_en_la_misma_si(mundo):
    """R1/R5: plataforma, ruta y tarjeta repetidas conviven entre cuentas; en una misma cuenta no."""
    ajenos = mundo.cargar_b()
    assert mundo.a.ids.plat != ajenos.plat and mundo.a.ids.ruta != ajenos.ruta and mundo.a.ids.tarjeta != ajenos.tarjeta

    with pytest.raises(sqlite3.IntegrityError):
        mundo.a.plataformas.create(PlataformaCreate(nombre="Plataforma común", url_acceso="https://otra.example"))
    mundo.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        mundo.a.rutas.create_roadmap(RoadmapCreate(titulo="Ruta común", categoria="data_ai", modulos=[]))

    # Repetir la tarjeta actualiza la propia y no toca la de la otra cuenta
    repetida = mundo.a.fsrs.create_card(
        FSRSCardCreate(categoria=NIVEL_DE_INGLES, item_pregunta="¿Pregunta común?", respuesta_esperada="Corregida")
    )
    assert repetida.id == mundo.a.ids.tarjeta
    assert mundo.a.fsrs.get_card_by_id(mundo.a.ids.tarjeta).respuesta_esperada == "Corregida"
    assert mundo.b.fsrs.get_card_by_id(ajenos.tarjeta).respuesta_esperada == "Respuesta de B"


def test_r5_exportar_las_tarjetas_de_una_clase_solo_pisa_las_propias(mundo):
    """El alta por coincidencia de `export_flashcards_to_fsrs` compara contra las tarjetas de la cuenta."""
    ajenos = mundo.cargar_b()
    # A tiene, en el mazo de su ruta, una tarjeta con la misma pregunta que una de la clase de B
    mundo.conn.execute(
        "INSERT INTO fsrs_items (user_id, categoria, item_pregunta, respuesta_esperada) VALUES (?, ?, ?, 'De A');",
        (mundo.a.user, ajenos.mazo, "¿Clase 0 de B?"),
    )
    mundo.conn.commit()
    assert mundo.b.estudio.export_flashcards_to_fsrs(ajenos.clase) == 3
    fila = mundo.conn.execute(
        "SELECT respuesta_esperada FROM fsrs_items WHERE user_id = ? AND item_pregunta = '¿Clase 0 de B?';", (mundo.a.user,)
    ).fetchone()
    assert fila[0] == "De A"
    assert len(mundo.b.fsrs.list_cards(categoria=ajenos.mazo)) == 3


def test_r5_la_deteccion_de_duplicados_mira_solo_las_tarjetas_de_la_cuenta(mundo):
    ajenos = mundo.cargar_b()

    def candidatos():
        return [
            HarvestCandidateCard(item_pregunta="Pregunta 2 de B", respuesta_esperada="otra", categoria=NIVEL_DE_INGLES, source="p"),
            HarvestCandidateCard(item_pregunta="otra", respuesta_esperada="R2 B", categoria=NIVEL_DE_INGLES, source="p"),
            HarvestCandidateCard(item_pregunta="¿Clase 1 de B?", respuesta_esperada="x", categoria=ajenos.mazo, source="p"),
            HarvestCandidateCard(item_pregunta="¿Pregunta común?", respuesta_esperada="x", categoria=NIVEL_DE_INGLES, source="p"),
        ]

    assert [c.is_duplicate for c in mundo.a.cosecha.check_duplicates(mundo.conn, mundo.a.user, candidatos())] == [
        False, False, False, True
    ]  # fmt: skip
    assert [c.is_duplicate for c in mundo.b.cosecha.check_duplicates(mundo.conn, mundo.b.user, candidatos())] == [
        True, True, True, True
    ]  # fmt: skip


def test_r5_el_consumo_de_ia_y_la_auditoria_llevan_la_cuenta(mundo):
    """R5/R10: cada registro lleva quién lo originó; un rechazo de autenticación queda sin cuenta y no lo lista nadie."""
    mundo.cargar_b()
    assert {log.model for log in mundo.a.rutas.get_recent_api_logs()} == {"modelo-de-A"}
    assert {log.model for log in mundo.b.rutas.get_recent_api_logs()} == {"modelo-de-B"}
    assert mundo.a.rutas.get_token_usage_summary().total_requests == 1
    assert mundo.b.rutas.get_token_usage_summary().total_requests == 3

    rechazo = mundo.a.auditoria.log("auth", status="denied", error_message="token inválido")
    assert mundo.conn.execute("SELECT user_id FROM mcp_audit_logs WHERE id = ?;", (rechazo,)).fetchone()[0] is None
    assert {r["tool_name"] for r in mundo.a.auditoria.get_recent_logs(mundo.a.user)} == {"herramienta_de_A"}
    assert {r["tool_name"] for r in mundo.b.auditoria.get_recent_logs(mundo.b.user)} == {"herramienta_de_B"}


# ------------------------------------------------------------------ R7: siembras


def test_r7_sembrar_afecta_solo_a_la_cuenta_que_lo_pide(mundo):
    conn, a, b = mundo.conn, mundo.a, mundo.b
    plataformas_de_a = len(a.plataformas.list_all())
    tarjetas_de_a = len(a.fsrs.list_cards())
    rutas_de_a = len(a.rutas.get_roadmaps())

    assert seed_plataformas(conn, b.user) == len(PLATAFORMAS_SEMILLA)
    sembradas = seed_fsrs_deck(conn, b.user)
    plantillas = b.rutas.ensure_curated_templates()
    assert sembradas > 100 and len(plantillas) >= 4

    assert len(a.plataformas.list_all()) == plataformas_de_a
    assert len(a.fsrs.list_cards()) == tarjetas_de_a
    assert len(a.rutas.get_roadmaps()) == rutas_de_a
    assert {p.nombre for p in b.plataformas.list_all()} == {p["nombre"] for p in PLATAFORMAS_SEMILLA}
    assert len(b.fsrs.list_cards()) == len({(c.categoria, c.item_pregunta) for c in b.fsrs.list_cards()})
    assert len(b.rutas.get_roadmaps()) == len(plantillas)

    # Sembrar de nuevo no duplica, y la otra cuenta recibe su propio juego completo
    seed_plataformas(conn, b.user)
    cantidad_de_b = len(b.fsrs.list_cards())
    seed_fsrs_deck(conn, b.user)
    assert b.rutas.ensure_curated_templates() == []
    assert len(b.plataformas.list_all()) == len(PLATAFORMAS_SEMILLA)
    assert len(b.fsrs.list_cards()) == cantidad_de_b

    seed_plataformas(conn, a.user)
    seed_fsrs_deck(conn, a.user)
    assert len(a.rutas.ensure_curated_templates()) == len(plantillas)
    assert len(a.plataformas.list_all()) == plataformas_de_a + len(PLATAFORMAS_SEMILLA)
    assert len(a.fsrs.list_cards()) == tarjetas_de_a + cantidad_de_b
    assert len(b.fsrs.list_cards()) == cantidad_de_b


def test_r7_migrar_la_base_no_siembra(tmp_path):
    from aulento.db.schema import init_db

    conn = get_connection(tmp_path / "nueva.db")
    try:
        init_db(conn)
        for tabla in TABLAS_RAIZ:
            assert conn.execute(f"SELECT count(*) FROM {tabla};").fetchone()[0] == 0, tabla
        with pytest.raises(TypeError):
            init_db(conn, seed=True)
    finally:
        conn.close()


# ------------------------------------------------------------------ R6: sin cuenta no hay acceso

CONSTRUCCIONES = {
    "PlataformaRepository": lambda conn, u: PlataformaRepository(conn, u),
    "CursoRepository": lambda conn, u: CursoRepository(conn, u),
    "LibroRepository": lambda conn, u: LibroRepository(conn, u),
    "BloqueHorarioRepository": lambda conn, u: BloqueHorarioRepository(conn, u),
    "FSRSRepository": lambda conn, u: FSRSRepository(conn, u),
    "FocusRepository": lambda conn, u: FocusRepository(conn, u),
    "RoadmapRepository": lambda conn, u: RoadmapRepository(u),
    "ActivityTracker": lambda conn, u: ActivityTracker(u, conn=conn),
    "MacroFSRSRepository": lambda conn, u: MacroFSRSRepository(u, conn=conn),
    "MacroFSRSEngine": lambda conn, u: MacroFSRSEngine(u),
    "CourseNoteGenerator": lambda conn, u: CourseNoteGenerator(u, conn=conn),
    "MaterialNoteGenerator": lambda conn, u: MaterialNoteGenerator(u, conn=conn),
    "WeeklyDigestExporter": lambda conn, u: WeeklyDigestExporter(u, conn=conn),
    "MCPAuditRepository.get_recent_logs": lambda conn, u: MCPAuditRepository(conn).get_recent_logs(u),
    "seed_plataformas": lambda conn, u: seed_plataformas(conn, u),
    "seed_fsrs_deck": lambda conn, u: seed_fsrs_deck(conn, u),
    "calculate_retention_rate": lambda conn, u: calculate_retention_rate(conn, u),
    "calculate_streak": lambda conn, u: calculate_streak(conn, u),
    "get_full_fsrs_stats": lambda conn, u: get_full_fsrs_stats(conn, u),
    "get_student_evolution_metrics": lambda conn, u: get_student_evolution_metrics(conn, u),
    "diagnose_evolution": lambda conn, u: diagnose_evolution(conn, u),
    "OmniHarvester.check_duplicates": lambda conn, u: OmniHarvester().check_duplicates(conn, u, []),
    "OmniHarvester.commit_harvest": lambda conn, u: OmniHarvester().commit_harvest(conn, u, []),
    "OmniHarvester.harvest_from_materials": lambda conn, u: OmniHarvester().harvest_from_materials(u, query="x"),
}
SIN_CUENTA = (None, 0, -1, "1", 1.0, True)


@pytest.mark.parametrize("nombre", sorted(CONSTRUCCIONES))
def test_r6_sin_una_cuenta_valida_no_se_construye_ni_se_consulta(memory_db, nombre):
    """R6: None, cero, negativos, textos y booleanos se rechazan antes de tocar la base."""
    antes = _contenido(memory_db)
    for invalido in SIN_CUENTA:
        with pytest.raises(ValueError, match="cuenta"):
            CONSTRUCCIONES[nombre](memory_db, invalido)
    assert _contenido(memory_db) == antes


@pytest.mark.parametrize(
    "clase",
    [
        PlataformaRepository, CursoRepository, LibroRepository, BloqueHorarioRepository, FSRSRepository,
        FocusRepository, RoadmapRepository, ActivityTracker, MacroFSRSRepository, MacroFSRSEngine,
        CourseNoteGenerator, MaterialNoteGenerator, WeeklyDigestExporter,
    ],
)  # fmt: skip
def test_r6_la_cuenta_no_tiene_valor_por_defecto(clase):
    parametro = inspect.signature(clase).parameters["user_id"]
    assert parametro.default is inspect.Parameter.empty


@pytest.mark.parametrize(
    "funcion",
    [
        seed_plataformas, seed_fsrs_deck, calculate_retention_rate, calculate_streak, get_full_fsrs_stats,
        get_student_evolution_metrics, diagnose_evolution, OmniHarvester.check_duplicates, OmniHarvester.commit_harvest,
        OmniHarvester.harvest_from_materials, MCPAuditRepository.get_recent_logs,
    ],
)  # fmt: skip
def test_r6_las_funciones_exigen_la_cuenta(funcion):
    parametro = inspect.signature(funcion).parameters["user_id"]
    assert parametro.default is inspect.Parameter.empty


@pytest.mark.parametrize("servicio", [LessonStudio, RoadmapEngine, PrerequisiteAdvisor, LessonPromptBuilder])
def test_r6_los_servicios_exigen_un_repositorio_con_cuenta(servicio):
    assert inspect.signature(servicio).parameters["repo"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        servicio()
    with pytest.raises(ValueError, match="cuenta"):
        servicio(None)
    with pytest.raises(ValueError, match="cuenta"):
        servicio(repo=object())


def test_r6_las_funciones_que_registran_consumo_de_ia_exigen_el_repositorio():
    for funcion in (SyllabusIngestor.enhance_with_ai, pedir_tarjetas, cosechar):
        assert inspect.signature(funcion).parameters["repo"].default is inspect.Parameter.empty
    with pytest.raises(ValueError, match="cuenta"):
        SyllabusIngestor.enhance_with_ai([], "t", "rol", repo=None)
    with pytest.raises(ValueError, match="cuenta"):
        pedir_tarjetas(None, 1, None, NIVEL_DE_INGLES, repo=None)
    with pytest.raises(ValueError, match="cuenta"):
        cosechar(None, "x", 1, repo=None)


def test_r6_el_motor_de_retencion_no_acepta_el_repositorio_de_otra_cuenta(cuenta, otra_cuenta):
    with pytest.raises(ValueError, match="otra cuenta"):
        MacroFSRSEngine(cuenta, repository=MacroFSRSRepository(otra_cuenta))
    assert MacroFSRSEngine(cuenta, repository=MacroFSRSRepository(cuenta)).repo.user_id == cuenta


def test_la_cuenta_del_fixture_existe_y_es_la_de_los_pedidos_web(cuenta, otra_cuenta):
    conn = get_connection()
    try:
        ids = {fila[0] for fila in conn.execute("SELECT id FROM usuarios;")}
    finally:
        conn.close()
    assert {cuenta, otra_cuenta} <= ids and cuenta != otra_cuenta
    assert cuenta_en() == cuenta


# ------------------------------------------------------------------ inventario

REPOSITORIOS = (
    PlataformaRepository,
    CursoRepository,
    LibroRepository,
    BloqueHorarioRepository,
    FSRSRepository,
    FocusRepository,
    MCPAuditRepository,
    RoadmapRepository,
    MacroFSRSRepository,
    MacroFSRSEngine,
    ActivityTracker,
)

# Métodos que no leen por la cuenta ni reciben un identificador: altas. Cada uno nombra el test que lo cubre.
ALTAS = {
    "PlataformaRepository.create": "test_r5_todo_lo_que_crea_una_cuenta_queda_a_su_nombre",
    "LibroRepository.create": "test_r5_todo_lo_que_crea_una_cuenta_queda_a_su_nombre",
    "BloqueHorarioRepository.create": "test_r5_todo_lo_que_crea_una_cuenta_queda_a_su_nombre",
    "RoadmapRepository.create_roadmap": "test_r5_todo_lo_que_crea_una_cuenta_queda_a_su_nombre",
    "RoadmapRepository.log_api_usage": "test_r5_el_consumo_de_ia_y_la_auditoria_llevan_la_cuenta",
    "MCPAuditRepository.log": "test_r5_el_consumo_de_ia_y_la_auditoria_llevan_la_cuenta",
    "RoadmapRepository.ensure_curated_templates": "test_r7_sembrar_afecta_solo_a_la_cuenta_que_lo_pide",
    "RoadmapRepository.exigir_poder_crear_una_ruta": "test_consultar_si_se_puede_crear_una_ruta_pregunta_por_la_cuenta",
}


def test_consultar_si_se_puede_crear_una_ruta_pregunta_por_la_cuenta(mundo):
    """062: antes de generar una ruta con IA se consulta `puede()` por la cuenta del repositorio, no por otra."""
    from aulento.core import permisos

    vistas = []
    permisos.registrar_permisos([lambda *, user_id, accion, conn, **detalle: vistas.append((user_id, accion))])
    try:
        mundo.b.rutas.exigir_poder_crear_una_ruta()
    finally:
        permisos.limpiar_permisos()

    assert vistas == [(mundo.b.user, permisos.CREAR_RUTA)]


def _metodos_publicos(clase) -> set[str]:
    return {
        f"{clase.__name__}.{nombre}"
        for nombre, miembro in vars(clase).items()
        if not nombre.startswith("_") and callable(getattr(clase, nombre))
    }


def test_inventario_cada_metodo_publico_de_un_repositorio_esta_en_la_bateria():
    """Un método nuevo que no se sume a `LECTURAS`, `POR_IDENTIFICADOR` o `ALTAS` hace fallar este test."""
    publicos = set().union(*(_metodos_publicos(clase) for clase in REPOSITORIOS))
    cubiertos = {caso.split("#")[0] for caso in (*LECTURAS, *POR_IDENTIFICADOR)} | set(ALTAS)

    assert publicos - cubiertos == set(), "Métodos públicos sin prueba de aislamiento"
    de_repositorios = {c for c in cubiertos if c.split(".")[0] in {clase.__name__ for clase in REPOSITORIOS}}
    assert de_repositorios - publicos == set(), "La batería nombra métodos que ya no existen"
    for metodo, test in ALTAS.items():
        assert callable(globals().get(test)), f"{metodo}: el test {test} no existe"


def test_inventario_los_metodos_con_identificador_tienen_su_caso_ajeno():
    """Todo método público cuyo primer parámetro es un id (o un nombre) está en `POR_IDENTIFICADOR`."""
    nombres_de_id = {
        "id", "card_id", "roadmap_id", "ruta_id", "topic_id", "tema_id", "module_id", "version_id", "lesson",
        "nombre", "titulo", "title", "identifier", "session", "c", "categoria",
    }  # fmt: skip
    con_caso = {caso.split("#")[0] for caso in POR_IDENTIFICADOR}
    faltan = []
    for clase in REPOSITORIOS:
        for metodo in sorted(_metodos_publicos(clase)):
            parametros = [p for p in inspect.signature(getattr(clase, metodo.split(".")[1])).parameters if p != "self"]
            if parametros and parametros[0] in nombres_de_id and metodo not in con_caso:
                faltan.append(metodo)
    assert faltan == []
