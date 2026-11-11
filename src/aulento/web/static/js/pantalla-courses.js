// --- ACCIONES DELEGADAS DE CURSOS (072 T5) ---
[
  ['abrir-webhook-cursos', () => showCourseWebhookModal()],
  ['abrir-nueva-plataforma', () => openAddPlatformModal()],
  ['abrir-agregar-curso', () => openAddCourseModal()],
  ['buscar-cursos', () => filterCoursesGrid()],
  ['filtrar-cursos', (el, datos) => setCourseFilter(datos.valor)],
  ['restablecer-filtros-cursos', () => resetCourseFilters()],
  ['editar-plataforma', (el, datos) => openEditPlatformModal(Number(datos.id))],
  ['eliminar-plataforma', (el, datos) => deletePlatform(Number(datos.id), datos.nombre || '')],
  ['abrir-carpeta-local-curso', (el, datos) => openCourseLocalFolder(Number(datos.courseId), datos.rutaLocal || '')],
  ['indexar-curso', (el, datos) => indexSingleCourse(Number(datos.id), el)],
  ['sincronizar-avance-curso', (el, datos) => syncCourseProgressModal(Number(datos.id))],
  ['apunte-sop-curso', (el, datos) => openCourseNoteModal(Number(datos.id))],
  ['editar-curso', (el, datos) => openEditCourseModal(Number(datos.id))],
  ['eliminar-curso', (el, datos) => deleteCourse(Number(datos.id), datos.nombre || '')],
  ['modal-crear-plataforma', (el, datos, ev) => handleCreatePlatform(ev)],
  ['modal-crear-curso', (el, datos, ev) => handleCreateCourse(ev)],
  ['modal-abrir-alta-plataforma', () => openAddPlatformModal()],
  ['modal-cambiar-plataforma-curso', (el) => handlePlatformSelectChange(el)],
  ['modal-editar-plataforma', (el, datos, ev) => handleEditPlatform(ev)],
  ['modal-eliminar-plataforma', () => deletePlatformFromModal()],
  ['modal-editar-curso', (el, datos, ev) => handleEditCourse(ev)],
  ['modal-eliminar-curso', () => deleteCourseFromModal()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

// --- PLATAFORMAS Y CURSOS ---
async function loadPlatforms() {
  try {
    const res = await fetch('/api/hub/platforms');
    if (res.ok) {
      state.platforms = await res.json();
      renderPlatforms();
      populatePlatformSelect();
    }
  } catch (err) {
    console.error("Error al cargar plataformas:", err);
  }
}

function renderPlatforms() {
  const container = document.getElementById('platforms-grid');
  if (!container) return;

  if (state.platforms.length === 0) {
    container.innerHTML = `
      <div class="col-span-full">${Au.vacio({
        icono: '🏛️',
        titulo: 'Tu Hub Académico está listo',
        texto: 'Centralizá tus cursadas universitarias, plataformas online (Coursera, Digital House, Humai) y certificaciones en un solo panel con acceso directo al aula y tracking de avance.',
        accionHtml: `
          <div class="flex flex-wrap items-center justify-center gap-3 pt-2">
            ${Au.boton({ texto: 'Registrar tu primera plataforma', variante: 'primario', icono: '➕', accion: 'abrir-nueva-plataforma' })}
            ${Au.boton({ texto: 'Conectar Webhook Universal', variante: 'secundario', icono: '📡', accion: 'abrir-webhook-cursos' })}
          </div>
        `,
      })}</div>
    `;
    return;
  }

  const searchQuery = (state.courseSearchQuery || '').toLowerCase().trim();
  const statusFilter = state.courseFilter || 'todos';

  let filteredPlatforms = state.platforms.map(p => {
    let cursos = p.cursos || [];
    if (statusFilter !== 'todos') {
      cursos = cursos.filter(c => c.estado === statusFilter);
    }
    if (searchQuery) {
      cursos = cursos.filter(c => 
        (c.nombre_curso || '').toLowerCase().includes(searchQuery) ||
        (p.nombre || '').toLowerCase().includes(searchQuery)
      );
    }
    return { ...p, cursos };
  });

  if (searchQuery || statusFilter !== 'todos') {
    filteredPlatforms = filteredPlatforms.filter(p => p.cursos.length > 0 || (searchQuery && (p.nombre || '').toLowerCase().includes(searchQuery)));
  }

  if (filteredPlatforms.length === 0 && state.platforms.length > 0) {
    container.innerHTML = `
      <div class="col-span-full">${Au.vacio({
        icono: '🔍',
        titulo: 'No se encontraron cursos con el filtro aplicado.',
        accionHtml: Au.boton({ texto: 'Restablecer filtros', variante: 'fantasma', chico: true, accion: 'restablecer-filtros-cursos' }),
      })}</div>
    `;
    return;
  }

  container.innerHTML = filteredPlatforms.map(p => `
    <section class="au-tarjeta au-tarjeta--interactiva">
      <div class="au-cabecera">
        <div class="au-cabecera__principal">
          <span class="w-3 h-3 rounded-full bg-${Au.escapar(p.icono_color || 'sky')}-400 shrink-0"></span>
          <div class="au-cabecera__textos">
            <h3 class="au-cabecera__titulo"><span>${Au.escapar(p.nombre)}</span></h3>
          </div>
        </div>
        <div class="au-cabecera__acciones">
          ${p.url_acceso ? Au.boton({ texto: 'Entrar ↗', variante: 'secundario', chico: true, href: p.url_acceso, attrs: { target: '_blank', rel: 'noopener noreferrer' } }) : ''}
          ${Au.boton({ icono: '✏️', soloIcono: true, etiqueta: 'Editar plataforma', variante: 'secundario', chico: true, accion: 'editar-plataforma', datos: { id: p.id } })}
          ${Au.boton({ icono: '🗑️', soloIcono: true, etiqueta: 'Eliminar plataforma', variante: 'peligro', chico: true, accion: 'eliminar-plataforma', datos: { id: p.id, nombre: p.nombre } })}
        </div>
      </div>

      <!-- Cursos en la plataforma -->
      <div class="space-y-3">
        ${p.cursos.length === 0 ? '<p class="text-xs text-slate-500 italic">No hay cursos registrados en esta plataforma.</p>' : ''}
        ${p.cursos.map(c => `
          <div class="au-tarjeta au-tarjeta--hundida">
            <div class="flex items-center justify-between text-xs">
              <span class="font-semibold text-slate-200">${Au.escapar(c.nombre_curso)}</span>
              <div class="flex items-center gap-1.5">
                ${c.fuente_sincronizacion && c.fuente_sincronizacion !== 'manual' ? Au.insignia({ texto: `🔄 ${c.fuente_sincronizacion}`, mono: true, attrs: { title: `Última sincronización: ${c.ultima_sincronizacion || ''}` } }) : ''}
                ${Au.insignia({ texto: c.estado, tono: c.estado === 'completado' ? 'exito' : 'primario' })}
              </div>
            </div>

            <!-- Barra de Progreso -->
            <div class="space-y-1">
              <div class="flex justify-between text-xs text-slate-400">
                <span>Progreso</span>
                <span class="font-bold text-slate-200">${c.progreso_pct.toFixed(0)}%</span>
              </div>
              ${Au.progreso({ valor: c.progreso_pct, maximo: 100, tono: c.estado === 'completado' ? 'exito' : undefined, etiqueta: 'Progreso del curso' })}
            </div>

            <!-- Botones de Acción y Recursos 360° -->
            <div class="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-800/80">
              <div class="flex flex-wrap items-center gap-1.5">
                ${c.url_aula ? Au.boton({ texto: 'Aula', icono: '🚀', chico: true, href: c.url_aula, attrs: { target: '_blank', rel: 'noopener noreferrer', title: 'Abrir Aula Virtual del curso' } }) : ''}
                ${c.url_drive ? Au.boton({ texto: 'Drive', icono: '📁', chico: true, href: c.url_drive, attrs: { target: '_blank', rel: 'noopener noreferrer', title: 'Abrir carpeta en Google Drive / Nube' } }) : ''}
                ${c.ruta_local ? Au.boton({ texto: 'Local', icono: '💻', chico: true, accion: 'abrir-carpeta-local-curso', datos: { courseId: c.id, rutaLocal: c.ruta_local }, attrs: { title: 'Abrir carpeta local / Copiar ruta en PC' } }) : ''}
                ${c.url_notion ? Au.boton({ texto: 'Notion', icono: '📓', chico: true, href: c.url_notion, attrs: { target: '_blank', rel: 'noopener noreferrer', title: 'Abrir notas en Notion' } }) : ''}
                ${c.ruta_obsidian ? `<a href="${formatObsidianUri(c.ruta_obsidian)}" class="au-boton au-boton--secundario au-boton--chico" title="Abrir apunte en Obsidian"><span aria-hidden="true">💎</span><span>Obsidian</span></a>` : ''}
              </div>
              <div class="flex flex-wrap items-center gap-1">
                ${Au.boton({ texto: 'Indexar', icono: '⚡', chico: true, accion: 'indexar-curso', datos: { id: c.id }, attrs: { title: 'Indexar este curso en el índice de búsqueda' } })}
                ${Au.boton({ texto: 'Sync', icono: '🔄', chico: true, accion: 'sincronizar-avance-curso', datos: { id: c.id }, attrs: { title: 'Sincronizar avance del curso' } })}
                ${Au.boton({ texto: 'SOP', icono: '📝', chico: true, accion: 'apunte-sop-curso', datos: { id: c.id }, attrs: { title: 'Crear apunte estructurado SOP en Obsidian' } })}
                ${Au.boton({ icono: '✏️', soloIcono: true, etiqueta: 'Editar curso', variante: 'secundario', chico: true, accion: 'editar-curso', datos: { id: c.id } })}
                ${Au.boton({ icono: '🗑️', soloIcono: true, etiqueta: 'Eliminar curso', variante: 'peligro', chico: true, accion: 'eliminar-curso', datos: { id: c.id, nombre: c.nombre_curso } })}
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    </section>
  `).join('');
}

function formatObsidianUri(path) {
  if (!path) return '#';
  const trimmed = path.trim();
  // Devuelve el valor listo para un atributo (escapado): quien lo usa no lo vuelve a escapar
  if (trimmed.startsWith('obsidian://')) return escapeHtml(trimmed);
  const cleanPath = trimmed.replace(/\.md$/, '');
  return `obsidian://open?file=${encodeURIComponent(cleanPath)}`;
}

async function openCourseLocalFolder(courseId, localPath) {
  try {
    const res = await fetch(`/api/hub/courses/${courseId}/open-local`, { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(data.message || 'Carpeta abierta en el explorador local.', 'success');
      return;
    }
  } catch (err) {
    console.warn("No se pudo invocar apertura directa, usando portapapeles:", err);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(localPath);
    showToast(`📋 Ruta copiada al portapapeles: ${localPath}`, 'success');
  } else {
    await showPromptDialog({
      title: 'Ruta local del curso',
      message: 'Copiá la ruta a continuación:',
      defaultValue: localPath,
      confirmText: 'Cerrar',
      icon: '📁'
    });
  }
}

async function updateCourseProgressPrompt(courseId, currentPct) {
  const newPct = await showPromptDialog({
    title: 'Actualizar Avance del Curso',
    message: 'Ingresá el nuevo porcentaje completado (0 a 100%):',
    defaultValue: String(currentPct != null ? currentPct : 0),
    placeholder: 'Ej. 45',
    confirmText: 'Guardar Avance',
    icon: '📊'
  });
  if (newPct === null || newPct.trim() === '') return;
  const num = parseFloat(newPct.trim());
  if (isNaN(num) || num < 0 || num > 100) {
    showToast('Por favor ingresá un número válido entre 0 y 100.', 'error');
    return;
  }

  try {
    const res = await fetch(`/api/hub/courses/${courseId}/progress`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ progreso_pct: num }),
    });

    if (res.ok) {
      showToast(`Avance actualizado al ${num}%`, 'success');
      await loadPlatforms();
      renderDashboard();
    } else {
      showToast('Error al actualizar avance del curso.', 'error');
    }
  } catch (err) {
    console.error("Error al actualizar progreso:", err);
    showToast('Error de conexión al actualizar avance.', 'error');
  }
}

function populatePlatformSelect(selectedId = null) {
  const select = document.getElementById('new-course-platform');
  if (!select) return;

  if (state.platforms.length === 0) {
    select.innerHTML = `
      <option value="" disabled selected class="bg-slate-900 text-slate-400">-- No hay plataformas aún --</option>
      <option value="__new__" class="bg-slate-900 text-sky-400 font-bold">➕ Registrar nueva plataforma...</option>
    `;
    return;
  }

  const options = state.platforms.map(p => `
    <option value="${Number(p.id)}" class="bg-slate-900 text-white" ${selectedId && p.id === selectedId ? 'selected' : ''}>${escapeHtml(p.nombre)}</option>
  `).join('');

  select.innerHTML = `
    <option value="" disabled ${!selectedId ? 'selected' : ''} class="bg-slate-900 text-slate-400">-- Seleccioná una plataforma --</option>
    ${options}
    <option value="__new__" class="bg-slate-900 text-sky-400 font-bold">➕ Registrar otra plataforma...</option>
  `;
}

function handlePlatformSelectChange(selectElem) {
  if (selectElem.value === '__new__') {
    selectElem.value = "";
    openAddPlatformModal();
  }
}

function openAddPlatformModal() {
  Au.modal.abrir('add-platform-modal');
}

function closeAddPlatformModal() {
  Au.modal.cerrar('add-platform-modal');
}

async function handleCreatePlatform(e) {
  e.preventDefault();
  const name = document.getElementById('new-platform-name').value.trim();
  const url = document.getElementById('new-platform-url').value.trim();
  const color = document.getElementById('new-platform-color').value;

  try {
    const res = await fetch('/api/hub/platforms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre: name,
        url_acceso: url,
        icono_color: color,
      }),
    });
    if (res.ok) {
      const created = await res.json();
      closeAddPlatformModal();
      document.getElementById('new-platform-name').value = '';
      document.getElementById('new-platform-url').value = '';

      await loadPlatforms();
      populatePlatformSelect(created.id);
      renderDashboard();
    } else {
      const err = await res.json();
      alert("Error al guardar plataforma: " + (err.detail || "Verificá los datos ingresados"));
    }
  } catch (err) {
    console.error("Error al registrar plataforma:", err);
    alert("Error de conexión al guardar la plataforma.");
  }
}

