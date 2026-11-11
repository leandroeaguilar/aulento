"""Tests de seguridad y auditoría: recursos y archivos (066, T3 y T4: R8, R9, R11, R12)."""

import io
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from materiales_de_prueba import pdf_con_lineas
from pypdf import PageObject, PdfReader, PdfWriter

from aulento.config import dir_de_cuenta
from aulento.core import permisos
from aulento.core.extensiones import Extension, registrar_extensiones
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.mcp.pdf_text import (
    MAX_PAGINAS,
    PdfSinTextoError,
    extraer_texto_pdf,
)
from aulento.roadmap.syllabus_ingestor import SyllabusIngestor
from aulento.vault.rutas import (
    CarpetaDeVaultInvalida,
    fijar_vault_externo,
    vault_de_la_cuenta,
)
from aulento.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_recursos.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    monkeypatch.setenv("AULENTO_DATA_DIR", str(tmp_path / "datos"))

    conn = get_connection(db_file)
    init_db(conn)
    conn.close()

    app = create_app()
    return TestClient(app)


# --- R8: Syllabus import y compare-pdf acotados y seguros ---


def test_r8_import_syllabus_file_rechaza_cuerpo_mayor_25mb(client):
    """POST /api/roadmap/import-syllabus-file responde 413 si el Content-Length supera 25 MB."""
    exceso = 26 * 1024 * 1024
    res = client.post(
        "/api/roadmap/import-syllabus-file",
        data={"titulo": "Curso Grande"},
        files={"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")},
        headers={"content-length": str(exceso)},
    )
    assert res.status_code == 413, f"Esperaba 413 pero obtuve {res.status_code}: {res.text}"


def test_r8_compare_pdf_rechaza_cuerpo_mayor_25mb(client):
    """POST /api/roadmap/{id}/compare-pdf responde 413 si el Content-Length supera 25 MB."""
    # Crear una ruta básica primero
    res_crear = client.post(
        "/api/roadmap",
        json={
            "titulo": "Ruta Base",
            "modulos": [{"titulo": "Mod 1", "orden": 1, "temas": [{"titulo": "Tema 1", "orden": 1}]}],
        },
    )
    assert res_crear.status_code == 200, res_crear.text
    ruta_id = res_crear.json()["id"]

    exceso = 26 * 1024 * 1024
    res = client.post(
        f"/api/roadmap/{ruta_id}/compare-pdf",
        files={"file": ("syllabus.pdf", b"%PDF-1.4...", "application/pdf")},
        headers={"content-length": str(exceso)},
    )
    assert res.status_code == 413, f"Esperaba 413 pero obtuve {res.status_code}: {res.text}"


def test_r8_syllabus_parser_rapido_con_bomba_stream():
    """El extractor de temarios no usa regex cuadrática y termina rápido ante cadenas repetidas."""
    bomba = b"stream\n" * 5000
    t0 = time.monotonic()
    resultado = SyllabusIngestor.extract_text_from_pdf_bytes(bomba)
    duracion = time.monotonic() - t0
    assert duracion < 0.5, f"La extracción tardó {duracion:.2f}s (posible regex cuadrática)"
    assert resultado == "" or isinstance(resultado, str)


def test_r8_subida_streaming_mayor_25mb_con_content_length_falso_se_corta_en_lectura(client):
    """Si el Content-Length es falso o menor, la lectura por bloques se corta al superar 25 MB."""
    exceso_bytes = b"%PDF-1.4 " + (b"A" * (26 * 1024 * 1024))
    res = client.post(
        "/api/roadmap/import-syllabus-file",
        data={"titulo": "Syllabus Gigante"},
        files={"file": ("gigante.pdf", io.BytesIO(exceso_bytes), "application/pdf")},
        headers={"content-length": "100"},
    )
    assert res.status_code == 413, f"Esperaba 413 pero obtuve {res.status_code}: {res.text}"
    assert "supera el tamaño máximo permitido" in res.text


