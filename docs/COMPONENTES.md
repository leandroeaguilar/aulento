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
| Espacio | `--au-espacio-0-5` … `--au-espacio-10`: pasos de 4 px en rem (0,5 = 2 px, 1 = 4 px, 4 = 16 px, 10 = 40 px). En CSS propio, nada de px sueltos para el relleno interior |

## Catálogo

### ¿Tarjeta o sección?

La regla viene de [Astryx](https://github.com/meta/astryx), el sistema de diseño de Meta: **la tarjeta es la excepción, no la forma por defecto de agrupar**.

- **Tarjeta** (`au-tarjeta`): un elemento suelto que se puede comparar, reordenar o accionar por separado. Por ejemplo, un curso en la grilla de cursos, una tarjeta de repaso o un examen.
- **Sección** (`au-seccion`): una región de la página. Por ejemplo, un grupo de ajustes, un panel de la barra lateral, un bloque de métricas o una barra de filtros. Un título y el espacio ya marcan qué va junto, sin bordes.

Qué no hacer:
- **Tarjeta dentro de tarjeta.** Adentro de una tarjeta se usa una sección `--con-linea`, o una `au-tarjeta--hundida` solo si es un recuadro de verdad (una cita, un código).
- **Grillas de tarjetas idénticas.** Ícono, título y texto repetidos no hacen falta: o se varía el diseño, o va una lista de `au-fila`, o una grilla de `au-kpi`.
- **Relleno doble.** El contenedor es dueño del relleno, y lo de adentro no suma el suyo.
- **Un mismo hueco en toda la pantalla.** Se combina uno chico dentro de cada grupo (`gap-2`, `gap-3`) con uno grande entre grupos (`gap-6`, `gap-8`).

### Sección: `Au.seccion`, `.au-seccion`

Una región de la página: va en columna, con un hueco de 16 px entre sus hijos, sin fondo, sin borde y sin sombra. Arriba lleva una `au-cabecera` (con `nivel: 3` si está dentro de otra región). Variantes, que se combinan:

- `--suave`: fondo hundido, borde y relleno. Es un panel o una barra de filtros que tiene que separarse del fondo.
- `--con-linea`: un separador arriba. Es la siguiente región dentro de la misma tarjeta o columna.
- `--apretada`: un hueco de 8 px. Es para un grupo cuyos elementos van juntos.

```js
Au.seccion({
  cabecera: { titulo: 'Notificaciones', nivel: 3, subtitulo: 'Qué te avisa Aulento y cuándo' },
  cuerpoHtml: camposHtml,
  variantes: ['con-linea'],
});
```

En HTML estático: `<section class="au-seccion au-seccion--suave">`. Una variante que no existe lanza un error.

### Tarjeta: `Au.tarjeta`, `.au-tarjeta`

Un elemento suelto de la pantalla (ver «¿Tarjeta o sección?»). Variantes:
- `--interactiva`: borde al pasar el mouse.
- `--destacada`: la del saludo del Dashboard.
- `--hundida`: un recuadro dentro de otro.
- `--plana`: sin sombra, para tarjetas que comparten una grilla.

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

### Íconos: `Au.icono`, `Au.ICONOS`, `.au-icono`

Set propio de Aulento (`src/aulento/web/static/icons/aulento-iconos.svg`), de línea fina sobre grilla `24×24`, que hereda `currentColor`. Catálogo visual en `/static/icons/catalogo.html`.

- **En JS (`Au.icono`):**
  - `${Au.icono('guardar')}` devuelve `<svg class="au-icono" aria-hidden="true" focusable="false"><use href="/static/icons/aulento-iconos.svg#i-guardar"></use></svg>`.
  - `Au.icono('alerta', { etiqueta: 'Atención' })` agrega `role="img"` y `aria-label="Atención"` (escapado con `Au.escapar`).
  - `Au.icono('cargando', { clase: 'au-icono--chico au-icono--girando' })` suma clases extra.
  - `Au.ICONOS` lista todos los nombres válidos; pasar un nombre fuera de esa lista lanza un `Error`.
  - Los componentes (`Au.boton`, `Au.cabecera`, `Au.insignia`, `Au.vacio`, `Au.aviso`, `Au.pestanas`, `Au.fila`) aceptan directamente el nombre del ícono en `icono: 'nombre'`.
- **En `index.html`:**
  ```html
  <svg class="au-icono" aria-hidden="true" focusable="false">
    <use href="/static/icons/aulento-iconos.svg#i-NOMBRE"></use>
  </svg>
  ```
- **Clases de tamaño y movimiento:**
  - `.au-icono`: `1em × 1em`, `vertical-align: -0.125em`, `flex-shrink: 0`.
  - `.au-icono--chico`: `0.875em`.
  - `.au-icono--grande`: `1.25em`.
  - `.au-icono--girando`: rotación continua con `--au-duracion-giro`, desactivada con `prefers-reduced-motion: reduce`.
- **Regla de accesibilidad:**
  - **Ícono decorativo junto a texto** (título, pestaña, botón con texto): va con `aria-hidden="true" focusable="false"` (es el comportamiento por defecto de `Au.icono`).
  - **Botón de solo ícono**: el `<svg>` mantiene `aria-hidden="true"` y el `<button>` lleva `aria-label` (y `title` si aplica) describiendo la acción.
  - **Ícono informativo sin texto al lado**: usar `Au.icono('nombre', { etiqueta: 'Descripción' })`, que coloca `role="img"` y `aria-label`.

| Nombre | Para qué |
|---|---|
| `inicio` | Pantalla principal / inicio |
| `cursos` | Cursos y formación |
| `libros` | Biblioteca de libros |
| `lectura` | Lectura activa / capítulos |
| `agenda` | Agenda y calendario semanal |
| `rutas` | Rutas de aprendizaje (motivo DAG) |
| `repaso` | Repaso FSRS y tarjetas para hoy |
| `cerebro` | Segundo cerebro y notas enlazadas (motivo DAG) |
| `indice` | Índice de apuntes, vectores y fragmentos (motivo DAG) |
| `tarjetas` | Mazos y tarjetas de estudio |
| `notas` | Escribir y editar notas |
| `cuaderno` | Cuadernos y libretas |
| `estadisticas` | Métricas y gráficos de avance |
| `examen` | Exámenes y pruebas |
| `objetivo` | Metas y retención objetivo |
| `ajustes` | Configuración y preferencias |
| `cuenta` | Cuenta individual / perfil |
| `cuentas` | Múltiples cuentas / usuarios |
| `plataforma` | Plataformas e instituciones |
| `trabajo` | Trabajo y proyectos |
| `brujula` | Exploración y orientación |
| `grafo` | Grafo de prelaciones o conocimiento (motivo DAG) |
| `modulo` | Módulos y bloques (motivo DAG) |
| `cerrar` | Cerrar modal, panel o cancelar |
| `ok` | Confirmar, completado, válido |
| `agregar` | Crear o sumar un elemento |
| `quitar` | Restar o quitar un elemento |
| `guardar` | Guardar cambios |
| `borrar` | Eliminar |
| `editar` | Editar |
| `copiar` | Copiar al portapapeles |
| `lista` | Lista de tareas o pasos |
| `descargar` | Descargar o exportar |
| `importar` | Importar datos hacia adentro |
| `subir` | Subir archivo o elemento |
| `buscar` | Buscar y filtrar |
| `recargar` | Recargar, sincronizar o reintentar |
| `ver` | Ver detalle o previsualizar |
| `enlace` | Enlazar o copiar vínculo |
| `externo` | Abrir enlace externo |
| `siguiente` | Avanzar / siguiente paso |
| `saltar` | Saltar ítem o paso |
| `pausa` | Pausar sesión o audio |
| `detener` | Detener proceso o temporizador |
| `ordenar` | Ordenar lista |
| `fijar` | Fijar elemento |
| `etiqueta` | Etiquetas y categorías |
| `carpeta` | Carpetas y directorios |
| `documento` | Documentos y apuntes |
| `paquete` | Paquetes y exportaciones |
| `imagen` | Imágenes |
| `video` | Videos y clases grabadas |
| `menu` | Menú de navegación |
| `atajos` | Atajos de teclado |
| `ayuda` | Ayuda y manual |
| `alerta` | Advertencia o atención |
| `cargando` | Estado de carga (centrado en 12,12 para girar) |
| `punto` | Indicador de estado circular (color por clase de texto) |
| `bloqueado` | Elemento bloqueado o con prerequisitos |
| `desbloqueado` | Elemento desbloqueado |
| `seguridad` | Seguridad y privacidad |
| `salud` | Diagnóstico y salud del sistema |
| `vacio` | Estado vacío sin elementos |
| `celebrar` | Celebración y logros recientes |
| `logro` | Trofeo o hito alcanzado |
| `meta` | Meta o fin de ruta |
| `idea` | Sugerencia, consejo o idea |
| `ia` | Asistente y funciones de IA |
| `generar` | Generar contenido con IA |
| `rapido` | Acciones rápidas |
| `empezar` | Iniciar proceso o ruta |
| `analizar` | Análisis profundo |
| `foco` | Modo foco y cronómetro |
| `reloj` | Horarios y duración |
| `pomodoro` | Técnica Pomodoro |
| `descanso` | Pausa o descanso |
| `racha` | Racha de días de estudio |
| `idioma` | Idiomas y práctica lingüística |
| `crecimiento` | Progreso y consolidación |
| `fruto` | Fuente externa o cosecha |
| `premium` | Funciones destacadas |
| `pago` | Facturación y suscripción |
| `voz` | Voz y dictado |
| `audio` | Audio y escucha |
| `celular` | Dispositivo móvil y atajos |
| `computadora` | Escritorio |
| `web` | Web y enlaces en línea |
| `nube` | Sincronización en la nube |
| `conexion` | Conexión y webhooks |
| `integracion` | Integraciones y MCP |
| `clave` | Claves y tokens |
| `apariencia` | Apariencia y estilos |
| `tema-oscuro` | Selector de tema oscuro |
| `tema-claro` | Selector de tema claro |
| `tema-sistema` | Selector de tema según sistema |

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
