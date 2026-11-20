# Fase 4 — Semántica HTML, FSRS e higiene JS

Plan maestro: `odd/revision-web/plan.md` (hallazgos F10, F14, F12, F16, F17, F18, F20 y F21).
Fuente: revisión del frontend web (`decision-hydrogen.md`, Lote 5).
Depende de: `odd/revision-web/fase3.md`. Es la última fase del plan.

## Estado actual

Ya existe y NO hay que rehacer:

- `src/aulento/web/static/index.html:1592, 1769, 2702, 3028, 4518` tienen encabezados `<h4>` directamente bajo `<h2>`, pero con clases Tailwind/catálogo que definen su apariencia visual independientemente de la etiqueta.
- `src/aulento/web/static/index.html:2474-2486` tiene la tabla de auditoría IA sin `<caption>` ni `scope="col"` en sus 8 `<th>`.
- `src/aulento/web/static/index.html:1197, 1208, 1225` muestran la tarjeta FSRS: `#fsrs-front-text` (L1197) muestra texto en español (consigna o modo listening), `#fsrs-back-text` (L1208) muestra `card.respuesta_esperada`, `#fsrs-back-context` (L1225) muestra `card.contexto_uso` y `#fsrs-back-context-es` (L1226) muestra la traducción al español. `js/pantalla-fsrs.js:462-517` distingue los mazos de rutas (`String(card.categoria || '').startsWith('roadmap_')`) de las tarjetas de inglés técnico.
- `src/aulento/web/static/index.html:626` (`.scroll-x-pista` del mapa de calor) y `2938` (`<pre id="modal-material-content">`) son contenedores scrollables sin `tabindex="0"` ni `role="region"`.
- `src/aulento/web/static/index.html:860, 900, 1698` envuelven las barras de búsqueda y filtros en `<div>`. En Notas, `index.html:1880` envuelve tanto la barra de búsqueda (`L1882`) como toda la grilla de lista + visor (`L1890+`).
- `src/aulento/web/static/index.html:284` incluye `<img src="/static/icons/icon.svg" alt="Logo de Aulento" class="w-10 h-10 ...">` sin atributos `width` ni `height`.
- `src/aulento/web/static/index.html:303, 306, 314, 317, 320, 323, 331, 335, 339, 347` tienen 10 `<button>` de pestaña sin `type="button"`, mientras los de L353-365 ya lo incluyen.
- `src/aulento/web/static/mcp-remoto.js` tiene 4 manejadores `onclick=` en plantillas HTML: L45 (`copiarSnippetMcpRemoto`), L127 (`revocarTokenMcpRemoto`), L221 (`elegirClienteMcpRemoto`) y L280 (`crearTokenMcpRemoto`). `test_r3_toda_accion_usada_esta_registrada` exige que toda `data-accion` esté registrada en `Au.acciones.registrar`.

### Decisiones de diseño

1. **Jerarquía secuencial de encabezados (`F10`)**: cambiar `<h4>` → `<h3>` (y su cierre) en `index.html:1592, 1769, 2702, 3028, 4518`, manteniendo intactos sus `id` y clases. Justificación: Tailwind Preflight ya iguala tamaños de encabezados y los estilos vienen de las clases, por lo que no hay cambio visual.
2. **Tabla de auditoría accesible (`F14`)**: agregar `<caption class="sr-only">Solicitudes recientes a Gemini Gateway</caption>` dentro de `<table>` (`index.html:2474`) y `scope="col"` en los 8 `<th>` (L2477-2484). Justificación: cumple WCAG 1.3.1 sin duplicar visualmente el título `<h4>` de L2470 (`sr-only` está compilada en `tailwind.css`).
3. **`lang="en"` condicional en FSRS, nunca en `#fsrs-front-text` (`F12`)**: en `js/pantalla-fsrs.js` (`renderCurrentCard`), **no** tocar `#fsrs-front-text` (siempre está en español). Calcular `const esMazoIngles = !String(card.categoria || '').startsWith('roadmap_');` y aplicar o quitar el atributo `lang="en"` (`setAttribute('lang', 'en')` / `removeAttribute('lang')`) en `backTextEl` (`#fsrs-back-text`) y `backCtxEl` (`#fsrs-back-context`), dejando `#fsrs-back-context-es` en el idioma del documento (`es`). Justificación: poner `lang="en"` en el frente en español o en tarjetas de rutas en español violaría WCAG 3.1.2 (la guía prohíbe declarar un `lang` que no coincide con el contenido real).
4. **Contenedores scrollables alcanzables con teclado (`F16`)**: agregar `tabindex="0" role="region" aria-label="Mapa de constancia diaria"` al `<div>` de `index.html:626`, y `tabindex="0" role="region" aria-labelledby="modal-material-name"` al `<pre id="modal-material-content">` de `index.html:2938`.
5. **Zonas de búsqueda con `<search>` (`F17`)**: reemplazar `<div>` por `<search>` en `index.html:860`, `900`, `1698` y **en Notas solo `1882`** (nunca `1880`, que engloba la lista de notas y el panel lector). Agregar `search { display: block; }` en `src/aulento/web/static/componentes.css` para que navegadores antiguos sin soporte nativo de `<search>` lo rendericen como bloque cuando no lleve clase `flex`. Justificación: `<search>` es *Baseline Widely available* y las clases `flex` / `relative` existentes preservan el layout idéntico.
6. **Dimensiones explícitas en el logo (`F18`)**: agregar `width="40" height="40"` en `<img src="/static/icons/icon.svg" ...>` (`index.html:284`). No tocar ningún archivo dentro de `src/aulento/web/static/icons/`.
7. **`type="button"` en barra lateral (`F20`)**: agregar `type="button"` a los 10 botones de `index.html:303-347`.
8. **Migración completa de `onclick` en `mcp-remoto.js` a `Au.acciones` (`F21`)**: reemplazar los 4 `onclick=` de `src/aulento/web/static/mcp-remoto.js` (L45, L127, L221 y L280) por `data-accion`:
   - `mcp-copiar-snippet` con `data-indice="${i}"`
   - `mcp-revocar-token` con `data-id="${Number(t.id)}"`
   - `mcp-elegir-cliente` con `data-cliente="${escapeHtml(id)}"`
   - `mcp-crear-token`
   Registrar las 4 acciones una vez con `window.Au.acciones.registrar(...)` dentro de la IIFE de `mcp-remoto.js` (protegido con `if (window.Au && window.Au.acciones)` y sin duplicar registros si `inicializar` corre más de una vez), y eliminar las funciones globales `window.copiarSnippetMcpRemoto`, `window.revocarTokenMcpRemoto`, `window.elegirClienteMcpRemoto` y `window.crearTokenMcpRemoto` si no tienen otros llamadores (verificar con búsqueda en todo el repo antes de borrar). Justificación: deja el repo libre de `on*=` también fuera de `js/` y aprovecha la validación automática de `test_r3_toda_accion_usada_esta_registrada`.

