// --- ACCIONES DELEGADAS DE AGENDA (072 T6) ---
[
  ['abrir-google-calendar', () => openGoogleCalendarModal()],
  ['abrir-agendar-bloque', (el, datos) => datos.dia ? openAddScheduleModal(Number(datos.dia)) : openAddScheduleModal()],
  ['filtrar-agenda', (el, datos) => setScheduleFilter(datos.filtro)],
  ['ver-dias-agenda', (el, datos) => setScheduleDaysView(datos.dias)],
  ['tamano-tarjetas-agenda', (el, datos) => setScheduleCardSize(datos.tamano)],
  ['seleccionar-dia-agenda', (el, datos) => seleccionarDiaAgenda(Number(datos.dia))],
  ['sincronizar-bloque-gcal', (el, datos) => addBlockToGoogleCalendar(Number(datos.id))],
  ['confirmar-eliminar-bloque', (el, datos, evento) => confirmDeleteScheduleBlock(Number(datos.id), evento)],
  ['ajustar-minutos-bloque', (el, datos, evento) => quickExtendInlineScheduleBlock(Number(datos.id), Number(datos.minutos), evento)],
  ['modal-crear-bloque-agenda', (el, datos, ev) => handleCreateSchedule(ev)],
  ['modal-elegir-dia-agenda', (el, datos) => selectScheduleDay(Number(datos.dia))],
  ['modal-elegir-tipo-agenda', (el, datos) => selectScheduleType(datos.tipo)],
  ['modal-autocompletar-agenda', (el) => handleScheduleAutoFill(el)],
  ['modal-aplicar-preset-agenda', (el, datos) => applySchedulePreset(datos.inicio, datos.fin)],
  ['modal-cambiar-horario-agenda', () => updateScheduleDurationBadge()],
  ['modal-ejecutar-eliminar-agenda', () => executeDeleteScheduleBlock()],
  ['modal-actualizar-bloque-agenda', (el, datos, ev) => handleUpdateSchedule(ev)],
  ['modal-editar-dia-agenda', (el, datos) => selectEditScheduleDay(Number(datos.dia))],
  ['modal-editar-tipo-agenda', (el, datos) => selectEditScheduleType(datos.tipo)],
  ['modal-ajustar-minutos-agenda', (el, datos) => adjustEditScheduleMinutes(Number(datos.minutos))],
  ['modal-cambiar-horario-edicion-agenda', () => updateEditScheduleDurationBadge()],
  ['modal-extender-detalle-bloque', (el, datos) => quickExtendDetailBlock(Number(datos.minutos))],
  ['modal-iniciar-foco-detalle', () => launchFocusFromDetailBlock()],
  ['modal-editar-desde-detalle', () => openEditModalFromDetail()],
  ['modal-sincronizar-gcal-detalle', () => syncGcalFromDetail()],
  ['modal-eliminar-desde-detalle', () => deleteFromDetail()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

// --- AGENDA SEMANAL ---
async function loadSchedule() {
  try {
    const res = await fetch('/api/schedule');
    if (res.ok) {
      state.schedule = await res.json();
      renderSchedule();
    }
  } catch (err) {
    console.error("Error al cargar agenda:", err);
  }
}

const DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

const SCHEDULE_TYPE_META = {
  curso: {
    label: 'Curso',
    icon: 'cursos',
    borderClass: 'border-l-sky-500',
    badgeClass: 'bg-sky-950 text-sky-400 border border-sky-800/80',
    timeColor: 'text-sky-400',
  },
  ingles: {
    label: 'Inglés Técnico',
    icon: 'idioma',
    borderClass: 'border-l-emerald-500',
    badgeClass: 'bg-emerald-950 text-emerald-400 border border-emerald-800/80',
    timeColor: 'text-emerald-400',
  },
  lectura: {
    label: 'Lectura',
    icon: 'lectura',
    borderClass: 'border-l-purple-500',
    badgeClass: 'bg-purple-950 text-purple-400 border border-purple-800/80',
    timeColor: 'text-purple-400',
  },
  repaso: {
    label: 'Repaso',
    icon: 'repaso',
    borderClass: 'border-l-amber-500',
    badgeClass: 'bg-amber-950 text-amber-400 border border-amber-800/80',
    timeColor: 'text-amber-400',
  },
  otro: {
    label: 'Otro',
    icon: 'rapido',
    borderClass: 'border-l-slate-400',
    badgeClass: 'bg-slate-800 text-slate-300 border border-slate-700',
    timeColor: 'text-slate-300',
  },
};

function parseTimeMinutes(hhmm) {
  if (!hhmm || typeof hhmm !== 'string') return 0;
  const parts = hhmm.split(':');
  if (parts.length < 2) return 0;
  return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
}

function getDurationMinutes(start, end) {
  const s = parseTimeMinutes(start);
  const e = parseTimeMinutes(end);
  return e > s ? (e - s) : 0;
}

function formatDuration(minutes) {
  if (minutes <= 0) return '0m';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

function addMinutesToTime(timeStr, deltaMinutes) {
  if (!timeStr || typeof timeStr !== 'string') return '12:00';
  const parts = timeStr.split(':');
  let mins = (parseInt(parts[0], 10) || 0) * 60 + (parseInt(parts[1], 10) || 0);
  mins += deltaMinutes;
  if (mins < 0) mins = 0;
  if (mins > 23 * 60 + 59) mins = 23 * 60 + 59;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function setScheduleCardSize(size) {
  state.scheduleCardSize = size;
  const btnNormal = document.getElementById('btn-card-size-normal');
  const btnExpanded = document.getElementById('btn-card-size-expanded');
  if (btnNormal && btnExpanded) {
    btnNormal.setAttribute('aria-selected', size !== 'expanded');
    btnExpanded.setAttribute('aria-selected', size === 'expanded');
  }
  renderSchedule();
}

function setScheduleDaysView(view) {
  state.scheduleDaysView = view;
  document.querySelectorAll('.schedule-days-view-pill').forEach(btn => {
    btn.setAttribute('aria-selected', btn.getAttribute('data-days-view') === view);
  });
  renderSchedule();
}

function setScheduleFilter(filterType) {
  state.scheduleFilter = filterType;
  document.querySelectorAll('.schedule-filter-pill').forEach(btn => {
    btn.setAttribute('aria-selected', btn.getAttribute('data-filter') === filterType);
  });
  renderSchedule();
}

function seleccionarDiaAgenda(diaNum) {
  state.selectedScheduleDay = diaNum;
  renderSchedule();
}

function renderSchedule() {
  const container = document.getElementById('week-schedule-grid');
  if (!container) return;

  const allBlocks = state.schedule || [];

  const emptyScheduleBanner = document.getElementById('schedule-empty-banner');
  if (emptyScheduleBanner) {
    if (allBlocks.length === 0) {
      emptyScheduleBanner.classList.remove('hidden');
    } else {
      emptyScheduleBanner.classList.add('hidden');
    }
  }

  // 1. Cálculos de métricas globales (Horas semanales y desglose)
  let totalMinutes = 0;
  let cursosMinutes = 0;
  let inglesMinutes = 0;
  let lecturaMinutes = 0;
  let otrosMinutes = 0;

  allBlocks.forEach(b => {
    const dur = getDurationMinutes(b.hora_inicio, b.hora_fin);
    totalMinutes += dur;
    if (b.tipo === 'curso') cursosMinutes += dur;
    else if (b.tipo === 'ingles') inglesMinutes += dur;
    else if (b.tipo === 'lectura') lecturaMinutes += dur;
    else otrosMinutes += dur;
  });

  const kpiHours = document.getElementById('schedule-kpi-hours');
  if (kpiHours) kpiHours.innerText = (totalMinutes / 60).toFixed(1);
  const kpiTotal = document.getElementById('schedule-kpi-total');
  if (kpiTotal) kpiTotal.innerText = allBlocks.length;
  const kpiCursos = document.getElementById('schedule-kpi-cursos');
  if (kpiCursos) kpiCursos.innerText = (cursosMinutes / 60).toFixed(1);
  const kpiIngles = document.getElementById('schedule-kpi-ingles');
  if (kpiIngles) kpiIngles.innerText = (inglesMinutes / 60).toFixed(1);
  const kpiLectura = document.getElementById('schedule-kpi-lectura');
  if (kpiLectura) kpiLectura.innerText = (lecturaMinutes / 60).toFixed(1);
  const kpiOtros = document.getElementById('schedule-kpi-otros');
  if (kpiOtros) kpiOtros.innerText = (otrosMinutes / 60).toFixed(1);

  // 2. Indicador dinámico de "Hoy"
  const todayJs = new Date().getDay(); // 0=Dom, 1=Lun ... 6=Sab
  const todayDb = todayJs === 0 ? 7 : todayJs; // 1=Lun ... 7=Dom
  const todayBlocks = allBlocks.filter(b => b.dia_semana === todayDb);
  const todayIndicator = document.getElementById('schedule-today-indicator');
  if (todayIndicator) {
    todayIndicator.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
      <span>Hoy es <strong class="text-white">${DIAS_SEMANA[todayDb - 1]}</strong> • <span class="font-mono text-sky-400 font-bold">${todayBlocks.length}</span> ${todayBlocks.length === 1 ? 'bloque' : 'bloques'}</span>
    `;
  }

  // 3. Determinar qué días mostrar según la vista seleccionada (7d, 5d, today, weekend)
  const daysView = state.scheduleDaysView || '7d';
  let targetDays = [1, 2, 3, 4, 5, 6, 7]; // 1=Lun ... 7=Dom
  if (daysView === '5d') {
    targetDays = [1, 2, 3, 4, 5]; // Lun a Vie
  } else if (daysView === 'today') {
    targetDays = [todayDb]; // Solo hoy
  } else if (daysView === 'weekend') {
    targetDays = [6, 7]; // Sáb y Dom
  }

  // R10: Selector de día en vista celular (debajo de md): hoy por defecto, y siempre un día de la vista elegida
  if (!targetDays.includes(state.selectedScheduleDay)) {
    state.selectedScheduleDay = targetDays.includes(todayDb) ? todayDb : targetDays[0];
  }
  const selectedDay = state.selectedScheduleDay;

  let selectorDia = document.getElementById('agenda-selector-dia');
  if (!selectorDia) {
    selectorDia = document.createElement('div');
    selectorDia.id = 'agenda-selector-dia';
    selectorDia.className = 'md:hidden au-pestanas pb-3 mb-2 scroll-x-pista';
    container.parentNode.insertBefore(selectorDia, container);
  }

  selectorDia.innerHTML = targetDays.map(num => ({ num, letra: DIAS_SEMANA[num - 1][0] })).map(d => {
    const isActivo = (d.num === selectedDay);
    const esHoy = (d.num === todayDb);
    return `
      <button type="button" data-accion="seleccionar-dia-agenda" data-dia="${d.num}" role="tab" aria-selected="${isActivo}" class="au-pestanas__boton flex-1 flex flex-col items-center justify-center gap-0.5">
        <span>${d.letra}</span>
        ${esHoy ? '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>' : '<span class="w-1.5 h-1.5"></span>'}
      </button>
    `;
  }).join('');

  // 4. Renderizado de las columnas seleccionadas
  container.innerHTML = targetDays.map(diaNum => {
    const diaNom = DIAS_SEMANA[diaNum - 1];
    const isToday = (diaNum === todayDb);
    const isChosenDay = (diaNum === selectedDay);
    const responsiveFlex = isChosenDay ? 'flex flex-col' : 'hidden md:flex flex-col';
    const dayBlocks = allBlocks.filter(b => b.dia_semana === diaNum);

    // Filtrar según píldora seleccionada
    const currentFilter = state.scheduleFilter || 'todos';
    const visibleBlocks = currentFilter === 'todos' 
      ? dayBlocks 
      : dayBlocks.filter(b => b.tipo === currentFilter);

    // Ordenar cronológicamente por hora de inicio
    visibleBlocks.sort((a, b) => (a.hora_inicio || '').localeCompare(b.hora_inicio || ''));

    // Minutos del día
    const dayMinutes = dayBlocks.reduce((acc, b) => acc + getDurationMinutes(b.hora_inicio, b.hora_fin), 0);
    const dayHoursStr = (dayMinutes / 60).toFixed(1);

    // Ancho cómodo de columna según vista
    let columnWidthClass = 'w-full min-w-0 md:min-w-[300px] flex-1 shrink-0';
    if (daysView === 'today') {
      columnWidthClass = 'w-full max-w-2xl mx-auto min-w-0 md:min-w-[320px]';
    } else if (daysView === 'weekend') {
      columnWidthClass = 'w-full min-w-0 md:min-w-[300px] max-w-xl flex-1 shrink-0';
    } else if (daysView === '5d') {
      columnWidthClass = 'w-full min-w-0 md:min-w-[290px] flex-1 shrink-0';
    }

    const cardClasses = isToday
      ? `au-seccion au-seccion--suave border-2 border-sky-500/80 shadow-xl shadow-sky-950/50 min-h-[300px] ring-1 ring-sky-500/30 ${columnWidthClass} ${responsiveFlex}`
      : `au-seccion au-seccion--suave hover:border-slate-700/80 min-h-[300px] transition ${columnWidthClass} ${responsiveFlex}`;

    const botonAgregarDia = Au.boton({
      icono: 'agregar',
      soloIcono: true,
      variante: 'fantasma',
      chico: true,
      etiqueta: `Agendar bloque el ${diaNom}`,
      accion: 'abrir-agendar-bloque',
      datos: { dia: diaNum }
    });

    return `
      <div class="${cardClasses}" id="${isToday ? 'schedule-col-today' : `schedule-col-${diaNum}`}" data-dia-agenda="${diaNum}">
        <!-- Cabecera del Día -->
        <div class="border-b border-slate-800 pb-2.5 mb-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="font-bold ${isToday ? 'text-sky-400 font-extrabold text-base' : 'text-white text-sm'}">${diaNom}</span>
              ${isToday ? Au.insignia({ texto: 'HOY', tono: 'primario' }) : ''}
            </div>
            ${botonAgregarDia}
          </div>
          <div class="flex items-center justify-between text-xs text-slate-500 font-mono mt-1.5">
            <span>${dayBlocks.length} ${dayBlocks.length === 1 ? 'bloque' : 'bloques'}</span>
            ${Au.insignia({ texto: `${dayHoursStr} hs`, mono: true })}
          </div>
        </div>

        <!-- Lista de Bloques del Día -->
        ${visibleBlocks.length === 0 ? Au.vacio({
          texto: dayBlocks.length === 0 ? 'Sin bloques agendados' : 'Sin coincidencia con filtro',
          accionHtml: Au.boton({
            texto: 'Agendar actividad',
            icono: 'agregar',
            variante: 'fantasma',
            chico: true,
            accion: 'abrir-agendar-bloque',
            datos: { dia: diaNum }
          })
        }) : `
          <div class="space-y-2.5 flex-1">
            ${visibleBlocks.map(b => {
              const meta = SCHEDULE_TYPE_META[b.tipo] || SCHEDULE_TYPE_META.otro;
              const durMin = getDurationMinutes(b.hora_inicio, b.hora_fin);
              const durStr = formatDuration(durMin);
              const isExpanded = (state.scheduleCardSize === 'expanded');

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
              const botonGcal = Au.boton({
                icono: 'agenda',
                soloIcono: true,
                variante: 'fantasma',
                chico: true,
                etiqueta: 'Sincronizar este bloque con Google Calendar',
                accion: 'sincronizar-bloque-gcal',
                datos: { id: Number(b.id) }
              });
              const botonEliminar = Au.boton({
                icono: 'borrar',
                soloIcono: true,
                variante: 'fantasma',
                chico: true,
                etiqueta: 'Eliminar bloque de horario',
                accion: 'confirmar-eliminar-bloque',
                datos: { id: Number(b.id) }
              });
              const enlaceAcceso = b.url_acceso ? Au.boton({
                texto: 'Acceso ↗',
                variante: 'fantasma',
                chico: true,
                href: b.url_acceso,
                attrs: { target: '_blank', rel: 'noopener noreferrer' }
              }) : '';

              return `
                <div data-accion="detalle-bloque-agenda" data-id="${Number(b.id)}" class="au-tarjeta au-tarjeta--plana au-tarjeta--interactiva ${meta.borderClass} border-l-4 cursor-pointer">
                  <!-- Fila 1: Horario, Duración y Botones de Acción -->
                  <div class="flex flex-wrap items-center justify-between gap-1.5 pb-1.5 border-b border-slate-800 text-xs font-mono">
                    <div class="flex items-center gap-1.5 min-w-0">
                      <span class="${meta.timeColor} font-bold">${Au.escapar(b.hora_inicio)} - ${Au.escapar(b.hora_fin)}</span>
                      ${Au.insignia({ texto: durStr, mono: true })}
                    </div>
                    <div class="flex items-center gap-0.5 shrink-0 ml-auto">
                      ${botonDetalle}
                      ${botonEditar}
                      ${botonGcal}
                      ${botonEliminar}
                    </div>
                  </div>

                  <!-- Fila 2: Título / Descripción -->
                  <p class="text-xs font-semibold text-slate-200 leading-snug break-words ${isExpanded ? '' : 'line-clamp-2'}">
                    ${Au.escapar(b.descripcion)}
                  </p>

                  <!-- Fila 3: Categoría y Botón de Acceso Directo -->
                  <div class="flex items-center justify-between gap-2 pt-0.5 text-xs">
                    ${Au.insignia({ texto: meta.label, icono: meta.icon })}
                    ${enlaceAcceso}
                  </div>

                  ${isExpanded ? `
                    <!-- Fila 4 (Modo Agrandado): Controles directos de redimensión -->
                    <div data-sin-accion class="pt-2 border-t border-slate-800 flex items-center justify-between text-xs font-mono">
                      <div class="flex items-center gap-1">
                        <span class="text-xs text-slate-500">Ajustar:</span>
                        ${Au.boton({ texto: '+15m', variante: 'secundario', chico: true, etiqueta: 'Sumar 15 minutos', accion: 'ajustar-minutos-bloque', datos: { id: Number(b.id), minutos: 15 } })}
                        ${Au.boton({ texto: '+30m', variante: 'secundario', chico: true, etiqueta: 'Sumar 30 minutos', accion: 'ajustar-minutos-bloque', datos: { id: Number(b.id), minutos: 30 } })}
                        ${Au.boton({ texto: '-15m', variante: 'secundario', chico: true, etiqueta: 'Restar 15 minutos', accion: 'ajustar-minutos-bloque', datos: { id: Number(b.id), minutos: -15 } })}
                      </div>
                      ${Au.boton({ texto: 'Detalle', icono: 'ver', variante: 'fantasma', chico: true, accion: 'detalle-bloque-agenda', datos: { id: Number(b.id) } })}
                    </div>
                  ` : ''}
                </div>
              `;
            }).join('')}
          </div>
        `}
      </div>
    `;
  }).join('');

  // Auto-scroll suave para centrar el día de hoy si estamos en vista de 7 días
  if (daysView === '7d' && !state.hasAutoScrolledSchedule) {
    state.hasAutoScrolledSchedule = true;
    setTimeout(() => {
      const todayEl = document.getElementById('schedule-col-today');
      if (todayEl) {
        todayEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    }, 150);
  }
}

let scheduleBlockPendingDelete = null;

function confirmDeleteScheduleBlock(blockId, event) {
  if (event) event.stopPropagation();
  const block = (state.schedule || []).find(b => b.id === blockId);
  if (!block) return;

  scheduleBlockPendingDelete = block;

  const preview = document.getElementById('delete-schedule-preview');
  if (preview) {
    const meta = SCHEDULE_TYPE_META[block.tipo] || SCHEDULE_TYPE_META.otro;
    const diaNom = DIAS_SEMANA[block.dia_semana - 1] || `Día ${block.dia_semana}`;
    const durMin = getDurationMinutes(block.hora_inicio, block.hora_fin);
    const durStr = formatDuration(durMin);

    preview.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="font-bold text-white text-sm">${escapeHtml(diaNom)}</span>
        <span class="font-mono text-xs font-semibold ${meta.timeColor}">${escapeHtml(block.hora_inicio)} - ${escapeHtml(block.hora_fin)} (${durStr})</span>
      </div>
      <p class="text-slate-300 font-medium">${escapeHtml(block.descripcion)}</p>
      <div class="pt-1 flex items-center justify-between text-xs">
        <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs ${meta.badgeClass}">
          ${Au.icono(meta.icon)} <span>${meta.label}</span>
        </span>
        ${block.url_acceso ? `<span class="text-slate-500 truncate max-w-[180px] inline-flex items-center gap-1">${Au.icono('enlace')} ${escapeHtml(block.url_acceso)}</span>` : ''}
      </div>
    `;
  }

  Au.modal.abrir('delete-schedule-modal');
}

function closeDeleteScheduleModal() {
  Au.modal.cerrar('delete-schedule-modal');
}

document.getElementById('delete-schedule-modal')?.addEventListener('au:cerrado', () => {
  scheduleBlockPendingDelete = null;
});

async function executeDeleteScheduleBlock() {
  if (!scheduleBlockPendingDelete) return;
  const blockId = scheduleBlockPendingDelete.id;
  const btn = document.getElementById('btn-confirm-delete-schedule');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `${Au.icono('cargando')} Eliminando...`;
  }

  try {
    const res = await fetch(`/api/schedule/${blockId}`, {
      method: 'DELETE',
    });
    if (res.ok) {
      closeDeleteScheduleModal();
      showToast('Bloque de estudio eliminado con éxito.', 'success');
      await loadSchedule();
      renderDashboard();
      populateFocusBlockSelect();
    } else {
      showToast('No se pudo eliminar el bloque.', 'error');
    }
  } catch (err) {
    console.error("Error al eliminar bloque de horario:", err);
    showToast('Error de conexión al eliminar el bloque.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `${Au.icono('borrar')} Sí, eliminar bloque`;
    }
  }
}

// --- ONBOARDING STARTER ACTIONS ---
// --- MODAL: AGENDAR BLOQUE SEMANAL ---
function openAddScheduleModal(diaNum = null) {
  const modal = document.getElementById('add-schedule-modal');
  if (!modal) return;

  // Determinar día por defecto: el día pasado por argumento, o el día de hoy
  let targetDay = diaNum;
  if (!targetDay) {
    const todayJs = new Date().getDay();
    targetDay = todayJs === 0 ? 7 : todayJs;
  }
  selectScheduleDay(targetDay);

  // Tipo por defecto: curso
  selectScheduleType('curso');

  // Horarios por defecto si están vacíos
  const startEl = document.getElementById('new-schedule-start');
  const endEl = document.getElementById('new-schedule-end');
  if (startEl && !startEl.value) startEl.value = '10:30';
  if (endEl && !endEl.value) endEl.value = '12:30';

  // Limpiar campos
  const descEl = document.getElementById('new-schedule-desc');
  if (descEl) descEl.value = '';
  const urlEl = document.getElementById('new-schedule-url');
  if (urlEl) urlEl.value = '';

  // Poblar dropdown de autocompletado y calcular duración
  populateScheduleAutoFillSelect();
  updateScheduleDurationBadge();

  Au.modal.abrir('add-schedule-modal');
  if (descEl) setTimeout(() => descEl.focus(), 50);
}

function closeAddScheduleModal() {
  Au.modal.cerrar('add-schedule-modal');
}

function selectScheduleDay(diaNum) {
  const hiddenInput = document.getElementById('new-schedule-day');
  if (hiddenInput) hiddenInput.value = diaNum;

  document.querySelectorAll('.schedule-day-pill').forEach(btn => {
    const d = parseInt(btn.getAttribute('data-day'), 10);
    btn.setAttribute('aria-pressed', d === diaNum ? 'true' : 'false');
  });
}

function selectScheduleType(tipo) {
  const hiddenInput = document.getElementById('new-schedule-type');
  if (hiddenInput) hiddenInput.value = tipo;

  document.querySelectorAll('.schedule-type-chip').forEach(btn => {
    const t = btn.getAttribute('data-type');
    btn.setAttribute('aria-pressed', t === tipo ? 'true' : 'false');
  });
}

function applySchedulePreset(inicio, fin) {
  const startEl = document.getElementById('new-schedule-start');
  const endEl = document.getElementById('new-schedule-end');
  if (startEl) startEl.value = inicio;
  if (endEl) endEl.value = fin;
  updateScheduleDurationBadge();
}

function updateScheduleDurationBadge() {
  const badge = document.getElementById('new-schedule-duration-badge');
  if (!badge) return;

  const start = document.getElementById('new-schedule-start')?.value;
  const end = document.getElementById('new-schedule-end')?.value;
  if (!start || !end) {
    badge.innerHTML = `${Au.icono('cargando')} Definir horarios`;
    badge.className = 'au-insignia au-insignia--mono';
    return;
  }

  const dur = getDurationMinutes(start, end);
  if (dur <= 0) {
    badge.innerHTML = `${Au.icono('alerta')} Fin debe ser posterior a inicio`;
    badge.className = 'au-insignia au-insignia--peligro au-insignia--mono font-bold';
  } else {
    badge.innerHTML = `${Au.icono('cargando')} Duración: ${formatDuration(dur)}`;
    badge.className = 'au-insignia au-insignia--primario au-insignia--mono font-semibold';
  }
}

function populateScheduleAutoFillSelect() {
  const select = document.getElementById('new-schedule-autofill');
  if (!select) return;

  const allCourses = state.platforms ? state.platforms.flatMap(p => (p.cursos || []).map(c => ({ ...c, plataformaNombre: p.nombre }))) : [];
  const activeBooks = state.books || [];

  let html = '<option value="">-- Seleccionar curso o libro activo --</option>';

  if (allCourses.length > 0) {
    html += '<optgroup label="Cursos">';
    allCourses.forEach(c => {
      const dataPayload = JSON.stringify({
        tipo: 'curso',
        desc: `${c.nombre_curso} (${c.plataformaNombre})`,
        url: c.url_aula || '',
      });
      html += `<option value='${escapeHtml(dataPayload)}'>${escapeHtml(c.nombre_curso)} • ${escapeHtml(c.plataformaNombre)}</option>`;
    });
    html += '</optgroup>';
  }

  if (activeBooks.length > 0) {
    html += '<optgroup label="Libros Técnicos">';
    activeBooks.forEach(b => {
      const dataPayload = JSON.stringify({
        tipo: 'lectura',
        desc: `Lectura: ${b.titulo}${b.autor ? ` — ${b.autor}` : ''}`,
        url: '',
      });
      html += `<option value='${escapeHtml(dataPayload)}'>${escapeHtml(b.titulo)} (${escapeHtml(b.autor || 'Libro')})</option>`;
    });
    html += '</optgroup>';
  }

  // Presets especiales para inglés FSRS y Obsidian
  html += '<optgroup label="Inglés & Repaso">';
  html += `<option value='${JSON.stringify({ tipo: 'ingles', desc: 'Inglés Técnico FSRS (Vocabulario & Collocations)', url: '' })}'>Sesión Diaria Inglés FSRS</option>`;
  html += `<option value='${JSON.stringify({ tipo: 'repaso', desc: 'Repaso y Conexión de Mis notas', url: '' })}'>Repaso de Notas / MOCs en Obsidian</option>`;
  html += '</optgroup>';

  select.innerHTML = html;
}

function handleScheduleAutoFill(selectEl) {
  if (!selectEl.value) return;
  try {
    const data = JSON.parse(selectEl.value);
    if (data.desc) {
      const descInput = document.getElementById('new-schedule-desc');
      if (descInput) descInput.value = data.desc;
    }
    if (data.url !== undefined) {
      const urlInput = document.getElementById('new-schedule-url');
      if (urlInput) urlInput.value = data.url;
    }
    if (data.tipo) {
      selectScheduleType(data.tipo);
    }
  } catch (err) {
    console.error("Error al autocompletar horario:", err);
  }
}

async function handleCreateSchedule(event) {
  event.preventDefault();
  const diaSemana = parseInt(document.getElementById('new-schedule-day').value, 10);
  const tipo = document.getElementById('new-schedule-type').value;
  const horaInicio = document.getElementById('new-schedule-start').value.trim();
  const horaFin = document.getElementById('new-schedule-end').value.trim();
  const descripcion = document.getElementById('new-schedule-desc').value.trim();
  const urlAcceso = (document.getElementById('new-schedule-url')?.value || '').trim();

  if (!horaInicio || !horaFin || !descripcion) {
    alert("Por favor completá los campos obligatorios (horarios y descripción).");
    return;
  }

  if (horaFin <= horaInicio) {
    alert("La hora de fin debe ser posterior a la hora de inicio.");
    return;
  }

  const btnSubmit = document.getElementById('btn-submit-schedule');
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.innerHTML = `${Au.icono('cargando')} Guardando...`;
  }

  try {
    const res = await fetch('/api/schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dia_semana: diaSemana,
        hora_inicio: horaInicio,
        hora_fin: horaFin,
        tipo: tipo,
        descripcion: descripcion,
        url_acceso: urlAcceso || null,
      }),
    });

    if (res.ok) {
      closeAddScheduleModal();
      await loadSchedule();
      renderDashboard();
      populateFocusBlockSelect();
    } else {
      const errData = await res.json().catch(() => ({}));
      alert(`Error al agendar bloque: ${errData.detail || 'Ocurrió un error'}`);
    }
  } catch (err) {
    console.error("Error al agendar bloque:", err);
    alert("Error de conexión al agendar el bloque.");
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = `${Au.icono('guardar')} Agendar Bloque`;
    }
  }
}

