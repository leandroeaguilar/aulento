---
type: Guide
title: "Componentes de la interfaz"
description: "Catálogo de componentes de Aulento (clases au-* y funciones Au.*): cuándo usar cada uno, su API, ejemplos y qué no hacer. Es la referencia para migrar pantallas en la feature 072 y para todo marcado nuevo."
generated:
  by: process:claude-code
  at: 2026-11-10T00:00:00Z
sources:
  - src/aulento/web/static/componentes.css
  - src/aulento/web/static/componentes.js
  - specs/072-componentes-de-ui/spec.md
---

# Componentes de la interfaz

Aulento no usa React ni ningún framework con compilación. La interfaz se arma con dos piezas:

- **`componentes.css`**: tokens (variables CSS) y clases `au-*`. Sirven tanto en el HTML estático (`index.html`) como en el que arma JS.
- **`componentes.js`**: funciones `Au.*` que devuelven texto HTML ya escapado, las acciones delegadas (`Au.acciones`) y el modal (`Au.modal`). Es un script clásico que se carga antes que el resto del JS.

Las dos traen incluidas las reglas de la versión de celular (071):
- áreas de 40 px con el dedo;
- texto de al menos 12 px;
- cabeceras que bajan de línea en vez de aplastar el título;
- modales que empiezan arriba.

Por eso, en marcado nuevo, **no hacen falta** `.toque`, `text-xs sm:text-[11px]` ni las clases de capa de modal de la 071 (`.modal-capa`, ya borradas).

## Reglas

1. **Si existe un componente, se usa el componente.** Nada de copiar las clases de Tailwind de una tarjeta, un botón o una insignia.
2. **Todo texto se escapa.** Las funciones `Au.*` lo hacen solas. El HTML confiable entra únicamente por parámetros cuyo nombre termina en `Html` (`cuerpoHtml`, `accionesHtml`), y tiene que haberlo armado otra función `Au.*` o código propio, nunca un dato del usuario.
3. **Sin `onclick` en marcado nuevo.** Se usa `data-accion="nombre"` y se registra una vez con `Au.acciones.registrar('nombre', fn)` en el `pantalla-<tab>.js` de la pantalla. Un test (`test_componentes_estatico.py`) frena las acciones usadas que no están registradas.
4. **Los colores salen de los tokens** (`var(--au-…)`), no de valores sueltos. El primario es uno solo (`sky`); el resto de los tonos comunica un tipo: éxito, alerta o peligro.
5. **Tailwind sigue sirviendo para el layout** de cada pantalla: grillas, columnas y espacios entre bloques. Lo que tiene nombre en este catálogo no se arma con Tailwind.
6. **Las utilidades de Tailwind pisan al componente, así que se usan con criterio.** `componentes.css` carga antes que Tailwind: `hidden`, `md:hidden`, `flex-row`, `border-l-4` o un `w-full` sobre un `.au-*` funcionan, como en cualquier proyecto con Tailwind. Se usan para visibilidad y layout. La forma del componente (relleno, color, alto, radio) sale de sus modificadores (`au-campo__control--con-icono`, `au-boton--extremos`, tonos): un `p-3` o un `bg-*` sueltos lo desalinean del resto, y el estático los frena. Tampoco se suma `space-y-*` a un componente que ya tiene `gap`: los espacios se duplican.

## Tokens

Están en `:root`, al principio de `componentes.css`:

| Grupo | Variables |
|---|---|
| Superficies | `--au-fondo`, `--au-superficie`, `--au-superficie-alta`, `--au-superficie-hundida`, `--au-borde`, `--au-borde-fuerte` |
| Texto | `--au-texto`, `--au-texto-titulo`, `--au-texto-suave`, `--au-texto-tenue` |
| Tonos | `--au-primario*`, `--au-exito*`, `--au-alerta*`, `--au-peligro*` (fuerte, `-texto`, `-suave` de fondo, `-borde`) |
| Forma | `--au-radio-tarjeta` (24 px), `--au-radio-subtarjeta` (16 px), `--au-radio-control` (12 px), `--au-radio-pildora` |
| Controles | `--au-alto-control` (36 px con mouse), `--au-alto-control-tactil` (40 px con el dedo) |

## Catálogo

### Tarjeta: `Au.tarjeta`, `.au-tarjeta`

Agrupa un tema de la pantalla. Variantes: `--interactiva` (borde al pasar el mouse), `--destacada` (la del saludo del Dashboard) y `--hundida` (una subtarjeta dentro de otra).

```js
Au.tarjeta({
  cabecera: { titulo: 'Retención Macro de Temas', icono: '🧠', insignias: [{ texto: '0 pendientes', tono: 'primario' }],
              accionesHtml: [Au.boton({ texto: 'Actualizar', icono: '🔄', chico: true, accion: 'actualizar-macro' })] },
  cuerpoHtml: Au.vacio({ icono: '🎉', titulo: 'Todo consolidado', texto: 'No tenés temas vencidos hoy.' }),
});
```

