// Control del menú desplegable de usuario
function toggleUserDropdown() {
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) menu.classList.toggle('hidden');
}

function closeUserDropdown() {
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) menu.classList.add('hidden');
}

function toggleSystemHealthPopover() {
  const pop = document.getElementById('system-health-popover');
  if (!pop) return;
  pop.classList.toggle('hidden');
  if (!pop.classList.contains('hidden')) renderSystemHealth();
}

// Estado real de cada servicio: lo que no está encendido se muestra así, nunca como "conectado"
async function renderSystemHealth() {
  const lista = document.getElementById('system-health-list');
  const nombresIA = { gemini: 'Gemini', anthropic: 'Claude', openai: 'OpenAI' };
  let ia = null;
  try {
    const res = await fetch('/api/config/ia');
    if (res.ok) ia = await res.json();
  } catch (e) {
    console.warn('No se pudo consultar la IA de la cuenta', e);
  }
  const activo = ia && ia.proveedores && ia.proveedores[ia.proveedor_activo];
  const nombreIA = ia ? (nombresIA[ia.proveedor_activo] || ia.proveedor_activo) : 'IA';

  const servicios = [
    { icono: '💾', nombre: 'Base local', encendido: true, estado: 'Lista' },
    { icono: '🧠', nombre: 'Motor de repaso', encendido: true, estado: 'Activo' },
    {
      icono: '🤖', nombre: `IA (${nombreIA})`,
      encendido: !!(activo && activo.tiene_clave),
      estado: activo && activo.tiene_clave ? 'Con clave' : 'Sin clave',
    },
    {
      icono: '🔎', nombre: 'Índice de apuntes',
      encendido: !!state.vectorOnline,
      estado: state.vectorOnline ? 'Activo' : 'Apagado',
    },
  ];
  const encendidos = servicios.filter(s => s.encendido).length;

  if (lista) {
    lista.innerHTML = servicios.map(s => `
      <div class="flex items-center justify-between p-2 rounded-xl bg-slate-950/70 border border-slate-800/60">
        <span class="text-slate-300 flex items-center gap-1.5"><span>${s.icono}</span> ${escapeHtml(s.nombre)}</span>
        <span class="${s.encendido ? 'text-emerald-400' : 'text-slate-500'} font-bold text-xs sm:text-[11px]">${escapeHtml(s.estado)}</span>
      </div>
    `).join('') + '<p class="text-xs sm:text-[10px] text-slate-500">La IA y el índice son opcionales: sin ellos la app funciona igual.</p>';
  }
  const contador = document.getElementById('system-health-count');
  if (contador) contador.innerText = `${encendidos}/${servicios.length} encendidos`;
  const punto = document.getElementById('system-health-dot');
  // Verde solo con todo encendido; celeste si falta algo opcional (la app funciona igual)
  if (punto) punto.className = `w-2 h-2 rounded-full ${encendidos === servicios.length ? 'bg-emerald-400' : 'bg-sky-400'}`;
  const etiqueta = document.getElementById('system-health-label');
  if (etiqueta) etiqueta.innerText = encendidos === servicios.length ? 'Todo encendido' : `${encendidos}/${servicios.length} servicios`;
}

function closeSystemHealthPopover() {
  const pop = document.getElementById('system-health-popover');
  if (pop) pop.classList.add('hidden');
}


// Modal de atajos de teclado
function openKeyboardShortcutsModal() {
  Au.modal.abrir('modal-keyboard-shortcuts');
}

function closeKeyboardShortcutsModal() {
  Au.modal.cerrar('modal-keyboard-shortcuts');
}

