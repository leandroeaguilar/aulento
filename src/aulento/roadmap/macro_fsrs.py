"""Motor de Repetición Espaciada Macro (FSRS v5) para Temas del Roadmap y Micro-Quizzes Feynman.

Gestiona la retención a largo plazo de los temas completados en las Rutas de Aprendizaje,
calibra la dificultad inicial según la Taxonomía de Bloom y genera micro-evaluaciones
activas de 3 minutos basadas en la Técnica Feynman.
"""

from datetime import datetime, timezone, timedelta
import logging
import sqlite3
from typing import Any

from aulento.config import get_db_path
from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta
from aulento.models.macro_fsrs import (
    MacroFSRSState,
    TopicRetention,
    TopicRetentionCreate,
    TopicReviewLog,
    MicroQuizFeynman,
)

logger = logging.getLogger(__name__)


def calibrate_bloom_difficulty(titulo: str, descripcion: str | None = None) -> float:
    """Calcula la dificultad inicial de retención FSRS v5 según la Taxonomía de Bloom."""
    text = f"{titulo} {descripcion or ''}".lower()

    # Nivel 5 & 6 (Evaluar / Crear / Arquitectura)
    if any(w in text for w in ("arquitectura", "diseñ", "crear", "evaluar", "optimizar", "avanzad", "tunning", "troubleshoot", "internals")):
        return 7.0

    # Nivel 3 & 4 (Aplicar / Analizar)
    if any(w in text for w in ("implementar", "analiz", "construir", "consultoría", "desarrollo", "pipeline", "etl", "orquestaci")):
        return 5.5

    # Nivel 1 & 2 (Recordar / Comprender / Fundamentos)
    if any(w in text for w in ("introducci", "fundamento", "básico", "conceptos", "qu[eé] es", "primeros pasos", "sintaxis")):
        return 3.8

    return 5.0  # Dificultad neutra por defecto


