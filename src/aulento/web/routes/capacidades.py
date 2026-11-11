"""Ruta de capacidades y textos de la versión activa (R1, R2, R8)."""

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Request

from aulento.config import is_local_mode, is_saas_mode
from aulento.core import cliente_google_compartido
from aulento.web.dependencies import Conexion, Cuenta
from aulento.web.routes.books import enlace_del_atajo_de_libros

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Frontend"])


def tiene_cliente_google(conn: sqlite3.Connection, user_id: int | None) -> bool:
    """Verifica si el servidor cuenta con un cliente de Google configurado (compartido o propio)."""
    try:
        if cliente_google_compartido.obtener_cliente_compartido() is not None:
            return True
    except (OSError, ValueError) as error:
        logger.debug("No se pudo leer el cliente compartido de Google: %s", error)

    if user_id is not None:
        try:
            from aulento.connectors.google_books import GoogleBooksConnector

            conector = GoogleBooksConnector(conn, user_id)
            if conector.obtener_cliente_oauth() is not None:
                return True
        except (OSError, ValueError) as error:
            logger.debug("No se pudo leer el cliente propio de Google: %s", error)

    return False


@router.get("/api/capacidades")
def obtener_capacidades(
    request: Request,
    usuario: Cuenta,
    conn: Conexion,
) -> dict[str, Any]:
    """Informa el modo del servidor, las capacidades activas y los textos de reemplazo para la interfaz."""
    local = is_local_mode()
    modo = "saas" if is_saas_mode() else "local"
    user_id = getattr(usuario, "id", None)

    tiene_mcp = any(getattr(route, "path", None) == "/mcp" for route in getattr(request.app, "routes", []))

    capacidades: dict[str, bool] = {
        "carpeta_local": local,
        "mcp_escritorio": local,
        "mcp_web": bool(tiene_mcp and not local),
        "google_libros": tiene_cliente_google(conn, user_id),
        "atajo_libros": enlace_del_atajo_de_libros() is not None,
    }
    textos: dict[str, str] = {}

    extensiones = getattr(request.app.state, "extensiones", ())
    for ext in extensiones:
        if ext.capacidades is not None:
            if callable(ext.capacidades):
                capacidades.update(ext.capacidades(usuario))
            else:
                capacidades.update(ext.capacidades)
        if ext.textos:
            if callable(ext.textos):
                textos.update(ext.textos(usuario))
            else:
                textos.update(ext.textos)

    return {
        "modo": modo,
        "capacidades": capacidades,
        "textos": textos,
    }
