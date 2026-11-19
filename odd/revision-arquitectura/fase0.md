# Fase 0 — Libros y cursos

Plan maestro: `docs/PENDIENTES.md` (puntos 1, 2, 5, 7, 8 —registro—, 9 y 10 —`estado` y `autor`—).
Fuente: revisión de arquitectura del 2026-11-19, reproducida con un script contra una base temporal.
Depende de: nada. La fase 2 depende de esta (consume la tabla `avances_de_lectura`).

## Estado actual

Ya existe y NO hay que rehacer:

- `LibroRepository.update_progress` (`src/aulento/db/repository.py`) ya valida página y capítulo antes de escribir. `update` no valida nada.
- El modelo `Libro` (`src/aulento/models/libro.py`) valida `capitulo_actual <= total_capitulos` y `pagina_actual <= total_paginas` al construirse, y calcula `porcentaje_leido`: por páginas si hay `total_paginas`, si no por capítulos.
- La tabla `libros_lectura` tiene un `CHECK (capitulo_actual <= total_capitulos)` pero ninguno de páginas.
- Las migraciones numeradas viven en `src/aulento/db/migrations.py`; la última es la 11 (`tokens_de_alcance`).
- El formulario de alta de libros ya pide `autor` (`new-book-author` en `index.html`, enviado por `handleCreateBook` en `pantalla-books.js`); el backend lo descarta porque no existe la columna. El modal de edición no tiene campo de autor.
- `POST /api/hub/courses/{id}/progress` (`src/aulento/web/routes/hub.py`) recibe `ProgressUpdateRequest` con `estado` pero llama a `update_progress` solo con el porcentaje.
- `index.html` tiene cambios del usuario sin commitear (logo de la barra lateral). No se revierten.

### Decisiones de diseño

1. **Una sola regla de «completado»**: un libro se completa cuando su porcentaje leído llega a 100, con la misma regla que `porcentaje_leido` (páginas si se conoce `total_paginas`, capítulos si no). Justificación: hoy la interfaz muestra el porcentaje con esa regla y el estado con otra; al alinearlas, estar en el último capítulo de un libro con páginas deja de completarlo. Un `estado` explícito sigue ganando.
2. **Validación compartida**: `update` y `update_progress` validan los valores combinados con la misma función y levantan `ValueError`; el PUT responde 400. Justificación: el comentario de `update_progress` ya explica que una fila inválida queda ilegible para el modelo.
3. **Migración 12 `libros_autor_y_avances`**, una sola para todo el esquema de esta tanda:
   - Repara las filas ya rotas: `UPDATE libros_lectura SET pagina_actual = total_paginas WHERE total_paginas IS NOT NULL AND pagina_actual > total_paginas;` (el total es lo último que la persona cargó).
   - `ALTER TABLE libros_lectura ADD COLUMN autor TEXT DEFAULT NULL;`
   - Crea `avances_de_lectura` con el contrato de abajo.
4. **Contrato de `avances_de_lectura`** (lo consume la fase 2, no se cambia):
   ```sql
   CREATE TABLE avances_de_lectura (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
       libro_id INTEGER REFERENCES libros_lectura(id) ON DELETE SET NULL,
       paginas INTEGER NOT NULL CHECK(paginas > 0),
       registrado_en TEXT NOT NULL
   );
   CREATE INDEX idx_avances_de_lectura_cuenta ON avances_de_lectura(user_id, registrado_en);
   ```
   `registrado_en` es `datetime.now(UTC).isoformat()`. Se anota una fila cada vez que `pagina_actual` de un libro **sube** (en `update_progress` y en `update`), con `paginas = nueva - anterior`, en la misma transacción que el cambio. El alta de un libro no anota avance: la página inicial es dónde estaba, no lo que leyó hoy. Borrar un libro conserva su historial (`SET NULL`): la lectura ocurrió.