// --- MODAL: EDITAR BLOQUE SEMANAL ---
function openEditScheduleModal(blockId, event) {
  if (event) event.stopPropagation();
  const block = (state.schedule || []).find(b => b.id === blockId);
  if (!block) return;

  const idInput = document.getElementById('edit-schedule-id');
  if (idInput) idInput.value = block.id;

  selectEditScheduleDay(block.dia_semana);
  selectEditScheduleType(block.tipo);

  const startInput = document.getElementById('edit-schedule-start');
  const endInput = document.getElementById('edit-schedule-end');
  const descInput = document.getElementById('edit-schedule-desc');
  const urlInput = document.getElementById('edit-schedule-url');

  if (startInput) startInput.value = block.hora_inicio;
  if (endInput) endInput.value = block.hora_fin;
  if (descInput) descInput.value = block.descripcion;
  if (urlInput) urlInput.value = block.url_acceso || '';

  updateEditScheduleDurationBadge();

  Au.modal.abrir('edit-schedule-modal');
}

function closeEditScheduleModal() {
  Au.modal.cerrar('edit-schedule-modal');
}

function selectEditScheduleDay(diaNum) {
  const hiddenInput = document.getElementById('edit-schedule-day');
  if (hiddenInput) hiddenInput.value = diaNum;

  document.querySelectorAll('.edit-schedule-day-pill').forEach(btn => {
    const d = parseInt(btn.getAttribute('data-edit-day'), 10);
    btn.setAttribute('aria-pressed', d === diaNum ? 'true' : 'false');
  });
}

