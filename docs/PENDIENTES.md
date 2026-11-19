---
type: Plan
title: "Pendientes de la revisión de arquitectura"
description: "Bugs, fallos e inconsistencias encontrados en la revisión de arquitectura del 2026-11-19, con su estado. Los puntos 1 a 10 se corrigen en la rama fix/revision-arquitectura; el resto queda pendiente."
generated:
  by: process:claude-code
  at: 2026-11-19T00:00:00Z
---

# Pendientes de la revisión de arquitectura

Hallazgos de la revisión del 2026-11-19 (core v0.1.0). Cada uno tiene su estado: ✅ hecho, 🔧 en curso, ⏳ pendiente. Cuando se cierre un punto, se marca acá con el commit que lo resolvió.

Al revisar, la suite daba 2345 tests verdes y 3 rojos en Windows (los del punto 3), con `ruff` limpio.

## Tablero

| # | Hallazgo | Severidad | Estado | Fase |
|---|---|---|---|---|
| 1 | Editar un libro (PUT) guarda valores inválidos y deja la lista de libros en 500 | Alta | ✅ Hecho | 0 |
| 2 | Un libro se marca «completado» al avanzar páginas si está en su último capítulo | Alta | ✅ Hecho | 0 |
| 3 | Sin `tzdata`, en Windows el calendario (.ics, feed y enlaces) responde 500 | Alta | ✅ Hecho | 1 |
| 4 | Con `--port` distinto de 8000/8001/8080, la interfaz no puede guardar nada (403) | Media | ✅ Hecho | 1 |
| 5 | Los cursos se ordenan por prioridad alfabéticamente (alta, baja, media) | Baja | ✅ Hecho | 0 |
| 6 | Actividad, rachas y «minutos de hoy» cuentan el día en UTC | Media | ✅ Hecho | 2 |
| 7 | El webhook de libros busca por título parcial y puede actualizar otro libro | Media | ✅ Hecho | 0 |
| 8 | «Páginas leídas» del mapa de calor suma la página actual, no lo leído ese día | Media | ✅ Hecho | 0 y 2 |
| 9 | En modo local, la ayuda del atajo de Libros promete abrir la app a la red, cosa que el modo local impide | Baja | ✅ Hecho | 0 |
| 10 | Campos que se aceptan y se ignoran: `estado` del avance de un curso, `autor` del libro, días del log FSRS | Baja | ✅ Hecho | 0 y 1 |
| 11 | Manejo de conexiones heterogéneo: `RoadmapRepository` ignora la conexión recibida | Media | ⏳ Pendiente | — |
| 12 | Las migraciones corren desde varios lugares y con criterios distintos ante un fallo | Media | ⏳ Pendiente | — |
| 13 | `AULENTO_EXTENSIONS` se lee en `aulento mcp serve` pero no en `aulento web` | Baja | ⏳ Pendiente | — |
| 14 | Revocaciones masivas que no confirman su transacción, contra lo que dice el docstring | Baja | ⏳ Pendiente | — |
| M1 | Piso de dependencia `fsrs>=3.0.0` incompatible con el código; el README dice FSRS v5 | Baja | ⏳ Pendiente | — |
| M2 | Docstring de `web/routes/books.py` ubicado después de los imports | Baja | ⏳ Pendiente | — |
| M3 | Comentarios de `start.sh` y `start.bat` sobre un código de administrador que el modo local no tiene | Baja | ⏳ Pendiente | — |
| M4 | Versión «0.1.0» escrita a mano en `web/app.py` en lugar de `__version__` | Baja | ⏳ Pendiente | — |
| M5 | `docs/` no viaja en el wheel: instalado sin `-e`, el manual de la app queda «en preparación» | Baja | ⏳ Pendiente | — |
| M6 | Datos personales dentro del producto: plataformas semilla, zona por defecto y nombres heredados | Baja | ⏳ Pendiente | — |
| M7 | El calendario cae en Buenos Aires si la cuenta no fijó `zona_horaria`, y no hay interfaz para fijarla | Baja | ⏳ Pendiente | — |
| M8 | Las herramientas MCP y el copiloto también buscan libros por título parcial | Baja | ⏳ Pendiente | — |
| M9 | Una marca de tiempo ilegible en la base hace responder 500 a todo el mapa de calor | Baja | ⏳ Pendiente | — |
| M10 | Sin `zona_horaria`, el día se cuenta con el desfase fijo de la máquina (sin cambios de horario) | Baja | ⏳ Pendiente | — |
| M11 | Revisión independiente (Gemini 4 Hydrogen) de la fase 2: se cortó por falta de memoria | Baja | ⏳ Pendiente | 2 |

## Fases de la rama `fix/revision-arquitectura`

Las tareas de cada fase están en `odd/revision-arquitectura/faseN.md`.

