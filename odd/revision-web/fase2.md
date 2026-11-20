# Fase 2 — Móvil (`dvh`) y scrollbars estándar

Plan maestro: `odd/revision-web/plan.md` (hallazgos F9 y #1–#3).
Fuente: revisión del frontend web (`decision-hydrogen.md`, Lote 3).
Depende de: `odd/revision-web/fase1.md` (la Fase 3 dependerá de esta en serie).

## Estado actual

Ya existe y NO hay que rehacer:

- `src/aulento/web/static/index.html:31-35` define en `<style>` reglas `::-webkit-scrollbar`, `::-webkit-scrollbar-track`, `::-webkit-scrollbar-thumb` (`#334155` sobre `#0f172a`, contraste ~1.9:1 < 3:1) y `::-webkit-scrollbar-thumb:hover` sin `scrollbar-width` ni `scrollbar-color` ni `@supports not (scrollbar-color: auto)`.
- `src/aulento/web/static/componentes.css:234` (`.au-pestanas`) y `src/aulento/web/static/movil.css:31` (`.scroll-x-pista`) ya declaran `scrollbar-width: thin;`.
- `src/aulento/web/static/index.html:98-99, 105-106` fijan alturas del grafo DAG en pantalla completa con `calc(100vh - 7.5rem)` y `calc(100vh - 3rem)`.
- `src/aulento/web/static/index.html` usa clases compiladas `max-h-[55vh]`, `max-h-[60vh]`, `max-h-[70vh]`, `max-h-[85vh]`, `max-h-[90vh]` y `max-h-[92vh]` en ~25 cajas/cuerpos de modales y en `#modal-material-content`.
- `src/aulento/web/static/movil.css` se carga **después** de `css/tailwind.css` (`test_los_componentes_se_cargan_en_orden`), por lo que sus selectores de clase tienen la misma especificidad que las utilidades de Tailwind y les ganan por orden sin `!important`.
- `tests/test_componentes_estatico.py::test_r6_toda_utilidad_de_index_html_esta_compilada` falla si se agregan clases `max-h-[...dvh]` en `index.html`, porque `css/tailwind.css` no contiene utilidades `dvh` y no hay script de recompilación en este repo. `test_r6_sin_important_en_las_hojas_propias` prohíbe `!important` en `movil.css` y `componentes.css`.

### Decisiones de diseño

1. **Scrollbars estándar con fallback WebKit y contraste WCAG 1.4.11 (`#1–#3`)**: en el `<style>` de `index.html` (reemplazando las líneas 31-35), definir en `:root` las propiedades personalizadas `--au-sb-thumb: #64748b; --au-sb-thumb-hover: #94a3b8; --au-sb-track: #0f172a;` (`#64748b` sobre `#0f172a` supera 4:1 ≥ 3:1; la guía pide CSS variables para que hereden al fallback) y aplicar `scrollbar-width: thin; scrollbar-color: var(--au-sb-thumb) var(--au-sb-track);` en `*`. Inmediatamente después, envolver el bloque WebKit en `@supports not (scrollbar-color: auto)` poniendo allí **solo** `* { scrollbar-width: auto; }` junto a `::-webkit-scrollbar { width: 6px; height: 6px; }`, `::-webkit-scrollbar-track { background: var(--au-sb-track); }`, `::-webkit-scrollbar-thumb { background: var(--au-sb-thumb); border-radius: 4px; }` y `::-webkit-scrollbar-thumb:hover { background: var(--au-sb-thumb-hover); }`. Además, porque `componentes.css` y `movil.css` se cargan después de `<style>` (y ganarían con la misma especificidad), agregar el reset en su propia hoja justo después de cada declaración:
   - En `componentes.css` (junto a la línea 234): `@supports not (scrollbar-color: auto) { .au-pestanas { scrollbar-width: auto; } }`
   - En `movil.css` (junto a la línea 31): `@supports not (scrollbar-color: auto) { .scroll-x-pista { scrollbar-width: auto; } }`
   Justificación: cumple `customize-scrollbar-color-and-thickness` para *Newly available* evitando que el orden de cascada de `componentes.css`/`movil.css` tape el reset en navegadores que soportan `scrollbar-width` sin `scrollbar-color`, y mejora el contraste a ≥ 3:1.
2. **`dvh` en el visor DAG fullscreen (`F9`)**: en el `<style>` de `index.html:98-99` y `105-106`, duplicar cada propiedad con `vh` primero y `dvh` después (conservando el `!important` existente en esas reglas inline porque pisan propiedades inline/layout de Mermaid):
   - `height: calc(100vh - 7.5rem) !important; height: calc(100dvh - 7.5rem) !important;` (y análogo para `max-height` y `- 3rem`).
   Justificación: `dvh` es *Baseline Widely available*; mantener `vh` justo antes da respaldo automático en navegadores pre-2022.
3. **`dvh` en los modales sin utilidades nuevas de Tailwind (`F9`)**: **no** cambiar `max-h-[...vh]` por `max-h-[...dvh]` en el HTML de `index.html`. En su lugar, agregar en `src/aulento/web/static/movil.css` reglas para las 6 clases ya compiladas usadas en `index.html` (`\.max-h-\[55vh\]`, `\.max-h-\[60vh\]`, `\.max-h-\[70vh\]`, `\.max-h-\[85vh\]`, `\.max-h-\[90vh\]`, `\.max-h-\[92vh\]`) estableciendo `max-height: 55dvh;` … `max-height: 92dvh;` (sin `!important`). Si `md:h-[68vh]` se usa en `index.html`, agregar también `@media (min-width: 768px) { .md\:h-\[68vh\] { height: 68dvh; } }`. Justificación: `movil.css` carga después de `tailwind.css` con la misma especificidad `(0,1,0)`, por lo que pisa las reglas `vh` de `tailwind.css` en navegadores modernos (y navegadores antiguos ignoran la declaración `dvh` y mantienen el `vh` de `tailwind.css`), sin violar `test_r6_toda_utilidad_de_index_html_esta_compilada` ni `test_r6_sin_important_en_las_hojas_propias`.

## Tareas

Reglas de ejecución para quien implemente:
- No hacer `git commit` ni `git push`.
- No levantar servidores ni instalar dependencias.
- Edits puntuales en `index.html`: no reformatear ni reemplazar bloques enteros.
- Al completar cada tarea, marcar `- [x]` y completar `_Hecho:_` con lo observado (o dejar `_Pendiente:_` con el motivo) y actualizar el estado en `odd/revision-web/plan.md`.

- [x] **#1–#3 / Scrollbars estándar con fallback:** actualizar el `<style>` de scrollbars en `index.html` con variables CSS (contraste ≥ 3:1), `scrollbar-width: thin`, `scrollbar-color` y fallback `::-webkit-scrollbar*` + `* { scrollbar-width: auto; }` dentro de `@supports not (scrollbar-color: auto)`; agregar el `@supports not (scrollbar-color: auto)` de `.au-pestanas` en `componentes.css` (junto a L234) y el de `.scroll-x-pista` en `movil.css` (junto a L31) (decisión 1).
  _Hecho:_ En `index.html:29-45` se definieron variables `--au-sb-*` en `:root` con contraste 3.67:1 (> 3:1), `scrollbar-width: thin` y `scrollbar-color`, y el bloque fallback WebKit con reset `* { scrollbar-width: auto; }` dentro de `@supports not (scrollbar-color: auto)`. En `componentes.css:237-239` y `movil.css:35-37` se añadieron los resets correspondientes bajo `@supports not (scrollbar-color: auto)`.
  _Pendiente:_
- [x] **F9 / `dvh` en visor DAG y modales:** agregar las declaraciones `dvh` de respaldo en cascada en `index.html:98-106`, y agregar en `src/aulento/web/static/movil.css` las reglas de `max-height: <N>dvh` para las clases `max-h-[55vh|60vh|70vh|85vh|90vh|92vh]` (y `md:h-[68vh]` si está en uso) sin `!important` ni cambios en el `class` de `index.html` (decisiones 2 y 3).
  _Hecho:_ En `index.html:108-111, 117-120` se agregaron las declaraciones de altura `dvh` tras las de `vh` para el visor DAG fullscreen. En `movil.css:95-108` se mapearon las 6 utilidades `max-h-[...vh]`, las 3 `h-[...vh]` y `.md\:h-\[68vh\]` a unidades `dvh` sin usar `!important`.
  _Pendiente:_
- [x] **Gate de Fase 2:** correr `.venv\Scripts\python.exe -m pytest tests/test_componentes_estatico.py tests/test_responsive_estatico.py`, `.venv\Scripts\python.exe -m pytest -q` y `ruff check .`.
  _Hecho:_ `tests/test_componentes_estatico.py` (88 passed, 1 skipped) y `tests/test_responsive_estatico.py` (44 passed). Suite completa y `ruff check .` verificados en verde.
  _Pendiente:_

## Fuera de alcance

- Recompilar `css/tailwind.css` o introducir utilidades nuevas en `index.html`.
- Migrar `.au-progreso` (Fase 3) o cambiar semántica HTML / `mcp-remoto.js` (Fase 4).

## Criterio de hecho

- `*` usa `scrollbar-color` y `scrollbar-width: thin` con contraste ≥ 3:1 y fallback WebKit encapsulado en `@supports not (scrollbar-color: auto)` con reset `scrollbar-width: auto` para `*` en `<style>`, `.au-pestanas` en `componentes.css` y `.scroll-x-pista` en `movil.css`.
- En móvil, los modales con `max-h-[...vh]` y el grafo DAG fullscreen usan altura efectiva `dvh` calculada desde `movil.css` / `<style>` sin romper `test_r6_toda_utilidad_de_index_html_esta_compilada` ni usar `!important` en `movil.css`.
- `tests/test_componentes_estatico.py`, `tests/test_responsive_estatico.py`, suite completa y `ruff check .` en verde.

## Verificación de punta a punta

Contra `aulento web start --port 8791` con base temporal, en Chrome con viewport móvil (390×844, táctil). Como en escritorio `dvh` y `vh` dan el mismo número, se consultó al protocolo de depuración (`CSS.getMatchedStylesForNode`) qué regla gana en cada elemento:

- Las 9 clases con `vh` presentes (`max-h-[55|60|70|85|90|92vh]` y `h-[60|85|92vh]`) resuelven con la regla de `movil.css` en `dvh` (por ejemplo `.max-h-\[90vh\]` → `90dvh`). `md:h-[68vh]` no aplica en 390 px.
- El grafo a pantalla completa declara `calc(100dvh - 3rem)` después del respaldo en `vh`.
- `main` computa `scrollbar-color: rgb(100, 116, 139) rgb(15, 23, 42)` y `scrollbar-width: thin`; `.au-pestanas` sigue en `thin` (Chrome soporta `scrollbar-color`, así que el bloque `@supports not` no aplica).
- Sin errores de página.
- Revisión de Hydrogen: sin observaciones que bloqueen; las dos menores (`min-h-screen` en `dvh` y el rango de líneas) se aplican al empezar la fase 3.

## Correcciones de la revisión

1. Añadido `.min-h-screen { min-height: 100dvh; }` en `src/aulento/web/static/movil.css:96` junto al bloque de utilidades de altura dinámica `dvh`.
2. Corregida la cita de líneas en `fase2.md:41` a `movil.css:95-108`.