function selectEditScheduleType(tipo) {
  const hiddenInput = document.getElementById('edit-schedule-type');
  if (hiddenInput) hiddenInput.value = tipo;

  document.querySelectorAll('.edit-schedule-type-chip').forEach(btn => {
    const t = btn.getAttribute('data-edit-type');
    btn.setAttribute('aria-pressed', t === tipo ? 'true' : 'false');
  });
}

function adjustEditScheduleMinutes(minutes) {
  const startEl = document.getElementById('edit-schedule-start');
  const endEl = document.getElementById('edit-schedule-end');
  if (!startEl || !endEl || !endEl.value) return;

  const curFin = endEl.value;
  const newFin = addMinutesToTime(curFin, minutes);
  const startVal = startEl.value;

  if (startVal && newFin <= startVal) {
    alert("La nueva hora fin no puede ser anterior o igual a la hora de inicio.");
    return;
  }

  endEl.value = newFin;
  updateEditScheduleDurationBadge();
}

function updateEditScheduleDurationBadge() {
  const badge = document.getElementById('edit-schedule-duration-badge');
  if (!badge) return;

  const start = document.getElementById('edit-schedule-start')?.value;
  const end = document.getElementById('edit-schedule-end')?.value;
  if (!start || !end) {
    badge.innerHTML = `${Au.icono('cargando')} Definir horarios`;
    badge.className = 'au-insignia au-insignia--mono';
    return;
  }

  const dur = getDurationMinutes(start, end);
  if (dur <= 0) {
    badge.innerHTML = `${Au.icono('alerta')} Fin debe ser posterior a inicio`;
    badge.className = 'au-insignia au-insignia--peligro au-insignia--mono font-bold';
  } else {
    badge.innerHTML = `${Au.icono('cargando')} Duración: ${formatDuration(dur)}`;
    badge.className = 'au-insignia au-insignia--alerta au-insignia--mono font-semibold';
  }
}