def test_r8_extraccion_pdf_corre_en_threadpool(client):
    """La extracción de texto del PDF en import-syllabus-file y compare-pdf corre en run_in_threadpool."""
    from starlette.concurrency import run_in_threadpool

    funciones_ejecutadas_en_threadpool = []

    async def espia_threadpool(func, *args, **kwargs):
        funciones_ejecutadas_en_threadpool.append(func)
        return await run_in_threadpool(func, *args, **kwargs)

    with patch("aulento.web.routes.roadmap.run_in_threadpool", side_effect=espia_threadpool):
        pdf_bytes = pdf_con_lineas(["# Tema de Prueba", "Contenido relevante para el temario."])

        # 1. import-syllabus-file
        res_import = client.post(
            "/api/roadmap/import-syllabus-file",
            data={"titulo": "Ruta Threadpool", "create_direct": True},
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )
        assert res_import.status_code == 200, res_import.text
        assert SyllabusIngestor.extract_text_from_pdf_bytes in funciones_ejecutadas_en_threadpool

        # 2. compare-pdf
        ruta_id = res_import.json()["roadmap"]["id"]
        funciones_ejecutadas_en_threadpool.clear()
        res_comp = client.post(
            f"/api/roadmap/{ruta_id}/compare-pdf",
            files={"file": ("comp.pdf", pdf_bytes, "application/pdf")},
        )
        assert res_comp.status_code == 200, res_comp.text
        assert any(
            getattr(f, "__name__", "") == "compare_syllabus" or "compare" in str(f)
            for f in funciones_ejecutadas_en_threadpool
        )


# --- R9: Topes en extracción de PDF (páginas, bytes decodificados, plazo) ---


def test_r9_extraer_texto_pdf_tope_paginas():
    """Un PDF con más páginas que MAX_PAGINAS falla con PdfSinTextoError."""
    escritor = PdfWriter()
    una_pag = PdfReader(io.BytesIO(pdf_con_lineas(["Texto de prueba"]))).pages[0]
    for _ in range(MAX_PAGINAS + 10):
        escritor.add_page(una_pag)
    salida = io.BytesIO()
    escritor.write(salida)
    pdf_muchas_paginas = salida.getvalue()

    with pytest.raises(PdfSinTextoError, match="páginas"):
        extraer_texto_pdf(pdf_muchas_paginas, max_caracteres=100_000)


def test_r9_extraer_texto_pdf_tope_bytes_decodificados_totales(monkeypatch):
    """Un PDF cuyas páginas acumulan más bytes decodificados que MAX_BYTES_DECODIFICADOS_TOTALES falla."""
    import aulento.mcp.pdf_text as pdf_modulo

    monkeypatch.setattr(pdf_modulo, "MAX_BYTES_DECODIFICADOS_TOTALES", 20)
    datos = pdf_con_lineas(["Linea de texto que supera el tope total acumulado cuando son varias lineas"])
    with pytest.raises(PdfSinTextoError, match="decodificado"):
        extraer_texto_pdf(datos, max_caracteres=100_000)


def test_r9_extraer_texto_pdf_tope_tiempo(monkeypatch):
    """Si la extracción supera el plazo de tiempo límite, falla con PdfSinTextoError."""
    import aulento.mcp.pdf_text as pdf_modulo

    monkeypatch.setattr(pdf_modulo, "MAX_SEGUNDOS_EXTRACCION", 0.001)

    # Simular que extract_text tarda un poco
    def extract_lento(self, *args, **kwargs):
        time.sleep(0.05)
        return "texto"

    monkeypatch.setattr(PageObject, "extract_text", extract_lento)
    datos = pdf_con_lineas(["Linea uno", "Linea dos"])
    with pytest.raises(PdfSinTextoError, match="tiempo límite"):
        extraer_texto_pdf(datos, max_caracteres=100_000)


# --- R11: Vault externo sin temp/proc/sys/dev y exportación en carpeta de cuenta ---