// Cerrar dropdowns y popovers al hacer clic fuera
document.addEventListener('click', (e) => {
  const btn = document.getElementById('btn-user-menu');
  const menu = document.getElementById('user-dropdown-menu');
  if (menu && !menu.classList.contains('hidden')) {
    if (btn && !btn.contains(e.target) && !menu.contains(e.target)) {
      menu.classList.add('hidden');
    }
  }
  const btnHealth = document.getElementById('btn-system-health');
  const popHealth = document.getElementById('system-health-popover');
  if (popHealth && !popHealth.classList.contains('hidden')) {
    if (btnHealth && !btnHealth.contains(e.target) && !popHealth.contains(e.target)) {
      popHealth.classList.add('hidden');
    }
  }
});




// R4: Sincronización de la barra inferior con la pestaña activa
function actualizarBarraInferiorPestana(pestana) {
  const tab = pestana || state.currentTab || 'dashboard';
  const botones = document.querySelectorAll('#barra-inferior [data-pestana]');
  botones.forEach((btn) => {
    if (btn.getAttribute('data-pestana') === tab) {
      btn.setAttribute('aria-current', 'page');
    } else {
      btn.removeAttribute('aria-current');
    }
  });
}

document.addEventListener('aulento:pestana', (e) => {
  actualizarBarraInferiorPestana(e.detail && e.detail.pestana);
});

// Configuración de atajos de teclado para sesión FSRS
function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Si el usuario está escribiendo en un input, ignorar atajos
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;

    // Atajo global para abrir modal de atajos [?]
    if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
      e.preventDefault();
      openKeyboardShortcutsModal();
      return;
    }

    // Escape para cerrar dropdowns, popovers y fullscreen. Los modales no: con uno abierto,
    // Au.modal atrapa el Esc en captura y este listener ni se entera.
    if (e.key === 'Escape') {
      const dagEl = document.getElementById('dag-canvas-card') || document.getElementById('dag-diagram');
      if (dagEl && dagEl.classList.contains('dag-fullscreen')) {
        toggleDagFullscreen();
        return;
      }
      closeUserDropdown();
      closeSystemHealthPopover();
    }

    // Atajos rápidos de navegación global fuera de sesión activa
    if (e.key === 'd' || e.key === 'D') {
      if (!e.ctrlKey && !e.metaKey && state.currentTab !== 'dashboard') {
        switchTab('dashboard');
        return;
      }
    } else if (e.shiftKey && (e.key === 'F' || e.key === 'f')) {
      switchTab('fsrs');
      return;
    } else if (e.shiftKey && (e.key === 'S' || e.key === 's')) {
      switchTab('schedule');
      return;
    }

    // Si el micrófono está activo o se está procesando evaluación de voz, ignorar atajos de avance
    if ((state.voiceRecognition && state.voiceRecognition.isListening) || state.isEvaluatingVoice) return;

    if (state.currentTab === 'fsrs' && state.fsrsCards.length > 0) {
      if (e.code === 'KeyR') {
        e.preventDefault();
        playCurrentCardAudio();
      } else if (e.code === 'Space') {
        e.preventDefault();
        if (!state.isCardFlipped) {
          flipFsrsCard();
        } else {
          // Si ya está volteada, presionar Espacio avanza a la siguiente tarjeta con calificación 'Good' (3)
          submitCardRating(3);
        }
      } else if (e.code === 'Enter') {
        e.preventDefault();
        if (!state.isCardFlipped) {
          flipFsrsCard();
        } else {
          submitCardRating(3);
        }
      } else if (state.isCardFlipped) {
        if (e.key === '1') submitCardRating(1);
        else if (e.key === '2') submitCardRating(2);
        else if (e.key === '3') submitCardRating(3);
        else if (e.key === '4') submitCardRating(4);
      }
    }
  });
}

// Navegación Sidebar y cambio de pestaña
function toggleMobileSidebar() {
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (!sidebar) return;
  const isClosed = sidebar.classList.contains('-translate-x-full');
  if (isClosed) {
    sidebar.classList.remove('-translate-x-full');
    if (backdrop) backdrop.classList.remove('hidden');
  } else {
    sidebar.classList.add('-translate-x-full');
    if (backdrop) backdrop.classList.add('hidden');
  }
}

