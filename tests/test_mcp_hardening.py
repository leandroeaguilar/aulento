"""Tests de la feature 029: correcciones de la auditoría del servidor MCP."""

import os
import sqlite3
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import cuenta_en, token_mcp_de_prueba, vault_de_prueba
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from typer.testing import CliRunner

from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.repository import CursoRepository, LibroRepository
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.db.schema import init_db
from aulento.mcp import security
from aulento.mcp import server as mcp_server
from aulento.mcp.copilot import StudyCopilotEngine, identificar_por_nombre
from aulento.mcp.server import BearerAuthMiddleware, create_study_mcp_server
from aulento.models.curso import CursoCreate
from aulento.models.fsrs_card import FSRSCardCreate
from aulento.models.libro import EstadoLibro, LibroCreate
from aulento.models.roadmap import (
    EstadoTema,
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
)
from aulento.roadmap.lesson_studio import LessonStudio, nombre_seguro
from aulento.vault.rutas import (
    RutaFueraDelVaultError,
    VaultNoDisponibleError,
    fijar_vault_externo,
    vault_de_la_cuenta,
)

CLASE_1 = "# Memoria de trabajo\n\nContenido original de la clase.\n\n```cards-fsrs\nQ: ¿Qué es la memoria de trabajo?\nA: Un sistema de capacidad limitada.\n```\n"
CLASE_2 = "# Memoria de trabajo (v2)\n\nContenido nuevo.\n\n```cards-fsrs\nQ: ¿Quién propuso el modelo?\nA: Baddeley y Hitch.\n```\n"


@pytest.fixture
def db(tmp_path, operar_por_mcp):
    """Base con dos cursos, un libro en lectura y una ruta con un tema pendiente, de la cuenta que opera por MCP."""
    db_file = tmp_path / "hardening.db"
    conn = get_connection(db_file)
    init_db(conn)
    cuenta = operar_por_mcp(cuenta_en(db_file))
    cursos = CursoRepository(conn, cuenta)
    cursos.create(CursoCreate(plataforma_id=1, nombre_curso="BigQuery for Data Engineers", url_aula="https://coursera.org/learn/bigquery", progreso_pct=60.0))
    cursos.create(CursoCreate(plataforma_id=1, nombre_curso="Kubernetes Fundamentals", url_aula="https://coursera.org/learn/kubernetes", progreso_pct=10.0))
    LibroRepository(conn, cuenta).create(
        LibroCreate(titulo="Designing Data-Intensive Applications", capitulo_actual=2, total_capitulos=12, pagina_actual=40, total_paginas=600)
    )
    conn.close()
    ruta = RoadmapRepository(cuenta, db_file).create_roadmap(
        RoadmapCreate(
            titulo="Psicología Cognitiva",
            descripcion="Ruta de prueba",
            nivel_objetivo="Intermedio",
            categoria="psicologia",
            modulos=[
                RoadmapModuleCreate(
                    titulo="Memoria",
                    orden=1,
                    temas=[RoadmapTopicCreate(titulo="Memoria de trabajo", orden=1, estado=EstadoTema.PENDIENTE)],
                )
            ],
        )
    )
    return db_file, ruta.id, ruta.modulos[0].temas[0].id


def q(db_file, sql, params=()):
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def cursos(db_file):
    return {r["nombre_curso"]: r["progreso_pct"] for r in q(db_file, "SELECT nombre_curso, progreso_pct FROM cursos_externos")}


def sesiones(db_file):
    return [r["duracion_minutos"] for r in q(db_file, "SELECT duracion_minutos FROM sesiones_estudio ORDER BY id")]


def libro(db_file, titulo="Designing Data-Intensive Applications"):
    return q(db_file, "SELECT pagina_actual, capitulo_actual, estado FROM libros_lectura WHERE titulo = ?", (titulo,))[0]


async def llamar(server, nombre, args):
    res = await server.call_tool(nombre, args)
    return res.content[0].text


# ---------------------------------------------------------------- R1: sesiones


@pytest.mark.parametrize(
    "instruccion",
    ["¿Cuál es mi horario de hoy?", "Mostrame la agenda de hoy", "¿Cómo funciona la técnica pomodoro?", "Quiero una sesión de estudio mañana"],
)
def test_r1_preguntar_por_la_agenda_no_registra_sesion(db, instruccion):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert sesiones(db_file) == []
    assert not any("Sesión registrada" in a for a in res.actions_taken)


def test_r1_con_minutos_registra_esa_duracion(db):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Estudié 45 min de Apache Beam")
    assert sesiones(db_file) == [45]
    assert any("45 minutos" in a for a in res.actions_taken)


# ---------------------------------------------------------------- R2: cursos


def test_r2_actualiza_el_curso_nombrado_y_no_otro(db):
    db_file, _, _ = db
    # "BigQuery…" es el primero de la lista (mayor avance): antes se actualizaba ese
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Llevo 30% de avance en el curso de Kubernetes")
    assert cursos(db_file) == {"BigQuery for Data Engineers": 60.0, "Kubernetes Fundamentals": 30.0}
    assert "Kubernetes Fundamentals" in res.actions_taken[0]


def test_r2_actualiza_por_url_del_aula(db):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan("Completé el 80% del curso https://coursera.org/learn/kubernetes")
    assert cursos(db_file)["Kubernetes Fundamentals"] == 80.0
    assert cursos(db_file)["BigQuery for Data Engineers"] == 60.0


@pytest.mark.parametrize(
    ("instruccion", "aviso"),
    [
        ("Llevo 50% de avance en el curso de Rust", "No se pudo saber a qué curso"),
        ("Llevo 50% de avance en el curso", "No se pudo saber a qué curso"),
        ("Llevo 50% de avance en el curso de BigQuery y Kubernetes", "más de un curso"),
        ("Llevo 150% de avance en el curso de Kubernetes", "no es válido"),
    ],
)
def test_r2_ante_la_duda_no_escribe_y_las_demas_acciones_siguen(db, instruccion, aviso):
    db_file, _, _ = db
    antes = cursos(db_file)
    res = StudyCopilotEngine(db_path=db_file).execute_plan(f"Estudié 20 min. {instruccion}")
    assert cursos(db_file) == antes
    assert any(aviso in w for w in res.warnings), res.warnings
    assert sesiones(db_file) == [20]


