[
  ['abrir-cosechador-fsrs', () => openHarvesterModal()],
  ['seleccionar-nivel-fsrs', (el, datos) => selectFsrsLevel(datos.nivel)],
  ['abrir-evolucion-fsrs', () => openEvolutionModal()],
  ['abrir-simulador-consultoria', () => openConsultingSimModal()],
  ['seleccionar-mazo-ruta-fsrs', (el) => selectFsrsRoadmapDeck(el.value)],
  ['reproducir-audio-tarjeta', (el, datos, evento) => playCurrentCardAudio(evento)],
  ['alternar-grabacion-voz', (el, datos, evento) => toggleCardVoiceRecording(evento)],
  ['cambiar-acento-audio', (el) => updateAudioAccent(el.value)],
  ['cambiar-velocidad-audio', (el) => updateAudioSpeed(el.value)],
  ['alternar-modo-listening', (el) => toggleListeningMode(el.checked)],
  ['calificar-tarjeta-fsrs', (el, datos) => submitCardRating(Number(datos.calificacion))],
  ['voltear-tarjeta-fsrs', () => flipFsrsCard()],
  ['traducir-contexto-ejemplo', (el, datos, evento) => toggleContextTranslation(evento)],
  ['configurar-clave-gemini', () => promptConfigureGeminiKey()],
  ['cargar-tarjetas-extra-fsrs', () => loadFsrsSession(true)],
  ['saltar-a-tarjeta-fsrs', (el, datos) => jumpToFsrsCard(Number(datos.indice))],
  ['cambiar-seleccion-cosecha', () => updateHarvestCommitButtonState()],
  ['abrir-modal-duolingo', () => openDuolingoModal()],
  ['sincronizar-duolingo-config', (el) => syncDuolingoFromConfig(el)],
  ['modal-cambiar-canal-cosecha', (el) => handleHarvestSourceChange(el.value)],
  ['modal-previsualizar-cosecha', () => executeHarvestPreview()],
  ['modal-alternar-todas-tarjetas-cosecha', (el) => toggleAllHarvestCheckboxes(el.checked)],
  ['modal-guardar-seleccionadas-cosecha', () => commitHarvestSelected()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

// --- DUOLINGO SYNC & KPIS ---
async function loadDuolingoStatus() {
  try {
    const config = await fetch('/api/duolingo/config');
    state.duolingoUsername = config.ok ? (await config.json()).username : null;
    const res = state.duolingoUsername ? await fetch('/api/duolingo/profile') : null;
    if (res && res.ok) {
      state.duolingoProfile = await res.json();
      updateDuolingoKpis();
    } else {
      state.duolingoProfile = null;
      const saludDuo = document.getElementById('salud-duolingo-estado');
      if (saludDuo) {
        saludDuo.innerText = state.duolingoUsername ? 'Sin datos' : 'Conectar';
        saludDuo.className = 'text-slate-500 font-bold text-xs';
      }
      const saludFila = document.getElementById('salud-duolingo');
      if (saludFila) {
        saludFila.title = state.duolingoUsername
          ? `Duolingo (@${state.duolingoUsername}): todavía no se pudo leer el perfil. Clic para revisarlo.`
          : 'Duolingo: clic para conectar tu usuario y ver la racha.';
      }
    }
  } catch (err) {
    console.error("Error al cargar perfil de Duolingo:", err);
  }
  renderDuolingoConfigCard();
}

function updateDuolingoKpis() {
  const p = state.duolingoProfile;
  if (!p) return;
  const saludDuo = document.getElementById('salud-duolingo-estado');
  const xpFormatted = (p.total_xp || 0).toLocaleString();
  if (saludDuo) {
    saludDuo.innerText = `${p.streak}d (${xpFormatted} XP)`;
    saludDuo.className = 'text-emerald-400 font-bold text-xs';
  }
  const saludFila = document.getElementById('salud-duolingo');
  if (saludFila) {
    saludFila.title = `Duolingo (${escapeHtml(p.name)}): ${p.streak} días de racha • ${xpFormatted} XP acumulados. Clic para sincronizar.`;
  }
}

// Sin usuario o sin perfil leído, la cabecera abre el modal; con perfil, sincroniza
async function syncDuolingoFromHeader() {
  if (!state.duolingoProfile) {
    openDuolingoModal();
    return;
  }
  const saludDuo = document.getElementById('salud-duolingo-estado');
  if (saludDuo) saludDuo.innerText = 'Sincronizando...';
  const result = await syncDuolingoNow();
  if (result && result.status === 'error') {
    showToast(result.message || 'No se pudo sincronizar Duolingo.', 'error');
  }
}

// Sincroniza con Duolingo y recarga la cabecera y la tarjeta; devuelve el resultado o null si falló la red
async function syncDuolingoNow() {
  try {
    const res = await fetch('/api/duolingo/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const result = res.ok ? await res.json() : null;
    await loadDuolingoStatus();
    return result;
  } catch (err) {
    console.error("Error al sincronizar Duolingo:", err);
    await loadDuolingoStatus();
    return null;
  }
}

// Acepta el usuario solo o el enlace del perfil (duolingo.com/profile/<usuario>), con o sin @
function normalizarUsuarioDuolingo(texto) {
  let valor = (texto || '').trim();
  const enlace = valor.match(/duolingo\.com\/profile\/([^/?#\s]+)/i);
  if (enlace) {
    try {
      valor = decodeURIComponent(enlace[1]);
    } catch (e) {
      valor = enlace[1];
    }
  }
  return valor.replace(/^@+/, '').trim();
}

function setDuolingoModalMessage(texto, tipo = 'info') {
  const box = document.getElementById('duolingo-modal-message');
  if (!box) return;
  const estilos = {
    info: 'text-sky-200 bg-sky-950/40 border-sky-800/60',
    ok: 'text-emerald-200 bg-emerald-950/40 border-emerald-800/60',
    error: 'text-rose-200 bg-rose-950/40 border-rose-800/60',
  };
  box.textContent = texto || '';
  box.className = texto ? `text-xs rounded-xl px-3 py-2 border ${estilos[tipo] || estilos.info}` : 'hidden';
}

function duolingoProfileHtml(p) {
  const xp = (p.total_xp || 0).toLocaleString();
  const fecha = p.cached_at ? new Date(p.cached_at).toLocaleString() : '';
  return `
    <div class="grid grid-cols-3 gap-2 text-center">
      <div class="bg-slate-950/70 border border-slate-800 rounded-xl p-2.5">
        <div class="text-lg font-extrabold text-orange-300">${Au.icono('racha')} ${escapeHtml(String(p.streak || 0))}</div>
        <div class="text-xs uppercase font-bold text-slate-500">días de racha</div>
      </div>
      <div class="bg-slate-950/70 border border-slate-800 rounded-xl p-2.5">
        <div class="text-lg font-extrabold text-lime-300">${escapeHtml(xp)}</div>
        <div class="text-xs uppercase font-bold text-slate-500">XP total</div>
      </div>
      <div class="bg-slate-950/70 border border-slate-800 rounded-xl p-2.5 min-w-0">
        <div class="text-sm font-bold text-sky-300 truncate mt-1">${escapeHtml(p.current_course_title || '—')}</div>
        <div class="text-xs uppercase font-bold text-slate-500 mt-0.5">curso actual</div>
      </div>
    </div>
    ${fecha ? `<p class="text-xs text-slate-500 mt-2">Última lectura: ${escapeHtml(fecha)}${p.is_cached ? ' (guardada)' : ''}</p>` : ''}`;
}

function openDuolingoModal() {
  const input = document.getElementById('duolingo-username-input');
  if (input) input.value = state.duolingoUsername || '';
  const preview = document.getElementById('duolingo-modal-preview');
  if (preview) {
    preview.innerHTML = state.duolingoProfile ? duolingoProfileHtml(state.duolingoProfile) : '';
    preview.classList.toggle('hidden', !state.duolingoProfile);
  }
  document.getElementById('btn-duolingo-remove')?.classList.toggle('hidden', !state.duolingoUsername);
  document.getElementById('duolingo-modal-title').textContent = state.duolingoUsername ? 'Tu Duolingo' : 'Conectar Duolingo';
  setDuolingoModalMessage('');
  Au.modal.abrir('duolingo-modal');
  if (input) input.focus();
}

function closeDuolingoModal() {
  Au.modal.cerrar('duolingo-modal');
}

async function saveDuolingoUsername(event) {
  event.preventDefault();
  const input = document.getElementById('duolingo-username-input');
  const usuario = normalizarUsuarioDuolingo(input.value);
  if (!usuario) {
    setDuolingoModalMessage('Escribí tu usuario de Duolingo.', 'error');
    input.focus();
    return;
  }
  input.value = usuario;
  const boton = document.getElementById('btn-duolingo-save');
  boton.disabled = true;
  setDuolingoModalMessage('Leyendo tu perfil en Duolingo…');
  try {
    const res = await fetch('/api/duolingo/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: usuario }),
    });
    const datos = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorText(datos, 'No se pudo guardar el usuario.'));
    const result = await syncDuolingoNow();
    // Sin perfil leído del usuario nuevo, no queda a la vista el del anterior
    const preview = document.getElementById('duolingo-modal-preview');
    if (preview) {
      preview.innerHTML = state.duolingoProfile ? duolingoProfileHtml(state.duolingoProfile) : '';
      preview.classList.toggle('hidden', !state.duolingoProfile);
    }
    document.getElementById('btn-duolingo-remove')?.classList.remove('hidden');
    document.getElementById('duolingo-modal-title').textContent = 'Tu Duolingo';
    if (result && result.status !== 'error') {
      setDuolingoModalMessage(`Listo: @${datos.username || usuario} quedó conectado.`, 'ok');
    } else {
      setDuolingoModalMessage((result && result.message) || 'Se guardó el usuario, pero Duolingo no devolvió el perfil. Revisá que sea público y probá de nuevo.', 'error');
    }
  } catch (err) {
    setDuolingoModalMessage(err.message || 'Error de red al conectar Duolingo.', 'error');
  } finally {
    boton.disabled = false;
  }
}

async function removeDuolingoUsername() {
  try {
    const res = await fetch('/api/duolingo/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: null }),
    });
    const datos = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorText(datos, 'No se pudo desconectar Duolingo.'));
    await loadDuolingoStatus();
    closeDuolingoModal();
    showToast('Duolingo quedó desconectado de tu cuenta.', 'info');
  } catch (err) {
    setDuolingoModalMessage(err.message || 'Error de red al desconectar Duolingo.', 'error');
  }
}

// Tarjeta de Configuración > Duolingo: estado del usuario y del último perfil leído
function renderDuolingoConfigCard() {
  const card = document.getElementById('duolingo-config-card');
  if (!card) return;
  const usuario = state.duolingoUsername;
  if (!usuario) {
    card.innerHTML = `
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-950/60 border border-dashed border-slate-700 rounded-2xl p-5">
        <div>
          <p class="text-sm font-semibold text-white">Todavía no conectaste Duolingo</p>
          <p class="text-xs text-slate-400 mt-0.5">Con tu usuario público, la racha y el XP aparecen en la cabecera.</p>
        </div>
        ${Au.boton({
          texto: 'Conectar Duolingo',
          icono: 'idioma',
          variante: 'primario',
          accion: 'abrir-modal-duolingo'
        })}
      </div>`;
    return;
  }
  const perfil = state.duolingoProfile;
  card.innerHTML = `
    <div class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-sm font-semibold text-white truncate">@${escapeHtml(usuario)}${perfil && perfil.name ? ` <span class="text-slate-400 font-normal">· ${escapeHtml(perfil.name)}</span>` : ''}</p>
          <p class="text-xs ${perfil ? 'text-emerald-400' : 'text-amber-300'}">${perfil ? 'Conectado' : 'Todavía no se pudo leer el perfil: revisá que sea público.'}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          ${Au.boton({
            texto: 'Sincronizar ahora',
            icono: 'recargar',
            variante: 'primario',
            accion: 'sincronizar-duolingo-config'
          })}
          ${Au.boton({
            texto: 'Cambiar usuario',
            variante: 'secundario',
            accion: 'abrir-modal-duolingo'
          })}
        </div>
      </div>
      ${perfil ? duolingoProfileHtml(perfil) : ''}
    </div>`;
}

async function syncDuolingoFromConfig(boton) {
  if (boton) boton.disabled = true;
  const result = await syncDuolingoNow();
  if (result && result.status !== 'error') showToast('Duolingo sincronizado.', 'success');
  else showToast((result && result.message) || 'No se pudo sincronizar Duolingo.', 'error');
}

// --- FSRS STUDIO ---
async function loadFsrsStatus() {
  try {
    const res = await fetch('/api/fsrs/status');
    if (res.ok) {
      state.fsrsStatus = await res.json();
      updateFsrsKpis();
    }
    await loadGeminiTutorStatus();
  } catch (err) {
    console.error("Error al cargar estado FSRS:", err);
  }
}

function updateFsrsKpis() {
  if (!state.fsrsStatus) return;

  const due = state.fsrsStatus.vencidas_hoy || 0;
  const streak = state.fsrsStatus.racha_dias || 0;
  const retention = state.fsrsStatus.retencion_pct || 0;

  // Header
  document.getElementById('hdr-streak').innerHTML = `${Au.icono('racha')} ${streak} días`;
  document.getElementById('hdr-due').innerHTML = `${Au.icono('tarjetas')} ${due} para hoy`;
  document.getElementById('hdr-retention').innerHTML = `${Au.icono('objetivo')} ${retention.toFixed(0)}% retención`;
  document.getElementById('tab-fsrs-badge').innerText = due;

  // KPIs
  const kpiDue = document.getElementById('kpi-fsrs-due');
  if (kpiDue) kpiDue.innerText = due;
  const kpiStreak = document.getElementById('kpi-streak');
  if (kpiStreak) kpiStreak.innerText = `${streak} días`;
  const kpiRet = document.getElementById('kpi-retention-text');
  if (kpiRet) kpiRet.innerText = `Retención histórica: ${retention.toFixed(1)}%`;
  const deckCount = document.getElementById('fsrs-deck-count');
  if (deckCount) deckCount.innerText = `${state.fsrsStatus.tarjetas_totales} tarjetas`;

  // Companion Sidebar: Métricas FSRS v5 en Vivo
  const sbRet = document.getElementById('fsrs-sidebar-retention');
  if (sbRet) sbRet.innerText = `${retention.toFixed(0)}%`;
  const sbStreak = document.getElementById('fsrs-sidebar-streak');
  if (sbStreak) sbStreak.innerText = `${streak}d`;
  const sbDue = document.getElementById('fsrs-sidebar-due');
  if (sbDue) sbDue.innerText = due;
  const sbTot = document.getElementById('fsrs-sidebar-total');
  if (sbTot) sbTot.innerText = state.fsrsStatus.tarjetas_totales || 0;

  const cog = state.fsrsStatus.estado_cognitivo || {};
  const elNew = document.getElementById('fsrs-stat-new');
  if (elNew) elNew.innerText = cog.new || 0;
  const elLearn = document.getElementById('fsrs-stat-learning');
  if (elLearn) elLearn.innerText = cog.learning || 0;
  const elRev = document.getElementById('fsrs-stat-review');
  if (elRev) elRev.innerText = cog.review || 0;
  const elRelearn = document.getElementById('fsrs-stat-relearning');
  if (elRelearn) elRelearn.innerText = cog.relearning || 0;
}

let fsrsSessionRequestSeq = 0;

async function loadFsrsSession(force = false) {
  const btn = document.getElementById('btn-fsrs-extra-cards');
  if (btn && force) {
    btn.innerHTML = '<span class="animate-spin">' + Au.icono('cargando') + '</span> Cargando tarjetas...';
  }
  try {
    const lvl = state.fsrsSelectedLevel;
    const levelQuery = lvl && lvl !== 'all' ? `&level=${encodeURIComponent(lvl)}` : '';
    const forceQuery = force ? '&force=true' : '';
    loadFsrsRoadmapDecks();
    const pedido = ++fsrsSessionRequestSeq;
    const res = await fetch(`/api/fsrs/due?limit=10${levelQuery}${forceQuery}`);
    if (res.ok) {
      const cards = await res.json();
      // Si mientras tanto se eligió otro nivel o ruta, esta respuesta ya es vieja.
      if (pedido !== fsrsSessionRequestSeq) return;
      state.fsrsCards = cards;
      state.currentCardIndex = 0;
      state.isCardFlipped = false;
      renderCurrentCard();
    }
  } catch (err) {
    console.error("Error al cargar sesión FSRS:", err);
  } finally {
    if (btn) {
      btn.innerHTML = Au.icono('recargar') + ' <span>Repasar 10 tarjetas más</span>';
    }
  }
}

async function loadFsrsRoadmapDecks() {
  const row = document.getElementById('fsrs-roadmap-deck-row');
  const select = document.getElementById('fsrs-roadmap-deck-select');
  if (!row || !select) return;
  let decks = [];
  try {
    const res = await fetch('/api/fsrs/decks');
    // Si no se pudieron consultar los mazos se deja el selector como estaba.
    if (!res.ok) return;
    decks = await res.json();
  } catch (err) {
    console.error("Error al cargar los mazos de rutas:", err);
    return;
  }
  state.fsrsRoadmapDecks = decks;
  const elegido = String(state.fsrsSelectedLevel || '').startsWith('roadmap_') ? state.fsrsSelectedLevel : '';
  select.innerHTML = '';
  const porNivel = document.createElement('option');
  porNivel.value = '';
  porNivel.textContent = 'Repasar por nivel (todas las tarjetas)';
  select.appendChild(porNivel);
  decks.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.categoria;
    opt.textContent = `${d.titulo} — ${d.total} ${d.total === 1 ? 'tarjeta' : 'tarjetas'}, ${d.vencidas} para hoy`;
    select.appendChild(opt);
  });
  const sigueExistiendo = decks.some(d => d.categoria === elegido);
  select.value = sigueExistiendo ? elegido : '';
  row.classList.toggle('hidden', decks.length === 0);
  row.classList.toggle('flex', decks.length > 0);
  // El mazo elegido ya no existe (se quedó sin tarjetas): volver al repaso por nivel.
  if (elegido && !sigueExistiendo) selectFsrsLevel('all');
}

