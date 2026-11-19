"""Servidor y agregador unificado de métricas de consistencia y Heatmap de Actividad.

Consolida por fecha local minutos de estudio, páginas leídas, tarjetas FSRS repasadas
y temas de rutas completados, calculando scores de consistencia, niveles de intensidad (0-4)
y rachas de estudio activas y récord en la zona horaria de la cuenta.
"""

from datetime import date, datetime, timedelta, timezone, tzinfo
import logging
import sqlite3

from aulento.config import get_db_path
from aulento.core.zona_horaria import fecha_local, fecha_local_str, zona_de_la_cuenta
from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta
from aulento.models.macro_fsrs import (
    ActivityDay,
    ActivityHeatmapResponse,
    StreakInfo,
)

logger = logging.getLogger(__name__)

# Las tablas dependientes se resuelven hasta la tabla raíz que lleva la cuenta dueña
_REPASOS_DE_TARJETAS = "fsrs_review_logs l JOIN fsrs_items i ON i.id = l.card_id"
_TEMAS_DE_RUTAS = (
    "ruta_temas t JOIN ruta_modulos m ON m.id = t.modulo_id JOIN rutas_aprendizaje a ON a.id = m.ruta_id"
)
_REPASOS_DE_TEMAS = (
    "roadmap_topic_reviews v JOIN roadmap_topic_retention r ON r.id = v.retention_id "
    "JOIN ruta_temas t ON t.id = r.tema_id JOIN ruta_modulos m ON m.id = t.modulo_id "
    "JOIN rutas_aprendizaje a ON a.id = m.ruta_id"
)


