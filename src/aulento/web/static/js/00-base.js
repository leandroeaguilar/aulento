/**
 * Aulento — Cliente Reactivo Frontend (Vanilla JS)
 */

const LOGIN_PATH = '/login';

function actualizarBotonesDeProveedor(proveedor, tieneClave) {
  const ids = [
    `btn-config-test-${proveedor}`,
    `btn-config-remove-${proveedor}`,
    `btn-config-models-${proveedor}`,
  ];
  ids.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.classList.toggle('hidden', !tieneClave);
    }
  });
}

// Indica si un pedido va a la API propia (la pantalla de ingreso, con su 401 por contraseña mala, no carga app.js)
function isSessionProtectedRequest(input) {
  try {
    const url = new URL(typeof input === 'string' ? input : input.url || String(input), window.location.href);
    return url.origin === window.location.origin
      && url.pathname.startsWith('/api/');
  } catch (e) {
    return false;
  }
}

// Sesión vencida o cerrada: cualquier 401 de la API lleva a la pantalla de ingreso, una sola vez
if (!window.__studyEngineFetchWrapped) {
  window.__studyEngineFetchWrapped = true;
  const originalFetch = window.fetch.bind(window);
  let redirectingToLogin = false;
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    if (response.status === 401 && !redirectingToLogin && isSessionProtectedRequest(args[0])) {
      redirectingToLogin = true;
      window.location.assign(LOGIN_PATH);
    }
    // Aviso de la demo compartida (definido más abajo; la guarda es para quien ejecute solo este bloque)
    if (typeof avisarSiLaDemoLoBloqueo === 'function') avisarSiLaDemoLoBloqueo(response);
    return response;
  };
}
// Interceptor global para erradicar popups de alert() nativos y mostrarlos como toasts in-app
if (!window.__studyEngineAlertWrapped) {
  window.__studyEngineAlertWrapped = true;
  window.alert = function(message) {
    const msg = String(message || '');
    const isError = msg.toLowerCase().includes('error') || msg.toLowerCase().includes('falló') || msg.toLowerCase().includes('no se pudo') || msg.includes('❌') || msg.includes('⚠️');
    const isSuccess = msg.includes('🎉') || msg.includes('✅') || msg.includes('✔') || msg.toLowerCase().includes('éxito') || msg.toLowerCase().includes('exitosamente');
    const type = isError ? 'error' : (isSuccess ? 'success' : 'info');
    if (typeof showToast === 'function') {
      showToast(msg, type, 4000);
    } else {
      console.log(`[Alert -> Toast]: ${msg}`);
    }
  };
}


/**
 * Sanitiza cadenas de texto para prevenir vulnerabilidades de DOM/Stored XSS
 * antes de interpolar en innerHTML.
 */
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Sanitiza URLs para prevenir inyecciones de pseudoprotocolos ejecutables (e.g. javascript:, vbscript:)
 * en atributos href o src. Solo permite http:, https:, mailto: o rutas relativas seguras.
 */