def test_r2_curso_sin_porcentaje_no_escribe(db):
    db_file, _, _ = db
    antes = cursos(db_file)
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Tengo que pagar el curso de Kubernetes, ya completé el pago")
    assert cursos(db_file) == antes
    assert res.actions_taken == []


# ---------------------------------------------------------------- R3: lectura


@pytest.mark.parametrize("instruccion", ["¿Qué libro me recomendás leer?", "Leí sobre redes neuronales", "Empecé un libro de 300 páginas"])
def test_r3_sin_pagina_ni_capitulo_no_escribe(db, instruccion):
    db_file, _, _ = db
    antes = libro(db_file)
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert libro(db_file) == antes
    assert not any("Lectura actualizada" in a for a in res.actions_taken)


def test_r3_identifica_el_libro_por_su_titulo(db):
    db_file, _, _ = db
    conn = get_connection(db_file)
    LibroRepository(conn, cuenta_en(db_file)).create(LibroCreate(titulo="Clean Architecture", total_capitulos=30, total_paginas=400, pagina_actual=10))
    conn.close()
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Leí 25 páginas de Clean Architecture")
    assert libro(db_file, "Clean Architecture")["pagina_actual"] == 35
    assert libro(db_file)["pagina_actual"] == 40
    assert "Clean Architecture" in res.actions_taken[0]


def test_r3_varios_libros_en_lectura_sin_nombrar_ninguno_advierte(db):
    db_file, _, _ = db
    conn = get_connection(db_file)
    LibroRepository(conn, cuenta_en(db_file)).create(LibroCreate(titulo="Clean Architecture", total_capitulos=30, total_paginas=400, pagina_actual=10))
    conn.close()
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Voy por la página 90")
    assert libro(db_file)["pagina_actual"] == 40
    assert libro(db_file, "Clean Architecture")["pagina_actual"] == 10
    assert any("a qué libro" in w for w in res.warnings)


def test_r3_un_solo_libro_en_lectura_se_usa_sin_nombrarlo(db):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan("Voy por la página 90 del libro")
    assert libro(db_file)["pagina_actual"] == 90


def test_r3_pagina_fuera_de_rango_advierte_sin_guardar(db):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Voy por la página 9999 del libro")
    assert libro(db_file) == {"pagina_actual": 40, "capitulo_actual": 2, "estado": "leyendo"}
    assert any("supera el total" in w for w in res.warnings)


@pytest.mark.parametrize(
    ("instruccion", "no_debe"),
    [
        ("Quiero disfrutar el fin de semana", "ROADMAP_QUERY"),
        ("¿Se puede exportar el vault?", "FSRS_STATUS"),
        ("Tengo que pagar la cuenta", "READING_UPDATE"),
        ("Voy a elegir un tema", "READING_UPDATE"),
    ],
)
def test_r3_una_palabra_dentro_de_otra_no_activa_la_intencion(instruccion, no_debe):
    intents = StudyCopilotEngine(db_path=":memory:").classify_intents(instruccion)
    assert no_debe not in [i.name for i in intents]


def test_identificar_por_nombre():
    candidatos = [("a", "BigQuery for Data Engineers"), ("b", "Kubernetes Fundamentals")]
    assert identificar_por_nombre("el curso de bigquery", candidatos) == ("a", False)
    assert identificar_por_nombre("el curso de data", candidatos) == (None, False)
    assert identificar_por_nombre("bigquery y kubernetes", candidatos) == (None, True)
    assert identificar_por_nombre("Kubernetes Fundamentals, no BigQuery", candidatos) == ("b", False)


# ---------------------------------------------------------------- R4–R8: clases


@pytest.fixture
def clases(db, tmp_path, monkeypatch):
    db_file, ruta_id, tema_id = db
    return create_study_mcp_server(db_path=db_file), db_file, ruta_id, tema_id, vault_de_prueba(db_file)


def clase(db_file, tema_id):
    return q(db_file, "SELECT contenido_markdown, flashcards_json FROM ruta_clases WHERE tema_id = ?", (tema_id,))


def estado_tema(db_file, tema_id):
    return q(db_file, "SELECT estado FROM ruta_temas WHERE id = ?", (tema_id,))[0]["estado"]


@pytest.mark.anyio
async def test_r4_sin_overwrite_no_reemplaza_nada(clases):
    server, db_file, _, tema_id, vault = clases
    primera = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})
    assert "guardada exitosamente" in primera
    nota = next(vault.rglob("*.md"))
    antes = (clase(db_file, tema_id), q(db_file, "SELECT item_pregunta FROM fsrs_items ORDER BY id"), nota.read_bytes())
    conn = sqlite3.connect(str(db_file))
    conn.execute("UPDATE ruta_temas SET estado = 'en_progreso' WHERE id = ?", (tema_id,))
    conn.commit()
    conn.close()

    segunda = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_2})

    assert "ya tiene una clase" in segunda and "overwrite=true" in segunda
    assert (clase(db_file, tema_id), q(db_file, "SELECT item_pregunta FROM fsrs_items ORDER BY id"), nota.read_bytes()) == antes
    assert estado_tema(db_file, tema_id) == "en_progreso"
    assert len(list(vault.rglob("*.md"))) == 1


@pytest.mark.anyio
async def test_r4_con_overwrite_reemplaza(clases):
    server, db_file, _, tema_id, vault = clases
    await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})
    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_2, "overwrite": True})
    assert "reemplazada exitosamente" in res
    assert "Contenido nuevo." in clase(db_file, tema_id)[0]["contenido_markdown"]
    # La nota no tenía cambios a mano: se reescribe sin dejar respaldo
    notas = list(vault.rglob("*.md"))
    assert len(notas) == 1 and "Contenido nuevo." in notas[0].read_text(encoding="utf-8")
    assert "Respaldo" not in res


