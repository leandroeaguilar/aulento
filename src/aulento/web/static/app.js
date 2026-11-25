// Inicialización al cargar DOM
document.addEventListener('DOMContentLoaded', () => {
  setupKeyboardShortcuts();
  actualizarBarraInferiorPestana();
  actualizarBotonMenuCuenta();
  loadCurrentUser();
  loadAllData();
  initPdfGapDropzone();
});

document.addEventListener('capacidades-listas', () => {
  actualizarBotonMenuCuenta();
});

function actualizarBotonMenuCuenta() {
  const modo = (window.SE_CAPACIDADES && window.SE_CAPACIDADES.modo) ||
               (document.body && document.body.dataset && document.body.dataset.modo) ||
               'local';
  const esLocal = modo === 'local';
  const hdrAccount = document.getElementById('hdr-account');
  if (hdrAccount) hdrAccount.classList.remove('hidden');

  const avatar = document.getElementById('hdr-user-avatar');
  const iconoMenu = document.getElementById('hdr-menu-icono');
  const labelMenu = document.getElementById('hdr-user-label');
  const hdrUser = document.getElementById('hdr-user');
  const tituloMenu = document.getElementById('menu-cuenta-titulo');

  if (esLocal || !state.currentUser) {
    if (avatar) avatar.classList.add('hidden');
    if (iconoMenu) iconoMenu.classList.remove('hidden');
    if (labelMenu) labelMenu.classList.remove('hidden');
    if (hdrUser) {
      hdrUser.textContent = '';
      hdrUser.classList.add('hidden');
    }
    if (tituloMenu) tituloMenu.textContent = 'Opciones';
  } else {
    if (avatar) avatar.classList.remove('hidden');
    if (iconoMenu) iconoMenu.classList.add('hidden');
    if (labelMenu) labelMenu.classList.add('hidden');
    if (hdrUser) {
      hdrUser.textContent = state.currentUser.nombre_usuario;
      hdrUser.classList.remove('hidden');
    }
    if (tituloMenu) tituloMenu.textContent = 'Mi Cuenta';
  }
}

// Muestra en la cabecera quién ingresó; sin sesión vigente vuelve a la pantalla de ingreso
async function loadCurrentUser() {
  actualizarBotonMenuCuenta();
  try {
    const response = await fetch('/api/auth/me');
    if (response.status === 401) {
      window.location.assign(LOGIN_PATH);
      return;
    }
    if (response.ok) {
      state.currentUser = await response.json();
    }

    actualizarBotonMenuCuenta();

    if (state.currentUser) {
      // Las extensiones (las cuentas de la nube) suman lo suyo al menú y a la barra lateral con la cuenta ya leída
      document.dispatchEvent(new CustomEvent('aulento:cuenta', { detail: state.currentUser }));
    }

    actualizarAvisoTutorDemo();

    if (esCuentaCompartida()) {
      try {
        const resIa = await fetch('/api/config/ia');
        if (resIa.ok) {
          const ia = await resIa.json();
          const activo = ia.proveedores && ia.proveedores[ia.proveedor_activo];
          state.demoTieneIA = Boolean(activo && activo.tiene_clave);
        }
      } catch (e) {
        console.warn('No se pudo saber si la cuenta compartida tiene IA', e);
      }
    }
    aplicarAvisosDemo();

    // Auto-disparo del Asistente de Onboarding si la cuenta lo requiere
    checkOnboardingAutoTrigger();
  } catch (e) {
    console.error('No se pudo cargar la cuenta de la sesión', e);
  }
}