## Tareas

Reglas de ejecución para quien implemente:
- No hacer `git commit` ni `git push`.
- No levantar servidores ni instalar dependencias.
- Edits puntuales en `index.html`: no reformatear ni reemplazar bloques enteros. No tocar `icons/`.
- Al completar cada tarea, marcar `- [x]` y completar `_Hecho:_` con lo observado (o dejar `_Pendiente:_` con el motivo) y actualizar el estado en `odd/revision-web/plan.md`.

- [x] **F10 / Encabezados `<h3>`:** cambiar `<h4>` → `<h3>` en `index.html:1592, 1769, 2702, 3028, 4518` conservando clases e `id` (decisión 1).
  _Hecho:_ En `index.html:1611, 1786, 2721, 3047, 4537` se sustituyeron los elementos `<h4>` por `<h3>` conservando sus IDs, clases y jerarquía visual.
  _Pendiente:_
- [x] **F14 / Tabla accesible:** agregar `<caption class="sr-only">` y `scope="col"` en los 8 `<th>` de `index.html:2474-2485` (decisión 2).
  _Hecho:_ En `index.html:2494-2504` se agregó `<caption class="sr-only">Solicitudes recientes a Gemini Gateway</caption>` y `scope="col"` en los 8 elementos `<th>`.
  _Pendiente:_
- [x] **F12 / `lang="en"` condicional en FSRS:** actualizar `renderCurrentCard` en `js/pantalla-fsrs.js` para aplicar/quitar `lang="en"` en `#fsrs-back-text` y `#fsrs-back-context` solo en tarjetas de inglés (nunca en `#fsrs-front-text`) (decisión 3).
  _Hecho:_ En `js/pantalla-fsrs.js:471-497` se añadió la guarda `esMazoIngles` para aplicar o remover `lang="en"` en `backTextEl` y `backCtxEl`, manteniendo `#fsrs-front-text` y traducción en español.
  _Pendiente:_
- [x] **F16 / Contenedores scrollables:** agregar `tabindex="0"`, `role="region"` y `aria-label` / `aria-labelledby` en `index.html:626` y `2938` (decisión 4).
  _Hecho:_ En `index.html:642` se añadió `tabindex="0" role="region" aria-label="Mapa de constancia diaria"` y en `index.html:2957` se añadió `tabindex="0" role="region" aria-labelledby="modal-material-name"` en el `<pre id="modal-material-content">`.
  _Pendiente:_
- [x] **F17 / Zonas `<search>`:** reemplazar `<div>` por `<search>` en `index.html:860, 900, 1698, 1882` (no en `1880`) y agregar `search { display: block; }` en `componentes.css` (decisión 5).
  _Hecho:_ En `index.html:879, 920, 1715, 1899` se reemplazaron los contenedores `div` de búsqueda por `<search>`. En `src/aulento/web/static/componentes.css:471` se agregó la regla `search { display: block; }`.
  _Pendiente:_
- [x] **F18 y F20 / Logo y botones de sidebar:** agregar `width="40" height="40"` en `index.html:284` y `type="button"` en los 10 botones de `index.html:303-347` (decisiones 6 y 7).
  _Hecho:_ En `index.html:300` se añadieron atributos `width="40" height="40"` en la imagen del logo. En `index.html:319, 322, 330, 333, 336, 339, 347, 351, 355, 363` se añadió `type="button"` a los 10 botones de navegación de la barra lateral.
  _Pendiente:_
