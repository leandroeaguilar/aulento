"""Rutas de API para el diagnóstico y depuración del sistema."""

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from aulento.core.diagnostics import (
    exportar_reporte_anonimizado,
    obtener_resumen_diagnostico,
)
from aulento.db.connection import get_db_connection


def solo_en_modo_local() -> None:
    """En saas el diagnóstico mostraría el registro y la base de todas las cuentas: responde 404."""
    from aulento.config import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"], dependencies=[Depends(solo_en_modo_local)])


@router.get("/summary")
def get_diagnostic_summary(
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> dict[str, Any]:
    """Retorna el resumen de diagnóstico del sistema (salud de base de datos, Ollama y logs)."""
    return obtener_resumen_diagnostico(conn)


@router.get("/export-markdown", response_class=PlainTextResponse)
def get_diagnostic_markdown(
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> str:
    """Retorna un reporte de diagnóstico estructurado en Markdown listo para GitHub Issues."""
    return exportar_reporte_anonimizado(conn)
