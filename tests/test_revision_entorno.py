"""Tests de la Fase 1 (Entorno): zonas horarias, orígenes y días del log FSRS."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from conftest import cuenta_de_prueba
from fastapi.testclient import TestClient

from aulento.connectors.google_calendar import (
    GoogleCalendarConnector,
    zona_valida,
)
from aulento.db.fsrs_repository import FSRSRepository
from aulento.fsrs.engine import FSRSEngine
from aulento.models.fsrs_card import FSRSCardCreate, FSRSRating
from aulento.models.horario import BloqueHorario, TipoBloque
from aulento.web.app import create_app


# ---------------------------------------------------------------------------
# Punto 3 / Decisión 1 y 2: tzdata y resiliencia ante ausencia de zonas IANA
# ---------------------------------------------------------------------------


def test_tzdata_carga_zona_por_defecto():
    """Verifica que tzdata provee la base de zonas horarias IANA."""
    tz = ZoneInfo("America/Argentina/Buenos_Aires")
    assert tz.key == "America/Argentina/Buenos_Aires"


def test_conector_calendario_cuando_ninguna_zona_carga(monkeypatch):
    """Decisión 2: si ZoneInfo nunca encuentra una zona, el conector cae en UTC y no falla."""

    def raise_not_found(key):
        raise ZoneInfoNotFoundError(f"Zona simulada no encontrada: {key}")

    monkeypatch.setattr("aulento.connectors.google_calendar.ZoneInfo", raise_not_found)

    # 1. zona_valida cae en UTC
    assert zona_valida("America/Argentina/Buenos_Aires") == "UTC"
    assert zona_valida(None) == "UTC"
    assert zona_valida("Invalida") == "UTC"

    connector = GoogleCalendarConnector()

    # 2. get_next_date_for_weekday no falla
    proxima_fecha = connector.get_next_date_for_weekday(1)
    assert isinstance(proxima_fecha, date)
    assert proxima_fecha.isoweekday() == 1

    # 3. generate_gcal_web_url genera ctz=UTC
    bloque = BloqueHorario(
        id=1,
        dia_semana=2,
        hora_inicio="10:00",
        hora_fin="11:30",
        tipo=TipoBloque.CURSO,
        descripcion="Arquitectura de Software",
        url_acceso="https://aulento.test",
    )
    url = connector.generate_gcal_web_url(bloque)
    assert "ctz=UTC" in url
    assert "Arquitectura+de+Software" in url

    # 4. generate_ical_content genera .ics sin VTIMEZONE y con DTSTART/DTEND en UTC (Z sin TZID, RFC 5545)
    fecha_bloque = connector.get_next_date_for_weekday(bloque.dia_semana)
    fecha_str = fecha_bloque.strftime("%Y%m%d")
    ical = connector.generate_ical_content([bloque])
    assert "BEGIN:VCALENDAR" in ical
    assert "X-WR-TIMEZONE:UTC" in ical
    assert "BEGIN:VTIMEZONE" not in ical
    assert f"DTSTART:{fecha_str}T100000Z" in ical
    assert f"DTEND:{fecha_str}T113000Z" in ical
    assert ";TZID=" not in ical
    assert "END:VCALENDAR" in ical

    # También con zona UTC explícita
    ical_utc = connector.generate_ical_content([bloque], zona="UTC")
    assert f"DTSTART:{fecha_str}T100000Z" in ical_utc
    assert f"DTEND:{fecha_str}T113000Z" in ical_utc
    assert ";TZID=" not in ical_utc


def test_endpoint_ics_cuando_ninguna_zona_carga(monkeypatch):
    """GET /api/schedule/export/calendar.ics responde 200 aunque ninguna zona IANA cargue."""

    def raise_not_found(key):
        raise ZoneInfoNotFoundError(f"Zona simulada no encontrada: {key}")

    monkeypatch.setattr("aulento.connectors.google_calendar.ZoneInfo", raise_not_found)

    app = create_app()
    with TestClient(app) as client:
        # Crear un bloque de prueba
        res_create = client.post(
            "/api/schedule",
            json={
                "dia_semana": 3,
                "hora_inicio": "15:00",
                "hora_fin": "16:00",
                "tipo": "lectura",
                "descripcion": "Estudio sin zonas",
            },
        )
        assert res_create.status_code == 201

        # Endpoint .ics responde 200 con fallback UTC, sin VTIMEZONE y con formato Z sin TZID
        res_ics = client.get("/api/schedule/export/calendar.ics")
        assert res_ics.status_code == 200
        assert "text/calendar" in res_ics.headers.get("content-type", "")
        assert "BEGIN:VCALENDAR" in res_ics.text
        assert "X-WR-TIMEZONE:UTC" in res_ics.text
        assert "BEGIN:VTIMEZONE" not in res_ics.text
        assert ";TZID=" not in res_ics.text
        assert "T150000Z" in res_ics.text
        assert "T160000Z" in res_ics.text

        # Status y links también responden 200
        res_status = client.get("/api/schedule/google-calendar/status")
        assert res_status.status_code == 200
        res_links = client.get("/api/schedule/google-calendar/links")
        assert res_links.status_code == 200


def test_ical_content_dtstart_dtend_formato_segun_zona_utc_y_buenos_aires():
    """RFC 5545 (§3.2.19 y §3.3.5): en UTC emite Z sin TZID; en Buenos Aires emite TZID sin Z."""
    connector = GoogleCalendarConnector()
    ref = date(2026, 9, 21)  # Lunes
    bloque = BloqueHorario(
        id=1,
        dia_semana=2,  # Martes -> 2026-09-22
        hora_inicio="10:00",
        hora_fin="11:30",
        tipo=TipoBloque.CURSO,
        descripcion="Arquitectura de Software",
        url_acceso="https://aulento.test",
    )

    # 1. Zona UTC explícita: formato UTC AAAAMMDDTHHMMSSZ, sin TZID ni VTIMEZONE
    ical_utc = connector.generate_ical_content([bloque], ref_date=ref, zona="UTC")
    assert "BEGIN:VCALENDAR" in ical_utc
    assert "X-WR-TIMEZONE:UTC" in ical_utc
    assert "BEGIN:VTIMEZONE" not in ical_utc
    assert "DTSTART:20260922T100000Z" in ical_utc
    assert "DTEND:20260922T113000Z" in ical_utc
    assert ";TZID=" not in ical_utc

    # 2. Zona normal (Buenos Aires): DTSTART;TZID=America/Argentina/Buenos_Aires:..., con VTIMEZONE
    ical_ba = connector.generate_ical_content([bloque], ref_date=ref, zona="America/Argentina/Buenos_Aires")
    assert "BEGIN:VCALENDAR" in ical_ba
    assert "X-WR-TIMEZONE:America/Argentina/Buenos_Aires" in ical_ba
    assert "BEGIN:VTIMEZONE" in ical_ba
    assert "DTSTART;TZID=America/Argentina/Buenos_Aires:20260922T100000" in ical_ba
    assert "DTEND;TZID=America/Argentina/Buenos_Aires:20260922T113000" in ical_ba
    assert "DTSTART;TZID=America/Argentina/Buenos_Aires:20260922T100000Z" not in ical_ba


# ---------------------------------------------------------------------------
# Punto 4 / Decisión 3: LocalOriginAuthMiddleware acepta el propio origen
# ---------------------------------------------------------------------------


def test_local_origin_auth_puerto_9000_pasa():
    """Punto 4: un POST con Origin y Host en el puerto 9000 es aceptado (201)."""
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:9000") as client:
        headers = {
            "Host": "127.0.0.1:9000",
            "Origin": "http://127.0.0.1:9000",
        }
        res = client.post(
            "/api/books",
            json={"titulo": "Designing Data-Intensive Applications"},
            headers=headers,
        )
        assert res.status_code == 201
        assert res.json()["titulo"] == "Designing Data-Intensive Applications"


def test_local_origin_auth_puerto_80_por_defecto_normalizado_pasa():
    """Host 127.0.0.1:80 con Origin http://127.0.0.1 pasa al normalizar el puerto por defecto."""
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {
            "Host": "127.0.0.1:80",
            "Origin": "http://127.0.0.1",
        }
        res = client.post(
            "/api/books",
            json={"titulo": "Libro Puerto 80"},
            headers=headers,
        )
        assert res.status_code == 201
        assert res.json()["titulo"] == "Libro Puerto 80"


