"""Suite de Pruebas de Ciberseguridad y Blindaje Defensivo (AppSec & SecOps).

Ejecuta auditoría adversarial sobre la superficie de ataque de Aulento:
1. TEST-SEC-01: Protección y enmascaramiento estricto de secretos y tokens en API.
2. TEST-SEC-02: Blindaje contra Path Traversal y Directory Escape en rutas de notas y configs.
3. TEST-SEC-03: Mitigación de DNS Rebinding y Host Header Injection (TrustedHostMiddleware).
4. TEST-SEC-04: Bloqueo de CORS no autorizados y mitigación CSRF (LocalOriginAuthMiddleware).
5. TEST-SEC-05: Inyección de cabeceras HTTP defensivas (CSP estricto, Clickjacking, MIME sniffing).
6. TEST-SEC-06: Verificación de tokens a prueba de ataques de temporización (Timing Attacks).
7. TEST-SEC-07: Contención estricta de Prompt Injection en el motor de Inteligencia Artificial.
8. TEST-SEC-08: Inmunidad contra SQL Injection en repositorios SQLite (100% parametrizado).
9. TEST-SEC-09: Integridad de .gitignore contra filtraciones accidentales de credenciales a Git.
"""

import os
import re
import hmac
import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba, token_mcp_de_prueba, vault_de_prueba
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.db.repository import LibroRepository, CursoRepository
from aulento.mcp.security import (
    resolver_token_mcp,
    validate_vault_path_sandbox,
    SecurityViolationError,
)
from aulento.audio.gemini_tutor import GEMINI_SYSTEM_PROMPT
from aulento.web.app import create_app


@pytest.fixture
def sec_env(tmp_path, monkeypatch):
    """Entorno aislado para pruebas adversariales de seguridad."""
    db_file = tmp_path / "sec_audit.db"

    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))

    conn = get_connection(db_file)
    init_db(conn)
    conn.close()
    vault_dir = vault_de_prueba(db_file)

    app = create_app()
    client = TestClient(app)

    return {
        "client": client,
        "vault_dir": vault_dir,
        "db_file": db_file,
    }


def test_sec_01_credential_masking_and_static_leak_defense(sec_env):
    """Verifica que secretos nunca se expongan en texto plano y no sean accesibles vía /static."""
    client = sec_env["client"]

    # 1. Una clave de IA se guarda cifrada y no vuelve en ninguna respuesta ni queda en claro en la base
    res = client.put("/api/config/ia/anthropic/key", json={"clave": "UltraSecretPassword999!"})
    assert res.status_code == 200
    assert "UltraSecretPassword999!" not in res.text
    assert "UltraSecretPassword999!" not in client.get("/api/config/ia").text
    assert b"UltraSecretPassword999!" not in sec_env["db_file"].read_bytes()

    # 2. Intento de leer archivos de credenciales fuera de /static
    res_static_traversal = client.get("/static/../credentials.json")
    assert res_static_traversal.status_code in (403, 404)

    res_static_secret = client.get("/static/credentials.json")
    assert res_static_secret.status_code == 404


def test_sec_02_path_traversal_defense_in_notes_and_configs(sec_env):
    """Verifica que los intentos de path traversal sean rechazados sin escribir nada."""
    client = sec_env["client"]
    vault_dir = sec_env["vault_dir"]

    # 1. Intento de escape en guardado de notas hacia Windows/Linux root
    traversal_payload = {
        "title": "../../../../evil_script",
        "folder": "../../system32",
        "content": "malicious payload",
    }
    res = client.post("/api/mcp/agent/save-note", json=traversal_payload)

    # Un nombre de nota que apunta fuera del vault de la cuenta responde 404 (034, R8) y no escribe nada
    assert res.status_code == 404
    assert [p for p in vault_dir.rglob("*") if p.is_file() and not p.name.startswith(".")] == []
    assert list(vault_dir.parent.rglob("evil_script*")) == []

    # Un título común se guarda dentro de 04 Knowledge/Cursos/ del vault de la cuenta
    res = client.post("/api/mcp/agent/save-note", json={"title": "Nota: segura", "folder": "Curso", "content": "ok"})
    assert res.status_code == 200
    target_disk_path = (vault_dir / res.json()["relative_path"]).resolve()
    assert target_disk_path.is_relative_to((vault_dir / "04 Knowledge" / "Cursos").resolve())
    assert target_disk_path.read_text(encoding="utf-8") == "ok"