class ActivityTracker:
    """Motor de métricas diarias de consistencia y análisis de hábitos de estudio de una cuenta."""

    def __init__(
        self,
        user_id: int,
        db_path: str | None = None,
        conn: sqlite3.Connection | None = None,
        zona: tzinfo | None = None,
    ):
        self.user_id = exigir_cuenta(user_id)
        self.db_path = db_path or get_db_path()
        self._external_conn = conn
        self._zona = zona

    def _get_conn(self) -> sqlite3.Connection:
        if self._external_conn:
            return self._external_conn
        conn = get_connection(self.db_path)
        from aulento.db.schema import create_schema
        create_schema(conn)
        return conn

    def _obtener_zona(self, conn: sqlite3.Connection) -> tzinfo:
        if self._zona is not None:
            return self._zona
        return zona_de_la_cuenta(conn, self.user_id)

    @property
    def zona(self) -> tzinfo:
        if self._zona is not None:
            return self._zona
        conn = self._get_conn()
        try:
            return zona_de_la_cuenta(conn, self.user_id)
        finally:
            if not self._external_conn:
                conn.close()

    def get_heatmap(self, days: int = 90, reference_date: date | None = None) -> ActivityHeatmapResponse:
        """Obtiene la serie temporal completa de actividad y las estadísticas de racha."""
        conn = self._get_conn()
        try:
            zona = self._obtener_zona(conn)
            if reference_date is None:
                reference_date = datetime.now(zona).date()

            start_date = reference_date - timedelta(days=days - 1)
            start_str = start_date.isoformat()
            end_str = reference_date.isoformat()

            # Rango SQL ampliado un día de cada lado para cubrir desfases horarios entre UTC y la zona local
            sql_start_str = (start_date - timedelta(days=1)).isoformat()
            sql_end_str = (reference_date + timedelta(days=1)).isoformat()

            cursor = conn.cursor()

            # 1. Minutos de sesiones de estudio reales (Pomodoro / Focus)
            cursor.execute(
                """
                SELECT fecha_hora, duracion_minutos
                FROM sesiones_estudio
                WHERE user_id = ? AND substr(fecha_hora, 1, 10) >= ? AND substr(fecha_hora, 1, 10) <= ?;
                """,
                (self.user_id, sql_start_str, sql_end_str),
            )
            minutes_by_day: dict[str, int] = {}
            for row in cursor.fetchall():
                if not row["fecha_hora"]:
                    continue
                d = fecha_local_str(row["fecha_hora"], zona)
                if start_str <= d <= end_str:
                    minutes_by_day[d] = minutes_by_day.get(d, 0) + int(row["duracion_minutos"] or 0)

            # 2. Tarjetas FSRS repasadas (Inglés y Conceptos)
            cursor.execute(
                f"""
                SELECT l.review_datetime
                FROM {_REPASOS_DE_TARJETAS}
                WHERE i.user_id = ? AND substr(l.review_datetime, 1, 10) >= ? AND substr(l.review_datetime, 1, 10) <= ?;
                """,
                (self.user_id, sql_start_str, sql_end_str),
            )
            fsrs_by_day: dict[str, int] = {}
            for row in cursor.fetchall():
                if not row["review_datetime"]:
                    continue
                d = fecha_local_str(row["review_datetime"], zona)
                if start_str <= d <= end_str:
                    fsrs_by_day[d] = fsrs_by_day.get(d, 0) + 1

            # 3. Revisiones macro FSRS de temas
            cursor.execute(
                f"""
                SELECT v.review_time
                FROM {_REPASOS_DE_TEMAS}
                WHERE a.user_id = ? AND substr(v.review_time, 1, 10) >= ? AND substr(v.review_time, 1, 10) <= ?;
                """,
                (self.user_id, sql_start_str, sql_end_str),
            )
            for row in cursor.fetchall():
                if not row["review_time"]:
                    continue
                d = fecha_local_str(row["review_time"], zona)
                if start_str <= d <= end_str:
                    fsrs_by_day[d] = fsrs_by_day.get(d, 0) + 1

            # 4. Temas completados del Roadmap
            cursor.execute(
                f"""
                SELECT t.fecha_actualizacion
                FROM {_TEMAS_DE_RUTAS}
                WHERE a.user_id = ? AND t.estado = 'completado'
                  AND substr(t.fecha_actualizacion, 1, 10) >= ? AND substr(t.fecha_actualizacion, 1, 10) <= ?;
                """,
                (self.user_id, sql_start_str, sql_end_str),
            )
            topics_by_day: dict[str, int] = {}
            for row in cursor.fetchall():
                if not row["fecha_actualizacion"]:
                    continue
                d = fecha_local_str(row["fecha_actualizacion"], zona)
                if start_str <= d <= end_str:
                    topics_by_day[d] = topics_by_day.get(d, 0) + 1

            # 5. Páginas leídas por día desde avances_de_lectura (decisión 4)
            pages_by_day: dict[str, int] = {}
            try:
                cursor.execute(
                    """
                    SELECT registrado_en, paginas
                    FROM avances_de_lectura
                    WHERE user_id = ? AND substr(registrado_en, 1, 10) >= ? AND substr(registrado_en, 1, 10) <= ?;
                    """,
                    (self.user_id, sql_start_str, sql_end_str),
                )
                for row in cursor.fetchall():
                    if not row["registrado_en"]:
                        continue
                    d = fecha_local_str(row["registrado_en"], zona)
                    if start_str <= d <= end_str:
                        pages_by_day[d] = pages_by_day.get(d, 0) + int(row["paginas"] or 0)
            except sqlite3.OperationalError:
                # Si la base aún no tiene la migración 12 de avances de lectura
                pass

            # Construir la cuadrícula completa día por día
            days_list: list[ActivityDay] = []
            curr = start_date
            while curr <= reference_date:
                d_str = curr.isoformat()
                m = minutes_by_day.get(d_str, 0)
                f = fsrs_by_day.get(d_str, 0)
                t = topics_by_day.get(d_str, 0)
                p = pages_by_day.get(d_str, 0)

                # Fórmula ponderada del Daily Activity Score
                score = round((m * 0.1) + (p * 0.2) + (f * 0.5) + (t * 5.0), 2)

                # Nivel de intensidad (0 a 4)
                if score == 0:
                    level = 0
                elif score <= 5.0:
                    level = 1
                elif score <= 15.0:
                    level = 2
                elif score <= 30.0:
                    level = 3
                else:
                    level = 4

                days_list.append(
                    ActivityDay(
                        date=d_str,
                        study_minutes=m,
                        pages_read=p,
                        fsrs_reviews=f,
                        topics_completed=t,
                        score=score,
                        level=level,
                    )
                )
                curr += timedelta(days=1)

            streak_info = self._calculate_streaks(reference_date, zona=zona)

            return ActivityHeatmapResponse(
                days=days_list,
                streak=streak_info,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            if not self._external_conn:
                conn.close()

    def _calculate_streaks(self, reference_date: date, zona: tzinfo | None = None) -> StreakInfo:
        """Calcula la racha actual y récord histórico recorriendo los días activos en la zona de la cuenta."""
        conn = self._get_conn()
        try:
            if zona is None:
                zona = self._obtener_zona(conn)
            cursor = conn.cursor()

            # Recolectar todos los días con actividad histórica (minutos, tarjetas o temas)
            # Decisión 5: la racha no suma lectura
            query = f"""
            SELECT fecha_hora FROM (
                SELECT fecha_hora FROM sesiones_estudio WHERE user_id = ? AND duracion_minutos > 0
                UNION ALL
                SELECT l.review_datetime FROM {_REPASOS_DE_TARJETAS} WHERE i.user_id = ?
                UNION ALL
                SELECT v.review_time FROM {_REPASOS_DE_TEMAS} WHERE a.user_id = ?
                UNION ALL
                SELECT t.fecha_actualizacion FROM {_TEMAS_DE_RUTAS}
                WHERE a.user_id = ? AND t.estado = 'completado'
            ) WHERE fecha_hora IS NOT NULL;
            """
            cursor.execute(query, (self.user_id,) * 4)
            active_dates_set = {
                fecha_local(row[0], zona)
                for row in cursor.fetchall()
                if row[0]
            }

            total_active_days = len(active_dates_set)

            # 1. Racha Actual
            current_streak = 0
            check_date = reference_date

            if check_date in active_dates_set:
                # Hoy está activo, contamos hacia atrás
                while check_date in active_dates_set:
                    current_streak += 1
                    check_date -= timedelta(days=1)
            else:
                # Hoy aún no ha estudiado, chequeamos si ayer estudió (período de gracia diurno)
                yesterday = reference_date - timedelta(days=1)
                if yesterday in active_dates_set:
                    check_date = yesterday
                    while check_date in active_dates_set:
                        current_streak += 1
                        check_date -= timedelta(days=1)

            # 2. Racha Récord (Longest Streak)
            longest_streak = 0
            if active_dates_set:
                sorted_dates = sorted(active_dates_set)
                temp_streak = 1
                longest_streak = 1
                for i in range(1, len(sorted_dates)):
                    if sorted_dates[i] == sorted_dates[i - 1] + timedelta(days=1):
                        temp_streak += 1
                    elif sorted_dates[i] != sorted_dates[i - 1]:
                        temp_streak = 1
                    if temp_streak > longest_streak:
                        longest_streak = temp_streak

            # 3. Totales acumulados
            cursor.execute(
                "SELECT COALESCE(SUM(duracion_minutos), 0) FROM sesiones_estudio WHERE user_id = ?;", (self.user_id,)
            )
            total_study_mins = int(cursor.fetchone()[0] or 0)

            cursor.execute(f"SELECT COUNT(l.id) FROM {_REPASOS_DE_TARJETAS} WHERE i.user_id = ?;", (self.user_id,))
            total_fsrs = int(cursor.fetchone()[0] or 0)

            cursor.execute(f"SELECT COUNT(v.id) FROM {_REPASOS_DE_TEMAS} WHERE a.user_id = ?;", (self.user_id,))
            total_topic_revs = int(cursor.fetchone()[0] or 0)

            cursor.execute(
                f"SELECT COUNT(t.id) FROM {_TEMAS_DE_RUTAS} WHERE a.user_id = ? AND t.estado = 'completado';",
                (self.user_id,),
            )
            total_topics = int(cursor.fetchone()[0] or 0)

            # Decisión 4: StreakInfo.total_pages_read sigue siendo la suma de pagina_actual
            cursor.execute(
                "SELECT COALESCE(SUM(pagina_actual), 0) FROM libros_lectura WHERE user_id = ?;", (self.user_id,)
            )
            total_pages = int(cursor.fetchone()[0] or 0)

            return StreakInfo(
                current_streak=current_streak,
                longest_streak=longest_streak,
                total_active_days=total_active_days,
                total_study_minutes=total_study_mins,
                total_pages_read=total_pages,
                total_fsrs_reviews=total_fsrs + total_topic_revs,
                total_topics_completed=total_topics,
            )
        finally:
            if not self._external_conn:
                conn.close()
