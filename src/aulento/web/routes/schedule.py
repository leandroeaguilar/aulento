import sqlite3
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from aulento.auth.dependencias import usuario_de_token_de_alcance
from aulento.connectors.google_calendar import GoogleCalendarConnector, zona_valida
from aulento.core import tokens_de_alcance
from aulento.core.secretos import AjustesDeCuenta
from aulento.core.zona_horaria import AJUSTE_ZONA_HORARIA
from aulento.db.repository import BloqueHorarioRepository
from aulento.models.horario import (
    BloqueHorario,
    BloqueHorarioCreate,
    BloqueHorarioUpdate,
)
from aulento.web.dependencies import (
    Conexion,
    Cuenta,
    RepoBloques,
    SinCuentaCompartida,
    no_encontrado,
)

router = APIRouter(prefix="/api/schedule", tags=["Schedule"])

# Sin sesión: la cuenta sale del token del feed, que solo sirve para leer el calendario (feature 061, R2)
feed_publico = APIRouter(prefix="/api/schedule", tags=["Schedule"])



def _zona_de_la_cuenta(conn: sqlite3.Connection, user_id: int) -> str:
    return zona_valida(AjustesDeCuenta(conn, user_id).leer(AJUSTE_ZONA_HORARIA))


def _respuesta_ics(bloques: Sequence[BloqueHorario], zona: str, disposicion: str) -> Response:
    return Response(
        content=GoogleCalendarConnector().generate_ical_content(bloques, zona=zona),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'{disposicion}; filename="aulento-schedule.ics"',
            "Cache-Control": "no-cache",
        },
    )


def _url_del_feed(request: Request, token: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/api/schedule/feed/{token}.ics"


# Declaradas antes que `/{block_id}`: si no, `DELETE /feed` se leería como el bloque "feed"
@router.get("/feed")
def estado_del_feed(usuario: Cuenta, conn: Conexion) -> dict[str, Any]:
    """Dice si la cuenta tiene activa la suscripción al calendario; el token solo se muestra al crearlo."""
    creado_en = tokens_de_alcance.vigente(conn, usuario.id, tokens_de_alcance.CALENDARIO)
    return {"activo": creado_en is not None, "creado_en": creado_en}


@router.post("/feed", dependencies=[SinCuentaCompartida])
def activar_feed(request: Request, usuario: Cuenta, conn: Conexion) -> dict[str, Any]:
    """Crea la URL de suscripción al calendario; si ya había una, la anterior deja de funcionar."""
    token, creado_en = tokens_de_alcance.emitir(conn, usuario.id, tokens_de_alcance.CALENDARIO)
    return {"activo": True, "creado_en": creado_en, "url": _url_del_feed(request, token)}


@router.delete("/feed", dependencies=[SinCuentaCompartida])
def revocar_feed(usuario: Cuenta, conn: Conexion) -> dict[str, Any]:
    """Revoca la URL de suscripción: los calendarios suscritos dejan de recibir el cronograma."""
    return {"revocado": tokens_de_alcance.revocar(conn, usuario.id, tokens_de_alcance.CALENDARIO)}


@feed_publico.get("/feed/{token}.ics")
def feed_del_calendario(token: str, request: Request, conn: Conexion) -> Response:
    """Cronograma de la cuenta dueña del token, para suscribirse desde Google Calendar, Apple u Outlook.

    El token va en la ruta porque las apps de calendario no mandan encabezados; solo sirve para esto.
    Uno inexistente, revocado o de otro alcance responde 404, sin decir cuál de las tres cosas pasó.
    """
    no_encontrado_ = HTTPException(status_code=404, detail="Calendario no encontrado.")
    try:
        usuario = usuario_de_token_de_alcance(request, conn, token, tokens_de_alcance.CALENDARIO)
    except HTTPException:
        # Una extensión frenó la cuenta: se responde igual que a un token que no vale, sin decir por qué
        raise no_encontrado_ from None
    if usuario is None:
        raise no_encontrado_
    bloques = BloqueHorarioRepository(conn, usuario.id).list_all()
    return _respuesta_ics(bloques, _zona_de_la_cuenta(conn, usuario.id), "inline")


@router.get("", response_model=list[BloqueHorario])
def list_schedule(repo: RepoBloques, dia_semana: int | None = None):
    """Lista los bloques horarios semanales de la cuenta (opcionalmente filtrado por día 1=Lun..7=Dom)."""
    return repo.list_all(dia_semana=dia_semana)


@router.post("", response_model=BloqueHorario, status_code=status.HTTP_201_CREATED)
def create_schedule_block(data: BloqueHorarioCreate, repo: RepoBloques):
    """Agrega un bloque horario al cronograma semanal."""
    return repo.create(data)


@router.put("/{block_id}", response_model=BloqueHorario)
@router.patch("/{block_id}", response_model=BloqueHorario)
def update_schedule_block(block_id: int, data: BloqueHorarioUpdate, repo: RepoBloques):
    """Actualiza un bloque horario del cronograma semanal."""
    try:
        updated = repo.update(block_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise no_encontrado("Bloque", block_id)
    return updated


@router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_block(block_id: int, repo: RepoBloques):
    """Elimina un bloque horario."""
    deleted = repo.delete(block_id)
    if not deleted:
        raise no_encontrado("Bloque", block_id)


@router.get("/export/calendar.ics")
def export_icalendar_feed(repo: RepoBloques, usuario: Cuenta, conn: Conexion):
    """Exporta el cronograma de estudio de la cuenta en formato RFC 5545 iCalendar (.ics), con su zona horaria.

    Compatible con Google Calendar Web/Mobile, Apple Calendar y Outlook (importación única).
    """
    return _respuesta_ics(repo.list_all(), _zona_de_la_cuenta(conn, usuario.id), "attachment")


@router.get("/google-calendar/status")
def get_google_calendar_status(repo: RepoBloques) -> dict[str, Any]:
    """Retorna el estado de la integración de Google Calendar y métodos disponibles."""
    bloques = repo.list_all()
    connector = GoogleCalendarConnector()
    return connector.get_status(bloques)


@router.get("/google-calendar/links")
def get_google_calendar_links(repo: RepoBloques, usuario: Cuenta, conn: Conexion) -> list[dict[str, Any]]:
    """Devuelve los bloques de estudio de la cuenta con sus URLs de integración directa de 1-clic a Google Calendar."""
    bloques = repo.list_all()
    connector = GoogleCalendarConnector()
    return connector.get_block_links(bloques, zona=_zona_de_la_cuenta(conn, usuario.id))


@router.get("/google-calendar/link/{block_id}")
def get_google_calendar_link_for_block(
    block_id: int, repo: RepoBloques, usuario: Cuenta, conn: Conexion
) -> dict[str, Any]:
    """Genera la URL directa de 1-clic para un bloque específico."""
    target = repo.get(block_id)
    if not target:
        raise no_encontrado("Bloque", block_id)

    connector = GoogleCalendarConnector()
    gcal_url = connector.generate_gcal_web_url(target, zona=_zona_de_la_cuenta(conn, usuario.id))
    return {
        "id": target.id,
        "descripcion": target.descripcion,
        "gcal_url": gcal_url,
    }