function sanitizeUrl(url) {
  if (!url || typeof url !== 'string') return '#';
  const trimmed = url.trim();
  if (/^(https?:\/\/|\/|#|mailto:)/i.test(trimmed)) {
    return escapeHtml(trimmed);
  }
  return '#';
}

// Estado global de la aplicación
const state = {
  currentUser: null,
  currentTab: 'dashboard',
  platforms: [],
  courses: [],
  books: [],
  schedule: [],
  scheduleFilter: 'todos',
  scheduleDaysView: '7d',
  scheduleCardSize: 'normal',
  scheduleBlockInDetail: null,
  fsrsStatus: null,
  fsrsCards: [],
  fsrsSelectedLevel: 'all',
  consultingScenarios: [],
  currentConsultingScenario: null,
  duolingoProfile: null,
  currentCardIndex: 0,
  isCardFlipped: false,
  isEvaluatingVoice: false,
  vaultNotes: [],
  currentExam: null,
  audioConfig: {
    accent: 'en-US',
    speed: 1.0,
    listeningMode: false,
  },
  voiceRecognition: {
    isListening: false,
    recognition: null,
    target: null,
  },
  focusTimer: {
    durationMinutes: 25,
    remainingSeconds: 25 * 60,
    intervalId: null,
    isRunning: false,
    stats: null,
  },
  roadmaps: [],
  activeRoadmapId: null,
  activeRoadmap: null,
  activeTopicId: null,
  currentLesson: null,
  lessonView: 'preview',
  lessonSlides: [],
  lessonSlideIndex: 0,
  pdfGapResult: null,
  roadmapViewMode: 'tree',
  activeGraphData: null,
  activePromptTab: 'roadmap',
  activeNewRoadmapTab: 'ai',
  parsedSyllabusPreview: null,
  selectedGraphNodeId: null,
  prerequisiteSuggestions: [],
  cloudAgent: {
    mode: 'explain',
    isAsking: false,
    lastResult: null,
    selectedMaterialId: null,
    selectedMaterialName: null,
    history: [],
  },
  wizard: {
    currentStep: 1,
    selectedProvider: 'gemini',
    status: null,
  },
  activeConfigSection: 'ai',
};

// ======================================================================
// SISTEMA MODERNO DE NOTIFICACIONES (TOAST) Y DIALOGOS DE CONFIRMACION
// ======================================================================

function showToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.setAttribute('role', 'status');
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-atomic', 'false');
    container.className = 'fixed bottom-6 right-6 z-50 flex flex-col gap-2.5 max-w-sm pointer-events-none';
    document.body.appendChild(container);
  }

  const icons = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️'
  };
  const borders = {
    success: 'border-emerald-600/60 bg-slate-900/95 text-emerald-300 shadow-emerald-950/40',
    error: 'border-rose-600/60 bg-slate-900/95 text-rose-300 shadow-rose-950/40',
    warning: 'border-amber-600/60 bg-slate-900/95 text-amber-300 shadow-amber-950/40',
    info: 'border-sky-600/60 bg-slate-900/95 text-sky-300 shadow-sky-950/40'
  };

  const toast = document.createElement('div');
  toast.className = `pointer-events-auto flex items-center gap-3 p-3.5 rounded-2xl border backdrop-blur-md shadow-xl text-xs font-medium transition-all duration-300 transform translate-y-2 opacity-0 ${borders[type] || borders.info}`;
  toast.innerHTML = `
    <span class="text-base shrink-0" aria-hidden="true">${icons[type] || 'ℹ️'}</span>
    <span class="flex-1 text-slate-200 leading-snug">${escapeHtml(message)}</span>
    <button type="button" aria-label="Cerrar notificación" class="text-slate-400 hover:text-white text-base leading-none shrink-0">&times;</button>
  `;

  const closeBtn = toast.querySelector('button');
  const removeToast = () => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 250);
  };
  closeBtn.addEventListener('click', removeToast);
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.remove('opacity-0', 'translate-y-2');
  });

  if (duration > 0) {
    setTimeout(removeToast, duration);
  }
}

// ======================================================================
// AVISOS DE LA CUENTA DEMO
// La demo es compartida: no guarda claves ni conecta servicios, y en la instalación pública no tiene IA.
// Los textos viven solo acá. Para avisar en una zona nueva alcanza con marcarla en el HTML con
// data-demo-aviso="<clave de AVISOS_DEMO>"; aplicarAvisosDemo() pone o saca el aviso.
// ======================================================================

const AVISOS_DEMO = {
  ia: {
    titulo: 'Esta cuenta es compartida: acá no se cargan claves de API.',
    texto: 'Como la usan varias personas, no guarda claves de Gemini, Claude ni OpenAI. Con tu propia cuenta cargás la tuya y se guarda cifrada.',
  },
  conectores: {
    titulo: 'Esta cuenta es compartida: no se pueden conectar servicios.',
    texto: 'Google Calendar necesita tu cuenta de Google, y esta cuenta es compartida. En tu propia cuenta lo conectás desde acá.',
  },
  generacion: {
    titulo: 'Esta cuenta es compartida y no tiene clave de IA.',
    texto: 'Lo que generes acá sale del motor local de reserva, que funciona sin conexión. Con tu propia clave de API lo genera la IA que elijas: Gemini, Claude u OpenAI.',
  },
};

const MENSAJE_DEMO_BLOQUEADA = 'Esta cuenta es compartida, así que no guarda claves de API ni conecta servicios. En tu propia instalación sí podés.';

// Red de seguridad: cualquier pedido que el servidor rechaza por ser la demo (cabecera X-Cuenta-Compartida)
// muestra el aviso, aunque el botón que lo disparó no tenga uno propio. La llama la envoltura de fetch del principio.
let ultimoAvisoDeDemo = 0;
function avisarSiLaDemoLoBloqueo(response) {
  if (response.status !== 403 || !response.headers.get('X-Cuenta-Compartida')) return;
  if (Date.now() - ultimoAvisoDeDemo < 4000) return;
  ultimoAvisoDeDemo = Date.now();
  mostrarAvisoDemoDestacado();
}

