"""Pruebas del mazo inicial de 100 colocaciones de inglés técnico profesional."""

import pytest
from conftest import cuenta_de_prueba
from aulento.fsrs.deck_seed import DECK_100_ITEMS, seed_fsrs_deck
from aulento.db.fsrs_repository import FSRSRepository


def test_deck_contains_exactly_100_items():
    assert len(DECK_100_ITEMS) == 100


def test_deck_categories_distribution():
    categories = {item["categoria"] for item in DECK_100_ITEMS}
    expected = {
        "data_engineering",
        "business_intelligence",
        "ai_machine_learning",
        "cloud_infrastructure",
        "scrum_workplace",
    }
    assert categories == expected
    for cat in expected:
        count = sum(1 for item in DECK_100_ITEMS if item["categoria"] == cat)
        assert count == 20, f"Categoría {cat} tiene {count} items, se esperaban 20"


def test_deck_no_duplicate_questions():
    questions = [item["item_pregunta"] for item in DECK_100_ITEMS]
    assert len(questions) == len(set(questions)), "Existen preguntas duplicadas en el mazo"


def test_deck_seed_idempotent(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    # Primera siembra
    seed_fsrs_deck(memory_db, cuenta_de_prueba(memory_db).id)
    all_cards = repo.list_cards()
    assert len(all_cards) >= 100

    # Segunda siembra (no debe duplicar registros)
    seed_fsrs_deck(memory_db, cuenta_de_prueba(memory_db).id)
    all_cards_2 = repo.list_cards()
    assert len(all_cards_2) == len(all_cards)