function selectFsrsRoadmapDeck(categoria) {
  // Sin ruta elegida se vuelve al repaso por nivel, con todas las tarjetas.
  selectFsrsLevel(categoria || 'all');
}

function selectFsrsLevel(lvl) {
  state.fsrsSelectedLevel = lvl;
  const deckSelect = document.getElementById('fsrs-roadmap-deck-select');
  if (deckSelect) deckSelect.value = String(lvl).startsWith('roadmap_') ? lvl : '';

  // Actualizar aria-selected en las pestañas de nivel
  const buttons = document.querySelectorAll('.fsrs-lvl-btn');
  buttons.forEach(btn => {
    const esActivo = btn.id === `btn-lvl-${lvl}`;
    btn.setAttribute('aria-selected', esActivo ? 'true' : 'false');
  });

  loadFsrsSession(true);
}

function extractSpanishTranslation(pregunta) {
  if (!pregunta) return '';
  let cleaned = pregunta.trim();
  const m = cleaned.match(/[¿Cc]ómo (?:decir|se dice)\s+['"“‘](.+?)['"”’](\s*\(.+?\))?\??/i);
  if (m) {
    const term = m[1].trim();
    const extra = m[2] ? ` ${m[2].trim()}` : '';
    return `${term}${extra}`;
  }
  const m2 = cleaned.match(/['"“‘](.+?)['"”’]/);
  if (m2) return m2[1].trim();
  return cleaned.replace(/^[¿?¡!\s]*[Cc]ómo (?:decir|se dice)\s*/i, '')
                .replace(/[\s¿?¡!]+$/g, '');
}

function renderCurrentCard() {
  const player = document.getElementById('fsrs-player-container');
  const complete = document.getElementById('fsrs-complete-container');

  if (state.fsrsCards.length === 0 || state.currentCardIndex >= state.fsrsCards.length) {
    player.classList.add('hidden');
    complete.classList.remove('hidden');
    renderFsrsSessionQueue();
    return;
  }

  player.classList.remove('hidden');
  complete.classList.add('hidden');

  const card = state.fsrsCards[state.currentCardIndex];
  state.isCardFlipped = false;

  // Reset visuales de tarjeta de forma inmediata (frente visible, reverso oculto)
  const frontEl = document.getElementById('fsrs-card-front');
  const backEl = document.getElementById('fsrs-card-back');
  if (frontEl) frontEl.classList.remove('hidden');
  if (backEl) backEl.classList.add('hidden');

  const levelLabels = {
    'a1_foundations': `${Au.icono('punto', { clase: 'text-emerald-400' })} A1 BASES`,
    'a2_daily_work': `${Au.icono('punto', { clase: 'text-amber-400' })} A2 STANDUPS & SYNC`,
    'b1_data_storytelling': `${Au.icono('punto', { clase: 'text-orange-300' })} B1 DATA STORYTELLING`,
    'b2_tech_data_ai': `${Au.icono('punto', { clase: 'text-sky-400' })} B2 TECH & CLOUD AI`,
    'c1_consulting_ai': `${Au.icono('punto', { clase: 'text-purple-400' })} C1 CONSULTING & DISCOVERY`,
  };
  const mazoDeRuta = (state.fsrsRoadmapDecks || []).find(d => d.categoria === card.categoria);
  const categoryLabel = levelLabels[card.categoria] || (mazoDeRuta ? mazoDeRuta.titulo : (card.categoria ? escapeHtml(card.categoria.replace(/_/g, ' ').toUpperCase()) : 'GENERAL'));

  const counterEl = document.getElementById('fsrs-card-counter');
  if (counterEl) counterEl.innerText = `Tarjeta ${state.currentCardIndex + 1} de ${state.fsrsCards.length}`;

  const catEl = document.getElementById('fsrs-card-category');
  if (catEl) catEl.innerHTML = categoryLabel;

  const esMazoIngles = !String(card.categoria || '').startsWith('roadmap_');

  const backTextEl = document.getElementById('fsrs-back-text');
  if (backTextEl) {
    backTextEl.innerText = card.respuesta_esperada || '';
    if (esMazoIngles) {
      backTextEl.setAttribute('lang', 'en');
    } else {
      backTextEl.removeAttribute('lang');
    }
  }

  // Traducción técnica al español en pequeño
  const spanishTerm = extractSpanishTranslation(card.item_pregunta);
  const translationEl = document.getElementById('fsrs-back-translation');
  if (translationEl) {
    translationEl.innerText = spanishTerm || card.item_pregunta || '';
  }

  const backCtxEl = document.getElementById('fsrs-back-context');
  if (backCtxEl) {
    backCtxEl.innerText = card.contexto_uso ? `"${card.contexto_uso}"` : "Colocación profesional técnica.";
    if (esMazoIngles && card.contexto_uso) {
      backCtxEl.setAttribute('lang', 'en');
    } else {
      backCtxEl.removeAttribute('lang');
    }
  }

  // Reset traducción opcional del ejemplo de uso
  const ctxEs = document.getElementById('fsrs-back-context-es');
  if (ctxEs) {
    ctxEs.classList.add('hidden');
    ctxEs.innerText = '';
  }
  const btnTrans = document.getElementById('btn-translate-context');
  if (btnTrans) {
    btnTrans.innerHTML = Au.icono('web') + ' <span>Traducir ejemplo</span>';
  }

  const statsPreviewEl = document.getElementById('fsrs-card-stats-preview');
  if (statsPreviewEl) {
    const diff = (card.difficulty != null && !isNaN(card.difficulty)) ? Number(card.difficulty).toFixed(1) : 'Nuevo';
    const reps = card.reps != null ? card.reps : (card.racha || 0);
    statsPreviewEl.innerText = `Repasos: ${reps} • Dificultad: ${diff}`;
  }

  if (state.audioConfig.listeningMode) {
    const frontText = document.getElementById('fsrs-front-text');
    if (frontText) frontText.innerHTML = Au.icono('audio') + " [Listening Mode] Escucha la colocación y repítela antes de voltear...";
    const stateLabel = document.getElementById('fsrs-card-state-label');
    if (stateLabel) stateLabel.innerHTML = Au.icono('audio') + " Escucha con atención & Shadowing";
    setTimeout(() => {
      if (state.audioConfig.listeningMode && !state.isCardFlipped) {
        playCurrentCardAudio();
      }
    }, 250);
  } else {
    const frontText = document.getElementById('fsrs-front-text');
    if (frontText) frontText.innerText = card.item_pregunta || '';
    const stateLabel = document.getElementById('fsrs-card-state-label');
    if (stateLabel) stateLabel.innerText = "Pregunta / Significado";
  }

  // Deshabilitar botones de calificación hasta flip
  const buttons = document.getElementById('fsrs-rating-buttons');
  if (buttons) {
    buttons.classList.add('opacity-50', 'pointer-events-none');
  }
  clearRatingButtonHighlights();

  // Reset feedback de evaluación de voz
  const evalBox = document.getElementById('fsrs-voice-eval-box');
  if (evalBox) evalBox.classList.add('hidden');
  resetVoiceRecordingButton();

  // Reset hint y botón de avance rápido
  const flipHint = document.getElementById('fsrs-card-flip-hint');
  if (flipHint) {
    flipHint.innerHTML = "Presioná [Espacio] o hacé clic para voltear " + Au.icono('recargar');
    flipHint.classList.remove('text-emerald-400');
  }
  const advanceBtn = document.getElementById('fsrs-quick-advance-container');
  if (advanceBtn) advanceBtn.classList.add('hidden');

  // Actualizar barra de progreso de la sesión
  const progressBar = document.getElementById('fsrs-session-progress-bar');
  if (progressBar) {
    const total = state.fsrsCards.length || 1;
    const current = Math.min(state.currentCardIndex + 1, total);
    const pct = Math.max(0, Math.min(100, Math.round((current / total) * 100)));
    progressBar.value = pct;
  }

  // Actualizar cola de tarjetas en el companion sidebar
  renderFsrsSessionQueue();
}

function renderFsrsSessionQueue() {
  const listEl = document.getElementById('fsrs-session-queue-list');
  const countBadge = document.getElementById('fsrs-queue-count-badge');
  if (!listEl) return;

  const total = (state.fsrsCards || []).length;
  if (total === 0) {
    listEl.innerHTML = '<div class="text-center py-6 text-slate-500 italic">No hay tarjetas en la sesión</div>';
    if (countBadge) countBadge.innerText = '0 tarjetas';
    return;
  }

  const remaining = Math.max(0, total - state.currentCardIndex);
  if (countBadge) countBadge.innerText = `${remaining} ${remaining === 1 ? 'pendiente' : 'pendientes'}`;

  let html = '';
  state.fsrsCards.forEach((c, idx) => {
    const isActive = idx === state.currentCardIndex;
    const isDone = idx < state.currentCardIndex;
    const rawPreview = extractSpanishTranslation(c.item_pregunta) || c.item_pregunta || `Tarjeta ${idx + 1}`;
    const preview = rawPreview.length > 36 ? rawPreview.slice(0, 34) + '...' : rawPreview;

    let itemClass = "flex items-center justify-between p-2 rounded-xl transition cursor-pointer select-none border ";
    let badgeHtml = '';

    if (isActive) {
      itemClass += "bg-sky-950/70 border-sky-500/60 shadow-sm shadow-sky-950/50";
      badgeHtml = '<span class="au-insignia au-insignia--primario au-insignia--mono animate-pulse shrink-0 font-extrabold">▶ Activa</span>';
    } else if (isDone) {
      itemClass += "bg-slate-950/40 border-emerald-900/40 text-slate-400 hover:bg-slate-900/60";
      badgeHtml = '<span class="au-insignia au-insignia--exito au-insignia--mono shrink-0 font-bold">' + Au.icono('ok') + ' Hecho</span>';
    } else {
      itemClass += "bg-slate-950/40 border-slate-800/60 text-slate-400 hover:bg-slate-900/60 hover:text-slate-200";
      badgeHtml = `<span class="au-insignia au-insignia--mono shrink-0">#${idx + 1}</span>`;
    }

    html += `
      <div data-accion="saltar-a-tarjeta-fsrs" data-indice="${idx}" class="${itemClass}" title="Clic para ir a la tarjeta ${idx + 1}">
        <div class="flex items-center gap-2 min-w-0 pr-1">
          <span class="w-5 h-5 rounded-lg flex items-center justify-center text-xs font-mono font-bold shrink-0 ${isActive ? 'bg-sky-600 text-white' : isDone ? 'bg-emerald-950 text-emerald-400' : 'bg-slate-800 text-slate-400'}">${idx + 1}</span>
          <span class="truncate text-xs ${isActive ? 'font-bold text-white' : isDone ? 'line-through text-slate-500' : 'text-slate-300'}">${escapeHtml(preview)}</span>
        </div>
        <div class="shrink-0">${badgeHtml}</div>
      </div>
    `;
  });

  listEl.innerHTML = html;
}

function jumpToFsrsCard(index) {
  if (index >= 0 && index < state.fsrsCards.length) {
    state.currentCardIndex = index;
    state.isCardFlipped = false;
    renderCurrentCard();
  }
}

async function toggleContextTranslation(event) {
  if (event) event.stopPropagation();
  const ctxEs = document.getElementById('fsrs-back-context-es');
  const btnTrans = document.getElementById('btn-translate-context');
  if (!ctxEs || !btnTrans) return;

  if (!ctxEs.classList.contains('hidden')) {
    ctxEs.classList.add('hidden');
    btnTrans.innerHTML = Au.icono('web') + ' <span>Traducir ejemplo</span>';
    return;
  }

  const card = state.fsrsCards[state.currentCardIndex];
  if (!card || !card.contexto_uso) return;

  if (card._contexto_uso_es) {
    ctxEs.innerText = `🇪🇸 ${card._contexto_uso_es}`;
    ctxEs.classList.remove('hidden');
    btnTrans.innerHTML = '<span>Ocultar traducción</span>';
    return;
  }

  btnTrans.innerHTML = '<span class="animate-pulse">Traduciendo...</span>';
  try {
    const res = await fetch('/api/fsrs/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: card.contexto_uso, target_lang: 'es' })
    });
    if (res.ok) {
      const data = await res.json();
      card._contexto_uso_es = data.translated_text;
      ctxEs.innerText = `🇪🇸 ${data.translated_text}`;
      ctxEs.classList.remove('hidden');
      btnTrans.innerHTML = '<span>Ocultar traducción</span>';
    } else {
      btnTrans.innerHTML = Au.icono('web') + ' <span>Traducir ejemplo</span>';
    }
  } catch (err) {
    console.error("Error al traducir ejemplo:", err);
    btnTrans.innerHTML = Au.icono('web') + ' <span>Traducir ejemplo</span>';
  }
}

function updateAudioAccent(val) {
  state.audioConfig.accent = val;
}

function updateAudioSpeed(val) {
  state.audioConfig.speed = parseFloat(val) || 1.0;
}

function toggleListeningMode(checked) {
  state.audioConfig.listeningMode = checked;
  const bg = document.getElementById('fsrs-listening-toggle-bg');
  const knob = document.getElementById('fsrs-listening-toggle-knob');
  if (bg && knob) {
    if (checked) {
      bg.className = "w-8 h-4.5 bg-emerald-500 rounded-full transition-colors relative";
      knob.className = "w-3.5 h-3.5 bg-white rounded-full transition-transform translate-x-3.5 mt-0.5";
    } else {
      bg.className = "w-8 h-4.5 bg-slate-700 rounded-full transition-colors relative";
      knob.className = "w-3.5 h-3.5 bg-white rounded-full transition-transform translate-x-0.5 mt-0.5";
    }
  }
  renderCurrentCard();
}

function playCurrentCardAudio(event) {
  if (event) event.stopPropagation();
  if (state.fsrsCards.length === 0 || state.currentCardIndex >= state.fsrsCards.length) return;

  const card = state.fsrsCards[state.currentCardIndex];
  const phrase = card.respuesta_esperada;

  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(phrase);
    utterance.lang = state.audioConfig.accent || 'en-US';
    utterance.rate = state.audioConfig.speed || 1.0;

    const voices = window.speechSynthesis.getVoices();
    const targetLang = (state.audioConfig.accent || 'en-US').toLowerCase();
    const voice = voices.find(v => v.lang.toLowerCase().replace('_', '-').startsWith(targetLang.slice(0, 5)))
               || voices.find(v => v.lang.toLowerCase().startsWith('en'));
    if (voice) utterance.voice = voice;

    window.speechSynthesis.speak(utterance);
  } else {
    // Fallback: llamada al backend
    fetch('/api/fsrs/audio/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: phrase,
        accent: state.audioConfig.accent,
        speed: state.audioConfig.speed,
      })
    }).then(r => r.json()).then(data => {
      console.log("Audio phonetic guide:", data.phonetic_guide);
    });
  }
}