async function handleCreateCourse(e) {
  e.preventDefault();
  const platformId = parseInt(document.getElementById('new-course-platform').value);
  const name = document.getElementById('new-course-name').value.trim();
  const url = document.getElementById('new-course-url').value.trim();
  const priority = document.getElementById('new-course-priority').value;

  const drive = document.getElementById('new-course-drive')?.value.trim() || null;
  const local = document.getElementById('new-course-local')?.value.trim() || null;
  const notion = document.getElementById('new-course-notion')?.value.trim() || null;
  const obsidian = document.getElementById('new-course-obsidian')?.value.trim() || null;

  try {
    const res = await fetch('/api/hub/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plataforma_id: platformId,
        nombre_curso: name,
        url_aula: url,
        prioridad: priority,
        progreso_pct: 0.0,
        url_drive: drive,
        ruta_local: local,
        url_notion: notion,
        ruta_obsidian: obsidian,
      }),
    });
    if (res.ok) {
      closeAddCourseModal();
      document.getElementById('new-course-name').value = '';
      document.getElementById('new-course-url').value = '';
      if (document.getElementById('new-course-drive')) document.getElementById('new-course-drive').value = '';
      if (document.getElementById('new-course-local')) document.getElementById('new-course-local').value = '';
      if (document.getElementById('new-course-notion')) document.getElementById('new-course-notion').value = '';
      if (document.getElementById('new-course-obsidian')) document.getElementById('new-course-obsidian').value = '';

      await loadPlatforms();
      renderDashboard();
    } else {
      const err = await res.json();
      alert("Error al registrar curso: " + (err.detail || "Verificá los datos ingresados"));
    }
  } catch (err) {
    console.error("Error al crear curso:", err);
  }
}

