"""Dependencias de FastAPI que exigen sesión y rol, y manejo de la cookie de sesión."""

import sqlite3
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request

from aulento.auth import servicio
from aulento.auth.modelos import Usuario
from aulento.config import is_local_mode
from aulento.core.identity import IIdentityProvider, obtener_proveedor_de_identidad
from aulento.db.connection import get_db_connection

if TYPE_CHECKING:
    from aulento.core.extensiones import Extension
else:
    Extension = object


def proveedor_identidad(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> IIdentityProvider:
    """Inyecta el proveedor de identidad configurado según el modo de Aulento (SOLID DIP)."""
    return obtener_proveedor_de_identidad(request, conn)


def _validar_extensiones_de_cuenta(request: Request, conn: sqlite3.Connection, usuario: Usuario) -> None:
    extensiones: Sequence[Extension] = ()
    if hasattr(request, "app") and hasattr(request.app, "state"):
        extensiones = getattr(request.app.state, "extensiones", ())
    for extension in extensiones:
        for validador in extension.validadores_de_cuenta:
            validador(usuario, conn)


def usuario_actual(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
    proveedor: Annotated[IIdentityProvider, Depends(proveedor_identidad)],
) -> Usuario:
    """Exige una sesión vigente; responde 401 si el pedido no la trae (en modo SaaS). En local, asume local_user."""
    usuario = proveedor.get_usuario()
    if is_local_mode():
        return usuario
    _validar_extensiones_de_cuenta(request, conn, usuario)
    return usuario


def requiere_admin(
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    proveedor: Annotated[IIdentityProvider, Depends(proveedor_identidad)],
) -> Usuario:
    """Exige una sesión de administrador; responde 403 a cualquier otra cuenta."""
    if not proveedor.es_admin() or not usuario.es_admin:
        raise HTTPException(status_code=403, detail="Esta operación es solo para administradores.")
    return usuario


def usuario_de_sesion_o_token(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> Usuario:
    """Acepta sesión interactiva (cookie) o token en encabezado (Authorization: Bearer o X-MCP-Token).

    Por seguridad (R5), el token ya no se acepta en la URL (?token=).
    """
    if "token" in request.query_params:
        raise HTTPException(
            status_code=401,
            detail=(
                "El token ya no se acepta en la URL por seguridad. "
                "Enviá el token en el encabezado 'Authorization: Bearer <token>' o 'X-MCP-Token: <token>'."
            ),
        )

    if is_local_mode():
        from aulento.core.identity import LocalIdentityProvider
        return LocalIdentityProvider(conn).get_usuario()

    # 1. La sesión interactiva, si el proveedor de identidad de la extensión la reconoce
    usuario = obtener_proveedor_de_identidad(request, conn).get_usuario_opcional()

    # 2. Intentar Bearer token o encabezado X-MCP-Token
    if usuario is None:
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif request.headers.get("X-MCP-Token"):
            token = request.headers.get("X-MCP-Token", "").strip()

        if token:
            usuario = servicio.resolver_token_mcp(conn, token)

    if usuario is None:
        raise HTTPException(
            status_code=401,
            detail="Se requiere sesión activa o token válido (encabezado Authorization: Bearer o X-MCP-Token).",
        )

    _validar_extensiones_de_cuenta(request, conn, usuario)
    return usuario


def usuario_para_el_avance_de_libros(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> Usuario:
    """Webhook de libros (061, R3): acepta el token de alcance `libros` en `Authorization: Bearer`.

    Ese token no abre ninguna otra ruta. Por compatibilidad con atajos ya armados, si el encabezado no trae un
    token de libros vigente se sigue aceptando la sesión o el token MCP, con las mismas reglas de siempre.
    """
    from aulento.core import tokens_de_alcance

    auth_header = request.headers.get("Authorization", "")
    if "token" not in request.query_params and auth_header.startswith("Bearer "):
        usuario = usuario_de_token_de_alcance(request, conn, auth_header[7:].strip(), tokens_de_alcance.LIBROS)
        if usuario is not None:
            return usuario
    return usuario_de_sesion_o_token(request, conn)


def usuario_de_token_de_alcance(
    request: Request, conn: sqlite3.Connection, token: str | None, alcance: str
) -> Usuario | None:
    """Cuenta dueña de un token de alcance vigente (061), o None.

    Corre los validadores de cuenta de las extensiones igual que una sesión: lo que frena a una cuenta
    (por ejemplo, una prueba vencida en la nube) la frena también por estos tokens.
    """
    from aulento.auth.repositorio import RepositorioAuth
    from aulento.core import tokens_de_alcance

    user_id = tokens_de_alcance.resolver(conn, token, alcance)
    fila = RepositorioAuth(conn).usuario_por_id(user_id) if user_id is not None else None
    if fila is None:
        return None
    usuario = Usuario(id=fila["id"], nombre_usuario=fila["nombre_usuario"], rol=fila["rol"], activo=bool(fila["activo"]))
    _validar_extensiones_de_cuenta(request, conn, usuario)
    return usuario
