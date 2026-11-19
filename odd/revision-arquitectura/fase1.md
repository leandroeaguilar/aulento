# Fase 1 — Entorno: zonas horarias, orígenes y log FSRS

Plan maestro: `docs/PENDIENTES.md` (puntos 3, 4 y 10 —días del log FSRS—).
Fuente: revisión de arquitectura del 2026-11-19; los 3 tests de `tests/test_google_calendar.py` fallan en Windows.
Depende de: nada. La fase 2 depende de esta (necesita `tzdata` para sus tests en Windows).

## Estado actual

Ya existe y NO hay que rehacer:

- `src/aulento/connectors/google_calendar.py` define `ZONA_POR_DEFECTO = "America/Argentina/Buenos_Aires"` y `zona_valida(nombre)`, que devuelve la zona pedida si carga o, si no, la por defecto, sin comprobar que esa cargue. `_bloque_vtimezone`, `get_next_date_for_weekday` y la generación del `.ics` llaman a `ZoneInfo(zona)`.
- En Windows sin el paquete `tzdata`, `ZoneInfo` no encuentra ninguna zona (tampoco `"UTC"`).
- `LocalOriginAuthMiddleware` (`src/aulento/web/app.py`) rechaza con 403 todo `Origin` que no esté en `get_allowed_origins()` (8000, 8001, 8080 y `AULENTO_ALLOWED_ORIGINS`). `TrustedHostMiddleware` ya restringe el `Host` a `get_allowed_hosts()`.
- `FSRSEngine.review` (`src/aulento/fsrs/engine.py`) lee `review_log.elapsed_days` y `scheduled_days`, que py-fsrs 6 ya no tiene: siempre guarda 0.
- La CLI de la web pasa `proxy_headers=False`; el esquema real lo resuelve `ProxyHeadersMiddleware` solo con `AULENTO_TRUSTED_PROXIES`.

### Decisiones de diseño

1. **`tzdata` sin condición de plataforma**: `"tzdata>=2024.1"` en `pyproject.toml` y `tzdata==2026.6` en `requirements.txt` (orden alfabético). Justificación: también falta en contenedores Linux mínimos; es un paquete de datos sin dependencias.
2. **Nunca un 500 por la zona**: si ninguna zona IANA carga (ni la pedida, ni la por defecto, ni `"UTC"`), el conector trabaja en UTC con `datetime.timezone.utc` y no falla. El `.ics` se genera igual (por ejemplo, con horas UTC sin `VTIMEZONE`). Se prueba simulando que `ZoneInfo` nunca encuentra una zona.
3. **Aceptar el propio origen**: además de la lista, `LocalOriginAuthMiddleware` acepta un `Origin` igual a `f"{request.url.scheme}://{request.headers['host']}"`. Justificación: un sitio ajeno no puede hacer que el navegador mande como `Origin` el origen del propio servidor; un ataque de DNS rebinding, que sí lo lograría, llega con un `Host` ajeno y lo frena `TrustedHostMiddleware`. Así funciona cualquier `--port` y también `uvicorn` lanzado a mano. El bloqueo por `Sec-Fetch-Site: cross-site` queda igual.
4. **Sin cambios en el esquema OpenAPI**: no se toca `DESCRIPCION_DE_LA_API` ni nada que cambie `app.openapi()`. La fase 0 regenera `docs/api/openapi.json` en paralelo.
5. **Días del log FSRS calculados**: `elapsed_days` = días (con decimales) entre el repaso anterior y este, 0 si es el primero; `scheduled_days` = días entre este repaso y el nuevo `due`. Ambos `>= 0`.

## Tareas

- [x] Punto 3: declarar `tzdata` (decisión 1).
  _Hecho:_ Se agregó `"tzdata>=2024.1"` a `dependencies` en `pyproject.toml` y `tzdata==2026.6` en `requirements.txt` en estricto orden alfabético.
- [x] Punto 3: el conector de calendario no falla aunque ninguna zona cargue (decisión 2), con test.
  _Hecho:_ Se actualizó `src/aulento/connectors/google_calendar.py` (`zona_valida`, `_tzinfo_o_utc`, `_bloque_vtimezone`, `get_next_date_for_weekday`, `generate_ical_content`) para fallback resiliente a UTC sin emitir `VTIMEZONE` ni lanzar excepción. Probado con simulación `ZoneInfoNotFoundError` en `tests/test_revision_entorno.py` (`test_conector_calendario_cuando_ninguna_zona_carga`, `test_endpoint_ics_cuando_ninguna_zona_carga`).
- [x] Punto 4: `LocalOriginAuthMiddleware` acepta el propio origen (decisión 3), con tests: puerto 9000 pasa; origen ajeno sigue en 403; rebinding (`Origin` = `Host` ajeno) frenado por el host.
  _Hecho:_ Se adaptó `LocalOriginAuthMiddleware` en `src/aulento/web/app.py` para permitir `Origin` igual a `f"{request.url.scheme}://{host}"`. Probado en `tests/test_revision_entorno.py` con puerto 9000 (201), origen ajeno (403) y rebinding (400 frenado por `TrustedHostMiddleware`).
