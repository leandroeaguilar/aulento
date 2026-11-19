"""Pruebas de la Fase 0: Libros y cursos (revisión de arquitectura).

Cubre:
- Migración 12: reparación de filas rotas, columna autor y tabla avances_de_lectura.
- Punto 1: validación en PUT de libros (400) y repositorio; lista legible en 200.
- Punto 2: regla única de completado en update_progress y advance_chapter.
- Punto 5: orden de prioridad alta -> media -> baja en cursos.
- Punto 7: buscar_por_titulo y webhook con 0/1/varios candidatos y error 400.
- Punto 8: registro de avances de lectura en avances_de_lectura.
- Punto 10: campo estado en progreso de cursos y autor en libros.
"""

import sqlite3
import pytest
from conftest import administrador_de_prueba
from fastapi.testclient import TestClient

from aulento.db.connection import get_connection
from aulento.db.migrations import MIGRACIONES, migrar, version_actual
from aulento.db.repository import CursoRepository, LibroRepository
from aulento.db.schema import create_schema, init_db
from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
from aulento.models.libro import EstadoLibro, LibroCreate, LibroUpdate
from aulento.web.app import create_app


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Inicializa una base de datos temporal en la última versión de migración."""
    db_file = tmp_path / "fase0_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    administrador_de_prueba(conn)
    conn.close()
    return db_file


@pytest.fixture
def client(test_db):
    """Cliente de pruebas FastAPI conectado a la base temporal."""
    app = create_app()
    return TestClient(app)


# ----------------------------------------------------------------------
# 1. Migración 12 (decisiones 3 y 4)
# ----------------------------------------------------------------------


def test_migracion_12_repara_filas_rotas_y_crea_esquema(tmp_path):
    """La migración 12 ajusta pagina_actual = total_paginas si estaba rota, agrega autor y crea avances_de_lectura."""
    db_file = tmp_path / "test_migracion_12.db"
    conn = get_connection(db_file)

    # Aplicamos hasta la migración 11
    from aulento.db import migrations

    for numero, nombre, funcion, *opciones in MIGRACIONES[:11]:
        migrations._aplicar(conn, numero, nombre, funcion, sin_claves_foraneas=bool(opciones and opciones[0]))
    assert version_actual(conn) == 11

    # Insertamos un usuario y filas de libros: una sana y una con pagina_actual > total_paginas
    conn.execute("INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, rol, activo, creado_en) VALUES (1, 'u', 'p', 'usuario', 1, '2026-01-01');")
    conn.execute(
        """
        INSERT INTO libros_lectura (id, user_id, titulo, capitulo_actual, total_capitulos, pagina_actual, total_paginas)
        VALUES (1, 1, 'Libro Roto', 1, 1, 350, 200),
               (2, 1, 'Libro Sano', 1, 1, 50, 200);
        """
    )
    conn.commit()

    # Ejecutamos la migración
    version_final = migrar(conn, respaldo=False)
    assert version_final == 12

    # Verificamos la reparación de la fila rota
    fila_rota = conn.execute("SELECT pagina_actual, total_paginas FROM libros_lectura WHERE id = 1;").fetchone()
    assert fila_rota[0] == 200
    assert fila_rota[1] == 200

    # La fila sana no se modificó
    fila_sana = conn.execute("SELECT pagina_actual, total_paginas FROM libros_lectura WHERE id = 2;").fetchone()
    assert fila_sana[0] == 50
    assert fila_sana[1] == 200

    # Columna autor existe
    columnas = [c[1] for c in conn.execute("PRAGMA table_info(libros_lectura);").fetchall()]
    assert "autor" in columnas

    # Tabla avances_de_lectura y su índice existen
    tablas = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    assert "avances_de_lectura" in tablas

    indices = [i[1] for i in conn.execute("PRAGMA index_list(avances_de_lectura);").fetchall()]
    assert "idx_avances_de_lectura_cuenta" in indices
    conn.close()


# ----------------------------------------------------------------------
# 2. Punto 1 y Decisión 2: Validación en PUT y LibroRepository.update
# ----------------------------------------------------------------------


def test_put_libro_valores_invalidos_responde_400_y_lista_sigue_en_200(client):
    """Un PUT con total_paginas menor a la página actual responde 400 y GET /api/books sigue en 200."""
    creacion = client.post(
        "/api/books",
        json={
            "titulo": "Sistemas Distribuidos",
            "capitulo_actual": 1,
            "total_capitulos": 5,
            "pagina_actual": 80,
            "total_paginas": 200,
        },
    )
    assert creacion.status_code == 201
    libro_id = creacion.json()["id"]

    # Intentamos bajar total_paginas a 50 cuando la página actual es 80
    res_invalida = client.put(
        f"/api/books/{libro_id}",
        json={"total_paginas": 50},
    )
    assert res_invalida.status_code == 400
    assert "supera el total de páginas" in res_invalida.json()["detail"]

    # GET /api/books debe seguir respondiendo 200 sin romperse el modelo
    res_lista = client.get("/api/books")
    assert res_lista.status_code == 200
    libros = res_lista.json()
    libro = next(b for b in libros if b["id"] == libro_id)
    assert libro["pagina_actual"] == 80
    assert libro["total_paginas"] == 200


def test_libro_repository_update_valida_valores_combinados(test_db):
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id=user_id)

    libro = repo.create(
        LibroCreate(
            titulo="Data Pipelines",
            capitulo_actual=2,
            total_capitulos=10,
            pagina_actual=50,
            total_paginas=300,
        )
    )

    # Página mayor a total páginas
    with pytest.raises(ValueError, match="supera el total de páginas"):
        repo.update(libro.id, LibroUpdate(total_paginas=30))

    # Capítulo mayor a total capítulos
    with pytest.raises(ValueError, match="supera el total de capítulos"):
        repo.update(libro.id, LibroUpdate(capitulo_actual=15))

    # Página negativa (usando model_construct para probar la validación del repositorio)
    with pytest.raises(ValueError, match="no pueden ser negativos"):
        repo.update(libro.id, LibroUpdate.model_construct(pagina_actual=-1))

    # Total capítulos inválido
    with pytest.raises(ValueError, match="El total de capítulos debe ser mayor a 0"):
        repo.update(libro.id, LibroUpdate.model_construct(total_capitulos=0))

    conn.close()


# ----------------------------------------------------------------------
# 3. Punto 2 y Decisión 1: Regla única de completado
# ----------------------------------------------------------------------


def test_regla_unica_completado_libro_con_paginas(test_db):
    """Un libro de 300 páginas con 1 de 1 capítulos sigue leyendo al pasar a página 10 y se completa al llegar a 300."""
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id=user_id)

    libro = repo.create(
        LibroCreate(
            titulo="Designing Data-Intensive Applications",
            capitulo_actual=1,
            total_capitulos=1,
            pagina_actual=0,
            total_paginas=300,
        )
    )
    assert libro.estado == EstadoLibro.LEYENDO

    # Al pasar a la página 10 sigue leyendo aunque capitulo_actual == total_capitulos
    up1 = repo.update_progress(libro.id, pagina_actual=10)
    assert up1.pagina_actual == 10
    assert up1.estado == EstadoLibro.LEYENDO

    # advance_chapter no lo completa porque tiene total_paginas y no llegó
    adv = repo.advance_chapter(libro.id, chapters=1)
    assert adv.estado == EstadoLibro.LEYENDO

    # Al llegar a la página 300 se completa
    up_fin = repo.update_progress(libro.id, pagina_actual=300)
    assert up_fin.pagina_actual == 300
    assert up_fin.estado == EstadoLibro.COMPLETADO

    # Estado explícito gana
    up_pausa = repo.update_progress(libro.id, pagina_actual=300, estado=EstadoLibro.PAUSADO)
    assert up_pausa.estado == EstadoLibro.PAUSADO

    conn.close()


def test_regla_unica_completado_libro_solo_con_capitulos(test_db):
    """Un libro sin total_paginas se completa cuando sus capítulos llegan al total."""
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id=user_id)

    libro = repo.create(
        LibroCreate(
            titulo="Manual sin páginas",
            capitulo_actual=1,
            total_capitulos=3,
            total_paginas=None,
        )
    )
    assert libro.estado == EstadoLibro.LEYENDO

    up1 = repo.advance_chapter(libro.id)
    assert up1.capitulo_actual == 2
    assert up1.estado == EstadoLibro.LEYENDO

    up2 = repo.advance_chapter(libro.id)
    assert up2.capitulo_actual == 3
    assert up2.estado == EstadoLibro.COMPLETADO

    conn.close()


# ----------------------------------------------------------------------
# 4. Punto 5 y Decisión 6: Orden de prioridad de cursos
# ----------------------------------------------------------------------


def test_orden_prioridad_cursos(client, test_db):
    """Los cursos se ordenan: alta -> media -> baja y luego por progreso desc."""
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    plat_id = conn.execute("SELECT id FROM plataformas WHERE user_id = ? LIMIT 1;", (user_id,)).fetchone()[0]
    conn.close()

    # Creamos cursos en desorden
    client.post("/api/hub/courses", json={"plataforma_id": plat_id, "nombre_curso": "Curso Baja", "url_aula": "https://example.com/baja", "prioridad": "baja", "progreso_pct": 90.0})
    client.post("/api/hub/courses", json={"plataforma_id": plat_id, "nombre_curso": "Curso Media", "url_aula": "https://example.com/media", "prioridad": "media", "progreso_pct": 50.0})
    client.post("/api/hub/courses", json={"plataforma_id": plat_id, "nombre_curso": "Curso Alta 1", "url_aula": "https://example.com/alta1", "prioridad": "alta", "progreso_pct": 20.0})
    client.post("/api/hub/courses", json={"plataforma_id": plat_id, "nombre_curso": "Curso Alta 2", "url_aula": "https://example.com/alta2", "prioridad": "alta", "progreso_pct": 70.0})

    res = client.get("/api/hub/courses")
    assert res.status_code == 200
    cursos = res.json()

    nombres = [c["nombre_curso"] for c in cursos]
    # Alta 2 (70%), Alta 1 (20%), Media (50%), Baja (90%)
    assert nombres == ["Curso Alta 2", "Curso Alta 1", "Curso Media", "Curso Baja"]


# ----------------------------------------------------------------------
# 5. Punto 7 y Decisión 5: Webhook de libros y buscar_por_titulo
# ----------------------------------------------------------------------


def test_buscar_por_titulo_exacta_y_parcial(test_db):
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id=user_id)

    l1 = repo.create(LibroCreate(titulo="Python Fluente", total_paginas=500))
    l2 = repo.create(LibroCreate(titulo="Python Crash Course", total_paginas=400))

    # Búsqueda exacta (case insensitive) devuelve solo la exacta
    res_exacta = repo.buscar_por_titulo("python fluente")
    assert len(res_exacta) == 1
    assert res_exacta[0].id == l1.id

    # Búsqueda parcial cuando no hay exacta devuelve ambas
    res_parcial = repo.buscar_por_titulo("python")
    assert len(res_parcial) == 2
    assert {r.id for r in res_parcial} == {l1.id, l2.id}

    # Búsqueda sin coincidencia
    assert repo.buscar_por_titulo("Rust") == []
    assert repo.buscar_por_titulo("") == []

    conn.close()


def test_webhook_sync_0_crea_1_actualiza_varios_409(client):
    # 0 candidatos: crea el libro
    r_crea = client.post(
        "/api/books/sync/webhook",
        json={"titulo": "Libro Nuevo", "pagina_actual": 25, "total_paginas": 200},
    )
    assert r_crea.status_code == 200
    datos_crea = r_crea.json()
    assert datos_crea["accion"] == "creado"
    assert datos_crea["pagina_actual"] == 25

    # 1 candidato: actualiza el libro
    r_act = client.post(
        "/api/books/sync/webhook",
        json={"titulo": "Libro Nuevo", "pagina_actual": 50},
    )
    assert r_act.status_code == 200
    assert r_act.json()["accion"] == "actualizado"
    assert r_act.json()["pagina_actual"] == 50

    # Creamos dos libros ambiguos con la palabra "Cloud"
    res_b1 = client.post("/api/books", json={"titulo": "Google Cloud Architect", "total_paginas": 400})
    id_b1 = res_b1.json()["id"]
    res_b2 = client.post("/api/books", json={"titulo": "Cloud Native Patterns", "total_paginas": 350})
    id_b2 = res_b2.json()["id"]

    libros_antes = client.get("/api/books").json()
    total_antes = len(libros_antes)

    # Webhook con "Cloud": coincide con 2 libros -> responde 409
    r_conflicto = client.post(
        "/api/books/sync/webhook",
        json={"titulo": "Cloud", "pagina_actual": 80},
    )
    assert r_conflicto.status_code == 409
    data_conflicto = r_conflicto.json()
    assert "detail" in data_conflicto
    assert "candidatos" in data_conflicto
    assert len(data_conflicto["candidatos"]) == 2
    titulos = {c["titulo"] for c in data_conflicto["candidatos"]}
    assert titulos == {"Google Cloud Architect", "Cloud Native Patterns"}

    # Después del 409 ningún libro cambió (página_actual, total_paginas) ni se creó ninguno
    libros_despues = client.get("/api/books").json()
    assert len(libros_despues) == total_antes
    mapa_despues = {b["id"]: b for b in libros_despues}
    assert mapa_despues[id_b1]["pagina_actual"] == 0
    assert mapa_despues[id_b1]["total_paginas"] == 400
    assert mapa_despues[id_b2]["pagina_actual"] == 0
    assert mapa_despues[id_b2]["total_paginas"] == 350
    assert mapa_despues[datos_crea["libro_id"]]["pagina_actual"] == 50
    assert mapa_despues[datos_crea["libro_id"]]["total_paginas"] == 200

    # Error de validación en webhook responde 400
    r_err = client.post(
        "/api/books/sync/webhook",
        json={"titulo": "Libro Roto", "pagina_actual": 500, "total_paginas": 200},
    )
    assert r_err.status_code == 400


# ----------------------------------------------------------------------
# 6. Punto 8 y Decisión 4: Registro de avances_de_lectura
# ----------------------------------------------------------------------


def test_registro_avances_de_lectura(test_db):
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id=user_id)

    # El alta no debe registrar avance
    libro = repo.create(LibroCreate(titulo="Deep Learning", pagina_actual=10, total_paginas=500))
    filas_0 = conn.execute("SELECT * FROM avances_de_lectura WHERE user_id = ?;", (user_id,)).fetchall()
    assert len(filas_0) == 0

    # Subida de páginas con update_progress: de 10 a 35 -> registra 25 páginas
    repo.update_progress(libro.id, pagina_actual=35)
    filas_1 = conn.execute("SELECT libro_id, paginas, registrado_en FROM avances_de_lectura WHERE user_id = ?;", (user_id,)).fetchall()
    assert len(filas_1) == 1
    assert filas_1[0][0] == libro.id
    assert filas_1[0][1] == 25
    assert filas_1[0][2] is not None

    # Baja o misma página: no registra
    repo.update_progress(libro.id, pagina_actual=35)
    repo.update_progress(libro.id, pagina_actual=20)
    assert conn.execute("SELECT COUNT(*) FROM avances_de_lectura WHERE user_id = ?;", (user_id,)).fetchone()[0] == 1

    # Subida de páginas con update: de 20 a 70 -> registra 50 páginas
    repo.update(libro.id, LibroUpdate(pagina_actual=70))
    filas_2 = conn.execute("SELECT paginas FROM avances_de_lectura WHERE user_id = ? ORDER BY id ASC;", (user_id,)).fetchall()
    assert len(filas_2) == 2
    assert filas_2[1][0] == 50

    # Borrado del libro conserva el historial con libro_id = NULL
    repo.delete(libro.id)
    filas_post_delete = conn.execute("SELECT libro_id, paginas FROM avances_de_lectura WHERE user_id = ?;", (user_id,)).fetchall()
    assert len(filas_post_delete) == 2
    assert filas_post_delete[0][0] is None
    assert filas_post_delete[1][0] is None

    conn.close()


# ----------------------------------------------------------------------
# 7. Punto 10 y Decisión 7: estado en cursos y autor en libros
# ----------------------------------------------------------------------


def test_curso_progreso_actualiza_estado(client, test_db):
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    plat_id = conn.execute("SELECT id FROM plataformas WHERE user_id = ? LIMIT 1;", (user_id,)).fetchone()[0]
    conn.close()

    curso_res = client.post(
        "/api/hub/courses",
        json={"plataforma_id": plat_id, "nombre_curso": "Curso Reactivo", "url_aula": "https://example.com/reactivo", "progreso_pct": 10.0, "estado": "en_curso"},
    )
    curso_id = curso_res.json()["id"]

    # Actualizamos progreso pasando estado
    res = client.post(
        f"/api/hub/courses/{curso_id}/progress",
        json={"progreso_pct": 85.0, "estado": "pausado"},
    )
    assert res.status_code == 200
    datos = res.json()
    assert datos["progreso_pct"] == 85.0
    assert datos["estado"] == "pausado"


def test_autor_en_alta_edicion_y_consulta(client):
    # Alta con autor
    res_crear = client.post(
        "/api/books",
        json={"titulo": "Clean Architecture", "autor": "Robert C. Martin", "total_paginas": 350},
    )
    assert res_crear.status_code == 201
    libro = res_crear.json()
    assert libro["autor"] == "Robert C. Martin"
    libro_id = libro["id"]

    # Consulta por lista
    res_get = client.get("/api/books")
    assert res_get.status_code == 200
    en_lista = next(b for b in res_get.json() if b["id"] == libro_id)
    assert en_lista["autor"] == "Robert C. Martin"

    # Edición de autor
    res_edit = client.put(
        f"/api/books/{libro_id}",
        json={"autor": "Uncle Bob"},
    )
    assert res_edit.status_code == 200
    assert res_edit.json()["autor"] == "Uncle Bob"

    # PUT con autor null lo deja en null
    res_null_aut = client.put(
        f"/api/books/{libro_id}",
        json={"autor": None},
    )
    assert res_null_aut.status_code == 200
    assert res_null_aut.json()["autor"] is None

    # Verificación en lista
    res_get_null = client.get("/api/books")
    assert res_get_null.status_code == 200
    en_lista_null = next(b for b in res_get_null.json() if b["id"] == libro_id)
    assert en_lista_null["autor"] is None

    # PUT con total_paginas null lo borra y pasa a medirse por capítulos
    res_null_pag = client.put(
        f"/api/books/{libro_id}",
        json={"total_paginas": None},
    )
    assert res_null_pag.status_code == 200
    assert res_null_pag.json()["total_paginas"] is None

    res_get_final = client.get("/api/books")
    en_lista_final = next(b for b in res_get_final.json() if b["id"] == libro_id)
    assert en_lista_final["total_paginas"] is None


def test_webhook_sync_regla_completado_libro_existente(client):
    """El webhook no anula _esta_completado en libros existentes ni descompleta libros completados."""
    # Libro sin total_paginas (solo capítulos)
    res = client.post(
        "/api/books",
        json={"titulo": "Sistemas en la Práctica", "capitulo_actual": 1, "total_capitulos": 3, "total_paginas": None},
    )
    assert res.status_code == 201
    libro_id = res.json()["id"]
    assert res.json()["estado"] == "leyendo"

    # Webhook avanza al capítulo 3 (el total): debe completarse automáticamente
    r_sync = client.post(
        "/api/books/sync/webhook",
        json={"titulo": "Sistemas en la Práctica", "capitulo_actual": 3},
    )
    assert r_sync.status_code == 200
    libros = client.get("/api/books").json()
    libro = next(b for b in libros if b["id"] == libro_id)
    assert libro["capitulo_actual"] == 3
    assert libro["estado"] == "completado"

    # Si un libro ya está completado, otro webhook no lo vuelve a 'leyendo'
    r_sync2 = client.post(
        "/api/books/sync/webhook",
        json={"titulo": "Sistemas en la Práctica", "pagina_actual": 1},
    )
    assert r_sync2.status_code == 200
    libros2 = client.get("/api/books").json()
    libro2 = next(b for b in libros2 if b["id"] == libro_id)
    assert libro2["estado"] == "completado"


def test_buscar_por_titulo_escapa_caracteres_especiales_like(test_db, client):
    """buscar_por_titulo escapa %, _ y \\ para no coincidir con todos los libros."""
    conn = get_connection(test_db)
    user_id = administrador_de_prueba(conn).id
    repo = LibroRepository(conn, user_id=user_id)

    l1 = repo.create(LibroCreate(titulo="Python 100% Practico", total_paginas=200))
    repo.create(LibroCreate(titulo="Clean Code", total_paginas=300))
    l3 = repo.create(LibroCreate(titulo="Clean_Architecture", total_paginas=400))
    l4 = repo.create(LibroCreate(titulo="Ruta\\Vault", total_paginas=150))

    # Búsqueda con "%" solo debe devolver el libro que contiene "%" literalmente
    res_pct = repo.buscar_por_titulo("%")
    assert len(res_pct) == 1
    assert res_pct[0].id == l1.id

    # Búsqueda con "Clean_" solo coincide con "Clean_Architecture" y no con "Clean Code"
    res_guion = repo.buscar_por_titulo("Clean_")
    assert len(res_guion) == 1
    assert res_guion[0].id == l3.id

    # Búsqueda con "\\" coincide con "Ruta\\Vault"
    res_barra = repo.buscar_por_titulo("\\")
    assert len(res_barra) == 1
    assert res_barra[0].id == l4.id

    # Webhook con "%": no coincide con todos los libros ni genera 409 falso
    r_hook = client.post("/api/books/sync/webhook", json={"titulo": "%Nuevo%"})
    assert r_hook.status_code == 200
    assert r_hook.json()["accion"] == "creado"

    conn.close()


def test_texto_atajo_libros_modo_local_en_html_y_manual():
    """El texto sobre el atajo en modo local no promete abrir la app a la red en html ni en el manual."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    html_path = raiz / "src" / "aulento" / "web" / "static" / "index.html"
    manual_path = raiz / "docs" / "MANUAL_DE_USUARIO.md"

    texto_html = html_path.read_text(encoding="utf-8")
    texto_manual = manual_path.read_text(encoding="utf-8")

    texto_viejo = "en la misma red wifi y con la app abierta a la red"
    assert texto_viejo not in texto_html
    assert texto_viejo not in texto_manual

    assert "desde el iPhone hace falta la versión en la nube" in texto_html
    assert "desde el iPhone hace falta la versión en la nube" in texto_manual