En HTML estático: `<section class="au-tarjeta">` con la misma estructura que devuelve la función.

### Cabecera: `Au.cabecera`, `.au-cabecera`

Va arriba de una tarjeta o de una sección: ícono, título con sus insignias, subtítulo y acciones. En el celular, las acciones bajan de línea y el título nunca queda en una columna angosta. Usá `conLinea: true` para el separador de abajo, `nivel: 3` para un `h3` y `idTitulo` si un `aria-labelledby` apunta al título.

### Insignia: `Au.insignia`, `.au-insignia`

Estado, conteo o categoría. Tonos: `primario`, `exito`, `alerta`, `peligro`; sin tono queda neutra. Con `mono: true` usa letra monoespaciada, para cifras o códigos.

### Botón: `Au.boton`, `.au-boton`

- **Variantes:** `primario` (uno por bloque), `secundario` (la que va por defecto), `peligro` (borrar) y `fantasma` (acciones de bajo peso).
- **Teñidos suaves:** `au-boton--suave-primario`, `--suave-exito`, `--suave-alerta` y `--suave-peligro` (solo en el marcado, por clase). Son para un grupo de opciones donde el tono comunica algo y ninguna es la acción principal, como las calificaciones de una tarjeta (otra vez, difícil, bien, fácil).
- **Modificadores:** `chico`, `bloque` (ancho completo) y `soloIcono`, que **exige** `etiqueta`, porque es el `aria-label`.
- **Acción:** `accion` y `datos` generan `data-accion` y `data-*`.
- **Enlace:** con `href` se arma un `<a>`. La URL pasa por `Au.urlSegura`: solo `http(s)`, `mailto`, rutas relativas y anclas; cualquier otra cosa (por ejemplo `javascript:`) queda en `#`. Se pasa la URL tal cual, **sin** `sanitizeUrl` ni `escapeHtml`: escaparla dos veces rompe los `&`.
- **Mosaico:** `au-boton--extremos` pone el texto a la izquierda y el ícono final a la derecha.
- **Prendido y apagado:** un botón que se elige y se suelta (los días de la agenda, los minutos del planificador) lleva `aria-pressed="true"`/`"false"` y se pinta como primario cuando está prendido. El JS cambia el atributo, nunca la clase: un `className = '… bg-sky-600 …'` le pisa el componente.

```js
Au.boton({ texto: 'Registrar libro', variante: 'primario', icono: '+', accion: 'abrir-registro-libro' });
Au.boton({ icono: '🗑️', soloIcono: true, etiqueta: 'Eliminar libro', variante: 'fantasma', accion: 'eliminar-libro', datos: { libro: 3 } });
```

### Pestañas: `Au.pestanas`, `.au-pestanas`

Control segmentado: vistas, filtros o niveles. Usa `role="tablist"` y marca la activa con `aria-selected`. Con `accion`, cada pestaña manda su `data-valor`. Si no entra en el ancho, se desplaza de costado.

### Campo: `Au.campo`, `.au-campo`

Etiqueta, control, ayuda y error, enlazados entre sí (`for`, `aria-describedby`, `aria-invalid`). Para un ícono adentro, a la izquierda (una lupa), el control lleva `au-campo__control--con-icono` y el ícono va en un `<span class="au-campo__icono" aria-hidden="true">` hermano, dentro de un contenedor `relative`. Con `opciones` arma un `select`; con `tipo: 'textarea'`, un área de texto. El `id` es obligatorio. Con el dedo, el control mide 40 px y la letra 16 px, para que iOS no haga zoom.

### Métrica: `Au.kpi`, `.au-kpi`

Etiqueta (que se parte en dos líneas, nunca se trunca), valor, unidad y detalle.

### Barra de progreso: `Au.progreso`, `.au-progreso`

Renderiza un `<progress>` nativo (con semántica implícita `role="progressbar"`). `valor` y `maximo`, acotados entre 0 y `maximo` (por defecto 100). Accesible con `etiqueta` (`aria-label`). Tonos: `exito`, `alerta` y `peligro` (`au-progreso--exito`, `au-progreso--alerta`, `au-progreso--peligro`).

### Estado vacío: `Au.vacio`, `.au-vacio`

Cuando una lista no tiene elementos: ícono, título, texto y, opcionalmente, una acción (`accionHtml`).

### Aviso: `Au.aviso`, `.au-aviso`

Un mensaje dentro de la página. Con `alerta` o `peligro` lleva `role="alert"`; si no, `role="status"`. Para mensajes pasajeros sigue estando `showToast`.

### Fila: `Au.fila`, `.au-fila`

Un elemento de una lista lateral, como notas o materiales. Con `accion` es un botón; con `activa`, queda marcado y con `aria-current`.

### Modal: `Au.modal`, `.au-modal`

