// Tema de la interfaz: oscuro (por defecto), claro o según el sistema.
// Se carga sin defer en el <head> para poner data-tema en <html> antes de pintar (sin parpadeo).
// La preferencia es de este navegador (localStorage); si no se puede leer, queda el tema oscuro.
// Los colores cambian solos: css/paleta.css redefine la paleta según data-tema.
(function () {
  const CLAVE = 'aulento.tema';
  const TEMAS = ['oscuro', 'claro', 'sistema'];
  const consultaClaro = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

  function leer() {
    try {
      const valor = localStorage.getItem(CLAVE);
      return TEMAS.includes(valor) ? valor : 'oscuro';
    } catch (e) {
      return 'oscuro';
    }
  }

  function esClaro(tema) {
    return tema === 'claro' || (tema === 'sistema' && !!consultaClaro && consultaClaro.matches);
  }

  function aplicar(tema) {
    const raiz = document.documentElement;
    if (tema === 'oscuro') raiz.removeAttribute('data-tema');
    else raiz.setAttribute('data-tema', tema);
    document.dispatchEvent(new CustomEvent('aulento:tema', { detail: { tema, claro: esClaro(tema) } }));
  }

  function guardar(tema) {
    if (!TEMAS.includes(tema)) return;
    try {
      localStorage.setItem(CLAVE, tema);
    } catch (e) {
      // Sin almacenamiento (modo privado): el tema se aplica igual, solo por esta sesión.
    }
    aplicar(tema);
  }

  const ETIQUETAS = {
    oscuro: 'oscuro',
    claro: 'claro',
    sistema: 'según el sistema',
  };
  const ICONOS = {
    oscuro: 'tema-oscuro',
    claro: 'tema-claro',
    sistema: 'tema-sistema',
  };

  function siguienteTema(tema) {
    const idx = TEMAS.indexOf(tema);
    return TEMAS[(idx + 1) % TEMAS.length];
  }

  function alternar() {
    const sig = siguienteTema(leer());
    guardar(sig);
    return sig;
  }

  function actualizarBotonTema(tema) {
    const btn = document.getElementById('btn-tema');
    const selector = document.getElementById('config-tema-select');
    const sig = siguienteTema(tema);
    const desc = `Tema: ${ETIQUETAS[tema] || tema}. Cambiar a ${ETIQUETAS[sig] || sig}`;

    if (btn) {
      btn.setAttribute('aria-label', desc);
      btn.title = desc;
      const icono = btn.querySelector('#btn-tema-icono') || btn;
      const nombreIcono = ICONOS[tema] || 'tema-oscuro';
      if (typeof Au !== 'undefined' && Au.icono) {
        icono.innerHTML = Au.icono(nombreIcono);
      } else {
        icono.innerHTML = `<svg class="au-icono" aria-hidden="true" focusable="false"><use href="/static/icons/aulento-iconos.svg#i-${nombreIcono}"></use></svg>`;
      }
    }
    if (selector && selector.value !== tema) {
      selector.value = tema;
    }
  }

  window.aulentoTema = { leer, guardar, alternar, actualizarBotonTema, esClaro: () => esClaro(leer()) };

  aplicar(leer());

  if (consultaClaro && consultaClaro.addEventListener) {
    consultaClaro.addEventListener('change', () => {
      if (leer() === 'sistema') aplicar('sistema');
    });
  }

  document.addEventListener('aulento:tema', (e) => {
    const tema = (e.detail && e.detail.tema) || leer();
    actualizarBotonTema(tema);
  });

  document.addEventListener('DOMContentLoaded', () => {
    const tema = leer();
    const selector = document.getElementById('config-tema-select');
    if (selector) selector.value = tema;
    actualizarBotonTema(tema);
  });
})();