async function handleUpdateSchedule(event) {
  event.preventDefault();
  const blockId = document.getElementById('edit-schedule-id')?.value;
  if (!blockId) return;

  const diaSemana = parseInt(document.getElementById('edit-schedule-day').value, 10);
  const tipo = document.getElementById('edit-schedule-type').value;
  const horaInicio = document.getElementById('edit-schedule-start').value.trim();
  const horaFin = document.getElementById('edit-schedule-end').value.trim();
  const descripcion = document.getElementById('edit-schedule-desc').value.trim();
  const urlAcceso = (document.getElementById('edit-schedule-url')?.value || '').trim();

  if (!horaInicio || !horaFin || !descripcion) {
    alert("Por favor completá los campos obligatorios (horarios y descripción).");
    return;
  }

  if (horaFin <= horaInicio) {
    alert("La hora de fin debe ser posterior a la hora de inicio.");
    return;
  }

  const btnSubmit = document.getElementById('btn-submit-edit-schedule');
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.innerHTML = `${Au.icono('cargando')} Guardando...`;
  }

  try {
    const res = await fetch(`/api/schedule/${blockId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dia_semana: diaSemana,
        hora_inicio: horaInicio,
        hora_fin: horaFin,
        tipo: tipo,
        descripcion: descripcion,
        url_acceso: urlAcceso || null,
      }),
    });

    if (res.ok) {
      closeEditScheduleModal();
      await loadSchedule();
      renderDashboard();
      populateFocusBlockSelect();

      // Si el modal de detalle estaba abierto para este bloque, actualizarlo
      if (state.scheduleBlockInDetail && state.scheduleBlockInDetail.id === parseInt(blockId, 10)) {
        openScheduleCardDetailModal(parseInt(blockId, 10));
      }
    } else {
      const errData = await res.json().catch(() => ({}));
      alert(`Error al actualizar bloque: ${errData.detail || 'Ocurrió un error'}`);
    }
  } catch (err) {
    console.error("Error al actualizar bloque:", err);
    alert("Error de conexión al actualizar el bloque.");
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = `${Au.icono('guardar')} Guardar Cambios`;
    }
  }
}

// --- MODAL: DETALLE COMPLETO Y AGRANDADO DE TARJETA ---
function openScheduleCardDetailModal(blockId, event) {
  if (event) event.stopPropagation();
  const block = (state.schedule || []).find(b => b.id === blockId);
  if (!block) return;

  state.scheduleBlockInDetail = block;

  const diaNom = DIAS_SEMANA[block.dia_semana - 1] || `Día ${block.dia_semana}`;
  const meta = SCHEDULE_TYPE_META[block.tipo] || SCHEDULE_TYPE_META.otro;
  const durMin = getDurationMinutes(block.hora_inicio, block.hora_fin);
  const durStr = formatDuration(durMin);

  const titleEl = document.getElementById('detail-schedule-title');
  if (titleEl) titleEl.innerText = block.descripcion;

  const dayEl = document.getElementById('detail-schedule-day');
  if (dayEl) dayEl.innerText = `${diaNom} (Día ${block.dia_semana})`;

  const timeEl = document.getElementById('detail-schedule-time');
  if (timeEl) timeEl.innerText = `${block.hora_inicio} - ${block.hora_fin}`;

  const durEl = document.getElementById('detail-schedule-duration');
  if (durEl) durEl.innerText = durStr;

  const iconContainer = document.getElementById('detail-schedule-icon-container');
  if (iconContainer) iconContainer.innerHTML = Au.icono(meta.icon);

  const badgeEl = document.getElementById('detail-schedule-badge');
  if (badgeEl) {
    badgeEl.className = `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-xs font-semibold ${meta.badgeClass}`;
    badgeEl.innerHTML = `${Au.icono(meta.icon)} <span>${meta.label}</span>`;
  }

  const urlWrap = document.getElementById('detail-schedule-url-wrap');
  if (urlWrap) {
    if (block.url_acceso) {
      urlWrap.innerHTML = Au.boton({
        texto: 'Entrar al Aula ↗',
        icono: 'empezar',
        variante: 'primario',
        chico: true,
        href: block.url_acceso,
        attrs: { target: '_blank', rel: 'noopener noreferrer' }
      });
    } else {
      urlWrap.innerHTML = '<span class="text-xs text-slate-500 italic">Sin enlace directo</span>';
    }
  }

  Au.modal.abrir('schedule-card-detail-modal');
}

function closeScheduleCardDetailModal() {
  Au.modal.cerrar('schedule-card-detail-modal');
}

document.getElementById('schedule-card-detail-modal')?.addEventListener('au:cerrado', () => {
  state.scheduleBlockInDetail = null;
});

async function quickExtendDetailBlock(deltaMinutes) {
  if (!state.scheduleBlockInDetail) return;
  const block = state.scheduleBlockInDetail;
  const newFin = addMinutesToTime(block.hora_fin, deltaMinutes);
  if (newFin <= block.hora_inicio) {
    alert("La nueva hora de fin debe ser posterior a la hora de inicio.");
    return;
  }

  try {
    const res = await fetch(`/api/schedule/${block.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hora_fin: newFin }),
    });

    if (res.ok) {
      const updated = await res.json();
      await loadSchedule();
      renderDashboard();
      populateFocusBlockSelect();

      // Refrescar modal de detalle con el bloque actualizado
      const refreshed = (state.schedule || []).find(b => b.id === block.id) || updated;
      openScheduleCardDetailModal(refreshed.id);
    } else {
      const err = await res.json().catch(() => ({}));
      alert(`Error al ajustar duración: ${err.detail || 'No se pudo actualizar'}`);
    }
  } catch (err) {
    console.error("Error al ajustar duración del bloque:", err);
    alert("Error de conexión al ajustar el horario.");
  }
}