@pytest.mark.anyio
async def test_r5_la_nota_editada_a_mano_queda_respaldada(clases):
    server, _, _, tema_id, vault = clases
    await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})
    nota = next(vault.rglob("*.md"))
    nota.write_text(nota.read_text(encoding="utf-8") + "\n\nMIS APUNTES A MANO\n", encoding="utf-8")

    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_2, "overwrite": True})

    respaldos = [p for p in vault.rglob("*.md") if "(respaldo " in p.name]
    assert len(respaldos) == 1
    assert respaldos[0].parent == nota.parent
    assert "MIS APUNTES A MANO" in respaldos[0].read_text(encoding="utf-8")
    assert "Contenido nuevo." in nota.read_text(encoding="utf-8")
    # La respuesta nombra el respaldo por su ruta dentro del vault, no por la del disco del servidor
    assert respaldos[0].relative_to(vault).as_posix() in res
    assert str(vault) not in res


@pytest.mark.anyio
@pytest.mark.parametrize("previo", ["pendiente", "en_progreso"])
async def test_r6_mark_completed_false_conserva_el_estado(clases, previo):
    server, db_file, _, tema_id, _ = clases
    conn = sqlite3.connect(str(db_file))
    conn.execute("UPDATE ruta_temas SET estado = ? WHERE id = ?", (previo, tema_id))
    conn.commit()
    conn.close()
    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1, "mark_completed": False})
    assert estado_tema(db_file, tema_id) == previo
    assert "Sin cambios" in res


@pytest.mark.anyio
async def test_r6_mark_completed_true_completa_el_tema(clases):
    server, db_file, _, tema_id, _ = clases
    await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})
    assert estado_tema(db_file, tema_id) == "completado"


def _fijar_un_vault_externo_y_borrarlo(db_file, carpeta: Path) -> Path:
    """Deja a la cuenta de prueba con un vault externo fijado cuya carpeta ya no existe."""
    carpeta.mkdir()
    cuenta = cuenta_en(db_file)
    conn = get_connection(db_file)
    try:
        fijar_vault_externo(conn, cuenta, carpeta)
    finally:
        conn.close()
    carpeta.rmdir()
    return carpeta


def test_r7_vault_configurado_inexistente_falla_sin_usar_otro(db, tmp_path, directorio_y_clave_de_prueba):
    db_file, _, _ = db
    cuenta = cuenta_en(db_file)
    externo = _fijar_un_vault_externo_y_borrarlo(db_file, tmp_path / "no-existe")

    conn = get_connection(db_file)
    try:
        with pytest.raises(VaultNoDisponibleError, match="ya no existe"):
            vault_de_la_cuenta(conn, cuenta)
    finally:
        conn.close()

    assert not externo.exists()
    assert not (directorio_y_clave_de_prueba / "usuarios" / str(cuenta) / "vault").exists(), "no cae al vault propio"


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [("..", "Sin título"), (".", "Sin título"), ("...", "Sin título"), ("", "Sin título"), ("  ", "Sin título"), ("../x", "..x"), ("a/b\\c:d", "abcd"), ("Tema.", "Tema"), ("Psicología Cognitiva", "Psicología Cognitiva")],
)
def test_r7_nombre_seguro(nombre, esperado):
    assert nombre_seguro(nombre) == esperado


@pytest.mark.anyio
@pytest.mark.parametrize(("titulo_ruta", "titulo_tema"), [("..", "Memoria de trabajo"), ("Psicología", ".."), ("..", "..")])
async def test_r7_titulos_de_puntos_quedan_dentro_de_cursos(clases, titulo_ruta, titulo_tema):
    server, db_file, ruta_id, tema_id, vault = clases
    conn = sqlite3.connect(str(db_file))
    conn.execute("UPDATE rutas_aprendizaje SET titulo = ? WHERE id = ?", (titulo_ruta, ruta_id))
    conn.execute("UPDATE ruta_temas SET titulo = ? WHERE id = ?", (titulo_tema, tema_id))
    conn.commit()
    conn.close()

    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})

    assert "guardada exitosamente" in res
    cursos_dir = (vault / "04 Knowledge" / "Cursos").resolve()
    notas = list(vault.rglob("*.md"))
    assert len(notas) == 1
    assert notas[0].resolve().parent.parent == cursos_dir


def test_r7_la_ruta_se_valida_antes_de_escribir(db, tmp_path, monkeypatch):
    db_file, _, tema_id = db
    vault = tmp_path / "vault"
    vault.mkdir()
    studio = LessonStudio(repo=RoadmapRepository(cuenta_en(db_file), db_file), vault_path=vault)
    lesson = studio.import_external_lesson(tema_id, CLASE_1)
    monkeypatch.setattr("aulento.roadmap.lesson_studio.nombre_seguro", lambda n: "..")
    with pytest.raises(RutaFueraDelVaultError):
        studio.export_lesson_to_vault(lesson.id)
    assert list(vault.rglob("*.md")) == []


@pytest.mark.anyio
async def test_r8_si_falla_el_vault_dice_lo_que_quedo_guardado(clases, tmp_path, monkeypatch):
    server, db_file, _, tema_id, vault_propio = clases
    _fijar_un_vault_externo_y_borrarlo(db_file, tmp_path / "no-existe")
    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})
    assert "Clase guardada, pero no se pudo sincronizar con el Vault" in res
    assert "Tarjetas FSRS v5 extraídas:** 1" in res
    assert "no existe" in res
    assert list(vault_propio.rglob("*.md")) == [], "la nota no se escribe en otro vault"
    assert len(clase(db_file, tema_id)) == 1
    assert estado_tema(db_file, tema_id) == "completado"


# ---------------------------------------------------------------- R9–R11


@pytest.mark.anyio
@pytest.mark.parametrize("args", [{"current_page": -50}, {"current_page": 9999}, {"current_chapter": 99}, {"current_chapter": -1}, {"total_pages": 10}])
async def test_r9_progreso_invalido_no_se_guarda(db, args):
    db_file, _, _ = db
    server = create_study_mcp_server(db_path=db_file)
    res = await llamar(server, "study_update_book_progress", {"book_identifier": "Designing Data", **args})
    assert res.startswith("Error")
    assert libro(db_file) == {"pagina_actual": 40, "capitulo_actual": 2, "estado": "leyendo"}
    # El libro sigue siendo legible para el modelo
    assert "Designing Data-Intensive Applications" in await llamar(server, "study_list_books", {})


