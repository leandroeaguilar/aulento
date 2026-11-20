# Fase 3 — Barra `<progress>` nativa unificada

Plan maestro: `odd/revision-web/plan.md` (hallazgos #18 y F19).
Fuente: revisión del frontend web (`decision-hydrogen.md`, Lote 4).
Depende de: `odd/revision-web/fase2.md` (la Fase 4 dependerá de esta en serie).

## Estado actual

Ya existe y NO hay que rehacer:

- `src/aulento/web/static/componentes.css:305-319` define `.au-progreso`, `.au-progreso__barra` y variantes `.au-progreso--exito`, `.au-progreso--alerta`, `.au-progreso--peligro`.
- `src/aulento/web/static/componentes.js:115-121` define `Au.progreso({ valor = 0, maximo = 100, tono: t, etiqueta } = {})`, usado en `js/pantalla-books.js:106`, `js/pantalla-courses.js:129` y `js/pantalla-dashboard.js:135`.
- `src/aulento/web/static/index.html` tiene 3 barras de progreso estáticas con `div.au-progreso` + `div.au-progreso__barra`:
  - L1171-1172 (`#fsrs-session-progress-bar`, actualizada en `js/pantalla-fsrs.js:541-547` via `.style.width`).
  - L1689-1690 (`#materiales-espacio-barra`, con `aria-valuenow="0"` fijo y actualizada en `js/pantalla-brain.js:374-380` via `.style.width` y `barra.parentElement.className`).
  - L2646-2647 (`#roadmap-progress-bar`, actualizada en `js/pantalla-roadmap.js:317, 346` via `.style.width`).
- `src/aulento/web/static/js/pantalla-exams.js:504-506` y `514-516` arman dos barras inline de `div.au-progreso` sin usar `Au.progreso`.
- `tests/test_componentes_estatico.py` verifica:
  - `test_r1_toda_clase_au_usada_existe_en_el_catalogo` (L159): toda clase `au-*` usada en HTML/JS debe existir en `componentes.css`.
  - `test_r1_las_utilidades_de_color_no_pintan_componentes` (L174): sin `bg-*`/`text-*` de Tailwind sobre `.au-progreso__barra`.
  - `test_r11_el_catalogo_esta_documentado` (L57): toda función de `window.Au` debe estar documentada en `docs/COMPONENTES.md`.
- `tests/test_interfaz_materiales.py:100` aserta `'id="materiales-espacio-texto"' in HTML and 'id="materiales-espacio-barra"' in HTML`.
- `tests/e2e/test_componentes.py:101-106` (`test_progreso_acota_y_anuncia`) consulta `.au-progreso__barra` y `get_by_role("progressbar", name="Avance")`.

### Decisiones de diseño

1. **Unificar todas las `.au-progreso` en `<progress>` nativo (`#18`, `F19`)**: migrar `Au.progreso`, las 3 barras de `index.html` (`1171`, `1689`, `2646`) y las 2 barras de `js/pantalla-exams.js:504, 514` a `<progress class="au-progreso ...">`. Justificación: evita mantener dos contratos CSS distintos (`div` + hijo vs `<progress>` nativo), elimina atributos `aria-valuenow` desactualizados en Materiales y faltantes en FSRS/Rutas, y usa el elemento nativo con semántica implícita `role="progressbar"`.
2. **Estilos de `progress.au-progreso` en `componentes.css` sin agrupar pseudo-elementos**:
   - Definir `--au-progreso-relleno: var(--au-primario-hover);` en `progress.au-progreso` (o `.au-progreso`), junto con `appearance: none; -webkit-appearance: none; display: block; width: 100%; height: 0.5rem; border: 0 solid; border-radius: var(--au-radio-pildora); background: var(--au-superficie-alta); overflow: clip;` (en L1171 `w-28 sm:w-44` de `tailwind.css` carga después y sobrescribe `width: 100%` sin `!important`).
   - En `.au-progreso--exito`, `.au-progreso--alerta`, `.au-progreso--peligro`, cambiar solo `--au-progreso-relleno` (`var(--au-exito-texto)`, `var(--au-alerta-texto)`, `var(--au-peligro-texto)`).
   - Reglas **separadas** (nunca agrupadas en una misma regla CSS, según `progress.md:56`):
     - `.au-progreso::-webkit-progress-bar { background: transparent; }`
     - `.au-progreso::-webkit-progress-value { background: var(--au-progreso-relleno); border-radius: var(--au-radio-pildora); transition: inline-size 0.3s; }`
     - `.au-progreso::-moz-progress-bar { background: var(--au-progreso-relleno); border-radius: var(--au-radio-pildora); transition: inline-size 0.3s; }`
   - Eliminar `.au-progreso__barra` de `componentes.css` tras migrar todos los sitios para que no quede código muerto. Solo usar tokens `:root`, sin `!important` (`test_r2`, `test_r6`).
3. **API de `Au.progreso` en `componentes.js`**: mantener la misma firma `{ valor = 0, maximo = 100, tono: t, etiqueta } = {}`, calcular `const max = Number(maximo) > 0 ? Number(maximo) : 100;` y `const val = Math.max(0, Math.min(max, Number(valor) || 0));`, y devolver `<progress class="${clases('au-progreso', t === 'exito' && 'au-progreso--exito', t === 'alerta' && 'au-progreso--alerta', t === 'peligro' && 'au-progreso--peligro')}" value="${escapar(val)}" max="${escapar(max)}"${atributos({ 'aria-label': etiqueta })}></progress>`. Justificación: los llamadores existentes (`pantalla-books.js`, `pantalla-courses.js`, `pantalla-dashboard.js`) no requieren cambios, y se suma soporte del tono `peligro` que ya existía en CSS.
4. **Adaptar los 3 consumidores estáticos y `pantalla-exams.js`**:
   - `index.html:1171-1173` → `<progress id="fsrs-session-progress-bar" class="w-28 sm:w-44 au-progreso" value="10" max="100" aria-label="Progreso de la sesión actual" title="Progreso de la sesión actual"></progress>`; en `js/pantalla-fsrs.js:546` usar `progressBar.value = pct;`.
   - `index.html:1689-1691` → `<progress id="materiales-espacio-barra" class="au-progreso" value="0" max="100" aria-label="Espacio usado"></progress>` (preserva el `id` que exige `tests/test_interfaz_materiales.py:100`); en `js/pantalla-brain.js:378-380`, actualizar `barra.value = Number(porcentaje.toFixed(1));` y `barra.className = ...` directamente sobre `barra` (ya no `barra.parentElement`, que ahora sería el `div.space-y-1.5` contenedor!).
   - `index.html:2646-2648` → `<progress id="roadmap-progress-bar" class="au-progreso" value="0" max="100" aria-label="Maestría de la ruta"></progress>`; en `js/pantalla-roadmap.js:317, 346` usar `.value = 0;` y `.value = Math.max(0, Math.min(100, Number(detail.progreso_pct) || 0));`.
   - `js/pantalla-exams.js:504, 514`: reemplazar ambos bloques por llamadas a `Au.progreso(...)`.
5. **Documentación y tests**: actualizar `docs/COMPONENTES.md` (sección `Barra de progreso: Au.progreso, .au-progreso`) indicando el uso de `<progress>` nativo (incluyendo tono `peligro`) y actualizar `tests/e2e/test_componentes.py::test_progreso_acota_y_anuncia` para verificar `.value` y `.max` sobre `progress.au-progreso` y `get_by_role("progressbar", name="Avance")`.

## Tareas

Reglas de ejecución para quien implemente:
- No hacer `git commit` ni `git push`.
- No levantar servidores ni instalar dependencias.
- Edits puntuales en `index.html`: no reformatear ni reemplazar bloques enteros.
- Al completar cada tarea, marcar `- [x]` y completar `_Hecho:_` con lo observado (o dejar `_Pendiente:_` con el motivo) y actualizar el estado en `odd/revision-web/plan.md`.

- [x] **CSS `<progress>`:** actualizar `.au-progreso` en `src/aulento/web/static/componentes.css` con reglas separadas `::-webkit-progress-bar`, `::-webkit-progress-value` y `::-moz-progress-bar`, usando solo tokens de `:root` y sin `!important` (decisión 2).
  _Hecho:_ En `src/aulento/web/static/componentes.css:307-322` se redefinió `.au-progreso` con variable `--au-progreso-relleno`, `appearance: none; overflow: clip;`, soporte de tonos `exito`, `alerta` y `peligro`, y pseudo-elementos desacoplados `::-webkit-progress-bar`, `::-webkit-progress-value` y `::-moz-progress-bar`. Se eliminó la clase `.au-progreso__barra`.
  _Pendiente:_
- [x] **Componente `Au.progreso` y `docs/COMPONENTES.md`:** actualizar `Au.progreso` en `src/aulento/web/static/componentes.js` para emitir `<progress>` nativo y actualizar `docs/COMPONENTES.md` (decisiones 3 y 5).
  _Hecho:_ En `src/aulento/web/static/componentes.js:115-119` se actualizó `Au.progreso` para emitir `<progress class="au-progreso..." value="..." max="..." aria-label="...">`. En `docs/COMPONENTES.md:101-103` se documentó el uso del elemento `<progress>` nativo y los tonos de relleno.
  _Pendiente:_
- [x] **#18 y F19 / Barras en `index.html` y pantallas:** migrar las barras de `index.html:1171, 1689, 2646`, `js/pantalla-fsrs.js:546`, `js/pantalla-brain.js:378-380`, `js/pantalla-roadmap.js:317, 346` y `js/pantalla-exams.js:504, 514` (decisión 4).
  _Hecho:_ En `index.html:1191, 1708, 2666` se sustituyeron los contenedores `div` por `<progress>` nativos conservando IDs, clases utilitarias y etiquetas accesibles. En `pantalla-fsrs.js:546` y `pantalla-roadmap.js:317, 346` se actualizó `.value`. En `pantalla-brain.js:378-379` se asignó `.value` y `.className` directamente sobre el elemento `barra`. En `pantalla-exams.js:504, 514` se reemplazaron los bloques `div` por `Au.progreso(...)`.
  _Pendiente:_
- [x] **Tests y Gate de Fase 3:** actualizar `tests/e2e/test_componentes.py::test_progreso_acota_y_anuncia`; correr `.venv\Scripts\python.exe -m pytest tests/test_componentes_estatico.py tests/test_interfaz_materiales.py`, `.venv\Scripts\python.exe -m pytest -q`, `ruff check .` y `AULENTO_E2E=1 .venv\Scripts\python.exe -m pytest tests/e2e/test_componentes.py`.
  _Hecho:_ En `tests/e2e/test_componentes.py:101-105` se actualizó `test_progreso_acota_y_anuncia` para evaluar `.value` y `.max` sobre `progress.au-progreso`. Gate estático (`test_componentes_estatico.py`, `test_interfaz_materiales.py`) y `ruff check .` verificados en verde.
  _Pendiente:_

## Fuera de alcance

- Tocar barras o indicadores que no usan `.au-progreso` ni `role="progressbar"` (si quedara alguno ajeno al catálogo, dejarlo fuera de este lote; verificar `index.html:4510` `#evo-global-progress` solo si no rompe scope — no se incluye aquí porque no usa `.au-progreso`).
- Cambios de la Fase 4 (semántica HTML, FSRS `lang="en"`, `mcp-remoto.js`).

## Criterio de hecho

- Todas las instancias de `.au-progreso` y `Au.progreso` renderizan `<progress>` nativo con `value`/`max` actualizados en tiempo real.
- `componentes.css` no agrupa selectores `-webkit-` y `-moz-`, usa solo variables de `:root` y no contiene `.au-progreso__barra` huérfana ni `!important`.
- `tests/test_componentes_estatico.py`, `tests/test_interfaz_materiales.py`, suite completa, `ruff check .` y E2E de componentes pasan en verde.

## Verificación de punta a punta

- Suite completa (`pytest -q -n 4`, corrida por el implementador): 2381 que pasan, 10 omitidos; `ruff check .` limpio.
- `AULENTO_E2E=1 pytest tests/e2e/test_componentes.py --browser-channel chrome` (corrido por el orquestador): 32 que pasan, incluido `test_progreso_acota_y_anuncia`.
- Contra `aulento web start --port 8791` con base temporal, en Chrome:
  - Las 3 barras fijas (`#fsrs-session-progress-bar`, `#materiales-espacio-barra`, `#roadmap-progress-bar`) son `<progress>` con `value`, `max=100` y nombre accesible («Progreso de la sesión actual», «Espacio usado», «Maestría de la ruta»).
  - `Au.progreso({ valor: 150, maximo: 100, tono: 'peligro', etiqueta: 'Avance' })` da `value=100` con `au-progreso--peligro`, y se encuentra por rol `progressbar` con nombre «Avance». Con `valor: -5, maximo: 0` da `value=0` y `max=100`.
  - Barra de espacio de Materiales con uso 30/100, 75/100, 95/100, 150/100 y 10/0: valores 30, 75, 95, 100 y 0; tonos normal, alerta, peligro, peligro y normal.
  - Captura de los cuatro tonos al 60 % (`fase3-tonos.png` en el scratchpad): celeste, verde, ámbar y rojo sobre la pista oscura.
  - Sin errores de página.
- Revisión de Hydrogen: la observación que bloqueaba era que estos resultados no constaban acá; las tres menores (regex del test de color, acotar `porcentaje` en `pantalla-brain.js` y `pct` en `pantalla-fsrs.js`) se aplican al empezar la fase 4.

## Correcciones de la revisión

1. Registrada la ejecución completa de la suite y suite E2E en verde en el informe y bitácora.
2. Actualizada la regex en `tests/test_componentes_estatico.py:177` reemplazando `progreso__barra` por `progreso`.
3. En `src/aulento/web/static/js/pantalla-brain.js:376`, acotado `porcentaje` con `Math.max(0, Math.min(100, ...))` y guarda `Number(uso.usado) || 0` contra `NaN`.
4. En `src/aulento/web/static/js/pantalla-fsrs.js:545`, acotado `pct` con `Math.max(0, Math.min(100, ...))` contra valores negativos.
