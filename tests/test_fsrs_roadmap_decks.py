"""Tests del repaso FSRS por ruta: mazos `roadmap_<id>` (028)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import administrador_de_prueba, cuenta_de_prueba
from fastapi.testclient import TestClient
from front import js_del_front

from aulento.db.connection import get_connection
from aulento.db.fsrs_repository import FSRSRepository, es_mazo_de_ruta
from aulento.models.fsrs_card import FSRSCardCreate
from aulento.web.app import create_app


def _ruta(conn, titulo, ruta_id=None):
    """Crea una ruta de la cuenta de la base, con un id elegido si se pide."""
    cuenta = conn.execute("SELECT MIN(id) FROM usuarios").fetchone()[0]
    cursor = conn.execute(
        "INSERT INTO rutas_aprendizaje (id, user_id, titulo) VALUES (?, ?, ?)", (ruta_id, cuenta, titulo)
    )
    conn.commit()
    return cursor.lastrowid


def _tarjeta(repo, categoria, pregunta, vence_en_horas=-1):
    card = repo.create_card(FSRSCardCreate(categoria=categoria, item_pregunta=pregunta, respuesta_esperada=f"R de {pregunta}"))
    due = (datetime.now(UTC) + timedelta(hours=vence_en_horas)).isoformat()
    repo.update_card_fsrs(card.id, 1, 0, 1.0, 5.0, due, due, 1, 0)
    return card


@pytest.mark.parametrize(
    ("categoria", "esperado"),
    [
        ("roadmap_5", True),
        ("roadmap_120", True),
        ("ROADMAP_12", False),
        (" roadmap_7 ", False),
        ("roadmap_007", False),
        ("roadmap_0", False),
        ("roadmap_99999999999999999999", False),
        ("roadmap_", False),
        ("roadmap_5x", False),
        ("roadmap_abc", False),
        ("b2_tech_data_ai", False),
        ("all", False),
        ("", False),
        (None, False),
    ],
)
def test_es_mazo_de_ruta(categoria, esperado):
    assert es_mazo_de_ruta(categoria) is esperado


def test_repaso_filtra_el_mazo_exacto_de_la_ruta(memory_db):
    """R1: `roadmap_5` no trae las tarjetas de `roadmap_50` ni las de inglés."""
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    _ruta(memory_db, "Ruta 5", ruta_id=5)
    _ruta(memory_db, "Ruta 50", ruta_id=50)
    _tarjeta(repo, "roadmap_5", "¿Qué es la memoria de trabajo?")
    _tarjeta(repo, "roadmap_50", "¿Qué es el imperativo categórico?")
    _tarjeta(repo, "b2_tech_data_ai", "¿Cómo se dice 'cuello de botella'?")

    de_la_5 = repo.get_due_cards(limit=20, level="roadmap_5")
    assert [c.item_pregunta for c in de_la_5] == ["¿Qué es la memoria de trabajo?"]

    de_la_50 = repo.get_due_cards(limit=20, level="roadmap_50")
    assert [c.categoria for c in de_la_50] == ["roadmap_50"]

    assert repo.get_due_cards(limit=20, level="roadmap_999") == []
    assert len(repo.get_due_cards(limit=20, level="all")) == 3
    assert [c.categoria for c in repo.get_due_cards(limit=20, level="b2")] == ["b2_tech_data_ai"]


def test_repaso_de_ruta_respeta_vencimiento_y_practica_extra(memory_db):
    """R1: sin forzar solo salen las vencidas; con práctica extra, también las demás del mismo mazo."""
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    _ruta(memory_db, "Ruta 5", ruta_id=5)
    _ruta(memory_db, "Ruta 50", ruta_id=50)
    _tarjeta(repo, "roadmap_5", "Vencida")
    _tarjeta(repo, "roadmap_5", "Futura", vence_en_horas=48)
    _tarjeta(repo, "roadmap_50", "De otra ruta")

    assert [c.item_pregunta for c in repo.get_due_cards(limit=20, level="roadmap_5")] == ["Vencida"]
    extra = repo.get_due_cards(limit=20, level="roadmap_5", force=True)
    assert {c.item_pregunta for c in extra} == {"Vencida", "Futura"}


def test_mazos_de_rutas_con_titulo_y_conteos(memory_db):
    """R2: solo los mazos de rutas con tarjetas, con el título de la ruta, el total y las vencidas."""
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    psico = _ruta(memory_db, "Psicología Cognitiva")
    filo = _ruta(memory_db, "Filosofía Moderna")
    _ruta(memory_db, "Ruta sin tarjetas")

    _tarjeta(repo, f"roadmap_{psico}", "P1")
    _tarjeta(repo, f"roadmap_{psico}", "P2", vence_en_horas=48)
    _tarjeta(repo, f"roadmap_{filo}", "F1")
    # El mazo de una ruta borrada conserva sus tarjetas
    _ruta(memory_db, "Ruta que se borra", ruta_id=9999)
    _tarjeta(repo, "roadmap_9999", "Huérfana")
    memory_db.execute("DELETE FROM rutas_aprendizaje WHERE id = 9999")
    memory_db.commit()
    _tarjeta(repo, "roadmap_notas", "No es un mazo de ruta")
    _tarjeta(repo, "b2_tech_data_ai", "Inglés")

    mazos = repo.get_roadmap_decks()
    assert [(m["titulo"], m["total"], m["vencidas"], m["ruta_existe"]) for m in mazos] == [
        ("Filosofía Moderna", 1, 1, True),
        ("Psicología Cognitiva", 2, 1, True),
        ("Ruta eliminada (#9999)", 1, 1, False),
    ]
    assert mazos[1]["categoria"] == f"roadmap_{psico}"
    assert mazos[1]["roadmap_id"] == psico


def test_categorias_no_canonicas_ni_se_listan_ni_rompen(memory_db):
    """Solo se lista lo que después se puede repasar: mayúsculas, espacios, ceros a la izquierda o ids enormes quedan fuera."""
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    ruta = _ruta(memory_db, "Psicología Cognitiva")
    canonica = f"roadmap_{ruta}"
    _tarjeta(repo, canonica, "Canónica")
    for rara in (canonica.upper(), f"{canonica} ", f"roadmap_00{ruta}", "roadmap_99999999999999999999"):
        _tarjeta(repo, rara, f"Rara {rara!r}")

    mazos = repo.get_roadmap_decks()
    assert [(m["categoria"], m["total"]) for m in mazos] == [(canonica, 1)]
    assert [c.item_pregunta for c in repo.get_due_cards(limit=20, level=mazos[0]["categoria"])] == ["Canónica"]
    # El filtro acepta el nivel con otra capitalización o espacios y devuelve el mismo mazo canónico
    assert [c.item_pregunta for c in repo.get_due_cards(limit=20, level=f" {canonica.upper()} ")] == ["Canónica"]


def test_tarjeta_recien_creada_cuenta_como_vencida(memory_db):
    """Una tarjeta sin fecha de repaso todavía (due NULL) está para hoy."""
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    ruta = _ruta(memory_db, "Filosofía Moderna")
    nueva = repo.create_card(FSRSCardCreate(categoria=f"roadmap_{ruta}", item_pregunta="Nueva", respuesta_esperada="R"))
    memory_db.execute("UPDATE fsrs_items SET due = NULL WHERE id = ?", (nueva.id,))
    memory_db.commit()
    assert [(m["total"], m["vencidas"]) for m in repo.get_roadmap_decks()] == [(1, 1)]


def test_sin_tarjetas_de_rutas_no_hay_mazos(memory_db):
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    _tarjeta(repo, "b2_tech_data_ai", "Inglés")
    assert repo.get_roadmap_decks() == []


def test_api_mazos_y_repaso_por_ruta():
    conn = get_connection()
    try:
        repo = FSRSRepository(conn, administrador_de_prueba(conn).id)
        ruta_id = _ruta(conn, "Psicología Cognitiva")
        _tarjeta(repo, f"roadmap_{ruta_id}", "¿Qué es la atención selectiva?")
        _tarjeta(repo, "c1_consulting_ai", "¿Cómo se dice 'hoja de ruta'?")
        conn.commit()
    finally:
        conn.close()

    client = TestClient(create_app())
    mazos = client.get("/api/fsrs/decks")
    assert mazos.status_code == 200
    propios = [m for m in mazos.json() if m["roadmap_id"] == ruta_id]
    assert propios == [
        {
            "categoria": f"roadmap_{ruta_id}",
            "roadmap_id": ruta_id,
            "titulo": "Psicología Cognitiva",
            "ruta_existe": True,
            "total": 1,
            "vencidas": 1,
        }
    ]

    due = client.get(f"/api/fsrs/due?limit=20&level=roadmap_{ruta_id}")
    assert due.status_code == 200
    assert [c["item_pregunta"] for c in due.json()] == ["¿Qué es la atención selectiva?"]


def test_interfaz_tiene_el_selector_de_ruta():
    """R3: el repaso ofrece elegir una ruta y vuelve al repaso por nivel al deseleccionarla."""
    import aulento.web as web_pkg

    static = Path(web_pkg.__file__).parent / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    js = js_del_front()

    fila = html[html.index('id="fsrs-roadmap-deck-row"'):]
    fila = fila[: fila.index(">")]
    assert "hidden" in fila, "la fila del selector debe nacer oculta"
    assert 'id="fsrs-roadmap-deck-select"' in html
    assert 'data-accion="seleccionar-mazo-ruta-fsrs"' in html
    assert "['seleccionar-mazo-ruta-fsrs', (el) => selectFsrsRoadmapDeck(el.value)]" in js

    def cuerpo(nombre):
        inicio = js.index(f"function {nombre}(")
        return js[inicio : js.index("\n}\n", inicio)]

    carga = cuerpo("loadFsrsRoadmapDecks")
    assert "fetch('/api/fsrs/decks')" in carga
    assert "row.classList.toggle('hidden', decks.length === 0)" in carga
    # El título de la ruta se inserta como texto: el único innerHTML permitido es el vaciado del selector
    assert "opt.textContent = `${d.titulo} — ${d.total} ${d.total === 1 ? 'tarjeta' : 'tarjetas'}, ${d.vencidas} para hoy`" in carga
    assert carga.count("innerHTML") == 1
    assert "select.innerHTML = ''" in carga
    # Si el mazo elegido desaparece se vuelve al repaso por nivel; si falla la consulta no se toca nada
    assert "if (elegido && !sigueExistiendo) selectFsrsLevel('all');" in carga
    assert "if (!res.ok) return;" in carga

    # La sesión de repaso refresca los mazos y descarta respuestas viejas
    sesion = cuerpo("loadFsrsSession")
    assert "loadFsrsRoadmapDecks();" in sesion
    assert "if (pedido !== fsrsSessionRequestSeq) return;" in sesion

    assert "selectFsrsLevel(categoria || 'all')" in cuerpo("selectFsrsRoadmapDeck")
    # La tarjeta muestra el título de la ruta, no "ROADMAP 5"
    assert "mazoDeRuta ? mazoDeRuta.titulo" in js
    # Elegir un nivel deselecciona la ruta
    assert "deckSelect.value = String(lvl).startsWith('roadmap_') ? lvl : ''" in js