@pytest.mark.anyio
async def test_r9_progreso_valido_se_guarda(db):
    db_file, _, _ = db
    server = create_study_mcp_server(db_path=db_file)
    res = await llamar(server, "study_update_book_progress", {"book_identifier": "Designing Data", "current_page": 120, "status": "PAUSADO"})
    assert "actualizada exitosamente" in res
    assert libro(db_file) == {"pagina_actual": 120, "capitulo_actual": 2, "estado": "pausado"}


@pytest.mark.anyio
async def test_r10_status_invalido_se_rechaza(db):
    db_file, _, _ = db
    server = create_study_mcp_server(db_path=db_file)
    res = await llamar(server, "study_update_book_progress", {"book_identifier": "Designing Data", "current_page": 50, "status": "terminado"})
    assert "no es válido" in res
    assert libro(db_file)["pagina_actual"] == 40

    res = await llamar(server, "study_update_course_progress", {"course_identifier": "Kubernetes", "progreso_pct": 55, "status": "terminado"})
    assert "no es válido" in res
    assert cursos(db_file)["Kubernetes Fundamentals"] == 10.0


def _tarjeta(db_file, categoria, pregunta, vence):
    conn = get_connection(db_file)
    repo = FSRSRepository(conn, cuenta_en(db_file))
    card = repo.create_card(FSRSCardCreate(categoria=categoria, item_pregunta=pregunta, respuesta_esperada="r"))
    repo.update_card_fsrs(card.id, 1, 0, 1.0, 5.0, vence.isoformat(), vence.isoformat(), 1, 0)
    conn.close()


@pytest.mark.anyio
async def test_r11_la_categoria_trae_sus_vencidas_aunque_haya_otras_mas_vencidas(db):
    db_file, _, _ = db
    ahora = datetime.now(UTC)
    for i in range(8):
        _tarjeta(db_file, "b2_tech_data_ai", f"Inglés {i}", ahora - timedelta(days=30 - i))
    _tarjeta(db_file, "roadmap_1", "Vencida de la ruta", ahora - timedelta(hours=1))
    _tarjeta(db_file, "roadmap_1", "Futura de la ruta", ahora + timedelta(days=30))
    # Un mazo de ruta solo admite tarjetas si la ruta es de la cuenta: la 10 se crea para ese mazo
    conn = get_connection(db_file)
    conn.execute("INSERT INTO rutas_aprendizaje (id, user_id, titulo) VALUES (10, ?, 'Otra ruta');", (cuenta_en(db_file),))
    conn.commit()
    conn.close()
    _tarjeta(db_file, "roadmap_10", "De otra ruta", ahora - timedelta(hours=1))
    server = create_study_mcp_server(db_path=db_file)

    res = await llamar(server, "study_get_fsrs_due_cards", {"category": "roadmap_1", "limit": 5})

    assert "vencidas para repaso (1)" in res
    assert "Vencida de la ruta" in res
    assert "Futura de la ruta" not in res and "De otra ruta" not in res and "Inglés" not in res


@pytest.mark.anyio
async def test_r11_sin_vencidas_ofrece_practica_extra_y_lo_dice(db):
    db_file, _, _ = db
    ahora = datetime.now(UTC)
    _tarjeta(db_file, "roadmap_1", "Futura de la ruta", ahora + timedelta(days=30))
    _tarjeta(db_file, "b2_tech_data_ai", "Inglés vencida", ahora - timedelta(days=3))
    server = create_study_mcp_server(db_path=db_file)

    res = await llamar(server, "study_get_fsrs_due_cards", {"category": "roadmap_1"})
    assert "No hay tarjetas vencidas hoy en la categoría 'roadmap_1'" in res
    assert "Práctica extra" in res and "Futura de la ruta" in res
    assert "Inglés vencida" not in res

    res = await llamar(server, "study_get_fsrs_due_cards", {"category": "no_existe"})
    assert "No hay tarjetas de memoria registradas en la categoría 'no_existe'" in res


# ---------------------------------------------------------------- R12–R14: conexión

runner = CliRunner()


def test_r12_stdio_no_escribe_en_la_salida_estandar(monkeypatch, cuenta):
    llamadas = []
    monkeypatch.setattr("aulento.cli.mcp_commands.run_stdio_server", lambda **kw: llamadas.append(kw))
    res = runner.invoke(cli, ["mcp", "serve", "--read-only"])
    assert res.exit_code == 0
    assert llamadas == [{"user_id": cuenta, "read_only": True}]
    assert res.stdout == ""
    assert "READ-ONLY" in res.stderr


def test_r13_token_no_ascii_es_invalido_y_no_falla():
    assert security.resolver_token_mcp("ñandú") is None
    assert security.resolver_token_mcp("Bearer ñ") is None
    assert security.resolver_token_mcp(token_mcp_de_prueba()).id == cuenta_en()