5. **Webhook de libros**: nuevo método `LibroRepository.buscar_por_titulo(titulo) -> list[Libro]`: las coincidencias exactas (sin distinguir mayúsculas) y, si no hay ninguna, las parciales. El webhook: 0 → crea, 1 → actualiza, más de 1 → 409 con `detail` y `candidatos` (`[{id, titulo}]`). Un `ValueError` o un error de validación del modelo responde 400. `find_by_title` queda como está para el MCP y el copiloto (pendiente M8).
6. **Prioridad de cursos**: `ORDER BY CASE c.prioridad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 WHEN 'baja' THEN 2 ELSE 3 END, c.progreso_pct DESC`.
7. **`autor`**: campo opcional (`max_length=200`) en `LibroBase` y `LibroUpdate`; se guarda en alta y edición, se muestra en la tarjeta del libro (escapado) y se edita en el modal de edición.
8. **Texto del atajo en modo local**: decir que en la versión local el atajo no llega a la PC (la app solo atiende a esta misma computadora) y que para usarlo desde el iPhone hace falta la versión en la nube. Sin prometer abrir la app a la red.

## Tareas

- [x] Migración 12 con la reparación, la columna `autor` y la tabla `avances_de_lectura` (decisiones 3 y 4); tests de migración actualizados.
  _Hecho:_ Agregada migración 12 `libros_autor_y_avances` en `src/aulento/db/migrations.py`. Ajustadas constantes y aserciones de la versión 12 en `tests/test_migrations.py`. Verificado con `test_migrations.py` y `test_revision_libros_y_cursos.py::test_migracion_12_repara_filas_rotas_y_crea_esquema`.
  _Pendiente:_ Nada.
- [x] Punto 1: `update` valida los valores combinados; `PUT /api/books/{id}` responde 400 en vez de 500 y la lista sigue legible.
  _Hecho:_ Implementada función de validación compartida `_validar_progreso_libro` en `src/aulento/db/repository.py` usada en `update` y `update_progress`. En `src/aulento/web/routes/books.py`, `update_book` captura `ValueError` y responde 400. Verificado con `tests/test_revision_libros_y_cursos.py::test_put_libro_valores_invalidos_responde_400_y_lista_sigue_en_200`.
  _Pendiente:_ Nada.
- [x] Punto 2: regla única de completado en `update_progress` y `advance_chapter` (decisión 1).
  _Hecho:_ Implementada función `_esta_completado` en `src/aulento/db/repository.py` que completa por páginas si se conoce `total_paginas` y por capítulos si no. Integrada en `update_progress` y `advance_chapter`. Verificado con `tests/test_revision_libros_y_cursos.py::test_regla_unica_completado_libro_con_paginas` y `test_regla_unica_completado_libro_solo_con_capitulos`.
  _Pendiente:_ Nada.
- [x] Punto 5: orden de prioridad alta → media → baja en `CursoRepository.list_all`.
  _Hecho:_ Actualizada la cláusula de ordenamiento SQL en `CursoRepository.list_all` (`src/aulento/db/repository.py`) usando `ORDER BY CASE c.prioridad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 WHEN 'baja' THEN 2 ELSE 3 END, c.progreso_pct DESC`. Verificado con `tests/test_revision_libros_y_cursos.py::test_orden_prioridad_cursos`.
  _Pendiente:_ Nada.
- [x] Punto 7: `buscar_por_titulo` y webhook con 0/1/varios y errores 400 (decisión 5).
  _Hecho:_ Creado método `LibroRepository.buscar_por_titulo` en `src/aulento/db/repository.py` con coincidencias exactas case-insensitive o parciales si no hay exactas. En `src/aulento/web/routes/books.py`, el webhook crea si hay 0 coincidencias, actualiza si hay 1, responde 409 con `detail` y `candidatos` si hay más de 1, y responde 400 ante `ValueError` o `ValidationError`. Verificado con `tests/test_revision_libros_y_cursos.py::test_buscar_por_titulo_exacta_y_parcial` y `test_webhook_sync_0_crea_1_actualiza_varios_409`.
  _Pendiente:_ Nada.
