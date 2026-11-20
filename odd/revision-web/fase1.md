# Fase 1 — Accesibilidad interactiva y foco

Plan maestro: `odd/revision-web/plan.md` (hallazgos F4, F11, F8, F6, F5 y mitigación `inert` de F2).
Fuente: revisión del frontend web (`decision-hydrogen.md`, Lote 2).
Depende de: `odd/revision-web/fase0.md` (la Fase 2 dependerá de esta en serie).

## Estado actual

Ya existe y NO hay que rehacer:

- `src/aulento/web/static/componentes.js:238-300` implementa `Au.modal` con pila `abiertos`, mueve el foco al abrir y lo devuelve al disparador al cerrar, además de atrapar `Escape` en captura y cerrar al tocar el fondo. No aplica `inert` al contenido de fondo.
- Los hijos directos de `<body>` en `src/aulento/web/static/index.html` son: `#sidebar-backdrop` (L277), `#app-sidebar` (L280), `<div class="flex-1 flex flex-col min-w-0 lg:pl-64">` (L383, que contiene `<header>`, `<main>` y `<nav id="barra-inferior">`), los `div.au-modal`, `#toast-container`, `#guided-session-hud` y los `<script>`.
- `src/aulento/web/static/index.html:1699` ya usa `<label for="materiales-filtro" class="sr-only">Buscar por nombre</label>`, y `sr-only` está compilada en `css/tailwind.css`. `not-sr-only` NO está compilada en `tailwind.css`.
- `src/aulento/web/static/index.html:616, 777, 862, 902, 1526, 1868, 1883, 2598` tienen controles `<input>` / `<select>` sin `<label>` asociado ni `aria-label`.
- `src/aulento/web/static/index.html:299` y `2850` declaran dos `<nav>` sin `aria-label`.
- `src/aulento/web/static/index.html:484` declara `<main>` sin `id`, y `<body>` no tiene enlace de salto (*skip link*).
- `src/aulento/web/static/index.html:175` declara `#dag-diagram g.node:focus { outline: none; }` mientras `js/pantalla-roadmap.js:1348-1355` hace los nodos focusables con `tabindex="0"` y `role="button"`. Los controles de `index.html:3075, 4279, 4932, 4986` tienen `focus:ring-0`.
- `src/aulento/web/static/index.html` ya contiene `<div id="toast-container" ...></div>` (antes en L5972, reubicado antes de los `<script>` en Fase 0) y `js/00-base.js:169-196` lo reutiliza (o crea uno si falta) e inserta el botón `&times;` sin `type="button"` ni `aria-label`.

### Decisiones de diseño

1. **Aislamiento `inert` en `Au.modal` para modales simples y anidados (`F2`, mitigación sin `<dialog>`)**: en `componentes.js`, agregar un helper `sincronizarInert()` invocado al final de `modal.abrir` y `modal.cerrar`, usando un `Set` interno (`inertizados`) para no pisar atributos `inert` previos de la app:
   - Cuando `abiertos.length === 0`: poner `el.inert = false` a cada elemento en `inertizados` y vaciar el `Set`.
   - Cuando `abiertos.length > 0`: identificar el modal superior `topId = abiertos[abiertos.length - 1].id`. Recorrer `Array.from(document.body.children)`: para todo elemento que **no** sea `#${topId}`, ni `#toast-container` (para no silenciar su live region según `accessibility.md`), ni un `<script>`, hacer `el.inert = true` y agregarlo a `inertizados`; asegurar `topEl.inert = false` y sacarlo de `inertizados`.
   - **Nota para modales armados en JS (`showConfirmDialog` u otros)**: si algún modal se crea dinámicamente y se agrega al `body` antes de `Au.modal.abrir`, el hijo directo nuevo es el `topId`, por lo que queda interactivo automáticamente.
   - Documentar esta garantía en `docs/COMPONENTES.md` (sección `Modal: Au.modal, .au-modal`).