def test_local_origin_auth_origen_ajeno_bloqueado_403():
    """Punto 4: un POST con Origin ajeno sigue respondiendo 403 Forbidden."""
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:9000") as client:
        headers = {
            "Host": "127.0.0.1:9000",
            "Origin": "https://evil.example",
        }
        res = client.post(
            "/api/books",
            json={"titulo": "Libro Malicioso"},
            headers=headers,
        )
        assert res.status_code == 403
        assert "cross-origin request not permitted" in res.json()["detail"]


def test_local_origin_auth_rebinding_frenado_por_host():
    """Punto 4: un ataque de DNS rebinding (Origin == Host ajeno) es frenado por TrustedHostMiddleware (400)."""
    app = create_app()
    with TestClient(app, base_url="http://evil.example") as client:
        headers = {
            "Host": "evil.example",
            "Origin": "http://evil.example",
        }
        res = client.post(
            "/api/books",
            json={"titulo": "Ataque Rebinding"},
            headers=headers,
        )
        # TrustedHostMiddleware rechaza hosts no autorizados con 400 Bad Request
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Punto 10 / Decisión 5: Días calculados en FSRS review log
# ---------------------------------------------------------------------------


def test_fsrs_engine_review_log_dias_calculados(memory_db):
    """Punto 10: elapsed_days y scheduled_days se calculan con valores reales >= 0."""
    repo = FSRSRepository(memory_db, cuenta_de_prueba(memory_db).id)
    engine = FSRSEngine(repo)

    card = repo.create_card(
        FSRSCardCreate(
            categoria="cloud_ia",
            item_pregunta="¿Cómo se define 'prompt injection'?",
            respuesta_esperada="Técnica que manipula el modelo para omitir instrucciones previas.",
        )
    )

    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Primer repaso: elapsed_days debe ser 0.0, scheduled_days >= 0.0
    saved_card1, log1 = engine.review(card.id, FSRSRating.GOOD, review_time=t0)
    assert log1.elapsed_days == 0.0
    assert log1.scheduled_days >= 0.0

    due1 = engine._parse_datetime(saved_card1.due)
    esperado_scheduled1 = max(0.0, (due1 - t0).total_seconds() / 86400.0)
    assert abs(log1.scheduled_days - esperado_scheduled1) < 1e-4

    # 2. Segundo repaso 2 días y medio después: elapsed_days debe ser ~2.5 (> 0)
    t1 = t0 + timedelta(days=2.5)
    saved_card2, log2 = engine.review(card.id, FSRSRating.GOOD, review_time=t1)
    assert log2.elapsed_days > 0.0
    assert abs(log2.elapsed_days - 2.5) < 1e-4
    assert log2.scheduled_days >= 0.0

    due2 = engine._parse_datetime(saved_card2.due)
    esperado_scheduled2 = max(0.0, (due2 - t1).total_seconds() / 86400.0)
    assert abs(log2.scheduled_days - esperado_scheduled2) < 1e-4

    # 3. Tercer repaso con AGAIN 1 día después: scheduled_days >= 0 y elapsed_days ~1.0
    t2 = t1 + timedelta(days=1.0)
    saved_card3, log3 = engine.review(card.id, FSRSRating.AGAIN, review_time=t2)
    assert log3.elapsed_days > 0.0
    assert abs(log3.elapsed_days - 1.0) < 1e-4
    assert log3.scheduled_days >= 0.0
