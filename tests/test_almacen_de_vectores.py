"""Pruebas de contrato y comportamiento para los almacenes de vectores (SQLite con sqlite-vec y pgvector)."""

import contextlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aulento.core.embedding_service import EMBEDDING_DIMENSIONS
from aulento.core.knowledge_rag import KnowledgeRAGService, _guardar_hash, _huella
from aulento.db.connection import get_connection
from aulento.db.postgres import is_postgres_available
from aulento.db.vector_repository import AlmacenPgvector
from aulento.db.vectores_sqlite import AlmacenVectoresSqlite
from aulento.web.app import create_app

# Puerto y base de pruebas dedicados para pgvector (flash063: solo 5433, nunca 5432)
POSTGRES_TEST_URL = "postgresql://postgres:postgres@127.0.0.1:5433/aulento_local"


def _vector_unitario(indice: int = 0, dimensiones: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Genera un vector unitario de prueba con un 1.0 en la posición indicada."""
    v = [0.0] * dimensiones
    v[indice % dimensiones] = 1.0
    return v


@pytest.fixture
def almacen_sqlite(tmp_path: Path):
    """Crea un almacén SQLite de prueba sobre un archivo temporal."""
    db_file = tmp_path / "vectores_test.db"

    def fabrica(user_id: int) -> AlmacenVectoresSqlite:
        return AlmacenVectoresSqlite(user_id, db_path=db_file)

    return fabrica


@pytest.fixture
def almacen_pgvector(monkeypatch):
    """Crea un almacén pgvector contra el PostgreSQL de prueba en el puerto 5433 si está disponible."""
    from aulento.db import postgres, vector_repository
    monkeypatch.setenv("DATABASE_URL", POSTGRES_TEST_URL)
    monkeypatch.setenv("POSTGRES_PORT", "5433")

    def real_conn(connect_timeout: int = 2):
        try:
            import psycopg
            from pgvector.psycopg import register_vector
            conn = psycopg.connect(POSTGRES_TEST_URL, autocommit=True, connect_timeout=connect_timeout)
            register_vector(conn)
            return conn
        except Exception:  # noqa: BLE001
            return None

    monkeypatch.setattr(postgres, "get_postgres_connection", real_conn)
    monkeypatch.setattr(vector_repository, "get_postgres_connection", real_conn)

    if not is_postgres_available(timeout_seconds=2):
        pytest.skip("PostgreSQL de prueba no disponible en 127.0.0.1:5433")

    usuarios_usados: list[int] = []

    def fabrica(user_id: int) -> AlmacenPgvector:
        usuarios_usados.append(user_id)
        conn = real_conn()
        if conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM knowledge_embeddings WHERE user_id = %s;", (user_id,))
            conn.close()
        repo = AlmacenPgvector(user_id)
        return repo

    yield fabrica

    for u in set(usuarios_usados):
        with contextlib.suppress(Exception):
            repo = AlmacenPgvector(u)
            repo.delete_by_source("note", "n1")
            repo.delete_by_source("note", "n2")
            repo.delete_by_source("book", "b1")
            repo.delete_by_source("test", "t1")


@pytest.mark.parametrize("almacen_fixture", ["almacen_sqlite", "almacen_pgvector"])
def test_contrato_aislamiento_entre_cuentas(request, almacen_fixture):
    """R1: Los fragmentos indexados por una cuenta son invisibles para cualquier otra."""
    fabrica = request.getfixturevalue(almacen_fixture)
    almacen_1 = fabrica(101)
    almacen_2 = fabrica(102)

    vec = _vector_unitario(0)
    almacen_1.insert_chunk(
        source_type="note",
        source_id="n1",
        source_title="Nota de Cuenta 1",
        chunk_text="Contenido privado de la cuenta 1",
        embedding=vec,
        embedding_model="modelo-test",
    )

    assert almacen_1.count_embeddings() >= 1
    assert almacen_2.count_embeddings() == 0

    hallazgos_2 = almacen_2.search_similar(vec, embedding_model="modelo-test", limit=5)
    assert len(hallazgos_2) == 0

    hallazgos_1 = almacen_1.search_similar(vec, embedding_model="modelo-test", limit=5)
    assert len(hallazgos_1) == 1
    assert hallazgos_1[0]["source_id"] == "n1"


@pytest.mark.parametrize("almacen_fixture", ["almacen_sqlite", "almacen_pgvector"])
def test_contrato_filtro_por_modelo(request, almacen_fixture):
    """R1: La búsqueda vectorial solo compara vectores calculados con el mismo modelo."""
    fabrica = request.getfixturevalue(almacen_fixture)
    almacen = fabrica(103)

    vec = _vector_unitario(1)
    almacen.insert_chunk(
        source_type="note",
        source_id="n1",
        source_title="Nota Modelo A",
        chunk_text="Texto con modelo A",
        embedding=vec,
        embedding_model="modelo-A",
    )
    almacen.insert_chunk(
        source_type="note",
        source_id="n2",
        source_title="Nota Modelo B",
        chunk_text="Texto con modelo B",
        embedding=vec,
        embedding_model="modelo-B",
    )

    resultados_a = almacen.search_similar(vec, embedding_model="modelo-A", limit=10)
    assert len(resultados_a) == 1
    assert resultados_a[0]["source_id"] == "n1"

    resultados_b = almacen.search_similar(vec, embedding_model="modelo-B", limit=10)
    assert len(resultados_b) == 1
    assert resultados_b[0]["source_id"] == "n2"


@pytest.mark.parametrize("almacen_fixture", ["almacen_sqlite", "almacen_pgvector"])
def test_contrato_filtro_por_tipo_de_fuente(request, almacen_fixture):
    """R1: La búsqueda admite filtro opcional por source_type."""
    fabrica = request.getfixturevalue(almacen_fixture)
    almacen = fabrica(104)

    vec = _vector_unitario(2)
    almacen.insert_chunk("note", "n1", "Nota", "Contenido", vec, "modelo-test")
    almacen.insert_chunk("book", "b1", "Libro", "Contenido", vec, "modelo-test")

    solo_libros = almacen.search_similar(vec, "modelo-test", limit=10, source_type="book")
    assert len(solo_libros) == 1
    assert solo_libros[0]["source_type"] == "book"

    todos = almacen.search_similar(vec, "modelo-test", limit=10)
    assert len(todos) == 2


@pytest.mark.parametrize("almacen_fixture", ["almacen_sqlite", "almacen_pgvector"])
def test_contrato_orden_y_rango_de_similitud(request, almacen_fixture):
    """R1: Resultados ordenados de mayor a menor similitud con valores en [0.0, 1.0]."""
    fabrica = request.getfixturevalue(almacen_fixture)
    almacen = fabrica(105)

    v_query = _vector_unitario(0)
    v_cercano = _vector_unitario(0)  # similitud 1.0
    v_lejano = _vector_unitario(1)   # ortogonal, similitud 0.0

    almacen.insert_chunk("note", "n_lejano", "Lejano", "Texto", v_lejano, "modelo-test")
    almacen.insert_chunk("note", "n_cercano", "Cercano", "Texto", v_cercano, "modelo-test")

    resultados = almacen.search_similar(v_query, "modelo-test", limit=5, min_similarity=0.0)
    assert len(resultados) == 2
    assert resultados[0]["source_id"] == "n_cercano"
    assert resultados[1]["source_id"] == "n_lejano"
    assert 0.99 <= resultados[0]["similarity"] <= 1.0
    assert 0.0 <= resultados[1]["similarity"] <= 0.05


@pytest.mark.parametrize("almacen_fixture", ["almacen_sqlite", "almacen_pgvector"])
def test_contrato_borrar_por_fuente(request, almacen_fixture):
    """R1: delete_by_source elimina solo los fragmentos de la fuente y de la cuenta dada."""
    fabrica = request.getfixturevalue(almacen_fixture)
    almacen = fabrica(106)
    vec = _vector_unitario(3)

    almacen.insert_chunk("note", "n1", "Nota 1", "Chunk 1", vec, "modelo-test")
    almacen.insert_chunk("note", "n1", "Nota 1", "Chunk 2", vec, "modelo-test")
    almacen.insert_chunk("note", "n2", "Nota 2", "Chunk 1", vec, "modelo-test")

    borrados = almacen.delete_by_source("note", "n1")
    assert borrados == 2
    assert almacen.count_embeddings(source_type="note", source_id="n1") == 0
    assert almacen.count_embeddings(source_type="note", source_id="n2") == 1


@pytest.mark.parametrize("almacen_fixture", ["almacen_sqlite", "almacen_pgvector"])
def test_contrato_conteo_de_fragmentos_y_por_modelo(request, almacen_fixture):
    """R1: Conteo de fragmentos con y sin filtros, y resumen por modelo."""
    fabrica = request.getfixturevalue(almacen_fixture)
    almacen = fabrica(107)
    vec = _vector_unitario(4)

    almacen.insert_chunk("note", "n1", "N1", "T", vec, "modelo-X")
    almacen.insert_chunk("note", "n2", "N2", "T", vec, "modelo-X")
    almacen.insert_chunk("book", "b1", "B1", "T", vec, "modelo-Y")

    assert almacen.count_embeddings() == 3
    assert almacen.count_embeddings(source_type="note") == 2
    assert almacen.count_embeddings(embedding_model="modelo-X") == 2
    assert almacen.count_embeddings(embedding_model="modelo-Y") == 1

    por_modelo = almacen.count_by_model()
    assert por_modelo.get("modelo-X") == 2
    assert por_modelo.get("modelo-Y") == 1


def test_sqlite_sin_extension_informa_no_disponible_y_app_arranca(monkeypatch, tmp_path):
    """R5: Si sqlite-vec no puede cargarse, el sistema sigue funcionando y muestra índice apagado."""
    import sqlite_vec

    def fail_load(conn):
        raise RuntimeError("Extensión sqlite-vec simulada como no soportada")

    monkeypatch.setattr(sqlite_vec, "load", fail_load)

    db_file = tmp_path / "vectores_roto.db"
    almacen = AlmacenVectoresSqlite(1, db_path=db_file)
    assert almacen.disponible() is False
    assert almacen.motivo_no_disponible is not None
    assert "no soportada" in almacen.motivo_no_disponible

    # La app arranca y /api/vectors/status responde informando el estado sin fallar
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/api/vectors/status")
        assert res.status_code == 200
        data = res.json()
        assert data["almacen"] == "sqlite-vec"
        assert data["indice_disponible"] is False
        assert data["motivo_no_disponible"] is not None


def test_sqlite_archivo_danado_se_recrea_vacio(tmp_path):
    """R4: Si el archivo vectores.db está dañado, se renombra y se crea uno vacío funcional."""
    db_file = tmp_path / "vectores.db"
    db_file.write_bytes(b"CONTENIDO TOTALMENTE INVALIDO PARA UN ARCHIVO SQLITE")

    almacen = AlmacenVectoresSqlite(1, db_path=db_file)
    assert almacen.disponible() is True

    # Verificar que se creó el respaldo .danado-<fecha>
    danados = list(tmp_path.glob("vectores.db.danado-*"))
    assert len(danados) == 1

    # Comprobar que el nuevo archivo funciona insertando y contando
    vec = _vector_unitario(0)
    frag_id = almacen.insert_chunk("note", "n1", "Título", "Texto", vec, "modelo-test")
    assert frag_id > 0
    assert almacen.count_embeddings() == 1


def test_modo_local_usa_sqlite_por_defecto_sin_postgres():
    """R2: En modo local, KnowledgeRAGService usa SQLite sin requerir PostgreSQL ni Docker."""
    rag = KnowledgeRAGService(1)
    assert isinstance(rag.repo, AlmacenVectoresSqlite)
    assert rag.repo.nombre == "sqlite-vec"
    assert rag.is_ready() is True


def test_modo_local_inicializar_responde_que_no_hace_falta():
    """R7: POST /api/vectors/init en local responde que no hace falta sin error."""
    app = create_app()
    with TestClient(app) as client:
        res = client.post("/api/vectors/init")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "no necesita inicialización" in data["message"]


def test_modo_local_textos_sin_mencion_de_postgresql():
    """R7: En la versión local, ningún texto ni clave de la respuesta de estado contiene 'postgres'."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/api/vectors/status")
        assert res.status_code == 200
        data = res.json()
        assert data["almacen"] == "sqlite-vec"
        assert data["indice_disponible"] is True
        assert "postgres_connected" not in data

        def _revisar(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    assert "postgres" not in k.lower(), f"Clave contiene postgres: {k}"
                    _revisar(v)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    _revisar(item)
            elif isinstance(obj, str):
                assert "postgres" not in obj.lower(), f"Texto contiene postgres: {obj}"

        _revisar(data)


def test_filtro_por_tipo_en_knn_recupera_todos_los_del_tipo_pedido(tmp_path):
    """R1: Con 60 fragmentos más cercanos de otro tipo y 3 del tipo pedido, deben volver los 3."""
    db_file = tmp_path / "vectores_knn_filter.db"
    almacen = AlmacenVectoresSqlite(1, db_path=db_file)

    # 60 fragmentos de tipo 'course' muy cercanos al vector de consulta
    q = _vector_unitario(0)
    for i in range(1, 61):
        v = [0.0] * EMBEDDING_DIMENSIONS
        v[0] = 1.0
        v[1] = float(i) * 0.0001
        almacen.insert_chunk(
            source_type="course",
            source_id=f"c-{i}",
            source_title=f"Curso {i}",
            chunk_text=f"Texto del curso {i}",
            embedding=v,
            embedding_model="modelo-knn",
        )

    # 3 fragmentos de tipo 'book' con distancia algo mayor
    for i in range(1, 4):
        v = [0.0] * EMBEDDING_DIMENSIONS
        v[0] = 0.8
        v[2] = float(i) * 0.01
        almacen.insert_chunk(
            source_type="book",
            source_id=f"b-{i}",
            source_title=f"Libro {i}",
            chunk_text=f"Texto del libro {i}",
            embedding=v,
            embedding_model="modelo-knn",
        )

    # Buscar pidiendo 'book' con limit=5
    encontrados = almacen.search_similar(
        query_embedding=q,
        embedding_model="modelo-knn",
        limit=5,
        source_type="book",
        min_similarity=0.0,
    )
    assert len(encontrados) == 3
    assert {r["source_id"] for r in encontrados} == {"b-1", "b-2", "b-3"}


def test_sqlite_vec_ruta_por_defecto_crea_directorio(monkeypatch, tmp_path):
    """R4: La ruta por defecto es get_data_dir() / 'vectores.db' y se crea si falta."""
    nuevo_datos = tmp_path / "subcarpeta" / "datos"
    assert not nuevo_datos.exists()
    monkeypatch.setenv("AULENTO_DATA_DIR", str(nuevo_datos))

    almacen = AlmacenVectoresSqlite(1)
    assert almacen.db_path == nuevo_datos / "vectores.db"
    assert nuevo_datos.exists()
    assert almacen.disponible() is True
    assert almacen.db_path.exists()


def test_sqlite_vec_base_ocupada_no_se_renombra(tmp_path, monkeypatch):
    """R4: Una base ocupada (OperationalError('database is locked')) NO se trata como daño ni se renombra."""
    import sqlite3

    db_file = tmp_path / "vectores_ocupados.db"
    almacen = AlmacenVectoresSqlite(1, db_path=db_file)
    almacen.disponible()  # Crear base

    def mock_abrir_bloqueado(ruta):
        raise sqlite3.OperationalError("database is locked")

    from aulento.db import vectores_sqlite

    monkeypatch.setattr(vectores_sqlite, "_abrir_conexion_sqlite_vec", mock_abrir_bloqueado)
    vectores_sqlite._VERIFICADAS.clear()

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        almacen._get_conn()

    # El archivo original NO se renombró ni existen archivos .danado-*
    assert db_file.exists()
    danados = list(tmp_path.glob("*.danado*"))
    assert len(danados) == 0


def test_sqlite_vec_renombrar_mueve_wal_y_shm(tmp_path, monkeypatch):
    """R4: Al detectar una base dañada, se renombra la base y también sus archivos -wal y -shm."""
    import sqlite3

    db_file = tmp_path / "vectores_wal.db"
    wal_file = tmp_path / "vectores_wal.db-wal"
    shm_file = tmp_path / "vectores_wal.db-shm"

    db_file.write_text("CORRUPTO", encoding="utf-8")
    wal_file.write_text("WAL_DATA", encoding="utf-8")
    shm_file.write_text("SHM_DATA", encoding="utf-8")

    from aulento.db import vectores_sqlite

    vectores_sqlite._VERIFICADAS.clear()

    orig_abrir = vectores_sqlite._abrir_conexion_sqlite_vec
    intentos = [0]

    def mock_abrir(ruta):
        intentos[0] += 1
        if intentos[0] == 1:
            raise sqlite3.DatabaseError("database disk image is malformed")
        return orig_abrir(ruta)

    monkeypatch.setattr(vectores_sqlite, "_abrir_conexion_sqlite_vec", mock_abrir)

    almacen = AlmacenVectoresSqlite(1, db_path=db_file)
    assert almacen.disponible() is True

    # Los archivos -wal y -shm viejos se movieron junto con la copia dañada
    copias_danadas = list(tmp_path.glob("vectores_wal.db.danado-*"))
    assert any(str(p).endswith("-wal") for p in copias_danadas)
    assert any(str(p).endswith("-shm") for p in copias_danadas)


def test_sqlite_vec_falla_rename_de_danado_levanta_error(tmp_path, monkeypatch):
    """R4: Si falla el rename del archivo dañado, levanta un RuntimeError en vez de reabrir el mismo archivo."""
    db_file = tmp_path / "vectores_rename_fail.db"
    db_file.write_text("CORRUPTO", encoding="utf-8")

    from aulento.db import vectores_sqlite

    vectores_sqlite._VERIFICADAS.clear()

    almacen = AlmacenVectoresSqlite(1, db_path=db_file)

    def mock_rename_falla(self, target):
        raise OSError("Acceso denegado simulado")

    monkeypatch.setattr(Path, "rename", mock_rename_falla)

    with pytest.raises(RuntimeError, match="No se pudo respaldar el archivo de vectores dañado"):
        almacen._get_conn()


def test_r6_sync_catalog_con_almacen_vacio_vuelve_a_indexar(tmp_path):
    """R6: sync_catalog con huella guardada en SQLite pero almacén de vectores vacío vuelve a indexar."""
    from conftest import cuenta_de_prueba

    from aulento.core.materiales import AlmacenDeMateriales

    db_file = tmp_path / "vectores_sync_catalog.db"

    with get_connection() as conn:
        cuenta = cuenta_de_prueba(conn, "usuario-sync-test")
        almacen_mat = AlmacenDeMateriales(conn, cuenta.id)
        mat = almacen_mat.guardar("apunte_redes.md", b"# Redes\nProtocolos TCP y UDP en detalle.")

        almacen = AlmacenVectoresSqlite(cuenta.id, db_path=db_file)
        rag = KnowledgeRAGService(cuenta.id, repository=almacen)

        # 1. Primera sincronización: indexa 1 material
        res1 = rag.sync_catalog(conn)
        assert res1["materiales_indexados"] == 1
        assert res1["salteados"] == 0
        assert almacen.count_embeddings() > 0

        # 2. Segunda sincronización inmediata: saltea porque la huella coincide y hay fragmentos
        res2 = rag.sync_catalog(conn)
        assert res2["salteados"] == 1
        assert res2["materiales_indexados"] == 0

        # 3. Vaciamos el almacén de vectores (simulando reemplazo o borrado) pero dejamos la huella en conn
        almacen.delete_by_source("material", str(mat["id"]))
        assert almacen.count_embeddings() == 0

        # 4. Tercera sincronización: detecta almacén vacío para esa fuente y vuelve a indexar
        res3 = rag.sync_catalog(conn)
        assert res3["materiales_indexados"] == 1
        assert res3["salteados"] == 0
        assert almacen.count_embeddings() > 0


def test_huella_con_almacen_vacio_reindexa(tmp_path):
    """R6: Si la huella está guardada pero el almacén no tiene fragmentos, se vuelve a indexar."""
    from conftest import cuenta_de_prueba

    db_file = tmp_path / "vectores_reindex.db"

    with get_connection() as conn:
        cuenta = cuenta_de_prueba(conn, "usuario-huella-test")
        almacen = AlmacenVectoresSqlite(cuenta.id, db_path=db_file)
        rag = KnowledgeRAGService(cuenta.id, repository=almacen)

        huella = _huella("modelo-test", "Texto del apunte")
        _guardar_hash(conn, cuenta.id, "note", "nota-1", huella)

        # El almacén no tiene fragmentos: _ya_indexado debe devolver False
        assert rag._ya_indexado(conn, "note", "nota-1", huella, "modelo-test") is False

        # Insertamos fragmento en el almacén
        almacen.insert_chunk("note", "nota-1", "Nota 1", "Texto del apunte", _vector_unitario(0), "modelo-test")

        # Ahora sí debe figurar como ya indexado
        assert rag._ya_indexado(conn, "note", "nota-1", huella, "modelo-test") is True


def test_fts5_rebuild_en_base_existente(tmp_path):
    """Punto 1: Base con fragmentos insertados antes de que exista la tabla FTS -> al abrir, search_bm25 los encuentra."""
    import sqlite3

    db_file = tmp_path / "vectores_preexistente.db"

    # Crear esquema previo sin tabla FTS ni triggers FTS
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE fragmentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_title TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            embedding_model TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        "INSERT INTO fragmentos (user_id, source_type, source_id, source_title, chunk_text, embedding_model) VALUES (1, 'note', 'n1', 'Kafka Intro', 'Apache Kafka es una plataforma distribuida de transmisión de eventos.', 'modelo-test');"
    )
    conn.commit()
    conn.close()

    # Al abrir con AlmacenVectoresSqlite, corre _asegurar_esquema()
    almacen = AlmacenVectoresSqlite(1, db_path=db_file)
    resultados = almacen.search_bm25("Kafka eventos", limit=5)
    assert len(resultados) == 1
    assert resultados[0]["source_id"] == "n1"