- [x] Punto 10: `elapsed_days` y `scheduled_days` reales en `fsrs_review_logs` (decisión 5), con test.
  _Hecho:_ Se calculó `elapsed_days` (días con decimales desde el repaso previo o 0 en el primero) y `scheduled_days` (días hasta el nuevo `due`) en `FSRSEngine.review` (`src/aulento/fsrs/engine.py`), asegurando ambos `>= 0.0`. Cubierto en `tests/test_revision_entorno.py` (`test_fsrs_engine_review_log_dias_calculados`).
- [x] `tests/test_google_calendar.py` en verde en Windows; suite completa y `ruff check .` en verde.
  _Hecho:_ `tests/test_google_calendar.py` (5/5) y `tests/test_revision_entorno.py` (7/7) en verde. `ruff check . --no-cache` limpio (All checks passed!). Suite completa ejecutada: 2353 pasados; los únicos 2 fallos corresponden a archivos en trabajo por el agente de fase 0 en paralelo (`src/aulento/db/migrations.py` y `docs/api/openapi.json`).

## Fuera de alcance

- Lo que corresponde a la fase 0 (`db/repository.py`, `db/migrations.py`, `models/libro.py`, `routes/books.py`, `routes/hub.py`, `pantalla-books.js`, `index.html`, `docs/api/openapi.json`) y a la fase 2.
- Cambiar la zona por defecto del calendario o agregar una interfaz para `zona_horaria` (M7).

## Criterio de hecho

- `GET /api/schedule/export/calendar.ics` responde 200 en Windows.
- `POST /api/books` con `Origin: http://127.0.0.1:9000` y `Host: 127.0.0.1:9000` responde 201; con `Origin: https://evil.example` sigue en 403.
- Un segundo repaso de una tarjeta guarda `elapsed_days > 0` y todo repaso guarda `scheduled_days >= 0` coherente con el nuevo `due`.
- Suite completa y `ruff check .` en verde.

## Correcciones de la revisión

1. **`.ics` en UTC con `TZID` (RFC 5545 §3.2.19 y §3.3.5)**:
   - En `src/aulento/connectors/google_calendar.py` (`generate_ical_content`), cuando la zona resuelta es `"UTC"` (sea por fallback ante falta de zonas IANA o por configuración explícita), `DTSTART` y `DTEND` se emiten en formato UTC nativo (`AAAAMMDDTHHMMSSZ`) sin parámetro `;TZID=...`.
   - Si la zona es normal (ej. `"America/Argentina/Buenos_Aires"`), se preserva `DTSTART;TZID=...:AAAAMMDDTHHMMSS` y `DTEND;TZID=...:AAAAMMDDTHHMMSS`.
   - Se agregaron aserciones sobre `DTSTART` y `DTEND` en `tests/test_revision_entorno.py` para ambos casos (simulando fallo de `ZoneInfo`, con zona `"UTC"` explícita, y con `"America/Argentina/Buenos_Aires"`).

2. **Propio origen sin normalizar**:
   - En `LocalOriginAuthMiddleware` (`src/aulento/web/app.py`), se normaliza el `Host` antes de armar `propio_origen`: conversión a minúsculas y eliminación del puerto por defecto (`:80` para `http`, `:443` para `https`), coincidiendo con la especificación de `Origin` enviada por los navegadores.
   - Ajuste del cierre (Claude Code): se quitó la reescritura del `Host` en el `scope` que había agregado la corrección. Cambiaba el host efectivo de toda la app desde un middleware de seguridad y no estaba pedida; los navegadores mandan el host en minúsculas, y que `TrustedHostMiddleware` rechace `LOCALHOST` es el comportamiento que ya existía. La normalización quedó solo en la comparación, en `_propio_origen`. Se quitó también el test de `LOCALHOST:9000`.
   - Se agregaron tests en `tests/test_revision_entorno.py` verificando:
     - `Host: 127.0.0.1:80` + `Origin: http://127.0.0.1` -> 201 Created.
     - Origen ajeno (`Origin: https://evil.example`) -> 403 Forbidden.
     - Rebinding con host ajeno -> 400 Bad Request.

3. **Código muerto en tests**:
   - En `tests/test_revision_entorno.py`, se removieron las asignaciones innecesarias a la variable de entorno `DATABASE_PATH` (que la app no lee) y se limpiaron los parámetros de fixture `tmp_path` y `monkeypatch` que quedaron sin uso, delegando el aislamiento a `isolated_cloud_env`.

## Verificación del cierre

- Revisión independiente con Gemini 4 Hydrogen (solo lectura): 3 observaciones, corregidas. Claude Code quitó, además, la reescritura del `Host` que agregó la corrección (ver arriba).
- Gate final: suite completa con 2381 tests que pasan, 10 omitidos y ninguno que falle (antes, los 3 de `tests/test_google_calendar.py` fallaban en Windows); `ruff check .` limpio.
- De punta a punta, en Windows, con `aulento web start --port 8791` y datos temporales:
  - `POST /api/books` con `Origin: http://127.0.0.1:8791`: 201. Con `Origin: http://evil.example`: 403.
  - `GET /api/schedule/export/calendar.ics`: 200, con `DTSTART;TZID=America/Argentina/Buenos_Aires:…`.