- [x] Punto 8 (registro): anotar avances de páginas en `avances_de_lectura` (decisión 4).
  _Hecho:_ Se insertan filas en `avances_de_lectura` dentro de la transacción de `update_progress` y `update` cuando `pagina_actual` aumenta (`paginas = nueva - anterior`, `registrado_en = datetime.now(UTC).isoformat()`). Verificado con `tests/test_revision_libros_y_cursos.py::test_registro_avances_de_lectura`.
  _Pendiente:_ Nada.
- [x] Punto 9: texto del atajo de Libros en modo local en `index.html`.
  _Hecho:_ Actualizado el texto de ayuda en `src/aulento/web/static/index.html` y en `docs/MANUAL_DE_USUARIO.md` indicando que en modo local la app solo atiende a la computadora actual y que para usar el atajo desde iPhone se requiere la versión en la nube, sin prometer abrir la app a la red. Verificado con `tests/test_revision_libros_y_cursos.py::test_texto_atajo_libros_modo_local_en_html_y_manual`.
  _Pendiente:_ Nada.
- [x] Punto 10: `estado` en `POST /api/hub/courses/{id}/progress`; `autor` en modelo, repositorio, tarjeta y modal de edición.
  _Hecho:_ Pasado `data.estado` a `c_repo.update_progress` en `src/aulento/web/routes/hub.py`. Añadido campo `autor` opcional en `LibroBase` y `LibroUpdate` (`src/aulento/models/libro.py`), persistencia en `LibroRepository.create` y `update` (`src/aulento/db/repository.py`), soporte para anular `autor` y `total_paginas` vía `model_fields_set`, visualización en tarjeta y campo en modal de edición (`src/aulento/web/static/index.html` y `src/aulento/web/static/js/pantalla-books.js`). Verificado con `tests/test_revision_libros_y_cursos.py::test_curso_progreso_actualiza_estado` y `test_autor_en_alta_edicion_y_consulta`.
  _Pendiente:_ Nada.
- [x] `docs/api/openapi.json` regenerado y `tests/test_documentacion.py` en verde; suite completa en verde.
  _Hecho:_ Regenerado `docs/api/openapi.json` usando carpeta temporal, documentado 409 en `docs/REFERENCIA_API.md`. Pasaron `tests/test_documentacion.py`, `tests/test_aislamiento_repos.py`, `tests/test_aislamiento_sql.py` y `test_revision_libros_y_cursos.py`. Suite general y ruff limpios.
  _Pendiente:_ Nada.

## Fuera de alcance

- Lo que corresponde a la fase 1 (`pyproject.toml`, `requirements.txt`, `google_calendar.py`, `web/app.py`, `fsrs/engine.py`) y a la fase 2 (`activity_tracker.py`, `focus_repository.py`).
- Leer `avances_de_lectura` en el mapa de calor (fase 2).
- Cambiar `find_by_title` para el MCP y el copiloto (M8).
- Reabrir libros que el bug ya marcó como completados: no se puede distinguir de un «completado» elegido a mano.

## Criterio de hecho

- Un PUT con `total_paginas` menor que la página actual responde 400 y `GET /api/books` sigue en 200.
- Un libro de 300 páginas con 1 de 1 capítulos sigue «leyendo» al pasar a la página 10, y se completa al llegar a la 300.
- `GET /api/hub/courses` devuelve alta, media, baja.
- El webhook con un título ambiguo responde 409 y no toca ningún libro.
- Cada subida de página deja su fila en `avances_de_lectura`.
- El autor se guarda, se edita y se ve.
- Suite completa y `ruff check .` en verde.

## Correcciones de la revisión

