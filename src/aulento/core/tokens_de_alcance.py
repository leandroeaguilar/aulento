"""Tokens de alcance limitado (feature 061): cada uno sirve para una sola cosa y no para el resto de la API.

- `calendario`: lee el feed `.ics` del cronograma (va en la URL porque las apps de calendario no mandan
  encabezados; es de solo lectura y revocable).
- `libros`: actualiza el avance de lectura por el webhook de Atajos.

Cada cuenta tiene a lo sumo un token vigente por alcance: emitir uno nuevo revoca el anterior. En la base
queda solo la huella; el token en claro se muestra una vez, al emitirlo.
"""

import hashlib
import hmac
import secrets
import sqlite3
from datetime import UTC, datetime

CALENDARIO = "calendario"
LIBROS = "libros"
ALCANCES = (CALENDARIO, LIBROS)


def _huella(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _exigir_alcance(alcance: str) -> str:
    if alcance not in ALCANCES:
        raise ValueError(f"Alcance desconocido: {alcance!r}")
    return alcance


def emitir(conn: sqlite3.Connection, user_id: int, alcance: str) -> tuple[str, str]:
    """Emite un token nuevo para la cuenta y revoca el que tuviera en ese alcance; retorna (token, creado_en)."""
    _exigir_alcance(alcance)
    token = secrets.token_urlsafe(32)
    creado_en = _ahora()
    with conn:
        conn.execute(
            "UPDATE tokens_de_alcance SET revocado_en = ? WHERE user_id = ? AND alcance = ? AND revocado_en IS NULL;",
            (creado_en, user_id, alcance),
        )
        conn.execute(
            "INSERT INTO tokens_de_alcance (user_id, alcance, token_hash, creado_en) VALUES (?, ?, ?, ?);",
            (user_id, alcance, _huella(token), creado_en),
        )
    return token, creado_en


def vigente(conn: sqlite3.Connection, user_id: int, alcance: str) -> str | None:
    """Fecha de emisión del token vigente de la cuenta en ese alcance, o None si no tiene."""
    _exigir_alcance(alcance)
    fila = conn.execute(
        "SELECT creado_en FROM tokens_de_alcance WHERE user_id = ? AND alcance = ? AND revocado_en IS NULL "
        "ORDER BY id DESC LIMIT 1;",
        (user_id, alcance),
    ).fetchone()
    return fila[0] if fila else None


def revocar(conn: sqlite3.Connection, user_id: int, alcance: str) -> bool:
    """Revoca el token vigente de la cuenta en ese alcance; retorna si había uno."""
    _exigir_alcance(alcance)
    with conn:
        cursor = conn.execute(
            "UPDATE tokens_de_alcance SET revocado_en = ? WHERE user_id = ? AND alcance = ? AND revocado_en IS NULL;",
            (_ahora(), user_id, alcance),
        )
    return cursor.rowcount > 0


def revocar_todos(conn: sqlite3.Connection, user_id: int) -> int:
    """Revoca todos los tokens de alcance vigentes de la cuenta."""
    cursor = conn.execute(
        "UPDATE tokens_de_alcance SET revocado_en = ? WHERE user_id = ? AND revocado_en IS NULL;",
        (_ahora(), user_id),
    )
    return cursor.rowcount


def resolver(conn: sqlite3.Connection, token: str | None, alcance: str) -> int | None:
    """Cuenta activa dueña de un token vigente de ese alcance, o None si el token no vale para eso."""
    _exigir_alcance(alcance)
    if not token:
        return None
    huella = _huella(token)
    fila = conn.execute(
        "SELECT t.user_id, t.token_hash FROM tokens_de_alcance t JOIN usuarios u ON u.id = t.user_id "
        "WHERE t.token_hash = ? AND t.alcance = ? AND t.revocado_en IS NULL AND u.activo = 1;",
        (huella, alcance),
    ).fetchone()
    if fila is None or not hmac.compare_digest(fila[1], huella):
        return None
    return int(fila[0])
