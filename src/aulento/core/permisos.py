"""Enganche `puede(cuenta, accion)`: si una cuenta puede crear algo más (062, R4).

El core pregunta antes de crear un curso, una ruta o un material. Por defecto
todo está permitido: el core no tiene planes ni topes. Una extensión aporta sus reglas en `Extension.permisos`; cada
regla recibe la cuenta, la acción, la conexión y el detalle de la acción, y devuelve una `Decision` o `None` (no
opina). La primera que niega corta, con su motivo.

Las reglas se registran por proceso al arrancar la app (como los validadores de cuenta), así las respeta tanto la web
como el servidor MCP, que crean por los mismos repositorios.
"""

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Acciones que el core consulta. Son neutras: el core no sabe qué regla las limita ni por qué.
CREAR_CURSO = "crear_curso"
CREAR_RUTA = "crear_ruta"
SUBIR_MATERIAL = "subir_material"  # detalle: bytes del archivo

ACCIONES = (CREAR_CURSO, CREAR_RUTA, SUBIR_MATERIAL)


@dataclass(frozen=True)
class Decision:
    permitido: bool
    motivo: str = ""


PERMITIDO = Decision(permitido=True)

Permiso = Callable[..., Decision | None]


class AccionNoPermitida(Exception):
    """Una regla de una extensión negó la acción. La web responde 403 con el motivo; nada de lo que ya había cambia."""

    def __init__(self, accion: str, motivo: str) -> None:
        self.accion = accion
        self.motivo = motivo
        super().__init__(motivo)


_permisos_registrados: list[Permiso] = []


def registrar_permisos(permisos: Sequence[Permiso]) -> None:
    """Registra las reglas de una extensión en el proceso; cada registro cuenta, como el de los validadores."""
    _permisos_registrados.extend(permisos)


def desregistrar_permisos(permisos: Sequence[Permiso]) -> None:
    for permiso in permisos:
        if permiso in _permisos_registrados:
            _permisos_registrados.remove(permiso)


def limpiar_permisos() -> None:
    _permisos_registrados.clear()


def puede(user_id: int, accion: str, conn: sqlite3.Connection, **detalle: object) -> Decision:
    """La decisión sobre la acción: permitida salvo que alguna regla registrada la niegue."""
    if accion not in ACCIONES:
        raise ValueError(f"Acción desconocida para los permisos: {accion!r}")
    vistas: set[int] = set()
    for permiso in _permisos_registrados[:]:  # una copia: una regla puede desregistrar otra mientras se recorre
        # Dos apps del mismo proceso con la misma extensión la registran dos veces: se consulta una
        if id(permiso) in vistas:
            continue
        vistas.add(id(permiso))
        decision = permiso(user_id=user_id, accion=accion, conn=conn, **detalle)
        if decision is not None and not decision.permitido:
            return decision
    return PERMITIDO


def exigir(user_id: int, accion: str, conn: sqlite3.Connection, **detalle: object) -> None:
    """Como `puede`, pero corta con `AccionNoPermitida` si la acción está negada."""
    decision = puede(user_id, accion, conn, **detalle)
    if not decision.permitido:
        raise AccionNoPermitida(accion, decision.motivo or "Esta acción no está permitida para tu cuenta.")