function revealCard() {
  if (state.isCardFlipped) return;
  state.isCardFlipped = true;

  const frontEl = document.getElementById('fsrs-card-front');
  const backEl = document.getElementById('fsrs-card-back');
  if (frontEl) frontEl.classList.add('hidden');
  if (backEl) backEl.classList.remove('hidden');

  const stateLabel = document.getElementById('fsrs-card-state-label');
  if (stateLabel) stateLabel.innerText = "Respuesta Revelada";

  const flipHint = document.getElementById('fsrs-card-flip-hint');
  if (flipHint) {
    flipHint.innerHTML = "Presioná [Espacio] o hacé clic para avanzar " + Au.icono('saltar');
    flipHint.classList.add('text-emerald-400');
  }

  const buttons = document.getElementById('fsrs-rating-buttons');
  if (buttons) buttons.classList.remove('opacity-50', 'pointer-events-none');

  const advanceBtn = document.getElementById('fsrs-quick-advance-container');
  if (advanceBtn) advanceBtn.classList.remove('hidden');
}

function flipFsrsCard() {
  if (state.isEvaluatingVoice || (state.voiceRecognition && state.voiceRecognition.isListening)) {
    return;
  }
  if (state.isCardFlipped) {
    // Si la tarjeta ya está revelada, avanzar a la siguiente con calificación 'Good' (3)
    submitCardRating(3);
    return;
  }
  revealCard();
}


