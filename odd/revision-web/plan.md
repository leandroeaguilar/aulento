---
type: Plan
title: "Plan de mejoras del frontend web"
description: "Corrección y modernización en serie de los hallazgos decididos tras la revisión de src/aulento/web/static contra modern-web-guidance, en la rama fix/revision-web."
generated:
  by: process:decision-hydrogen
  at: 2026-11-20T11:40:00Z
---

# Plan de mejoras del frontend web (`src/aulento/web/static`)

Hallazgos evaluados a partir del escaneo automático (`legacy-scan.json`) y la auditoría manual (`informe-trabajador.md`) según las decisiones registradas en `decision-hydrogen.md`.

Estados posibles: `✅ Hecho`, `🔧 En curso`, `⏳ Pendiente`, `⏸️ Pospuesto`, `❌ Descartado`. Al cerrar cada tarea de una fase, quien implementa actualiza la fila correspondiente en este tablero.

## Tablero

| id | hallazgo | severidad | estado | fase |
|---|---|---|---|---|
| #1, #2, #3 | `::-webkit-scrollbar*` sin propiedades estándar `scrollbar-color` / `scrollbar-width`, sin `@supports not` ni contraste ≥ 3:1 (`index.html:32-35`) | Media | ✅ Hecho | 2 |
| #4 | `Enter` en `#modal-system-prompt` sin guarda IME `isComposing \|\| keyCode === 229` (`00-base.js:444`) | Alta | ✅ Hecho | 0 |
| #5 | Atajo global `e.code === 'Enter'` en `document` (`comunes.js:173`) ignora inputs | Baja | ❌ Descartado | — |
| #6 | Bucle de agrupación en `pantalla-notes.js:598` vs `Object.groupBy()` | Baja | ❌ Descartado | — |
| #7–#17 | Limpieza de contenedores con `.innerHTML = ''` en 11 sitios sin `replaceChildren()` | Baja | ⏸️ Pospuesto | — |
| #18 | Barra de espacio en Materiales (`index.html:1689`) con `div role="progressbar"` y `aria-valuenow="0"` congelado | Media | ✅ Hecho | 3 |
| #19, #20 | Reemplazo de `DOMPurify.sanitize` por `Element.prototype.setHTML()` (`pantalla-config.js:2059`, `pantalla-roadmap.js:2197`) | Baja | ❌ Descartado | — |
| F1 | `mermaid.min.js` (3,34 MB), `marked.min.js` y `purify.min.js` bloqueantes en `<head>` (`index.html:9-12`) | Alta | ✅ Hecho | 0 |
| F2 (mitigación) | Modales `.au-modal` sin aislamiento `inert` del resto de la página mientras están abiertos (`componentes.js:238-300`) | Alta | ✅ Hecho | 1 |
| F2 (`<dialog>`) | Migración completa de los >20 modales `.au-modal` a `<dialog>.showModal()` | Alta | ⏸️ Pospuesto | — |
| F3 | Interpolación sin escapar de `err.message` en `innerHTML` (`pantalla-roadmap.js:293, 1012`) | Alta | ✅ Hecho | 0 |
| F4 | 8 controles de formulario sin `<label>` programático (`index.html:616, 777, 862, 902, 1526, 1868, 1883, 2598`) | Alta | ✅ Hecho | 1 |
| F5 | Múltiples `<nav>` sin `aria-label` distintivo (`index.html:299, 2850`) | Media | ✅ Hecho | 1 |
| F6 | Ausencia de skip link al inicio de `<body>` y objetivo en `<main>` (`index.html:274, 484`) | Media | ✅ Hecho | 1 |
| F7 | `#system-health-popover` y `#user-dropdown-menu` implementados con `.hidden` en lugar de `[popover]` | Media | ❌ Descartado | — |
| F8 | `#dag-diagram g.node:focus { outline: none; }` (`index.html:175`) y `focus:ring-0` en checks/radios (`index.html:3075, 4279, 4932, 4986`) | Media | ✅ Hecho | 1 |
| F9 | Unidades fijas `vh` en visor DAG fullscreen (`index.html:98-106`) y ~25 modales (`max-h-[...vh]`) en lugar de `dvh` | Media | ✅ Hecho | 2 |
| F10 | Saltos de jerarquía `<h2>` → `<h4>` (`index.html:1592, 1769, 2702, 3028, 4518`) | Media | ✅ Hecho | 4 |
| F11 | `showToast` (`00-base.js:168-213`, `index.html:5972`) sin live region ni botón de cierre accesible | Media | ✅ Hecho | 1 |
| F12 | Ausencia de `lang="en"` en respuestas y ejemplos en inglés de tarjetas FSRS (`pantalla-fsrs.js:471-483`) | Media | ✅ Hecho | 4 |
| F13 | Falta de `autocomplete="off"` en campos `type="password"` de API keys | Media | ❌ Descartado | — |
| F14 | Tabla de auditoría IA sin `<caption>` ni `<th scope="col">` (`index.html:2474-2486`) | Media | ✅ Hecho | 4 |
| F15 | 15 `<script>` sin `defer` al final de `<body>` (`index.html:5327-5348`) bloquean el parseo antes de los 11 modales finales (`5352-6066`) | Media | ✅ Hecho | 0 |
| F16 | Contenedores scrollables sin `tabindex="0"` ni `role="region"` (`index.html:626, 2938`) | Baja | ✅ Hecho | 4 |
| F17 | 4 zonas de búsqueda en `<div>` en lugar de `<search>` (`index.html:860, 900, 1698, 1882`) | Baja | ✅ Hecho | 4 |
| F18 | Logo `<img src="/static/icons/icon.svg">` sin `width`/`height` (`index.html:284`) | Baja | ✅ Hecho | 4 |
| F19 | `Au.progreso` (`componentes.js:115-121`), `#fsrs-session-progress-bar` (`index.html:1171`), `#roadmap-progress-bar` (`2646`) y `pantalla-exams.js:504, 514` como `div` | Baja | ✅ Hecho | 3 |
| F20 | 10 botones de navegación lateral sin `type="button"` (`index.html:303-347`) | Baja | ✅ Hecho | 4 |
| F21 | Manejadores `onclick` inline en `mcp-remoto.js` (L45 y otros 3 en L127, L221, L280) fuera de `Au.acciones` | Baja | ✅ Hecho | 4 |