| Fase | Puntos | Depende de | Estado |
|---|---|---|---|
| 0. Libros y cursos | 1, 2, 5, 7, 8 (registro), 9, 10 (`estado` y `autor`) | — | ✅ Hecho |
| 1. Entorno | 3, 4, 10 (log FSRS) | — | ✅ Hecho |
| 2. El día de la cuenta | 6, 8 (lectura en el mapa de calor) | 0 (tabla de avances), 1 (`tzdata`) | ✅ Hecho |

```text
fase 0 ──┐
         ├──> fase 2
fase 1 ──┘
```

### Verificación (2026-11-19, sin commitear todavía)

- Implementación: Antigravity con Gemini 3.8 Flash. Revisión independiente: Gemini 4 Hydrogen, en modo de solo lectura, para las fases 0 y 1; sus observaciones se corrigieron. La de la fase 2 se cortó por falta de memoria (M11) y se revisó a mano.
- Suite completa: 2381 tests pasan, 10 omitidos y ninguno falla (antes, 3 fallaban en Windows). `ruff check .` limpio.
- De punta a punta, con `aulento web start --port 8791` y datos temporales:
  - Mismo origen en el puerto 8791: 201. Origen ajeno: 403.
  - Libro de 300 páginas a la página 30: sigue «leyendo».
  - PUT inválido: 400, y `GET /api/books` sigue en 200.
  - Se puede borrar el autor.
  - El `.ics` responde 200 en Windows.
  - Webhook: título ambiguo, 409 con candidatos; `%` no coincide con todos los libros; página fuera de rango, 400.
  - Cursos en orden alta, media, baja; el `estado` del avance se respeta.
  - «Minutos de hoy» y la semana se cuentan en hora local (−03:00).
  - El mapa de calor marca hoy 30 páginas, lo avanzado, y no la página actual.

## Detalle

### 1. PUT de un libro sin validación

`LibroRepository.update` (`src/aulento/db/repository.py`) escribe los valores combinados sin validarlos, a diferencia de `update_progress`. Un `PUT /api/books/{id}` con `total_paginas` menor que la página actual guarda la fila; al releerla, el modelo `Libro` la rechaza y tanto el PUT como `GET /api/books` responden 500 desde ese momento. **Arreglo:** validar antes de escribir (400) y reparar con una migración las filas que ya quedaron inválidas.

### 2. Libro completado por estar en el último capítulo

La regla `capitulo_actual >= total_capitulos` toma «estoy en el último capítulo» como «terminé». Con el valor por defecto (1 de 1), pasar a la página 10 de 300 marca el libro como completado. **Arreglo:** el libro se completa cuando su porcentaje leído llega a 100, con la misma regla que `porcentaje_leido`: por páginas si se conoce el total de páginas, por capítulos si no.

### 3. `tzdata` en Windows

Windows no trae base de zonas horarias y `zoneinfo` necesita el paquete `tzdata`, que no está declarado. `zona_valida` cae en una zona por defecto que tampoco puede cargar: `/api/schedule/export/calendar.ics`, el feed y los enlaces de Google Calendar responden 500. El CI corre en Ubuntu y no lo ve. **Arreglo:** declarar `tzdata` y, si aun así una zona no carga, caer en UTC en lugar de fallar.

### 4. Orígenes permitidos atados a tres puertos

`LocalOriginAuthMiddleware` (`src/aulento/web/app.py`) solo acepta los orígenes de los puertos 8000, 8001 y 8080. El navegador manda `Origin` en los POST, PUT y DELETE de la propia página, así que con `aulento web --port 9000` todo guardado responde 403. **Arreglo:** aceptar además el propio origen del pedido (esquema + `Host`); `TrustedHostMiddleware` sigue frenando los `Host` ajenos.

### 5. Orden de prioridad de cursos

`ORDER BY c.prioridad` ordena el texto: alta, baja, media. **Arreglo:** ordenar alta → media → baja.

### 6. El día de la cuenta en UTC

Las fechas se guardan en UTC y se agrupan contra `date.today()` o contra la medianoche UTC (`src/aulento/core/activity_tracker.py`, `src/aulento/db/focus_repository.py`). En Argentina, lo estudiado después de las 21 h cae en el día siguiente y «minutos de hoy» vuelve a cero a las 21 h. **Arreglo:** contar los días en la zona de la cuenta: el ajuste `zona_horaria` si está fijado y, si no, la zona de la máquina, que es la que ya usan el planificador y el MCP.

### 7. Webhook de libros por título parcial

`find_by_title` cae en un `LIKE %título%`: el webhook de Atajos con «Python» actualiza «Fluent Python» y le pisa el total de páginas. Además, un `ValueError` de validación no se captura y responde 500. **Arreglo:** coincidencia exacta; si no hay, una parcial solo si es única; si hay varias, 409 con los candidatos. Errores de validación, 400.