async function submitCardRating(rating) {
  if (!state.isCardFlipped) return;
  const card = state.fsrsCards[state.currentCardIndex];

  try {
    const res = await fetch('/api/fsrs/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ card_id: card.id, rating: rating }),
    });

    if (res.ok) {
      state.currentCardIndex++;
      clearRatingButtonHighlights();
      await loadFsrsStatus();
      renderCurrentCard();
    }
  } catch (err) {
    console.error("Error al registrar calificación FSRS:", err);
  }
}

// --- RECONOCIMIENTO DE VOZ, SHADOWING & EVALUACIÓN FONÉTICA ---
function getSpeechRecognitionInstance() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;
  const rec = new SpeechRecognition();
  rec.continuous = false;
  rec.interimResults = false;
  return rec;
}

function resetVoiceRecordingButton() {
  const btn = document.getElementById('btn-voice-rec');
  const icon = document.getElementById('btn-voice-rec-icon');
  const txt = document.getElementById('btn-voice-rec-text');
  if (btn && icon && txt) {
    btn.className = "au-boton au-boton--secundario au-boton--chico";
    icon.innerHTML = Au.icono('voz');
    txt.innerText = "Hablar (Shadowing)";
  }
  if (state.voiceRecognition.target === 'card') {
    state.voiceRecognition.isListening = false;
    state.voiceRecognition.target = null;
  }
}