// --- MODAL EDITAR PLATAFORMA ---
function openEditPlatformModal(platformId) {
  const p = state.platforms.find(x => x.id === platformId);
  if (!p) return;
  document.getElementById('edit-platform-id').value = p.id;
  document.getElementById('edit-platform-name').value = p.nombre;
  document.getElementById('edit-platform-url').value = p.url_acceso;
  document.getElementById('edit-platform-color').value = p.icono_color || 'sky';
  Au.modal.abrir('edit-platform-modal');
}

function closeEditPlatformModal() {
  Au.modal.cerrar('edit-platform-modal');
}

async function handleEditPlatform(e) {
  e.preventDefault();
  const id = document.getElementById('edit-platform-id').value;
  const name = document.getElementById('edit-platform-name').value.trim();
  const url = document.getElementById('edit-platform-url').value.trim();
  const color = document.getElementById('edit-platform-color').value;

  try {
    const res = await fetch(`/api/hub/platforms/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre: name, url_acceso: url, icono_color: color }),
    });
    if (res.ok) {
      closeEditPlatformModal();
      await loadPlatforms();
      renderDashboard();
    } else {
      const err = await res.json();
      alert("Error al actualizar plataforma: " + (err.detail || "Verificá los datos ingresados"));
    }
  } catch (err) {
    console.error("Error al actualizar plataforma:", err);
    alert("Error de conexión al actualizar.");
  }
}

async function deletePlatform(id, name) {
  const confirmed = await showConfirmDialog({
    title: '¿Eliminar plataforma académica?',
    message: `¿Estás seguro de eliminar la plataforma "${name}"?\nSe eliminarán también todos los cursos asociados a ella de forma permanente.`,
    confirmText: 'Eliminar Plataforma',
    cancelText: 'Cancelar',
    icon: '🗑️',
    danger: true
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/hub/platforms/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast(`Plataforma "${name}" eliminada`, 'success');
      await loadPlatforms();
      renderDashboard();
    } else {
      showToast('Error al eliminar la plataforma.', 'error');
    }
  } catch (err) {
    console.error("Error al eliminar plataforma:", err);
    showToast('Error de conexión al eliminar plataforma.', 'error');
  }
}

function deletePlatformFromModal() {
  const id = document.getElementById('edit-platform-id').value;
  const name = document.getElementById('edit-platform-name').value;
  closeEditPlatformModal();
  deletePlatform(id, name);
}

// --- MODAL EDITAR CURSO ---
function openEditCourseModal(courseId) {
  let found = null;
  for (const p of state.platforms) {
    const c = p.cursos.find(x => x.id === courseId);
    if (c) { found = c; break; }
  }
  if (!found) return;

  document.getElementById('edit-course-id').value = found.id;
  document.getElementById('edit-course-name').value = found.nombre_curso;
  document.getElementById('edit-course-url').value = found.url_aula;
  document.getElementById('edit-course-progress').value = Math.round(found.progreso_pct);
  document.getElementById('edit-course-priority').value = found.prioridad || 'alta';
  document.getElementById('edit-course-status').value = found.estado || 'en_curso';

  document.getElementById('edit-course-drive').value = found.url_drive || '';
  document.getElementById('edit-course-local').value = found.ruta_local || '';
  document.getElementById('edit-course-notion').value = found.url_notion || '';
  document.getElementById('edit-course-obsidian').value = found.ruta_obsidian || '';

  Au.modal.abrir('edit-course-modal');
}

function closeEditCourseModal() {
  Au.modal.cerrar('edit-course-modal');
}

async function handleEditCourse(e) {
  e.preventDefault();
  const id = document.getElementById('edit-course-id').value;
  const name = document.getElementById('edit-course-name').value.trim();
  const url = document.getElementById('edit-course-url').value.trim();
  const prog = parseFloat(document.getElementById('edit-course-progress').value);
  const prio = document.getElementById('edit-course-priority').value;
  const st = document.getElementById('edit-course-status').value;

  const drive = document.getElementById('edit-course-drive')?.value.trim() || null;
  const local = document.getElementById('edit-course-local')?.value.trim() || null;
  const notion = document.getElementById('edit-course-notion')?.value.trim() || null;
  const obsidian = document.getElementById('edit-course-obsidian')?.value.trim() || null;

  try {
    const res = await fetch(`/api/hub/courses/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre_curso: name,
        url_aula: url,
        progreso_pct: isNaN(prog) ? 0.0 : prog,
        prioridad: prio,
        estado: st,
        url_drive: drive,
        ruta_local: local,
        url_notion: notion,
        ruta_obsidian: obsidian,
      }),
    });
    if (res.ok) {
      closeEditCourseModal();
      await loadPlatforms();
      renderDashboard();
    } else {
      const err = await res.json();
      alert("Error al actualizar curso: " + (err.detail || "Verificá los datos ingresados"));
    }
  } catch (err) {
    console.error("Error al actualizar curso:", err);
  }
}

