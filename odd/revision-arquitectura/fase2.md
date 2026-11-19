# Fase 2 — El día de la cuenta: zona horaria y páginas leídas

Plan maestro: `docs/PENDIENTES.md` (puntos 6 y 8 —lectura en el mapa de calor—).
Fuente: revisión de arquitectura del 2026-11-19.
Depende de: fase 0 (tabla `avances_de_lectura`) y fase 1 (`tzdata`, para que las zonas carguen en Windows).

## Estado actual

Ya existe y NO hay que rehacer:

- Las marcas de tiempo se guardan en UTC, en dos formatos:
  - ISO con zona, por ejemplo `2026-11-19T01:00:00.123456+00:00`: `fsrs_review_logs.review_datetime`, `sesiones_estudio.fecha_hora` (desde `FocusRepository`) y `avances_de_lectura.registrado_en`.
  - `CURRENT_TIMESTAMP` de SQLite, `2026-11-19 01:00:00`, sin zona y en UTC: `ruta_temas.fecha_actualizacion`, `roadmap_topic_reviews.review_time` y `libros_lectura.fecha_actualizacion`.
- `ActivityTracker` (`src/aulento/core/activity_tracker.py`) agrupa con `substr(x, 1, 10)` y toma `date.today()` como hoy; la racha usa los mismos días.
- `FocusRepository` (`src/aulento/db/focus_repository.py`) calcula «hoy» y «la semana» desde la medianoche UTC.
- El planificador (`core/study_planner.py`) y el MCP (`mcp/tools_schedule.py`) ya usan la hora local de la máquina.
- El ajuste de cuenta `zona_horaria` existe (`AJUSTE_ZONA_HORARIA` en `src/aulento/web/routes/schedule.py`), lo lee solo el calendario y no tiene interfaz para fijarlo. `AjustesDeCuenta.leer` acepta cualquier clave con nombre válido.
- Después de la fase 0 existe `avances_de_lectura (id, user_id, libro_id, paginas, registrado_en)`: una fila por cada subida de página, con `registrado_en` ISO UTC.

### Decisiones de diseño

1. **La zona de la cuenta**: nuevo módulo `src/aulento/core/zona_horaria.py` con `AJUSTE_ZONA_HORARIA = "zona_horaria"` (`schedule.py` pasa a importarlo de ahí, sin cambiar su comportamiento) y `zona_de_la_cuenta(conn, user_id) -> tzinfo`: el ajuste si está fijado y carga con `ZoneInfo`; si no, la zona de la máquina (`datetime.now().astimezone().tzinfo`). Justificación: es lo que ya hacen el planificador y el MCP, y en modo local es la zona de la persona; el ajuste manda cuando existe (una extensión de la nube puede fijarlo).
2. **Agrupar en Python, no en SQL**: los dos formatos de fecha no se comparan bien como texto y SQLite no conoce zonas IANA. Se filtra en SQL por un rango ampliado un día de cada lado y se convierte cada marca a fecha local en Python (un ayudante que acepte los dos formatos y tome como UTC lo que no trae zona).
3. **Inyectable para los tests**: `ActivityTracker` y `FocusRepository` aceptan `zona: tzinfo | None = None`; sin ella la resuelven con `zona_de_la_cuenta`. Las fábricas de `web/dependencies.py` no cambian.
4. **Páginas leídas por día** = suma de `avances_de_lectura.paginas` del día local. `StreakInfo.total_pages_read` sigue siendo la suma de `pagina_actual` (las páginas leídas en total). Los días anteriores a la migración 12 quedan en 0.
5. **La racha no suma lectura**: hoy cuentan minutos, tarjetas, repasos de temas y temas completados; se mantiene así, solo cambia cómo se calcula el día.

## Tareas

- [x] `core/zona_horaria.py` con `zona_de_la_cuenta` y el ayudante de conversión (decisiones 1 y 2), con tests de los dos formatos.
  _Hecho:_ Se creó `src/aulento/core/zona_horaria.py` con `AJUSTE_ZONA_HORARIA = "zona_horaria"`, `zona_de_la_cuenta(conn, user_id)` (lee de `AjustesDeCuenta` o cae a la zona del sistema), `convertir_a_zona(marca, zona)`, `fecha_local(marca, zona)` y `fecha_local_str(marca, zona)`. `src/aulento/web/routes/schedule.py` importa `AJUSTE_ZONA_HORARIA` de allí. Se verificaron ambos formatos de marca de tiempo (ISO con zona/Z y `CURRENT_TIMESTAMP` sin zona) en `tests/test_revision_dia_de_la_cuenta.py`.