class MacroFSRSRepository:
    """Acceso a datos persistentes para la retención macro de los temas de las rutas de una cuenta."""

    def __init__(self, user_id: int, db_path: str | None = None, conn: sqlite3.Connection | None = None):
        self.user_id = exigir_cuenta(user_id)
        self.db_path = db_path or get_db_path()
        self._external_conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        if self._external_conn:
            return self._external_conn
        conn = get_connection(self.db_path)
        from aulento.db.schema import create_schema
        create_schema(conn)
        return conn

    def init_topic_retention(
        self,
        tema_id: int,
        due_days: int = 3,
        stability: float = 2.0,
        difficulty: float | None = None,
    ) -> TopicRetention:
        """Inicializa de forma idempotente el registro de retención para un tema completado.

        Un tema de otra cuenta falla igual que uno que no existe (`sqlite3.IntegrityError`).
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Datos del tema, solo si es de una ruta de la cuenta
            cursor.execute(
                """
                SELECT t.titulo, t.descripcion
                FROM ruta_temas t
                JOIN ruta_modulos m ON m.id = t.modulo_id
                JOIN rutas_aprendizaje a ON a.id = m.ruta_id
                WHERE t.id = ? AND a.user_id = ?;
                """,
                (tema_id, self.user_id),
            )
            t_row = cursor.fetchone()
            if not t_row:
                raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

            # Verificar si ya existe
            cursor.execute("SELECT * FROM roadmap_topic_retention WHERE tema_id = ?;", (tema_id,))
            row = cursor.fetchone()
            if row:
                return TopicRetention(**dict(row))

            if difficulty is None:
                difficulty = calibrate_bloom_difficulty(t_row["titulo"], t_row["descripcion"])

            now = datetime.now(timezone.utc)
            due_date = now + timedelta(days=due_days)

            cursor.execute(
                """
                INSERT INTO roadmap_topic_retention (
                    tema_id, state, due_date, stability, difficulty,
                    elapsed_days, scheduled_days, reps, lapses, fecha_creacion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *;
                """,
                (
                    tema_id,
                    MacroFSRSState.NEW.value,
                    due_date.isoformat(),
                    stability,
                    difficulty,
                    0,
                    due_days,
                    0,
                    0,
                    now.isoformat(),
                ),
            )
            created_row = cursor.fetchone()
            conn.commit()
            return TopicRetention(**dict(created_row))
        finally:
            if not self._external_conn:
                conn.close()

    def get_due_topics(self, now_utc: datetime | None = None) -> list[TopicRetention]:
        """Obtiene la lista de temas que tienen su fecha de repaso vencida."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = """
            SELECT r.*, t.titulo as tema_titulo, a.titulo as ruta_titulo, a.id as ruta_id
            FROM roadmap_topic_retention r
            JOIN ruta_temas t ON t.id = r.tema_id
            JOIN ruta_modulos m ON m.id = t.modulo_id
            JOIN rutas_aprendizaje a ON a.id = m.ruta_id
            WHERE a.user_id = ? AND r.due_date <= ?
            ORDER BY r.due_date ASC;
            """
            cursor.execute(query, (self.user_id, now_utc.isoformat()))
            rows = cursor.fetchall()
            return [TopicRetention(**dict(row)) for row in rows]
        finally:
            if not self._external_conn:
                conn.close()

    def get_by_tema_id(self, tema_id: int) -> TopicRetention | None:
        """Obtiene el estado de retención de un tema por su ID."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = """
            SELECT r.*, t.titulo as tema_titulo, a.titulo as ruta_titulo, a.id as ruta_id
            FROM roadmap_topic_retention r
            JOIN ruta_temas t ON t.id = r.tema_id
            JOIN ruta_modulos m ON m.id = t.modulo_id
            JOIN rutas_aprendizaje a ON a.id = m.ruta_id
            WHERE r.tema_id = ? AND a.user_id = ?;
            """
            cursor.execute(query, (tema_id, self.user_id))
            row = cursor.fetchone()
            return TopicRetention(**dict(row)) if row else None
        finally:
            if not self._external_conn:
                conn.close()

    def list_all_retention(self) -> list[TopicRetention]:
        """Lista todos los temas en el sistema de retención macro."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = """
            SELECT r.*, t.titulo as tema_titulo, a.titulo as ruta_titulo, a.id as ruta_id
            FROM roadmap_topic_retention r
            JOIN ruta_temas t ON t.id = r.tema_id
            JOIN ruta_modulos m ON m.id = t.modulo_id
            JOIN rutas_aprendizaje a ON a.id = m.ruta_id
            WHERE a.user_id = ?
            ORDER BY r.due_date ASC;
            """
            cursor.execute(query, (self.user_id,))
            return [TopicRetention(**dict(row)) for row in cursor.fetchall()]
        finally:
            if not self._external_conn:
                conn.close()


class MacroFSRSEngine:
    """Motor de cálculo de intervalos espaciados y micro-quizzes de retención Feynman de una cuenta."""

    def __init__(self, user_id: int, repository: MacroFSRSRepository | None = None, db_path: str | None = None):
        self.user_id = exigir_cuenta(user_id)
        if repository is not None and repository.user_id != self.user_id:
            raise ValueError("El repositorio de retención es de otra cuenta.")
        self.repo = repository or MacroFSRSRepository(self.user_id, db_path=db_path)

    def review_topic(
        self,
        tema_id: int,
        rating: int,  # 1: Again, 2: Hard, 3: Good, 4: Easy
        notas: str = "",
        review_time: datetime | None = None,
    ) -> TopicRetention:
        """Aplica la fórmula de repetición espaciada FSRS v5 a un tema del Roadmap."""
        retention = self.repo.get_by_tema_id(tema_id)
        if not retention:
            # Inicializar si no existía
            retention = self.repo.init_topic_retention(tema_id)

        if review_time is None:
            review_time = datetime.now(timezone.utc)

        # Cálculo de intervalo FSRS v5 adaptado a temas macro
        current_interval = max(1, retention.scheduled_days)
        reps = retention.reps + 1
        lapses = retention.lapses

        if rating == 1:  # AGAIN (Olvido / Falla)
            lapses += 1
            new_state = MacroFSRSState.RELEARNING.value
            new_stability = max(1.0, retention.stability * 0.6)
            new_difficulty = min(10.0, retention.difficulty + 0.8)
            next_interval_days = 1
        elif rating == 2:  # HARD (Recordado con esfuerzo)
            new_state = MacroFSRSState.REVIEW.value
            new_stability = retention.stability * 1.2
            new_difficulty = min(10.0, retention.difficulty + 0.3)
            next_interval_days = max(2, int(current_interval * 1.3))
        elif rating == 3:  # GOOD (Recordado con éxito)
            new_state = MacroFSRSState.REVIEW.value
            new_stability = retention.stability * 2.2
            new_difficulty = max(1.0, retention.difficulty - 0.1)
            next_interval_days = max(4, int(current_interval * 2.4))
        else:  # EASY (Dominio absoluto)
            new_state = MacroFSRSState.REVIEW.value
            new_stability = retention.stability * 3.5
            new_difficulty = max(1.0, retention.difficulty - 0.5)
            next_interval_days = max(7, int(current_interval * 3.6))

        new_due_date = review_time + timedelta(days=next_interval_days)

        # Persistir en base de datos
        conn = self.repo._get_conn()
        try:
            cursor = conn.cursor()
            # 1. Insertar review log
            cursor.execute(
                """
                INSERT INTO roadmap_topic_reviews (
                    retention_id, rating, scheduled_days, elapsed_days, review_time, notas
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    retention.id,
                    rating,
                    next_interval_days,
                    retention.elapsed_days,
                    review_time.isoformat(),
                    notas or None,
                ),
            )
            # 2. Actualizar topic retention
            cursor.execute(
                """
                UPDATE roadmap_topic_retention
                SET state = ?,
                    due_date = ?,
                    stability = ?,
                    difficulty = ?,
                    elapsed_days = ?,
                    scheduled_days = ?,
                    reps = ?,
                    lapses = ?,
                    last_review = ?
                WHERE id = ?;
                """,
                (
                    new_state,
                    new_due_date.isoformat(),
                    round(new_stability, 2),
                    round(new_difficulty, 2),
                    current_interval,
                    next_interval_days,
                    reps,
                    lapses,
                    review_time.isoformat(),
                    retention.id,
                ),
            )
            conn.commit()
            return self.repo.get_by_tema_id(tema_id)  # type: ignore
        finally:
            if not self.repo._external_conn:
                conn.close()

    def get_feynman_microquiz(self, tema_id: int) -> MicroQuizFeynman:
        """Genera un micro-quiz interactivo de 3 minutos aplicando Active Recall y Técnica Feynman."""
        conn = self.repo._get_conn()
        try:
            cursor = conn.cursor()
            query = """
            SELECT t.id, t.titulo as tema_titulo, t.descripcion as tema_desc,
                   a.titulo as ruta_titulo, c.contenido_markdown
            FROM ruta_temas t
            JOIN ruta_modulos m ON m.id = t.modulo_id
            JOIN rutas_aprendizaje a ON a.id = m.ruta_id
            LEFT JOIN ruta_clases c ON c.tema_id = t.id
            WHERE t.id = ? AND a.user_id = ?;
            """
            cursor.execute(query, (tema_id, self.user_id))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Tema con ID {tema_id} no encontrado.")

            titulo = row["tema_titulo"]
            ruta = row["ruta_titulo"]
            desc = row["tema_desc"] or ""

            # Pregunta de Active Recall y Desafío Feynman específicos
            active_recall = (
                f"Sin mirar apuntes ni documentación: ¿Cuál es el problema fundamental que resuelve '{titulo}' "
                f"en {ruta}, y qué consecuencia crítica ocurre si no se implementa correctamente en producción?"
            )

            feynman_challenge = (
                f"Explica '{titulo}' en un mensaje de voz o párrafo breve como si se lo estuvieras "
                "enseñando a un programador junior. Utiliza una analogía del mundo real, evita tecnicismos "
                "vacíos y destaca cuándo utilizarlo y cuándo evitarlo."
            )

            evaluation_points = [
                f"Definición clara y propósito de negocio/técnico de '{titulo}'",
                "Mención de ventajas, compensaciones (trade-offs) o alternativas",
                "Ejemplo concreto o analogía clara sin repetir definiciones de memoria",
            ]

            return MicroQuizFeynman(
                tema_id=tema_id,
                tema_titulo=titulo,
                ruta_titulo=ruta,
                concepto_clave=desc or titulo,
                pregunta_active_recall=active_recall,
                desafio_feynman=feynman_challenge,
                puntos_clave_evaluacion=evaluation_points,
            )
        finally:
            if not self.repo._external_conn:
                conn.close()
