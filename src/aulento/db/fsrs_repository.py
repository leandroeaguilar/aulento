"""Repositorio SQLite para Tarjetas de Repetición Espaciada (FSRS) y Logs de Repaso."""

import re
import sqlite3
from datetime import datetime, timezone
from typing import Sequence
from aulento.db.cuenta import exigir_cuenta
from aulento.db.roadmap_repository import RoadmapNotFoundError
from aulento.models.fsrs_card import FSRSCard, FSRSCardCreate, FSRSReviewLog


PREFIJO_MAZO_DE_RUTA = "roadmap_"
# Forma canónica, la única que escribe la app: minúsculas, sin ceros a la izquierda y con un id que entra en SQLite.
_MAZO_DE_RUTA = re.compile(r"roadmap_[1-9]\d{0,17}")


def es_mazo_de_ruta(categoria: str | None) -> bool:
    """Indica si la categoría es, exactamente, el mazo de una ruta (`roadmap_<id>`) y no un nivel de inglés."""
    return bool(categoria) and _MAZO_DE_RUTA.fullmatch(categoria) is not None


class MazoDeRutaNoEncontradoError(RoadmapNotFoundError):
    """El mazo `roadmap_<id>` no es de la cuenta: la ruta no existe o es de otra, y la cuenta no tiene tarjetas en él."""

    def __init__(self, roadmap_id: int):
        super().__init__(f"Ruta con ID {roadmap_id} no encontrada: no se puede usar su mazo.")
        self.roadmap_id = roadmap_id