async function deleteCourse(id, name) {
  const confirmed = await showConfirmDialog({
    title: '¿Eliminar curso?',
    message: `¿Estás seguro de eliminar el curso "${name}"?`,
    confirmText: 'Eliminar Curso',
    cancelText: 'Cancelar',
    icon: '🗑️',
    danger: true
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/hub/courses/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast(`Curso "${name}" eliminado`, 'success');
      await loadPlatforms();
      renderDashboard();
    } else {
      showToast('Error al eliminar el curso.', 'error');
    }
  } catch (err) {
    console.error("Error al eliminar curso:", err);
    showToast('Error de conexión al eliminar curso.', 'error');
  }
}

function deleteCourseFromModal() {
  const id = document.getElementById('edit-course-id').value;
  const name = document.getElementById('edit-course-name').value;
  closeEditCourseModal();
  deleteCourse(id, name);
}

// Filtros en tiempo real para Hub de Cursos
function filterCoursesGrid() {
  const input = document.getElementById('course-search-input');
  state.courseSearchQuery = input ? input.value : '';
  renderPlatforms();
}

function setCourseFilter(filter) {
  state.courseFilter = filter;
  ['todos', 'progreso', 'completado'].forEach(f => {
    const btn = document.getElementById(`btn-course-filter-${f}`);
    if (btn) {
      const active = (f === 'progreso' && filter === 'en_progreso') || (f === filter);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    }
  });
  renderPlatforms();
}

function resetCourseFilters() {
  state.courseSearchQuery = '';
  state.courseFilter = 'todos';
  const input = document.getElementById('course-search-input');
  if (input) input.value = '';
  setCourseFilter('todos');
}