function clearRatingButtonHighlights() {
  const buttons = document.querySelectorAll('#fsrs-rating-buttons button');
  buttons.forEach(b => {
    b.classList.remove('ring-4', 'ring-sky-400', 'scale-105', 'shadow-lg');
  });
}

function highlightSuggestedRatingButton(suggestedRating) {
  clearRatingButtonHighlights();
  const buttons = document.querySelectorAll('#fsrs-rating-buttons button');
  const targetIndex = suggestedRating - 1;
  if (buttons && buttons[targetIndex]) {
    buttons[targetIndex].classList.add('ring-4', 'ring-sky-400', 'scale-105', 'shadow-lg');
  }
}

function toggleCardVoiceRecording(event) {
  if (event) event.stopPropagation();
  if (state.fsrsCards.length === 0 || state.currentCardIndex >= state.fsrsCards.length) return;

  if (state.voiceRecognition.isListening && state.voiceRecognition.target === 'card') {
    if (state.voiceRecognition.recognition) {
      state.voiceRecognition.recognition.stop();
    }
    resetVoiceRecordingButton();
    return;
  }

  const rec = getSpeechRecognitionInstance();
  if (!rec) {
    alert("El reconocimiento de voz Web Speech API no está soportado en este navegador. Te recomendamos usar Google Chrome o Microsoft Edge.");
    return;
  }

  const card = state.fsrsCards[state.currentCardIndex];
  const btn = document.getElementById('btn-voice-rec');
  const icon = document.getElementById('btn-voice-rec-icon');
  const txt = document.getElementById('btn-voice-rec-text');
  const evalBox = document.getElementById('fsrs-voice-eval-box');
  const evalVerdict = document.getElementById('fsrs-voice-eval-verdict');
  const evalBadge = document.getElementById('fsrs-voice-eval-badge');
  const evalSpoken = document.getElementById('fsrs-voice-eval-spoken');
  const evalTip = document.getElementById('fsrs-voice-eval-tip');
  const evalHint = document.getElementById('fsrs-voice-eval-rating-hint');

  // UI activo
  if (btn && icon && txt) {
    btn.className = "au-boton au-boton--peligro au-boton--chico animate-pulse";
    icon.innerHTML = Au.icono('punto', { clase: 'text-rose-500' });
    txt.innerText = "Escuchando...";
  }

  if (evalBox) {
    evalBox.classList.remove('hidden');
    evalVerdict.innerText = "Escuchando tu pronunciación...";
    evalBadge.innerText = "EN VIVO";
    evalBadge.className = "au-insignia au-insignia--peligro animate-pulse font-extrabold";
    evalSpoken.innerText = "Pronuncia en voz alta en inglés...";
    evalTip.innerText = "Habla claro y a ritmo natural.";
    evalHint.innerText = "Sugerencia de Repaso: Pendiente...";
  }

  rec.lang = state.audioConfig.accent || 'en-US';
  state.voiceRecognition.isListening = true;
  state.voiceRecognition.target = 'card';
  state.voiceRecognition.recognition = rec;

  rec.onresult = async (e) => {
    if (!e.results || !e.results[0] || !e.results[0][0]) return;
    const spoken = e.results[0][0].transcript;
    if (evalSpoken) evalSpoken.innerText = `"${spoken}"`;
    if (evalVerdict) evalVerdict.innerText = "Evaluando exactitud fonética...";

    state.isEvaluatingVoice = true;
    try {
      const res = await fetch('/api/fsrs/audio/gemini-evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_text: card.respuesta_esperada,
          spoken_text: spoken,
          context_type: 'shadowing',
        })
      });

      if (res.ok) {
        const evalData = await res.json();
        if (evalVerdict) evalVerdict.innerText = evalData.verdict;
        if (evalBadge) {
          evalBadge.innerText = `${evalData.accuracy_score}% Match`;
          if (evalData.accuracy_score >= 85) {
            evalBadge.className = "au-insignia au-insignia--exito font-extrabold";
          } else if (evalData.accuracy_score >= 60) {
            evalBadge.className = "au-insignia au-insignia--primario font-extrabold";
          } else if (evalData.accuracy_score >= 40) {
            evalBadge.className = "au-insignia au-insignia--alerta font-extrabold";
          } else {
            evalBadge.className = "au-insignia au-insignia--peligro font-extrabold";
          }
        }

        const modelBadge = document.getElementById('fsrs-voice-eval-model');
        if (modelBadge) {
          if (evalData.is_fallback) {
            modelBadge.innerHTML = Au.icono('rapido') + ' Fallback Local';
            modelBadge.className = "au-insignia au-insignia--alerta cursor-pointer flex items-center gap-1";
          } else {
            modelBadge.innerHTML = Au.icono('generar') + ' Gemini 1.5 Flash';
            modelBadge.className = "au-insignia au-insignia--primario cursor-pointer flex items-center gap-1";
          }
        }

        if (evalSpoken) evalSpoken.textContent = `"${spoken}"`;

        if (evalTip) evalTip.innerText = evalData.phonetic_feedback || '';
        const consultingTipEl = document.getElementById('fsrs-voice-consulting-tip');
        if (consultingTipEl) {
          consultingTipEl.innerText = evalData.consulting_tip || 'Entrega concisa y con dicción profesional.';
        }

        const ratingNames = ['Again (1)', 'Hard (2)', 'Good (3)', 'Easy (4)'];
        const ratingIdx = (evalData.suggested_fsrs_rating || 3) - 1;
        if (evalHint) evalHint.innerText = `Sugerencia de Repaso: ${ratingNames[ratingIdx] || 'Good (3)'}`;

        // Revelar respuesta para feedback visual inmediato (NUNCA avanzar a la siguiente tarjeta)
        revealCard();
        highlightSuggestedRatingButton(evalData.suggested_fsrs_rating || 3);
      }
    } catch (err) {
      console.error("Error al evaluar pronunciación con Gemini:", err);
      if (evalVerdict) evalVerdict.innerText = "Error en evaluación de voz.";
    } finally {
      state.isEvaluatingVoice = false;
    }
  };

  rec.onerror = (e) => {
    console.warn("Speech recognition error:", e.error);
    if (evalVerdict) evalVerdict.innerText = "No se detectó audio claro o permiso denegado.";
    resetVoiceRecordingButton();
  };

  rec.onend = () => {
    resetVoiceRecordingButton();
  };

  try {
    rec.start();
  } catch (err) {
    console.error("No se pudo iniciar el micrófono:", err);
    resetVoiceRecordingButton();
  }
}