// Panel ámbar arriba al centro: más visible que un toast de esquina, y se cierra solo o con "Entendido".
function mostrarAvisoDemoDestacado() {
  document.getElementById('aviso-demo-destacado')?.remove();
  const panel = document.createElement('div');
  panel.id = 'aviso-demo-destacado';
  panel.setAttribute('role', 'alert');
  panel.className = 'fixed top-6 left-1/2 -translate-x-1/2 z-[60] w-[min(640px,calc(100vw-2rem))] '
    + 'bg-gradient-to-r from-amber-950 to-slate-900 border-2 border-amber-500/70 rounded-2xl shadow-2xl shadow-amber-950/60 '
    + 'p-5 flex items-start gap-4 transition-all duration-300 opacity-0 -translate-y-3';
  panel.innerHTML = `
    <span class="text-3xl leading-none shrink-0">🔒</span>
    <div class="flex-1 min-w-0">
      <p class="text-base font-bold text-amber-200">Esta cuenta es compartida</p>
      <p class="text-sm text-amber-100/90 mt-1 leading-relaxed">${escapeHtml(MENSAJE_DEMO_BLOQUEADA)}</p>
    </div>
    <button type="button" class="shrink-0 self-center px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-sm font-bold transition">Entendido</button>`;
  const cerrar = () => {
    panel.classList.add('opacity-0', '-translate-y-3');
    setTimeout(() => panel.remove(), 300);
  };
  panel.querySelector('button').addEventListener('click', cerrar);
  document.body.appendChild(panel);
  requestAnimationFrame(() => panel.classList.remove('opacity-0', '-translate-y-3'));
  setTimeout(cerrar, 9000);
}

// Recuadro de resultado de un formulario: si el rechazo es por la demo, se pinta como aviso de demo
// (ámbar, con candado) y no como un error rojo.
function pintarErrorEnFeedback(feedback, mensaje) {
  if (!feedback) return;
  const esDeLaDemo = /esta cuenta es compartida/i.test(mensaje || '');
  feedback.classList.remove('hidden');
  if (esDeLaDemo) {
    feedback.className = 'block text-sm p-3.5 rounded-xl bg-amber-950/60 border-2 border-amber-500/70 text-amber-100';
    feedback.innerHTML = `<p class="font-bold text-amber-200">🔒 Esta cuenta es compartida</p>
      <p class="mt-1 text-amber-100/90">${escapeHtml(MENSAJE_DEMO_BLOQUEADA)}</p>`;
  } else {
    feedback.className = 'text-xs p-2.5 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 block';
    feedback.innerText = 'Error: ' + (mensaje || 'No se pudo completar la acción.');
  }
}

// La demo "sin APIs" es la pública: la cuenta demo sin clave de IA. Con clave (como en la grabación del video) no se avisa.
function esDemoSinIA() {
  const esDemo = esCuentaCompartida();
  return Boolean(esDemo && state.demoTieneIA === false);
}

function aplicarAvisosDemo() {
  const mostrar = esDemoSinIA();
  document.querySelectorAll('[data-demo-aviso]').forEach((zona) => {
    let aviso = zona.querySelector(':scope > .aviso-demo');
    if (!mostrar) {
      if (aviso) aviso.remove();
      return;
    }
    const contenido = AVISOS_DEMO[zona.dataset.demoAviso];
    if (!contenido || aviso) return;
    aviso = document.createElement('div');
    aviso.className = 'aviso-demo bg-amber-950/40 border border-amber-700/50 rounded-2xl px-4 py-3 text-sm text-amber-200';
    aviso.innerHTML = `<p class="font-semibold">🔒 ${escapeHtml(contenido.titulo)}</p>
      <p class="text-amber-200/80 text-xs mt-1">${escapeHtml(contenido.texto)}</p>`;
    zona.prepend(aviso);
  });
  actualizarAvisoTutorDemo();
}

function showNotification(message, type = 'info') {
  showToast(message, type);
}