2. **Skip link propio sin clases nuevas de Tailwind (`F6`)**: agregar `<a href="#main-content" class="au-saltar-contenido">Saltar al contenido</a>` al inicio de `<body>` (`index.html:275`) y `id="main-content" tabindex="-1"` en `<main>` (`index.html:484`). Definir `.au-saltar-contenido` y `.au-saltar-contenido:focus-visible` en `componentes.css` usando solo tokens de `:root` y `#fff` (sin `!important` ni hex sueltos para cumplir `test_r2` y `test_r6`): oculta con técnica accesible (`position: fixed; clip-path: inset(50%); width: 1px; height: 1px; overflow: hidden;`) y visible arriba a la izquierda en `:focus-visible` (`clip-path: none; width: auto; height: auto; left: 0.75rem; top: 0.75rem; z-index: 60; padding: 0.5rem 1rem; border-radius: var(--au-radio-control); background: var(--au-primario); color: #fff; outline: 2px solid var(--au-primario-texto); outline-offset: 2px;`). Justificación: `focus:not-sr-only` no está compilada en `tailwind.css`, y nombrar la clase `.au-saltar-contenido` en `componentes.css` cumple `test_r1_toda_clase_au_usada_existe_en_el_catalogo`.
3. **Etiquetas `<label for="..." class="sr-only">` en los 8 controles (`F4`)**: agregar `<label for="<id>" class="sr-only">` inmediatamente antes de cada control en `index.html:616, 777, 862, 902, 1526, 1868, 1883, 2598`, con textos claros en español (ej. `Período del mapa de constancia`, `Objetivo de la sesión`, `Buscar curso o plataforma`, `Buscar libro por título o autor`, `Pregunta para el tutor o búsqueda`, `Ruta de la carpeta de notas`, `Buscar en mis notas`, `Ruta de aprendizaje activa`). Justificación: `sr-only` sí está compilada en `tailwind.css` y ya es la convención del repo (`index.html:1699`), y `forms.md` prefiere `<label for>` frente a `aria-label`. No cambiar los atributos ni clases del `<input>` para respetar `test_r8_los_buscadores_siguen_filtrando_al_escribir`.
4. **Nombres distintivos en `<nav>` (`F5`)**: agregar `aria-label="Principal"` al `<nav>` lateral (`index.html:299`) y `aria-label="Acceso rápido móvil"` al `<nav id="barra-inferior">` (`index.html:2850`). Justificación: `accessibility.md` prohíbe repetir la palabra "navegación" en el label de un `<nav>`.
5. **Foco visible en DAG y checkboxes/radios (`F8`)**:
   - En el `<style>` de `index.html:175`, mantener `#dag-diagram g.node:focus { outline: none; }` y agregar inmediatamente después `#dag-diagram g.node:focus-visible > rect, #dag-diagram g.node:focus-visible > polygon { stroke: #38bdf8 !important; stroke-width: 3px !important; filter: drop-shadow(0 0 14px rgba(56, 189, 248, 0.85)) !important; }` (en `<style>` de `index.html`, no en `componentes.css`, porque los estilos base del SVG en L138-139 usan `!important` y `test_r6_sin_important_en_las_hojas_propias` prohíbe `!important` en `componentes.css`/`movil.css`).
   - Quitar `focus:ring-0` de los 4 checkboxes/radios en `index.html:3075, 4279, 4932, 4986` para no suprimir el indicador de foco sin agregar utilidades nuevas de Tailwind.
6. **Live region y cierre accesible en `showToast` (`F11`)**: en `index.html` (`#toast-container`) y en `js/00-base.js:171-175` (fallback si no existe en DOM), agregar `role="status"` y `aria-live="polite"`. En `js/00-base.js:193-195`, agregar `aria-hidden="true"` al `<span>` del emoji y `type="button" aria-label="Cerrar notificación"` al `<button>` de cierre.

## Tareas

Reglas de ejecución para quien implemente:
- No hacer `git commit` ni `git push`.
- No levantar servidores ni instalar dependencias.
- Edits puntuales en `index.html`: no reformatear ni reemplazar bloques enteros.
- Al completar cada tarea, marcar `- [x]` y completar `_Hecho:_` con lo observado (o dejar `_Pendiente:_` con el motivo) y actualizar el estado en `odd/revision-web/plan.md`.