// --- HARVESTER OMNICANAL DE FLASHCARDS FSRS ---
state.harvestCandidates = [];

function openHarvesterModal() {
  const modal = document.getElementById('fsrs-harvester-modal');
  if (!modal) return;
  Au.modal.abrir('fsrs-harvester-modal');
  handleHarvestSourceChange(document.getElementById('harvester-source-select').value);
}

function closeHarvesterModal() {
  Au.modal.cerrar('fsrs-harvester-modal');
}

async function loadHarvestRoadmapOptions() {
  const select = document.getElementById('harvester-roadmap-select');
  if (!select) return;
  let roadmaps = state.roadmaps || [];
  if (roadmaps.length === 0) {
    try {
      const res = await fetch('/api/roadmap');
      if (res.ok) roadmaps = await res.json();
    } catch (_) {}
  }
  const elegido = select.value;
  select.innerHTML = '';
  const sinRuta = document.createElement('option');
  sinRuta.value = '';
  sinRuta.textContent = 'Sin ruta: tarjetas de inglés técnico';
  select.appendChild(sinRuta);
  roadmaps.forEach(r => {
    const opt = document.createElement('option');
    opt.value = String(r.id);
    opt.textContent = r.titulo;
    select.appendChild(opt);
  });
  select.value = elegido;
}

