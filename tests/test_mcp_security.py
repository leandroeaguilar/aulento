"""Tests para el módulo de seguridad, autenticación, sandboxing de archivos y auditoría del servidor MCP."""

import sqlite3
import pytest
from pathlib import Path

from conftest import cuenta_en, token_mcp_de_prueba

from aulento.mcp.security import (
    resolver_token_mcp,
    validate_vault_path_sandbox,
    SecurityViolationError,
    log_mcp_tool_execution,
)
from aulento.db.repository import MCPAuditRepository
from aulento.db.schema import create_schema


def test_mcp_auth_token_generation_and_verification():
    """Verifica que el token criptográfico de una cuenta tenga 256 bits y resuelva a su cuenta."""
    token = token_mcp_de_prueba()
    assert token is not None
    assert len(token) >= 32

    # Verificación de Bearer Token
    assert resolver_token_mcp(token).id == cuenta_en()
    assert resolver_token_mcp(f"Bearer {token}").id == cuenta_en()
    assert resolver_token_mcp("Bearer invalid_token") is None
    assert resolver_token_mcp(None) is None
    assert resolver_token_mcp("") is None


def test_validate_vault_path_sandbox_allows_valid_paths(tmp_path):
    """Verifica que rutas dentro del Vault sean autorizadas normalmente."""
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()
    target_note = vault_root / "04 Knowledge" / "Cursos" / "GCP" / "Leccion 1.md"
    target_note.parent.mkdir(parents=True)
    target_note.touch()

    validated = validate_vault_path_sandbox(target_note, vault_root)
    assert validated == target_note.resolve()


def test_validate_vault_path_sandbox_blocks_path_traversal(tmp_path):
    """Verifica que intentos de path traversal sean interceptados con SecurityViolationError."""
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    # Intento de escapar con ../../
    traversal_path = vault_root / "04 Knowledge" / ".." / ".." / "system32" / "trojan.dll"

    with pytest.raises(SecurityViolationError) as exc_info:
        validate_vault_path_sandbox(traversal_path, vault_root)

    assert "Violación de seguridad (Path Traversal)" in str(exc_info.value)


def test_mcp_audit_logging(tmp_path, operar_por_mcp):
    """Verifica que las invocaciones a herramientas MCP se registren en mcp_audit_logs."""
    db_file = tmp_path / "test_audit.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    conn.close()
    cuenta = operar_por_mcp(cuenta_en(db_file))

    log_mcp_tool_execution(
        tool_name="study_create_or_update_lesson",
        params={"topic_id": 42, "content": "A" * 600},
        transport="stdio",
        status="success",
        db_path=db_file,
    )

    conn2 = sqlite3.connect(str(db_file))
    conn2.row_factory = sqlite3.Row
    repo = MCPAuditRepository(conn2)
    logs = repo.get_recent_logs(cuenta, limit=10)
    conn2.close()

    assert len(logs) == 1
    log = logs[0]
    assert log["tool_name"] == "study_create_or_update_lesson"
    assert log["transport"] == "stdio"
    assert log["status"] == "success"
    # Parámetro largo debe estar truncado/sanitizado
    assert "truncado" in log["params_json"]