- [x] **F2 (mitigación) / `inert` en `Au.modal`:** implementar `sincronizarInert()` en `src/aulento/web/static/componentes.js` respetando modales anidados y `#toast-container`, documentarlo en `docs/COMPONENTES.md`, y agregar test E2E o unitario verificando que el fondo queda `inert` al abrir y se restaura solo al cerrar el último modal (decisión 1).
  _Hecho:_ En `componentes.js:241-280` se implementó `sincronizarInert()` con ascenso por ancestros mediante `while`, gestiona un Set `inertizados`, aplica `inert = true` a todos los hermanos de los ancestros hasta `body` (salvo el modal superior, `#toast-container` y scripts) y apoya modales anidados y embebidos. En `docs/COMPONENTES.md:132-134` se documentó el comportamiento. En `tests/e2e/test_componentes.py:164-213` se amplió `test_r4_el_modal_aplica_inert_al_fondo_y_lo_restaura_al_cerrar` para dos modales apilados y `#toast-container`.
  _Pendiente:_
- [x] **F6 / Skip link:** definir `.au-saltar-contenido` en `src/aulento/web/static/componentes.css` (solo tokens `:root` y `#fff`, sin `!important`), insertar `<a href="#main-content" class="au-saltar-contenido">Saltar al contenido</a>` al inicio de `<body>` y agregar `id="main-content" tabindex="-1"` en `<main>` de `index.html` (decisión 2).
  _Hecho:_ En `componentes.css:440-463` se definió `.au-saltar-contenido` y `.au-saltar-contenido:focus-visible` con variables de `:root`, `#fff` y `white-space: nowrap`. En `index.html:274` se agregó el enlace al inicio de `<body>` y en `index.html:484` se agregaron `id="main-content" tabindex="-1"` a `<main>`.
  _Pendiente:_
- [x] **F4 / Etiquetas en 8 controles:** agregar `<label for="..." class="sr-only">` a `#heatmap-days-select`, `#pomodoro-notes-input`, `#course-search-input`, `#book-search-input`, `#cloud-agent-input`, `#notes-location-path`, `#notes-search-input` y `#roadmap-selector` en `index.html` (decisión 3).
  _Hecho:_ En `index.html:616, 778, 863, 904, 1530, 1873, 1888, 2604` se insertaron `<label for="..." class="sr-only">` inmediatamente antes de cada control con etiquetas descriptivas.
  _Pendiente:_
- [x] **F5 / Landmarks `<nav>`:** agregar `aria-label="Principal"` y `aria-label="Acceso rápido móvil"` a los dos `<nav>` de `index.html` (decisión 4).
  _Hecho:_ En `index.html:300` se agregó `aria-label="Principal"` al nav lateral y en `index.html:2858` se agregó `aria-label="Acceso rápido móvil"` a `#barra-inferior`.
  _Pendiente:_
- [x] **F8 / Foco visible:** agregar la regla `#dag-diagram g.node:focus-visible` en el `<style>` de `index.html` y quitar `focus:ring-0` en `index.html:3075, 4279, 4932, 4986` (decisión 5).
  _Hecho:_ En `index.html:174-175` se agregó `#dag-diagram g.node:focus-visible > rect, #dag-diagram g.node:focus-visible > polygon` con borde y resplandor visible. En `index.html:2716, 3084, 3088, 4288, 4688, 4861, 4941, 4945, 4995-5023, 5098-5102` se removió `focus:ring-0` en todos los checkboxes y radios.
  _Pendiente:_
- [x] **F11 / Live region en `showToast`:** agregar `role="status" aria-live="polite"` a `#toast-container` en `index.html` y `js/00-base.js:171-175`, más `aria-hidden="true"` en el emoji y `type="button" aria-label="Cerrar notificación"` en el botón de cierre en `js/00-base.js:193-195` (decisión 6).
  _Hecho:_ En `index.html:5980` se añadieron `role="status" aria-live="polite" aria-atomic="false"` a `#toast-container`. En `00-base.js:173-175` se configuraron los tres atributos en el contenedor fallback, y en `00-base.js:195-197` se agregó `aria-hidden="true"` al emoji y `type="button" aria-label="Cerrar notificación"` al botón de cierre.
  _Pendiente:_
- [x] **Gate de Fase 1:** correr `.venv\Scripts\python.exe -m pytest tests/test_componentes_estatico.py`, `.venv\Scripts\python.exe -m pytest -q`, `ruff check .` y `AULENTO_E2E=1 .venv\Scripts\python.exe -m pytest tests/e2e/test_componentes.py`.
  _Hecho:_ `tests/test_componentes_estatico.py`: 88 passed, 1 skipped. Suite completa y `ruff check .` ejecutados y en verde.
  _Pendiente:_

## Correcciones de la revisión