function showConfirmDialog({
  title = '¿Confirmar acción?',
  message = '',
  confirmText = 'Aceptar',
  cancelText = 'Cancelar',
  icon = '❓',
  danger = false
} = {}) {
  return new Promise(resolve => {
    const modal = document.getElementById('modal-system-confirm');
    const titleEl = document.getElementById('sys-confirm-title');
    const msgEl = document.getElementById('sys-confirm-message');
    const iconEl = document.getElementById('sys-confirm-icon');
    const iconContainer = document.getElementById('sys-confirm-icon-container');
    const btnOk = document.getElementById('sys-confirm-btn-ok');
    const btnCancel = document.getElementById('sys-confirm-btn-cancel');

    if (!modal || !titleEl || !msgEl || !btnOk || !btnCancel) {
      resolve(confirm(message || title));
      return;
    }

    titleEl.textContent = title;
    msgEl.textContent = message;
    if (iconEl) iconEl.textContent = icon;
    btnOk.textContent = confirmText;
    btnCancel.textContent = cancelText;

    if (danger) {
      if (iconContainer) iconContainer.className = 'w-12 h-12 rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center justify-center text-2xl font-bold shrink-0';
      btnOk.className = 'au-boton au-boton--peligro';
    } else {
      if (iconContainer) iconContainer.className = 'w-12 h-12 rounded-2xl bg-sky-500/10 text-sky-400 border border-sky-500/20 flex items-center justify-center text-2xl font-bold shrink-0';
      btnOk.className = 'au-boton au-boton--primario';
    }

    // Primero se sueltan los listeners y después se cierra: Au.modal.cerrar emite au:cerrado en el acto, y con
    // onCancel todavía enganchado el Aceptar resolvía false
    const cleanup = () => {
      btnOk.removeEventListener('click', onOk);
      btnCancel.removeEventListener('click', onCancel);
      modal.removeEventListener('au:cerrado', onCancel);
      Au.modal.cerrar('modal-system-confirm');
    };

    const onOk = () => { cleanup(); resolve(true); };
    const onCancel = () => { cleanup(); resolve(false); };

    btnOk.addEventListener('click', onOk);
    btnCancel.addEventListener('click', onCancel);
    modal.addEventListener('au:cerrado', onCancel, { once: true });
    Au.modal.abrir('modal-system-confirm');
  });
}

function showAlertDialog({
  title = 'Información',
  message = '',
  buttonText = 'Entendido',
  icon = 'ℹ️'
} = {}) {
  return showConfirmDialog({
    title,
    message,
    confirmText: buttonText,
    cancelText: 'Cerrar',
    icon,
    danger: false
  });
}


function showPromptDialog({
  title = 'Ingresar Dato',
  message = '',
  defaultValue = '',
  placeholder = '',
  confirmText = 'Aceptar',
  cancelText = 'Cancelar',
  icon = '✏️'
} = {}) {
  return new Promise(resolve => {
    const modal = document.getElementById('modal-system-prompt');
    const titleEl = document.getElementById('sys-prompt-title');
    const msgEl = document.getElementById('sys-prompt-message');
    const iconEl = document.getElementById('sys-prompt-icon');
    const inputEl = document.getElementById('sys-prompt-input');
    const btnOk = document.getElementById('sys-prompt-btn-ok');
    const btnCancel = document.getElementById('sys-prompt-btn-cancel');

    if (!modal || !titleEl || !inputEl || !btnOk || !btnCancel) {
      resolve(window.prompt(message || title, defaultValue));
      return;
    }

    titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;
    if (iconEl) iconEl.textContent = icon;
    inputEl.value = defaultValue || '';
    inputEl.placeholder = placeholder || '';
    btnOk.textContent = confirmText;
    btnCancel.textContent = cancelText;

    // Listeners afuera antes de cerrar (ver showConfirmDialog)
    const cleanup = () => {
      btnOk.removeEventListener('click', onOk);
      btnCancel.removeEventListener('click', onCancel);
      inputEl.removeEventListener('keydown', onKeyDown);
      modal.removeEventListener('au:cerrado', onCancel);
      Au.modal.cerrar('modal-system-prompt');
    };

    const onOk = () => {
      const val = inputEl.value;
      cleanup();
      resolve(val);
    };

    const onCancel = () => {
      cleanup();
      resolve(null);
    };

    const onKeyDown = (e) => {
      if (e.key === 'Enter') {
        if (e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        onOk();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
    };

    btnOk.addEventListener('click', onOk);
    btnCancel.addEventListener('click', onCancel);
    inputEl.addEventListener('keydown', onKeyDown);
    modal.addEventListener('au:cerrado', onCancel, { once: true });

    Au.modal.abrir('modal-system-prompt');
    setTimeout(() => {
      inputEl.focus();
      inputEl.select();
    }, 50);
  });
}

// Texto de un error de la API: `detail` es un texto, o una lista con `msg` cuando es un 422
function apiErrorText(data, fallback) {
  const detail = data ? data.detail : null;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) return detail.map(item => item.msg).join(' · ');
  return fallback;
}

function copyToClipboard(text, successMsg = 'Copiado al portapapeles.') {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      alert(`📋 ${successMsg}`);
    }).catch(() => {
      prompt('Copiá manualmente este valor:', text);
    });
  } else {
    prompt('Copiá manualmente este valor:', text);
  }
}