def test_r13_el_middleware_responde_401_con_token_no_ascii():
    app = Starlette(routes=[Route("/sse", lambda request: PlainTextResponse("ok"))])
    app.add_middleware(BearerAuthMiddleware)
    client = TestClient(app, raise_server_exceptions=True)
    token = token_mcp_de_prueba()

    assert client.get("/sse", headers=[(b"authorization", "Bearer ñandú".encode())]).status_code == 401
    assert client.get("/sse").status_code == 401
    assert client.get("/sse", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_r13_el_arranque_sse_no_muestra_ningun_token_ni_registra_accesos(monkeypatch, capsys):
    capturado = {}
    monkeypatch.setattr(mcp_server.uvicorn, "run", lambda app, **kw: capturado.update(kw))
    token = token_mcp_de_prueba()
    try:
        mcp_server.run_sse_server(port=8123)
    finally:
        security.set_audit_transport("stdio")
    salida = capsys.readouterr()
    assert token not in salida.out and token not in salida.err
    # Ya no hay un token del servidor que mostrar ni que guardar en un archivo: se crea uno por cuenta
    assert "mcp token create" in salida.out
    assert list(Path(os.environ["AULENTO_HOME"]).iterdir()) == []
    assert capturado["access_log"] is False
    assert capturado["host"] == "127.0.0.1"


def test_r14_allow_remote_advierte(monkeypatch):
    llamadas = []
    monkeypatch.setattr("aulento.cli.mcp_commands.run_sse_server", lambda **kw: llamadas.append(kw))
    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse", "--allow-remote", "--insecure-http"], env={"COLUMNS": "300"})
    assert res.exit_code == 0
    assert llamadas[0]["host"] == "0.0.0.0"
    assert "sin cifrar" in res.stdout and "Solo el token" in res.stdout

    res = runner.invoke(cli, ["mcp", "serve", "--transport", "sse"], env={"COLUMNS": "300"})
    assert "sin cifrar" not in res.stdout


# ---------------------------------------------------------------- R15–R18


def auditoria(db_file):
    return q(db_file, "SELECT tool_name, transport, status FROM mcp_audit_logs ORDER BY id")


@pytest.mark.anyio
async def test_r15_las_herramientas_de_materiales_quedan_auditadas(db):
    from aulento.core.materiales import AlmacenDeMateriales

    db_file, _, _ = db
    almacen = AlmacenDeMateriales.con_conexion_propia(cuenta_en(db_file), db_file)
    material = almacen.guardar("BigQuery.md", b"BigQuery y Dremel")
    server = create_study_mcp_server(db_path=db_file)
    await llamar(server, "materials_search", {"query": "BigQuery"})
    await llamar(server, "materials_search", {"query": "termodinamica"})
    await llamar(server, "materials_read", {"material_id": material["id"]})
    await llamar(server, "materials_read", {"material_id": 987654})

    assert [(f["tool_name"], f["status"]) for f in auditoria(db_file)] == [
        ("materials_search", "success"),
        ("materials_search", "success"),
        ("materials_read", "success"),
        ("materials_read", "error"),
    ]


@pytest.mark.anyio
async def test_r15_la_auditoria_lleva_el_transporte_real(db):
    db_file, _, _ = db
    server = create_study_mcp_server(db_path=db_file)
    await llamar(server, "study_list_books", {})
    security.set_audit_transport("sse")
    try:
        await llamar(server, "study_list_books", {})
        await llamar(server, "materials_search", {"query": "x"})
    finally:
        security.set_audit_transport("stdio")
    assert [f["transport"] for f in auditoria(db_file)] == ["stdio", "sse", "sse"]


@pytest.mark.anyio
async def test_r16_sin_db_path_todo_usa_la_base_configurada_y_crea_el_esquema(tmp_path, monkeypatch, operar_por_mcp):
    db_file = tmp_path / "nueva" / "configurada.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    server = create_study_mcp_server()
    operar_por_mcp(cuenta_en(db_file))

    assert "añadido" in await llamar(server, "study_add_book", {"title": "Libro en la base configurada", "total_pages": 100})
    assert "Curso registrado" in await llamar(
        server, "study_add_course", {"platform_name": "Plataforma X", "course_name": "Curso X", "url_aula": "https://example.com/x"}
    )
    assert "Tarjeta FSRS creada" in await llamar(server, "study_create_flashcard", {"question": "P", "answer": "R"})
    assert "registrada" in await llamar(server, "study_log_study_session", {"activity_type": "curso", "duration_minutes": 15})
    assert "Libro en la base configurada" in await llamar(server, "study_copilot", {"instruction": "resumen"})
    await llamar(server, "study_list_roadmaps", {})
    recurso = await server.read_resource("study://books/reading")
    assert "Libro en la base configurada" in str(recurso)

    assert q(db_file, "SELECT titulo FROM libros_lectura") == [{"titulo": "Libro en la base configurada"}]
    assert q(db_file, "SELECT nombre_curso FROM cursos_externos") == [{"nombre_curso": "Curso X"}]
    assert len(q(db_file, "SELECT id FROM fsrs_items")) == 1
    assert sesiones(db_file) == [15]
    assert {f["tool_name"] for f in auditoria(db_file)} >= {
        "study_add_book", "study_add_course", "study_create_flashcard", "study_log_study_session", "study_copilot",
    }


def test_r18_pyproject_exige_mcp_2():
    datos = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    requisito = next(d for d in datos["project"]["dependencies"] if d.replace(" ", "").startswith("mcp>="))
    assert int(requisito.split(">=")[1].split(".")[0]) >= 2


# ---------------------------------------------------------------- hallazgos de la revisión de código


@pytest.mark.parametrize(
    "instruccion",
    [
        "¿De qué trata el capítulo 7 de Designing Data-Intensive Applications?",
        "¿Cuántas páginas tiene el capítulo 5?",
        "Terminé el capítulo 3 del curso de Kubernetes Fundamentals",
        "Estudié 45 minutos y leí la página 10 de mis notas de Kubernetes",
        "Voy por la página 300 de El Quijote",
        "El capítulo 9 del libro es el más largo",
    ],
)
def test_r3_preguntas_y_menciones_de_otra_cosa_no_mueven_el_libro(db, instruccion):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert libro(db_file) == {"pagina_actual": 40, "capitulo_actual": 2, "estado": "leyendo"}
    assert not any("Lectura actualizada" in a for a in res.actions_taken)


def test_r3_libro_nombrado_y_no_reconocido_no_cae_al_libro_en_lectura(db):
    db_file, _, _ = db
    conn = get_connection(db_file)
    LibroRepository(conn, cuenta_en(db_file)).create(LibroCreate(titulo="Go", total_capitulos=10, total_paginas=200, pagina_actual=5, estado=EstadoLibro.PAUSADO))
    LibroRepository(conn, cuenta_en(db_file)).create(LibroCreate(titulo="DDD", total_capitulos=10, total_paginas=200, pagina_actual=5, estado=EstadoLibro.PAUSADO))
    conn.close()
    engine = StudyCopilotEngine(db_path=db_file)

    # Un título de tres letras se reconoce
    engine.execute_plan("Leí 20 páginas de DDD")
    assert libro(db_file, "DDD")["pagina_actual"] == 25
    assert libro(db_file)["pagina_actual"] == 40

    # Uno de dos letras no se puede reconocer: se advierte en vez de mover el libro en lectura
    res = engine.execute_plan("Leí 20 páginas de Go")
    assert libro(db_file, "Go")["pagina_actual"] == 5
    assert libro(db_file)["pagina_actual"] == 40
    assert any("no coincide con ningún libro" in w for w in res.warnings)


def test_r3_desde_hasta_toma_la_ultima_pagina(db):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan("Leí desde la página 40 hasta la página 90 del libro")
    assert libro(db_file)["pagina_actual"] == 90


@pytest.mark.parametrize(("instruccion", "pagina"), [("Leí unas 20 páginas", 60), ("Hoy leí otras 5 págs del libro", 45), ("Llegué a la pág. 120 del libro.", 120)])
def test_r3_formas_habituales_de_decir_el_avance(db, instruccion, pagina):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert libro(db_file)["pagina_actual"] == pagina


def test_r1_minutos_con_palabras_intermedias(db):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan("Estudié por 45 minutos")
    assert sesiones(db_file) == [45]


def test_r2_porcentaje_con_coma_decimal(db):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan("Avancé al 50,5% el curso de Kubernetes Fundamentals")
    assert cursos(db_file)["Kubernetes Fundamentals"] == 50.5


@pytest.mark.parametrize(
    ("instruccion", "aviso"),
    [
        ("Completé el 30% del libro y el curso Kubernetes Fundamentals va 80%", "más de un porcentaje"),
        ("El curso https://coursera.org/learn/otro va 70%, es mejor que el de bigquery", "La URL indicada no coincide"),
    ],
)
def test_r2_porcentaje_o_url_dudosos_no_escriben(db, instruccion, aviso):
    db_file, _, _ = db
    antes = cursos(db_file)
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert cursos(db_file) == antes
    assert any(aviso in w for w in res.warnings), res.warnings


@pytest.mark.anyio
async def test_r5_nota_propia_en_el_destino_de_un_tema_sin_clase_queda_respaldada(clases):
    server, _, _, tema_id, vault = clases
    destino = vault / "04 Knowledge" / "Cursos" / "Psicología Cognitiva" / "Memoria de trabajo.md"
    destino.parent.mkdir(parents=True)
    destino.write_text("NOTA PROPIA ANTERIOR AL SISTEMA\n", encoding="utf-8")

    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})

    respaldos = [p for p in vault.rglob("*.md") if "(respaldo " in p.name]
    assert len(respaldos) == 1
    assert respaldos[0].read_text(encoding="utf-8") == "NOTA PROPIA ANTERIOR AL SISTEMA\n"
    assert "Contenido original de la clase." in destino.read_text(encoding="utf-8")
    assert "Respaldo" in res


