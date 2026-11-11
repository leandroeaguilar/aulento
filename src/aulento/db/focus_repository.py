"""Repositorio SQLite para Sesiones Reales de Estudio y Métricas de Enfoque."""

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from aulento.db.cuenta import exigir_cuenta
from aulento.models.focus_session import FocusSession, FocusSessionCreate


class FocusRepository:
    """Acceso a datos para el registro de sesiones reales de estudio (Focus / Pomodoro)."""

    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

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

    def list_sessions(self, limit: int = 50) -> List[FocusSession]:
        """Obtiene las sesiones de estudio más recientes."""
        cursor = self.conn.cursor()
        query = (
            "SELECT id, bloque_id, duracion_minutos, tipo, fecha_hora, notas FROM sesiones_estudio "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?;"
        )
        cursor.execute(query, (self.user_id, limit))
        return [FocusSession(**dict(row)) for row in cursor.fetchall()]

    def get_weekly_stats(self, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
        """Calcula minutos y horas reales estudiadas en la semana actual y hoy."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        # Inicio de la semana actual (Lunes)
        start_of_week = (now_utc - timedelta(days=now_utc.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_of_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        cursor = self.conn.cursor()

        # Total semana
        cursor.execute(
            "SELECT COALESCE(SUM(duracion_minutos), 0), COUNT(id) FROM sesiones_estudio WHERE user_id = ? AND fecha_hora >= ?;",
            (self.user_id, start_of_week.isoformat()),
        )
        row_week = cursor.fetchone()
        total_mins_week = int(row_week[0] if row_week else 0)
        total_sessions_week = int(row_week[1] if row_week else 0)

        # Total hoy
        cursor.execute(
            "SELECT COALESCE(SUM(duracion_minutos), 0) FROM sesiones_estudio WHERE user_id = ? AND fecha_hora >= ?;",
            (self.user_id, start_of_today.isoformat()),
        )
        row_today = cursor.fetchone()
        total_mins_today = int(row_today[0] if row_today else 0)

        # Desglose por tipo en la semana
        cursor.execute(
            "SELECT tipo, COALESCE(SUM(duracion_minutos), 0) FROM sesiones_estudio "
            "WHERE user_id = ? AND fecha_hora >= ? GROUP BY tipo;",
            (self.user_id, start_of_week.isoformat()),
        )
        by_type = {row[0]: int(row[1]) for row in cursor.fetchall()}

        return {
            "minutos_semana": total_mins_week,
            "horas_semana": round(total_mins_week / 60.0, 1),
            "sesiones_semana": total_sessions_week,
            "minutos_hoy": total_mins_today,
            "horas_hoy": round(total_mins_today / 60.0, 1),
            "por_tipo_minutos": by_type,
            "inicio_semana": start_of_week.isoformat(),
        }