def test_r11_vault_externo_no_admite_tempdir_ni_proc_sys_dev(tmp_path, monkeypatch):
    """Un vault externo no puede apuntar al directorio temporal del sistema ni a /proc, /sys o /dev."""
    db_file = tmp_path / "vault_test.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    conn.execute(
        "INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, rol, activo, creado_en) "
        "VALUES (1, 'usuario1', 'hash', 'admin', 1, '2026-01-01 00:00:00');"
    )
    conn.commit()

    # _carpetas_del_servidor solo contiene las carpetas del servidor (datos y base)
    from aulento.vault.rutas import (
        _carpetas_del_servidor,
        _es_temporal_o_del_sistema,
    )
    carpetas_servidor = _carpetas_del_servidor()
    assert Path(tempfile.gettempdir()).resolve() not in carpetas_servidor

    # Directorio temporal del sistema es rechazado
    temp_dir = Path(tempfile.gettempdir()).resolve()
    assert _es_temporal_o_del_sistema(temp_dir)
    with pytest.raises(CarpetaDeVaultInvalida, match="servidor"):
        fijar_vault_externo(conn, user_id=1, carpeta=temp_dir)

    # Ancestro del directorio temporal es rechazado
    ancestro_temp = temp_dir.parent
    assert _es_temporal_o_del_sistema(ancestro_temp)
    with pytest.raises(CarpetaDeVaultInvalida, match="servidor"):
        fijar_vault_externo(conn, user_id=1, carpeta=ancestro_temp)

    # Subcarpeta dentro del directorio temporal del sistema SÍ está permitida
    sub_temp = temp_dir / "sub_vault_test_r11"
    sub_temp.mkdir(exist_ok=True)
    try:
        assert not _es_temporal_o_del_sistema(sub_temp)
        fijada = fijar_vault_externo(conn, user_id=1, carpeta=sub_temp)
        assert fijada == sub_temp.resolve()
        assert Path(vault_de_la_cuenta(conn, 1)).resolve() == sub_temp.resolve()
    finally:
        sub_temp.rmdir()

    # Carpetas virtuales de sistema si son absolutas y existen
    for ruta_prohibida in ("/tmp", "/proc", "/sys", "/dev"):
        p = Path(ruta_prohibida)
        if p.is_absolute() and p.is_dir():
            with pytest.raises(CarpetaDeVaultInvalida, match="servidor"):
                fijar_vault_externo(conn, user_id=1, carpeta=ruta_prohibida)
    conn.close()


def test_r11_export_vault_zip_se_crea_en_carpeta_de_cuenta(client, tmp_path):
    """GET /api/vault/export.zip arma el zip dentro del directorio de la cuenta (usuarios/<id>), no en /tmp."""
    directorio_creado = None
    mkstemp_original = tempfile.mkstemp

    def mkstemp_espia(*args, **kwargs):
        nonlocal directorio_creado
        directorio_creado = kwargs.get("dir")
        return mkstemp_original(*args, **kwargs)

    with patch("tempfile.mkstemp", side_effect=mkstemp_espia):
        res = client.get("/api/vault/export.zip")
        assert res.status_code == 200

    assert directorio_creado is not None, "No se llamó a mkstemp con un directorio"
    carpeta_esperada = dir_de_cuenta(1).resolve()
    assert Path(directorio_creado).resolve() == carpeta_esperada, (
        f"El zip se creó en {directorio_creado}, se esperaba en {carpeta_esperada}"
    )


# --- R12: mcp serve registra extensiones configuradas ---


def test_r12_registrar_extensiones_helper():
    """registrar_extensiones registra validadores, permisos y suscripciones, y los limpia al desregistrar."""
    regla_invocada = False

    def regla_test(*, user_id: int, accion: str, conn, **kwargs):
        nonlocal regla_invocada
        regla_invocada = True
        return permisos.Decision(False, "Bloqueado por prueba")

    ext = Extension(
        nombre="test_ext_mcp",
        permisos=(regla_test,),
    )

    desregistrar = registrar_extensiones([ext])
    try:
        conn = get_connection(":memory:")
        init_db(conn)
        decision = permisos.puede(1, permisos.CREAR_CURSO, conn)
        conn.close()
        assert not decision.permitido
        assert decision.motivo == "Bloqueado por prueba"
        assert regla_invocada
    finally:
        desregistrar()

    # Tras desregistrar, el permiso ya no está activo
    conn = get_connection(":memory:")
    init_db(conn)
    decision = permisos.puede(1, permisos.CREAR_CURSO, conn)
    conn.close()
    assert decision.permitido


# Helper público en el módulo para que AULENTO_EXTENSIONS lo importe
def extension_prueba_mcp_bloqueadora() -> Extension:
    def regla_mcp(*, user_id: int, accion: str, conn, **kwargs):
        return permisos.Decision(False, "Bloqueado por extension_prueba_mcp")

    return Extension(nombre="prueba_mcp_bloqueo", permisos=(regla_mcp,))