@pytest.mark.anyio
async def test_r5_dos_temas_con_el_mismo_titulo_no_se_pisan_sin_respaldo(clases):
    server, db_file, ruta_id, tema_id, vault = clases
    conn = sqlite3.connect(str(db_file))
    modulo = conn.execute("INSERT INTO ruta_modulos (ruta_id, titulo, orden) VALUES (?, 'Otro módulo', 2)", (ruta_id,)).lastrowid
    gemelo = conn.execute("INSERT INTO ruta_temas (modulo_id, titulo, orden) VALUES (?, 'Memoria de trabajo', 1)", (modulo,)).lastrowid
    conn.commit()
    conn.close()

    await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})
    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": gemelo, "markdown_content": CLASE_2})

    respaldos = [p for p in vault.rglob("*.md") if "(respaldo " in p.name]
    assert len(respaldos) == 1
    assert "Contenido original de la clase." in respaldos[0].read_text(encoding="utf-8")
    assert "Respaldo" in res


@pytest.mark.anyio
async def test_r5_markdown_con_crlf_no_genera_respaldos_falsos(clases):
    server, _, _, tema_id, vault = clases
    con_crlf = CLASE_1.replace("\n", "\r\n")
    await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": con_crlf})
    nota = next(vault.rglob("*.md"))
    assert b"\r\r\n" not in nota.read_bytes()

    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": con_crlf, "overwrite": True})

    assert "Respaldo" not in res
    assert len(list(vault.rglob("*.md"))) == 1


@pytest.mark.anyio
async def test_r6_un_fallo_de_las_tarjetas_no_deja_el_tema_completado(clases, monkeypatch):
    server, db_file, _, tema_id, _ = clases

    def falla(self, lesson_id):
        raise RuntimeError("base de tarjetas no disponible")

    monkeypatch.setattr(LessonStudio, "export_flashcards_to_fsrs", falla)
    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1, "mark_completed": False})
    assert estado_tema(db_file, tema_id) == "pendiente"
    assert "FALLÓ (base de tarjetas no disponible)" in res


# ---------------------------------------------------------------- hallazgos de la auditoría de la spec


@pytest.mark.parametrize(
    ("instruccion", "aviso"),
    [
        ("Llevo -5% de avance en el curso de Kubernetes", "no es válido"),
        ("Voy 30% en Rust Avanzado", "No se pudo saber a qué curso"),
    ],
)
def test_r2_porcentaje_negativo_o_curso_desconocido_advierten(db, instruccion, aviso):
    db_file, _, _ = db
    antes = cursos(db_file)
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert cursos(db_file) == antes
    assert any(aviso in w for w in res.warnings), res.warnings


@pytest.mark.parametrize(
    "instruccion",
    [
        "Estudié 20 min con 80% de batería, después sigo el curso de Kubernetes",
        "En el curso de kubernetes vi 3% de teoría; ¿qué es un pod?",
        "Completé el 30% del libro",
    ],
)
def test_r2_un_porcentaje_que_no_es_avance_del_curso_no_escribe(db, instruccion):
    db_file, _, _ = db
    antes = cursos(db_file)
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert cursos(db_file) == antes
    assert not any("Curso actualizado" in a for a in res.actions_taken)


def test_r2_curso_por_nombre_sin_la_palabra_curso(db):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan("Voy 30% en Kubernetes Fundamentals")
    assert cursos(db_file)["Kubernetes Fundamentals"] == 30.0


def test_r3_mas_paginas_que_las_que_quedan_se_avisa(db):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Leí 9999 páginas del libro")
    assert libro(db_file)["pagina_actual"] == 600
    assert any("superan lo que queda" in w for w in res.warnings)


@pytest.mark.anyio
async def test_r4_contenido_vacio_no_guarda(clases):
    server, db_file, _, tema_id, vault = clases
    res = await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": "  \n "})
    assert res.startswith("Error")
    assert clase(db_file, tema_id) == []
    assert estado_tema(db_file, tema_id) == "pendiente"
    assert list(vault.rglob("*.md")) == []