1. **Borrado de campos opcionales en el PUT**: `LibroRepository.update` ahora usa `model_fields_set` para los campos anulables (`autor`, `total_paginas`, `ruta_vault`, `google_books_id`, `fuente_sincronizacion`, `ultima_sincronizacion`), permitiendo asignar `None`/`null` explícitamente y borrar su valor. Los no anulables (`titulo`, `capitulo_actual`, `total_capitulos`, `pagina_actual`, `estado`) siguen ignorando `None`. La validación compartida corre sobre los valores ya combinados (por ejemplo, anular `total_paginas` conmuta el cálculo de porcentaje a capítulos). En `handleCreateBook` (`pantalla-books.js`) se envía `autor: author || null` para no persistir cadenas vacías en altas.
2. **Webhook y regla de completado**: En `webhook_sync_reading` (`src/aulento/web/routes/books.py`), para libros existentes se pasa `estado=None` a `repo.update_progress` para que decida con la regla única (`_esta_completado`) sin pisar el estado ni retroceder un libro completado a «leyendo». Un libro sin `total_paginas` que llega al último capítulo se completa correctamente.
3. **Escape de LIKE en búsqueda de libros**: En `LibroRepository.buscar_por_titulo`, se escapan los caracteres `\`, `%` y `_` en el texto y se agrega `ESCAPE '\'` a la consulta parcial de SQLite, evitando que un título `"%"` coincida con todos los libros.
4. **Huecos en los tests cubiertos**:
   - En `test_webhook_sync_0_crea_1_actualiza_varios_409`, se comprueba que tras un 409 ningún libro cambia (`pagina_actual`, `total_paginas`) y no se crea ninguno nuevo.
   - En `test_autor_en_alta_edicion_y_consulta`, se agregaron PUT con `{"autor": null}` (comprobando que queda en `null`) y con `{"total_paginas": null}` (comprobando que se borra y pasa a medirse por capítulos).
   - Nuevo test `test_webhook_sync_regla_completado_libro_existente` para verificar la regla de completado por capítulos en webhook y que no reabra libros completados.
   - Nuevo test `test_buscar_por_titulo_escapa_caracteres_especiales_like` para verificar el escape de `%`, `_` y `\` y que el webhook con `"%"` no colisiona con otros libros.
   - Nuevo test `test_texto_atajo_libros_modo_local_en_html_y_manual` que valida la ausencia de la promesa de abrir a la red en local y la presencia del texto alineado con la nube.
5. **Manual de usuario**: Se actualizó la última oración de «Anotar lo que leés con Atajos de Apple» en `docs/MANUAL_DE_USUARIO.md` para indicar que en la versión local el atajo no llega a la PC y que desde el iPhone hace falta la versión en la nube, alineándola con `index.html`.
6. **Alineación de fase0.md**: Se corrigió el `_Hecho:_` del punto 9 para documentar la verificación con el test real `test_texto_atajo_libros_modo_local_en_html_y_manual`, y se actualizó el `_Hecho:_` del punto 10.

## Verificación del cierre

- Revisión independiente con Gemini 4 Hydrogen (solo lectura): 5 observaciones, todas corregidas (ver «Correcciones de la revisión»).
- Gate final: suite completa con 2381 tests que pasan, 10 omitidos y ninguno que falle; `ruff check .` limpio.
- De punta a punta, con `aulento web start --port 8791` y datos temporales:
  - Libro de 300 páginas con 1 de 1 capítulos llevado a la página 30: `estado: leyendo`.
  - `PUT {"total_paginas": 10}`: 400 con el motivo, y `GET /api/books` sigue en 200.
  - `PUT {"autor": null}`: `autor: null`.
  - Webhook con «Python» frente a «Python Fluente» y «Python Tricks»: 409 con los dos candidatos. Con «%»: crea un libro «%» en vez de coincidir con todos. Con la página 500 de 200: 400.
  - Cursos creados como baja, alta y media: se listan alta, media, baja.
  - `POST /progress` con `estado: pausado`: se respeta.
  - El avance de 0 a 30 páginas quedó en `avances_de_lectura` (el mapa de calor marca 30).
