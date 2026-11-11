"""Gestión de conexiones SQLite con Foreign Keys activas y Row factory."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from aulento.config import ensure_data_dir, get_db_path, DEFAULT_DB_PATH


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Crea y retorna una conexión a la base de datos SQLite configurada.
    
    Asegura:
    - PRAGMA foreign_keys = ON;
    - row_factory = sqlite3.Row
    """
    if db_path is None:
        target = ensure_data_dir()
        conn = sqlite3.connect(str(target), check_same_thread=False)
    elif str(db_path) == ":memory:":
        conn = sqlite3.connect(":memory:", check_same_thread=False)
    else:
        target = Path(db_path)
        ensure_data_dir(target)
        conn = sqlite3.connect(str(target), check_same_thread=False)

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if str(db_path) != ":memory:" and (db_path is not None or str(target) != ":memory:"):
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
        except Exception:
            pass
    return conn


@contextmanager
def database_context(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager para operaciones transaccionales seguras."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Provee una conexión activa a SQLite y asegura su cierre tras la petición."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