- [x] Punto 6: mapa de calor y rachas en días de la zona de la cuenta (decisiones 2 y 3).
  _Hecho:_ En `src/aulento/core/activity_tracker.py`, `ActivityTracker` acepta `zona: tzinfo | None = None` y la resuelve con `zona_de_la_cuenta` si no fue provista. `get_heatmap` y `_calculate_streaks` filtran en SQL por rango ampliado y convierten cada marca de tiempo de las 4 fuentes históricas a fecha local en Python. La racha se evalúa contra las fechas locales activas y `reference_date` cae en la fecha local de la cuenta.
- [x] Punto 6: «hoy» y «la semana» de `FocusRepository` en la zona de la cuenta (semana desde el lunes local).
  _Hecho:_ En `src/aulento/db/focus_repository.py`, `FocusRepository` recibe `zona: tzinfo | None = None` y resuelve con `zona_de_la_cuenta`. En `get_weekly_stats`, `start_of_today` y `start_of_week` (lunes a las 00:00 h local) se calculan en la zona local; las sesiones se agrupan en Python por comparación con los datetimes conscientes locales, evitando que los minutos de hoy se reinicien a las 21 h locales (00 h UTC).
- [x] Punto 8: páginas por día desde `avances_de_lectura` (decisión 4).
  _Hecho:_ En `src/aulento/core/activity_tracker.py`, `pages_by_day` suma los avances reales registrados en `avances_de_lectura.paginas` para el día local. `StreakInfo.total_pages_read` se mantiene como la suma de `libros_lectura.pagina_actual`. La racha no incluye lectura (decisión 5).
- [x] Tests con la cuenta en `America/Argentina/Buenos_Aires`: un repaso a las 23:30 locales (02:30 UTC del día siguiente) cuenta en el día local; una sesión a las 22:00 locales suma a «hoy»; las páginas del día salen de los avances. Suite completa y `ruff check .` en verde.
  _Hecho:_ Creado `tests/test_revision_dia_de_la_cuenta.py` con 9 tests exhaustivos cubriendo resolución de zona, conversión de formatos, actividad nocturna entre 21 y 24 h en heatmap y racha, cálculo semanal desde el lunes local, «hoy» sin reseteo nocturno, y suma de páginas desde avances de lectura. Suite completa (2378 pasados, 10 salteados) y `ruff check . --no-cache` limpios.

## Fuera de alcance

- La zona del calendario y una interfaz para fijar `zona_horaria` (M7).
- Que la lectura cuente para la racha (decisión 5).
- Otras pantallas o métricas que calculen «hoy» por su cuenta.

## Criterio de hecho

- Con la cuenta en Buenos Aires, la actividad de las 21 a las 24 h locales aparece en el día local en el mapa de calor y mantiene la racha.
- «Minutos de hoy» no vuelve a cero a las 21 h locales.
- Un libro que pasa de la página 100 a la 130 suma 30 páginas ese día, no 130.
- Suite completa y `ruff check .` en verde.

## Verificación del cierre

- Revisión independiente con Gemini 4 Hydrogen: se detuvo porque el sistema se quedó sin memoria, antes de escribir nada. La revisión la hizo Claude Code a mano: la implementación respeta las decisiones 1 a 5. Quedan dos riesgos menores, anotados en `docs/PENDIENTES.md` como M9 (una marca de tiempo ilegible tumba el mapa de calor) y M10 (sin `zona_horaria`, desfase fijo de la máquina). La revisión con Hydrogen sigue pendiente (M11).
- Gate final: suite completa con 2381 tests que pasan, 10 omitidos y ninguno que falle; `ruff check .` limpio.
- De punta a punta, con `aulento web start --port 8791` y datos temporales: `GET /api/focus/stats` devolvió `minutos_hoy: 25` con `inicio_semana` del lunes a las 00:00 −03:00. `GET /api/activity/heatmap?days=7` marcó hoy (2026-11-19, local) `pages_read: 30` tras avanzar un libro de 0 a 30, mientras `total_pages_read` sigue siendo la suma de páginas actuales. No se probó con una cuenta en otra zona por HTTP: no hay ruta para fijar `zona_horaria` (M7); ese caso lo cubren los tests con el ajuste en Buenos Aires.