def test_r9_la_web_rechaza_progreso_invalido_y_no_pasa_de_la_ultima_pagina():
    from aulento.web.app import create_app

    client = TestClient(create_app())
    creado = client.post("/api/books", json={"titulo": "Libro Web", "total_capitulos": 10, "total_paginas": 100, "pagina_actual": 95})
    assert creado.status_code in (200, 201), creado.text
    book_id = creado.json()["id"]

    malo = client.patch(f"/api/books/{book_id}/progress", json={"pagina_actual": 500})
    assert malo.status_code in (400, 422)
    assert client.get("/api/books").status_code == 200

    avance = client.post(f"/api/books/{book_id}/advance-pages?pages=50")
    assert avance.status_code == 200
    assert avance.json()["pagina_actual"] == 100


@pytest.mark.anyio
async def test_r11_respeta_el_limite_dentro_de_la_categoria(db):
    db_file, _, _ = db
    ahora = datetime.now(UTC)
    for i in range(7):
        _tarjeta(db_file, "roadmap_1", f"Ruta {i}", ahora - timedelta(days=i + 1))
    server = create_study_mcp_server(db_path=db_file)
    res = await llamar(server, "study_get_fsrs_due_cards", {"category": "roadmap_1", "limit": 3})
    assert "vencidas para repaso (3)" in res
    assert res.count("Card ID") == 3
    res = await llamar(server, "study_get_fsrs_due_cards", {"category": "roadmap_1", "limit": 0})
    assert res.count("Card ID") == 1


def test_r12_stdio_real_la_primera_linea_de_stdout_es_del_protocolo(cuenta):
    import json
    import subprocess
    import sys

    pedido = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
    }
    proc = subprocess.run(
        [sys.executable, "-m", "aulento", "mcp", "serve"],
        input=(json.dumps(pedido) + "\n").encode(),
        capture_output=True,
        timeout=60,
        check=False,
    )
    lineas = proc.stdout.decode("utf-8", "replace").splitlines()
    assert lineas, proc.stderr.decode("utf-8", "replace")
    assert json.loads(lineas[0])["id"] == 1
    for linea in lineas:
        json.loads(linea)


def test_r13_token_por_parametro_responde_401_aunque_sea_valido():
    """El token en la URL ya no se acepta (058 R2): queda en registros; solo va por encabezado."""
    app = Starlette(routes=[Route("/sse", lambda request: PlainTextResponse("ok"))])
    app.add_middleware(BearerAuthMiddleware)
    client = TestClient(app)
    assert client.get("/sse", params={"token": "ñandú"}).status_code == 401
    assert client.get("/sse", params={"token": token_mcp_de_prueba()}).status_code == 401


def test_r15_cada_transporte_fija_el_suyo_en_la_auditoria(monkeypatch, cuenta):
    visto = []
    monkeypatch.setattr(mcp_server.uvicorn, "run", lambda app, **kw: visto.append(security._audit_transport))
    monkeypatch.setattr(mcp_server.asyncio, "run", lambda coro: (visto.append(security._audit_transport), coro.close()))
    try:
        mcp_server.run_sse_server(port=8124)
        mcp_server.run_stdio_server(cuenta)
    finally:
        security.set_audit_transport("stdio")
    assert visto == ["sse", "stdio"]


@pytest.mark.anyio
async def test_r16_clases_y_recursos_usan_la_base_configurada(tmp_path, monkeypatch, operar_por_mcp):
    db_file = tmp_path / "configurada.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    server = create_study_mcp_server()
    ruta = RoadmapRepository(operar_por_mcp(cuenta_en(db_file)), db_file).create_roadmap(
        RoadmapCreate(
            titulo="Ruta Configurada",
            descripcion="d",
            nivel_objetivo="Inicial",
            categoria="general",
            modulos=[RoadmapModuleCreate(titulo="M", orden=1, temas=[RoadmapTopicCreate(titulo="Tema Configurado", orden=1)])],
        )
    )
    tema_id = ruta.modulos[0].temas[0].id

    assert "Ruta Configurada" in await llamar(server, "study_list_roadmaps", {})
    assert "Tema Configurado" in await llamar(server, "study_get_roadmap_topics", {"roadmap_id": ruta.id})
    assert "guardada exitosamente" in await llamar(server, "study_create_or_update_lesson", {"topic_id": tema_id, "markdown_content": CLASE_1})
    assert "Contenido original" in await llamar(server, "study_get_topic_lesson", {"topic_id": tema_id})
    await llamar(server, "study_add_course", {"platform_name": "P", "course_name": "Curso Configurado", "url_aula": "https://example.com/c"})
    assert "Curso Configurado" in str(await server.read_resource("study://courses/list"))
    assert "Ruta Configurada" in str(await server.read_resource("study://roadmaps/active"))
    assert len(q(db_file, "SELECT id FROM ruta_clases")) == 1


# ---------------------------------------------------------------- feature 030: R8 y R9 del copilot

AVISO_SIN_REGISTRO = "No se registró ningún cambio"


@pytest.mark.parametrize(
    ("instruccion", "minutos"),
    [
        ("Estudié 2 horas", 120),
        ("Estuve estudiando una hora y media de Kubernetes", 90),
        ("Practiqué media hora", 30),
        ("Repasé 1,5 hs", 90),
        ("Estudié 2 horas y 15 minutos", 135),
        ("Hoy estudié 30 min, ¿qué tema sigue en mi ruta?", 30),
    ],
)
def test_030_r8_tiempo_de_estudio_en_horas_y_con_otros_verbos(db, instruccion, minutos):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert sesiones(db_file) == [minutos]


@pytest.mark.parametrize("instruccion", ["¿Cuánto estudié esta semana?", "¿Estudié 2 horas ayer?", "Estudié mucho hoy"])
def test_030_r8_sin_una_duracion_afirmada_no_registra(db, instruccion):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert sesiones(db_file) == []


