/* 072: componentes de Aulento. Funciones que arman HTML, acciones delegadas y el modal.
 * Script clásico, cargado antes de app.js: no depende de nada de app.js.
 * Catálogo y reglas en docs/COMPONENTES.md.
 *
 * Reglas:
 * - Todo texto se escapa. El HTML confiable entra solo por parámetros cuyo nombre termina en `Html`.
 * - Nada de onclick en el marcado nuevo: `data-accion="nombre"` y `Au.acciones.registrar('nombre', fn)`.
 */
(function () {
  'use strict';

  const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  function escapar(valor) {
    if (valor === null || valor === undefined) return '';
    return String(valor).replace(/[&<>"']/g, (c) => ESCAPES[c]);
  }

  /** Atributos extra: {id: 'x', 'data-libro': 3}. Los valores se escapan; null/false se omiten; true deja el atributo solo. */
  function atributos(attrs) {
    if (!attrs) return '';
    return Object.entries(attrs)
      .filter(([, v]) => v !== null && v !== undefined && v !== false)
      .map(([k, v]) => {
        if (!/^[a-zA-Z_:][a-zA-Z0-9_:.-]*$/.test(k)) throw new Error(`Atributo inválido: ${k}`);
        if (/^on/i.test(k)) throw new Error(`Atributo inválido: ${k} (usá data-accion, no manejadores en línea)`);
        return v === true ? ` ${k}` : ` ${k}="${escapar(v)}"`;
      })
      .join('');
  }

  /** La URL si es http(s), mailto, relativa (/) o un ancla (#); si no, '#'. No escapa: eso lo hace el atributo. */
  function urlSegura(url) {
    if (!url || typeof url !== 'string') return '#';
    const limpia = url.trim();
    return /^(https?:\/\/|\/|#|mailto:)/i.test(limpia) ? limpia : '#';
  }

  function clases(...lista) {
    return lista.filter(Boolean).join(' ');
  }

  /** Atributos de acción delegada: {accion: 'borrar-libro', datos: {libro: 3}} → data-accion y data-*. */
  function atributosDeAccion(accion, datos) {
    if (!accion) return {};
    const attrs = { 'data-accion': accion };
    Object.entries(datos || {}).forEach(([k, v]) => {
      attrs[`data-${k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())}`] = v;
    });
    return attrs;
  }

  const TONOS = ['primario', 'exito', 'alerta', 'peligro'];
  function tono(base, valor) {
    return TONOS.includes(valor) ? `${base}--${valor}` : '';
  }

  // ---------- Íconos ----------

  const ICONOS = Object.freeze([
    'inicio', 'cursos', 'libros', 'lectura', 'agenda', 'rutas',
    'repaso', 'cerebro', 'indice', 'tarjetas', 'notas', 'cuaderno',
    'estadisticas', 'examen', 'objetivo', 'ajustes', 'cuenta', 'cuentas',
    'plataforma', 'trabajo', 'brujula', 'grafo', 'modulo',
    'cerrar', 'ok', 'agregar', 'quitar', 'guardar', 'borrar', 'editar',
    'copiar', 'lista', 'descargar', 'importar', 'subir', 'buscar',
    'recargar', 'ver', 'enlace', 'externo', 'siguiente', 'saltar',
    'pausa', 'detener', 'ordenar', 'fijar', 'etiqueta', 'carpeta',
    'documento', 'paquete', 'imagen', 'video', 'menu', 'atajos', 'ayuda',
    'alerta', 'cargando', 'punto', 'bloqueado', 'desbloqueado', 'seguridad',
    'salud', 'vacio', 'celebrar', 'logro', 'meta', 'idea',
    'ia', 'generar', 'rapido', 'empezar', 'analizar', 'foco', 'reloj',
    'pomodoro', 'descanso', 'racha', 'idioma', 'crecimiento', 'fruto',
    'premium', 'pago',
    'voz', 'audio', 'celular', 'computadora', 'web', 'nube',
    'conexion', 'integracion', 'clave', 'apariencia',
    'tema-oscuro', 'tema-claro', 'tema-sistema',
  ]);
  const ICONOS_SET = new Set(ICONOS);
  const ICONO_SVG_RE = /^<svg class="au-icono(?: [a-z0-9_-]+)*" (?:aria-hidden="true"|role="img" aria-label="[^"<>]*") focusable="false"><use href="\/static\/icons\/aulento-iconos\.svg#i-([a-z-]+)"><\/use><\/svg>$/;

  /** Devuelve el marcado SVG del ícono del sprite; si no existe en Au.ICONOS lanza Error. */
  function icono(nombre, { etiqueta, clase } = {}) {
    if (!ICONOS_SET.has(nombre)) throw new Error(`Ícono desconocido: ${nombre}`);
    const claseFinal = escapar(clases('au-icono', clase));
    const aria = etiqueta
      ? `role="img" aria-label="${escapar(etiqueta)}"`
      : 'aria-hidden="true"';
    return `<svg class="${claseFinal}" ${aria} focusable="false"><use href="/static/icons/aulento-iconos.svg#i-${nombre}"></use></svg>`;
  }

  function renderIcono(valor) {
    if (!valor) return '';
    if (typeof valor === 'string' && ICONOS_SET.has(valor)) return icono(valor);
    if (typeof valor === 'string') {
      const m = ICONO_SVG_RE.exec(valor);
      if (m && ICONOS_SET.has(m[1])) return valor;
    }
    return escapar(valor);
  }

  // ---------- Componentes ----------

  function insignia({ texto, tono: t, icono: ic, mono = false, attrs } = {}) {
    return `<span class="${clases('au-insignia', tono('au-insignia', t), mono && 'au-insignia--mono')}"${atributos(attrs)}>`
      + `${ic ? `<span aria-hidden="true">${renderIcono(ic)}</span>` : ''}${escapar(texto)}</span>`;
  }

  const VARIANTES_BOTON = ['primario', 'secundario', 'peligro', 'fantasma'];

  function boton({ texto, variante = 'secundario', icono: ic, soloIcono = false, etiqueta, chico = false, bloque = false,
    accion, datos, tipo = 'button', deshabilitado = false, href, attrs } = {}) {
    if (!VARIANTES_BOTON.includes(variante)) throw new Error(`Variante de botón desconocida: ${variante}`);
    if (soloIcono && !etiqueta) throw new Error('Un botón de solo ícono necesita `etiqueta` (aria-label)');
    const clase = clases('au-boton', variante !== 'secundario' && `au-boton--${variante}`,
      soloIcono && 'au-boton--icono', chico && 'au-boton--chico', bloque && 'au-boton--bloque');
    const contenido = soloIcono
      ? `<span aria-hidden="true">${renderIcono(ic)}</span>`
      : `${ic ? `<span aria-hidden="true">${renderIcono(ic)}</span>` : ''}<span>${escapar(texto)}</span>`;
    const comunes = {
      ...atributosDeAccion(accion, datos),
      'aria-label': soloIcono ? etiqueta : null,
      title: etiqueta || null,
      ...attrs,
    };
    if (href) {
      return `<a class="${clase}" href="${escapar(urlSegura(href))}"${atributos(comunes)}>${contenido}</a>`;
    }
    return `<button type="${escapar(tipo)}" class="${clase}"${atributos({ ...comunes, disabled: deshabilitado })}>${contenido}</button>`;
  }

  /** Cabecera de tarjeta. `accionesHtml` es una lista de HTML ya armado con Au.boton (confiable). */
  function cabecera({ titulo, subtitulo, icono: ic, insignias = [], accionesHtml = [], conLinea = false, nivel = 2, idTitulo } = {}) {
    const h = nivel === 3 ? 'h3' : 'h2';
    return `<div class="${clases('au-cabecera', conLinea && 'au-cabecera--con-linea')}">`
      + '<div class="au-cabecera__principal">'
      + (ic ? `<span class="au-cabecera__icono" aria-hidden="true">${renderIcono(ic)}</span>` : '')
      + '<div class="au-cabecera__textos">'
      + `<${h} class="au-cabecera__titulo"${atributos({ id: idTitulo })}><span>${escapar(titulo)}</span>${insignias.map((i) => insignia(i)).join('')}</${h}>`
      + (subtitulo ? `<p class="au-cabecera__subtitulo">${escapar(subtitulo)}</p>` : '')
      + '</div></div>'
      + (accionesHtml.length ? `<div class="au-cabecera__acciones">${accionesHtml.join('')}</div>` : '')
      + '</div>';
  }

  function tarjeta({ cabecera: cab, cuerpoHtml = '', variante, attrs } = {}) {
    const clase = clases('au-tarjeta', variante && `au-tarjeta--${variante}`);
    return `<section class="${clase}"${atributos(attrs)}>${cab ? cabecera(cab) : ''}${cuerpoHtml}</section>`;
  }

  function kpi({ etiqueta, valor, unidad, detalle, attrs } = {}) {
    return `<div class="au-kpi"${atributos(attrs)}>`
      + `<span class="au-kpi__etiqueta">${escapar(etiqueta)}</span>`
      + `<span class="au-kpi__valor">${escapar(valor)}${unidad ? `<span class="au-kpi__unidad">${escapar(unidad)}</span>` : ''}</span>`
      + (detalle ? `<span class="au-kpi__detalle">${escapar(detalle)}</span>` : '')
      + '</div>';
  }

  function progreso({ valor = 0, maximo = 100, tono: t, etiqueta } = {}) {
    const max = Number(maximo) > 0 ? Number(maximo) : 100;
    const val = Math.max(0, Math.min(max, Number(valor) || 0));
    return `<progress class="${clases('au-progreso', t === 'exito' && 'au-progreso--exito', t === 'alerta' && 'au-progreso--alerta', t === 'peligro' && 'au-progreso--peligro')}" value="${escapar(val)}" max="${escapar(max)}"${atributos({ 'aria-label': etiqueta })}></progress>`;
  }

  function vacio({ icono: ic = 'vacio', titulo, texto, accionHtml = '' } = {}) {
    return '<div class="au-vacio">'
      + `<span class="au-vacio__icono" aria-hidden="true">${renderIcono(ic)}</span>`
      + (titulo ? `<p class="au-vacio__titulo">${escapar(titulo)}</p>` : '')
      + (texto ? `<p class="au-vacio__texto">${escapar(texto)}</p>` : '')
      + accionHtml
      + '</div>';
  }

  function aviso({ titulo, texto, tono: t, icono: ic, rol } = {}) {
    const role = rol || (t === 'peligro' || t === 'alerta' ? 'alert' : 'status');
    return `<div class="${clases('au-aviso', tono('au-aviso', t))}" role="${escapar(role)}">`
      + (ic ? `<span class="au-aviso__icono" aria-hidden="true">${renderIcono(ic)}</span>` : '')
      + '<div class="au-aviso__contenido">'
      + (titulo ? `<strong class="au-aviso__titulo">${escapar(titulo)}</strong>` : '')
      + (texto ? `<span>${escapar(texto)}</span>` : '')
      + '</div></div>';
  }

  function campo({ id, etiqueta, tipo = 'text', valor = '', placeholder, opciones, ayuda, error, attrs } = {}) {
    if (!id) throw new Error('Un campo necesita `id` para enlazar su etiqueta');
    const descripcion = error ? `${id}-error` : (ayuda ? `${id}-ayuda` : null);
    const comunes = atributos({ id, name: id, placeholder, 'aria-describedby': descripcion, 'aria-invalid': error ? 'true' : null, ...attrs });
    let control;
    if (opciones) {
      control = `<select class="au-campo__control"${comunes}>`
        + opciones.map((o) => `<option value="${escapar(o.valor)}"${String(o.valor) === String(valor) ? ' selected' : ''}>${escapar(o.texto)}</option>`).join('')
        + '</select>';
    } else if (tipo === 'textarea') {
      control = `<textarea class="au-campo__control"${comunes}>${escapar(valor)}</textarea>`;
    } else {
      control = `<input type="${escapar(tipo)}" class="au-campo__control" value="${escapar(valor)}"${comunes}>`;
    }
    return '<div class="au-campo">'
      + `<label class="au-campo__etiqueta" for="${escapar(id)}">${escapar(etiqueta)}</label>`
      + control
      + (error ? `<span class="au-campo__error" id="${escapar(id)}-error">${escapar(error)}</span>`
        : (ayuda ? `<span class="au-campo__ayuda" id="${escapar(id)}-ayuda">${escapar(ayuda)}</span>` : ''))
      + '</div>';
  }

  /** Pestañas: items [{valor, texto, icono}], `activa` = valor elegido, `accion` = acción delegada que recibe data-valor. */
  function pestanas({ items = [], activa, accion, etiqueta } = {}) {
    return `<div class="au-pestanas" role="tablist"${atributos({ 'aria-label': etiqueta })}>`
      + items.map((it) => {
        const sel = String(it.valor) === String(activa);
        return `<button type="button" role="tab" class="au-pestanas__boton" aria-selected="${sel}"`
          + `${atributos(atributosDeAccion(accion, { valor: it.valor }))}>`
          + `${it.icono ? `<span aria-hidden="true">${renderIcono(it.icono)}</span> ` : ''}${escapar(it.texto)}</button>`;
      }).join('')
      + '</div>';
  }

  function fila({ titulo, detalle, icono: ic, activa = false, accion, datos, accionesHtml = '', attrs } = {}) {
    const etiqueta = accion ? 'button' : 'div';
    const tipo = accion ? ' type="button"' : '';
    return `<${etiqueta}${tipo} class="${clases('au-fila', activa && 'au-fila--activa')}"`
      + `${atributos({ ...atributosDeAccion(accion, datos), 'aria-current': activa ? 'true' : null, ...attrs })}>`
      + (ic ? `<span aria-hidden="true">${renderIcono(ic)}</span>` : '')
      + `<span class="au-fila__contenido"><span class="au-fila__titulo">${escapar(titulo)}</span>`
      + (detalle ? `<span class="au-fila__detalle">${escapar(detalle)}</span>` : '')
      + '</span>'
      + (accionesHtml ? `<span class="au-fila__acciones">${accionesHtml}</span>` : '')
      + `</${etiqueta}>`;
  }

  // ---------- Acciones delegadas ----------

  const registradas = new Map();

  const acciones = {
    /** fn(elemento, dataset, evento) */
    registrar(nombre, fn) {
      if (typeof fn !== 'function') throw new Error(`La acción ${nombre} necesita una función`);
      if (registradas.has(nombre)) throw new Error(`La acción ${nombre} ya está registrada`);
      registradas.set(nombre, fn);
    },
    existe(nombre) {
      return registradas.has(nombre);
    },
  };

  function despachar(evento) {
    const objetivo = evento.target instanceof Element ? evento.target : null;
    const el = objetivo ? objetivo.closest('[data-accion], [data-sin-accion]') : null;
    if (!el || el.hasAttribute('data-sin-accion')) return;
    // Un enlace o control propio dentro de un elemento con acción (una tarjeta clickeable) hace lo suyo y nada más
    const interactivo = objetivo.closest('a[href], button, input, select, textarea, label');
    if (interactivo && interactivo !== el && el.contains(interactivo)) return;
    // En un formulario, la acción va en el submit; en un select o input, en el change.
    // Un campo con data-al-escribir (un buscador) la dispara en cada tecla (input) y no al salir (change)
    const esCampo = el.matches('select, input, textarea');
    const alEscribir = esCampo && el.hasAttribute('data-al-escribir');
    if (evento.type === 'click' && (esCampo || el.tagName === 'FORM')) return;
    if (evento.type === 'change' && (!esCampo || alEscribir)) return;
    if (evento.type === 'input' && !alEscribir) return;
    if (evento.type === 'submit' && el.tagName !== 'FORM') return;
    const fn = registradas.get(el.dataset.accion);
    if (!fn) {
      console.warn(`Acción sin registrar: ${el.dataset.accion}`);
      return;
    }
    if (evento.type === 'submit' || el.tagName === 'A') evento.preventDefault();
    fn(el, el.dataset, evento);
  }

  ['click', 'change', 'submit', 'input'].forEach((tipo) => document.addEventListener(tipo, despachar));

  // ---------- Modal ----------
  /* Marcado:
   * <div id="x" class="au-modal" hidden role="dialog" aria-modal="true" aria-labelledby="x-titulo">
   *   <div class="au-modal__caja"> <div class="au-modal__cabecera"><h2 id="x-titulo" class="au-modal__titulo">…</h2>
   *     <button … data-accion="au-cerrar-modal" aria-label="Cerrar">✕</button></div> … </div></div>
   */

  const abiertos = []; // pila de {id, disparador}
  const inertizados = new Set();

  function sincronizarInert() {
    if (!abiertos.length) {
      for (const el of inertizados) {
        el.inert = false;
      }
      inertizados.clear();
      return;
    }
    const topId = abiertos[abiertos.length - 1].id;
    const topEl = document.getElementById(topId);
    if (!topEl) return;

    const ancestros = new Set();
    let curr = topEl;
    while (curr && curr !== document.body) {
      ancestros.add(curr);
      curr = curr.parentElement;
    }

    for (const el of inertizados) {
      if (ancestros.has(el)) {
        el.inert = false;
        inertizados.delete(el);
      }
    }

    let actual = topEl;
    while (actual && actual !== document.body && actual.parentElement) {
      actual.inert = false;
      inertizados.delete(actual);
      for (const hermano of actual.parentElement.children) {
        if (ancestros.has(hermano)) continue;
        if (hermano.tagName === 'SCRIPT' || hermano.id === 'toast-container') continue;
        hermano.inert = true;
        inertizados.add(hermano);
      }
      actual = actual.parentElement;
    }
  }

  const modal = {
    abrir(id, disparador) {
      const el = document.getElementById(id);
      if (!el) throw new Error(`No existe el modal #${id}`);
      const titulo = el.getAttribute('aria-labelledby');
      if (el.getAttribute('role') !== 'dialog' || el.getAttribute('aria-modal') !== 'true' || !titulo || !document.getElementById(titulo)) {
        throw new Error(`El modal #${id} necesita role="dialog", aria-modal="true" y aria-labelledby a su título`);
      }
      if (!el.hidden) return;
      el.hidden = false;
      abiertos.push({ id, disparador: disparador || document.activeElement });
      // Encima del anterior: con el mismo z-index mandaría el orden del DOM, y un modal abierto desde otro quedaba atrás
      el.style.zIndex = String(50 + abiertos.length);
      document.body.classList.add('au-modal-abierto');
      sincronizarInert();
      // El primero que se ve: un botón dentro de un bloque oculto no recibe el foco y lo dejaba fuera del modal.
      // `a[href]` y no `[href]`: el <use href> de los íconos también tiene href y tampoco se puede enfocar.
      const visible = (nodo) => nodo.getClientRects().length > 0;
      const primero = (selector) => Array.from(el.querySelectorAll(selector)).find(visible);
      const foco = primero('[autofocus]')
        || primero('input, select, textarea, button:not([data-accion="au-cerrar-modal"])')
        || primero('button, a[href], [tabindex]:not([tabindex="-1"])');
      if (foco) foco.focus();
    },
    cerrar(id) {
      const i = abiertos.map((m) => m.id).lastIndexOf(id);
      const el = document.getElementById(id);
      if (!el || el.hidden) return;
      el.hidden = true;
      el.style.zIndex = '';
      const [{ disparador } = {}] = i >= 0 ? abiertos.splice(i, 1) : [];
      if (!abiertos.length) document.body.classList.remove('au-modal-abierto');
      sincronizarInert();
      if (disparador && typeof disparador.focus === 'function' && document.contains(disparador)) disparador.focus();
      // Cierre por Esc, ✕, fondo o código: la limpieza de cada pantalla (resetear un form, cortar un audio) va acá
      el.dispatchEvent(new CustomEvent('au:cerrado'));
    },
    abierto(id) {
      const el = document.getElementById(id);
      return !!el && !el.hidden;
    },
  };

  acciones.registrar('au-cerrar-modal', (el) => {
    const capa = el.closest('.au-modal');
    if (capa) modal.cerrar(capa.id);
  });

  // Tocar el fondo (la capa, no la caja) cierra
  document.addEventListener('click', (e) => {
    // data-sin-cierre: un modal de progreso (generando…) no se cierra a mano, solo desde el código
    if (e.target instanceof Element && e.target.classList.contains('au-modal') && !e.target.hidden
        && !e.target.hasAttribute('data-sin-cierre')) {
      modal.cerrar(e.target.id);
    }
  });

  // Esc cierra el de arriba. En captura y con stopImmediatePropagation: los atajos viejos (también en document)
  // no deben cerrar además el modal o el menú que quedó debajo
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && abiertos.length) {
      e.stopImmediatePropagation();
      e.preventDefault();
      const arriba = document.getElementById(abiertos[abiertos.length - 1].id);
      if (!arriba || !arriba.hasAttribute('data-sin-cierre')) modal.cerrar(abiertos[abiertos.length - 1].id);
    }
  }, true);

  window.Au = Object.freeze({
    escapar, atributos, clases, urlSegura,
    ICONOS, icono,
    insignia, boton, cabecera, tarjeta, kpi, progreso, vacio, aviso, campo, pestanas, fila,
    acciones, modal,
  });
})();