// Los materiales de la cuenta para cosechar de uno en particular; el nombre va como texto, no como HTML
async function loadHarvestMaterialOptions() {
  const select = document.getElementById('harvester-material-select');
  if (!select) return;
  await loadMisMateriales();
  const elegido = select.value;
  select.innerHTML = '';
  const todos = document.createElement('option');
  todos.value = '';
  todos.textContent = 'Buscar el tema en todos mis materiales';
  select.appendChild(todos);
  misMateriales.lista.forEach(m => {
    const opt = document.createElement('option');
    opt.value = String(m.id);
    opt.textContent = m.nombre;
    select.appendChild(opt);
  });
  select.value = misMateriales.lista.some(m => String(m.id) === elegido) ? elegido : '';
}

function handleHarvestSourceChange(source) {
  const label = document.getElementById('harvester-topic-label');
  const input = document.getElementById('harvester-topic-input');
  const roadmapRow = document.getElementById('harvester-roadmap-row');
  if (roadmapRow) {
    roadmapRow.classList.toggle('hidden', source !== 'materiales');
    if (source === 'materiales') {
      loadHarvestRoadmapOptions();
      loadHarvestMaterialOptions();
    }
  }
  if (!label || !input) return;

  if (source === 'vault') {
    label.innerText = "Filtro de búsqueda (opcional)";
    input.placeholder = "Dejar vacío para escanear todo Mis notas...";
  } else if (source === 'materiales') {
    label.innerText = "Tema a buscar en tus materiales";
    input.placeholder = "Ej. el tema que querés repasar (opcional si elegís un material)";
  } else {
    label.innerText = "Tecnología / Tema a Generar";
    input.placeholder = "Ej. el tema que estás estudiando";
  }
}