def test_r12_cmd_mcp_serve_registra_extensiones_en_el_proceso(monkeypatch, tmp_path):
    """cmd_mcp_serve carga extensiones de AULENTO_EXTENSIONS y permisos.puede niega dentro del proceso."""
    from typer.testing import CliRunner

    from aulento.cli.mcp_commands import mcp_app

    db_file = tmp_path / "mcp_serve_test.db"
    conn = get_connection(db_file)
    init_db(conn)
    conn.execute(
        "INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, rol, activo, creado_en) "
        "VALUES (1, 'testuser', 'hash', 'admin', 1, '2026-01-01 00:00:00');"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    monkeypatch.setenv("AULENTO_USER", "testuser")
    monkeypatch.setenv(
        "AULENTO_EXTENSIONS",
        "tests.test_seguridad_auditoria_recursos:extension_prueba_mcp_bloqueadora",
    )

    estado_dentro_del_servidor = {}

    def fake_run_stdio_server(*, user_id: int, read_only: bool):
        c = get_connection(db_file)
        try:
            decision = permisos.puede(user_id, permisos.CREAR_CURSO, c)
            estado_dentro_del_servidor["permitido_stdio"] = decision.permitido
            estado_dentro_del_servidor["motivo_stdio"] = decision.motivo
        finally:
            c.close()

    def fake_run_sse_server(**kwargs):
        c = get_connection(db_file)
        try:
            decision = permisos.puede(1, permisos.CREAR_CURSO, c)
            estado_dentro_del_servidor["permitido_sse"] = decision.permitido
            estado_dentro_del_servidor["motivo_sse"] = decision.motivo
        finally:
            c.close()

    monkeypatch.setattr("aulento.cli.mcp_commands.run_stdio_server", fake_run_stdio_server)
    monkeypatch.setattr("aulento.cli.mcp_commands.run_sse_server", fake_run_sse_server)

    runner = CliRunner()

    # 1. Modo stdio
    res_stdio = runner.invoke(mcp_app, ["serve", "--transport", "stdio"])
    assert res_stdio.exit_code == 0, res_stdio.output
    assert estado_dentro_del_servidor.get("permitido_stdio") is False
    assert estado_dentro_del_servidor.get("motivo_stdio") == "Bloqueado por extension_prueba_mcp"

    # Al terminar cmd_mcp_serve, las extensiones fueron desregistradas
    c_post1 = get_connection(db_file)
    try:
        assert permisos.puede(1, permisos.CREAR_CURSO, c_post1).permitido
    finally:
        c_post1.close()

    # 2. Modo http / sse
    res_http = runner.invoke(mcp_app, ["serve", "--transport", "http"])
    assert res_http.exit_code == 0, res_http.output
    assert estado_dentro_del_servidor.get("permitido_sse") is False
    assert estado_dentro_del_servidor.get("motivo_sse") == "Bloqueado por extension_prueba_mcp"

    # Al terminar cmd_mcp_serve, las extensiones fueron desregistradas nuevamente
    c_post2 = get_connection(db_file)
    try:
        assert permisos.puede(1, permisos.CREAR_CURSO, c_post2).permitido
    finally:
        c_post2.close()


# --- Correcciones 066-2 (agy066b) ---


def test_import_syllabus_file_pdf_supera_tope_paginas_responde_422_sin_extractor_lineal(client, monkeypatch):
    """Bug 1: Si un PDF supera el tope de páginas, responde 422 con el motivo y no cae al extractor lineal."""
    import aulento.mcp.pdf_text as pdf_modulo
    from aulento.roadmap.syllabus_ingestor import SyllabusIngestor

    monkeypatch.setattr(pdf_modulo, "MAX_PAGINAS", 2)
    datos_pdf = pdf_con_lineas(["Pagina 1\n# Modulo 1\n- Tema 1"])
    escritor = PdfWriter()
    una_pag = PdfReader(io.BytesIO(datos_pdf)).pages[0]
    for _ in range(3):
        escritor.add_page(una_pag)
    salida = io.BytesIO()
    escritor.write(salida)
    pdf_3_paginas = salida.getvalue()

    lineal_invocado = False
    original_lineal = SyllabusIngestor._extraer_texto_lineal_acotado

    def spy_lineal(pdf_b):
        nonlocal lineal_invocado
        lineal_invocado = True
        return original_lineal(pdf_b)

    monkeypatch.setattr(SyllabusIngestor, "_extraer_texto_lineal_acotado", spy_lineal)

    res = client.post(
        "/api/roadmap/import-syllabus-file",
        data={"titulo": "Syllabus Largo"},
        files={"file": ("largo.pdf", pdf_3_paginas, "application/pdf")},
    )

    assert res.status_code == 422, f"Se esperaba 422 pero fue {res.status_code}: {res.text}"
    assert "supera el máximo permitido de 2 páginas" in res.json()["detail"]
    assert not lineal_invocado, "No se debió invocar el extractor lineal de fallback"


def test_materiales_permisos_denegados_no_deja_transaccion_abierta(tmp_path, monkeypatch):
    """Bug 2: Si permisos.exigir deniega la subida, la transacción iniciada se revierte y conn.in_transaction es False."""
    from aulento.core.materiales import AlmacenDeMateriales
    from aulento.core.permisos import AccionNoPermitida

    db_file = tmp_path / "test_mat_tx.db"
    conn = get_connection(db_file)
    init_db(conn)
    conn.execute(
        "INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, rol, activo, creado_en) "
        "VALUES (1, 'u_mat', 'hash', 'usuario', 1, '2026-01-01');"
    )
    conn.commit()

    almacen = AlmacenDeMateriales(conn, 1)

    def denegar_subida(*args, **kwargs):
        raise AccionNoPermitida("subir_material", "Tope de plan excedido")

    monkeypatch.setattr(permisos, "exigir", denegar_subida)

    with pytest.raises(AccionNoPermitida):
        almacen._registrar("doc.txt", ".txt", 100, "sha256dummy", "doc.txt", "texto")

    assert not conn.in_transaction, "conn.in_transaction debería ser False tras el rollback por negación de permisos"
    conn.close()


def test_create_con_transaccion_externa_no_la_confirma(tmp_path):
    """Bug 3: Si hay una transacción externa abierta, CursoRepository.create, AlmacenDeMateriales y create_roadmap no la confirman."""
    from aulento.core.materiales import AlmacenDeMateriales
    from aulento.db.repository import CursoRepository, PlataformaRepository
    from aulento.db.roadmap_repository import RoadmapRepository
    from aulento.models.curso import CursoCreate, EstadoCurso, PrioridadCurso
    from aulento.models.plataforma import PlataformaCreate
    from aulento.models.roadmap import (
        RoadmapCreate,
        RoadmapModuleCreate,
        RoadmapTopicCreate,
    )

    db_file = tmp_path / "test_tx_ext.db"
    conn = get_connection(db_file)
    init_db(conn)
    conn.execute(
        "INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, rol, activo, creado_en) "
        "VALUES (1, 'u_tx', 'hash', 'usuario', 1, '2026-01-01');"
    )
    plat_repo = PlataformaRepository(conn, 1)
    plat = plat_repo.create(PlataformaCreate(nombre="Plat TX", url_acceso="https://plat.tx"))
    conn.commit()

    # 1. CursoRepository.create
    curso_repo = CursoRepository(conn, 1)
    conn.execute("BEGIN IMMEDIATE;")
    curso = curso_repo.create(
        CursoCreate(
            plataforma_id=plat.id,
            nombre_curso="Curso No Confirmado",
            url_aula="https://plat.tx/aula",
            progreso_pct=0.0,
            estado=EstadoCurso.EN_CURSO,
            prioridad=PrioridadCurso.MEDIA,
        )
    )
    assert conn.in_transaction, "conn.in_transaction debe seguir activo tras create con transacción externa"
    conn.rollback()
    assert curso_repo.get_by_id(curso.id) is None, "El curso no debe persistir si la transacción externa hizo rollback"

    # 2. AlmacenDeMateriales._registrar
    from aulento.core.materiales import MaterialNoEncontrado
    almacen = AlmacenDeMateriales(conn, 1)
    conn.execute("BEGIN IMMEDIATE;")
    mat_id = almacen._registrar("ext.txt", ".txt", 50, "sha256ext", "ext.txt", "contenido")
    assert conn.in_transaction, "conn.in_transaction debe seguir activo tras _registrar con transacción externa"
    conn.rollback()
    with pytest.raises(MaterialNoEncontrado):
        almacen.obtener(mat_id)

    # 3. RoadmapRepository.create_roadmap
    roadmap_repo = RoadmapRepository(1, conn=conn)
    conn.execute("BEGIN IMMEDIATE;")
    rm = roadmap_repo.create_roadmap(
        RoadmapCreate(
            titulo="Ruta Externa",
            modulos=[RoadmapModuleCreate(titulo="M1", temas=[RoadmapTopicCreate(titulo="T1")])],
        )
    )
    assert conn.in_transaction, "conn.in_transaction debe seguir activo tras create_roadmap con transacción externa"
    conn.rollback()
    assert roadmap_repo.get_roadmap(rm.id) is None, "La ruta no debe persistir tras rollback externo"

    conn.close()