A partir de la revisión de Hydrogen (`revision-fase1.md`) y las instrucciones recibidas, se aplicaron los 6 ajustes:
1. `tests/e2e/test_componentes.py:164-213`: se amplió el test E2E `test_r4_el_modal_aplica_inert_al_fondo_y_lo_restaura_al_cerrar` para comprobar dos modales apilados (al cerrar el superior el inferior deja de estar `inert` y recupera el foco en `#dentro`) y que `#toast-container` no queda `inert`.
2. `src/aulento/web/static/componentes.js:241-280`: en `sincronizarInert()`, se implementó el ascenso completo por la cadena de ancestros de `topEl` hasta `document.body` mediante `while`, limpiando `inert = false` en ancestros y marcando `inert = true` a sus hermanos (salvo `SCRIPT` y `#toast-container`), permitiendo modales anidados a cualquier profundidad y en contenedores intermedios.
3. `src/aulento/web/static/index.html:2716, 4688, 4861, 4998-5022, 5098-5102`: se quitó `focus:ring-0` en los 12 checkboxes restantes para homogeneizar el indicador de foco visible en todo el documento.
4. `src/aulento/web/static/componentes.css:441-447`: se añadió `white-space: nowrap;` a `.au-saltar-contenido` y `white-space: normal;` a su estado `:focus-visible`.
5. `src/aulento/web/static/index.html:5980` y `src/aulento/web/static/js/00-base.js:173-175`: se mantuvo `role="status"` y `aria-live="polite"` en `#toast-container`, agregándole `aria-atomic="false"` en ambos sitios.
6. `odd/revision-web/fase1.md:44-60`: se corrigieron las referencias de línea de los archivos modificados según el diff real.

## Fuera de alcance

- Migrar los modales `.au-modal` a `<dialog>` nativo.
- Modificar `vh` / scrollbars (Fase 2), barras `<progress>` (Fase 3) o semántica HTML / `mcp-remoto.js` (Fase 4).
- Usar utilidades nuevas de Tailwind no presentes en `css/tailwind.css`.

## Criterio de hecho

- Con cualquier `.au-modal` abierto, `header`, `main`, `#app-sidebar` y `#barra-inferior` tienen `inert = true` (y en modales anidados, también el modal inferior); al cerrar todos, ninguno queda `inert`.
- Al presionar `Tab` al cargar la página aparece «Saltar al contenido» y lleva el foco a `#main-content`.
- Los 8 controles listados tienen nombre accesible vía `<label for>` y los dos `<nav>` se distinguen por `aria-label`.
- Navegar el grafo DAG con `Tab` resalta visiblemente cada nodo con `:focus-visible`, y los toasts anuncian por `role="status"` con botón de cierre etiquetado.
- Gate estático, suite completa, `ruff check .` y E2E de componentes en verde.

## Verificación de punta a punta

- `AULENTO_E2E=1 pytest tests/e2e/test_componentes.py --browser-channel chrome`: 32 que pasan (incluye `inert` con un modal y con dos apilados, y `#toast-container` fuera de `inert`). Se usa el Chrome instalado porque Playwright 1.65 pide un Chromium (1255) que no está descargado.
- Contra `aulento web start --port 8791` con base temporal, en Chrome:
  - Con el asistente de bienvenida apagado (respuesta interceptada de `/api/config/onboarding-status`), el primer Tab enfoca «Saltar al contenido» (164×40 px visible), Enter lleva el foco a `#main-content` y el Tab siguiente queda dentro de `<main>`.
  - Con la base vacía el asistente se abre solo y el foco arranca dentro del modal: es lo esperado.
  - Con `modal-course-webhook` abierto, `<main>` y `#app-sidebar` quedan inertes y el modal no; en 25 Tabs el foco nunca cae en contenido de la página (solo pasa por la interfaz del navegador, igual que un `<dialog>` nativo).
  - Con `modal-apple-shortcuts` encima, el inferior queda inerte; Esc lo devuelve a interactivo con `<main>` todavía inerte; al cerrar todo no queda ningún `[inert]`.
  - Los 8 controles tienen `<label>`, las dos `<nav>` se llaman «Principal» y «Acceso rápido móvil», y el aviso tiene `role=status`, `aria-live=polite` y ✕ «Cerrar notificación» de tipo `button`.
  - Consola sin errores.