function harvestPreviewPayload(source, topic, level) {
  const payload = { source, topic, level, limit: 15 };
  if (source !== 'materiales') return payload;
  const materialSelect = document.getElementById('harvester-material-select');
  if (materialSelect && materialSelect.value) {
    payload.material_id = Number(materialSelect.value);
  }
  const roadmapSelect = document.getElementById('harvester-roadmap-select');
  if (roadmapSelect && roadmapSelect.value) {
    payload.roadmap_id = Number(roadmapSelect.value);
  }
  return payload;
}

async function executeHarvestPreview() {
  const source = document.getElementById('harvester-source-select').value;
  const topic = document.getElementById('harvester-topic-input').value.trim();
  const level = document.getElementById('harvester-level-select').value;
  const container = document.getElementById('harvester-candidates-container');
  const countLabel = document.getElementById('harvester-count-label');
  const commitBtn = document.getElementById('btn-harvest-commit');
  const statusInfo = document.getElementById('harvester-status-info');

  container.innerHTML = `
    <div class="text-center py-8 space-y-2">
      <span class="text-2xl animate-spin inline-block">${Au.icono('cargando')}</span>
      <p class="text-xs text-slate-400">Extrayendo colocaciones y analizando duplicados...</p>
    </div>
  `;
  commitBtn.disabled = true;

  try {
    const res = await fetch('/api/fsrs/harvest/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(harvestPreviewPayload(source, topic, level))
    });

    if (res.ok) {
      const candidates = await res.json();
      state.harvestCandidates = candidates;
      renderHarvestCandidates();
    } else {
      const err = await res.json();
      const detalle = typeof err.detail === 'string' ? err.detail : 'No se pudo completar la cosecha.';
      // La cosecha desde los materiales explica por qué no hay tarjetas (sin materiales, sin coincidencias, sin IA).
      container.innerHTML = source === 'materiales'
        ? `<p class="text-xs text-amber-300 text-center py-6">${escapeHtml(detalle)}</p>`
        : `<p class="text-xs text-rose-400 text-center py-6">Error: ${escapeHtml(detalle)}</p>`;
    }
  } catch (err) {
    console.error("Error al cosechar tarjetas:", err);
    container.innerHTML = `<p class="text-xs text-rose-400 text-center py-6">Error de red al consultar el servidor.</p>`;
  }
}

function renderHarvestCandidates() {
  const container = document.getElementById('harvester-candidates-container');
  const countLabel = document.getElementById('harvester-count-label');
  const commitBtn = document.getElementById('btn-harvest-commit');
  const selectAll = document.getElementById('harvester-select-all');

  const candidates = state.harvestCandidates;
  if (!candidates || candidates.length === 0) {
    container.innerHTML = '<p class="text-xs text-slate-500 italic text-center py-8">No se encontraron candidatos para los criterios especificados.</p>';
    countLabel.innerText = "0 tarjetas encontradas";
    commitBtn.disabled = true;
    return;
  }

  const newCount = candidates.filter(c => !c.is_duplicate).length;
  countLabel.innerText = `${candidates.length} encontradas (${newCount} nuevas)`;

  container.innerHTML = candidates.map((c, idx) => `
    <div class="p-3 rounded-2xl border ${c.is_duplicate ? 'bg-slate-950/40 border-slate-800/50 opacity-60' : 'bg-slate-950 border-slate-800 hover:border-slate-700'} space-y-1.5 transition text-xs">
      <div class="flex items-start justify-between gap-3">
        <label class="flex items-start gap-2.5 cursor-pointer flex-1">
          <input type="checkbox" data-index="${idx}" ${c.is_duplicate ? 'disabled' : 'checked'} data-accion="cambiar-seleccion-cosecha" class="harvest-card-checkbox mt-0.5 rounded bg-slate-900 border-slate-700 text-sky-500 focus:ring-0">
          <div class="space-y-0.5">
            <span class="font-bold text-white block">${escapeHtml(c.respuesta_esperada)}</span>
            <p class="text-slate-400">${escapeHtml(c.item_pregunta)}</p>
            ${c.contexto_uso ? `<p class="text-xs text-slate-500 italic">"${escapeHtml(c.contexto_uso)}"</p>` : ''}
          </div>
        </label>
        <div class="flex flex-col items-end gap-1 shrink-0">
          <span class="au-insignia ${c.is_duplicate ? 'au-insignia--alerta' : 'au-insignia--exito'}">
            ${c.is_duplicate ? Au.icono('alerta') + ' Ya existe' : Au.icono('ok') + ' Nueva'}
          </span>
          <span class="au-insignia au-insignia--mono">${escapeHtml(c.source)}</span>
        </div>
      </div>
    </div>
  `).join('');

  if (selectAll) selectAll.checked = true;
  updateHarvestCommitButtonState();
}

function toggleAllHarvestCheckboxes(checked) {
  const checkboxes = document.querySelectorAll('.harvest-card-checkbox:not(:disabled)');
  checkboxes.forEach(cb => {
    cb.checked = checked;
  });
  updateHarvestCommitButtonState();
}

function updateHarvestCommitButtonState() {
  const commitBtn = document.getElementById('btn-harvest-commit');
  const checkedBoxes = document.querySelectorAll('.harvest-card-checkbox:checked');
  if (!commitBtn) return;
  commitBtn.disabled = checkedBoxes.length === 0;
  commitBtn.innerHTML = `${Au.icono('importar')} Importar ${checkedBoxes.length} Tarjetas al Mazo FSRS`;
}

async function commitHarvestSelected() {
  const checkedBoxes = document.querySelectorAll('.harvest-card-checkbox:checked');
  if (checkedBoxes.length === 0) return;

  const selectedCards = [];
  checkedBoxes.forEach(cb => {
    const idx = parseInt(cb.dataset.index);
    if (!isNaN(idx) && state.harvestCandidates[idx]) {
      selectedCards.push(state.harvestCandidates[idx]);
    }
  });

  const commitBtn = document.getElementById('btn-harvest-commit');
  commitBtn.disabled = true;
  commitBtn.innerText = "Importando...";

  try {
    const res = await fetch('/api/fsrs/harvest/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cards: selectedCards })
    });

    if (res.ok) {
      const data = await res.json();
      alert(data.message);
      closeHarvesterModal();
      await loadFsrsStatus();
      await loadFsrsSession(true);
    } else {
      const err = await res.json();
      alert(`Error al guardar tarjetas: ${err.detail || 'Fallo desconocido'}`);
      commitBtn.disabled = false;
      updateHarvestCommitButtonState();
    }
  } catch (err) {
    console.error("Error al importar tarjetas cosechadas:", err);
    alert("Error de red al importar tarjetas.");
    commitBtn.disabled = false;
    updateHarvestCommitButtonState();
  }
}

