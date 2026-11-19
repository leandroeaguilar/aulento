"""Repositorio SQLite para Sesiones Reales de Estudio y Métricas de Enfoque."""

from datetime import datetime, timedelta, timezone, tzinfo
import sqlite3
from typing import Any

from aulento.core.zona_horaria import convertir_a_zona, zona_de_la_cuenta
from aulento.db.cuenta import exigir_cuenta
from aulento.models.focus_session import FocusSession, FocusSessionCreate


class FocusRepository:
    """Acceso a datos para el registro de sesiones reales de estudio (Focus / Pomodoro)."""

    def __init__(self, conn: sqlite3.Connection, user_id: int, zona: tzinfo | None = None):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)
        self.zona = zona if zona is not None else zona_de_la_cuenta(conn, self.user_id)

    def record_session(self, session: FocusSessionCreate) -> FocusSession:
        """Registra una sesión de estudio completada en SQLite."""
        cursor = self.conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        if session.bloque_id is not None:
            cursor.execute(
                "SELECT 1 FROM bloques_horarios WHERE id = ? AND user_id = ?;", (session.bloque_id, self.user_id)
            )
            if not cursor.fetchone():
                # Un bloque de otra cuenta falla igual que uno que no existe
                raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

        query = """
        INSERT INTO sesiones_estudio (user_id, bloque_id, duracion_minutos, tipo, fecha_hora, notas)
        VALUES (?, ?, ?, ?, ?, ?)
        RETURNING id, bloque_id, duracion_minutos, tipo, fecha_hora, notas;
        """
        cursor.execute(
            query,
            (self.user_id, session.bloque_id, session.duracion_minutos, session.tipo, now_iso, session.notas),
        )
        row = cursor.fetchone()
        self.conn.commit()
        return FocusSession(**dict(row))

    def list_sessions(self, limit: int = 50) -> list[FocusSession]:
        """Obtiene las sesiones de estudio más recientes."""
        cursor = self.conn.cursor()
        query = (
            "SELECT id, bloque_id, duracion_minutos, tipo, fecha_hora, notas FROM sesiones_estudio "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?;"
        )
        cursor.execute(query, (self.user_id, limit))
        return [FocusSession(**dict(row)) for row in cursor.fetchall()]

    def get_weekly_stats(self, now_utc: datetime | None = None) -> dict[str, Any]:
        """Calcula minutos y horas reales estudiadas en la semana actual y hoy en la zona de la cuenta."""
        if now_utc is None:
            now_local = datetime.now(self.zona)
        else:
            now_local = convertir_a_zona(now_utc, self.zona)

        # Inicio de hoy y de la semana en la zona horaria de la cuenta (lunes a las 00:00 locales)
        start_of_today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_today - timedelta(days=start_of_today.weekday())

        # Filtramos en SQL ampliando un día hacia atrás desde el lunes para capturar sesiones
        # cuya marca UTC haya caído en el día calendario anterior según la diferencia de zona.
        sql_start = (start_of_week.date() - timedelta(days=1)).isoformat()

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT duracion_minutos, tipo, fecha_hora
            FROM sesiones_estudio
            WHERE user_id = ? AND substr(fecha_hora, 1, 10) >= ?;
            """,
            (self.user_id, sql_start),
        )

        total_mins_week = 0
        total_sessions_week = 0
        total_mins_today = 0
        by_type: dict[str, int] = {}

        for row in cursor.fetchall():
            if not row["fecha_hora"]:
                continue
            dt_local = convertir_a_zona(row["fecha_hora"], self.zona)
            if dt_local >= start_of_week:
                minutos = int(row["duracion_minutos"] or 0)
                tipo = str(row["tipo"])
                total_mins_week += minutos
                total_sessions_week += 1
                by_type[tipo] = by_type.get(tipo, 0) + minutos
                if dt_local >= start_of_today:
                    total_mins_today += minutos

        return {
            "minutos_semana": total_mins_week,
            "horas_semana": round(total_mins_week / 60.0, 1),
            "sesiones_semana": total_sessions_week,
            "minutos_hoy": total_mins_today,
            "horas_hoy": round(total_mins_today / 60.0, 1),
            "por_tipo_minutos": by_type,
            "inicio_semana": start_of_week.isoformat(),
        }