## Fases de la rama `fix/revision-web`

Las 5 fases modifican `src/aulento/web/static/index.html`, por lo que se implementan **estrictamente en serie** (una fase por vez, un solo agente), verificando el gate completo al cierre de cada una.

| Fase | Lote | Hallazgos | Depende de | Estado |
|---|---|---|---|---|
| 0. Carga crítica y seguridad | Lote 1 | F1, F15, F3, #4 | — | ✅ Hecho |
| 1. Accesibilidad interactiva y foco | Lote 2 | F4, F11, F8, F6, F5, F2 (mitigación `inert`) | Fase 0 | ✅ Hecho |
| 2. Móvil (`dvh`) y scrollbars | Lote 3 | F9, #1–#3 | Fase 1 | ✅ Hecho |
| 3. Barra `<progress>` nativa | Lote 4 | #18, F19 | Fase 2 | ✅ Hecho |
| 4. Semántica HTML, FSRS e higiene JS | Lote 5 | F10, F14, F12, F16, F17, F18, F20, F21 | Fase 3 | ✅ Hecho |

```text
fase 0 ──> fase 1 ──> fase 2 ──> fase 3 ──> fase 4
```

## Restricciones transversales

- **Tailwind CSS sin recompilar:** `css/tailwind.css` está precompilado (`v3.4.17`) y no existe `scripts/compilar_css.py` en el repo. `tests/test_componentes_estatico.py::test_r6_toda_utilidad_de_index_html_esta_compilada` falla ante cualquier clase con prefijo Tailwind no compilada (p. ej. `max-h-[90dvh]` o `focus:not-sr-only`).
- **Hojas propias:** `componentes.css` (carga antes de Tailwind; solo colores de `:root` o `#fff`, sin `!important`) y `movil.css` (carga después de Tailwind; sin `!important`).
- **Contratos estáticos:** sin `on*=` en HTML ni en plantillas JS; toda `data-accion` registrada con `Au.acciones.registrar`; todo `.au-modal` con su contrato intacto (`test_r4`); toda clase `au-*` en `componentes.css` (`test_r1`); toda función de `window.Au` documentada en `docs/COMPONENTES.md` (`test_r11`); todo recurso `src`/`href` de `index.html` precacheado en `sw.js`.
- **Gate obligatorio por fase:** `.venv\Scripts\python.exe -m pytest tests/test_componentes_estatico.py`, `.venv\Scripts\python.exe -m pytest -q`, `ruff check .` (y los tests E2E en `tests/e2e` con `AULENTO_E2E=1` cuando correspondan).
