"""Pruebas para el servicio de embeddings, búsqueda semántica y endpoints vectoriales."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pgvector_fake import COLUMNAS_DE_ORIGEN, ErrorDePostgres

from aulento.core.embedding_service import EMBEDDING_DIMENSIONS, EmbeddingService
from aulento.core.knowledge_rag import KnowledgeRAGService
from aulento.db.connection import get_connection
from aulento.db.postgres import (
    ALTA_DE_LA_COLUMNA_DE_DUENO,
    ALTA_DE_LA_COLUMNA_DE_MODELO,
    init_postgres_db,
)
from aulento.db.repository import (
    CursoRepository,
    LibroRepository,
    PlataformaRepository,
)
from aulento.db.vector_repository import VectorRepository
from aulento.mcp.agent import TutorDeMateriales
from aulento.mcp.server import create_study_mcp_server
from aulento.models.curso import CursoCreate
from aulento.models.libro import LibroCreate
from aulento.models.plataforma import PlataformaCreate
from aulento.web.app import create_app


@pytest.fixture
def client():
    """Cliente de pruebas FastAPI."""
    app = create_app()
    return TestClient(app)


def test_embedding_service_dimensions_and_fallback():
    """Verifica que el servicio de embeddings genere vectores de exactamente 768 dimensiones."""
    service = EmbeddingService()  # Sin pasarela: el generador local
    vector = service.generate_embedding("Arquitectura de microservicios y bases de datos distribuidas")
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert isinstance(vector[0], float)

    # Vector no nulo
    magnitude = sum(x * x for x in vector)
    assert 0.99 <= magnitude <= 1.01  # Norma unitaria


def test_embedding_service_batch():
    """Verifica la generación de embeddings por lote."""
    service = EmbeddingService()
    texts = ["Texto A", "Texto B", "Texto C"]
    batch = service.generate_batch(texts)
    assert len(batch) == 3
    for v in batch:
        assert len(v) == EMBEDDING_DIMENSIONS


def test_rag_chunking_logic():
    """Verifica la partición de texto con solapamiento."""
    long_text = "Palabra " * 300  # ~2400 caracteres
    chunks = KnowledgeRAGService._chunk_text(long_text, chunk_size=500, chunk_overlap=100)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 600


def test_vectors_api_status(client, pgvector_falso):
    """Verifica el endpoint de estado de PostgreSQL y pgvector."""
    res = client.get("/api/vectors/status")
    assert res.status_code == 200
    data = res.json()
    assert "postgres_connected" in data
    assert "embedding_dimensions" in data
    assert data["embedding_dimensions"] == 768


def test_vectors_api_search_when_disconnected(client):
    """Verifica que /api/vectors/search responda con error explicativo si PostgreSQL no está levantado."""
    res = client.post("/api/vectors/search", json={
        "query": "consulta semántica de prueba",
        "limit": 5,
    })
    # Si PostgreSQL no está corriendo en Docker, responde 503 con mensaje de ayuda
    if res.status_code == 503:
        assert "no está disponible" in res.json()["detail"].lower() or "no está conectado" in res.json()["detail"].lower()
        assert "docker" not in res.json()["detail"].lower()
    else:
        assert res.status_code == 200


def test_vectors_api_sync_catalog_when_disconnected(client):
    """Verifica que /api/vectors/sync-catalog maneje limpiamente el estado desconectado."""
    res = client.post("/api/vectors/sync-catalog")
    if res.status_code == 503:
        assert "no está disponible" in res.json()["detail"].lower() or "no está conectado" in res.json()["detail"].lower()
        assert "docker" not in res.json()["detail"].lower()
    else:
        assert res.status_code == 200



@pytest.mark.anyio
async def test_mcp_semantic_search_tool_registered():
    """Verifica que la herramienta study_semantic_search esté registrada en el servidor MCP."""
    server = create_study_mcp_server(read_only=True)
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "study_semantic_search" in tool_names


@pytest.fixture
def sin_escritura_en_pgvector(monkeypatch):
    """Si hay un pgvector real conectado, el test no debe escribir datos de prueba en él."""
    indexados = []

    def _index_document(self, **kwargs):
        indexados.append(kwargs["source_id"])
        return 1

    monkeypatch.setattr(KnowledgeRAGService, "index_document", _index_document)
    return indexados


def test_vectors_api_index_selection_con_un_material(client, pgvector_falso, sin_escritura_en_pgvector):
    """La indexación selectiva toma materiales subidos (048); la ruta de archivos de la nube ya no existe."""
    from conftest import cuenta_en

    from aulento.core.materiales import AlmacenDeMateriales

    material = AlmacenDeMateriales.con_conexion_propia(cuenta_en()).guardar("Arboles.md", b"Arboles de decision")

    res_batch = client.post("/api/vectors/index-selection", json={"items": [{"type": "material", "id": str(material["id"])}]})

    assert res_batch.status_code == 200
    assert res_batch.json()["total_indexed"] == 1
    assert sin_escritura_en_pgvector == [str(material["id"])]
    assert client.post("/api/vectors/index-selection", json={"items": [{"type": "cloud_file", "id": "x"}]}).status_code == 400
    assert client.post("/api/vectors/index-cloud-file", json={"provider": "gdrive", "file_id": "x"}).status_code in (404, 405)


# --- 033 · R11: la búsqueda semántica es por cuenta (sobre el doble `pgvector_fake`, nunca un Postgres real) ---

VECTOR = [1.0, 0.0, 0.0]
MODELO = "gemini-embedding-001"
ALTAS_DE_COLUMNAS = [ALTA_DE_LA_COLUMNA_DE_DUENO, ALTA_DE_LA_COLUMNA_DE_MODELO]


def _fragmento(
    repo: VectorRepository, texto: str, source_id: str = "nota-1", source_type: str = "obsidian_note", modelo: str = MODELO
) -> int:
    return repo.insert_chunk(source_type, source_id, f"Título de {texto}", texto, VECTOR, modelo, {"origen": texto})


def _catalogo(cuenta_id: int, marca: str) -> dict:
    """Una plataforma, un curso y un libro de la cuenta en la base aislada."""
    conn = get_connection()
    try:
        plataforma = PlataformaRepository(conn, cuenta_id).create(
            PlataformaCreate(nombre=f"Plataforma {marca}", url_acceso="https://ejemplo.org", icono_color="blue")
        )
        curso = CursoRepository(conn, cuenta_id).create(
            CursoCreate(plataforma_id=plataforma.id, nombre_curso=f"Curso {marca}", url_aula=f"https://ejemplo.org/{marca}")
        )
        libro = LibroRepository(conn, cuenta_id).create(LibroCreate(titulo=f"Libro {marca}", total_capitulos=10))
        return {"curso": curso.id, "libro": libro.id}
    finally:
        conn.close()


def test_r6_el_repositorio_y_el_servicio_de_vectores_no_se_construyen_sin_cuenta(pgvector_falso):
    with pytest.raises(TypeError):
        VectorRepository()
    with pytest.raises(TypeError):
        KnowledgeRAGService()
    for sin_cuenta in (None, 0, -1, "1", True):
        with pytest.raises(ValueError, match="cuenta dueña"):
            VectorRepository(sin_cuenta)
        with pytest.raises(ValueError, match="cuenta dueña"):
            KnowledgeRAGService(sin_cuenta)
    with pytest.raises(ValueError, match="misma cuenta"):
        KnowledgeRAGService(1, repository=VectorRepository(2))
    assert pgvector_falso.sentencias == []


def test_r11_cada_fragmento_se_guarda_con_su_dueno(pgvector_falso):
    _fragmento(VectorRepository(7), "apunte de la siete")
    _fragmento(VectorRepository(9, conn=pgvector_falso), "apunte de la nueve")

    assert [(fila["user_id"], fila["chunk_text"]) for fila in pgvector_falso.filas] == [
        (7, "apunte de la siete"),
        (9, "apunte de la nueve"),
    ]


def test_r11_buscar_contar_y_borrar_alcanzan_solo_los_fragmentos_de_la_cuenta(pgvector_falso):
    de_la_siete, de_la_nueve = VectorRepository(7), VectorRepository(9)
    _fragmento(de_la_siete, "siete A")
    _fragmento(de_la_siete, "siete B", source_id="libro-1", source_type="book")
    _fragmento(de_la_nueve, "nueve A")
    _fragmento(de_la_nueve, "nueve B", source_id="libro-1", source_type="book")
    pgvector_falso.sembrar_fila_sin_dueno(
        source_type="obsidian_note", source_id="nota-1", source_title="Vieja", chunk_text="sin dueño", embedding=VECTOR
    )
    pgvector_falso.sentencias.clear()

    assert [m["chunk_text"] for m in de_la_siete.search_similar(VECTOR, MODELO, limit=10)] == ["siete A", "siete B"]
    assert [m["chunk_text"] for m in de_la_nueve.search_similar(VECTOR, MODELO, limit=10, source_type="book")] == ["nueve B"]
    assert (de_la_siete.count_embeddings(), de_la_nueve.count_embeddings()) == (2, 2)
    assert (de_la_siete.count_embeddings("book"), VectorRepository(11).count_embeddings()) == (1, 0)

    assert de_la_siete.delete_by_source("obsidian_note", "nota-1") == 1

    assert [fila["chunk_text"] for fila in pgvector_falso.filas] == ["siete B", "nueve A", "nueve B", "sin dueño"]
    assert VectorRepository(11).delete_by_source("book", "libro-1") == 0
    assert len(pgvector_falso.filas) == 4
    sentencias_datos = [(s, p) for s, p in pgvector_falso.sentencias if not s.upper().startswith("SET ")]
    assert len(sentencias_datos) == 8
    for sentencia, parametros in sentencias_datos:
        assert "user_id = %s" in sentencia, sentencia
        assert {7, 9, 11} & {p for p in parametros if isinstance(p, int)}, sentencia


def test_r11_los_fragmentos_sin_dueno_no_los_ve_ni_los_borra_ninguna_cuenta(pgvector_falso):
    pgvector_falso.sembrar_fila_sin_dueno(
        source_type="book", source_id="1", source_title="Viejo", chunk_text="anterior a la 033", embedding=VECTOR
    )
    repo = VectorRepository(7)

    assert repo.search_similar(VECTOR, MODELO, limit=10) == []
    assert repo.count_embeddings() == 0
    assert repo.delete_by_source("book", "1") == 0
    assert len(pgvector_falso.filas) == 1


def test_set_local_falla_savepoint_lo_absorbe_y_consulta_devuelve_filas(pgvector_falso):
    """Punto 2: si SET LOCAL falla (pgvector viejo), el savepoint lo absorbe y el cursor de datos posterior corre y devuelve filas."""
    repo = VectorRepository(user_id=7)
    _fragmento(repo, "fragmento recuperado a pesar de fallo en set local")

    cursor_original = pgvector_falso.cursor

    class CursorConFalloSet:
        def __init__(self, c):
            self._c = c

        def __enter__(self):
            self._c.__enter__()
            return self

        def __exit__(self, *args):
            return self._c.__exit__(*args)

        def execute(self, sql, params=()):
            if "SET LOCAL" in sql.upper():
                raise ErrorDePostgres("unrecognized configuration parameter 'hnsw.iterative_scan'")
            return self._c.execute(sql, params)

        def fetchall(self):
            return self._c.fetchall()

        def fetchone(self):
            return self._c.fetchone()

    pgvector_falso.cursor = lambda: CursorConFalloSet(cursor_original())

    resultados = repo.search_similar(VECTOR, MODELO, limit=5)
    assert len(resultados) == 1
    assert resultados[0]["chunk_text"] == "fragmento recuperado a pesar de fallo en set local"



def test_r11_reindexar_una_fuente_reemplaza_solo_los_fragmentos_de_la_cuenta(pgvector_falso):
    """Dos cuentas indexan la misma fuente (mismo tipo e identificador): reindexar una no toca la otra."""
    de_la_siete, de_la_nueve = KnowledgeRAGService(7), KnowledgeRAGService(9)
    de_la_siete.index_document("cloud_file", "archivo-1", "Archivo", "Texto de la siete, primera versión")
    de_la_nueve.index_document("cloud_file", "archivo-1", "Archivo", "Texto de la nueve")

    de_la_siete.index_document("cloud_file", "archivo-1", "Archivo", "Texto de la siete, segunda versión")

    assert sorted((fila["user_id"], fila["chunk_text"]) for fila in pgvector_falso.filas) == [
        (7, "Texto de la siete, segunda versión"),
        (9, "Texto de la nueve"),
    ]
    assert [m["chunk_text"] for m in de_la_nueve.search("texto", min_similarity=-1.0)] == ["Texto de la nueve"]
    assert de_la_siete.get_stats()["total_embeddings"] == 1


def test_r11_sincronizar_el_catalogo_indexa_solo_los_materiales_y_notas_de_la_cuenta(pgvector_falso, cuenta, otra_cuenta):
    from aulento.core.materiales import AlmacenDeMateriales
    AlmacenDeMateriales.con_conexion_propia(cuenta).guardar("propio.md", b"Texto de material propio")
    AlmacenDeMateriales.con_conexion_propia(otra_cuenta).guardar("ajeno.md", b"Texto de material ajeno")
    conn = get_connection()
    try:
        resultado = KnowledgeRAGService(cuenta).sync_catalog(conn)
    finally:
        conn.close()

    assert resultado["indexados"] >= 1
    assert any(fila["source_title"] == "propio.md" for fila in pgvector_falso.filas)
    assert not any(fila["source_title"] == "ajeno.md" for fila in pgvector_falso.filas)
    assert {fila["user_id"] for fila in pgvector_falso.filas} == {cuenta}


@pytest.mark.parametrize(("ruta", "clave", "que"), [("index-book", "libro", "Libro"), ("index-course", "curso", "Curso")])
def test_r11_reindexar_un_libro_o_un_curso_ajeno_responde_404(client, pgvector_falso, cuenta, otra_cuenta, ruta, clave, que):
    propio, ajeno = _catalogo(cuenta, "propio"), _catalogo(otra_cuenta, "ajeno")

    con_ajeno = client.post(f"/api/vectors/{ruta}/{ajeno[clave]}")
    con_inexistente = client.post(f"/api/vectors/{ruta}/987654")

    assert (con_ajeno.status_code, con_inexistente.status_code) == (404, 404)
    assert con_ajeno.json() == {"detail": f"{que} con ID {ajeno[clave]} no encontrado."}
    assert con_inexistente.json() == {"detail": f"{que} con ID 987654 no encontrado."}
    assert pgvector_falso.filas == []

    con_propio = client.post(f"/api/vectors/{ruta}/{propio[clave]}")
    assert con_propio.status_code == 200, con_propio.text
    assert [(fila["user_id"], fila["source_title"]) for fila in pgvector_falso.filas] == [(cuenta, f"{que} propio")]


@pytest.mark.parametrize(("tipo", "clave", "que"), [("book", "libro", "Libro"), ("course", "curso", "Curso")])
def test_r11_una_seleccion_con_un_libro_o_un_curso_ajeno_no_indexa_nada(
    client, pgvector_falso, cuenta, otra_cuenta, tipo, clave, que
):
    propio, ajeno = _catalogo(cuenta, "propio"), _catalogo(otra_cuenta, "ajeno")
    propios = [{"type": "book", "id": str(propio["libro"])}, {"type": "course", "id": str(propio["curso"])}]

    con_ajeno = client.post("/api/vectors/index-selection", json={"items": [*propios, {"type": tipo, "id": str(ajeno[clave])}]})
    con_inexistente = client.post("/api/vectors/index-selection", json={"items": [*propios, {"type": tipo, "id": "987654"}]})

    assert (con_ajeno.status_code, con_inexistente.status_code) == (404, 404)
    assert con_ajeno.json() == {"detail": f"{que} con ID {ajeno[clave]} no encontrado."}
    assert pgvector_falso.filas == []

    solo_propios = client.post("/api/vectors/index-selection", json={"items": propios})
    assert solo_propios.status_code == 200 and solo_propios.json()["total_indexed"] == 2
    assert {fila["user_id"] for fila in pgvector_falso.filas} == {cuenta}


def test_r11_una_seleccion_con_un_tipo_o_un_identificador_invalido_sigue_respondiendo_400(client, pgvector_falso):
    de_otro_tipo = client.post("/api/vectors/index-selection", json={"items": [{"type": "video", "id": "1"}]})
    sin_numero = client.post("/api/vectors/index-selection", json={"items": [{"type": "book", "id": "abc"}]})

    assert (de_otro_tipo.status_code, sin_numero.status_code) == (400, 400)
    assert pgvector_falso.filas == []


def test_r11_la_api_indexa_busca_y_cuenta_para_la_cuenta_de_la_sesion(client, pgvector_falso, cuenta, otra_cuenta):
    KnowledgeRAGService(otra_cuenta).index_document("obsidian_note", "nota-1", "Apunte ajeno", "Apunte de la otra cuenta")

    alta = client.post(
        "/api/vectors/index",
        json={"source_type": "obsidian_note", "source_id": "nota-1", "source_title": "Apunte propio", "content": "Apunte de la cuenta"},
    )
    busqueda = client.post("/api/vectors/search", json={"query": "apunte", "limit": 50, "min_similarity": 0.0})

    assert alta.status_code == 201, alta.text
    assert [m["source_title"] for m in busqueda.json()["matches"]] == ["Apunte propio"]
    assert client.get("/api/vectors/status").json()["total_embeddings"] == 1
    assert [(fila["user_id"], fila["source_title"]) for fila in pgvector_falso.filas] == [
        (otra_cuenta, "Apunte ajeno"),
        (cuenta, "Apunte propio"),
    ]


def test_r11_el_alta_de_la_columna_de_dueno_es_idempotente_y_conserva_los_fragmentos(pgvector_falso):
    """Sobre el esquema anterior (sin `user_id`), inicializar agrega la columna; repetirlo no falla ni pierde filas."""
    pgvector_falso.columnas = set(COLUMNAS_DE_ORIGEN)
    pgvector_falso.sembrar_fila_sin_dueno(
        source_type="book", source_id="1", source_title="Viejo", chunk_text="anterior a la 033", embedding=VECTOR
    )
    with pytest.raises(ErrorDePostgres, match='"user_id" does not exist'):
        _fragmento(VectorRepository(7), "antes de inicializar")

    assert init_postgres_db(pgvector_falso) is True
    assert init_postgres_db() is True

    assert "user_id" in pgvector_falso.columnas and "idx_knowledge_embeddings_user_id" in pgvector_falso.indices
    altas = [s for s, _ in pgvector_falso.sentencias if s.upper().startswith("ALTER TABLE")]
    assert altas == ALTAS_DE_COLUMNAS * 2
    assert ALTA_DE_LA_COLUMNA_DE_DUENO == "ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS user_id INTEGER;"
    _fragmento(VectorRepository(7), "después de inicializar")
    assert [fila.get("user_id") for fila in pgvector_falso.filas] == [None, 7]
    assert VectorRepository(7).count_embeddings() == 1


def test_r11_un_contenedor_nuevo_nace_con_la_columna_de_dueno(pgvector_falso):
    """El script con el que Docker crea la base deja el mismo esquema que `init_postgres_db`."""
    script = (Path(__file__).parents[1] / "docker" / "init-db" / "01-init.sql").read_text(encoding="utf-8")
    sin_comentarios = "\n".join(linea.split("--")[0] for linea in script.splitlines())
    with pgvector_falso.cursor() as cursor:
        for sentencia in filter(str.strip, sin_comentarios.split(";")):
            cursor.execute(sentencia + ";")
    del_script = (set(pgvector_falso.columnas), set(pgvector_falso.indices))

    _fragmento(VectorRepository(7), "en un contenedor nuevo")
    assert init_postgres_db(pgvector_falso) is True

    assert [fila["user_id"] for fila in pgvector_falso.filas] == [7]
    assert "user_id" in del_script[0] and "idx_knowledge_embeddings_user_id" in del_script[1]
    assert set(pgvector_falso.columnas) == del_script[0]


def test_r11_inicializar_por_la_api_agrega_la_columna_de_dueno(client, pgvector_falso):
    pgvector_falso.columnas = set(COLUMNAS_DE_ORIGEN)

    assert client.post("/api/vectors/init").status_code == 200
    assert client.post("/api/vectors/init").status_code == 200
    assert "user_id" in pgvector_falso.columnas


def _altas_de_columna(falso) -> list[str]:
    return [s for s, _ in falso.sentencias if s.upper().startswith("ALTER TABLE")]


def test_r11_un_almacen_anterior_a_la_columna_de_dueno_queda_utilizable_sin_inicializar(pgvector_falso):
    """Un contenedor creado antes de la 033 no tiene `user_id`: el primer uso la agrega, sin pasar por `init`."""
    pgvector_falso.columnas = set(COLUMNAS_DE_ORIGEN)
    pgvector_falso.sembrar_fila_sin_dueno(
        source_type="book", source_id="1", source_title="Viejo", chunk_text="anterior a la 033", embedding=VECTOR
    )
    servicio = KnowledgeRAGService(7)

    assert servicio.index_document("obsidian_note", "nota-1", "Apunte", "Apunte sobre particionado") == 1

    assert "user_id" in pgvector_falso.columnas and "idx_knowledge_embeddings_user_id" in pgvector_falso.indices
    assert [fila.get("user_id") for fila in pgvector_falso.filas] == [None, 7]
    assert servicio.get_stats()["total_embeddings"] == 1
    assert [r["source_title"] for r in servicio.search("particionado", min_similarity=0.0)] == ["Apunte"]
    assert KnowledgeRAGService(9).get_stats()["total_embeddings"] == 0
    # Una vez por proceso: ni los usos siguientes ni otra cuenta vuelven a tocar el esquema
    assert _altas_de_columna(pgvector_falso) == ALTAS_DE_COLUMNAS


def test_r11_el_estado_de_un_almacen_anterior_cuenta_bien_sin_inicializar(client, pgvector_falso, cuenta):
    """Antes, `GET /api/vectors/status` tragaba el error de la columna que faltaba y mostraba 0 para siempre."""
    pgvector_falso.columnas = set(COLUMNAS_DE_ORIGEN)

    antes = client.get("/api/vectors/status")
    alta = client.post(
        "/api/vectors/index",
        json={"source_type": "obsidian_note", "source_id": "nota-1", "source_title": "Apunte", "content": "Apunte de la cuenta"},
    )

    assert antes.status_code == 200 and antes.json()["postgres_connected"] is True
    assert "user_id" in pgvector_falso.columnas
    assert alta.status_code == 201, alta.text
    assert client.get("/api/vectors/status").json()["total_embeddings"] == 1
    assert [fila["user_id"] for fila in pgvector_falso.filas] == [cuenta]
    assert not any(s.upper().startswith(("CREATE TABLE", "CREATE EXTENSION")) for s, _ in pgvector_falso.sentencias)


def test_r11_un_postgres_sin_la_tabla_no_recibe_el_alta_de_la_columna_hasta_que_se_inicializa(pgvector_falso):
    pgvector_falso.sin_tabla = True
    servicio = KnowledgeRAGService(7)

    assert servicio.is_ready() is True
    assert servicio.is_ready() is True
    assert _altas_de_columna(pgvector_falso) == []

    assert init_postgres_db() is True
    assert servicio.index_document("obsidian_note", "nota-1", "Apunte", "Apunte sobre particionado") == 1
    assert [fila["user_id"] for fila in pgvector_falso.filas] == [7]


def test_r11_las_estadisticas_no_ocultan_un_error_del_almacen(pgvector_falso, monkeypatch):
    servicio = KnowledgeRAGService(7)

    def fallar():
        raise ErrorDePostgres('column "user_id" does not exist')

    monkeypatch.setattr(servicio.repo, "count_embeddings", fallar)

    with pytest.raises(ErrorDePostgres, match="user_id"):
        servicio.get_stats()


def test_r11_con_el_almacen_apagado_las_estadisticas_dan_cero_sin_fallar(sin_postgres_real):
    estadisticas = KnowledgeRAGService(7, repository=VectorRepository(7)).get_stats()

    assert estadisticas["postgres_connected"] is False
    assert estadisticas["total_embeddings"] == 0
    assert estadisticas["vector_extension"] == "disconnected"


def test_r11_si_el_alta_de_la_columna_falla_el_error_no_se_disfraza_de_almacen_apagado(pgvector_falso, monkeypatch):
    from aulento.core import knowledge_rag

    def fallar():
        raise ErrorDePostgres("must be owner of table knowledge_embeddings")

    monkeypatch.setattr(knowledge_rag, "asegurar_columna_de_dueno", fallar)

    with pytest.raises(ErrorDePostgres, match="must be owner"):
        KnowledgeRAGService(7).is_ready()


def test_r11_el_agente_consulta_solo_los_fragmentos_de_su_cuenta(pgvector_falso):
    KnowledgeRAGService(7).index_document("obsidian_note", "nota-1", "Apunte de la siete", "Apunte sobre particionado")
    KnowledgeRAGService(9).index_document("obsidian_note", "nota-1", "Apunte de la nueve", "Apunte sobre particionado")

    def titulos(tutor: TutorDeMateriales) -> list[str]:
        return [fragmento.nombre for fragmento in tutor.retrieve_context("particionado", provider="vector")]

    assert titulos(TutorDeMateriales(user_id=7)) == ["[OBSIDIAN_NOTE] Apunte de la siete"]
    assert titulos(TutorDeMateriales(user_id=9)) == ["[OBSIDIAN_NOTE] Apunte de la nueve"]
    # Sin cuenta no hay agente (034): antes se podía armar uno que no consultaba fragmentos
    with pytest.raises(TypeError):
        TutorDeMateriales()


def test_r11_la_herramienta_mcp_busca_solo_en_los_fragmentos_de_su_cuenta(pgvector_falso, operar_por_mcp):
    import anyio

    KnowledgeRAGService(7).index_document("obsidian_note", "nota-1", "Apunte de la siete", "Apunte sobre particionado")
    KnowledgeRAGService(9).index_document("obsidian_note", "nota-1", "Apunte de la nueve", "Apunte sobre particionado")
    servidor = create_study_mcp_server(read_only=True)

    async def buscar() -> str:
        operar_por_mcp(9)
        llamada = await servidor.call_tool("study_semantic_search", {"query": "particionado", "min_similarity": 0.0})
        return llamada.content[0].text

    respuesta = anyio.run(buscar)

    assert "Apunte de la nueve" in respuesta and "Apunte de la siete" not in respuesta
