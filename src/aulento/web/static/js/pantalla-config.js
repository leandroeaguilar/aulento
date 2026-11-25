[
  ['alternar-sidebar-movil', () => toggleMobileSidebar()],
  ['abrir-manual-usuario', (el, datos) => openUserManualModal(datos.tipo || 'manual')],
  ['abrir-diagnostico', () => openDiagnosticsModal()],
  ['instalar-pwa', () => promptPwaInstall()],
  ['sincronizar-duolingo-cabecera', () => syncDuolingoFromHeader()],
  ['ir-a-seccion-vectores', () => goToVectorSection()],
  ['detener-pomodoro', () => stopPomodoroTimer()],
  ['alternar-salud-sistema', () => toggleSystemHealthPopover()],
  ['verificar-conexiones-salud', () => { refreshBrainStatus(); toggleSystemHealthPopover(); }],
  ['abrir-atajos-teclado', () => openKeyboardShortcutsModal()],
  ['recargar-pagina', () => reloadApp()],
  ['alternar-tema', () => window.aulentoTema.alternar()],
  ['alternar-menu-usuario', () => toggleUserDropdown()],
  ['abrir-onboarding-desde-menu', () => { openOnboardingWizard(); closeUserDropdown(); }],
  ['abrir-atajos-desde-menu', () => { openKeyboardShortcutsModal(); closeUserDropdown(); }],
  ['ver-pomodoro-agenda', () => viewPomodoroInSchedule()],

  // Pestaña Config
  ['config-abrir-onboarding', () => openOnboardingWizard()],
  ['config-seccion', (el, datos) => switchConfigSection(datos.seccion)],
  ['config-cambiar-proveedor-ia', (el) => changeActiveIAProvider(el.value)],
  ['config-cambiar-tema', (el) => window.aulentoTema.guardar(el.value)],
  ['config-proveedor-tab', (el, datos) => switchProviderConfigTab(datos.proveedor)],
  ['config-alternar-visibilidad-clave', (el, datos) => toggleGeminiKeyVisibility(datos.input)],
  ['config-guardar-gemini', () => saveGeminiDualKeysConfig()],
  ['config-probar-gemini', () => testGeminiConnection()],
  ['config-quitar-clave', (el, datos) => removeProviderKeyUI(datos.proveedor)],
  ['config-obtener-modelos', (el, datos) => fetchProviderModelsUI(datos.proveedor)],
  ['config-guardar-anthropic', () => saveAnthropicKeyUI()],
  ['config-probar-proveedor', (el, datos) => testProviderConnectionUI(datos.proveedor)],
  ['config-guardar-openai', () => saveOpenAIKeyUI()],
  ['config-abrir-gcal', () => openGoogleCalendarModal()],
  ['config-cargar-carpetas-vault', () => loadVaultFolders()],
  ['config-crear-carpeta-vault', (el, datos, e) => createVaultFolder(e)],
  ['config-guardar-carpetas-tutor', () => saveTutorFolders()],
  ['config-tab-prompt', (el, datos) => switchPromptTab(datos.tipo)],
  ['config-guardar-prompt', () => saveActiveSystemPrompt()],
  ['config-restablecer-prompt', () => resetActiveSystemPrompt()],
  ['config-cargar-analiticas', () => loadTokenAnalytics()],
  ['config-copiar-snippet-mcp', (el, datos) => copiarSnippetMcp(Number(datos.indice), el)],
  ['config-revocar-token-mcp', (el, datos) => revocarTokenMcp(Number(datos.id))],
  ['config-elegir-cliente-mcp', (el, datos) => elegirClienteMcp(datos.cliente)],
  ['config-crear-token-mcp', () => crearTokenMcp()],
  ['config-limpiar-busqueda-manual', () => clearManualSearch()],

  // Modales
  ['guardar-usuario-duolingo', (el, datos, e) => saveDuolingoUsername(e)],
  ['eliminar-usuario-duolingo', () => removeDuolingoUsername()],
  ['wizard-omitir-por-ahora', () => dismissOnboardingForNow()],
  ['wizard-ir-paso', (el, datos) => setWizardStep(Number(datos.paso))],
  ['wizard-elegir-proveedor', (el, datos) => selectWizardProvider(datos.proveedor)],
  ['wizard-alternar-clave', () => toggleWizardKeyVisibility()],
  ['wizard-guardar-clave', () => wizardSaveAiKey()],
  ['wizard-probar-clave', () => wizardTestAiKey()],
  ['wizard-sembrar-mazo', () => wizardSeedDeck()],
  ['wizard-accion-y-cerrar', (el, datos) => wizardActionAndClose(datos.destino)],
  ['wizard-inicio-rapido', (el, datos) => wizardQuickStart(datos.accionTipo)],
  ['wizard-anterior', () => wizardPrev()],
  ['wizard-omitir-paso', () => wizardSkipStep()],
  ['wizard-siguiente', () => wizardNext()],
  ['wizard-completar', () => completeOnboardingWizard()],
  ['copiar-url-webhook-cursos', () => copyCourseWebhookUrl()],
  ['copiar-url-atajo-apple', () => copyShortcutUrl()],
  ['filtrar-contenido-manual', (el) => filterManualContent(el.value)],
  ['limpiar-busqueda-manual', () => clearManualSearch()],
  ['cambiar-tab-manual', (el, datos) => switchDocTab(datos.tipo)],
  ['copiar-reporte-diagnostico', () => copiarReporteDiagnostico()],
  ['refrescar-diagnostico', () => refreshDiagnosticsModal()],
  ['fijar-duracion-sesion-guiada', (el, datos) => setGuidedSessionDuration(Number(datos.duracion))],
  ['iniciar-sesion-guiada', () => launchGuidedStudySession()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

function reloadApp() {
  window.location.reload();
}

function viewPomodoroInSchedule() {
  switchTab('schedule');
  document.getElementById('focus-timer-section')?.scrollIntoView({ behavior: 'smooth' });
}

// --- ACCIONES DELEGADAS DE MODALES (072 T9b) ---
[
  ['modal-cambiar-escenario-consultoria', (el) => handleSelectConsultingScenario(el.value)],
  ['modal-evaluar-consultoria', (el, datos, ev) => handleEvaluateConsulting(ev)],
  ['modal-dictado-voz-consultoria', () => toggleConsultingVoiceDictation()],
  ['modal-audio-modelo-consultoria', () => playConsultingModelAudio()],
  ['modal-aplicar-nivel-recomendado', () => applyRecommendedLevel()],
  ['modal-iniciar-sesion-adaptativa', () => startAdaptiveSession()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

// Sub-navegacion de categorias para el Panel de Configuracion
function switchConfigSection(section) {
  state.activeConfigSection = section;
  const sections = ['ai', 'cloud', 'vault', 'duolingo', 'mcp', 'prompts', 'analytics', 'system'];
  if (section === 'mcp' || section === 'all') renderMcpConnect();
  if (section === 'vault' || section === 'all') loadVaultFolders();
  if (section === 'duolingo' || section === 'all') renderDuolingoConfigCard();
  const navBtns = document.querySelectorAll('.cfg-nav-btn');
  navBtns.forEach(btn => {
    btn.setAttribute('aria-selected', 'false');
  });

  const activeBtn = document.getElementById(`cfg-nav-${section}`);
  if (activeBtn) {
    activeBtn.setAttribute('aria-selected', 'true');
  }

  sections.forEach(s => {
    const el = document.getElementById(`cfg-sec-${s}`);
    if (!el) return;
    if (section === 'all' || section === s) {
      el.classList.remove('hidden');
    } else {
      el.classList.add('hidden');
    }
  });
}

// ======================================================================
// CONECTAR TU ASISTENTE (MCP)
// Arma la configuración lista para copiar con los datos reales de esta instalación (/api/mcp/connection-info).
// Dos caminos: en esta computadora (el asistente arranca Aulento por su cuenta, sin token ni puerto)
// y por red (con un token de la cuenta). Los comandos siguen la guía docs/GUIA_MCP.md.
// ======================================================================

const mcpConnect = { info: null, cliente: 'claude-desktop', tokenNuevo: null, tokens: [], snippets: [] };

const EJEMPLOS_DE_PEDIDOS_MCP = [
  'Listá mis rutas de aprendizaje de Aulento y decime qué temas todavía no tienen clase.',
  'Creá la clase completa del primer tema sin clase de mi ruta y guardala en Aulento.',
  'Repasemos juntos mis tarjetas de inglés que tocan hoy.',
];

function comillasDeConsola(texto) {
  return /[\s"'&()]/.test(texto) ? `"${String(texto).replace(/"/g, '\\"')}"` : String(texto);
}

function snippetMcp(texto) {
  mcpConnect.snippets.push(texto);
  const i = mcpConnect.snippets.length - 1;
  return `<div class="relative group">
      <pre class="bg-slate-950 border border-slate-800 rounded-xl p-4 pr-24 text-xs text-sky-200 font-mono whitespace-pre-wrap break-all">${escapeHtml(texto)}</pre>
      <button type="button" data-accion="config-copiar-snippet-mcp" data-indice="${i}" class="absolute top-2.5 right-2.5 au-boton au-boton--primario au-boton--chico">Copiar</button>
    </div>`;
}

async function copiarSnippetMcp(i, boton) {
  try {
    await navigator.clipboard.writeText(mcpConnect.snippets[i]);
    if (boton) {
      boton.innerHTML = `${Au.icono('ok')} Copiado`;
      setTimeout(() => { boton.textContent = 'Copiar'; }, 1800);
    }
  } catch (e) {
    showToast('No se pudo copiar: seleccioná el texto y copialo a mano.', 'warning');
  }
}

function servidorLocalMcp(info) {
  const servidor = {
    command: info.python,
    args: ['-m', 'aulento', '--user', info.usuario, 'mcp', 'serve'],
    cwd: info.directorio,
  };
  if (Object.keys(info.variables || {}).length) servidor.env = { ...info.variables };
  return servidor;
}

function pasosLocalesMcp(info) {
  const json = JSON.stringify({ mcpServers: { 'aulento': servidorLocalMcp(info) } }, null, 2);
  const envs = Object.entries(info.variables || {}).map(([k, v]) => `--env ${k}=${comillasDeConsola(v)} `).join('');
  const claudeCode = `claude mcp add ${envs}--transport stdio --scope user aulento -- `
    + `${comillasDeConsola(info.python)} -m aulento --user ${comillasDeConsola(info.usuario)} mcp serve`;
  const pasos = {
    'claude-desktop': `<p class="text-sm text-slate-300">1. En Claude Desktop abrí <b>Configuración → Desarrollador → Editar configuración</b>
        (es el archivo <code class="text-sky-300">claude_desktop_config.json</code>).</p>
      <p class="text-sm text-slate-300">2. Pegá esto. Si ya tenés otros servidores, sumá solo la entrada <code class="text-sky-300">"aulento"</code> dentro de <code class="text-sky-300">"mcpServers"</code>.</p>
      ${snippetMcp(json)}
      <p class="text-sm text-slate-300">3. Cerrá Claude Desktop del todo y volvé a abrirlo. Vas a ver <b>aulento</b> entre las herramientas.</p>`,
    'claude-code': `<p class="text-sm text-slate-300">1. En una terminal, corré este comando (deja Aulento disponible en todos tus proyectos):</p>
      ${snippetMcp(claudeCode)}
      <p class="text-sm text-slate-300">2. Abrí Claude Code y escribí <code class="text-sky-300">/mcp</code> para confirmar que <b>aulento</b> está conectado.</p>`,
    'cursor': `<p class="text-sm text-slate-300">1. En Cursor abrí <b>Settings → MCP → Add new global MCP server</b> (es el archivo <code class="text-sky-300">~/.cursor/mcp.json</code>).</p>
      <p class="text-sm text-slate-300">2. Pegá esto y guardá. Sirve también para otros asistentes que usan el mismo formato <code class="text-sky-300">mcpServers</code>.</p>
      ${snippetMcp(json)}`,
  };
  return pasos[mcpConnect.cliente];
}

function pasosDeRedMcp(info) {
  const token = mcpConnect.tokenNuevo ? mcpConnect.tokenNuevo.token : '<TU_TOKEN>';
  // Abierta desde otra máquina, el servidor MCP tiene que aceptar conexiones de afuera con ese nombre
  const remoto = info.red_remota ? ` --allow-remote --allowed-host ${info.host_red}` : '';
  const arrancar = info.local_disponible
    ? `${comillasDeConsola(info.python)} -m aulento mcp serve --transport http --port ${info.puerto_red}${remoto}`
    : `python -m aulento mcp serve --transport http --port ${info.puerto_red}${remoto}`;
  const claudeCode = `claude mcp add --transport http --scope user aulento ${info.url_red} --header "Authorization: Bearer ${token}"`;
  const json = JSON.stringify({
    mcpServers: { 'aulento': { type: 'http', url: info.url_red, headers: { Authorization: `Bearer ${token}` } } },
  }, null, 2);
  const variables = Object.keys(info.variables || {});
  const paso1 = info.local_disponible
    ? '1. Dejá corriendo el servidor por red en esta computadora:'
    : '1. Quien administra la instalación tiene que dejar corriendo el servidor por red (pasale este comando):';
  return `<p class="text-sm text-slate-300">${paso1}</p>
    ${snippetMcp(arrancar)}
    ${variables.length ? `<p class="text-xs text-slate-400">Con las mismas variables que usa la app: ${variables.map((v) => `<code class="text-sky-300">${escapeHtml(v)}</code>`).join(', ')}.</p>` : ''}
    <p class="text-sm text-slate-300">2. En Claude Code:</p>
    ${snippetMcp(claudeCode)}
    <p class="text-sm text-slate-300">3. En Cursor u otro asistente que se conecte por URL:</p>
    ${snippetMcp(json)}`;
}

function filaDeTokenMcp(t) {
  const fecha = (iso) => (iso ? new Date(iso).toLocaleString() : '—');
  const estado = t.revocado_en
    ? '<span class="text-rose-300">Revocado</span>'
    : '<span class="text-emerald-300">Activo</span>';
  const accion = t.revocado_en ? '' : `<button type="button" data-accion="config-revocar-token-mcp" data-id="${t.id}" class="au-boton au-boton--peligro au-boton--chico">Revocar</button>`;
  return `<tr class="border-t border-slate-800">
      <td class="py-2 pr-3 text-slate-200">${escapeHtml(t.nombre || 'Sin nombre')}</td>
      <td class="py-2 pr-3 text-slate-400">${fecha(t.creado_en)}</td>
      <td class="py-2 pr-3 text-slate-400">${fecha(t.ultimo_uso)}</td>
      <td class="py-2 pr-3">${estado}</td>
      <td class="py-2 text-right">${accion}</td>
    </tr>`;
}

async function renderMcpConnect() {
  const cuerpo = document.getElementById('mcp-connect-body');
  if (!cuerpo) return;
  mcpConnect.snippets = [];

  if (esCuentaCompartida()) {
    cuerpo.innerHTML = `<div class="bg-amber-950/40 border border-amber-700/50 rounded-2xl px-5 py-4 text-sm text-amber-200">
        <p class="font-semibold flex items-center gap-1.5">${Au.icono('bloqueado')} <span>Esta cuenta es compartida: acá no se conecta ningún asistente.</span></p>
        <p class="text-amber-200/80 text-xs mt-1">La usan varias personas. En tu propia instalación, esta pantalla te da la configuración lista para copiar
        en Claude Desktop, Claude Code o Cursor, y tu asistente genera las clases con tu suscripción, sin clave de API.</p>
      </div>`;
    return;
  }

  try {
    if (!mcpConnect.info) {
      const res = await fetch('/api/mcp/connection-info');
      if (!res.ok) throw new Error('No se pudieron leer los datos de conexión.');
      mcpConnect.info = await res.json();
    }
    const resTokens = await fetch('/api/mcp/tokens');
    mcpConnect.tokens = resTokens.ok ? await resTokens.json() : [];
  } catch (e) {
    cuerpo.innerHTML = `<div class="text-sm text-rose-300 p-6">${escapeHtml(e.message)}</div>`;
    return;
  }

  const info = mcpConnect.info;
  const pestana = (id, texto) => `<button type="button" role="tab" aria-selected="${mcpConnect.cliente === id ? 'true' : 'false'}" data-accion="config-elegir-cliente-mcp" data-cliente="${id}"
      class="au-pestanas__boton">${texto}</button>`;
  const avisoClave = info.clave_maestra_por_variable
    ? `<p class="text-xs text-amber-200 bg-amber-950/40 border border-amber-700/50 rounded-xl p-3">Tu servidor toma la clave maestra de la variable
        <code>${escapeHtml(info.variable_de_la_clave_maestra)}</code>. Agregala también en <code>"env"</code> de la configuración del asistente:
        por seguridad no se muestra acá.</p>`
    : '';
  const nuevo = mcpConnect.tokenNuevo
    ? `<div class="bg-emerald-950/40 border-2 border-emerald-600/60 rounded-2xl p-4 space-y-2">
        <p class="text-sm font-bold text-emerald-200">Tu token «${escapeHtml(mcpConnect.tokenNuevo.nombre || 'Sin nombre')}». Copialo ahora: no se vuelve a mostrar.</p>
        ${snippetMcp(mcpConnect.tokenNuevo.token)}
      </div>`
    : '';
  const activos = mcpConnect.tokens.filter((t) => !t.revocado_en);

  const tarjetaLocal = info.local_disponible
    ? `<div class="au-tarjeta au-tarjeta--destacada">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 class="font-bold text-white text-base">En esta computadora <span class="text-xs font-semibold text-violet-300 ml-1">Recomendado</span></h4>
          <p class="text-xs text-slate-400">Tu asistente arranca Aulento solo cuando lo necesita. Sin token ni puertos abiertos.</p>
        </div>
        <div class="au-pestanas scroll-x-pista" role="tablist" aria-label="Clientes MCP">${pestana('claude-desktop', 'Claude Desktop')}${pestana('claude-code', 'Claude Code')}${pestana('cursor', 'Cursor y otros')}</div>
      </div>
      ${pasosLocalesMcp(info)}
      ${avisoClave}
    </div>`
    : `<div class="au-tarjeta">
      <h4 class="font-bold text-white text-base">En esta computadora</h4>
      <p class="text-xs text-slate-400">Esta forma la usa quien administra la instalación, porque necesita estar en la misma computadora que el servidor.
        Vos te conectás por red, con un token propio: está acá abajo.</p>
    </div>`;

  cuerpo.innerHTML = `
    ${tarjetaLocal}

    <div class="au-tarjeta">
      <div>
        <h4 class="font-bold text-white text-base">Por red, con un token</h4>
        <p class="text-xs text-slate-400">Para un asistente que se conecta por URL. Cada token es de tu cuenta y lo podés revocar cuando quieras.</p>
      </div>
      <div class="flex flex-col sm:flex-row gap-2">
        <input id="mcp-token-nombre" type="text" maxlength="64" placeholder="Nombre del token (ej. Claude Code de la notebook)"
          class="au-campo__control flex-1">
        <button type="button" data-accion="config-crear-token-mcp" class="au-boton au-boton--primario">Crear token</button>
      </div>
      ${nuevo}
      ${pasosDeRedMcp(info)}
      ${mcpConnect.tokens.length ? `<div class="overflow-x-auto">
        <p class="text-xs font-semibold text-slate-400 mb-1">Tus tokens (${activos.length} activos)</p>
        <table class="w-full text-xs"><thead><tr class="text-left text-slate-500">
          <th class="py-1 pr-3">Nombre</th><th class="py-1 pr-3">Creado</th><th class="py-1 pr-3">Último uso</th><th class="py-1 pr-3">Estado</th><th></th>
        </tr></thead><tbody>${mcpConnect.tokens.map(filaDeTokenMcp).join('')}</tbody></table></div>` : ''}
    </div>

    <div class="au-tarjeta">
      <h4 class="font-bold text-white text-base">Probalo</h4>
      <p class="text-xs text-slate-400">Con el asistente conectado, pedile por ejemplo:</p>
      ${EJEMPLOS_DE_PEDIDOS_MCP.map(snippetMcp).join('')}
    </div>`;
}

function elegirClienteMcp(cliente) {
  mcpConnect.cliente = cliente;
  renderMcpConnect();
}

async function crearTokenMcp() {
  const input = document.getElementById('mcp-token-nombre');
  const nombre = input && input.value.trim() ? input.value.trim() : null;
  const res = await fetch('/api/mcp/tokens', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nombre }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    if (!res.headers.get('X-Cuenta-Compartida')) showToast(err.detail || 'No se pudo crear el token.', 'error');
    return;
  }
  mcpConnect.tokenNuevo = await res.json();
  await renderMcpConnect();
  showToast('Token creado. Copialo ahora: no se vuelve a mostrar.', 'success', 5000);
}

async function revocarTokenMcp(id) {
  const ok = await showConfirmDialog({
    title: 'Revocar el token',
    message: 'El asistente que lo use deja de poder conectarse. Esto no se puede deshacer.',
    confirmText: 'Revocar',
    icon: 'clave',
    danger: true,
  });
  if (!ok) return;
  const res = await fetch(`/api/mcp/tokens/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    showToast('No se pudo revocar el token.', 'error');
    return;
  }
  if (mcpConnect.tokenNuevo && mcpConnect.tokenNuevo.id === id) mcpConnect.tokenNuevo = null;
  await renderMcpConnect();
}

// --- GEMINI 1.5 FLASH CONFIGURACIÓN Y ESTADO ---
async function loadGeminiTutorStatus() {
  try {
    const res = await fetch('/api/fsrs/audio/gemini-status');
    if (res.ok) {
      const data = await res.json();
      const modelBadge = document.getElementById('fsrs-voice-eval-model');
      if (modelBadge) {
        if (data.configured) {
          modelBadge.innerHTML = `${Au.icono('generar')} Gemini 1.5 Flash`;
          modelBadge.className = "au-insignia au-insignia--primario cursor-pointer";
          modelBadge.title = "Gemini 1.5 Flash activo (Google AI Studio Free Tier). Clic para cambiar clave.";
        } else {
          modelBadge.innerHTML = `${Au.icono('rapido')} Fallback Local`;
          modelBadge.className = "au-insignia au-insignia--alerta cursor-pointer";
          modelBadge.title = "Modo heurístico local activo. Clic para activar Gemini 1.5 Flash con tu API Key.";
        }
      }

      // Actualizar badge en el Panel de Configuración
      const configBadge = document.getElementById('config-gemini-status-badge');
      if (configBadge) {
        if (data.configured) {
          configBadge.innerHTML = `${Au.icono('punto')} Conectado`;
          configBadge.className = "au-insignia au-insignia--exito";
        } else {
          configBadge.innerHTML = `${Au.icono('punto')} Fallback Local Activo`;
          configBadge.className = "au-insignia au-insignia--alerta";
        }
      }

      // Actualizar badge en el modal Harvester
      const harvesterBadge = document.getElementById('harvester-gemini-badge');
      if (harvesterBadge) {
        if (data.configured) {
          harvesterBadge.innerHTML = `${Au.icono('generar')} Gemini Enriquecido`;
          harvesterBadge.className = "au-insignia au-insignia--primario";
          harvesterBadge.title = "Google Gemini 1.5 Flash genera y enriquece tarjetas en tiempo real.";
        } else {
          harvesterBadge.innerHTML = `${Au.icono('rapido')} Modo Local Heurístico`;
          harvesterBadge.className = "au-insignia";
          harvesterBadge.title = "Configura tu API Key en el panel de Configuración para activar Gemini.";
        }
      }
      // Actualizar selector de modelo en Configuración
      const modelSelect = document.getElementById('config-gemini-model-select');
      if (modelSelect && data.model) {
        modelSelect.value = data.model;
      }
    }
  } catch (err) {
    console.debug("No se pudo verificar estado de Gemini Tutor:", err);
  }
}

async function promptConfigureGeminiKey() {
  switchTab('config');
  const input = document.getElementById('config-gemini-key-input');
  if (input) input.focus();
}

// --- PANEL DE CONFIGURACIÓN INTEGRAL ---
async function loadConfigPanel() {
  switchConfigSection(state.activeConfigSection || 'ai');
  await loadGeminiTutorStatus();
  await loadGeminiDualKeysConfig();
  await loadIAConfig();
  await loadSystemPrompts();
  await loadTokenAnalytics();
}

async function saveGeminiKeyFromConfig() {
  const input = document.getElementById('config-gemini-key-input');
  const modelSelect = document.getElementById('config-gemini-model-select');
  const feedback = document.getElementById('config-gemini-feedback');
  const btn = document.getElementById('btn-config-save-gemini');
  if (!input) return;
  const key = input.value.trim();
  const model = modelSelect ? modelSelect.value : null;

  btn.disabled = true;
  btn.innerText = "Guardando...";

  try {
    const payload = {};
    if (key) payload.key = key;
    if (model) payload.model = model;

    const res = await fetch('/api/fsrs/audio/gemini-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      if (feedback) {
        feedback.className = "au-aviso au-aviso--exito block";
        feedback.innerText = "Configuración guardada correctamente (clave y modelo activo).";
      }
      input.value = "";
      await loadGeminiTutorStatus();
    } else {
      const err = await res.json();
      pintarErrorEnFeedback(feedback, err.detail || "Verificá la clave.");
    }
  } catch (err) {
    if (feedback) {
      feedback.className = "au-aviso au-aviso--peligro block";
      feedback.innerText = "Error de red al conectar con el servidor.";
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${Au.icono('guardar')} Guardar Clave`;
  }
}

async function testGeminiConnection() {
  const feedback = document.getElementById('config-gemini-feedback');
  const btn = document.getElementById('btn-config-test-gemini');
  btn.disabled = true;
  btn.innerText = "Probando...";
  if (feedback) {
    feedback.className = "au-aviso block";
    feedback.innerText = "Conectando con Google AI Studio...";
  }

  try {
    const res = await fetch('/api/fsrs/audio/gemini-test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
      if (res.status === 404) {
        throw new Error("El servidor local está corriendo una versión previa en memoria. Detenelo con Ctrl+C en tu terminal y reinicialo con 'python -m aulento web' para cargar los nuevos endpoints.");
      }
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Error HTTP ${res.status}`);
    }
    const data = await res.json();
    if (data.ok) {
      if (feedback) {
        feedback.className = "au-aviso au-aviso--exito block";
        feedback.innerText = `Conexión exitosa con Google AI Studio. Modelo: ${data.model} (Status: 200 OK)`;
      }
      await loadGeminiTutorStatus();
    } else {
      if (feedback) {
        feedback.className = "au-aviso au-aviso--peligro block";
        feedback.innerText = `Error de conexión: ${data.error || 'Verificá tu API key o conexión a internet.'}`;
      }
    }
  } catch (err) {
    if (feedback) {
      feedback.className = "au-aviso au-aviso--peligro block";
      feedback.innerText = err.message || 'Error de red al realizar el test.';
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${Au.icono('rapido')} Probar Conexión`;
  }
}

function toggleGeminiKeyVisibility(inputId = 'config-gemini-key-input') {
  const input = document.getElementById(inputId);
  if (input) {
    input.type = input.type === 'password' ? 'text' : 'password';
  }
}

// --- DUAL GEMINI KEYS CONFIGURATION ---
async function loadGeminiDualKeysConfig() {
  const freeBadge = document.getElementById('config-gemini-free-status');
  const paidBadge = document.getElementById('config-gemini-paid-status');
  const tierBadge = document.getElementById('config-gemini-tier-badge');
  const tierSelect = document.getElementById('config-gemini-tier-select');
  const statusBadge = document.getElementById('config-gemini-status-badge');

  try {
    const res = await fetch('/api/config/gemini-keys');
    if (res.ok) {
      const data = await res.json();
      if (freeBadge) {
        freeBadge.className = data.free_key_error ? "text-xs text-rose-400 font-bold" : (data.has_free_key ? "text-xs text-emerald-400 font-bold" : "text-xs text-slate-500");
        freeBadge.textContent = data.free_key_error || (data.has_free_key ? `Configurada (${data.free_key_masked})` : "No configurada");
      }
      if (paidBadge) {
        paidBadge.className = data.paid_key_error ? "text-xs text-rose-400 font-bold" : (data.has_paid_key ? "text-xs text-emerald-400 font-bold" : "text-xs text-slate-500");
        paidBadge.textContent = data.paid_key_error || (data.has_paid_key ? `Configurada (${data.paid_key_masked})` : "No configurada");
      }
      if (tierBadge) {
        tierBadge.textContent = `Modo: ${String(data.active_tier).toUpperCase()}`;
      }
      if (tierSelect) {
        tierSelect.value = data.active_tier;
      }
      if (statusBadge) {
        if (data.has_free_key || data.has_paid_key) {
          statusBadge.className = "au-insignia au-insignia--exito";
          statusBadge.innerHTML = `${Au.icono('punto')} Listo (${data.active_tier})`;
        } else {
          statusBadge.className = "au-insignia";
          statusBadge.textContent = "Sin Clave";
        }
      }
    }
  } catch (err) {
    console.error("Error al cargar dual keys config:", err);
  }
}

async function saveGeminiDualKeysConfig() {
  const freeKeyInput = document.getElementById('config-gemini-key-input');
  const paidKeyInput = document.getElementById('config-gemini-paid-input');
  const tierSelect = document.getElementById('config-gemini-tier-select');
  const modelSelect = document.getElementById('config-gemini-model-select');
  const feedback = document.getElementById('config-gemini-feedback');
  const btn = document.getElementById('btn-config-save-gemini');

  const freeKey = freeKeyInput ? freeKeyInput.value.trim() : '';
  const paidKey = paidKeyInput ? paidKeyInput.value.trim() : '';
  const tier = tierSelect ? tierSelect.value : 'auto';
  const model = modelSelect ? modelSelect.value : 'gemini-2.5-flash';

  btn.disabled = true;
  btn.innerText = "Guardando...";

  try {
    const payload = {
      active_tier: tier,
      preferred_model: model
    };
    if (freeKey) payload.key_free = freeKey;
    if (paidKey) payload.key_paid = paidKey;

    const res = await fetch('/api/config/gemini-keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      if (feedback) {
        feedback.className = "au-aviso au-aviso--exito block";
        feedback.innerText = "Infraestructura de claves Gemini actualizada con éxito.";
      }
      if (freeKeyInput) freeKeyInput.value = '';
      if (paidKeyInput) paidKeyInput.value = '';
      await loadGeminiDualKeysConfig();
      await loadGeminiTutorStatus();
    } else {
      const err = await res.json();
      pintarErrorEnFeedback(feedback, err.detail || "Verificá los datos.");
    }
  } catch (err) {
    if (feedback) {
      feedback.className = "au-aviso au-aviso--peligro block";
      feedback.innerText = "Error de conexión al guardar configuración.";
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${Au.icono('guardar')} Guardar Configuración`;
  }
}

// --- PROVEEDORES DE IA (GEMINI, ANTHROPIC, OPENAI) ---

function switchProviderConfigTab(provider) {
  const tabs = ['gemini', 'anthropic', 'openai'];
  tabs.forEach(p => {
    const panel = document.getElementById(`panel-provider-${p}`);
    const btn = document.getElementById(`btn-tab-provider-${p}`);
    if (panel) {
      if (p === provider) {
        panel.classList.remove('hidden');
      } else {
        panel.classList.add('hidden');
      }
    }
    if (btn) {
      btn.setAttribute('aria-selected', p === provider ? 'true' : 'false');
    }
  });
}

async function loadIAConfig() {
  try {
    const res = await fetch('/api/config/ia');
    if (!res.ok) return;
    const data = await res.json();
    const activo = data.proveedor_activo || 'gemini';

    const selectActivo = document.getElementById('config-ia-active-provider-select');
    if (selectActivo) selectActivo.value = activo;

    const badgeActivo = document.getElementById('config-ia-active-badge');
    if (badgeActivo) {
      const nombres = { gemini: 'Gemini Activo', anthropic: 'Anthropic Activo', openai: 'OpenAI Activo' };
      badgeActivo.textContent = nombres[activo] || `${activo.toUpperCase()} Activo`;
    }

    const proveedores = data.proveedores || {};

    // Anthropic
    const ant = proveedores.anthropic || {};
    const antBadge = document.getElementById('config-anthropic-status-badge');
    const antStatus = document.getElementById('config-anthropic-key-status');
    const antModelInput = document.getElementById('config-anthropic-model-input');
    if (antBadge) {
      antBadge.className = ant.tiene_clave ? "au-insignia au-insignia--exito" : "au-insignia";
      antBadge.innerHTML = ant.tiene_clave ? `${Au.icono('punto')} Configurada` : "Sin Clave";
    }
    if (antStatus) {
      antStatus.className = ant.tiene_clave ? "text-xs text-emerald-400 font-bold" : "text-xs text-slate-500";
      antStatus.textContent = ant.tiene_clave ? `Configurada (${ant.clave || 'activa'})` : "No configurada";
    }
    if (antModelInput && ant.modelo) {
      antModelInput.value = ant.modelo;
    }

    // OpenAI
    const oa = proveedores.openai || {};
    const oaBadge = document.getElementById('config-openai-status-badge');
    const oaStatus = document.getElementById('config-openai-key-status');
    const oaModelInput = document.getElementById('config-openai-model-input');
    if (oaBadge) {
      oaBadge.className = oa.tiene_clave ? "au-insignia au-insignia--exito" : "au-insignia";
      oaBadge.innerHTML = oa.tiene_clave ? `${Au.icono('punto')} Configurada` : "Sin Clave";
    }
    if (oaStatus) {
      oaStatus.className = oa.tiene_clave ? "text-xs text-emerald-400 font-bold" : "text-xs text-slate-500";
      oaStatus.textContent = oa.tiene_clave ? `Configurada (${oa.clave || 'activa'})` : "No configurada";
    }
    if (oaModelInput && oa.modelo) {
      oaModelInput.value = oa.modelo;
    }

    const gemini = proveedores.gemini || {};
    actualizarBotonesDeProveedor('gemini', !!gemini.tiene_clave);
    actualizarBotonesDeProveedor('anthropic', !!ant.tiene_clave);
    actualizarBotonesDeProveedor('openai', !!oa.tiene_clave);
  } catch (err) {
    console.error("Error al cargar configuración de IA:", err);
  }
}

async function changeActiveIAProvider(proveedor) {
  try {
    const res = await fetch('/api/config/ia', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proveedor_activo: proveedor })
    });
    if (res.ok) {
      await loadIAConfig();
    }
  } catch (err) {
    console.error("Error al cambiar proveedor activo de IA:", err);
  }
}

async function saveAnthropicKeyUI() {
  const keyInput = document.getElementById('config-anthropic-key-input');
  const modelInput = document.getElementById('config-anthropic-model-input');
  const feedback = document.getElementById('config-anthropic-feedback');
  const key = keyInput ? keyInput.value.trim() : '';
  const model = modelInput ? modelInput.value.trim() : '';

  try {
    if (key) {
      const resKey = await fetch('/api/config/ia/anthropic/key', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clave: key })
      });
      if (!resKey.ok) {
        const err = await resKey.json();
        throw new Error(err.detail || "Error al guardar clave");
      }
      if (keyInput) keyInput.value = '';
    }
    if (model) {
      await fetch('/api/config/ia', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modelos: { anthropic: model } })
      });
    }
    if (feedback) {
      feedback.className = "au-aviso au-aviso--exito block";
      feedback.innerText = "Configuración de Anthropic actualizada con éxito.";
    }
    await loadIAConfig();
    actualizarBotonesDeProveedor('anthropic', true);
  } catch (err) {
    pintarErrorEnFeedback(feedback, err.message);
  }
}

async function saveOpenAIKeyUI() {
  const keyInput = document.getElementById('config-openai-key-input');
  const modelInput = document.getElementById('config-openai-model-input');
  const feedback = document.getElementById('config-openai-feedback');
  const key = keyInput ? keyInput.value.trim() : '';
  const model = modelInput ? modelInput.value.trim() : '';

  try {
    if (key) {
      const resKey = await fetch('/api/config/ia/openai/key', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clave: key })
      });
      if (!resKey.ok) {
        const err = await resKey.json();
        throw new Error(err.detail || "Error al guardar clave");
      }
      if (keyInput) keyInput.value = '';
    }
    if (model) {
      await fetch('/api/config/ia', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modelos: { openai: model } })
      });
    }
    if (feedback) {
      feedback.className = "au-aviso au-aviso--exito block";
      feedback.innerText = "Configuración de OpenAI actualizada con éxito.";
    }
    await loadIAConfig();
  } catch (err) {
    pintarErrorEnFeedback(feedback, err.message);
  }
}

async function removeProviderKeyUI(provider) {
  if (!confirm(`¿Eliminar la clave guardada de ${provider.toUpperCase()}?`)) return;
  try {
    const res = await fetch(`/api/config/ia/${provider}/key`, { method: 'DELETE' });
    if (res.ok) {
      await loadIAConfig();
      actualizarBotonesDeProveedor(provider, false);
    }
  } catch (err) {
    console.error("Error al eliminar clave de IA:", err);
  }
}

async function fetchProviderModelsUI(provider) {
  const btn = document.getElementById(`btn-config-models-${provider}`);
  const input = document.getElementById(`config-${provider}-model-input`);
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `${Au.icono('cargando', { clase: 'au-icono--girando' })} Consultando...`;
  }

  try {
    const res = await fetch(`/api/config/ia/${provider}/models`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (typeof showToast === 'function') {
        showToast(`No se pudo obtener modelos: ${err.detail || 'Verificá tu clave de API.'}`, 'error');
      }
      return;
    }
    const data = await res.json();
    const modelos = data.modelos || [];
    if (modelos.length === 0) {
      if (typeof showToast === 'function') {
        showToast("El proveedor no reportó modelos disponibles.", 'info');
      }
      return;
    }

    let select = document.getElementById(`config-${provider}-models-select`);
    if (!select) {
      select = document.createElement('select');
      select.id = `config-${provider}-models-select`;
      select.className = 'au-campo__control w-full mt-2 font-mono';
      if (input && input.parentElement) {
        input.parentElement.parentElement.appendChild(select);
      }
    }
    select.innerHTML = `
      <option value="">-- Seleccionar modelo (${modelos.length} disponibles) --</option>
      ${modelos.map(m => `<option value="${escapeHtml(m)}" ${input && input.value === m ? 'selected' : ''}>${escapeHtml(m)}</option>`).join('')}
    `;
    select.classList.remove('hidden');
    select.onchange = () => {
      if (select.value && input) {
        input.value = select.value;
      }
    };
    if (typeof showToast === 'function') {
      showToast(`Se encontraron ${modelos.length} modelos disponibles.`, 'success');
    }
  } catch (err) {
    console.error("Error al obtener modelos de IA:", err);
    if (typeof showToast === 'function') {
      showToast("Error de conexión al obtener modelos.", 'error');
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }
}

async function testProviderConnectionUI(provider) {
  const feedback = document.getElementById(`config-${provider}-feedback`);
  if (feedback) {
    feedback.className = "au-aviso block";
    feedback.innerText = `Probando conexión con ${provider.toUpperCase()}...`;
  }
  try {
    const res = await fetch(`/api/config/ia/${provider}/test`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      if (feedback) {
        feedback.className = "au-aviso au-aviso--exito block";
        feedback.innerText = `${data.mensaje} (Latencia: ${data.latencia_ms || 0} ms)`;
      }
    } else {
      if (feedback) {
        feedback.className = "au-aviso au-aviso--peligro block";
        feedback.innerText = `Error de conexión: ${data.mensaje}`;
      }
    }
  } catch (err) {
    if (feedback) {
      feedback.className = "au-aviso au-aviso--peligro block";
      feedback.innerText = "Error de red al probar conexión.";
    }
  }
}

// --- SYSTEM PROMPTS PEDAGÓGICOS ---
function switchPromptTab(tab) {
  state.activePromptTab = tab;
  const containerRoadmap = document.getElementById('container-prompt-roadmap');
  const containerLesson = document.getElementById('container-prompt-lesson');
  const btnRoadmap = document.getElementById('btn-prompt-tab-roadmap');
  const btnLesson = document.getElementById('btn-prompt-tab-lesson');

  if (tab === 'lesson') {
    if (containerRoadmap) containerRoadmap.classList.add('hidden');
    if (containerLesson) containerLesson.classList.remove('hidden');
    if (btnRoadmap) btnRoadmap.setAttribute('aria-selected', 'false');
    if (btnLesson) btnLesson.setAttribute('aria-selected', 'true');
  } else {
    if (containerRoadmap) containerRoadmap.classList.remove('hidden');
    if (containerLesson) containerLesson.classList.add('hidden');
    if (btnRoadmap) btnRoadmap.setAttribute('aria-selected', 'true');
    if (btnLesson) btnLesson.setAttribute('aria-selected', 'false');
  }
}

async function loadSystemPrompts() {
  try {
    const res = await fetch('/api/roadmap/system-prompts');
    if (res.ok) {
      const data = await res.json();
      const roadmapText = document.getElementById('config-prompt-roadmap-text');
      const lessonText = document.getElementById('config-prompt-lesson-text');
      if (roadmapText) roadmapText.value = data.roadmap_prompt || '';
      if (lessonText) lessonText.value = data.lesson_prompt || '';
    }
  } catch (err) {
    console.error("Error al cargar system prompts:", err);
  }
}

async function saveActiveSystemPrompt() {
  const roadmapText = document.getElementById('config-prompt-roadmap-text');
  const lessonText = document.getElementById('config-prompt-lesson-text');
  const feedback = document.getElementById('config-prompt-feedback');
  const btn = document.getElementById('btn-save-prompts');

  btn.disabled = true;
  btn.innerHTML = `${Au.icono('cargando', { clase: 'au-icono--girando' })} Guardando...`;

  try {
    const payload = {};
    if (roadmapText) payload.roadmap_prompt = roadmapText.value;
    if (lessonText) payload.lesson_prompt = lessonText.value;

    const res = await fetch('/api/roadmap/system-prompts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      if (feedback) {
        feedback.textContent = "Guardado exitosamente";
        feedback.classList.remove('hidden');
        setTimeout(() => feedback.classList.add('hidden'), 3500);
      }
    } else {
      alert("Error al guardar prompt pedagógico.");
    }
  } catch (err) {
    alert("Error de conexión al guardar prompt: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${Au.icono('guardar')} Guardar Prompt`;
  }
}

async function resetActiveSystemPrompt() {
  const confirmed = await showConfirmDialog({
    title: 'Restaurar System Prompts',
    message: '¿Deseas restaurar los System Prompts a sus valores predeterminados (Backward Design y Taxonomía de Bloom)?',
    confirmText: 'Restaurar Defaults',
    cancelText: 'Cancelar',
    icon: 'recargar'
  });
  if (!confirmed) {
    return;
  }
  try {
    const res = await fetch('/api/roadmap/system-prompts/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: 'all' })
    });
    if (res.ok) {
      await loadSystemPrompts();
      alert("System Prompts restaurados a las directivas pedagógicas oficiales.");
    }
  } catch (err) {
    alert("Error al restaurar prompts: " + err.message);
  }
}

// --- TOKEN & COST ANALYTICS ---
async function loadTokenAnalytics() {
  try {
    // 1. Resumen de tokens
    const resSummary = await fetch('/api/analytics/tokens');
    if (resSummary.ok) {
      const summary = await resSummary.json();
      const kpiReq = document.getElementById('analytics-kpi-requests');
      const kpiPrompt = document.getElementById('analytics-kpi-prompt-tokens');
      const kpiComp = document.getElementById('analytics-kpi-comp-tokens');
      const kpiTotal = document.getElementById('analytics-kpi-total-tokens');
      const kpiCost = document.getElementById('analytics-kpi-cost');

      if (kpiReq) kpiReq.textContent = summary.total_requests;
      if (kpiPrompt) kpiPrompt.textContent = (summary.total_prompt_tokens || 0).toLocaleString();
      if (kpiComp) kpiComp.textContent = (summary.total_completion_tokens || 0).toLocaleString();
      if (kpiTotal) kpiTotal.textContent = (summary.total_tokens || 0).toLocaleString();
      if (kpiCost) kpiCost.textContent = `$${(summary.total_estimated_cost_usd || 0).toFixed(4)}`;

      // Model breakdown
      const modelsContainer = document.getElementById('analytics-table-models');
      if (modelsContainer) {
        const models = Object.keys(summary.by_model || {});
        if (models.length === 0) {
          modelsContainer.innerHTML = '<p class="text-slate-500 italic">Sin registros de modelos.</p>';
        } else {
          modelsContainer.innerHTML = models.map(m => {
            const data = summary.by_model[m];
            return `
              <div class="flex items-center justify-between p-2.5 bg-slate-900 rounded-xl border border-slate-800">
                <span class="font-mono text-white">${escapeHtml(m)}</span>
                <div class="text-right">
                  <div class="text-slate-300 font-bold">${(data.total_tokens || 0).toLocaleString()} tokens</div>
                  <div class="text-xs text-emerald-400">$${(data.cost_usd || 0).toFixed(4)} • ${data.requests} reqs</div>
                </div>
              </div>
            `;
          }).join('');
        }
      }

      // Endpoint breakdown
      const endpointsContainer = document.getElementById('analytics-table-endpoints');
      if (endpointsContainer) {
        const endpoints = Object.keys(summary.by_endpoint || {});
        if (endpoints.length === 0) {
          endpointsContainer.innerHTML = '<p class="text-slate-500 italic">Sin registros de endpoints.</p>';
        } else {
          endpointsContainer.innerHTML = endpoints.map(ep => {
            const data = summary.by_endpoint[ep];
            return `
              <div class="flex items-center justify-between p-2.5 bg-slate-900 rounded-xl border border-slate-800">
                <span class="font-mono text-white text-xs truncate max-w-[180px]">${escapeHtml(ep)}</span>
                <div class="text-right">
                  <div class="text-slate-300 font-bold">${(data.total_tokens || 0).toLocaleString()} tokens</div>
                  <div class="text-xs text-emerald-400">$${(data.cost_usd || 0).toFixed(4)} • ${data.requests} reqs</div>
                </div>
              </div>
            `;
          }).join('');
        }
      }
    }

    // 2. Logs recientes
    const resLogs = await fetch('/api/analytics/logs?limit=15');
    if (resLogs.ok) {
      const logs = await resLogs.json();
      const logsBody = document.getElementById('analytics-table-logs-body');
      if (logsBody) {
        if (!logs || logs.length === 0) {
          logsBody.innerHTML = '<tr><td colspan="8" class="py-3 px-3 text-center text-slate-500 italic">Sin llamadas registradas en esta base de datos.</td></tr>';
        } else {
          logsBody.innerHTML = logs.map(l => {
            const dateStr = l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : '-';
            const statusClass = l.status === 'success' ? 'text-emerald-400' : 'text-rose-400';
            const tierBadge = l.tier === 'paid' ? '<span class="text-purple-400">Paid</span>' : '<span class="text-sky-400">Free</span>';
            return `
              <tr class="hover:bg-slate-900/50">
                <td class="py-2 px-3 text-slate-400">${dateStr}</td>
                <td class="py-2 px-3 text-white truncate max-w-[120px]">${escapeHtml(l.endpoint)}</td>
                <td class="py-2 px-3 text-slate-300">${escapeHtml(l.model)}</td>
                <td class="py-2 px-3">${tierBadge}</td>
                <td class="py-2 px-3 text-slate-300">${l.prompt_tokens} / ${l.completion_tokens}</td>
                <td class="py-2 px-3 text-slate-400">${l.latency_ms} ms</td>
                <td class="py-2 px-3 text-emerald-400">$${(l.cost_usd || 0).toFixed(4)}</td>
                <td class="py-2 px-3 ${statusClass} font-bold">${escapeHtml(l.status)}</td>
              </tr>
            `;
          }).join('');
        }
      }
    }
  } catch (err) {
    console.error("Error al cargar analítica de tokens:", err);
  }
}

// Dictado por voz en Simulador de Consultoría
function toggleConsultingVoiceDictation() {
  const btn = document.getElementById('btn-consulting-mic');
  const icon = document.getElementById('btn-consulting-mic-icon');
  const txt = document.getElementById('btn-consulting-mic-text');
  const input = document.getElementById('consulting-user-input');

  if (state.voiceRecognition.isListening && state.voiceRecognition.target === 'consulting') {
    if (state.voiceRecognition.recognition) {
      state.voiceRecognition.recognition.stop();
    }
    if (btn && icon && txt) {
      btn.setAttribute('aria-pressed', 'false');
      icon.innerHTML = Au.icono('voz');
      txt.innerText = "Dictar";
    }
    state.voiceRecognition.isListening = false;
    state.voiceRecognition.target = null;
    return;
  }

  const rec = getSpeechRecognitionInstance();
  if (!rec) {
    alert("Reconocimiento de voz no soportado en este navegador.");
    return;
  }

  if (btn && icon && txt) {
    btn.setAttribute('aria-pressed', 'true');
    icon.innerHTML = Au.icono('punto');
    txt.innerText = "Escuchando...";
  }

  rec.lang = 'en-US';
  state.voiceRecognition.isListening = true;
  state.voiceRecognition.target = 'consulting';
  state.voiceRecognition.recognition = rec;

  rec.onresult = (e) => {
    const spoken = e.results[0][0].transcript;
    if (input) {
      const current = input.value.trim();
      input.value = current ? `${current} ${spoken}` : spoken;
    }
  };

  rec.onerror = () => {
    if (btn && icon && txt) {
      btn.setAttribute('aria-pressed', 'false');
      icon.innerHTML = Au.icono('voz');
      txt.innerText = "Dictar";
    }
    state.voiceRecognition.isListening = false;
    state.voiceRecognition.target = null;
  };

  rec.onend = () => {
    if (btn && icon && txt) {
      btn.setAttribute('aria-pressed', 'false');
      icon.innerHTML = Au.icono('voz');
      txt.innerText = "Dictar";
    }
    state.voiceRecognition.isListening = false;
    state.voiceRecognition.target = null;
  };

  try {
    rec.start();
  } catch (err) {
    console.error("Error al iniciar dictado de consultoría:", err);
  }
}

// --- DIAGNÓSTICO EVOLUTIVO & NIVEL ADAPTATIVO CON GEMINI ---
async function openEvolutionModal() {
  const modal = document.getElementById('fsrs-evolution-modal');
  if (!modal) return;
  Au.modal.abrir('fsrs-evolution-modal');

  const loading = document.getElementById('fsrs-evolution-loading');
  const results = document.getElementById('fsrs-evolution-results');
  if (loading) loading.classList.remove('hidden');
  if (results) results.classList.add('hidden');

  try {
    const res = await fetch('/api/fsrs/evolution/diagnose', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      state.evolutionDiagnosis = data;
      renderEvolutionDiagnosis(data);
    }
  } catch (err) {
    console.error("Error al obtener diagnóstico de evolución:", err);
  } finally {
    if (loading) loading.classList.add('hidden');
    if (results) results.classList.remove('hidden');
  }
}

function closeEvolutionModal() {
  Au.modal.cerrar('fsrs-evolution-modal');
}

function renderEvolutionDiagnosis(data) {
  const cefrBadge = document.getElementById('evo-cefr-badge');
  const levelName = document.getElementById('evo-level-name');
  const masteryScore = document.getElementById('evo-mastery-score');
  const globalProgress = document.getElementById('evo-global-progress');
  const summaryText = document.getElementById('evo-summary-text');
  const milestoneText = document.getElementById('evo-milestone-text');
  const modelTag = document.getElementById('evo-model-tag');
  const btnApply = document.getElementById('btn-apply-rec-level');

  if (cefrBadge) cefrBadge.innerText = data.cefr_rating || 'A1';
  if (levelName) levelName.innerText = data.recommended_level_name || 'Nivel Recomendado';
  if (masteryScore) masteryScore.innerText = `${data.mastery_score}%`;
  if (globalProgress) globalProgress.style.width = `${Math.max(5, data.mastery_score)}%`;
  if (summaryText) summaryText.innerText = data.diagnostic_summary || '';
  if (milestoneText) milestoneText.innerText = data.next_milestone || '';
  if (modelTag) {
    modelTag.innerText = `Evaluado por: ${data.model_used.includes('gemini') ? 'Google Gemini 1.5 Flash (AI Studio)' : 'Motor Heurístico FSRS v5 Local'}`;
  }

  if (btnApply) {
    btnApply.innerHTML = `${Au.icono('objetivo')} Aplicar Nivel: ${data.cefr_rating}`;
  }

  const strengthsList = document.getElementById('evo-strengths-list');
  if (strengthsList) {
    strengthsList.innerHTML = (data.strengths && data.strengths.length > 0)
      ? data.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')
      : '<li>Sesión de inicio pendiente</li>';
  }

  const focusList = document.getElementById('evo-focus-list');
  if (focusList) {
    focusList.innerHTML = (data.focus_areas && data.focus_areas.length > 0)
      ? data.focus_areas.map(f => `<li>${escapeHtml(f)}</li>`).join('')
      : '<li>Consolidar tarjetas activas</li>';
  }

  const levelsList = document.getElementById('evo-levels-list');
  if (levelsList && data.level_breakdown) {
    const statusBadges = {
      'mastered': '<span class="text-xs font-bold text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800">Dominado</span>',
      'consolidating': '<span class="text-xs font-bold text-sky-400 bg-sky-950/80 px-2 py-0.5 rounded border border-sky-800">Consolidando</span>',
      'in_progress': '<span class="text-xs font-bold text-amber-400 bg-amber-950/80 px-2 py-0.5 rounded border border-amber-800">En Progreso</span>',
      'not_started': '<span class="text-xs font-bold text-slate-500 bg-slate-800 px-2 py-0.5 rounded">Por Iniciar</span>',
    };

    levelsList.innerHTML = data.level_breakdown.map(b => `
      <div class="p-2.5 bg-slate-950/70 border border-slate-800/80 rounded-xl space-y-1.5">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="font-bold text-white uppercase tracking-wider text-xs">${escapeHtml(b.level_code)}</span>
            <span class="text-slate-300 font-medium text-xs">${escapeHtml(b.level_name)}</span>
          </div>
          <div class="flex items-center gap-2">
            ${statusBadges[b.status] || ''}
            <span class="font-mono font-bold text-xs ${b.mastery_pct >= 70 ? 'text-emerald-400' : 'text-slate-300'}">${b.mastery_pct}%</span>
          </div>
        </div>
        <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
          <div class="bg-sky-500 h-full rounded-full" style="width: ${Math.max(2, b.mastery_pct)}%"></div>
        </div>
        <div class="flex items-center justify-between text-xs text-slate-500 pt-0.5">
          <span>Repasadas: ${b.reviewed_cards} / ${b.total_cards}</span>
          <span>Retención: ${b.retention_rate}%</span>
          <span>Dominadas: ${b.mastered_cards}</span>
        </div>
      </div>
    `).join('');
  }
}

function applyRecommendedLevel() {
  if (!state.evolutionDiagnosis) return;
  const recLevel = state.evolutionDiagnosis.recommended_level;
  const code = recLevel.split('_')[0];
  selectFsrsLevel(code);
  closeEvolutionModal();
}

function startAdaptiveSession() {
  selectFsrsLevel('adaptive');
  closeEvolutionModal();
}

// --- SIMULADOR DE CONSULTORÍA IA & DISCOVERY ---
async function openConsultingSimModal() {
  const modal = document.getElementById('consulting-sim-modal');
  if (!modal) return;
  Au.modal.abrir('consulting-sim-modal');

  try {
    if (state.consultingScenarios.length === 0) {
      const res = await fetch('/api/fsrs/consulting/scenarios');
      if (res.ok) {
        state.consultingScenarios = await res.json();
      }
    }

    const select = document.getElementById('consulting-scenario-select');
    if (select && state.consultingScenarios.length > 0) {
      select.innerHTML = state.consultingScenarios.map(s => `
        <option value="${escapeHtml(s.id)}">[${escapeHtml(s.industry ? s.industry.toUpperCase() : '')}] ${escapeHtml(s.title)} (${escapeHtml(s.role)})</option>
      `).join('');
      handleSelectConsultingScenario(state.consultingScenarios[0].id);
    }
  } catch (err) {
    console.error("Error al cargar escenarios de consultoría:", err);
  }
}

function closeConsultingSimModal() {
  Au.modal.cerrar('consulting-sim-modal');
}

// Cualquier cierre (Esc, ✕, fondo o código) corta la voz y el dictado: si no, el micrófono sigue escribiendo en el modal oculto
document.getElementById('consulting-sim-modal')?.addEventListener('au:cerrado', () => {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  if (state.voiceRecognition.isListening && state.voiceRecognition.target === 'consulting') {
    toggleConsultingVoiceDictation();
  }
});

function handleSelectConsultingScenario(scenarioId) {
  const scenario = state.consultingScenarios.find(s => s.id === scenarioId);
  if (!scenario) return;

  state.currentConsultingScenario = scenario;

  document.getElementById('consulting-industry-tag').innerText = scenario.industry;
  document.getElementById('consulting-target-role').innerText = `Interlocutor: ${scenario.target_role || scenario.role || 'C-Level'}`;
  document.getElementById('consulting-background-text').innerText = scenario.client_background || scenario.background || '';
  document.getElementById('consulting-pain-text').innerText = scenario.client_pain || scenario.pain_point || '';
  document.getElementById('consulting-challenge-text').innerText = scenario.challenge_prompt || scenario.challenge || '';

  const userInput = document.getElementById('consulting-user-input');
  if (userInput) userInput.value = '';

  const feedbackContainer = document.getElementById('consulting-feedback-container');
  if (feedbackContainer) feedbackContainer.classList.add('hidden');
}

async function handleEvaluateConsulting(e) {
  e.preventDefault();
  if (!state.currentConsultingScenario) return;

  const inputEl = document.getElementById('consulting-user-input');
  const userInput = inputEl.value.trim();
  if (!userInput) return;

  const btn = document.getElementById('btn-eval-consulting');
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `${Au.icono('cargando', { clase: 'au-icono--girando' })} Evaluando...`;

  try {
    const res = await fetch('/api/fsrs/consulting/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario_id: state.currentConsultingScenario.id,
        user_response: userInput,
      }),
    });

    if (res.ok) {
      const feedback = await res.json();
      state.consultingEvaluation = feedback;

      // Renderizar feedback
      const scoreEl = document.getElementById('consulting-feedback-score');
      scoreEl.innerText = `${feedback.score}/100`;

      const badgeEl = document.getElementById('consulting-readiness-badge');
      if (feedback.score >= 80) {
        badgeEl.className = "au-insignia au-insignia--exito";
        badgeEl.innerText = "Senior Ready";
      } else if (feedback.score >= 60) {
        badgeEl.className = "au-insignia au-insignia--alerta";
        badgeEl.innerText = "Mid-Level Competent";
      } else {
        badgeEl.className = "au-insignia au-insignia--peligro";
        badgeEl.innerText = "Developing (Needs Polish)";
      }

      document.getElementById('consulting-krashen-text').innerText = `"${feedback.krashen_correction || feedback.krashen_polish}"`;
      document.getElementById('consulting-model-answer').innerText = feedback.recommended_model_answer || feedback.suggested_senior_response;
      document.getElementById('consulting-strategy-tip').innerText = feedback.consulting_tip || feedback.strategy_tip;

      const container = document.getElementById('consulting-feedback-container');
      container.classList.remove('hidden');
    }
  } catch (err) {
    console.error("Error al evaluar respuesta de consultoría:", err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

function playConsultingModelAudio() {
  let textToSpeak = "";
  if (state.consultingEvaluation) {
    textToSpeak = state.consultingEvaluation.krashen_correction || state.consultingEvaluation.recommended_model_answer || "";
  } else if (state.currentConsultingScenario) {
    textToSpeak = (state.currentConsultingScenario.recommended_phrasings && state.currentConsultingScenario.recommended_phrasings[0]) 
               || state.currentConsultingScenario.sample_roi_argument || "";
  }

  if (!textToSpeak) return;

  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.lang = state.audioConfig.accent || 'en-US';
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
  }
}

// =============================================================================
// ASISTENTE DE CONFIGURACIÓN INICIAL (ONBOARDING WIZARD)
// =============================================================================

async function checkOnboardingAutoTrigger() {
  try {
    const res = await fetch('/api/config/onboarding-status');
    if (!res.ok) return;
    const data = await res.json();
    state.wizard.status = data;
    if (data.should_show_onboarding) {
      openOnboardingWizard();
    }
  } catch (e) {
    console.error('Error al verificar estado de onboarding:', e);
  }
}

function openOnboardingWizard() {
  Au.modal.abrir('onboarding-wizard-modal');
  setWizardStep(1);
  selectWizardProvider(state.wizard.selectedProvider || 'gemini');
  refreshWizardStatus();
  loadVaultFolders();
}

function closeOnboardingWizard() {
  Au.modal.cerrar('onboarding-wizard-modal');
}

async function dismissOnboardingForNow() {
  closeOnboardingWizard();
  try {
    await fetch('/api/config/onboarding-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: true }),
    });
    showToast('Asistente omitido. Podés reabrirlo cuando quieras desde tu menú de perfil (arriba a la derecha).', 'info');
  } catch (e) {
    console.error('Error al omitir onboarding:', e);
  }
}

const WIZARD_PASOS = 4;

function setWizardStep(step) {
  state.wizard.currentStep = step;
  for (let i = 1; i <= WIZARD_PASOS; i++) {
    const content = document.getElementById(`wizard-step-${i}`);
    if (content) content.classList.toggle('hidden', i !== step);

    const ind = document.getElementById(`wizard-step-ind-${i}`);
    if (ind) {
      ind.setAttribute('aria-pressed', i === step ? 'true' : 'false');
      ind.setAttribute('aria-current', i === step ? 'step' : 'false');
    }
  }

  const btnPrev = document.getElementById('wizard-btn-prev');
  const btnSkip = document.getElementById('wizard-btn-skip');
  const btnNext = document.getElementById('wizard-btn-next');
  const btnFinish = document.getElementById('wizard-btn-finish');

  if (btnPrev) btnPrev.classList.toggle('hidden', step === 1);
  if (btnSkip) btnSkip.classList.toggle('hidden', step === WIZARD_PASOS);
  if (btnNext) btnNext.classList.toggle('hidden', step === WIZARD_PASOS);
  if (btnFinish) btnFinish.classList.toggle('hidden', step !== WIZARD_PASOS);

  if (step === 3) {
    if (!state.vaultFolders) loadVaultFolders();
    else renderVaultFolders();
  }
  if (step === WIZARD_PASOS) {
    refreshWizardStatus();
  }
}

async function wizardNext() {
  // Auto-guardado inteligente en Paso 1 si el usuario pegó una clave y pulsó Siguiente
  if (state.wizard.currentStep === 1) {
    const input = document.getElementById('wizard-key-input');
    if (input && input.value.trim().length > 5) {
      await wizardSaveAiKey();
    }
  }
  if (state.wizard.currentStep < WIZARD_PASOS) {
    setWizardStep(state.wizard.currentStep + 1);
  }
}

function wizardSkipStep() {
  if (state.wizard.currentStep < WIZARD_PASOS) {
    setWizardStep(state.wizard.currentStep + 1);
  }
}

function wizardPrev() {
  if (state.wizard.currentStep > 1) {
    setWizardStep(state.wizard.currentStep - 1);
  }
}

function selectWizardProvider(prov) {
  state.wizard.selectedProvider = prov;
  const providers = ['gemini', 'anthropic', 'openai'];
  providers.forEach(p => {
    const btn = document.getElementById(`wizard-prov-${p}`);
    if (btn) {
      btn.setAttribute('aria-pressed', p === prov ? 'true' : 'false');
    }
  });

  const label = document.getElementById('wizard-key-label');
  const input = document.getElementById('wizard-key-input');
  const tierBlock = document.getElementById('wizard-gemini-tier-block');
  const feedback = document.getElementById('wizard-key-feedback');
  const helpLink = document.getElementById('wizard-key-help-link');

  const nombres = {
    gemini: 'API Key de Google Gemini',
    anthropic: 'API Key de Anthropic Claude',
    openai: 'API Key de OpenAI GPT',
  };
  const placeholders = {
    gemini: 'AIzaSy... (Se guarda automáticamente al pulsar Siguiente)',
    anthropic: 'sk-ant-... (Se guarda automáticamente al pulsar Siguiente)',
    openai: 'sk-... (Se guarda automáticamente al pulsar Siguiente)',
  };
  const helpUrls = {
    gemini: { url: 'https://aistudio.google.com/apikey', text: 'Obtener clave gratis en Google AI Studio' },
    anthropic: { url: 'https://console.anthropic.com/settings/keys', text: 'Obtener clave en Anthropic Console' },
    openai: { url: 'https://platform.openai.com/api-keys', text: 'Obtener clave en OpenAI Platform' },
  };

  if (label) label.textContent = nombres[prov] || `API Key de ${prov}`;
  if (input) {
    input.value = '';
    input.placeholder = placeholders[prov] || 'Pegá tu clave acá...';
  }
  if (helpLink && helpUrls[prov]) {
    helpLink.href = helpUrls[prov].url;
    helpLink.innerHTML = `${Au.icono('clave')} ${helpUrls[prov].text}`;
  }
  if (tierBlock) tierBlock.classList.toggle('hidden', prov !== 'gemini');
  if (feedback) {
    feedback.textContent = '';
    feedback.classList.add('hidden');
  }

  // Verificar si el proveedor ya tiene clave configurada en status
  const badge = document.getElementById('wizard-key-status-badge');
  if (badge && state.wizard.status && state.wizard.status.ai) {
    const configured = (state.wizard.status.ai.configured_providers || []).includes(prov);
    badge.classList.toggle('hidden', !configured);
  }
}

function toggleWizardKeyVisibility() {
  const input = document.getElementById('wizard-key-input');
  if (input) {
    input.type = input.type === 'password' ? 'text' : 'password';
  }
}

async function wizardSaveAiKey() {
  const prov = state.wizard.selectedProvider || 'gemini';
  const input = document.getElementById('wizard-key-input');
  const feedback = document.getElementById('wizard-key-feedback');
  const clave = input ? input.value.trim() : '';

  if (!clave) {
    if (feedback) {
      feedback.textContent = 'Por favor, ingresá una clave antes de guardar.';
      feedback.className = 'text-xs text-rose-400 font-semibold';
      feedback.classList.remove('hidden');
    }
    return;
  }

  let nivel = 'free';
  if (prov === 'gemini') {
    const radio = document.querySelector('input[name="wizard-gemini-tier"]:checked');
    if (radio) nivel = radio.value;
  }

  if (feedback) {
    feedback.textContent = 'Guardando y cifrando clave...';
    feedback.className = 'text-xs text-slate-400 font-semibold';
    feedback.classList.remove('hidden');
  }

  try {
    const res = await fetch(`/api/config/ia/${prov}/key`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clave, nivel }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Error al guardar la clave.');

    // Fijar como proveedor activo de la cuenta
    await fetch('/api/config/ia', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proveedor_activo: prov }),
    });

    if (feedback) {
      feedback.textContent = `Clave de ${prov.toUpperCase()} guardada y activada correctamente.`;
      feedback.className = 'text-xs text-emerald-400 font-semibold';
    }
    if (input) input.value = '';

    const badge = document.getElementById('wizard-key-status-badge');
    if (badge) badge.classList.remove('hidden');

    await refreshWizardStatus();
  } catch (err) {
    pintarErrorEnFeedback(feedback, err.message);
  }
}

async function wizardTestAiKey() {
  const prov = state.wizard.selectedProvider || 'gemini';
  const feedback = document.getElementById('wizard-key-feedback');
  if (feedback) {
    feedback.textContent = `Probando conexión con ${prov.toUpperCase()}...`;
    feedback.className = 'text-xs text-sky-400 font-semibold';
    feedback.classList.remove('hidden');
  }

  try {
    const res = await fetch(`/api/config/ia/${prov}/test`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || data.detail || 'Fallo de autenticación o cuota.');

    if (feedback) {
      feedback.textContent = `Conexión exitosa: modelo '${data.modelo || 'predeterminado'}' respondió correctamente.`;
      feedback.className = 'text-xs text-emerald-400 font-semibold';
    }
    await refreshWizardStatus();
  } catch (err) {
    if (feedback) {
      feedback.textContent = `Error de conexión: ${err.message}`;
      feedback.className = 'text-xs text-rose-400 font-semibold';
    }
  }
}

async function wizardSeedDeck() {
  const btn = document.getElementById('wizard-seed-btn');
  const origHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `${Au.icono('cargando', { clase: 'au-icono--girando' })} Sembrando tarjetas...`;
  }

  try {
    const res = await fetch('/api/fsrs/seed', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      alert(`¡Mazo incorporado con éxito! Se cargaron ${data.tarjetas_sembradas || 159} tarjetas de inglés técnico.`);
      await loadFsrsStatus();
      await refreshWizardStatus();
    } else {
      alert(`Error al sembrar mazo: ${data.detail || 'Ocurrió un error inesperado.'}`);
    }
  } catch (err) {
    alert(`Error de red al sembrar mazo: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

async function refreshWizardStatus() {
  try {
    const res = await fetch('/api/config/onboarding-status');
    if (!res.ok) return;
    const data = await res.json();
    state.wizard.status = data;
    const ai = data.ai || {};
    const resData = data.data || {};

    // Badges en paso 1
    const keyBadge = document.getElementById('wizard-key-status-badge');
    if (keyBadge) {
      keyBadge.classList.toggle('hidden', !ai.ready);
    }

    // Resumen en el último paso
    const sumAi = document.getElementById('wizard-summary-ai');
    if (sumAi) {
      sumAi.textContent = ai.ready ? String(ai.proveedor_activo || 'IA').toUpperCase() : 'No configurada (Opcional)';
      sumAi.className = ai.ready ? 'font-bold text-emerald-400' : 'font-semibold text-amber-400';
    }

    const sumData = document.getElementById('wizard-summary-data');
    const hasMaterials = (resData.flashcards || 0) > 0 || (resData.total_materials || 0) > 0;
    if (sumData) {
      sumData.textContent = `${resData.flashcards || 0} tarjetas · ${resData.total_materials || 0} recursos`;
      sumData.className = hasMaterials ? 'font-bold text-emerald-400 truncate mt-0.5' : 'font-semibold text-slate-400 truncate mt-0.5';
    }

    // Actualizar checks en el Stepper (✓)
    const chk1 = document.getElementById('wizard-check-1');
    const chk2 = document.getElementById('wizard-check-2');
    const chk3 = document.getElementById('wizard-check-3');
    if (chk1) chk1.classList.toggle('hidden', !ai.ready);
    if (chk2) chk2.classList.toggle('hidden', !hasMaterials);
    const hasFolders = Boolean(state.vaultFolders && state.vaultFolders.del_tutor && state.vaultFolders.del_tutor.length);
    if (chk3) chk3.classList.toggle('hidden', !hasFolders);
  } catch (e) {
    console.error('Error al actualizar estado del wizard:', e);
  }
}

async function wizardActionAndClose(targetAction) {
  try {
    await fetch('/api/config/onboarding-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: true }),
    });
  } catch (e) {
    console.error(e);
  }
  closeOnboardingWizard();
  if (targetAction === 'book') {
    switchTab('books');
    openAddBookModal();
  } else if (targetAction === 'course') {
    switchTab('courses');
    openAddCourseModal();
  } else if (targetAction === 'roadmap') {
    switchTab('roadmap');
  }
}

async function wizardQuickStart(action) {
  try {
    await fetch('/api/config/onboarding-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: true }),
    });
  } catch (e) {
    console.error(e);
  }
  closeOnboardingWizard();
  if (action === 'plan') {
    switchTab('dashboard');
    await loadAllData();
    if (typeof generateDailyPlan === 'function') {
      generateDailyPlan();
    }
    showToast('Generando tu Plan de Estudio de hoy...', 'info');
  } else if (action === 'fsrs') {
    switchTab('fsrs');
    await loadAllData();
    if (typeof startFsrsSession === 'function') {
      startFsrsSession();
    }
    showToast('Iniciando sesión de práctica de inglés...', 'success');
  } else if (action === 'roadmap') {
    switchTab('roadmap');
    await loadAllData();
    showToast('Explorá tu Ruta de Aprendizaje y el Mapa Interactivo.', 'info');
  }
}

async function completeOnboardingWizard() {
  try {
    const res = await fetch('/api/config/onboarding-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: true }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'No se pudo guardar la finalización.');
    }
    closeOnboardingWizard();
    showToast('¡Configuración inicial lista! Bienvenido a tu entorno de estudio.', 'success');
    switchTab('dashboard');
    loadAllData();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}








// --- FEATURE 061: tokens de alcance (código de Atajos y suscripción al calendario) ---
// Cada panel muestra el estado, crea/renueva y revoca. El token en claro solo llega al crearlo.
function panelDeTokenDeAlcance(cfg) {
  const $ = (id) => document.getElementById(id);
  function pintar(estado, valor) {
    const activo = Boolean(estado && estado.activo);
    $(cfg.estado).textContent = valor
      ? cfg.textoRecienCreado
      : (activo ? cfg.textoActivo : cfg.textoInactivo);
    $(cfg.fila).classList.toggle('hidden', !valor);
    $(cfg.valor).value = valor || '';
    $(cfg.crear).textContent = activo ? cfg.textoRenovar : cfg.textoCrear;
    $(cfg.revocar).classList.toggle('hidden', !activo);
  }
  async function cargar() {
    try {
      const res = await fetch(cfg.ruta);
      if (!res.ok) throw new Error(res.statusText);
      pintar(await res.json(), null);
    } catch (err) {
      $(cfg.estado).textContent = 'No se pudo consultar el estado.';
    }
  }
  async function crear() {
    if ($(cfg.revocar).classList.contains('hidden') === false
        && !confirm(cfg.confirmarRenovar)) return;
    const res = await fetch(cfg.ruta, { method: 'POST' });
    if (!res.ok) {
      if (!res.headers.get('X-Cuenta-Compartida')) showNotification('No se pudo crear.', 'error');
      return;
    }
    const data = await res.json();
    pintar(data, data[cfg.campo]);
  }
  async function revocar() {
    if (!confirm(cfg.confirmarRevocar)) return;
    const res = await fetch(cfg.ruta, { method: 'DELETE' });
    if (!res.ok) {
      if (!res.headers.get('X-Cuenta-Compartida')) showNotification('No se pudo desactivar.', 'error');
      return;
    }
    pintar({ activo: false }, null);
  }
  function copiar() {
    navigator.clipboard.writeText($(cfg.valor).value);
    showNotification('Copiado al portapapeles', 'success');
  }
  $(cfg.crear).addEventListener('click', crear);
  $(cfg.revocar).addEventListener('click', revocar);
  $(cfg.copiar).addEventListener('click', copiar);
  return cargar;
}

let cargarTokenDeLibros = null;
let cargarFeedDelCalendario = null;

function iniciarTokensDeAlcance() {
  if (document.getElementById('shortcut-token-crear')) {
    cargarTokenDeLibros = panelDeTokenDeAlcance({
      ruta: '/api/books/sync/token', campo: 'token',
      estado: 'shortcut-token-estado', fila: 'shortcut-token-fila', valor: 'shortcut-token',
      crear: 'shortcut-token-crear', revocar: 'shortcut-token-revocar', copiar: 'shortcut-token-copiar',
      textoCrear: 'Crear mi código', textoRenovar: 'Crear un código nuevo',
      textoInactivo: 'Todavía no creaste tu código.',
      textoActivo: 'Ya tenés un código activo. Por seguridad no se vuelve a mostrar: si lo perdiste, creá uno nuevo.',
      textoRecienCreado: 'Este es tu código. Copialo ahora: no se vuelve a mostrar.',
      confirmarRenovar: 'El código anterior deja de funcionar y vas a tener que pegar el nuevo en el atajo. ¿Seguimos?',
      confirmarRevocar: 'El atajo deja de poder anotar páginas hasta que crees otro código. ¿Seguimos?',
    });
  }
  if (document.getElementById('gcal-feed-crear')) {
    cargarFeedDelCalendario = panelDeTokenDeAlcance({
      ruta: '/api/schedule/feed', campo: 'url',
      estado: 'gcal-feed-estado', fila: 'gcal-feed-url-fila', valor: 'gcal-feed-url',
      crear: 'gcal-feed-crear', revocar: 'gcal-feed-revocar', copiar: 'gcal-feed-copiar',
      textoCrear: 'Crear mi dirección', textoRenovar: 'Crear una dirección nueva',
      textoInactivo: 'La suscripción está desactivada.',
      textoActivo: 'La suscripción está activa. Por seguridad la dirección no se vuelve a mostrar: si la necesitás, creá una nueva.',
      textoRecienCreado: 'Esta es tu dirección. Copiala ahora: no se vuelve a mostrar.',
      confirmarRenovar: 'La dirección anterior deja de funcionar y vas a tener que suscribirte de nuevo. ¿Seguimos?',
      confirmarRevocar: 'Los calendarios suscritos dejan de recibir tu cronograma. ¿Seguimos?',
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', iniciarTokensDeAlcance);
} else {
  iniciarTokensDeAlcance();
}

async function cargarAtajoDeLibros() {
  if (cargarTokenDeLibros) cargarTokenDeLibros();
  const enlace = document.getElementById('shortcut-agregar');
  try {
    const res = await fetch('/api/books/sync/webhook-info');
    if (!res.ok) return;
    const info = await res.json();
    // Solo un enlace https del servidor: nunca un esquema que ejecute código
    if (enlace && typeof info.atajo_url === 'string' && info.atajo_url.startsWith('https://')) {
      enlace.href = info.atajo_url;
      enlace.classList.remove('pointer-events-none', 'opacity-50');
      enlace.removeAttribute('aria-disabled');
    }
  } catch (err) {
    console.warn('No se pudo leer la configuración del atajo:', err);
  }
}

function closeAppleShortcutsModal() {
  Au.modal.cerrar('modal-apple-shortcuts');
}

function copyShortcutUrl() {
  const input = document.getElementById('shortcut-webhook-url');
  if (input) {
    navigator.clipboard.writeText(input.value);
    showNotification('Dirección de sincronización copiada al portapapeles', 'success');
  }
}


// --- CENTRO DE DOCUMENTACIÓN & GUÍA OPERATIVA ---
let userManualRawMarkdown = '';
let currentDocType = 'manual';
const docsCache = {};

async function openUserManualModal(docType = 'manual') {
  Au.modal.abrir('modal-user-manual');
  await switchDocTab(docType);
}

function closeUserManualModal() {
  Au.modal.cerrar('modal-user-manual');
}

async function switchDocTab(docType) {
  currentDocType = docType || 'manual';

  // Actualizar estilos visuales de las pestañas
  const tabs = ['manual', 'api', 'mcp', 'cli'];
  tabs.forEach(t => {
    const btn = document.getElementById(`doc-tab-${t}`);
    if (btn) {
      btn.setAttribute('aria-selected', t === currentDocType ? 'true' : 'false');
    }
  });

  // Limpiar buscador sin re-renderizar
  clearManualSearch(false);

  // Cargar contenido (desde caché o API)
  if (docsCache[currentDocType]) {
    userManualRawMarkdown = docsCache[currentDocType];
    renderManualMarkdown(userManualRawMarkdown);
  } else {
    const container = document.getElementById('manual-modal-body');
    if (container) {
      container.innerHTML = `
        <div class="flex flex-col items-center justify-center py-20 text-slate-400 space-y-3 animate-pulse">
          <span class="text-3xl">${Au.icono('lectura', { clase: 'au-icono--grande' })}</span>
          <span class="text-xs font-semibold">Cargando documento...</span>
        </div>`;
    }
    try {
      const res = await fetch(`/api/docs/manual?doc=${currentDocType}`);
      if (res.ok) {
        const data = await res.json();
        userManualRawMarkdown = stripFrontmatter(data.content || '');
        docsCache[currentDocType] = userManualRawMarkdown;
        renderManualMarkdown(userManualRawMarkdown);
      } else {
        if (container) {
          container.innerHTML = '<div class="text-rose-400 p-6 bg-rose-950/20 border border-rose-900 rounded-2xl text-xs">No se pudo cargar la documentación solicitada.</div>';
        }
      }
    } catch (err) {
      console.error("Error al cargar documento:", err);
      if (container) {
        container.innerHTML = '<div class="text-rose-400 p-6 bg-rose-950/20 border border-rose-900 rounded-2xl text-xs">Error de conexión al cargar el documento.</div>';
      }
    }
  }

  // Estimar tiempo de lectura
  updateReadingTime(userManualRawMarkdown);
}

function stripFrontmatter(text) {
  if (!text) return '';
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '').trimStart();
}

function updateReadingTime(text) {
  const indicator = document.getElementById('doc-reading-time');
  if (!indicator) return;
  const wordCount = (text || '').split(/\s+/).filter(Boolean).length;
  const minutes = Math.max(1, Math.ceil(wordCount / 180));
  indicator.innerHTML = `${Au.icono('reloj')} ~${minutes} min de lectura (${wordCount.toLocaleString()} palabras)`;
}

function parseMarkdownAlerts(text) {
  if (!text) return '';
  // Parsea alertas estilo GitHub Markdown: > [!NOTE], > [!TIP], > [!IMPORTANT], etc.
  return text.replace(
    /(?:^|\n)>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION|INFO)\]\s*\n((?:>[^\n]*\n?)+)/gi,
    (match, type, content) => {
      const t = type.toUpperCase();
      const body = content.replace(/^>\s?/gm, '').trim();
      const meta = {
        NOTE: { icon: 'ayuda', title: 'Nota', cls: 'doc-alert-note' },
        INFO: { icon: 'ayuda', title: 'Información', cls: 'doc-alert-info' },
        TIP: { icon: 'idea', title: 'Consejo Práctico', cls: 'doc-alert-tip' },
        IMPORTANT: { icon: 'fijar', title: 'Importante', cls: 'doc-alert-important' },
        WARNING: { icon: 'alerta', title: 'Advertencia', cls: 'doc-alert-warning' },
        CAUTION: { icon: 'detener', title: 'Precaución', cls: 'doc-alert-caution' },
      }[t] || { icon: 'ayuda', title: 'Nota', cls: 'doc-alert-note' };

      return `\n\n<div class="doc-alert ${meta.cls}">` +
             `<div class="doc-alert-header"><span aria-hidden="true">${Au.icono(meta.icon)}</span> <span>${meta.title}</span></div>` +
             // marked no procesa Markdown dentro de un bloque HTML: el cuerpo se convierte acá
             `<div class="doc-alert-body">${marked.parse(body)}</div></div>\n\n`;
    }
  );
}

function renderManualMarkdown(mdText) {
  const container = document.getElementById('manual-modal-body');
  if (!container) return;

  const cleanText = stripFrontmatter(mdText);
  if (typeof marked !== 'undefined' && marked.parse) {
    const preprocessed = parseMarkdownAlerts(cleanText);
    const html = marked.parse(preprocessed);
    // Como las clases, todo HTML pasa por DOMPurify; sin la librería se muestra el texto plano
    if (!window.DOMPurify) {
      container.textContent = cleanText;
      return;
    }
    container.innerHTML = window.DOMPurify.sanitize(html, LESSON_SANITIZE_CONFIG);

    // Estilizar títulos H1
    container.querySelectorAll('h1').forEach(el => {
      el.className = "text-xl sm:text-2xl font-black text-white border-b border-slate-800 pb-3 mb-4 mt-2 flex items-center gap-2.5";
    });

    // Estilizar títulos H2 y extraer para el TOC
    const tocItems = [];
    container.querySelectorAll('h2').forEach((el, idx) => {
      let rawTitle = el.innerText.trim();
      let cleanId = el.id || rawTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
      if (!cleanId) cleanId = `section-${idx}`;
      el.id = cleanId;
      el.className = "text-base sm:text-lg font-extrabold text-sky-400 border-b border-slate-800/60 pb-1.5 mt-8 mb-3 flex items-center gap-2 scroll-mt-4";
      tocItems.push({ id: cleanId, title: rawTitle });
    });

    // Estilizar H3
    container.querySelectorAll('h3').forEach(el => {
      el.className = "text-sm sm:text-base font-bold text-indigo-300 mt-5 mb-2 flex items-center gap-1.5";
    });

    // Párrafos
    container.querySelectorAll('p').forEach(el => {
      el.className = "mb-3 text-slate-300 leading-relaxed text-xs sm:text-sm";
    });

    // Listas
    container.querySelectorAll('ul').forEach(el => {
      el.className = "list-disc pl-5 mb-4 space-y-1.5 text-slate-300 text-xs sm:text-sm";
    });
    container.querySelectorAll('ol').forEach(el => {
      el.className = "list-decimal pl-5 mb-4 space-y-1.5 text-slate-300 text-xs sm:text-sm";
    });

    // Tablas
    container.querySelectorAll('table').forEach(tbl => {
      tbl.classList.add('doc-table');
      if (tbl.parentElement && !tbl.parentElement.classList.contains('overflow-x-auto')) {
        const wrapper = document.createElement('div');
        wrapper.className = "overflow-x-auto my-4 rounded-xl border border-slate-800 bg-slate-950/40 shadow-sm";
        tbl.parentNode.insertBefore(wrapper, tbl);
        wrapper.appendChild(tbl);
      }
    });

    // Bloques de código <pre>
    container.querySelectorAll('pre').forEach(el => {
      el.className = "relative au-tarjeta au-tarjeta--hundida overflow-x-auto text-xs font-mono text-slate-200 mb-4 group shadow-inner";
      // Agregar botón copiar código
      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = "absolute right-2.5 top-2.5 au-boton au-boton--secundario au-boton--chico opacity-0 group-hover:opacity-100 transition shadow";
      copyBtn.innerHTML = `${Au.icono('copiar')} <span>Copiar</span>`;
      copyBtn.onclick = () => {
        const codeText = el.querySelector('code')?.innerText || el.innerText;
        navigator.clipboard.writeText(codeText).then(() => {
          copyBtn.innerHTML = `${Au.icono('ok')} <span class="text-emerald-300">Copiado</span>`;
          setTimeout(() => {
            copyBtn.innerHTML = `${Au.icono('copiar')} <span>Copiar</span>`;
          }, 2000);
        });
      };
      el.appendChild(copyBtn);
    });

    // Código inline
    container.querySelectorAll('code').forEach(el => {
      if (el.parentElement && el.parentElement.tagName !== 'PRE') {
        el.className = "au-insignia au-insignia--mono";
      }
    });

    // Construir Índice Dinámico (TOC)
    buildManualTOC(tocItems);
  } else {
    container.innerText = mdText;
  }
}

function buildManualTOC(items) {
  const tocContainer = document.getElementById('manual-toc-list');
  const countBadge = document.getElementById('manual-toc-count');
  if (!tocContainer) return;

  tocContainer.innerHTML = '';
  if (countBadge) countBadge.textContent = `${items.length} cap.`;

  if (items.length === 0) {
    tocContainer.innerHTML = '<div class="text-slate-500 italic p-2 text-xs">Sin secciones detectadas</div>';
    return;
  }

  items.forEach(item => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = "w-full au-boton au-boton--fantasma au-boton--bloque justify-start truncate";
    btn.title = item.title;
    btn.onclick = () => jumpManualSection(item.id);

    // Asignar icono semántico según nombre del capítulo
    const icon = getSectionIcon(item.title);
    btn.innerHTML = `<span class="shrink-0 text-slate-400 group-hover:text-sky-400 transition" aria-hidden="true">${Au.icono(icon)}</span> <span class="truncate">${escapeHtml(item.title)}</span>`;
    tocContainer.appendChild(btn);
  });
}

function getSectionIcon(title) {
  const t = title.toLowerCase();
  if (t.includes('dashboard') || t.includes('principal')) return 'inicio';
  if (t.includes('cronograma') || t.includes('agenda')) return 'agenda';
  if (t.includes('curso') || t.includes('hub')) return 'cursos';
  if (t.includes('libro') || t.includes('lectura')) return 'lectura';
  if (t.includes('ruta') || t.includes('roadmap') || t.includes('dag')) return 'rutas';
  if (t.includes('inglés') || t.includes('ingles') || t.includes('fsrs')) return 'repaso';
  if (t.includes('cerebro') || t.includes('ia') || t.includes('tutor') || t.includes('gemini')) return 'cerebro';
  if (t.includes('recall') || t.includes('quiz') || t.includes('examen')) return 'examen';
  if (t.includes('config') || t.includes('ajuste')) return 'ajustes';
  if (t.includes('admin') || t.includes('usuario')) return 'cuentas';
  if (t.includes('onboarding') || t.includes('inicio') || t.includes('primer')) return 'empezar';
  if (t.includes('api') || t.includes('endpoint')) return 'rapido';
  if (t.includes('mcp') || t.includes('conector')) return 'nube';
  if (t.includes('cli') || t.includes('comando')) return 'computadora';
  return 'fijar';
}

function filterManualContent(query) {
  if (!userManualRawMarkdown) return;
  const q = (query || '').toLowerCase().trim();
  const clearBtn = document.getElementById('btn-clear-manual-search');

  if (!q) {
    if (clearBtn) clearBtn.classList.add('hidden');
    renderManualMarkdown(userManualRawMarkdown);
    return;
  }

  if (clearBtn) clearBtn.classList.remove('hidden');

  const lines = userManualRawMarkdown.split('\n');
  const matchedLines = [];
  let currentH1 = '';
  let currentH2 = '';

  for (let line of lines) {
    if (line.startsWith('# ')) {
      currentH1 = line;
    } else if (line.startsWith('## ')) {
      currentH2 = line;
    }

    if (line.toLowerCase().includes(q)) {
      if (currentH1 && !matchedLines.includes(currentH1)) {
        matchedLines.push(currentH1);
      }
      if (currentH2 && !matchedLines.includes(currentH2)) {
        matchedLines.push(currentH2);
      }
      matchedLines.push(line);
    }
  }

  const container = document.getElementById('manual-modal-body');
  if (matchedLines.length === 0) {
    if (container) {
      container.innerHTML = `
        <div class="text-center py-16 text-slate-400 space-y-3">
          <span class="text-3xl block">${Au.icono('buscar', { clase: 'au-icono--grande' })}</span>
          <p>No se encontraron resultados para <strong class="text-white">"${escapeHtml(q)}"</strong> en este documento.</p>
          <button type="button" data-accion="config-limpiar-busqueda-manual" class="au-boton au-boton--secundario au-boton--chico">
            Limpiar búsqueda
          </button>
        </div>`;
    }
    buildManualTOC([]);
    return;
  }

  renderManualMarkdown(matchedLines.join('\n\n'));
}

function clearManualSearch(reRender = true) {
  const searchInput = document.getElementById('manual-search-input');
  if (searchInput) searchInput.value = '';
  const clearBtn = document.getElementById('btn-clear-manual-search');
  if (clearBtn) clearBtn.classList.add('hidden');
  if (reRender && userManualRawMarkdown) {
    renderManualMarkdown(userManualRawMarkdown);
  }
}

function jumpManualSection(anchorId) {
  const container = document.getElementById('manual-modal-body');
  if (!container) return;

  const searchInput = document.getElementById('manual-search-input');
  if (searchInput && searchInput.value) {
    clearManualSearch(true);
  }

  const el = document.getElementById(anchorId);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.classList.add('text-emerald-400');
    setTimeout(() => el.classList.remove('text-emerald-400'), 1500);
  }
}

function copyCourseWebhookUrl() {
  const input = document.getElementById('course-webhook-url');
  if (input) {
    navigator.clipboard.writeText(input.value);
    if (typeof showToast === 'function') showToast('URL copiada al portapapeles', 'success');
  }
}



