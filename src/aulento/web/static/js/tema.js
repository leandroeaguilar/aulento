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

  window.aulentoTema = { leer, guardar, esClaro: () => esClaro(leer()) };

  aplicar(leer());

  if (consultaClaro && consultaClaro.addEventListener) {
    consultaClaro.addEventListener('change', () => {
      if (leer() === 'sistema') aplicar('sistema');
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const selector = document.getElementById('config-tema-select');
    if (selector) selector.value = leer();
  });
})();