async function quickExtendInlineScheduleBlock(blockId, deltaMinutes, event) {
  if (event) event.stopPropagation();
  const block = (state.schedule || []).find(b => b.id === blockId);
  if (!block) return;

  const newFin = addMinutesToTime(block.hora_fin, deltaMinutes);
  if (newFin <= block.hora_inicio) {
    alert("La nueva hora de fin debe ser posterior a la hora de inicio.");
    return;
  }

  try {
    const res = await fetch(`/api/schedule/${blockId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hora_fin: newFin }),
    });

    if (res.ok) {
      await loadSchedule();
      renderDashboard();
      populateFocusBlockSelect();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(`Error al agrandar bloque: ${err.detail || 'No se pudo actualizar'}`);
    }
  } catch (err) {
    console.error("Error al agrandar bloque:", err);
    alert("Error de conexión al actualizar bloque.");
  }
}

function launchFocusFromDetailBlock() {
  if (!state.scheduleBlockInDetail) return;
  const block = state.scheduleBlockInDetail;
  closeScheduleCardDetailModal();

  switchTab('dashboard');

  const blockSelect = document.getElementById('focus-block-select');
  if (blockSelect) {
    blockSelect.value = String(block.id);
  }

  const dur = getDurationMinutes(block.hora_inicio, block.hora_fin);
  if (dur > 0 && dur <= 180) {
    setPomodoroMinutes(dur);
  }

  const timerEl = document.getElementById('focus-timer-section') || document.getElementById('hdr-focus-timer');
  if (timerEl) timerEl.scrollIntoView({ behavior: 'smooth' });
}

function openEditModalFromDetail() {
  if (!state.scheduleBlockInDetail) return;
  const blockId = state.scheduleBlockInDetail.id;
  closeScheduleCardDetailModal();
  openEditScheduleModal(blockId);
}

function syncGcalFromDetail() {
  if (!state.scheduleBlockInDetail) return;
  addBlockToGoogleCalendar(state.scheduleBlockInDetail.id);
}

function deleteFromDetail() {
  if (!state.scheduleBlockInDetail) return;
  const blockId = state.scheduleBlockInDetail.id;
  closeScheduleCardDetailModal();
  confirmDeleteScheduleBlock(blockId);
}

// --- GOOGLE CALENDAR INTEGRATION ---
async function openGoogleCalendarModal() {
  Au.modal.abrir('google-calendar-modal');
  if (cargarFeedDelCalendario) cargarFeedDelCalendario();

  const countBadge = document.getElementById('gcal-modal-block-count');
  const container = document.getElementById('gcal-modal-blocks-list');
  if (container) {
    container.innerHTML = '<p class="text-xs text-slate-500 italic text-center py-6">Cargando bloques de estudio y enlaces de Google Calendar...</p>';
  }

  try {
    const res = await fetch('/api/schedule/google-calendar/links');
    if (!res.ok) throw new Error("Error al obtener bloques de Google Calendar");
    const blocks = await res.json();

    if (countBadge) countBadge.innerText = `${blocks.length} bloques`;

    if (!container) return;
    if (blocks.length === 0) {
      container.innerHTML = '<p class="text-xs text-slate-500 italic text-center py-6">No hay bloques agendados en el cronograma semanal.</p>';
      return;
    }

    container.innerHTML = blocks.map(b => `
      <div class="au-tarjeta au-tarjeta--hundida flex items-center justify-between gap-3 hover:border-slate-700 transition">
        <div class="space-y-1 min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-xs font-bold text-white">${escapeHtml(b.dia_nombre)}</span>
            <span class="text-xs font-mono text-sky-400 font-semibold">${escapeHtml(b.hora_inicio)} - ${escapeHtml(b.hora_fin)}</span>
            <span class="au-insignia au-insignia--mono uppercase">
              ${escapeHtml(b.tipo)}
            </span>
          </div>
          <p class="text-xs text-slate-300 font-medium truncate">${escapeHtml(b.descripcion)}</p>
          ${b.url_acceso ? `<p class="text-xs text-slate-500 truncate">Enlace: <a href="${sanitizeUrl(b.url_acceso)}" target="_blank" class="text-sky-400 hover:underline">${escapeHtml(b.url_acceso)}</a></p>` : ''}
        </div>
        <div class="flex items-center gap-2">
          ${Au.boton({
            texto: 'Abrir en GCal',
            icono: 'agenda',
            variante: 'secundario',
            chico: true,
            href: b.gcal_url,
            attrs: { target: '_blank', title: 'Agregar evento recurrente a Google Calendar' }
          })}
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error("Error al cargar integración de Google Calendar:", err);
    if (container) {
      container.innerHTML = `<p class="text-xs text-rose-400 text-center py-4">Error al cargar bloques: ${escapeHtml(err.message)}</p>`;
    }
  }
}

function closeGoogleCalendarModal() {
  Au.modal.cerrar('google-calendar-modal');
}

async function addBlockToGoogleCalendar(blockId) {
  try {
    const res = await fetch(`/api/schedule/google-calendar/link/${blockId}`);
    if (res.ok) {
      const data = await res.json();
      if (data.gcal_url) {
        window.open(data.gcal_url, '_blank');
      }
    } else {
      alert("No se pudo generar el enlace a Google Calendar para este bloque.");
    }
  } catch (err) {
    console.error("Error al abrir bloque en Google Calendar:", err);
    alert("Error al conectar con el servidor para Google Calendar.");
  }
}

// --- FOCUS TIMER (POMODORO) & SESIONES DE ESTUDIO ---
async function loadFocusStats() {
  try {
    const res = await fetch('/api/focus/stats');
    if (res.ok) {
      const stats = await res.json();
      state.focusTimer.stats = stats;
      const hdrFocus = document.getElementById('hdr-focus');
      if (hdrFocus) {
        if (stats.minutos_hoy >= 60) {
          hdrFocus.innerHTML = `${Au.icono('foco')} ${stats.horas_hoy}h foco`;
        } else {
          hdrFocus.innerHTML = `${Au.icono('foco')} ${stats.minutos_hoy}m foco`;
        }
        hdrFocus.title = `Hoy: ${stats.minutos_hoy} min (${stats.horas_hoy} hrs) | Esta semana: ${stats.minutos_semana} min (${stats.horas_semana} hrs en ${stats.sesiones_semana} bloques)`;
      }
    }
  } catch (err) {
    console.error("Error al cargar estadísticas de focus:", err);
  }
}

function populateFocusBlockSelect() {
  const select = document.getElementById('pomodoro-block-select');
  if (!select) return;
  const blocks = state.schedule || [];
  const options = ['<option value="">Sesión Libre (Sin bloque)</option>'];

  blocks.forEach(b => {
    const diaNom = DIAS_SEMANA[b.dia_semana - 1] || `Día ${Number(b.dia_semana)}`;
    options.push(`<option value="${Number(b.id)}">[${escapeHtml(diaNom)} ${escapeHtml(b.hora_inicio)}] ${escapeHtml(b.descripcion)} (${escapeHtml(b.tipo)})</option>`);
  });

  select.innerHTML = options.join('');
}

function setPomodoroMinutes(minutes) {
  state.focusTimer.durationMinutes = minutes;
  state.focusTimer.remainingSeconds = minutes * 60;
  if (state.focusTimer.intervalId) {
    clearInterval(state.focusTimer.intervalId);
    state.focusTimer.intervalId = null;
    state.focusTimer.isRunning = false;
  }
  updatePomodoroDisplay();
  const toggleBtn = document.getElementById('btn-pomodoro-toggle');
  const icon = document.getElementById('btn-pomodoro-icon');
  const text = document.getElementById('btn-pomodoro-text');
  const badge = document.getElementById('pomodoro-state-badge');
  if (toggleBtn && icon && text && badge) {
    toggleBtn.className = "au-boton au-boton--primario flex-1";
    icon.innerText = "▶";
    text.innerText = "Iniciar Foco";
    badge.innerText = "Listo";
    badge.className = "au-insignia au-insignia--primario mt-2";
  }
}

function updatePomodoroDisplay() {
  const display = document.getElementById('pomodoro-timer-display');
  const hdrPill = document.getElementById('hdr-persistent-pomodoro');
  const hdrTime = document.getElementById('hdr-pomodoro-time');
  const hdrIcon = document.getElementById('hdr-pomodoro-icon');
  const hdrDot = document.getElementById('hdr-pomodoro-dot');

  const mins = Math.floor(state.focusTimer.remainingSeconds / 60);
  const secs = state.focusTimer.remainingSeconds % 60;
  const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

  if (display) display.innerText = timeStr;
  if (hdrTime) hdrTime.innerText = timeStr;

  if (hdrPill) {
    if (state.focusTimer.isRunning || state.focusTimer.remainingSeconds < state.focusTimer.durationMinutes * 60) {
      hdrPill.classList.remove('hidden');
      hdrPill.classList.add('flex');
    } else {
      hdrPill.classList.add('hidden');
      hdrPill.classList.remove('flex');
    }
  }

  if (hdrIcon) {
    hdrIcon.innerHTML = state.focusTimer.isRunning ? Au.icono('pausa') : '▶';
  }
  if (hdrDot) {
    if (state.focusTimer.isRunning) {
      hdrDot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
    } else {
      hdrDot.className = "w-2 h-2 rounded-full bg-amber-400";
    }
  }
}

function stopPomodoroTimer() {
  if (state.focusTimer.intervalId) {
    clearInterval(state.focusTimer.intervalId);
    state.focusTimer.intervalId = null;
  }
  state.focusTimer.isRunning = false;
  state.focusTimer.remainingSeconds = state.focusTimer.durationMinutes * 60;
  updatePomodoroDisplay();

  const toggleBtn = document.getElementById('btn-pomodoro-toggle');
  const icon = document.getElementById('btn-pomodoro-icon');
  const text = document.getElementById('btn-pomodoro-text');
  const badge = document.getElementById('pomodoro-state-badge');
  if (toggleBtn && icon && text && badge) {
    toggleBtn.className = "au-boton au-boton--primario flex-1";
    icon.innerText = "▶";
    text.innerText = "Iniciar Foco";
    badge.innerText = "Listo";
    badge.className = "au-insignia au-insignia--primario mt-2";
  }
  showToast('Sesión de foco finalizada', 'info');
}

function togglePomodoroTimer() {
  const toggleBtn = document.getElementById('btn-pomodoro-toggle');
  const icon = document.getElementById('btn-pomodoro-icon');
  const text = document.getElementById('btn-pomodoro-text');
  const badge = document.getElementById('pomodoro-state-badge');

  if (state.focusTimer.isRunning) {
    // Pausar
    clearInterval(state.focusTimer.intervalId);
    state.focusTimer.intervalId = null;
    state.focusTimer.isRunning = false;

    if (toggleBtn && icon && text && badge) {
      toggleBtn.className = "au-boton au-boton--primario flex-1";
      icon.innerText = "▶";
      text.innerText = "Reanudar";
      badge.innerText = "Pausado";
      badge.className = "au-insignia au-insignia--alerta mt-2";
    }
  } else {
    // Iniciar
    state.focusTimer.isRunning = true;
    if (toggleBtn && icon && text && badge) {
      toggleBtn.className = "au-boton au-boton--secundario flex-1";
      icon.innerHTML = Au.icono('pausa');
      text.innerText = "Pausar";
      badge.innerText = "Enfocado";
      badge.className = "au-insignia au-insignia--exito mt-2 animate-pulse";
    }

    state.focusTimer.intervalId = setInterval(() => {
      if (state.focusTimer.remainingSeconds > 0) {
        state.focusTimer.remainingSeconds--;
        updatePomodoroDisplay();
      } else {
        // Bloque completado
        clearInterval(state.focusTimer.intervalId);
        state.focusTimer.intervalId = null;
        state.focusTimer.isRunning = false;
        playPomodoroChime();
        finishPomodoroSession(state.focusTimer.durationMinutes);
      }
    }, 1000);
  }
}

function resetPomodoroTimer() {
  setPomodoroMinutes(state.focusTimer.durationMinutes);
}

function playPomodoroChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.3);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 1.2);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 1.2);
  } catch (e) {
    console.warn("AudioContext chime not available:", e);
  }
}

