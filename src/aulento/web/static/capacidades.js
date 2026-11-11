// Gestor de capacidades y textos por versión (ADR 017, Feature 056)
(function () {
  'use strict';

  var modoInicial = (document.body && document.body.dataset && document.body.dataset.modo) || 'local';

  window.SE_CAPACIDADES = {
    modo: modoInicial,
    capacidades: {
      carpeta_local: modoInicial === 'local',
      mcp_escritorio: modoInicial === 'local',
      mcp_web: false,
      google_libros: false,
      atajo_libros: false,
    },
    textos: {},
  };

  window.seTiene = function (nombre) {
    if (!window.SE_CAPACIDADES || !window.SE_CAPACIDADES.capacidades) {
      return false;
    }
    return Boolean(window.SE_CAPACIDADES.capacidades[nombre]);
  };

  function aplicarCapacidadesYTextos() {
    var textos = (window.SE_CAPACIDADES && window.SE_CAPACIDADES.textos) || {};
    var elementosTexto = document.querySelectorAll('[data-texto]');
    elementosTexto.forEach(function (el) {
      var clave = el.getAttribute('data-texto');
      if (clave && textos[clave] !== undefined) {
        el.textContent = textos[clave];
      }
    });

    var elementosRequeridos = document.querySelectorAll('[data-requiere]');
    elementosRequeridos.forEach(function (el) {
      var capacidad = el.getAttribute('data-requiere');
      if (capacidad) {
        // Clase propia: no pisa el 'hidden' que maneja app.js por otros motivos
        el.classList.toggle('se-sin-capacidad', !window.seTiene(capacidad));
      }
    });
  }

  var estilo = document.createElement('style');
  estilo.textContent = '.se-sin-capacidad { display: none !important; }';
  document.head.appendChild(estilo);

  window.aplicarCapacidades = aplicarCapacidadesYTextos;

  async function inicializarCapacidades() {
    try {
      var res = await fetch('/api/capacidades');
      if (res.ok) {
        var data = await res.json();
        window.SE_CAPACIDADES = data;
      }
    } catch (err) {
      // Si la ruta falla, usa document.body.dataset.modo y deja los textos propios del HTML
      console.warn('No se pudieron obtener las capacidades del servidor:', err);
    } finally {
      aplicarCapacidadesYTextos();
      document.dispatchEvent(
        new CustomEvent('capacidades-listas', {
          detail: window.SE_CAPACIDADES,
        })
      );
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inicializarCapacidades);
  } else {
    inicializarCapacidades();
  }
})();