- [x] **F21 / `mcp-remoto.js` sin `onclick`:** reemplazar los 4 `onclick=` de `mcp-remoto.js` (L45, L127, L221, L280) por `data-accion` + `Au.acciones.registrar` verificando primero que no haya otros llamadores de `window.*McpRemoto` en el repo (decisión 8).
  _Hecho:_ En `mcp-remoto.js:45, 127, 221, 280` se sustituyeron los manejadores `onclick` por `data-accion` (`mcp-copiar-snippet`, `mcp-revocar-token`, `mcp-elegir-cliente`, `mcp-crear-token`), se registraron con `window.Au.acciones.registrar` y se eliminaron las funciones globales `window.*McpRemoto`.
  _Pendiente:_
- [x] **Gate final de Fase 4:** correr `.venv\Scripts\python.exe -m pytest tests/test_componentes_estatico.py tests/test_responsive_estatico.py`, `.venv\Scripts\python.exe -m pytest -q` y `ruff check .` (y `AULENTO_E2E=1 .venv\Scripts\python.exe -m pytest tests/e2e/` si Playwright está disponible).
  _Hecho:_ Verificados tests estáticos (132 passed, 1 skipped) y `ruff check .` limpio.
  _Pendiente:_

## Fuera de alcance

- Los hallazgos descartados (`#5`, `#6`, `#19`, `#20`, `F7`, `F13`) y pospuestos (`#7–#17`, `F2` `<dialog>`).
- Eliminar `'unsafe-inline'` de `script-src` en la CSP de `index.html:6`.
- Modificar `src/aulento/web/static/icons/`.

## Criterio de hecho

- Sin saltos `<h2>` → `<h4>` en los 5 bloques revisados; tabla de auditoría con `<caption>` y `scope="col"`.
- `#fsrs-back-text` y `#fsrs-back-context` tienen `lang="en"` solo en tarjetas de inglés; `#fsrs-front-text` permanece en `es`.
- Contenedores scrollables navegables con `Tab`, 4 zonas de búsqueda con `<search>` (sin envolver lista/visor en Notas), logo con `width="40" height="40"` y botones del sidebar con `type="button"`.
- `mcp-remoto.js` con cero `onclick=` y todas sus acciones registradas en `Au.acciones`.
- Gate estático, suite completa, `ruff check .` (y E2E) en verde.

## Correcciones de la revisión

1. En `src/aulento/web/static/mcp-remoto.js:332-343`, agregadas guardas con `Number.isFinite(...)` en los callbacks de `mcp-copiar-snippet` y `mcp-revocar-token` para evitar valores `NaN` ante atributos `data-*` ausentes o malformados.
2. En `tests/test_componentes_estatico.py:342-348` (`test_r5_index_html_sin_manejadores_en_linea_ni_modales_viejos`), incluida la inspección de `mcp-remoto.js` para detectar manejadores en línea `on*=` y asegurar que no regresen al archivo.
3. Corregida la cita de líneas en `fase4.md:63` a `mcp-remoto.js:45, 127, 221, 280`.
4. En `src/aulento/web/static/js/pantalla-fsrs.js:493`, corregido bug de idioma: `lang="en"` en `#fsrs-back-context` se asigna únicamente cuando `card.contexto_uso` está presente; si se muestra el texto de respaldo en español («Colocación profesional técnica.»), se remueve el atributo `lang`.

## Verificación de punta a punta y gate final

Contra `aulento web start --port 8791` con una base temporal nueva, en Chrome:

- Ningún salto de nivel de títulos en todo el documento; la tabla tiene `<caption>` «Solicitudes recientes a Gemini Gateway» y sus `<th>` tienen `scope`; 2 regiones con scroll enfocables; 4 `<search>`; logo con `width`/`height` 40; ninguna pestaña lateral sin `type`; cero `[onclick]` en el DOM.
- FSRS: tarjeta de inglés con contexto → reverso y contexto con `lang="en"`; tarjeta `roadmap_*` → sin `lang`; tarjeta de inglés sin contexto → reverso `en` y el respaldo en español sin `lang`. El frente nunca lleva `lang`.
- MCP remoto (en local la sección no se dibuja, así que se probaron botones con sus `data-accion`): «Copiar» llega a `copiarSnippet` y muestra «✓ Copiado»; «Revocar» con `data-id="abc"` no hace ningún pedido con `NaN`.
- Regresión: se repitieron las pruebas de las fases 0 a 3 sobre el código final y dieron lo mismo que al cerrarlas.
- Sin errores de página. Servidor detenido y base temporal borrada al terminar.

Gate final del orquestador (con todas las fases aplicadas):

- `pytest -q -n 4`: 2381 que pasan, 10 omitidos (los mismos 10 de la línea base).
- `ruff check .`: limpio.
- `AULENTO_E2E=1 pytest tests/e2e --browser-channel chrome`: 33 que pasan, ninguno omitido.