async function finishPomodoroSession(minutesStudied) {
  const blockSelect = document.getElementById('pomodoro-block-select');
  const typeSelect = document.getElementById('pomodoro-type-select');
  const notesInput = document.getElementById('pomodoro-notes-input');

  const bloqueId = blockSelect && blockSelect.value ? parseInt(blockSelect.value) : null;
  const tipo = typeSelect ? typeSelect.value : 'pomodoro';
  const notas = notesInput ? notesInput.value.trim() : '';

  try {
    const res = await fetch('/api/focus/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bloque_id: bloqueId,
        duracion_minutos: minutesStudied,
        tipo: tipo,
        notas: notas || null,
      })
    });

    if (res.ok) {
      alert(`¡Excelente sesión de estudio!\nSe registraron ${minutesStudied} minutos de foco real vinculados a tu agenda y al Weekly Digest de Obsidian.`);
      if (notesInput) notesInput.value = '';
      resetPomodoroTimer();
      await loadFocusStats();
    }
  } catch (err) {
    console.error("Error al registrar sesión de estudio:", err);
  }
}

function completePomodoroSessionEarly() {
  const elapsedSeconds = (state.focusTimer.durationMinutes * 60) - state.focusTimer.remainingSeconds;
  const minutesStudied = Math.max(1, Math.round(elapsedSeconds / 60));
  if (confirm(`¿Deseas dar por terminada la sesión ahora y registrar ${minutesStudied} minutos de estudio enfocado?`)) {
    if (state.focusTimer.intervalId) {
      clearInterval(state.focusTimer.intervalId);
      state.focusTimer.intervalId = null;
      state.focusTimer.isRunning = false;
    }
    finishPomodoroSession(minutesStudied);
  }
}

