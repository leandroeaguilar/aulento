"""Tests para el conector y endpoints de integración con Google Calendar."""

from datetime import date
import pytest
from fastapi.testclient import TestClient

from aulento.connectors.google_calendar import GoogleCalendarConnector, DAY_MAP_ICAL
from aulento.models.horario import BloqueHorario, TipoBloque
from aulento.web.app import create_app


@pytest.fixture
def sample_blocks():
    return [
        BloqueHorario(
            id=1,
            dia_semana=1,  # Lunes
            hora_inicio="09:00",
            hora_fin="10:30",
            tipo=TipoBloque.CURSO,
            descripcion="Machine Learning Avanzado",
            url_acceso="https://meet.google.com/abc-defg-hij",
        ),
        BloqueHorario(
            id=2,
            dia_semana=4,  # Jueves
            hora_inicio="19:00",
            hora_fin="20:00",
            tipo=TipoBloque.INGLES,
            descripcion="Inglés Técnico - Spaced Repetition",
            url_acceso="https://study.engine/fsrs",
        ),
    ]


def test_get_next_date_for_weekday():
    connector = GoogleCalendarConnector()
    # 2026-09-25 es Viernes (isoweekday = 5)
    ref = date(2026, 9, 25)

    # Próximo Lunes (1) -> 2026-09-28 (+3 días)
    next_mon = connector.get_next_date_for_weekday(1, ref_date=ref)
    assert next_mon == date(2026, 9, 28)
    assert next_mon.isoweekday() == 1

    # Mismo día Viernes (5) -> 2026-09-25 (+0 días)
    next_fri = connector.get_next_date_for_weekday(5, ref_date=ref)
    assert next_fri == date(2026, 9, 25)
    assert next_fri.isoweekday() == 5

    # Próximo Domingo (7) -> 2026-09-27 (+2 días)
    next_sun = connector.get_next_date_for_weekday(7, ref_date=ref)
    assert next_sun == date(2026, 9, 27)
    assert next_sun.isoweekday() == 7


def test_generate_gcal_web_url(sample_blocks):
    connector = GoogleCalendarConnector()
    ref = date(2026, 9, 21)  # Lunes
    block = sample_blocks[0]  # Lunes 09:00 - 10:30

    url = connector.generate_gcal_web_url(block, ref_date=ref)
    assert url.startswith("https://calendar.google.com/calendar/render?")
    assert "action=TEMPLATE" in url
    assert "text=%5BStudy+Engine%5D+Machine+Learning+Avanzado+%28Curso%29" in url or "Machine+Learning+Avanzado" in url
    assert "dates=20260921T090000%2F20260921T103000" in url
    assert "recur=RRULE%3AFREQ%3DWEEKLY%3BBYDAY%3DMO" in url
    assert "location=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij" in url


def test_generate_ical_content(sample_blocks):
    connector = GoogleCalendarConnector()
    ref = date(2026, 9, 21)
    ical = connector.generate_ical_content(sample_blocks, ref_date=ref)

    assert "BEGIN:VCALENDAR" in ical
    assert "VERSION:2.0" in ical
    assert "PRODID:-//Aulento//Weekly Study Schedule//ES" in ical
    assert "END:VCALENDAR" in ical

    # Bloque 1
    assert "UID:study-engine-block-1-mo@studyengine.local" in ical
    assert "SUMMARY:[Aulento] Machine Learning Avanzado (Curso)" in ical
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO" in ical
    assert "LOCATION:https://meet.google.com/abc-defg-hij" in ical

    # Bloque 2
    assert "UID:study-engine-block-2-th@studyengine.local" in ical
    assert "SUMMARY:[Aulento] Inglés Técnico - Spaced Repetition (Ingles)" in ical
    assert "RRULE:FREQ=WEEKLY;BYDAY=TH" in ical


def test_get_status_and_links(sample_blocks):
    connector = GoogleCalendarConnector()
    status = connector.get_status(sample_blocks)
    assert status["configured"] is True
    assert status["total_blocks"] == 2
    assert status["ics_export_url"] == "/api/schedule/export/calendar.ics"
    assert "1-click-web-sync" in status["features"]

    links = connector.get_block_links(sample_blocks)
    assert len(links) == 2
    assert links[0]["id"] == 1
    assert "gcal_url" in links[0]
    assert links[0]["dia_nombre"] == "Lunes"


def test_api_schedule_calendar_endpoints(tmp_path, monkeypatch):
    """Valida los endpoints HTTP de Google Calendar en FastAPI."""
    db_file = tmp_path / "test_gcal.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))

    app = create_app()
    with TestClient(app) as client:
        # Crear un bloque de prueba
        res_create = client.post(
            "/api/schedule",
            json={
                "dia_semana": 2,
                "hora_inicio": "14:00",
                "hora_fin": "15:30",
                "tipo": "lectura",
                "descripcion": "Lectura Designing Data-Intensive Applications",
                "url_acceso": "https://learning.oreilly.com",
            },
        )
        assert res_create.status_code == 201
        block_id = res_create.json()["id"]

        # 1. Endpoint status
        res_status = client.get("/api/schedule/google-calendar/status")
        assert res_status.status_code == 200
        data_status = res_status.json()
        assert data_status["configured"] is True
        assert data_status["total_blocks"] >= 1

        # 2. Endpoint links
        res_links = client.get("/api/schedule/google-calendar/links")
        assert res_links.status_code == 200
        links = res_links.json()
        assert any(l["id"] == block_id for l in links)
        block_link = next(l for l in links if l["id"] == block_id)
        assert "calendar.google.com" in block_link["gcal_url"]

        # 3. Endpoint single link
        res_single = client.get(f"/api/schedule/google-calendar/link/{block_id}")
        assert res_single.status_code == 200
        assert "calendar.google.com" in res_single.json()["gcal_url"]

        # 4. Export iCalendar feed .ics
        res_ics = client.get("/api/schedule/export/calendar.ics")
        assert res_ics.status_code == 200
        assert "text/calendar" in res_ics.headers.get("content-type", "")
        assert "BEGIN:VCALENDAR" in res_ics.text
        assert "Designing Data-Intensive Applications" in res_ics.text
        assert "RRULE:FREQ=WEEKLY;BYDAY=TU" in res_ics.text