function switchTab(tabId) {
  if (tabId === 'mcp' || tabId === 'vectors') {
    tabId = 'brain';
  }
  state.currentTab = tabId;

  // Actualizar título dinámico en el topbar si existe
  const titleMap = {
    dashboard: '🏠 Dashboard',
    schedule: '📅 Cronograma Semanal',
    courses: '🎓 Aulas y Cursos',
    books: '📖 Biblioteca de Libros',
    roadmap: '🗺️ Rutas de Aprendizaje',
    notes: '📝 Mis notas',
    fsrs: '🇬🇧 Inglés Técnico',
    brain: '🧠 Cerebro & Tutor IA',
    exams: '📝 Repaso Activo',
    config: '⚙️ Configuración'
  };
  const activeBtn = document.getElementById(`tab-btn-${tabId}`);
  // Una pestaña que suma una extensión trae su título en el botón
  const titulo = titleMap[tabId] || (activeBtn && activeBtn.dataset.titulo);
  const topbarTitle = document.getElementById('topbar-section-title');
  if (topbarTitle && titulo) {
    topbarTitle.textContent = titulo;
  }

  // Actualizar botones de pestaña en el Sidebar
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.className = 'tab-btn w-full flex items-center justify-between px-3.5 py-2.5 text-xs sm:text-sm font-semibold rounded-xl bg-slate-950/70 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800/80 transition';
  });
  if (activeBtn) {
    activeBtn.className = 'tab-btn w-full flex items-center justify-between px-3.5 py-2.5 text-xs sm:text-sm font-bold rounded-xl bg-sky-600 text-white shadow-md shadow-sky-950/40 border border-sky-500/50 transition';
  }

  // Ocultar todos los contenidos y mostrar el activo
  document.querySelectorAll('.tab-content').forEach(section => {
    section.classList.add('hidden');
  });
  const activeContent = document.getElementById(`tab-${tabId}`);
  if (activeContent) {
    activeContent.classList.remove('hidden');
  }

  // Cerrar sidebar en mobile tras selección
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (sidebar && backdrop && window.innerWidth < 1024) {
    sidebar.classList.add('-translate-x-full');
    backdrop.classList.add('hidden');
  }

  if (tabId === 'fsrs' && state.fsrsCards.length === 0) {
    loadFsrsSession();
  } else if (tabId === 'schedule') {
    // R10: al entrar a la agenda, el celular vuelve a mostrar hoy
    state.selectedScheduleDay = null;
    renderSchedule();
    setTimeout(() => {
      const todayEl = document.getElementById('schedule-col-today');
      if (todayEl) {
        todayEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    }, 100);
  } else if (tabId === 'brain') {
    Promise.all([checkVectorStatus(), loadMisMateriales()]).then(renderMisMateriales);
    setTimeout(() => {
      const input = document.getElementById('cloud-agent-input');
      if (input) input.focus();
    }, 100);
  } else if (tabId === 'exams') {
    loadVaultNotesForExams();
  } else if (tabId === 'roadmap') {
    loadRoadmaps();
  } else if (tabId === 'notes') {
    loadNotesLocation();
    loadMisNotas();
  } else if (tabId === 'config') {
    loadConfigPanel();
  } else if (tabId === 'dashboard') {
    renderActivityHeatmap();
    loadMacroFsrsTopics();
  }
  // Las pestañas de las extensiones cargan lo suyo al abrirse
  document.dispatchEvent(new CustomEvent('aulento:pestana', { detail: { pestana: tabId } }));
}

// Carga inicial masiva de datos
async function loadAllData() {
  await Promise.all([
    loadPlatforms(),
    loadBooks(),
    loadSchedule(),
    loadFsrsStatus(),
    loadDuolingoStatus(),
    loadFocusStats(),
    renderActivityHeatmap(),
    loadMacroFsrsTopics(),
    checkVectorStatus(),
  ]);
  populateFocusBlockSelect();
  renderDashboard();
  renderSystemHealth();
}

if (typeof window !== 'undefined') {
  window.renderNoteMarkdown = renderNoteMarkdown;
  window.loadNotesLocation = loadNotesLocation;
  window.saveNotesLocation = saveNotesLocation;
  window.resetNotesLocation = resetNotesLocation;
  window.loadMisNotas = loadMisNotas;
  window.selectNote = selectNote;
  window.seleccionarDiaAgenda = seleccionarDiaAgenda;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    renderNoteMarkdown,
    escapeHtml,
    sanitizeUrl,
  };
}
