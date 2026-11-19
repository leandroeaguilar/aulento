from datetime import datetime, timezone
from fsrs import Card, Rating as LibRating, Scheduler, State as LibState

from aulento.db.fsrs_repository import FSRSRepository
from aulento.models.fsrs_card import FSRSCard, FSRSRating, FSRSReviewLog, FSRSState


class FSRSEngine:
    def __init__(self, repo: FSRSRepository, scheduler: Scheduler | None = None):
        self.repo = repo
        self.scheduler = scheduler or Scheduler()

    def _parse_datetime(self, val: datetime | str | None) -> datetime:
        if val is None:
            return datetime.now(timezone.utc)
        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=timezone.utc)
            return val
        parsed = datetime.fromisoformat(str(val))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def to_lib_card(self, db_card: FSRSCard) -> Card:
        """Convierte una entidad FSRSCard de la base de datos a un objeto Card de py-fsrs."""
        due_dt = self._parse_datetime(db_card.due)
        last_dt = self._parse_datetime(db_card.last_review) if db_card.last_review else None

        state_enum = LibState(db_card.state)
        return Card(
            card_id=db_card.id,
            state=state_enum,
            step=db_card.step,
            stability=db_card.stability,
            difficulty=db_card.difficulty,
            due=due_dt,
            last_review=last_dt,
        )

    def review(
        self,
        card_id: int,
        rating: FSRSRating,
        review_time: datetime | None = None,
    ) -> tuple[FSRSCard, FSRSReviewLog]:
        """Procesa una calificación de estudio aplicando las fórmulas de FSRS v5."""
        db_card = self.repo.get_card_by_id(card_id)
        if not db_card:
            raise ValueError(f"Tarjeta FSRS con ID {card_id} no encontrada.")

        now_utc = review_time or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        lib_card = self.to_lib_card(db_card)
        lib_rating = LibRating(int(rating.value))

        # Cálculo matemático FSRS
        updated_card, review_log = self.scheduler.review_card(lib_card, lib_rating, now_utc)

        # Estadísticas de racha y repetición
        reps = db_card.reps + 1
        lapses = db_card.lapses
        if rating == FSRSRating.AGAIN and db_card.state == int(FSRSState.REVIEW):
            lapses += 1

        due_iso = updated_card.due.isoformat()
        last_review_iso = now_utc.isoformat()

        # Cálculo de días del log FSRS (decisión 5 de arquitectura)
        if db_card.last_review:
            last_review_dt = self._parse_datetime(db_card.last_review)
            elapsed_days = max(0.0, (now_utc - last_review_dt).total_seconds() / 86400.0)
        else:
            elapsed_days = 0.0

        due_dt = self._parse_datetime(updated_card.due)
        scheduled_days = max(0.0, (due_dt - now_utc).total_seconds() / 86400.0)

        # Persistir tarjeta actualizada
        saved_card = self.repo.update_card_fsrs(
            card_id=card_id,
            state=int(updated_card.state.value),
            step=updated_card.step,
            stability=updated_card.stability,
            difficulty=updated_card.difficulty,
            due_iso=due_iso,
            last_review_iso=last_review_iso,
            reps=reps,
            lapses=lapses,
        )

        # Persistir log de revisión
        saved_log = self.repo.add_review_log(
            card_id=card_id,
            rating=int(rating.value),
            review_datetime_iso=last_review_iso,
            elapsed_days=elapsed_days,
            scheduled_days=scheduled_days,
            state=int(updated_card.state.value),
        )

        return saved_card, saved_log

    def get_session_cards(self, limit: int = 15, level: str | None = None, force: bool = False) -> list[FSRSCard]:
        """Retorna las tarjetas prioritarias para la sesión de estudio de hoy, con filtro de nivel opcional."""
        return self.repo.get_due_cards(limit=limit, level=level, force=force)