```html
<div id="mi-modal" class="au-modal" hidden role="dialog" aria-modal="true" aria-labelledby="mi-modal-titulo">
  <div class="au-modal__caja">
    <div class="au-modal__cabecera">
      <h2 id="mi-modal-titulo" class="au-modal__titulo">Título</h2>
      <button type="button" class="au-boton au-boton--fantasma au-boton--icono" data-accion="au-cerrar-modal" aria-label="Cerrar">✕</button>
    </div>
    <div class="au-modal__cuerpo">…</div>
    <div class="au-modal__pie">…</div>
  </div>
</div>
```

- `Au.modal.abrir(id, disparador)` lo muestra, pone el foco adentro (primero en el `[autofocus]`) y recuerda quién lo abrió. Lanza un error si al modal le falta `role="dialog"`, `aria-modal="true"` o un `aria-labelledby` que apunte a un elemento existente. Aplica `inert` al resto de los elementos de la página (hijos directos de `body`, salvo `#toast-container` y scripts) para aislar el fondo. En modales anidados, el modal inferior también pasa a ser `inert`.
- `Au.modal.cerrar(id)` lo oculta, remueve el aislamiento `inert` (si no quedan más modales abiertos, o restaurando el modal anterior si era anidado) y le devuelve el foco a ese control.
- Al cerrarse por cualquier vía (Esc, ✕, fondo o `Au.modal.cerrar`) el modal emite `au:cerrado`. La limpieza que hacía una función `closeX()` (resetear un formulario, cortar un audio) se engancha ahí, para que corra también con Esc y con el fondo:
  ```js
  document.getElementById('mi-modal').addEventListener('au:cerrado', limpiarMiModal);
  ```
- Un modal de progreso («generando…») lleva `data-sin-cierre`: Esc y el fondo no lo cierran, solo `Au.modal.cerrar` desde el código cuando termina.
- Un modal armado en JS lleva el mismo marcado, se agrega al `body` y se abre con `Au.modal.abrir`; si hay que borrarlo al cerrar, se borra en su `au:cerrado`.
- **Si un listener de `au:cerrado` resuelve una promesa** (como `showConfirmDialog`), soltalo **antes** de llamar a `Au.modal.cerrar`: `au:cerrado` se emite en el acto, y si sigue enganchado resuelve como «cancelar» lo que el usuario aceptó.
- `Au.modal.abierto(id)` reemplaza a `!el.classList.contains('hidden')`. Un `.au-modal` se oculta con el atributo `hidden`, nunca con la clase: el estático lo controla.
- Se cierra con Esc (el de arriba, si hay varios), con la ✕ (`data-accion="au-cerrar-modal"`) o tocando el fondo.
- Tamaños: `.au-modal__caja--angosta` (24 rem), la normal (32 rem) y `--ancha` (48 rem).

### Acciones delegadas: `Au.acciones`

`Au.acciones.registrar(nombre, fn)`, donde `fn(elemento, dataset, evento)`. Un único listener en `document` atiende:
- `click` en botones y enlaces;
- `change` en `select`, `input` y `textarea`;
- `submit` en formularios, con el `preventDefault` ya hecho.
- Un enlace o control propio (`a[href]`, `button`, campo) dentro de un elemento con acción, como una tarjeta clickeable, hace lo suyo y **no** dispara la acción del contenedor. `data-sin-accion` en un elemento corta la búsqueda: es el viejo `onclick="event.stopPropagation()"`.
- `input` en los campos marcados con `data-al-escribir` (un buscador que filtra mientras se escribe): esos campos disparan su acción en cada tecla y no en el `change`.

Registrar dos veces el mismo nombre es un error. `Au.acciones.existe(nombre)` sirve para los tests.

### Utilidades: `Au.escapar`, `Au.atributos`, `Au.clases`, `Au.urlSegura`

- `Au.escapar(texto)` escapa `& < > " '`.
- `Au.atributos({...})` arma atributos escapados y rechaza nombres raros y manejadores en línea (`on*`).
- `Au.urlSegura(url)` devuelve la URL si es `http(s)`, `mailto`, relativa o un ancla, y `#` si no. No escapa.
- `Au.clases(...)` une las clases que no sean vacías.

## Migrar una pantalla

Seguí la receta de `specs/072-componentes-de-ui/plan.md`:
1. Reemplazá los patrones por componentes y los `onclick` por acciones.
2. Mantené los `id`.
3. Agregá la pestaña a `PANTALLAS_MIGRADAS` en `tests/test_componentes_estatico.py`.
4. Corré los E2E de celular y compará capturas a 375 y 1280.

## Qué no hacer

- Armar HTML con `innerHTML` y datos sin escapar: usá `Au.*` o `Au.escapar`.
- Agregar `!important`: el orden de las hojas (componentes → Tailwind → movil) ya lo resuelve.
- Crear una variante nueva para un solo caso. Si hace falta, se agrega al catálogo, a este documento y a los tests.