@pytest.mark.parametrize(
    ("instruccion", "esperado"),
    [
        ("Quedé en la página 80 del libro", {"pagina_actual": 80, "capitulo_actual": 2}),
        ("Llegué a la página 95", {"pagina_actual": 95, "capitulo_actual": 2}),
        ("Voy en el capítulo 4", {"pagina_actual": 40, "capitulo_actual": 4}),
        ("Terminé el capítulo 3 del libro", {"pagina_actual": 40, "capitulo_actual": 3}),
    ],
)
def test_030_r8_otras_formas_de_decir_el_avance_de_lectura(db, instruccion, esperado):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert libro(db_file) == {**esperado, "estado": "leyendo"}


@pytest.mark.parametrize(
    "instruccion",
    ["Hoy hice 20 páginas", "Leí bastante hoy", "Completé el módulo 2", "Le metí 40 minutos a Kubernetes", "Estudié mucho hoy"],
)
def test_030_r9_un_avance_no_reconocido_se_avisa_con_las_herramientas_directas(db, instruccion):
    db_file, _, _ = db
    antes = (cursos(db_file), sesiones(db_file), libro(db_file))
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert (cursos(db_file), sesiones(db_file), libro(db_file)) == antes
    aviso = next(w for w in res.warnings if AVISO_SIN_REGISTRO in w)
    for herramienta in ("study_update_book_progress", "study_update_course_progress", "study_log_study_session"):
        assert herramienta in aviso
    assert AVISO_SIN_REGISTRO in res.to_markdown()


@pytest.mark.parametrize(
    "instruccion",
    ["Dame un resumen de mi día", "¿Qué tema me toca estudiar?", "¿Cómo voy?", "Voy a estudiar mañana", "¿Cuántas páginas tiene el capítulo 5?", "¿Cuál es mi horario de hoy?"],
)
def test_030_r9_una_consulta_no_lleva_el_aviso(db, instruccion):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert not any(AVISO_SIN_REGISTRO in w for w in res.warnings)


def test_030_r9_no_se_duplica_con_otra_advertencia_ni_con_una_accion(db):
    db_file, _, _ = db
    engine = StudyCopilotEngine(db_path=db_file)
    con_accion = engine.execute_plan("Estudié 20 min")
    assert not any(AVISO_SIN_REGISTRO in w for w in con_accion.warnings)
    con_aviso = engine.execute_plan("Llevo 50% de avance en el curso de Rust")
    assert len(con_aviso.warnings) == 1 and AVISO_SIN_REGISTRO not in con_aviso.warnings[0]


def test_030_r9_en_solo_lectura_dice_el_motivo(db):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file, read_only=True).execute_plan("Hoy hice 20 páginas")
    assert any("Read-Only" in w for w in res.warnings)
    assert not any("study_update_book_progress" in w for w in res.warnings)


@pytest.mark.anyio
async def test_030_r9_la_descripcion_de_la_herramienta_nombra_las_directas(db):
    db_file, _, _ = db
    server = create_study_mcp_server(db_path=db_file)
    copilot = next(t for t in await server.list_tools() if t.name == "study_copilot")
    assert "study_update_book_progress" in copilot.description and "no con IA" in copilot.description


@pytest.mark.parametrize(
    ("instruccion", "minutos"),
    [("Estudié 1.5 horas", 90), ("Estudié 2 h 30 min", 150), ("Estudié hora y media", 90), ("Estudié 2 horas el capítulo 3 del curso", 120), ("Repasé 15 tarjetas en 10 min", 10)],
)
def test_030_r8_duraciones_que_se_registran_bien(db, instruccion, minutos):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert sesiones(db_file) == [minutos]
    assert libro(db_file) == {"pagina_actual": 40, "capitulo_actual": 2, "estado": "leyendo"}


@pytest.mark.parametrize(
    "instruccion",
    [
        "Estudié de 10 a 12 hs",
        "Estudié hasta las 23 hs",
        "Estudié 1:30 hs",
        "Trabajé 8 horas en la oficina y no pude estudiar",
        "Repasé inglés, mañana tengo 2 horas de clase",
        "Hoy no pude: estudié poco, me faltan 3 horas",
        "Estudié 90 min en vez de 2 horas",
        "Estudié 3 minas",
        "No estudié 30 min",
    ],
)
def test_030_r8_una_duracion_dudosa_no_se_registra(db, instruccion):
    db_file, _, _ = db
    StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert sesiones(db_file) == []


@pytest.mark.parametrize("instruccion", ["Explicame el capítulo 3 del libro", "Configurá un pomodoro de 25 min"])
def test_030_r9_un_pedido_con_numeros_no_es_un_avance(db, instruccion):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert not any(AVISO_SIN_REGISTRO in w for w in res.warnings)


@pytest.mark.parametrize(
    "instruccion",
    [
        "Hoy 20 páginas del libro",
        "Sumé 40 minutos de estudio",
        "Hoy fueron 2 horas de Kubernetes",
        "Ya voy 3 capítulos adelante",
        "30% del curso de Rust listo",
        "Estuve estudiando Kubernetes toda la tarde",
        "Voy en la mitad del libro",
    ],
)
def test_030_r9_una_cantidad_o_un_verbo_de_avance_sin_interpretar_se_avisa(db, instruccion):
    db_file, _, _ = db
    antes = (cursos(db_file), sesiones(db_file), libro(db_file))
    res = StudyCopilotEngine(db_path=db_file).execute_plan(instruccion)
    assert (cursos(db_file), sesiones(db_file), libro(db_file)) == antes
    assert res.warnings, "un avance que no se registra no puede quedar sin aviso"


def test_030_r9_querer_estudiar_no_es_un_avance(db):
    db_file, _, _ = db
    res = StudyCopilotEngine(db_path=db_file).execute_plan("Quiero estudiar 2 horas mañana")
    assert sesiones(db_file) == []
    assert not any(AVISO_SIN_REGISTRO in w for w in res.warnings)


def test_030_r8_hora_y_cuarto_y_duraciones_aproximadas(db):
    db_file, _, _ = db
    engine = StudyCopilotEngine(db_path=db_file)
    engine.execute_plan("Practiqué una hora y cuarto")
    assert sesiones(db_file) == [75]
    for aproximada in ("Estudié 2 horas y pico", "Estudié casi 2 horas"):
        res = engine.execute_plan(aproximada)
        assert sesiones(db_file) == [75]
        assert any(AVISO_SIN_REGISTRO in w for w in res.warnings)