// --- INTEGRACIÓN PWA & APP DE ESCRITORIO ---
let deferredInstallPrompt = null;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js').then(reg => {
      console.log('Service Worker de Aulento registrado con alcance:', reg.scope);
    }).catch(err => {
      console.warn('Error al registrar Service Worker:', err);
    });
  });
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  const btn = document.getElementById('btn-pwa-install');
  if (btn) btn.classList.remove('hidden');
});

function promptPwaInstall() {
  if (!deferredInstallPrompt) {
    showToast('Para instalar Aulento en tu escritorio, podés usar la opción "Instalar aplicación" desde el menú de tu navegador.', 'info');
    return;
  }
  deferredInstallPrompt.prompt();
  deferredInstallPrompt.userChoice.then((choiceResult) => {
    if (choiceResult.outcome === 'accepted') {
      showToast('¡Aulento instalado como aplicación de escritorio!', 'success');
      const btn = document.getElementById('btn-pwa-install');
      if (btn) btn.classList.add('hidden');
    }
    deferredInstallPrompt = null;
  });
}

window.addEventListener('appinstalled', () => {
  const btn = document.getElementById('btn-pwa-install');
  if (btn) btn.classList.add('hidden');
  deferredInstallPrompt = null;
});

// --- Modal de Diagnóstico y Depurador del Sistema (Feature 049) ---
async function openDiagnosticsModal() {
  Au.modal.abrir('modal-diagnostics');
  await refreshDiagnosticsModal();
}

function closeDiagnosticsModal() {
  Au.modal.cerrar('modal-diagnostics');
}

async function refreshDiagnosticsModal() {
  try {
    const res = await fetch('/api/diagnostics/summary');
    if (!res.ok) throw new Error('Error al consultar diagnóstico');
    const data = await res.json();

    const modoEl = document.getElementById('diag-modo');
    if (modoEl) modoEl.textContent = (data.modo_motor || 'local').toUpperCase();

    const sqliteEl = document.getElementById('diag-sqlite');
    if (sqliteEl) {
      const ok = data.sqlite?.integridad === 'ok';
      sqliteEl.textContent = ok ? 'Saludable (ok)' : (data.sqlite?.integridad || 'Advertencia');
      sqliteEl.className = ok ? 'text-sm font-bold text-emerald-400 font-mono' : 'text-sm font-bold text-rose-400 font-mono';
    }

    const ollamaEl = document.getElementById('diag-ollama');
    if (ollamaEl) {
      ollamaEl.textContent = data.ollama?.disponible ? `En línea (${data.ollama.modelos.length} mods)` : 'No detectado';
    }

    const tamanoEl = document.getElementById('diag-tamano');
    if (tamanoEl) tamanoEl.textContent = data.sqlite?.tamano_humano || '0 KB';

    const logsEl = document.getElementById('diag-logs');
    if (logsEl) {
      logsEl.textContent = (data.logs_recientes || []).join('\n') || 'Sin eventos registrados.';
      logsEl.scrollTop = logsEl.scrollHeight;
    }
  } catch (err) {
    console.error('Error cargando diagnóstico:', err);
  }
}

async function copiarReporteDiagnostico() {
  const btn = document.getElementById('btn-copy-diagnostic');
  try {
    const res = await fetch('/api/diagnostics/export-markdown');
    if (!res.ok) throw new Error('Error obteniendo reporte Markdown');
    const md = await res.text();
    await navigator.clipboard.writeText(md);
    if (btn) {
      const originalText = btn.innerHTML;
      btn.innerHTML = '<span>✅</span> ¡Copiado al Portapapeles!';
      setTimeout(() => { btn.innerHTML = originalText; }, 2500);
    }
  } catch (err) {
    alert('No se pudo copiar el reporte automáticamente.');
  }
}


