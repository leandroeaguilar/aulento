// ======================================================================
// CONEXIÓN MCP REMOTO EN LA WEB (Feature 058)
// Servidor Streamable HTTP en /mcp con autenticación por Bearer Token.
// Soporta Claude Desktop, Claude Code y Cursor con headers.
// ======================================================================

(function () {
  'use strict';

  var mcpRemoto = {
    cliente: 'claude-desktop',
    tokenNuevo: null,
    tokens: [],
    snippets: [],
  };

  var EJEMPLOS_PEDIDOS = [
    'Listá mis rutas de aprendizaje de Aulento y decime qué temas todavía no tienen clase.',
    'Creá la clase completa del primer tema sin clase de mi ruta y guardala en Aulento.',
    'Repasemos juntos mis tarjetas de inglés que tocan hoy.',
  ];

  function escapeHtml(texto) {
    if (!texto) return '';
    return String(texto)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function urlRealMcp() {
    return window.location.origin + '/mcp';
  }

  function snippetMcp(texto) {
    mcpRemoto.snippets.push(texto);
    var i = mcpRemoto.snippets.length - 1;
    return (
      '<div class="relative group">' +
      '<pre class="bg-slate-950 border border-slate-800 rounded-xl p-4 pr-24 text-xs text-sky-200 font-mono whitespace-pre-wrap break-all">' +
      escapeHtml(texto) +
      '</pre>' +
      '<button type="button" onclick="window.copiarSnippetMcpRemoto(' +
      i +
      ', this)" class="absolute top-2.5 right-2.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold transition">Copiar</button>' +
      '</div>'
    );
  }

  window.copiarSnippetMcpRemoto = async function (i, boton) {
    try {
      await navigator.clipboard.writeText(mcpRemoto.snippets[i]);
      if (boton) {
        var textoOriginal = boton.textContent;
        boton.textContent = '✓ Copiado';
        setTimeout(function () {
          boton.textContent = textoOriginal;
        }, 1800);
      }
    } catch (e) {
      if (window.showToast) {
        window.showToast('No se pudo copiar: seleccioná el texto y copialo a mano.', 'warning');
      }
    }
  };

  window.elegirClienteMcpRemoto = function (cliente) {
    mcpRemoto.cliente = cliente;
    renderMcpRemoto();
  };

  function pasosCliente(url, token) {
    var jsonConfig = JSON.stringify(
      {
        mcpServers: {
          'aulento': {
            type: 'http',
            url: url,
            headers: {
              Authorization: 'Bearer ' + token,
            },
          },
        },
      },
      null,
      2
    );

    var claudeCode =
      'claude mcp add --transport http --scope user aulento ' +
      url +
      ' --header "Authorization: Bearer ' +
      token +
      '"';

    var pasos = {
      'claude-desktop':
        '<p class="text-sm text-slate-300">1. En Claude Desktop abrí <b>Configuración → Desarrollador → Editar configuración</b> (archivo <code class="text-sky-300">claude_desktop_config.json</code>).</p>' +
        '<p class="text-sm text-slate-300">2. Pegá esta configuración. Si ya tenés otros servidores, sumá la entrada <code class="text-sky-300">"aulento"</code> dentro de <code class="text-sky-300">"mcpServers"</code>:</p>' +
        snippetMcp(jsonConfig) +
        '<p class="text-sm text-slate-300">3. Cerrá Claude Desktop del todo y volvelo a abrir. Vas a ver <b>aulento</b> disponible.</p>',
      'claude-code':
        '<p class="text-sm text-slate-300">1. En una terminal, corré este comando (conecta Aulento a tu usuario):</p>' +
        snippetMcp(claudeCode) +
        '<p class="text-sm text-slate-300">2. Abrí Claude Code y ejecutá <code class="text-sky-300">/mcp</code> para confirmar la conexión.</p>',
      cursor:
        '<p class="text-sm text-slate-300">1. En Cursor abrí <b>Settings → MCP → Add new global MCP server</b> (en <code class="text-sky-300">~/.cursor/mcp.json</code>).</p>' +
        '<p class="text-sm text-slate-300">2. Pegá este bloque y guardá:</p>' +
        snippetMcp(jsonConfig) +
        '<p class="text-sm text-slate-300">3. Cursor va a conectarse a tu Aulento remoto.</p>',
    };

    return pasos[mcpRemoto.cliente] || pasos['claude-desktop'];
  }

  function filaDeToken(t) {
    var fecha = function (iso) {
      return iso ? new Date(iso).toLocaleString() : '—';
    };
    var estado = t.revocado_en
      ? '<span class="text-rose-300">Revocado</span>'
      : '<span class="text-emerald-300">Activo</span>';
    var accion = t.revocado_en
      ? ''
      : '<button type="button" onclick="window.revocarTokenMcpRemoto(' +
        t.id +
        ')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-rose-900 text-rose-300 text-xs font-semibold transition">Revocar</button>';

    return (
      '<tr class="border-t border-slate-800">' +
      '<td class="py-2 pr-3 text-slate-200">' +
      escapeHtml(t.nombre || 'Sin nombre') +
      '</td>' +
      '<td class="py-2 pr-3 text-slate-400">' +
      fecha(t.creado_en) +
      '</td>' +
      '<td class="py-2 pr-3 text-slate-400">' +
      fecha(t.ultimo_uso) +
      '</td>' +
      '<td class="py-2 pr-3">' +
      estado +
      '</td>' +
      '<td class="py-2 text-right">' +
      accion +
      '</td>' +
      '</tr>'
    );
  }

  window.crearTokenMcpRemoto = async function () {
    var input = document.getElementById('mcp-remoto-token-nombre');
    var nombre = input ? input.value.trim() : '';
    try {
      var res = await fetch('/api/mcp/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre: nombre || undefined }),
      });
      if (res.status === 403) {
        var errData = await res.json().catch(function () { return {}; });
        var msj = errData.detail || 'Una cuenta compartida no puede crear tokens MCP.';
        if (window.showToast) window.showToast(msj, 'warning');
        else alert(msj);
        return;
      }
      if (!res.ok) throw new Error('Error al crear el token MCP.');
      var creado = await res.json();
      mcpRemoto.tokenNuevo = creado;
      if (input) input.value = '';
      await cargarTokens();
      renderMcpRemoto();
    } catch (e) {
      if (window.showToast) window.showToast(e.message, 'error');
      else alert(e.message);
    }
  };

  window.revocarTokenMcpRemoto = async function (id) {
    try {
      var res = await fetch('/api/mcp/tokens/' + id, { method: 'DELETE' });
      if (!res.ok) throw new Error('Error al revocar el token.');
      if (mcpRemoto.tokenNuevo && mcpRemoto.tokenNuevo.id === id) {
        mcpRemoto.tokenNuevo = null;
      }
      await cargarTokens();
      renderMcpRemoto();
    } catch (e) {
      if (window.showToast) window.showToast(e.message, 'error');
      else alert(e.message);
    }
  };

  async function cargarTokens() {
    try {
      var res = await fetch('/api/mcp/tokens');
      mcpRemoto.tokens = res.ok ? await res.json() : [];
    } catch (e) {
      mcpRemoto.tokens = [];
    }
  }

  async function renderMcpRemoto() {
    var contenedor = document.getElementById('mcp-remoto-body');
    if (!contenedor) return;

    mcpRemoto.snippets = [];
    var url = urlRealMcp();

    var esDemo =
      window.state &&
      window.state.currentUser &&
      window.state.currentUser.compartida === true;

    var tokenActivo = mcpRemoto.tokenNuevo ? mcpRemoto.tokenNuevo.token : '<TU_TOKEN>';

    var pestana = function (id, texto) {
      var activo = mcpRemoto.cliente === id;
      return (
        '<button type="button" onclick="window.elegirClienteMcpRemoto(\'' +
        id +
        '\')" class="px-3.5 py-2 rounded-xl text-xs font-bold transition ' +
        (activo
          ? 'bg-violet-600 text-white'
          : 'bg-slate-800 text-slate-300 hover:bg-slate-700') +
        '">' +
        texto +
        '</button>'
      );
    };

    var avisoOAuth =
      '<div class="bg-amber-950/30 border border-amber-700/50 rounded-2xl p-4 flex items-start gap-3">' +
      '<span class="text-amber-400 text-lg shrink-0">ℹ️</span>' +
      '<div class="text-xs text-amber-200/90 leading-relaxed space-y-1">' +
      '<p class="font-bold text-amber-200">Conectores web y OAuth</p>' +
      '<p>Los conectores web que piden OAuth (como claude.ai o ChatGPT) todavía no están soportados. Podés conectar clientes de escritorio y terminal que aceptan encabezados HTTP Bearer (Claude Desktop, Claude Code, Cursor).</p>' +
      '</div>' +
      '</div>';

    var tarjetaUrl =
      '<div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 space-y-4 shadow-xl">' +
      '<div>' +
      '<h4 class="font-bold text-white text-base">URL del servidor MCP</h4>' +
      '<p class="text-xs text-slate-400">Endpoint HTTPS público listo para conectar tu asistente por Streamable HTTP.</p>' +
      '</div>' +
      snippetMcp(url) +
      '</div>';

    var avisoDemo =
      '<div class="bg-amber-950/40 border border-amber-700/50 rounded-2xl px-5 py-4 text-sm text-amber-200">' +
      '<p class="font-semibold">🔒 Esta cuenta es compartida: acá no se pueden crear tokens MCP.</p>' +
      '<p class="text-amber-200/80 text-xs mt-1">La usan varias personas. En tu propia cuenta podés crear tokens personales y conectar tu asistente.</p>' +
      '</div>';

    var nuevo = mcpRemoto.tokenNuevo
      ? '<div class="bg-emerald-950/40 border-2 border-emerald-600/60 rounded-2xl p-4 space-y-2">' +
        '<p class="text-sm font-bold text-emerald-200">Tu token «' +
        escapeHtml(mcpRemoto.tokenNuevo.nombre || 'Sin nombre') +
        '». Copialo ahora: no se vuelve a mostrar.</p>' +
        snippetMcp(mcpRemoto.tokenNuevo.token) +
        '</div>'
      : '';

    var activos = mcpRemoto.tokens.filter(function (t) {
      return !t.revocado_en;
    });

    var seccionTokens = esDemo
      ? avisoDemo
      : '<div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 space-y-4 shadow-xl">' +
        '<div>' +
        '<h4 class="font-bold text-white text-base">Tokens de acceso MCP</h4>' +
        '<p class="text-xs text-slate-400">Creá un Bearer Token para autenticar a tu asistente. Podés revocarlo cuando quieras.</p>' +
        '</div>' +
        '<div class="flex flex-col sm:flex-row gap-2">' +
        '<input id="mcp-remoto-token-nombre" type="text" maxlength="64" placeholder="Nombre del token (ej. Claude Code notebook)" ' +
        'class="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500">' +
        '<button type="button" onclick="window.crearTokenMcpRemoto()" class="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-bold transition">Crear token</button>' +
        '</div>' +
        nuevo +
        (mcpRemoto.tokens.length
          ? '<div class="overflow-x-auto pt-2">' +
            '<p class="text-xs font-semibold text-slate-400 mb-1">Tus tokens (' +
            activos.length +
            ' activos)</p>' +
            '<table class="w-full text-xs"><thead><tr class="text-left text-slate-500">' +
            '<th class="py-1 pr-3">Nombre</th><th class="py-1 pr-3">Creado</th><th class="py-1 pr-3">Último uso</th><th class="py-1 pr-3">Estado</th><th></th>' +
            '</tr></thead><tbody>' +
            mcpRemoto.tokens.map(filaDeToken).join('') +
            '</tbody></table></div>'
          : '') +
        '</div>';

    var tarjetaConfig =
      '<div class="bg-slate-900 border border-violet-800/50 rounded-3xl p-6 sm:p-8 space-y-4 shadow-xl">' +
      '<div class="flex flex-wrap items-center justify-between gap-3">' +
      '<div>' +
      '<h4 class="font-bold text-white text-base">Configuración para tu asistente</h4>' +
      '<p class="text-xs text-slate-400">Elegí tu cliente y pegá la configuración con tu token en encabezados Authorization.</p>' +
      '</div>' +
      '<div class="flex gap-2">' +
      pestana('claude-desktop', 'Claude Desktop') +
      pestana('claude-code', 'Claude Code') +
      pestana('cursor', 'Cursor') +
      '</div>' +
      '</div>' +
      pasosCliente(url, tokenActivo) +
      '</div>';

    var tarjetaEjemplos =
      '<div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 space-y-3 shadow-xl">' +
      '<h4 class="font-bold text-white text-base">Probalo</h4>' +
      '<p class="text-xs text-slate-400">Con el asistente conectado, pedile por ejemplo:</p>' +
      EJEMPLOS_PEDIDOS.map(snippetMcp).join('') +
      '</div>';

    contenedor.innerHTML =
      tarjetaUrl +
      avisoOAuth +
      seccionTokens +
      tarjetaConfig +
      tarjetaEjemplos;
  }

  async function inicializar() {
    if (window.seTiene && !window.seTiene('mcp_web')) {
      return;
    }
    await cargarTokens();
    renderMcpRemoto();
  }

  document.addEventListener('capacidades-listas', function () {
    if (window.seTiene && window.seTiene('mcp_web')) {
      inicializar();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inicializar);
  } else {
    inicializar();
  }
})();
