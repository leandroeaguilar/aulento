"""Router FastAPI para el estado de configuración inicial y onboarding por cuenta (ADR 012)."""

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from aulento.auth.dependencias import usuario_actual
from aulento.auth.modelos import Usuario
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.secretos import (
    AJUSTE_ONBOARDING_COMPLETADO,
    AjustesDeCuenta,
)
from aulento.web.dependencies import get_db_connection

router = APIRouter(prefix="/api/config/onboarding-status", tags=["Onboarding"])


class OnboardingStatusResponse(BaseModel):
    onboarding_completed: bool = Field(..., description="Si la cuenta ya completó o descartó el asistente")
    should_show_onboarding: bool = Field(..., description="Si se recomienda disparar el asistente de primer ingreso")
    ai: dict[str, Any] = Field(..., description="Estado de los proveedores de IA y si el proveedor activo está listo")
    data: dict[str, int] = Field(..., description="Conteo de recursos de estudio de la cuenta")


class OnboardingCompleteRequest(BaseModel):
    completed: bool = Field(True, description="True para marcar como completado, False para reactivarlo")


@router.get("", response_model=OnboardingStatusResponse, summary="Obtener el estado de configuración y onboarding")
def get_onboarding_status(
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> OnboardingStatusResponse:
    """Retorna el diagnóstico completo de la cuenta: estado de IA y datos."""
    ajustes = AjustesDeCuenta(conn, usuario.id)
    onboarding_completed = bool(ajustes.leer(AJUSTE_ONBOARDING_COMPLETADO, False))

    # Diagnóstico de IA
    pasarela = PasarelaDeIA.con_conexion_propia(usuario.id)
    estado_ia = pasarela.estado()
    prov_activo = estado_ia.get("proveedor_activo")
    proveedores = estado_ia.get("proveedores", {})
    prov_info = proveedores.get(prov_activo, {})
    ai_ready = bool(prov_info.get("tiene_clave"))
    configured_providers = [p for p, info in proveedores.items() if info.get("tiene_clave")]

    ai_dict = {
        "ready": ai_ready,
        "proveedor_activo": prov_activo,
        "configured_providers": configured_providers,
    }

    # Diagnóstico de datos pertenecientes a la cuenta
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM cursos_externos c JOIN plataformas p ON c.plataforma_id = p.id WHERE p.user_id = ?;",
        (usuario.id,),
    )
    total_cursos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM libros_lectura WHERE user_id = ?;", (usuario.id,))
    total_libros = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM fsrs_items WHERE user_id = ?;", (usuario.id,))
    total_tarjetas = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM rutas_aprendizaje WHERE user_id = ?;", (usuario.id,))
    total_rutas = cursor.fetchone()[0]

    total_materiales = total_cursos + total_libros + total_tarjetas + total_rutas
    data_dict = {
        "courses": total_cursos,
        "books": total_libros,
        "flashcards": total_tarjetas,
        "roadmaps": total_rutas,
        "total_materials": total_materiales,
    }

    has_data = total_materiales > 0
    should_show = (not onboarding_completed) and ((not ai_ready) or (not has_data))

    return OnboardingStatusResponse(
        onboarding_completed=onboarding_completed,
        should_show_onboarding=should_show,
        ai=ai_dict,
        data=data_dict,
    )


@router.post("", response_model=dict[str, Any], summary="Marcar el estado de onboarding")
def set_onboarding_status(
    body: OnboardingCompleteRequest,
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    conn: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> dict[str, Any]:
    """Guarda en los ajustes de la cuenta si el onboarding fue completado o descartado."""
    ajustes = AjustesDeCuenta(conn, usuario.id)
    ajustes.guardar(AJUSTE_ONBOARDING_COMPLETADO, bool(body.completed))
    return {
        "ok": True,
        "onboarding_completed": bool(body.completed),
    }