def test_sec_03_dns_rebinding_and_host_header_injection(sec_env):
    """Verifica que el middleware bloquee nombres de host falsificados de atacantes."""
    client = sec_env["client"]

    # Host Header falso (ataque de DNS Rebinding)
    res_evil_host = client.get("/api/health", headers={"host": "attacker.evil.com"})
    assert res_evil_host.status_code == 400

    # Host Header legítimo (localhost)
    res_valid_host = client.get("/api/health", headers={"host": "localhost:8000"})
    assert res_valid_host.status_code == 200


def test_sec_04_cors_and_csrf_cross_origin_blocking(sec_env):
    """Verifica que orígenes maliciosos no puedan ejecutar peticiones ni mutar estado."""
    client = sec_env["client"]

    # 1. Origen no autorizado es rechazado con 403 Forbidden
    res_evil_origin = client.get(
        "/api/health",
        headers={"origin": "https://hackers-site.org"},
    )
    assert res_evil_origin.status_code == 403

    # 2. Origen localhost legítimo es admitido
    res_good_origin = client.get(
        "/api/health",
        headers={"origin": "http://localhost:8000"},
    )
    assert res_good_origin.status_code == 200

    # 3. Petición mutante con Sec-Fetch-Site cross-site es bloqueada
    res_cross_site = client.post(
        "/api/mcp/tokens",
        headers={"sec-fetch-site": "cross-site"},
        json={"nombre": "desde otro sitio"},
    )
    assert res_cross_site.status_code == 403


def test_sec_05_http_security_headers_and_strict_csp(sec_env):
    """Verifica que las cabeceras defensivas para mitigar XSS, Clickjacking y Sniffing estén presentes."""
    client = sec_env["client"]
    res = client.get("/api/health")
    assert res.status_code == 200
    headers = res.headers

    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    csp = headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_sec_06_timing_attack_resilient_token_verification():
    """El token MCP de una cuenta se verifica por su huella; uno manipulado, vacío o ausente no resuelve ninguna."""
    valid_token = token_mcp_de_prueba()
    assert resolver_token_mcp(valid_token) is not None
    assert resolver_token_mcp(f"Bearer {valid_token}") is not None

    # Tokens manipulados de misma longitud o diferente longitud deben fallar limpiamente
    fake_token = "A" * len(valid_token)
    assert resolver_token_mcp(fake_token) is None
    assert resolver_token_mcp("") is None
    assert resolver_token_mcp(None) is None


def test_sec_07_prompt_injection_xml_containment():
    """Verifica que el prompt del sistema contenga barreras defensivas XML para neutralizar prompt injection."""
    assert "<target_phrase>" in GEMINI_SYSTEM_PROMPT
    assert "<student_speech>" in GEMINI_SYSTEM_PROMPT
    assert "SECURITY RULE" in GEMINI_SYSTEM_PROMPT
    assert "untrusted" in GEMINI_SYSTEM_PROMPT.lower()


def test_sec_08_sql_injection_immunity(sec_env):
    """Verifica que cargas útiles de SQL Injection sean tratadas como cadenas literales inofensivas."""
    db_file = sec_env["db_file"]
    conn = get_connection(db_file)
    repo = LibroRepository(conn, administrador_de_prueba(conn).id)

    # Inyección SQL clásica en búsqueda de libros
    sqli_payload = "' OR '1'='1' UNION SELECT 1, 'Hacked', '999', 1, 1, 1, 1, 'x' --"
    found = repo.find_by_title(sqli_payload)
    # Debe retornar None sin lanzar error de sintaxis SQL ni volcar datos no autorizados
    assert found is None

    # Consulta directa de verificación
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM libros_lectura")
    count_before = cur.fetchone()[0]

    # Inyección con DELETE / DROP TABLE
    destructive_payload = "Clean Architecture'; DROP TABLE libros_lectura; --"
    _ = repo.find_by_title(destructive_payload)

    cur.execute("SELECT COUNT(*) FROM libros_lectura")
    count_after = cur.fetchone()[0]
    assert count_before == count_after
    conn.close()


def test_sec_09_gitignore_integrity_for_secrets():
    """Verifica que el archivo .gitignore contenga todos los patrones para proteger secretos y bases de datos."""
    repo_root = Path(__file__).parent.parent
    gitignore_path = repo_root / ".gitignore"
    assert gitignore_path.exists(), "El archivo .gitignore debe existir en la raíz"

    content = gitignore_path.read_text(encoding="utf-8")
    required_patterns = [
        "credentials.json",
        "client_secret_*.json",
        "*token*.json",
        "gdrive_token.json",
        "mcp_config.json",
        ".study-engine/",
        "*.db",
        ".env",
    ]

    for pat in required_patterns:
        assert pat in content, f"Patrón de seguridad '{pat}' ausente en .gitignore"
