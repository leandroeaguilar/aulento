"""Acceso a los secretos y ajustes de una cuenta para los servicios que los leen en cada operación."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self

from aulento.core.secretos import AjustesDeCuenta, AlmacenDeSecretos
from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta, exigir_repositorio_de_cuenta
from aulento.db.schema import create_schema


class ServicioDeCuenta:
    """Base de un servicio atado a una cuenta que lee sus secretos y ajustes de la base.

    Trabaja sobre la conexión que recibe o, armado con `con_conexion_propia` o `de_repositorio`, abre una
    por lectura y la cierra al terminar (como hace el repositorio de rutas).
    """

    def __init__(self, conn: sqlite3.Connection, user_id: int) -> None:
        if not isinstance(conn, sqlite3.Connection):
            raise TypeError(
                f"{type(self).__name__} necesita la conexión a la base donde está la configuración de la cuenta."
            )
        self.user_id = exigir_cuenta(user_id)
        self._conn: sqlite3.Connection | None = conn
        self._db_path: Path | str | None = None

    @classmethod
    def con_conexion_propia(cls, user_id: int, db_path: Path | str | None = None) -> Self:
        """Servicio de la cuenta que abre y cierra su conexión en cada lectura, para quien no tiene una a mano."""
        servicio = cls.__new__(cls)
        servicio.user_id = exigir_cuenta(user_id)
        servicio._conn = None
        servicio._db_path = db_path
        return servicio

    @classmethod
    def de_repositorio(cls, repo: Any) -> Self:
        """Servicio de la cuenta de un repositorio de rutas, sobre la misma base que el repositorio."""
        return cls.con_conexion_propia(exigir_repositorio_de_cuenta(repo), getattr(repo, "db_path", None))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(user_id={self.user_id})"

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        """La conexión del servicio; si se armó sin una, abre la suya y la cierra al salir."""
        if self._conn is not None:
            yield self._conn
            return
        conn = get_connection(self._db_path)
        try:
            create_schema(conn)
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _almacenes(self) -> Iterator[tuple[AlmacenDeSecretos, AjustesDeCuenta]]:
        with self._conexion() as conn:
            yield AlmacenDeSecretos(conn, self.user_id), AjustesDeCuenta(conn, self.user_id)
