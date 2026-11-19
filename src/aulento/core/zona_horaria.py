"""Resolución de la zona horaria de una cuenta y conversión de marcas de tiempo UTC a fechas locales."""

from datetime import date, datetime, timezone, tzinfo
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aulento.core.secretos import AjustesDeCuenta

# Ajuste de cuenta que guarda el nombre IANA de la zona horaria elegida (ej. "America/Argentina/Buenos_Aires")
AJUSTE_ZONA_HORARIA = "zona_horaria"


def zona_de_la_cuenta(conn: sqlite3.Connection, user_id: int) -> tzinfo:
    """Devuelve la zona horaria de la cuenta si está configurada y es válida; si no, la zona de la máquina.

    En modo local la zona de la máquina coincide con la de la persona que usa Aulento.
    Si la cuenta tiene configurado el ajuste `zona_horaria` (por ejemplo en un despliegue
    en la nube), manda ese ajuste siempre que la base IANA lo reconozca.
    """
    try:
        ajustes = AjustesDeCuenta(conn, user_id)
        valor = ajustes.leer(AJUSTE_ZONA_HORARIA)
        if valor and isinstance(valor, str):
            try:
                return ZoneInfo(valor)
            except (ZoneInfoNotFoundError, ValueError, KeyError):
                pass
    except sqlite3.OperationalError:
        # En bases no migradas o en memoria sin la tabla `ajustes_usuario`
        pass

    tz_maquina = datetime.now().astimezone().tzinfo
    return tz_maquina if tz_maquina is not None else timezone.utc


def convertir_a_zona(marca: str | datetime, zona: tzinfo) -> datetime:
    """Convierte una marca de tiempo a un datetime consciente en la zona indicada.

    Acepta tanto ISO 8601 con zona (ej. "2026-11-19T01:00:00+00:00") como cadenas
    CURRENT_TIMESTAMP de SQLite sin zona (ej. "2026-11-19 01:00:00"), que se interpretan
    siempre en UTC. Si recibe un datetime naive, también asume UTC.
    """
    if isinstance(marca, str):
        dt = datetime.fromisoformat(marca.strip())
    elif isinstance(marca, datetime):
        dt = marca
    else:
        raise TypeError(f"Marca de tiempo inválida, se esperaba str o datetime: {marca!r}")

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(zona)


def fecha_local(marca: str | datetime, zona: tzinfo) -> date:
    """Devuelve la fecha calendario (`date`) de la marca de tiempo vista desde la zona horaria dada."""
    return convertir_a_zona(marca, zona).date()


def fecha_local_str(marca: str | datetime, zona: tzinfo) -> str:
    """Devuelve la fecha calendario como cadena ISO ("YYYY-MM-DD") en la zona horaria dada."""
    return fecha_local(marca, zona).isoformat()
