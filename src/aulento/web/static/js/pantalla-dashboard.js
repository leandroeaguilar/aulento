// --- ACCIONES DELEGADAS DEL DASHBOARD (072 T4) ---
// Cada acción llama a la misma función que antes llamaba su onclick. Sin `typeof` de por medio: si una función
// cambia de nombre, el error se ve (y lo frena tests/e2e/test_dashboard_acciones.py).
[
  ['abrir-sesion-guiada', () => openGuidedStudySessionModal()],
  ['avanzar-sesion-guiada', () => nextGuidedSessionStep()],
  ['terminar-sesion-guiada', () => cancelGuidedSession()],
  ['abrir-planificador', () => openStudyPlannerModal()],
  ['ruta-seleccionar-minutos-planificador', (el, datos) => selectPlannerMinutes(Number(datos.minutos))],
  ['ruta-generar-plan-estudio', () => generateAdaptiveStudyPlan()],
  ['ruta-aplicar-plan-agenda', () => applyPlanToScheduleAction()],
  ['ir-a-pestana', (el, datos) => switchTab(datos.pestana)],
  ['cambiar-dias-heatmap', () => renderActivityHeatmap()],
  ['indexar-vectores', () => syncAllCatalogToVectors()],
  ['preguntar-tutor-dashboard', () => askTutorFromDashboard()],
  ['actualizar-macro-fsrs', () => loadMacroFsrsTopics()],
  ['abrir-quiz-feynman', (el, datos) => openFeynmanQuizModal(Number(datos.temaId))],
  ['ruta-calificar-feynman', (el, datos) => submitFeynmanRating(Number(datos.calificacion))],
  ['fijar-minutos-pomodoro', (el, datos) => setPomodoroMinutes(Number(datos.minutos))],
  ['alternar-pomodoro', () => togglePomodoroTimer()],
  ['reiniciar-pomodoro', () => resetPomodoroTimer()],
  ['guardar-pomodoro', () => completePomodoroSessionEarly()],
  ['abrir-digest-semanal', () => openWeeklyDigestModal()],
  ['agendar-bloque-hoy', (el, datos) => { switchTab('schedule'); openAddScheduleModal(Number(datos.dia)); }],
  ['detalle-bloque-agenda', (el, datos, evento) => openScheduleCardDetailModal(Number(datos.id), evento)],
  ['editar-bloque-agenda', (el, datos, evento) => openEditScheduleModal(Number(datos.id), evento)],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

// --- RENDERIZADO DEL DASHBOARD GENERAL ---
async function loadDailyBriefingHero() {
  const card = document.getElementById('hero-daily-briefing-card');
  if (!card) return;
  try {
    const res = await fetch('/api/planner/daily-briefing');
    if (!res.ok) return;
    const briefing = await res.json();

    const userName = state.currentUser ? state.currentUser.nombre_usuario : 'Estudiante';
    const greetingEl = document.getElementById('hero-greeting-title');
    if (greetingEl) {
      if (briefing.fsrs_due_count > 0 && briefing.curso_sugerido) {
        greetingEl.textContent = `¡Hola, ${userName}! Tenés ${briefing.fsrs_due_count} tarjetas FSRS y 1 curso sugerido`;
      } else if (briefing.fsrs_due_count > 0) {
        greetingEl.textContent = `¡Hola, ${userName}! Tenés ${briefing.fsrs_due_count} tarjetas FSRS listas para afianzar`;
      } else {
        greetingEl.textContent = `¡Hola, ${userName}! Estás al día con tus repasos programados`;
      }
    }

    const msgEl = document.getElementById('hero-focus-message');
    if (msgEl && briefing.mensaje_enfoque) {
      msgEl.textContent = briefing.mensaje_enfoque;
    }

    const urgencyBadge = document.getElementById('hero-urgency-badge');
    if (urgencyBadge) {
      const score = briefing.urgency_score || 0;
      if (score >= 60) {
        urgencyBadge.className = 'au-insignia au-insignia--peligro';
        urgencyBadge.textContent = `Urgencia: Alta (${score}/100)`;
      } else if (score >= 35) {
        urgencyBadge.className = 'au-insignia au-insignia--alerta';
        urgencyBadge.textContent = `Urgencia: Media (${score}/100)`;
      } else {
        urgencyBadge.className = 'au-insignia au-insignia--exito';
        urgencyBadge.textContent = `Al día (${score}/100)`;
      }
    }

    const streakBadge = document.getElementById('hero-streak-badge');
    if (streakBadge) {
      streakBadge.innerHTML = `${Au.icono('racha')} Racha: ${briefing.racha_dias || 0} días`;
    }

    const fsrsCount = document.getElementById('hero-count-fsrs');
    if (fsrsCount) fsrsCount.textContent = briefing.fsrs_due_count || 0;

    const courseName = document.getElementById('hero-course-name');
    if (courseName) {
      courseName.textContent = briefing.curso_sugerido ? `${briefing.curso_sugerido.nombre_curso} (${briefing.curso_sugerido.progreso_pct}%)` : 'Sin cursos pendientes';
    }

    const bookName = document.getElementById('hero-book-name');
    if (bookName) {
      bookName.textContent = briefing.libro_sugerido ? `${briefing.libro_sugerido.titulo} (pág. ${briefing.libro_sugerido.pagina_actual})` : 'Sin lecturas activas';
    }
  } catch (err) {
    console.debug('Error al cargar daily briefing hero:', err);
  }
}

function startQuickStudySession() {
  const fsrsCount = parseInt(document.getElementById('hero-count-fsrs')?.textContent || '0', 10);
  if (fsrsCount > 0) {
    switchTab('fsrs');
  } else {
    openStudyPlannerModal();
  }
}

function renderDashboard() {
  loadDailyBriefingHero();
  // KPIs
  const allCourses = state.platforms.flatMap(p => p.cursos);
  const activeCourses = allCourses.filter(c => c.estado === 'en_curso');
  const readingBooks = state.books.filter(b => b.estado === 'leyendo');

  const kpiCourses = document.getElementById('kpi-active-courses');
  if (kpiCourses) kpiCourses.innerText = activeCourses.length;
  const kpiBooks = document.getElementById('kpi-reading-books');
  if (kpiBooks) kpiBooks.innerText = readingBooks.length;

  // Barra de plataformas en 1 clic
  const quickBar = document.getElementById('quick-platforms-bar');
  if (quickBar) {
    quickBar.innerHTML = state.platforms.map(p => `
      <a href="${sanitizeUrl(p.url_acceso)}" target="_blank" rel="noopener noreferrer" class="au-boton au-boton--secundario au-boton--bloque au-boton--extremos min-w-0" title="${Au.escapar(p.nombre)}">
        <span class="truncate min-w-0">${Au.escapar(p.nombre)}</span>
        <span class="text-slate-500 transition" aria-hidden="true">${Au.icono('externo')}</span>
      </a>
    `).join('');
  }

  // Lista de cursos activos en Dashboard
  const coursesList = document.getElementById('dashboard-courses-list');
  if (coursesList) {
    if (activeCourses.length === 0) {
      coursesList.innerHTML = Au.vacio({
        icono: 'cursos',
        titulo: 'No hay cursadas activas',
        texto: 'Usá la pestaña Cursos para agregar una.'
      });
    } else {
      coursesList.innerHTML = activeCourses.slice(0, 4).map(c => {
        const barra = Au.progreso({
          valor: c.progreso_pct,
          maximo: 100,
          etiqueta: `Progreso: ${c.progreso_pct.toFixed(0)}%`
        });
        const enlace = c.url_aula ? Au.boton({
          texto: 'Entrar al Aula',
          icono: 'externo',
          variante: 'fantasma',
          chico: true,
          href: c.url_aula,
          attrs: { target: '_blank', rel: 'noopener noreferrer' }
        }) : '';
        return `
        <div class="au-tarjeta au-tarjeta--plana">
          <div class="flex items-center justify-between text-xs">
            <span class="font-bold text-slate-200">${Au.escapar(c.nombre_curso)}</span>
            <span class="font-mono text-sky-400 font-bold">${c.progreso_pct.toFixed(0)}%</span>
          </div>
          ${barra}
          <div class="flex justify-end">
            ${enlace}
          </div>
        </div>
      `;
      }).join('');
    }
  }

  // Bloques de hoy en Dashboard
  const scheduleList = document.getElementById('dashboard-schedule-list');
  if (scheduleList) {
    // Determinar día de hoy (1=Lunes .. 7=Domingo)
    const todayJs = new Date().getDay(); // 0=Dom, 1=Lun ... 6=Sab
    const todayDb = todayJs === 0 ? 7 : todayJs;
    const todayBlocks = (state.schedule || []).filter(b => b.dia_semana === todayDb);
    todayBlocks.sort((a, b) => (a.hora_inicio || '').localeCompare(b.hora_inicio || ''));

    if (todayBlocks.length === 0) {
      scheduleList.innerHTML = Au.vacio({
        icono: 'agenda',
        titulo: `Sin bloques programados para hoy (${DIAS_SEMANA[todayDb - 1]})`,
        texto: 'Podés agendar un nuevo bloque de estudio para hoy.',
        accionHtml: Au.boton({
          texto: 'Agendar para hoy',
          icono: 'agregar',
          variante: 'secundario',
          chico: true,
          accion: 'agendar-bloque-hoy',
          datos: { dia: todayDb }
        })
      });
    } else {
      scheduleList.innerHTML = todayBlocks.map(b => {
        const meta = SCHEDULE_TYPE_META[b.tipo] || SCHEDULE_TYPE_META.otro;
        const durMin = getDurationMinutes(b.hora_inicio, b.hora_fin);
        const durStr = formatDuration(durMin);
        const botonDetalle = Au.boton({
          icono: 'ver',
          soloIcono: true,
          variante: 'fantasma',
          chico: true,
          etiqueta: 'Agrandar / Detalle',
          accion: 'detalle-bloque-agenda',
          datos: { id: Number(b.id) }
        });
        const botonEditar = Au.boton({
          icono: 'editar',
          soloIcono: true,
          variante: 'fantasma',
          chico: true,
          etiqueta: 'Editar bloque',
          accion: 'editar-bloque-agenda',
          datos: { id: Number(b.id) }
        });
        const enlaceAcceso = b.url_acceso ? Au.boton({
          texto: 'Entrar',
          icono: 'empezar',
          variante: 'fantasma',
          chico: true,
          href: b.url_acceso,
          attrs: { target: '_blank', rel: 'noopener noreferrer' }
        }) : '';
        const insigniaDuracion = Au.insignia({ texto: durStr, mono: true });
        const insigniaTipo = Au.insignia({ texto: meta.label, icono: meta.icon });

        return `
          <div data-accion="detalle-bloque-agenda" data-id="${Number(b.id)}" class="au-tarjeta au-tarjeta--hundida au-tarjeta--interactiva ${meta.borderClass} border-l-4 gap-2">
            <div class="flex items-center justify-between text-xs font-mono">
              <span class="${meta.timeColor} font-bold">${Au.escapar(b.hora_inicio)} - ${Au.escapar(b.hora_fin)}</span>
              <div class="flex items-center gap-1">
                ${insigniaDuracion}
                ${botonDetalle}
                ${botonEditar}
              </div>
            </div>
            <p class="text-xs font-medium text-slate-200">${Au.escapar(b.descripcion)}</p>
            <div class="flex items-center justify-between pt-1">
              ${insigniaTipo}
              ${enlaceAcceso}
            </div>
          </div>
        `;
      }).join('');
    }
  }
}

// Modales auxiliares
function openAddCourseModal() {
  populatePlatformSelect();
  Au.modal.abrir('add-course-modal');
}
function closeAddCourseModal() { Au.modal.cerrar('add-course-modal'); }

function openAddBookModal() { Au.modal.abrir('add-book-modal'); }
function closeAddBookModal() { Au.modal.cerrar('add-book-modal'); }

// ==========================================
// FEATURE 020: HEATMAP & MACRO-FSRS CLIENT
// ==========================================

let currentFeynmanTopicId = null;
document.getElementById('modal-feynman-quiz')?.addEventListener('au:cerrado', () => {
  currentFeynmanTopicId = null;
});

async function renderActivityHeatmap() {
  const container = document.getElementById('heatmap-grid-container');
  if (!container) return;

  const daysSelect = document.getElementById('heatmap-days-select');
  const days = daysSelect ? parseInt(daysSelect.value, 10) : 90;

  try {
    const res = await fetch(`/api/activity/heatmap?days=${days}`);
    if (!res.ok) throw new Error("Error obteniendo heatmap");
    const data = await res.json();

    // Actualizar badges
    const streakBadge = document.getElementById('heatmap-streak-badge');
    if (streakBadge) streakBadge.innerHTML = `${Au.icono('racha')} ${data.streak.current_streak} días`;

    const recordBadge = document.getElementById('heatmap-record-badge');
    if (recordBadge) recordBadge.innerHTML = `${Au.icono('logro')} Récord: ${data.streak.longest_streak}d`;

    const hdrStreak = document.getElementById('hdr-streak');
    if (hdrStreak) hdrStreak.innerHTML = `${Au.icono('racha')} ${data.streak.current_streak} días`;

    const kpiStreak = document.getElementById('kpi-streak');
    if (kpiStreak) kpiStreak.textContent = `${data.streak.current_streak} días`;

    // Resumen de totales
    const summaryEl = document.getElementById('heatmap-totals-summary');
    if (summaryEl) {
      const hrs = (data.streak.total_study_minutes / 60).toFixed(1);
      summaryEl.textContent = `${data.streak.total_active_days} días activos • ${hrs} hrs estudio • ${data.streak.total_fsrs_reviews} repasos • ${data.streak.total_topics_completed} temas completados`;
    }

    // Renderizado de celdas
    const levelColors = {
      0: 'bg-slate-900 border border-slate-800/80 hover:border-slate-500',
      1: 'bg-emerald-950 border border-emerald-800 hover:border-emerald-500',
      2: 'bg-emerald-700 hover:bg-emerald-600',
      3: 'bg-emerald-500 hover:bg-emerald-400',
      4: 'bg-emerald-400 shadow-sm shadow-emerald-400 hover:bg-emerald-300',
    };

    container.innerHTML = data.days.map(d => {
      const colorClass = levelColors[d.level] || levelColors[0];
      const tooltip = `${d.date}: ${d.score} pts (${d.study_minutes}m pomodoro, ${d.fsrs_reviews} tarjetas, ${d.topics_completed} temas, ${d.pages_read} pág)`;
      return `<div class="w-3.5 h-3.5 rounded-sm transition cursor-pointer ${colorClass}" title="${tooltip}"></div>`;
    }).join('');

  } catch (err) {
    console.error("Error al renderizar heatmap:", err);
    container.innerHTML = '<p class="text-xs text-slate-500">No se pudieron cargar los datos de consistencia.</p>';
  }
}

async function loadMacroFsrsTopics() {
  const container = document.getElementById('macro-fsrs-due-container');
  const badge = document.getElementById('macro-fsrs-due-badge');
  if (!container) return;

  try {
    const res = await fetch('/api/macro-fsrs/due');
    if (!res.ok) throw new Error("Error obteniendo temas macro FSRS");
    const topics = await res.json();

    if (badge) {
      badge.textContent = `${topics.length} pendientes`;
      badge.className = topics.length > 0
        ? 'au-insignia au-insignia--alerta'
        : 'au-insignia au-insignia--primario';
    }

    if (topics.length === 0) {
      container.innerHTML = `<div class="col-span-full">${Au.vacio({
        icono: 'celebrar',
        titulo: '¡Todo tu conocimiento de las rutas está consolidado!',
        texto: 'No tienes temas con fecha de recuperación vencida para hoy. El algoritmo FSRS v5 te notificará cuando sea momento de refrescar la memoria a largo plazo.'
      })}</div>`;
      return;
    }

    container.innerHTML = topics.map(t => {
      const dueStr = t.due_date ? t.due_date.substring(0, 10) : 'Hoy';
      const temaEscapado = escapeHtml(t.tema_titulo || ('Tema #' + t.tema_id));
      const insigniaRuta = Au.insignia({ texto: t.ruta_titulo || 'Ruta', tono: 'primario' });
      const insigniaVence = Au.insignia({ texto: 'Vence: ' + dueStr, icono: 'reloj', tono: 'alerta', mono: true });
      const botonQuiz = Au.boton({
        texto: 'Micro-Quiz Feynman (3 min)',
        variante: 'primario',
        icono: 'objetivo',
        bloque: true,
        accion: 'abrir-quiz-feynman',
        datos: { temaId: Number(t.tema_id) }
      });

      return `
        <div class="au-tarjeta au-tarjeta--plana">
          <div class="flex items-center justify-between text-xs text-slate-400">
            ${insigniaRuta}
            ${insigniaVence}
          </div>
          <div>
            <h4 class="font-bold text-white text-sm leading-tight">${temaEscapado}</h4>
            <div class="flex items-center gap-2 mt-1.5 text-xs text-slate-400">
              <span>Intervalo: <b class="text-slate-200">${t.scheduled_days}d</b></span>
              <span>•</span>
              <span>Repasos: <b class="text-slate-200">${t.reps}</b></span>
              <span>•</span>
              <span>Dificultad: <b class="text-slate-200">${t.difficulty.toFixed(1)}</b></span>
            </div>
          </div>
          ${botonQuiz}
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error("Error al cargar temas macro FSRS:", err);
  }
}

async function openFeynmanQuizModal(temaId) {
  currentFeynmanTopicId = temaId;
  const modal = document.getElementById('modal-feynman-quiz');
  if (!modal) return;

  try {
    const res = await fetch(`/api/macro-fsrs/quiz/${temaId}`);
    if (!res.ok) throw new Error("Error obteniendo quiz Feynman");
    const quiz = await res.json();

    document.getElementById('feynman-modal-topic-title').textContent = quiz.tema_titulo;
    document.getElementById('feynman-modal-ruta-badge').textContent = quiz.ruta_titulo || 'Ruta de Aprendizaje';
    document.getElementById('feynman-modal-active-recall-prompt').textContent = quiz.pregunta_active_recall;
    document.getElementById('feynman-modal-challenge-prompt').textContent = quiz.desafio_feynman;

    const evalList = document.getElementById('feynman-modal-eval-points');
    if (evalList) {
      evalList.innerHTML = quiz.puntos_clave_evaluacion.map(pt => `<li>${Au.escapar(pt)}</li>`).join('');
    }

    Au.modal.abrir('modal-feynman-quiz');
  } catch (err) {
    alert("Error al cargar Micro-Quiz: " + err.message);
  }
}

function closeFeynmanQuizModal() {
  Au.modal.cerrar('modal-feynman-quiz');
}

async function submitFeynmanRating(rating) {
  if (!currentFeynmanTopicId) return;

  try {
    const res = await fetch('/api/macro-fsrs/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tema_id: currentFeynmanTopicId,
        rating: rating,
        notas: `Repaso Feynman con calificación ${rating}`
      })
    });

    if (!res.ok) throw new Error("Error registrando calificación FSRS");
    const updated = await res.json();

    closeFeynmanQuizModal();
    await Promise.all([
      loadMacroFsrsTopics(),
      renderActivityHeatmap(),
    ]);

    alert(`¡Repaso registrado con éxito!\nPróximo repaso programado en: ${updated.scheduled_days} días.`);
  } catch (err) {
    alert("Error al enviar calificación: " + err.message);
  }
}

// =============================================================================
// Feature 044: Motor de Recomendación y Planificador Adaptativo de Estudio
// =============================================================================

let selectedPlannerMinutes = 60;
let currentPlannedBlocks = [];

async function openStudyPlannerModal() {
  const modal = document.getElementById('modal-study-planner');
  if (!modal) return;
  Au.modal.abrir('modal-study-planner');
  await loadPlannerBriefing();
  await generateAdaptiveStudyPlan();
}

function closeStudyPlannerModal() {
  Au.modal.cerrar('modal-study-planner');
}

function selectPlannerMinutes(min) {
  selectedPlannerMinutes = min;
  document.querySelectorAll('.planner-min-btn').forEach(btn => {
    const m = parseInt(btn.getAttribute('data-minutos') || btn.getAttribute('data-minutes'), 10);
    btn.setAttribute('aria-pressed', m === min ? 'true' : 'false');
  });
  generateAdaptiveStudyPlan();
}

async function loadPlannerBriefing() {
  try {
    const res = await fetch('/api/planner/daily-briefing');
    if (!res.ok) return;
    const b = await res.json();

    const streakEl = document.getElementById('planner-streak');
    if (streakEl) streakEl.textContent = `${b.racha_dias} días`;

    const fsrsEl = document.getElementById('planner-fsrs-due');
    if (fsrsEl) fsrsEl.textContent = `${b.fsrs_due_count} tarjetas`;

    const macroEl = document.getElementById('planner-macro-due');
    if (macroEl) macroEl.textContent = `${b.macro_fsrs_due_count} temas`;

    const studiedEl = document.getElementById('planner-studied-today');
    if (studiedEl) studiedEl.textContent = `${b.minutos_hoy} min`;

    const adviceEl = document.getElementById('planner-briefing-advice');
    if (adviceEl) adviceEl.textContent = b.mensaje_enfoque;

    const urgencyEl = document.getElementById('planner-urgency-badge');
    if (urgencyEl) {
      const u = b.urgency_score;
      let tono = 'exito';
      if (u > 60) tono = 'peligro';
      else if (u > 30) tono = 'alerta';

      urgencyEl.className = Au.clases('au-insignia', `au-insignia--${tono}`);
      urgencyEl.innerHTML = `${Au.icono('rapido')} Urgencia: ${u}/100`;
    }
  } catch (err) {
    console.error('Error al cargar briefing del planificador:', err);
  }
}

async function generateAdaptiveStudyPlan() {
  const startTimeInput = document.getElementById('planner-start-time');
  const breaksInput = document.getElementById('planner-include-breaks');
  const container = document.getElementById('planner-results-container');
  const list = document.getElementById('planner-blocks-list');
  const badge = document.getElementById('planner-total-time-badge');

  const startTime = startTimeInput && startTimeInput.value ? startTimeInput.value : null;
  const includeBreaks = breaksInput ? breaksInput.checked : true;

  try {
    const res = await fetch('/api/planner/recommendations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        available_minutes: selectedPlannerMinutes,
        start_time: startTime,
        include_breaks: includeBreaks,
      }),
    });

    if (!res.ok) {
      alert('No se pudo generar el plan adaptativo.');
      return;
    }

    const plan = await res.json();
    currentPlannedBlocks = plan.bloques || [];

    if (badge) badge.textContent = `${plan.total_minutos} min planificados (${currentPlannedBlocks.length} bloques)`;

    if (list) {
      list.innerHTML = '';
      const phaseStyles = {
        warmup_fsrs: { icon: 'tarjetas', bg: 'bg-violet-950/40 border-violet-800/60', text: 'text-violet-300' },
        macro_fsrs: { icon: 'repaso', bg: 'bg-sky-950/40 border-sky-800/60', text: 'text-sky-300' },
        deep_work_course: { icon: 'cursos', bg: 'bg-indigo-950/40 border-indigo-800/60', text: 'text-indigo-300' },
        active_reading_book: { icon: 'lectura', bg: 'bg-amber-950/40 border-amber-800/60', text: 'text-amber-300' },
        break: { icon: 'descanso', bg: 'bg-slate-900 border-slate-700/60', text: 'text-slate-400' },
      };

      currentPlannedBlocks.forEach((b) => {
        const style = phaseStyles[b.fase] || { icon: 'foco', bg: 'bg-slate-900 border-slate-800', text: 'text-slate-300' };
        const card = document.createElement('div');
        card.className = `p-3 rounded-xl border flex items-center justify-between gap-3 ${style.bg}`;
        card.innerHTML = `
          <div class="flex items-center gap-2.5">
            <span class="text-xl shrink-0" aria-hidden="true">${Au.icono(style.icon)}</span>
            <div>
              <div class="flex items-center gap-2">
                <span class="text-xs font-bold text-white">${escapeHtml(b.titulo || '')}</span>
                ${b.meta_especifica ? `<span class="au-insignia au-insignia--mono text-xs">${escapeHtml(b.meta_especifica)}</span>` : ''}
              </div>
              <p class="text-xs text-slate-400">${escapeHtml(b.descripcion || '')}</p>
            </div>
          </div>
          <div class="text-right whitespace-nowrap">
            <span class="text-xs font-bold ${style.text}">${b.duracion_minutos} min</span>
            <span class="block text-xs text-slate-400 font-mono">${escapeHtml(b.hora_inicio || '--')} - ${escapeHtml(b.hora_fin || '--')}</span>
          </div>
        `;
        list.appendChild(card);
      });
    }

    if (container) container.classList.remove('hidden');
  } catch (err) {
    console.error('Error al generar plan adaptativo:', err);
  }
}

async function applyPlanToScheduleAction() {
  if (!currentPlannedBlocks || currentPlannedBlocks.length === 0) {
    alert('No hay bloques de estudio generados para aplicar.');
    return;
  }

  try {
    const res = await fetch('/api/planner/apply-today', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bloques: currentPlannedBlocks,
        reemplazar_existentes: false,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      alert(data.mensaje);
      closeStudyPlannerModal();
      if (typeof loadSchedule === 'function') {
        loadSchedule();
      }
    } else {
      const err = await res.json();
      alert(`Error al aplicar a la agenda: ${err.detail || 'desconocido'}`);
    }
  } catch (err) {
    alert(`Error de red: ${err.message}`);
  }
}


// --- SESIÓN GUIADA EN 1 CLIC ("MISIÓN DE HOY") ---
let guidedSessionDuration = 45;
let currentGuidedStep = 1;

function openGuidedStudySessionModal() {
  const modal = document.getElementById('modal-guided-study-session');
  if (!modal) return;

  // Llenar detalles dinámicos según el estado del estudiante
  const fsrsCount = parseInt(document.getElementById('hero-count-fsrs')?.textContent || '0', 10);
  const step1Desc = document.getElementById('guided-step1-desc');
  if (step1Desc) {
    if (fsrsCount > 0) {
      step1Desc.textContent = `${fsrsCount} tarjeta(s) prioritarias en tu curva de olvido`;
    } else {
      step1Desc.textContent = 'Curva al día: 10 min de exploración o colocaciones nuevas';
    }
  }

  const courseName = document.getElementById('hero-course-name')?.textContent || '';
  const step2Desc = document.getElementById('guided-step2-desc');
  if (step2Desc) {
    if (courseName && !courseName.includes('Sin cursadas')) {
      step2Desc.textContent = `Avanzar en "${courseName}" o tema de la Ruta`;
    } else {
      step2Desc.textContent = 'Siguiente tema disponible en el Mapa de Requisitos Previos';
    }
  }

  const bookName = document.getElementById('hero-book-name')?.textContent || '';
  const step3Desc = document.getElementById('guided-step3-desc');
  if (step3Desc) {
    if (bookName && !bookName.includes('Sin libros')) {
      step3Desc.textContent = `10 páginas / Repaso activo en "${bookName}"`;
    } else {
      step3Desc.textContent = 'Auto-evaluación conceptual Feynman o repaso de apuntes';
    }
  }

  setGuidedSessionDuration(guidedSessionDuration);
  Au.modal.abrir('modal-guided-study-session');
}

function closeGuidedStudySessionModal() {
  Au.modal.cerrar('modal-guided-study-session');
}

function setGuidedSessionDuration(mins) {
  guidedSessionDuration = mins;
  [25, 45, 60].forEach(m => {
    const btn = document.getElementById(`btn-guided-dur-${m}`);
    if (btn) {
      btn.className = m === mins
        ? 'au-boton au-boton--primario au-boton--chico'
        : 'au-boton au-boton--secundario au-boton--chico';
    }
  });

  const t1 = document.getElementById('guided-step1-time');
  const t2 = document.getElementById('guided-step2-time');
  const t3 = document.getElementById('guided-step3-time');

  if (mins === 25) {
    if (t1) t1.textContent = '5 min';
    if (t2) t2.textContent = '15 min';
    if (t3) t3.textContent = '5 min';
  } else if (mins === 45) {
    if (t1) t1.textContent = '10 min';
    if (t2) t2.textContent = '25 min';
    if (t3) t3.textContent = '10 min';
  } else {
    if (t1) t1.textContent = '15 min';
    if (t2) t2.textContent = '35 min';
    if (t3) t3.textContent = '10 min';
  }
}

function launchGuidedStudySession() {
  closeGuidedStudySessionModal();
  currentGuidedStep = 1;

  // Iniciar Pomodoro con la duración elegida
  setPomodoroMinutes(guidedSessionDuration);
  if (!state.focusTimer.isRunning) {
    togglePomodoroTimer();
  }

  // Activar HUD
  updateGuidedSessionHud();
  const hud = document.getElementById('guided-session-hud');
  if (hud) hud.classList.remove('hidden');
  if (hud) hud.classList.add('flex');

  // Llevar a la primera fase (Inglés Técnico)
  switchTab('fsrs');
  showToast(`¡Misión iniciada! Fase 1: Calentamiento de Inglés Técnico (${guidedSessionDuration} min en marcha)`, 'success');
}

function updateGuidedSessionHud() {
  const title = document.getElementById('guided-hud-step-title');
  const count = document.getElementById('guided-hud-step-count');
  if (count) count.textContent = `Paso ${currentGuidedStep} de 3`;

  if (currentGuidedStep === 1) {
    if (title) title.textContent = 'Fase 1: Calentamiento de Inglés Técnico';
  } else if (currentGuidedStep === 2) {
    if (title) title.textContent = 'Fase 2: Bloque Principal (Ruta / Curso)';
  } else if (currentGuidedStep === 3) {
    if (title) title.textContent = 'Fase 3: Cierre & Repaso Activo';
  }
}

function nextGuidedSessionStep() {
  currentGuidedStep++;
  if (currentGuidedStep === 2) {
    updateGuidedSessionHud();
    switchTab('roadmap');
    showToast('Fase 2 activada: Enfocate en el siguiente tema de tu ruta', 'info');
  } else if (currentGuidedStep === 3) {
    updateGuidedSessionHud();
    switchTab('books');
    showToast('Fase 3 activada: Consolidá lo aprendido con lectura o repaso activo', 'info');
  } else {
    // Misión completada
    cancelGuidedSession();
    showToast('¡Felicitaciones! Has completado las 3 fases de la misión de estudio de hoy.', 'success');
  }
}

function cancelGuidedSession() {
  const hud = document.getElementById('guided-session-hud');
  if (hud) {
    hud.classList.add('hidden');
    hud.classList.remove('flex');
  }
  currentGuidedStep = 1;
}
