"""Conector e integración con Google Calendar para el cronograma de estudio.

Proporciona:
1. Enlaces directos web de 1-clic a Google Calendar con reglas de recurrencia semanal (RRULE).
2. Generación y exportación de archivos iCalendar (RFC 5545 .ics) para suscripción o importación masiva.
3. Diagnóstico de estado y compatibilidad con credenciales de Google Workspace / Cloud.
"""

import os
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aulento.models.horario import BloqueHorario

# Zona con la que se escriben los eventos si la cuenta no eligió otra (feature 061, R1)
ZONA_POR_DEFECTO = "America/Argentina/Buenos_Aires"


def zona_valida(nombre: str | None) -> str:
    """La zona IANA pedida si existe; si no, la zona por defecto."""
    if nombre and isinstance(nombre, str):
        try:
            ZoneInfo(nombre)
            return nombre
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return ZONA_POR_DEFECTO


def _desfase(minutos: int) -> str:
    signo = "-" if minutos < 0 else "+"
    minutos = abs(minutos)
    return f"{signo}{minutos // 60:02d}{minutos % 60:02d}"


def _bloque_vtimezone(zona: str, anio: int) -> list[str]:
    """`VTIMEZONE` para una zona sin horario de verano (como la de Argentina).

    Una zona con cambio de horario se identifica solo por su nombre IANA en `TZID`, que Google Calendar,
    Apple Calendar y Outlook reconocen: describir sus reglas de cambio a mano sería un error esperando pasar.
    """
    tz = ZoneInfo(zona)
    enero = datetime(anio, 1, 1, 12, tzinfo=tz).utcoffset()
    julio = datetime(anio, 7, 1, 12, tzinfo=tz).utcoffset()
    if enero is None or enero != julio:
        return []
    desfase = _desfase(int(enero.total_seconds() // 60))
    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{zona}",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        f"TZOFFSETFROM:{desfase}",
        f"TZOFFSETTO:{desfase}",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]


DAY_MAP_ICAL: dict[int, str] = {
    1: "MO",
    2: "TU",
    3: "WE",
    4: "TH",
    5: "FR",
    6: "SA",
    7: "SU",
}

DAY_NAMES_ES: dict[int, str] = {
    1: "Lunes",
    2: "Martes",
    3: "Miércoles",
    4: "Jueves",
    5: "Viernes",
    6: "Sábado",
    7: "Domingo",
}


class GoogleCalendarConnector:
    """Gestiona la integración y sincronización de bloques de estudio con Google Calendar."""

    GCAL_BASE_URL = "https://calendar.google.com/calendar/render"

    def __init__(self, credentials_path: str | None = None):
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    def has_api_credentials(self) -> bool:
        """Verifica si existen credenciales locales de Google Cloud/Workspace."""
        return bool(self.credentials_path and os.path.isfile(self.credentials_path))

    @staticmethod
    def get_next_date_for_weekday(dia_semana: int, ref_date: date | None = None, zona: str | None = None) -> date:
        """Calcula la próxima fecha calendario correspondiente a un día de la semana (1=Lunes..7=Domingo).

        Sin `ref_date`, "hoy" es el de la zona (la del servidor puede ir otro día por delante).
        """
        ref = ref_date or datetime.now(ZoneInfo(zona_valida(zona))).date()
        # isoweekday: 1=Lunes, 7=Domingo
        days_ahead = (dia_semana - ref.isoweekday()) % 7
        return ref + timedelta(days=days_ahead)

    def generate_gcal_web_url(
        self,
        bloque: BloqueHorario,
        ref_date: date | None = None,
        zona: str | None = None,
    ) -> str:
        """Genera una URL directa de 1-clic para agregar el bloque recurrente a Google Calendar Web.

        `ctz` le dice a Google en qué zona están las horas, para que no las tome en la del calendario.
        """
        target_date = self.get_next_date_for_weekday(bloque.dia_semana, ref_date, zona)
        
        # Parseo de horas HH:MM
        h_start, m_start = map(int, bloque.hora_inicio.split(":"))
        h_end, m_end = map(int, bloque.hora_fin.split(":"))

        start_dt = datetime.combine(target_date, time(hour=h_start, minute=m_start))
        end_dt = datetime.combine(target_date, time(hour=h_end, minute=m_end))

        # Formato Google Calendar: YYYYMMDDTHHMMSS
        dates_param = f"{start_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}"

        dia_nombre = DAY_NAMES_ES.get(bloque.dia_semana, f"Día {bloque.dia_semana}")
        tipo_str = bloque.tipo.value if hasattr(bloque.tipo, "value") else str(bloque.tipo)
        byday = DAY_MAP_ICAL.get(bloque.dia_semana, "MO")

        titulo = f"[Aulento] {bloque.descripcion} ({tipo_str.title()})"
        
        detalles = (
            f"Bloque semanal de estudio programado en Aulento.\n\n"
            f"• Actividad: {bloque.descripcion}\n"
            f"• Categoría: {tipo_str.upper()}\n"
            f"• Frecuencia: Todos los {dia_nombre}s de {bloque.hora_inicio} a {bloque.hora_fin}\n"
            f"• Acceso directo: {bloque.url_acceso or 'Sin URL especificada'}\n\n"
            f"Gestionado por Aulento (Local-first OS de Estudio)."
        )

        ubicacion = bloque.url_acceso or "Aulento"
        recur_rule = f"RRULE:FREQ=WEEKLY;BYDAY={byday}"

        query_params = {
            "action": "TEMPLATE",
            "text": titulo,
            "dates": dates_param,
            "details": detalles,
            "location": ubicacion,
            "recur": recur_rule,
            "ctz": zona_valida(zona),
        }

        return f"{self.GCAL_BASE_URL}?{urllib.parse.urlencode(query_params)}"

    @staticmethod
    def _escape_ical(text: str) -> str:
        """Escapa caracteres reservados según RFC 5545 (backslashes, comas, punto y coma, saltos)."""
        if not text:
            return ""
        return (
            text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n")
        )

    def generate_ical_content(
        self,
        bloques: Sequence[BloqueHorario],
        ref_date: date | None = None,
        zona: str | None = None,
    ) -> str:
        """Genera el contenido completo de un archivo iCalendar (.ics) RFC 5545 para el cronograma.

        Las horas de cada bloque son locales de `zona` (la de la cuenta, o la por defecto): cada evento
        lleva `TZID` para que el calendario no las corra al leerlas como UTC.
        """
        zona = zona_valida(zona)
        now_utc = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Aulento//Weekly Study Schedule//ES",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Aulento - Cronograma Semanal",
            f"X-WR-TIMEZONE:{zona}",
        ]
        lines.extend(_bloque_vtimezone(zona, (ref_date or datetime.now(ZoneInfo(zona)).date()).year))

        for bloque in bloques:
            target_date = self.get_next_date_for_weekday(bloque.dia_semana, ref_date, zona)
            h_start, m_start = map(int, bloque.hora_inicio.split(":"))
            h_end, m_end = map(int, bloque.hora_fin.split(":"))

            start_dt = datetime.combine(target_date, time(hour=h_start, minute=m_start))
            end_dt = datetime.combine(target_date, time(hour=h_end, minute=m_end))

            byday = DAY_MAP_ICAL.get(bloque.dia_semana, "MO")
            dia_nombre = DAY_NAMES_ES.get(bloque.dia_semana, f"Día {bloque.dia_semana}")
            tipo_str = bloque.tipo.value if hasattr(bloque.tipo, "value") else str(bloque.tipo)

            summary = f"[Aulento] {bloque.descripcion} ({tipo_str.title()})"
            description = (
                f"Bloque de estudio semanal ({tipo_str.upper()}).\n"
                f"Horario: {dia_nombre} {bloque.hora_inicio} - {bloque.hora_fin}\n"
                f"Acceso: {bloque.url_acceso or 'N/A'}"
            )
            location = bloque.url_acceso or "Aulento"

            uid = f"study-engine-block-{bloque.id}-{byday.lower()}@studyengine.local"

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_utc}",
                f"DTSTART;TZID={zona}:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID={zona}:{end_dt.strftime('%Y%m%dT%H%M%S')}",
                f"RRULE:FREQ=WEEKLY;BYDAY={byday}",
                f"SUMMARY:{self._escape_ical(summary)}",
                f"DESCRIPTION:{self._escape_ical(description)}",
                f"LOCATION:{self._escape_ical(location)}",
                "STATUS:CONFIRMED",
                "TRANSP:OPAQUE",
                "END:VEVENT",
            ])

        lines.append("END:VCALENDAR")
        lines.append("")  # newline final
        return "\r\n".join(lines)

    def get_block_links(
        self,
        bloques: Sequence[BloqueHorario],
        ref_date: date | None = None,
        zona: str | None = None,
    ) -> list[dict[str, Any]]:
        """Devuelve la lista de bloques con sus URLs de integración directa a Google Calendar."""
        results: list[dict[str, Any]] = []
        for b in sorted(bloques, key=lambda x: (x.dia_semana, x.hora_inicio)):
            dia_nombre = DAY_NAMES_ES.get(b.dia_semana, f"Día {b.dia_semana}")
            tipo_str = b.tipo.value if hasattr(b.tipo, "value") else str(b.tipo)
            gcal_url = self.generate_gcal_web_url(b, ref_date, zona)

            results.append({
                "id": b.id,
                "dia_semana": b.dia_semana,
                "dia_nombre": dia_nombre,
                "hora_inicio": b.hora_inicio,
                "hora_fin": b.hora_fin,
                "tipo": tipo_str,
                "descripcion": b.descripcion,
                "url_acceso": b.url_acceso,
                "gcal_url": gcal_url,
            })
        return results

    def get_status(
        self,
        bloques: Sequence[BloqueHorario] | None = None,
    ) -> dict[str, Any]:
        """Informa el estado de integración, métodos disponibles y estadísticas del cronograma."""
        has_creds = self.has_api_credentials()
        total_blocks = len(bloques) if bloques is not None else 0

        return {
            "configured": True,  # Modo web & iCal siempre disponible sin costo
            "mode": "api_and_web" if has_creds else "web_and_ical",
            "has_api_credentials": has_creds,
            "total_blocks": total_blocks,
            "ics_export_url": "/api/schedule/export/calendar.ics",
            "features": [
                "1-click-web-sync",
                "recurring-weekly-rrule",
                "rfc5545-ics-export",
                "zero-friction-no-cost",
            ],
            "instructions": (
                "Para sincronizar con Google Calendar puedes hacer 1-clic en el botón de cada bloque "
                "para agregarlo recurrentemente a tu calendario, o descargar el archivo .ics e importarlo "
                "en https://calendar.google.com/calendar/u/0/r/settings/export."
            ),
        }
