"""Modelos y errores del dominio de autenticación."""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

ROL_ADMIN = "admin"
ROL_USUARIO = "usuario"
ROLES = (ROL_ADMIN, ROL_USUARIO)


class ErrorDeAuth(Exception):
    """Base de los errores de autenticación; `mensaje` es apto para mostrar al usuario."""

    mensaje = "No se pudo completar la operación."

    def __init__(self, mensaje: str | None = None) -> None:
        super().__init__(mensaje or self.mensaje)


class NombreDeUsuarioInvalido(ErrorDeAuth):
    """El nombre de usuario no respeta el formato."""

    mensaje = "El nombre de usuario debe tener entre 3 y 32 caracteres: letras, números, punto, guion o guion bajo."


class NombreDeUsuarioReservado(NombreDeUsuarioInvalido):
    """El nombre de usuario está reservado por el sistema."""

    mensaje = "Ese nombre de usuario está reservado."


class UsuarioNoEncontrado(ErrorDeAuth):
    """No existe una cuenta con ese identificador."""

    mensaje = "La cuenta no existe."


class TokenMcpNoEncontrado(ErrorDeAuth):
    """El token MCP no existe, ya estaba revocado o es de otra cuenta (no se distingue cuál)."""

    mensaje = "El token no existe."


@dataclass(frozen=True)
class Usuario:
    """Cuenta ya autenticada o resuelta; nunca lleva la contraseña ni su derivación."""

    id: int
    nombre_usuario: str
    rol: str
    activo: bool

    @property
    def es_admin(self) -> bool:
        """Indica si la cuenta tiene rol de administrador."""
        return self.rol == ROL_ADMIN


@dataclass(frozen=True)
class TokenMcpEmitido:
    """Token MCP en claro; solo existe al momento de crearlo."""

    id: int
    token: str = field(repr=False)
    nombre: str | None
    creado_en: str


class UsuarioPublico(BaseModel):
    """Datos de una cuenta que la API puede devolver."""

    id: int
    nombre_usuario: str
    rol: str
    activo: bool


class Resultado(BaseModel):
    """Confirmación de una operación que no devuelve datos."""

    ok: bool = True


class PedidoTokenMcp(BaseModel):
    """Cuerpo para crear un token del servidor MCP."""

    nombre: str | None = Field(None, max_length=64)


class TokenMcpCreado(BaseModel):
    """Token MCP recién creado; es la única respuesta que lo lleva en claro."""

    id: int
    token: str
    nombre: str | None
    creado_en: str


class TokenMcpListado(BaseModel):
    """Token MCP tal como se lista: sin el token ni su huella."""

    id: int
    nombre: str | None
    creado_en: str
    ultimo_uso: str | None
    revocado_en: str | None
