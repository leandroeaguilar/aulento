"""Pruebas unitarias de conexión SQLite y configuración de directorios."""

import os
import sqlite3
from pathlib import Path

import pytest
from aulento.config import get_db_path, ensure_data_dir, DEFAULT_DB_PATH
from aulento.db.connection import get_connection, database_context


def test_get_db_path_default(monkeypatch):
    """Verifica que la ruta por defecto sea ~/.aulento/study_engine.db si no hay env var."""
    monkeypatch.delenv("AULENTO_DB_PATH", raising=False)
    monkeypatch.delenv("AULENTO_DATA_DIR", raising=False)
    assert DEFAULT_DB_PATH == Path.home() / ".aulento" / "study_engine.db"
    assert get_db_path() == DEFAULT_DB_PATH


def test_get_db_path_override(monkeypatch, tmp_path):
    """Verifica que la variable de entorno sobreescriba la ruta de la base de datos."""
    custom_path = tmp_path / "custom.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(custom_path))
    assert get_db_path() == custom_path


def test_ensure_data_dir_creates_directory(tmp_path):
    """Verifica que ensure_data_dir cree las carpetas padre."""
    sub_dir = tmp_path / "nested" / "deep"
    target_file = sub_dir / "test.db"
    assert not sub_dir.exists()
    ensure_data_dir(target_file)
    assert sub_dir.exists()


def test_get_connection_enforces_foreign_keys():
    """Verifica que foreign_keys esté activo en cada conexión."""
    conn = get_connection(":memory:")
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys;")
    result = cursor.fetchone()
    conn.close()
    assert result[0] == 1


def test_database_context_commits_transaction(temp_db_path):
    """Verifica que database_context ejecute commit automático ante éxito."""
    with database_context(temp_db_path) as conn:
        conn.execute("CREATE TABLE test_tx (id INT, val TEXT);")
        conn.execute("INSERT INTO test_tx VALUES (1, 'ok');")

    # Verificar en nueva conexión
    with database_context(temp_db_path) as conn:
        cursor = conn.execute("SELECT val FROM test_tx WHERE id=1;")
        row = cursor.fetchone()
        assert row["val"] == "ok"


def test_database_context_rolls_back_on_error(temp_db_path):
    """Verifica rollback ante excepciones dentro del contexto."""
    with database_context(temp_db_path) as conn:
        conn.execute("CREATE TABLE test_rb (id INT);")

    with pytest.raises(RuntimeError):
        with database_context(temp_db_path) as conn:
            conn.execute("INSERT INTO test_rb VALUES (1);")
            raise RuntimeError("Fallo provocado")

    with database_context(temp_db_path) as conn:
        cursor = conn.execute("SELECT count(*) as cnt FROM test_rb;")
        assert cursor.fetchone()["cnt"] == 0
