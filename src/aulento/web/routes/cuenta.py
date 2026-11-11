"""La cuenta que hace el pedido: en local, la cuenta única; en multiusuario, la que resuelve la extensión."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from aulento.auth.dependencias import usuario_actual
from aulento.auth.modelos import Usuario, UsuarioPublico
from aulento.web.dependencies import es_cuenta_compartida

router = APIRouter(prefix="/api/auth", tags=["Cuenta"])


class CuentaDelPedido(UsuarioPublico):
    """La cuenta del pedido y si la comparten varias personas, para que la interfaz avise lo que no guarda (051, R3)."""

    compartida: bool = Field(description="La declara compartida una extensión: no guarda claves ni conecta servicios.")


@router.get("/me", response_model=CuentaDelPedido)
def quien_soy(request: Request, usuario: Annotated[Usuario, Depends(usuario_actual)]) -> CuentaDelPedido:
    """Devuelve la cuenta que hace el pedido."""
    return CuentaDelPedido(
        id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        rol=usuario.rol,
        activo=usuario.activo,
        compartida=es_cuenta_compartida(request, usuario),
    )
