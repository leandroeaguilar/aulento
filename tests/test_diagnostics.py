"""Tests para el módulo de Diagnóstico y Depuración Local (R6)."""

import sqlite3

from fastapi.testclient import TestClient

from aulento.core.diagnostics import (
    anonimizar_texto,
    comprobar_salud_sqlite,
    exportar_reporte_anonimizado,
    leer_ultimas_lineas_log,
    obtener_resumen_diagnostico,
)
from aulento.web.app import app


def test_anonimizar_texto():
    """Verifica que rutas privadas, tokens y claves de API sean filtradas."""
    texto_sucio = (
        r"Error en C:\Users\leandro\dev\aulento\src\app.py y C:/Users/leandro/dev/app2.py con clave "
        + "sk-"
        + "1234567890abcdef1234567890 "
        + r"y hash a1b2c3d4e5f67890123456789012345678901234 y /home/leandro/archivo.txt "
        + r"y Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozGz"
    )
    limpio = anonimizar_texto(texto_sucio)

    assert "leandro" not in limpio
    assert "sk-1234567890" not in limpio
    assert "[CLAVE_OCULTA]" in limpio
    assert "[USUARIO]" in limpio
    assert "[HASH_ANONIMO]" in limpio
    assert "[JWT_ANONIMO]" in limpio or "[TOKEN_ANONIMO]" in limpio


def test_comprobar_salud_sqlite():
    """Verifica la comprobación de integridad y versiones sobre SQLite."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA user_version = 7;")
    res = comprobar_salud_sqlite(conn)

    assert res["estado"] == "saludable"
    assert res["version_esquema"] == 7
    assert res["integridad"] == "ok"
    conn.close()


def test_leer_ultimas_lineas_log_sin_archivo():
    """Si no hay archivo de log, retorna una lista con mensaje informativo sin explotar."""
    lineas = leer_ultimas_lineas_log(10)
    assert isinstance(lineas, list)
    assert len(lineas) > 0


def test_obtener_resumen_diagnostico():
    """Verifica que el resumen contenga las secciones esperadas del sistema."""
    conn = sqlite3.connect(":memory:")
    resumen = obtener_resumen_diagnostico(conn)

    assert "modo_motor" in resumen
    assert "sistema" in resumen
    assert "sqlite" in resumen
    assert "ollama" in resumen
    assert "logs_recientes" in resumen
    conn.close()


def test_exportar_reporte_anonimizado():
    """Genera el reporte Markdown estructurado listo para copiar en GitHub Issues."""
    conn = sqlite3.connect(":memory:")
    reporte = exportar_reporte_anonimizado(conn)

    assert "Reporte de Diagnóstico del Sistema" in reporte
    assert "Estado de Base de Datos SQLite" in reporte
    assert "Estado de IA Local (Ollama)" in reporte
    conn.close()


def test_endpoints_diagnostico_api(monkeypatch):
    """Verifica que las rutas de API respondan correctamente (el diagnóstico es del modo local)."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    client = TestClient(app)

    # 1. Resumen
    resp_summary = client.get("/api/diagnostics/summary")
    assert resp_summary.status_code == 200
    data = resp_summary.json()
    assert "sistema" in data
    assert "sqlite" in data

    # 2. Exportación a Markdown
    resp_md = client.get("/api/diagnostics/export-markdown")
    assert resp_md.status_code == 200
    assert "Reporte de Diagnóstico" in resp_md.text


def test_index_trae_data_modo_segun_entorno(monkeypatch):
    """La página raíz incluye data-modo='local' en modo local y data-modo='saas' en SaaS."""
    from identidad_de_prueba import extension_de_identidad

    from aulento.auth.modelos import Usuario
    from aulento.web.app import create_app

    # 1. Modo Local
    monkeypatch.setenv("AULENTO_MODE", "local")
    client = TestClient(app)
    resp_local = client.get("/")
    assert resp_local.status_code == 200
    assert '<body data-modo="local"' in resp_local.text

    # 2. Modo SaaS
    monkeypatch.setenv("AULENTO_MODE", "saas")
    usuario_saas = Usuario(id=1, nombre_usuario="usuario_saas", rol="usuario", activo=True)
    client = TestClient(create_app(extensiones=[extension_de_identidad(lambda conn: usuario_saas)]))
    resp_saas = client.get("/")
    assert resp_saas.status_code == 200
    assert '<body data-modo="saas"' in resp_saas.text