class FSRSRepository:
    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

    def mazo_es_de_la_cuenta(self, categoria: str | None) -> bool:
        """Falso solo si la categoría es el mazo de una ruta (`roadmap_<id>`) que no es de la cuenta.

        Es de la cuenta si la ruta es suya o si ya tiene tarjetas en ese mazo: el de una ruta propia
        borrada sigue valiendo mientras conserve tarjetas. Es la única regla, para leer y para escribir.
        """
        if not es_mazo_de_ruta(categoria):
            return True
        roadmap_id = int(categoria[len(PREFIJO_MAZO_DE_RUTA):])
        fila = self.conn.execute(
            "SELECT 1 FROM rutas_aprendizaje WHERE id = ? AND user_id = ? "
            "UNION ALL SELECT 1 FROM fsrs_items WHERE categoria = ? AND user_id = ? LIMIT 1;",
            (roadmap_id, self.user_id, categoria, self.user_id),
        ).fetchone()
        return fila is not None

    def exigir_mazo_de_la_cuenta(self, categoria: str | None) -> None:
        """Levanta `MazoDeRutaNoEncontradoError` si la categoría es un mazo de ruta que no es de la cuenta."""
        if not self.mazo_es_de_la_cuenta(categoria):
            raise MazoDeRutaNoEncontradoError(int(categoria[len(PREFIJO_MAZO_DE_RUTA):]))

    def create_card(self, c: FSRSCardCreate) -> FSRSCard:
        """Crea la tarjeta de la cuenta o, si ya tiene esa pregunta en ese mazo, actualiza su respuesta.

        Levanta `MazoDeRutaNoEncontradoError` (un `RoadmapNotFoundError`) si el mazo es el de una ruta que no es de la cuenta.
        """
        self.exigir_mazo_de_la_cuenta(c.categoria)
        cursor = self.conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        query = """
        INSERT INTO fsrs_items (user_id, categoria, item_pregunta, respuesta_esperada, contexto_uso, state, step, due)
        VALUES (?, ?, ?, ?, ?, 1, 0, ?)
        ON CONFLICT(user_id, categoria, item_pregunta) DO UPDATE SET
            respuesta_esperada = excluded.respuesta_esperada,
            contexto_uso = excluded.contexto_uso
        RETURNING id, categoria, item_pregunta, respuesta_esperada, contexto_uso, state, step, stability, difficulty, due, last_review, reps, lapses, fecha_creacion;
        """
        cursor.execute(
            query, (self.user_id, c.categoria, c.item_pregunta, c.respuesta_esperada, c.contexto_uso, now_iso)
        )
        row = cursor.fetchone()
        self.conn.commit()
        return FSRSCard(**dict(row))

    def get_card_by_id(self, id: int) -> FSRSCard | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM fsrs_items WHERE id = ? AND user_id = ?;", (id, self.user_id))
        row = cursor.fetchone()
        return FSRSCard(**dict(row)) if row else None

    def list_cards(self, categoria: str | None = None, limit: int | None = None) -> list[FSRSCard]:
        cursor = self.conn.cursor()
        query = "SELECT * FROM fsrs_items WHERE user_id = ?"
        params: list = [self.user_id]
        if categoria:
            query += " AND categoria = ?"
            params.append(categoria)
        query += " ORDER BY id ASC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        cursor.execute(query, params)
        return [FSRSCard(**dict(row)) for row in cursor.fetchall()]

    def get_roadmap_decks(self, now_utc: datetime | None = None) -> list[dict]:
        """Mazos de rutas (`roadmap_<id>`) que tienen tarjetas, con su título, total y vencidas."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT f.categoria AS categoria,
                   COUNT(*) AS total,
                   SUM(CASE WHEN f.due IS NULL OR f.due <= ? THEN 1 ELSE 0 END) AS vencidas
            FROM fsrs_items f
            WHERE f.user_id = ? AND f.categoria LIKE ?
            GROUP BY f.categoria;
            """,
            (now_utc.isoformat(), self.user_id, f"{PREFIJO_MAZO_DE_RUTA}%"),
        )
        mazos = []
        for row in cursor.fetchall():
            if not es_mazo_de_ruta(row["categoria"]):
                continue
            roadmap_id = int(row["categoria"][len(PREFIJO_MAZO_DE_RUTA):])
            ruta = self.conn.execute(
                "SELECT titulo FROM rutas_aprendizaje WHERE id = ? AND user_id = ?", (roadmap_id, self.user_id)
            ).fetchone()
            mazos.append(
                {
                    "categoria": row["categoria"],
                    "roadmap_id": roadmap_id,
                    "titulo": ruta["titulo"] if ruta else f"Ruta eliminada (#{roadmap_id})",
                    "ruta_existe": ruta is not None,
                    "total": row["total"],
                    "vencidas": row["vencidas"] or 0,
                }
            )
        mazos.sort(key=lambda m: (not m["ruta_existe"], m["titulo"].lower()))
        return mazos

    def get_due_cards(
        self,
        limit: int = 15,
        now_utc: datetime | None = None,
        level: str | None = None,
        force: bool = False,
        categoria: str | None = None,
    ) -> list[FSRSCard]:
        """Obtiene las tarjetas que deben ser repasadas hoy o antes de now_utc, con filtro opcional por nivel.
        Si force=True, si no hay tarjetas vencidas suficientes, entrega tarjetas elegibles para práctica extra.
        `categoria` filtra por igualdad exacta y tiene prioridad sobre `level`."""
        if categoria:
            level = None
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()

        if level and level.lower().strip() in ("adaptive", "adaptativo", "ia"):
            from aulento.fsrs.evolution_advisor import get_student_evolution_metrics, LEVEL_KEYS

            metrics = get_student_evolution_metrics(self.conn, self.user_id)
            rec_level = metrics["recommended_level"]
            idx = LEVEL_KEYS.index(rec_level) if rec_level in LEVEL_KEYS else 0
            prev_level = LEVEL_KEYS[max(0, idx - 1)]
            next_level = LEVEL_KEYS[min(len(LEVEL_KEYS) - 1, idx + 1)]

            count_rec = max(1, int(round(limit * 0.7)))
            count_prev = max(1, int(round(limit * 0.2)))
            count_next = max(1, limit - count_rec - count_prev)

            cards_rec = self.get_due_cards(limit=count_rec, level=rec_level, now_utc=now_utc, force=force)
            cards_prev = self.get_due_cards(limit=count_prev, level=prev_level, now_utc=now_utc, force=force) if prev_level != rec_level else []
            cards_next = self.get_due_cards(limit=count_next, level=next_level, now_utc=now_utc, force=force) if next_level != rec_level else []

            seen_ids = set()
            combined: list[FSRSCard] = []
            for c in cards_rec + cards_prev + cards_next:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    combined.append(c)

            if len(combined) < limit:
                fill_cards = self.get_due_cards(limit=limit, level=None, now_utc=now_utc, force=force)
                for c in fill_cards:
                    if c.id not in seen_ids:
                        seen_ids.add(c.id)
                        combined.append(c)
                        if len(combined) >= limit:
                            break
            return combined[:limit]

        cursor = self.conn.cursor()

        level_filter = ""
        level_params: list = []
        if level and level.lower() not in ("all", "todos", "*"):
            lvl = level.lower().strip()
            prefix_map = {
                "a1": "a1",
                "a1_foundations": "a1",
                "a2": "a2",
                "a2_daily_work": "a2",
                "b1": "b1",
                "b1_data_storytelling": "b1",
                "b2": "b2",
                "b2_tech_data_ai": "b2",
                "c1": "c1",
                "c1_consulting_ai": "c1",
            }
            if es_mazo_de_ruta(lvl):
                # El mazo de una ruta se filtra exacto: `roadmap_5` no debe traer `roadmap_50`.
                level_filter = " AND categoria = ?"
                level_params = [lvl]
            else:
                target_prefix = prefix_map.get(lvl, lvl)
                level_filter = " AND (categoria = ? OR categoria LIKE ?)"
                level_params = [lvl, f"{target_prefix}%"]
        if categoria:
            level_filter = " AND categoria = ?"
            level_params = [categoria]

        if not force:
            query = f"""
            SELECT * FROM fsrs_items
            WHERE user_id = ? AND (due IS NULL OR due <= ?)
            {level_filter}
            ORDER BY
                CASE WHEN state = 1 THEN 0 WHEN state = 3 THEN 1 ELSE 2 END,
                due ASC
            LIMIT ?;
            """
            params = [self.user_id, now_iso] + level_params + [limit]
        else:
            query = f"""
            SELECT * FROM fsrs_items
            WHERE user_id = ?
            {level_filter}
            ORDER BY
                CASE WHEN (due IS NULL OR due <= ?) THEN 0 ELSE 1 END,
                CASE WHEN state = 1 THEN 0 WHEN state = 3 THEN 1 ELSE 2 END,
                due ASC,
                stability ASC
            LIMIT ?;
            """
            params = [self.user_id] + level_params + [now_iso, limit]

        cursor.execute(query, params)
        return [FSRSCard(**dict(row)) for row in cursor.fetchall()]

    def update_card_fsrs(
        self,
        card_id: int,
        state: int,
        step: int,
        stability: float | None,
        difficulty: float | None,
        due_iso: str,
        last_review_iso: str,
        reps: int,
        lapses: int,
    ) -> FSRSCard | None:
        cursor = self.conn.cursor()
        query = """
        UPDATE fsrs_items
        SET state = ?,
            step = ?,
            stability = ?,
            difficulty = ?,
            due = ?,
            last_review = ?,
            reps = ?,
            lapses = ?
        WHERE id = ? AND user_id = ?;
        """
        cursor.execute(
            query,
            (state, step, stability, difficulty, due_iso, last_review_iso, reps, lapses, card_id, self.user_id),
        )
        self.conn.commit()
        return self.get_card_by_id(card_id)

    def add_review_log(
        self,
        card_id: int,
        rating: int,
        review_datetime_iso: str,
        elapsed_days: float,
        scheduled_days: float,
        state: int,
    ) -> FSRSReviewLog:
        if not self.get_card_by_id(card_id):
            # Una tarjeta de otra cuenta falla igual que una que no existe
            raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        cursor = self.conn.cursor()
        query = """
        INSERT INTO fsrs_review_logs (card_id, rating, review_datetime, elapsed_days, scheduled_days, state)
        VALUES (?, ?, ?, ?, ?, ?)
        RETURNING id, card_id, rating, review_datetime, elapsed_days, scheduled_days, state;
        """
        cursor.execute(
            query,
            (card_id, rating, review_datetime_iso, elapsed_days, scheduled_days, state),
        )
        row = cursor.fetchone()
        self.conn.commit()
        return FSRSReviewLog(**dict(row))

    def count_stats(self, now_utc: datetime | None = None) -> dict:
        """Calcula conteos de tarjetas por estado y vencimiento."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()

        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) as total FROM fsrs_items WHERE user_id = ?;", (self.user_id,))
        total = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT count(*) as due_today FROM fsrs_items WHERE user_id = ? AND (due IS NULL OR due <= ?);",
            (self.user_id, now_iso),
        )
        due_today = cursor.fetchone()["due_today"]

        cursor.execute(
            "SELECT state, count(*) as count FROM fsrs_items WHERE user_id = ? GROUP BY state;", (self.user_id,)
        )
        by_state = {row["state"]: row["count"] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT count(*) as total_reviews
            FROM fsrs_review_logs l
            JOIN fsrs_items i ON i.id = l.card_id
            WHERE i.user_id = ?;
            """,
            (self.user_id,),
        )
        total_reviews = cursor.fetchone()["total_reviews"]

        return {
            "total": total,
            "due_today": due_today,
            "learning": by_state.get(1, 0),
            "review": by_state.get(2, 0),
            "relearning": by_state.get(3, 0),
            "total_reviews": total_reviews,
        }

    def delete_card(self, id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM fsrs_items WHERE id = ? AND user_id = ?;", (id, self.user_id))
        self.conn.commit()
        return cursor.rowcount > 0