### 8. Páginas leídas por día

El mapa de calor suma `pagina_actual` de los libros actualizados ese día: un libro en la página 300 cuenta 300 páginas ese día, y el puntaje del día se infla. No existe un historial de avance. **Arreglo:** registrar cada avance de páginas (tabla `avances_de_lectura`) y sumar esos avances por día. Los días anteriores al arreglo no tienen historial y quedan en 0.

### 9. Texto del atajo de Libros en modo local

`src/aulento/web/static/index.html` dice que el atajo funciona en modo local «si abriste la app a la red». En modo local la CLI se niega a escuchar fuera de la máquina y el middleware responde 403 a cualquier otro equipo. **Arreglo:** decir que en modo local el atajo no llega a la PC y que funciona con la versión en la nube.

### 10. Campos ignorados

- `estado` de `POST /api/hub/courses/{id}/progress` se acepta y no se usa.
- `autor` del alta de libros se pide en la interfaz y se descarta: no hay columna.
- `elapsed_days` y `scheduled_days` del log FSRS siempre valen 0: la versión 6 de py-fsrs ya no los trae en `ReviewLog`.

**Arreglo:** usar `estado`, guardar `autor` (columna, modelo, alta, edición y tarjeta) y calcular los dos valores del log.

### 11. Conexiones heterogéneas

`RoadmapRepository` acepta `conn` pero casi todos sus métodos abren una conexión nueva y corren `create_schema` (`src/aulento/db/roadmap_repository.py`). El mismo patrón está en `MacroFSRSRepository`, `ActivityTracker` y los almacenes. Una operación que toca varios repositorios no es atómica, y quien pasa una conexión puede terminar escribiendo en otra base.

### 12. Migraciones desde varios lugares

`create_app()` ya migra al construir el servidor MCP, antes del arranque formal; en ese camino un fallo se registra y se sigue (`src/aulento/mcp/server.py`), mientras que el arranque de la web lo trata como fatal. `aulento web openapi` crea y migra `~/.aulento` como efecto secundario.

### 13. `AULENTO_EXTENSIONS`

`aulento mcp serve` carga las extensiones de la variable; `aulento web` no (solo con la opción oculta `--app`).

### 14. Revocaciones sin confirmar

`revocar_todos_los_tokens_mcp` (`src/aulento/auth/servicio.py`) y `tokens_de_alcance.revocar_todos` no confirman su transacción, aunque el módulo dice que cada función confirma la suya. Hoy no las llama el core; una extensión que confíe en el docstring pierde la revocación.

### Menores

- **M1.** `pyproject.toml` declara `fsrs>=3.0.0`, pero el código usa `Scheduler`, que esa versión no tiene. `requirements.txt` fija 6.3.2, que implementa FSRS-6; el README dice FSRS v5.
- **M2.** El docstring de `src/aulento/web/routes/books.py` está después de los imports y no funciona como docstring.
- **M3.** `start.sh` y `start.bat` hablan de un «código del primer administrador» que el modo local no tiene.
- **M4.** `src/aulento/web/app.py` repite «0.1.0» en lugar de usar `aulento.__version__`.
- **M5.** `pyproject.toml` no empaqueta `docs/`: instalado sin `-e`, `/api/docs/manual` muestra «Documentación en preparación».
- **M6.** Las plataformas semilla son «las 5 reales del usuario», la zona por defecto es Buenos Aires y el contenedor de Docker se sigue llamando `study-engine-postgres`.
- **M7.** El calendario usa `zona_horaria` o Buenos Aires; el resto de la app, la zona de la máquina. No hay ruta ni pantalla para fijar `zona_horaria`.
- **M8.** `study_update_book_progress` (MCP) y el copiloto siguen usando `find_by_title` con coincidencia parcial.
- **M9.** `ActivityTracker` convierte cada marca de tiempo con `datetime.fromisoformat` (`src/aulento/core/zona_horaria.py`). Una fila con una fecha que no se puede leer hace fallar todo el mapa de calor, cuando antes la agrupación por texto la toleraba. Conviene saltear la fila y anotarla en el log.
- **M10.** Sin el ajuste `zona_horaria`, `zona_de_la_cuenta` usa `datetime.now().astimezone().tzinfo`, que es un desfase fijo. En zonas con horario de verano, la actividad histórica cercana a un cambio de hora puede caer en el día vecino. Resolverlo bien requiere el nombre IANA de la zona de la máquina.
- **M11.** La revisión con Gemini 4 Hydrogen de la fase 2 se detuvo porque el sistema se quedó sin memoria; se revisó a mano (de ahí salen M9 y M10). Para repetirla, se le pide a Hydrogen que revise el diff de los archivos de la fase contra `odd/revision-arquitectura/fase2.md`.
