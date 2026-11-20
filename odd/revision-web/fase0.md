# Fase 0 — Carga crítica y seguridad

Plan maestro: `odd/revision-web/plan.md` (hallazgos F1, F15, F3 y #4).
Fuente: revisión del frontend web (`decision-hydrogen.md`, Lote 1).
Depende de: nada. Todas las fases siguientes (1 a 4) dependen de esta en serie porque todas editan `src/aulento/web/static/index.html`.

## Estado actual

Ya existe y NO hay que rehacer:

- `src/aulento/web/static/index.html:9-12` carga síncronamente en `<head>` `/static/vendor/mermaid.min.js` (3,34 MB), `/static/vendor/marked.min.js` y `/static/vendor/purify.min.js`, seguido del único `<script>` en línea (L12) con `mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict', maxTextSize: 500000, maxEdges: 5000 })`.
- `src/aulento/web/static/sw.js:10-12` ya precachea los tres archivos de `vendor/` en `STATIC_ASSETS` (`test_el_service_worker_precachea_todo_lo_que_carga_la_pagina`).
- `src/aulento/web/static/js/pantalla-roadmap.js` es el único archivo que usa `mermaid`: en `renderDagDiagram` (L1317-1324) y en `renderLessonMarkdown` (L2216-2226), y ya tiene manejo de error si `window.mermaid` falta o falla.
- `src/aulento/web/static/index.html:5327-5348` incluye 15 `<script src="...">` síncronos en orden (`componentes.js`, `capacidades.js`, `js/00-base.js`, `js/comunes.js`, 10 `js/pantalla-*.js`, `app.js`, `mcp-remoto.js`). `capacidades.js:72-76` lee `document.body.dataset.modo` al cargarse y difiere su fetch a `DOMContentLoaded`; `app.js:2` arranca en `DOMContentLoaded`.
- `src/aulento/web/static/index.html:5352-6066` contiene 11 `.au-modal`, `#toast-container` (L5972) y `#guided-session-hud` (L5975) declarados después de los `<script>`.
- `tests/front.py:19` detecta los scripts con la regex `re.findall(r'<script\s+src="([^"]+)"', html)`.
- `tests/test_capacidades.py:107` aserta literalmente `'<script src="/static/capacidades.js"></script>' in html`.
- `tests/test_web_roadmap_advanced.py:260-270, 537-557` verifica `<script src="/static/vendor/{archivo}"></script>` para los 3 vendor, `"securityLevel: 'strict'" in html`, `"securityLevel" not in js` y la guarda `if (!window.mermaid) {` en `renderDagDiagram`.
- `src/aulento/web/static/js/pantalla-roadmap.js:293, 1012` inserta `${err.message}` sin escapar dentro de `innerHTML`.
- `src/aulento/web/static/js/00-base.js:443-451` escucha `keydown` en `inputEl` de `showSystemPrompt` y dispara `onOk()` cuando `e.key === 'Enter'`.

### Decisiones de diseño

1. **Carga bajo demanda de `mermaid.min.js` (`F1`)**: quitar `<script src="/static/vendor/mermaid.min.js"></script>` y el `<script>` inline (L12) del `<head>` de `index.html`. En `js/pantalla-roadmap.js`, agregar un helper `ensureMermaidLoaded()` con promesa en módulo que:
   - Si `window.mermaid` ya existe, inicializa una sola vez (bandera `mermaidInicializado`) y resuelve `window.mermaid`.
   - Si no existe, reutiliza la promesa en vuelo o crea `<script src="/static/vendor/mermaid.min.js">` apuntando al mismo asset local (con `onerror` que limpie la promesa en vuelo y resuelva `null` sin lanzar, para poder reintentar luego).
   - Al resolver tras `onload`, ejecuta exactamente `window.mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict', maxTextSize: 500000, maxEdges: 5000 })` una sola vez antes del primer uso.
   - Llamar `await ensureMermaidLoaded()` al inicio de `renderDagDiagram` (respetando la guarda `if (seq !== dagRenderSeq) return;` inmediatamente después del `await` y conservando `if (!window.mermaid) { setDagDiagramNotice(...); return; }`) y en `renderLessonMarkdown` cuando `diagrams.length > 0`.
   Justificación: elimina 3,34 MB bloqueantes de la carga inicial de `aulento.com` sin perder soporte offline (el archivo sigue en `STATIC_ASSETS` de `sw.js`).
2. **Alinear tests del visor con Mermaid bajo demanda (`F1`)**: en `tests/test_web_roadmap_advanced.py`:
   - En `test_html_carga_las_librerias_del_visor_desde_la_propia_app`, verificar `marked.min.js` y `purify.min.js` en `index.html` (admitiendo `defer`), verificar que `mermaid.min.js` sigue servido en `/static/vendor/mermaid.min.js` y precacheado en `sw.js` y referenciado por `pantalla-roadmap.js`, y quitar la aserción de `<script>` estático de Mermaid en `index.html` y de `securityLevel` en `html`.
   - En `test_mermaid_sigue_en_modo_estricto_y_sin_callbacks_propios`, verificar `securityLevel: 'strict'` (y ausencia de `'loose'`) en `pantalla-roadmap.js` (dentro de `ensureMermaidLoaded`) en lugar de en `index.html`.
   Justificación: preserva intactas las garantías de seguridad y origen local sin anclar la implementación a un `<script>` bloqueante en `<head>`.
3. **`defer` con `src` primero y nunca `type="module"` (`F1`, `F15`)**: agregar `defer` a `marked.min.js` y `purify.min.js` en `<head>` y a los 15 `<script>` del final del `<body>`, escribiendo **siempre `src="..."` antes de `defer`** (`<script src="/static/..." defer></script>`). Justificación: `tests/front.py:19` exige `src="..."` inmediatamente tras `<script\s+`; `defer` mantiene el orden exacto de ejecución y el ámbito global compartido entre los 15 scripts (cosa que `type="module"` rompería), y como los scripts diferidos corren recién al terminar de parsear todo el documento, los 11 modales de `5352-6066` ya existen en el DOM sin mover ~700 líneas de `index.html`. Actualizar `tests/test_capacidades.py:107` para aceptar `defer` en `capacidades.js`.
4. **Escape de `err.message` (`F3`)**: en `js/pantalla-roadmap.js:293` y `1012`, reemplazar `${err.message}` por `${escapeHtml(err && err.message ? err.message : 'Error inesperado')}`. Justificación: evita interpretación de markup si el error contiene caracteres HTML.
5. **Enter seguro para IME en `#modal-system-prompt` (`#4`)**: en `js/00-base.js:444`, al entrar a `if (e.key === 'Enter')`, retornar inmediatamente si `e.isComposing || e.keyCode === 229` **antes** de `e.preventDefault()` y `onOk()`. Justificación: sigue la Estrategia 1 de `ime-safe-enter-submit` para cubrir tanto Chrome/Firefox como el bug de orden `compositionend`/`keydown` en Safari, sin interceptar la tecla de confirmación del IME.

## Tareas

Reglas de ejecución para quien implemente:
- No hacer `git commit` ni `git push`.
- No levantar servidores ni instalar dependencias.
- Edits puntuales en `index.html`: no reformatear ni reemplazar bloques enteros.
- Al completar cada tarea, marcar `- [x]` y completar `_Hecho:_` con lo observado (o dejar `_Pendiente:_` con el motivo) y actualizar el estado en `odd/revision-web/plan.md`.

- [x] **F1 / `mermaid` bajo demanda:** quitar `<script src="/static/vendor/mermaid.min.js">` y el `<script>` inline (L12) de `index.html`; implementar `ensureMermaidLoaded()` con `initialize` estricto (una sola vez) en `js/pantalla-roadmap.js` y usarlo en `renderDagDiagram` y `renderLessonMarkdown`, manteniendo `mermaid.min.js` en `sw.js` (decisiones 1 y 2).
  _Hecho:_ En `index.html:9-11` se removió la inclusión de `mermaid.min.js` y el script inline con `mermaid.initialize`. En `pantalla-roadmap.js:1307-1346` se implementó `ensureMermaidLoaded()` que inicializa `mermaid` bajo demanda con `securityLevel: 'strict'`, `maxTextSize: 500000`, `maxEdges: 5000`. Se integró con `await ensureMermaidLoaded()` en `renderDagDiagram` (L1349) y en `renderLessonMarkdown` (L2251). `mermaid.min.js` se mantiene en `sw.js:10`.
  _Pendiente:_
- [x] **F1 + F15 / `defer` en `<head>` y bloque final:** agregar `defer` (siempre después de `src="..."`) a `marked.min.js`, `purify.min.js` y los 15 scripts de `index.html:5327-5348` sin mover los modales de `5352-6066`; actualizar aserciones literales de `<script>` en `tests/test_capacidades.py` y `tests/test_web_roadmap_advanced.py` (decisiones 2 y 3).
  _Hecho:_ En `index.html:9-10` se agregó `defer` tras `src` a `marked.min.js` y `purify.min.js`. En `index.html:5325-5346` se agregó `defer` tras `src` a los 15 scripts locales. En `tests/test_capacidades.py:107` se actualizó la aserción para exigir únicamente `defer`. En `tests/test_web_roadmap_advanced.py:260-278, 537-558` se ajustaron los tests para exigir `defer` obligatorio, verificar ausencia de `mermaid.min.js` y script inline en `index.html`, y validar `securityLevel: 'strict'` en `pantalla-roadmap.js`.
  _Pendiente:_
- [x] **F3 / Escape de errores en `pantalla-roadmap.js`:** escapar `err.message` con `escapeHtml(...)` en `js/pantalla-roadmap.js:293` y `1012` (decisión 4).
  _Hecho:_ En `pantalla-roadmap.js:293` y `1012` se reemplazó `${err.message}` por `${escapeHtml(err && err.message ? err.message : 'Error inesperado')}`.
  _Pendiente:_
- [x] **#4 / Guarda IME en `showSystemPrompt`:** agregar `if (e.isComposing || e.keyCode === 229) return;` en `js/00-base.js:444` antes de `e.preventDefault()` y `onOk()` (decisión 5).
  _Hecho:_ En `00-base.js:444` se agregó la guarda `if (e.isComposing || e.keyCode === 229) return;` inmediatamente al detectar `Enter`, antes de `preventDefault()` y `onOk()`.
  _Pendiente:_
- [x] **Gate de Fase 0:** correr `.venv\Scripts\python.exe -m pytest tests/test_componentes_estatico.py`, `.venv\Scripts\python.exe -m pytest -q` y `ruff check .`; verificar todos en verde.
  _Hecho:_ `tests/test_componentes_estatico.py`: 88 passed, 1 skipped. Suite completa `pytest -q -n auto -p no:cacheprovider --ignore=tests/e2e`: 2381 passed, 10 skipped en 188.78s. `ruff check .`: All checks passed!
  _Pendiente:_

## Notas de implementación

- En `pantalla-roadmap.js`, `renderLessonMarkdown` se marcó como `async` para permitir el `await ensureMermaidLoaded()` cuando se detectan bloques con diagramas `mermaid`.
- En `renderDagDiagram`, se añadió una verificación de secuencia `if (seq !== dagRenderSeq) return;` inmediatamente tras `await ensureMermaidLoaded()` para evitar condiciones de carrera si el usuario cambia de nodo mientras el script de Mermaid se está descargando.

## Correcciones de la revisión

A partir de la revisión de Hydrogen (`revision-fase0.md`), se aplicaron 7 ajustes:
1. `tests/test_capacidades.py:107`: se endureció la aserción exigiendo únicamente `<script src="/static/capacidades.js" defer></script>`.
2. `tests/test_web_roadmap_advanced.py:257-278`: se eliminó `LIBRERIAS_DEL_VISOR`, se exigió `defer` obligatorio en `marked.min.js` y `purify.min.js`, y se añadieron aserciones de que `/static/vendor/mermaid.min.js` y `mermaid.initialize` no están en `index.html`.
3. `tests/test_web_roadmap_advanced.py:571`: se fijó la aserción exacta `assert dibujar.count("if (seq !== dagRenderSeq) return;") == 3`.
4. `src/aulento/web/static/js/pantalla-roadmap.js:2260-2273`: en `renderLessonMarkdown`, se filtraron los diagramas desconectados con `const conectados = Array.from(diagrams).filter((el) => el.isConnected);` ejecutando `mermaid.run({ nodes: conectados })` solo si `conectados.length > 0`.
5. `src/aulento/web/static/js/pantalla-roadmap.js:1334-1337`: en `ensureMermaidLoaded()`, en el callback `onload`, se resetea `if (!window.mermaid) mermaidPromise = null;` para permitir reintentos si `window.mermaid` quedara indefinido.
6. `tests/test_web_roadmap_advanced.py:547-550`: se acotó la comprobación de `securityLevel: 'strict'` a la función `inicializarMermaid` (`_funcion_js(js, "inicializarMermaid")`).
7. `odd/revision-web/fase0.md:47, 53`: se corrigieron las referencias de línea de `pantalla-roadmap.js` a 1307-1346 (helper Mermaid) y 293 / 1012 (escape de errores).

## Fuera de alcance

- Cualquier cambio de accesibilidad (foco, labels, `inert`, skip link, toasts), `dvh`, scrollbars, `<progress>`, semántica HTML o `mcp-remoto.js` (fases 1 a 4).
- Convertir los scripts a `type="module"` o reubicar el bloque de modales `5352-6066`.
- Tocar archivos en `src/aulento/web/static/icons/`.

## Criterio de hecho

- `<head>` de `index.html` no contiene scripts bloqueantes ni `<script>` inline; `mermaid.min.js` se carga bajo demanda en `pantalla-roadmap.js` con `securityLevel: 'strict'` y sigue en `sw.js`.
- Los 15 scripts al pie llevan `src="..." defer` (respetando `tests/front.py`) para ejecutarse recién con todo el DOM ya parseado, incluidos los modales finales.
- `err.message` pasa por `escapeHtml` en `pantalla-roadmap.js:293` y `1012`.
- `showSystemPrompt` ignora `Enter` durante composición IME (`isComposing` o `keyCode === 229`).
- `tests/test_componentes_estatico.py`, suite completa (`pytest -q`) y `ruff check .` pasan en verde.

## Verificación de punta a punta

Con `aulento web start --port 8791` y una base temporal (`AULENTO_DB_PATH`), en Google Chrome con Playwright:

- Al cargar: `Au`, `marked`, `DOMPurify` y `SE_CAPACIDADES` (modo `local`) disponibles; `window.mermaid` indefinido y 0 pedidos a `mermaid.min.js`.
- `ensureMermaidLoaded()` dos veces: un solo pedido; `securityLevel: strict`, `maxEdges: 5000`; `mermaid.render` devuelve un SVG.
- Caso de error: con `fetch` rechazando `new Error('<img src=x id=xss-e2e>')`, `loadRoadmapDetails` muestra el texto literal y no crea el `<img>`.
- IME: en `showPromptDialog`, Enter con `isComposing: true` deja el diálogo abierto; Enter normal lo confirma con el valor «こんにちは».
- Consola sin errores.
- Gate propio del orquestador: 2381 tests que pasan, 10 omitidos; `ruff check .` limpio.
