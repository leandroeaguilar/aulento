"""Desacoplamiento de Identidad bajo principios SOLID (LSP y DIP).

Define la interfaz abstracta IIdentityProvider y sus implementaciones concretas:
- LocalIdentityProvider: monousuario local-first sin fricción ni login.
- El proveedor multiusuario lo aporta una extensión (`Extension.identidad`, ADR 017).
"""

import sqlite3
from abc import ABC, abstractmethod

from fastapi import Request

from aulento.auth.modelos import ROL_ADMIN, Usuario
from aulento.auth.repositorio import RepositorioAuth


class SinProveedorDeIdentidad(RuntimeError):
    """El modo multiusuario necesita una extensión que aporte la identidad (`Extension.identidad`), y no hay."""

    def __init__(self) -> None:
        super().__init__(
            "AULENTO_MODE=saas necesita una extensión que aporte las cuentas (Extension.identidad). "
            "El core solo trae el modo local, de una sola persona."
        )


class IIdentityProvider(ABC):
    """Contrato base para la resolución de identidad en Aulento (DIP)."""

    @property
    @abstractmethod
    def modo(self) -> str:
        """Identificador del modo: 'local' o 'saas'."""
        ...

    @abstractmethod
    def get_usuario(self) -> Usuario:
        """Retorna el usuario actual o lanza HTTPException 401 si no está autenticado."""
        ...

    @abstractmethod
    def get_usuario_opcional(self) -> Usuario | None:
        """Retorna el usuario actual o None si no hay sesión activa."""
        ...

    @abstractmethod
    def es_admin(self) -> bool:
        """Indica si el usuario actual posee permisos de administrador."""
        ...

    @abstractmethod
    def es_autenticado(self) -> bool:
        """Indica si hay una identidad válida y activa resuelta."""
        ...


class LocalIdentityProvider(IIdentityProvider):
    """Proveedor para el Core Local-First (Monousuario).
    
    Asume automáticamente un usuario local único ('local_user') con privilegios completos,
    eliminando pantallas de login, contraseñas o tokens.
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.conn = conn

    @property
    def modo(self) -> str:
        return "local"

    def _asegurar_usuario_local(self) -> Usuario:
        """Asegura que exista una fila en la base de datos para satisfacer claves foráneas."""
        if self.conn is None:
            return Usuario(id=1, nombre_usuario="local_user", rol=ROL_ADMIN, activo=True)

        repo = RepositorioAuth(self.conn)
        try:
            row = repo.usuario_por_id(1)
            if row is not None:
                if not row["activo"]:
                    with repo.transaccion():
                        self.conn.execute("UPDATE usuarios SET activo = 1 WHERE id = ?;", (row["id"],))
                return Usuario(
                    id=row["id"],
                    nombre_usuario=row["nombre_usuario"],
                    rol=ROL_ADMIN,
                    activo=True,
                )
            # Sin cuenta 1, se crea como cualquier primera cuenta: hereda los datos sin dueño (051, R7)
            from aulento.auth.servicio import crear_cuenta_local

            return crear_cuenta_local(self.conn)
        except (sqlite3.Error, OSError):
            return Usuario(id=1, nombre_usuario="local_user", rol=ROL_ADMIN, activo=True)

    def get_usuario(self) -> Usuario:
        return self._asegurar_usuario_local()

    def get_usuario_opcional(self) -> Usuario | None:
        return self.get_usuario()

    def es_admin(self) -> bool:
        return True

    def es_autenticado(self) -> bool:
        return True


def obtener_proveedor_de_identidad(request: Request, conn: sqlite3.Connection) -> IIdentityProvider:
    """Fábrica de proveedor de identidad según la configuración del sistema."""
    from aulento.config import get_engine_mode

    if get_engine_mode() == "local":
        return LocalIdentityProvider(conn)
    estado = getattr(getattr(request, "app", None), "state", None)
    for extension in getattr(estado, "extensiones", ()):
        if extension.identidad is not None:
            return extension.identidad(request, conn)
    raise SinProveedorDeIdentidad()
