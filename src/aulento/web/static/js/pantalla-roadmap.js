// ========================================================
// 🗺️ RUTAS DE APRENDIZAJE, GAP ANALYSIS & LESSON STUDIO
// ========================================================

// --- ACCIONES DELEGADAS DE RUTAS (072 T4) ---
[
  ['ruta-cambiar-seleccion', (el) => handleRoadmapSelectionChange(el.value)],
  ['ruta-abrir-catalogo', () => openRoadmapCatalogModal()],
  ['ruta-eliminar-activa', () => deleteActiveRoadmap()],
  ['ruta-abrir-nueva', () => openNewRoadmapModal()],
  ['ruta-sugerir-evolucion', () => suggestNextRoadmapTopics()],
  ['ruta-abrir-pdf-gap', () => openPdfGapModal()],
  ['ruta-abrir-perfil', () => openPedagogicalProfileModal()],
  ['ruta-cambiar-modo-vista', (el, datos) => switchRoadmapViewMode(datos.modo)],
  ['ruta-alternar-todos-modulos', () => toggleAllRoadmapModules()],
  ['ruta-abrir-agregar-requisito', () => openAddPrerequisiteModal()],
  ['ruta-copiar-mermaid', () => copyRoadmapMermaid()],
  ['ruta-recargar-grafo', () => loadRoadmapGraph()],
  ['ruta-alternar-secuencia-implicita', (el) => toggleDagImplicitSequence(el.checked)],
  ['ruta-sugerir-requisitos', () => requestPrerequisiteSuggestions()],
  ['ruta-alternar-pantalla-completa', () => toggleDagFullscreen()],
  ['ruta-fijar-modo-dag', (el, datos) => setDagViewMode(datos.modo)],
  ['ruta-sincronizar-plantillas', () => reSeedTemplates()],
  ['ruta-guardar-requisito', () => submitCreatePrerequisite()],
  ['ruta-aceptar-sugerencias-requisitos', () => acceptPrerequisiteSuggestions()],
  ['ruta-cambiar-pestana-nueva-ruta', (el, datos) => switchNewRoadmapTab(datos.pestana)],
  ['ruta-cambiar-plantilla', (el) => handleTemplateSelectChange(el)],
  ['ruta-cambiar-categoria', (el) => handleCategorySelectChange(el.value)],
  ['ruta-previsualizar-temario', () => previewSyllabus()],
  ['ruta-crear-nueva-ruta', () => submitNewRoadmapForm()],
  ['ruta-agregar-seccion-perfil', () => addPedagogicalProfileSection()],
  ['ruta-guardar-perfil', () => savePedagogicalProfile()],
  ['ruta-refrescar-prompt-tema', () => refreshTopicPrompt()],
  ['ruta-copiar-prompt-maestro', () => copyMasterPrompt()],
  ['ruta-pegar-en-importador', () => switchToImportFromPrompt()],
  ['ruta-importar-clase', () => submitImportLesson()],
  ['ruta-cambiar-vista-clase', (el, datos) => switchLessonView(datos.vista)],
  ['ruta-copiar-markdown-clase', () => copyLessonMarkdown()],
  ['ruta-anterior-slide-clase', () => prevLessonSlide()],
  ['ruta-siguiente-slide-clase', () => nextLessonSlide()],
  ['ruta-exportar-clase-fsrs', () => exportCurrentLessonToFsrs()],
  ['ruta-restaurar-version-clase', () => restorePreviousLessonVersion()],
  ['ruta-exportar-clase-vault', () => exportCurrentLessonToVault()],
  ['ruta-abrir-selector-pdf-gap', () => document.getElementById('pdf-gap-file-input').click()],
  ['ruta-limpiar-pdf-gap', () => clearSelectedGapPdf()],
  ['ruta-seleccionar-pdf-gap', (el) => handleGapPdfSelected(el)],
  ['ruta-analizar-brechas-pdf', () => submitPdfGapAnalysis()],
  ['ruta-incorporar-temas-brecha', () => mergeGapTopicsToActiveRoadmap()],
  ['ruta-ver-clase', (el, datos) => viewLessonModal(Number(datos.temaId))],
  ['ruta-abrir-prompt-tema', (el, datos) => openTopicPromptModal(Number(datos.temaId))],
  ['ruta-abrir-importar-clase', (el, datos) => openImportLessonModal(Number(datos.temaId))],
  ['ruta-generar-clase', (el, datos) => generateLessonInApp(Number(datos.temaId))],
  ['ruta-alternar-modulo', (el) => toggleSingleModule(el)],
  ['ruta-expandir-modulo', (el, datos) => expandRoadmapModule(Number(datos.id), el)],
  ['ruta-destacar-nodo-grafo', (el, datos) => highlightGraphNode(Number(datos.id))],
  ['ruta-agregar-requisito-con-defaults', (el, datos) => openAddPrerequisiteWithDefaults(Number(datos.id))],
  ['ruta-seleccionar-de-catalogo', (el, datos) => selectRoadmapFromCatalog(Number(datos.id))],
  ['borrar-ruta', (el, datos) => deleteRoadmap(Number(datos.roadmapId), datos.roadmapTitulo || '')],
  ['cambiar-estado-tema', (el, datos) => toggleTopicStatus(Number(datos.topicId), datos.estado || 'pendiente')],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

async function loadRoadmaps() {
  const selector = document.getElementById('roadmap-selector');
  if (!selector) return;

  try {
    let res = await fetch('/api/roadmap');
    if (!res.ok) throw new Error("Error cargando rutas");
    let roadmaps = await res.json();

    // Sin rutas, precargar las 4 canónicas, solo la primera vez: si la persona las borra, no vuelven solas
    if (roadmaps.length === 0) {
      const seedRes = await fetch('/api/roadmap/templates/seed?solo_la_primera_vez=true', { method: 'POST' });
      if (seedRes.ok) {
        res = await fetch('/api/roadmap');
        if (res.ok) roadmaps = await res.json();
      }
    }

    state.roadmaps = roadmaps;

    selector.innerHTML = '';
    if (roadmaps.length === 0) {
      selector.innerHTML = '<option value="">-- Sin rutas activas --</option>';
      renderEmptyRoadmapState();
      return;
    }

    const getCatIcon = (cat) => {
      switch (cat) {
        case 'data_engineering': return '🛠️';
        case 'artificial_intelligence': return '🤖';
        case 'data_science': return '🔬';
        case 'cloud_devops': return '☁️';
        case 'business_intelligence': return '📊';
        case 'software_eng': return '💻';
        case 'frontend_web': return '🌐';
        case 'mobile_dev': return '📱';
        case 'cybersecurity': return '🛡️';
        case 'english_communication': return '🇬🇧';
        case 'product_management': return '🚀';
        default: return '🏷️';
      }
    };

    roadmaps.forEach(r => {
      const opt = document.createElement('option');
      opt.value = String(r.id);
      opt.textContent = `${getCatIcon(r.categoria)} ${r.titulo} (${r.progreso_pct}%)`;
      if (state.activeRoadmapId === r.id) opt.selected = true;
      selector.appendChild(opt);
    });

    if (!state.activeRoadmapId || !roadmaps.some(r => r.id === state.activeRoadmapId)) {
      state.activeRoadmapId = roadmaps[0].id;
    }
    selector.value = String(state.activeRoadmapId);

    await loadRoadmapDetails(state.activeRoadmapId);
  } catch (err) {
    console.error("Error en loadRoadmaps:", err);
  }
}

function handleRoadmapSelectionChange(roadmapId) {
  if (!roadmapId) return;
  state.activeRoadmapId = parseInt(roadmapId, 10);
  const selector = document.getElementById('roadmap-selector');
  if (selector) selector.value = String(state.activeRoadmapId);
  loadRoadmapDetails(state.activeRoadmapId);
}

// --- MODAL CATÁLOGO DE RUTAS ---
function openRoadmapCatalogModal() {
  const modal = document.getElementById('modal-roadmap-catalog');
  if (!modal) return;
  Au.modal.abrir('modal-roadmap-catalog');
  renderRoadmapCatalog();
}

function closeRoadmapCatalogModal() {
  Au.modal.cerrar('modal-roadmap-catalog');
}

function renderRoadmapCatalog() {
  const container = document.getElementById('roadmap-catalog-grid');
  if (!container) return;

  const roadmaps = state.roadmaps || [];
  if (roadmaps.length === 0) {
    container.innerHTML = '<div class="p-6 text-center text-slate-400 text-xs">No hay rutas cargadas.</div>';
    return;
  }

  const getCatBadge = (cat) => {
    switch (cat) {
      case 'data_engineering': return Au.insignia({ texto: '🛠️ Data Engineering', tono: 'alerta' });
      case 'artificial_intelligence': return Au.insignia({ texto: '🤖 Inteligencia Artificial', tono: 'primario' });
      case 'data_science': return Au.insignia({ texto: '🔬 Data Science & ML', tono: 'exito' });
      case 'cloud_devops': return Au.insignia({ texto: '☁️ Cloud, DevOps & SRE', tono: 'primario' });
      case 'business_intelligence': return Au.insignia({ texto: '📊 Business Intelligence', tono: 'exito' });
      case 'software_eng': return Au.insignia({ texto: '💻 Software Engineering', tono: 'primario' });
      case 'frontend_web': return Au.insignia({ texto: '🌐 Frontend & Web', tono: 'primario' });
      case 'mobile_dev': return Au.insignia({ texto: '📱 Mobile', tono: 'primario' });
      case 'cybersecurity': return Au.insignia({ texto: '🛡️ Ciberseguridad', tono: 'peligro' });
      case 'english_communication': return Au.insignia({ texto: '🇬🇧 Inglés Profesional', tono: 'alerta' });
      case 'product_management': return Au.insignia({ texto: '🚀 Product Management', tono: 'primario' });
      default: return Au.insignia({ texto: `🏷️ ${cat || 'General'}` });
    }
  };

  container.innerHTML = roadmaps.map(r => {
    const isActive = state.activeRoadmapId === r.id;
    const meta = r.metadata_json || {};
    const tags = Array.isArray(meta.tags) ? meta.tags : [];
    const tagsHtml = tags.map(t => `<span class="px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded text-xs font-mono">${escapeHtml(t)}</span>`).join(' ');

    return `
      <div class="p-5 rounded-2xl border ${isActive ? 'bg-slate-900/90 border-sky-500 shadow-lg shadow-sky-500/10' : 'bg-slate-950 border-slate-800 hover:border-slate-700'} flex flex-col justify-between gap-4 transition">
        <div class="space-y-2.5">
          <div class="flex items-center justify-between gap-2">
            ${getCatBadge(r.categoria)}
            <div class="flex items-center gap-1.5">
              <span class="text-xs font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                ${escapeHtml(r.nivel_objetivo || 'Senior')}
              </span>
              <button type="button" data-accion="borrar-ruta" data-roadmap-id="${Number(r.id)}" data-roadmap-titulo="${escapeHtml(r.titulo)}" class="au-boton au-boton--fantasma au-boton--icono au-boton--chico" title="Eliminar ruta">
                🗑️
              </button>
            </div>
          </div>
          <div>
            <h4 class="font-bold text-white text-sm flex items-center gap-1.5">
              ${escapeHtml(r.titulo)}
              ${isActive ? '<span class="text-xs px-1.5 py-0.2 rounded bg-sky-950 text-sky-400 border border-sky-800 font-semibold">Activa</span>' : ''}
            </h4>
            <p class="text-xs text-slate-400 mt-1 line-clamp-2">${escapeHtml(r.descripcion || '')}</p>
          </div>
          ${tagsHtml ? `<div class="flex flex-wrap gap-1 pt-1">${tagsHtml}</div>` : ''}
        </div>

        <div class="pt-3 border-t border-slate-800/80 space-y-3">
          <div class="flex items-center justify-between text-xs text-slate-400">
            <span>Progreso: <b class="text-white">${r.temas_completados} / ${r.total_temas} temas</b></span>
            <span class="font-bold ${r.progreso_pct > 0 ? 'text-emerald-400' : 'text-slate-400'}">${r.progreso_pct}%</span>
          </div>
          <div class="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div class="bg-gradient-to-r from-sky-500 to-emerald-500 h-full" style="width: ${r.progreso_pct}%;"></div>
          </div>
          <button 
            type="button" 
            data-accion="ruta-seleccionar-de-catalogo" 
            data-id="${r.id}" 
            class="w-full ${isActive ? 'au-boton au-boton--secundario' : 'au-boton au-boton--primario'}"
          >
            <span>${isActive ? '✔ Estudiando Actualmente' : '🚀 Seleccionar Ruta'}</span>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function selectRoadmapFromCatalog(roadmapId) {
  state.activeRoadmapId = parseInt(roadmapId, 10);
  const selector = document.getElementById('roadmap-selector');
  if (selector) selector.value = String(state.activeRoadmapId);
  closeRoadmapCatalogModal();
  loadRoadmapDetails(state.activeRoadmapId);
}

async function deleteRoadmap(roadmapId, title) {
  const confirmed = await showConfirmDialog({
    title: '¿Eliminar ruta de aprendizaje?',
    message: `¿Estás seguro de que deseas eliminar la ruta "${title}"?\nSe borrarán sus módulos y temas asociados de forma permanente.`,
    confirmText: 'Eliminar ruta',
    cancelText: 'Cancelar',
    icon: '🗑️',
    danger: true
  });
  if (!confirmed) {
    return;
  }
  try {
    const res = await fetch(`/api/roadmap/${roadmapId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error("No se pudo eliminar la ruta del servidor");
    if (state.activeRoadmapId === roadmapId) {
      state.activeRoadmapId = null;
    }
    await loadRoadmaps();
    renderRoadmapCatalog();
  } catch (err) {
    alert("Error al eliminar la ruta: " + err.message);
  }
}

async function deleteActiveRoadmap() {
  if (!state.activeRoadmapId) return;
  const current = (state.roadmaps || []).find(r => r.id === state.activeRoadmapId);
  const title = current ? current.titulo : `Ruta ID ${state.activeRoadmapId}`;
  await deleteRoadmap(state.activeRoadmapId, title);
}

async function reSeedTemplates() {
  try {
    const res = await fetch('/api/roadmap/templates/seed', { method: 'POST' });
    if (res.ok) {
      await loadRoadmaps();
      renderRoadmapCatalog();
      alert("✔ Todas las rutas canónicas están actualizadas.");
    }
  } catch (err) {
    alert("Error al sincronizar plantillas: " + err.message);
  }
}

async function loadRoadmapDetails(roadmapId) {
  const container = document.getElementById('roadmap-tree-container');
  if (!container) return;

  container.innerHTML = '<div class="p-8 text-center text-slate-400"><div class="inline-block animate-spin text-2xl mb-2">⚡</div><p class="text-xs">Cargando árbol curricular...</p></div>';

  try {
    const res = await fetch(`/api/roadmap/${roadmapId}`);
    if (!res.ok) throw new Error("Error cargando detalle de ruta");
    const detail = await res.json();
    state.activeRoadmap = detail;
    renderRoadmap(detail);
    if (state.roadmapViewMode === 'dag') {
      loadRoadmapGraph();
    }
  } catch (err) {
    container.innerHTML = `<div class="p-4 bg-red-950/40 border border-red-800 rounded-2xl text-red-300 text-xs">Error: ${escapeHtml(err && err.message ? err.message : 'Error inesperado')}</div>`;
  }
}

function renderRoadmapFallbackAviso(detail) {
  const banner = document.getElementById('roadmap-fallback-aviso');
  const text = document.getElementById('roadmap-fallback-aviso-text');
  if (!banner || !text) return;

  const aviso = detail && detail.metadata_json ? detail.metadata_json.aviso : null;
  text.textContent = aviso || '';
  banner.classList.toggle('hidden', !aviso);
}

function renderEmptyRoadmapState() {
  const container = document.getElementById('roadmap-tree-container');
  if (!container) return;

  renderRoadmapFallbackAviso(null);

  document.getElementById('roadmap-kpi-level').textContent = "-";
  document.getElementById('roadmap-kpi-topics').textContent = "0 / 0";
  document.getElementById('roadmap-kpi-pct').textContent = "0%";
  document.getElementById('roadmap-kpi-bar-text').textContent = "0%";
  document.getElementById('roadmap-progress-bar').value = 0;

  container.innerHTML = `
    <div class="au-tarjeta text-center">
      <div class="text-4xl">🗺️</div>
      <h3 class="text-lg font-bold text-white">Comienza tu Ruta de Aprendizaje Personalizada</h3>
      <p class="text-xs text-slate-400 max-w-md mx-auto">
        Diseña una ruta técnica con Gemini 1.5 Flash o elige una de las plantillas curadas (Data Engineer, AI Architect, Cloud & FinOps, BI Storytelling).
      </p>
      <div class="flex justify-center gap-3 pt-2">
        <button type="button" data-accion="ruta-abrir-nueva" class="au-boton au-boton--primario">
          <span>✨</span> Crear Nueva Ruta con IA
        </button>
      </div>
    </div>
  `;
}

function renderRoadmap(detail) {
  const container = document.getElementById('roadmap-tree-container');
  if (!container) return;

  renderRoadmapFallbackAviso(detail);

  // Actualizar KPIs
  document.getElementById('roadmap-kpi-level').textContent = detail.nivel_objetivo || "Senior";
  document.getElementById('roadmap-kpi-topics').textContent = `${detail.temas_completados} / ${detail.total_temas}`;
  document.getElementById('roadmap-kpi-pct').textContent = `${detail.progreso_pct}%`;
  document.getElementById('roadmap-kpi-bar-text').textContent = `${detail.progreso_pct}%`;
  document.getElementById('roadmap-progress-bar').value = Math.max(0, Math.min(100, Number(detail.progreso_pct) || 0));

  if (!detail.modulos || detail.modulos.length === 0) {
    container.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs">Esta ruta no contiene módulos configurados.</div>';
    return;
  }

  container.innerHTML = '';

  detail.modulos.forEach((mod, modIdx) => {
    const modDiv = document.createElement('div');
    modDiv.className = "roadmap-module-card au-tarjeta overflow-hidden shadow-lg transition p-0";

    const completedInMod = mod.temas.filter(t => t.estado === 'completado').length;
    const modPct = mod.temas.length > 0 ? Math.round((completedInMod / mod.temas.length) * 100) : 0;

    let topicsHtml = '';
    mod.temas.forEach(topic => {
      const isCompleted = topic.estado === 'completado';
      const isInProgress = topic.estado === 'en_progreso';
      // Títulos y descripciones pueden venir de la IA: se escapan; el estado va dentro de un onclick, solo valores conocidos
      const topicId = Number(topic.id);
      const estado = isCompleted ? 'completado' : (isInProgress ? 'en_progreso' : 'pendiente');

      let statusBadge = '';
      if (isCompleted) {
        statusBadge = Au.insignia({ texto: '✔ Dominado', tono: 'exito' });
      } else if (isInProgress) {
        statusBadge = Au.insignia({ texto: '🚀 En Curso', tono: 'primario' });
      } else {
        statusBadge = Au.insignia({ texto: '⏳ Pendiente' });
      }

      const hasClassBadge = topic.clase 
        ? Au.insignia({ texto: '📖 Clase Lista', tono: 'primario' }) 
        : '';

      const isGapBadge = topic.fuente === 'pdf_gap'
        ? Au.insignia({ texto: 'PDF Gap', tono: 'alerta' }) 
        : '';

      topicsHtml += `
        <div class="p-3.5 bg-slate-950/70 border border-slate-800/80 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-slate-700 transition">
          <div class="flex items-start gap-3">
            <button type="button" data-accion="cambiar-estado-tema" data-topic-id="${Number(topicId)}" data-estado="${escapeHtml(estado)}" class="au-boton au-boton--fantasma au-boton--icono au-boton--chico" title="Cambiar estado: Pendiente -> En curso -> Dominado">
              ${isCompleted ? '✅' : (isInProgress ? '🔄' : '⚪')}
            </button>
            <div>
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-sm ${isCompleted ? 'text-emerald-300 line-through' : 'text-slate-100'}">${escapeHtml(topic.titulo)}</span>
                ${statusBadge}
                ${hasClassBadge}
                ${isGapBadge}
              </div>
              ${topic.descripcion ? `<p class="text-xs text-slate-400 mt-0.5">${escapeHtml(topic.descripcion)}</p>` : ''}
            </div>
          </div>

          <div class="flex items-center gap-1.5 flex-wrap self-end md:self-center">
            ${topic.clase ? `
              <button type="button" data-accion="ruta-ver-clase" data-tema-id="${topicId}" class="au-boton au-boton--secundario au-boton--chico">
                <span>👁️</span> Ver Clase
              </button>
            ` : ''}
            <button type="button" data-accion="ruta-abrir-prompt-tema" data-tema-id="${topicId}" class="au-boton au-boton--secundario au-boton--chico" title="Generar Prompt Maestro para NotebookLM o Claude">
              <span>📋</span> Prompt Maestro
            </button>
            <button type="button" data-accion="ruta-generar-clase" data-tema-id="${topicId}" class="au-boton au-boton--primario au-boton--chico" title="Generar la clase con la IA que tengas configurada (o el motor local, si no hay clave)">
              <span>⚡</span> Generar clase
            </button>
            <button type="button" data-accion="ruta-abrir-importar-clase" data-tema-id="${topicId}" class="au-boton au-boton--secundario au-boton--chico" title="Importar clase copiada desde NotebookLM o Claude">
              <span>📥</span> Importar
            </button>
          </div>
        </div>
      `;
    });

    modDiv.innerHTML = `
      <div data-accion="ruta-alternar-modulo" class="cursor-pointer p-5 border-b border-slate-800/80 bg-slate-900/90 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-850 transition select-none">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-xl bg-sky-500/10 border border-sky-500/20 text-sky-400 font-bold flex items-center justify-center text-xs">
            ${modIdx + 1}
          </div>
          <div>
            <h3 class="font-bold text-white text-base">${escapeHtml(mod.titulo)}</h3>
            ${mod.descripcion ? `<p class="text-xs text-slate-400">${escapeHtml(mod.descripcion)}</p>` : ''}
          </div>
        </div>
        <div class="flex items-center gap-3 text-xs text-slate-400">
          <span>${completedInMod}/${mod.temas.length} temas (${modPct}%)</span>
          <div class="w-24 bg-slate-800 h-2 rounded-full overflow-hidden">
            <div class="bg-sky-500 h-full" style="width: ${modPct}%;"></div>
          </div>
        </div>
      </div>
      <div class="module-body p-5 space-y-2.5">
        ${mod.temas.length > 0 ? topicsHtml : `
          <div class="p-4 bg-slate-950/70 border border-dashed border-slate-700 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p class="text-xs text-slate-400">Esta materia todavía no tiene temas. Genéralos con IA cuando vayas a cursarla.</p>
            <button type="button" data-accion="ruta-expandir-modulo" data-id="${Number(mod.id)}" class="au-boton au-boton--secundario au-boton--chico" title="Generar con IA los temas de esta materia">
              <span>🌱</span> Expandir materia
            </button>
          </div>
        `}
      </div>
    `;

    container.appendChild(modDiv);
  });
}

async function toggleTopicStatus(topicId, currentStatus) {
  let nextStatus = 'en_progreso';
  if (currentStatus === 'pendiente') nextStatus = 'en_progreso';
  else if (currentStatus === 'en_progreso') nextStatus = 'completado';
  else nextStatus = 'pendiente';

  try {
    const res = await fetch(`/api/roadmap/topics/${topicId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ estado: nextStatus })
    });
    if (!res.ok) throw new Error("Error actualizando estado");
    await loadRoadmapDetails(state.activeRoadmapId);
  } catch (err) {
    alert("Error al actualizar estado: " + err.message);
  }
}

// --- EXPANSIÓN DE MATERIA A DEMANDA ---

async function expandRoadmapModule(moduleId, btn) {
  const originalLabel = btn ? btn.textContent : '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⚡ Generando temas...';
  }

  try {
    const res = await fetch(`/api/roadmap/modules/${moduleId}/expand`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "No se pudo expandir la materia");
    }
    const added = await res.json();
    await loadRoadmapDetails(state.activeRoadmapId);
    alert(`🌱 Se agregaron ${added.length} temas a la materia.`);
  } catch (err) {
    alert("No se pudo expandir la materia: " + err.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalLabel;
    }
  }
}

// --- MODAL PERFIL PEDAGÓGICO ---

const PEDAGOGICAL_PROFILE_ORIGIN_LABELS = {
  ia: 'generado por IA',
  arquetipo: 'arquetipo de la disciplina',
  editado: 'editado por ti'
};
const PEDAGOGICAL_PROFILE_MIN_SECTIONS = 3;
const PEDAGOGICAL_PROFILE_MAX_SECTIONS = 8;

function setPedagogicalProfileStatus(message) {
  document.getElementById('pedagogical-profile-status').textContent = message || '';
}

function addPedagogicalProfileSection(section) {
  const list = document.getElementById('pedagogical-profile-sections');
  if (list.children.length >= PEDAGOGICAL_PROFILE_MAX_SECTIONS) {
    setPedagogicalProfileStatus(`Un perfil admite como máximo ${PEDAGOGICAL_PROFILE_MAX_SECTIONS} secciones.`);
    return;
  }

  const row = document.createElement('div');
  row.className = 'pedagogical-profile-section au-tarjeta au-tarjeta--hundida';

  const header = document.createElement('div');
  header.className = 'flex items-center gap-2';

  const titleInput = document.createElement('input');
  titleInput.type = 'text';
  titleInput.maxLength = 200;
  titleInput.placeholder = 'Título de la sección';
  titleInput.className = 'pedagogical-profile-section-title au-campo__control flex-1';
  titleInput.value = section && section.titulo ? section.titulo : '';

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'au-boton au-boton--fantasma au-boton--icono au-boton--chico';
  removeBtn.title = 'Quitar sección';
  removeBtn.textContent = '🗑️';
  removeBtn.addEventListener('click', () => row.remove());

  const instructionInput = document.createElement('textarea');
  instructionInput.rows = 2;
  instructionInput.maxLength = 2000;
  instructionInput.placeholder = 'Qué debe desarrollar esta sección';
  instructionInput.className = 'pedagogical-profile-section-instruction au-campo__control w-full';
  instructionInput.value = section && section.instruccion ? section.instruccion : '';

  header.appendChild(titleInput);
  header.appendChild(removeBtn);
  row.appendChild(header);
  row.appendChild(instructionInput);
  list.appendChild(row);
}

function fillPedagogicalProfileForm(profile) {
  document.getElementById('pedagogical-profile-origen').textContent =
    PEDAGOGICAL_PROFILE_ORIGIN_LABELS[profile.origen] || profile.origen || '-';
  document.getElementById('pedagogical-profile-disciplina').value = profile.disciplina || '';
  document.getElementById('pedagogical-profile-arquetipo').value = profile.arquetipo || 'general';
  document.getElementById('pedagogical-profile-rol').value = profile.rol_docente || '';
  document.getElementById('pedagogical-profile-fuentes').value = profile.tipo_fuentes || '';
  document.getElementById('pedagogical-profile-usa-codigo').checked = Boolean(profile.usa_codigo);
  document.getElementById('pedagogical-profile-usa-diagramas').checked = Boolean(profile.usa_diagramas);

  document.getElementById('pedagogical-profile-sections').replaceChildren();
  (profile.secciones || []).forEach(section => addPedagogicalProfileSection(section));

  document.getElementById('pedagogical-profile-flashcards').value = (profile.flashcards_ejemplo || [])
    .map(card => `Q: ${card.pregunta}\nA: ${card.respuesta}`)
    .join('\n\n');
}

async function openPedagogicalProfileModal() {
  if (!state.activeRoadmapId) {
    alert("Selecciona primero una ruta de aprendizaje.");
    return;
  }

  setPedagogicalProfileStatus('');
  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/pedagogical-profile`);
    if (!res.ok) throw new Error("Error cargando el perfil pedagógico");
    fillPedagogicalProfileForm(await res.json());
    Au.modal.abrir('modal-pedagogical-profile');
  } catch (err) {
    alert("No se pudo abrir el perfil pedagógico: " + err.message);
  }
}

function closePedagogicalProfileModal() {
  Au.modal.cerrar('modal-pedagogical-profile');
}

function parsePedagogicalProfileFlashcards(text) {
  const cards = [];
  const pattern = /Q:\s*(.+?)\s*\n\s*A:\s*([\s\S]+?)(?=\n\s*Q:|$)/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const pregunta = match[1].trim();
    const respuesta = match[2].trim();
    if (pregunta && respuesta) cards.push({ pregunta, respuesta });
  }
  return cards;
}

async function savePedagogicalProfile() {
  const btn = document.getElementById('btn-save-pedagogical-profile');
  const secciones = Array.from(document.querySelectorAll('#pedagogical-profile-sections .pedagogical-profile-section'))
    .map(row => ({
      titulo: row.querySelector('.pedagogical-profile-section-title').value.trim(),
      instruccion: row.querySelector('.pedagogical-profile-section-instruction').value.trim()
    }));

  if (secciones.length < PEDAGOGICAL_PROFILE_MIN_SECTIONS || secciones.length > PEDAGOGICAL_PROFILE_MAX_SECTIONS) {
    setPedagogicalProfileStatus(`El perfil necesita entre ${PEDAGOGICAL_PROFILE_MIN_SECTIONS} y ${PEDAGOGICAL_PROFILE_MAX_SECTIONS} secciones.`);
    return;
  }
  if (secciones.some(s => !s.titulo || !s.instruccion)) {
    setPedagogicalProfileStatus('Cada sección necesita un título y una consigna.');
    return;
  }

  const payload = {
    disciplina: document.getElementById('pedagogical-profile-disciplina').value.trim(),
    arquetipo: document.getElementById('pedagogical-profile-arquetipo').value,
    rol_docente: document.getElementById('pedagogical-profile-rol').value.trim(),
    secciones: secciones,
    usa_codigo: document.getElementById('pedagogical-profile-usa-codigo').checked,
    usa_diagramas: document.getElementById('pedagogical-profile-usa-diagramas').checked,
    tipo_fuentes: document.getElementById('pedagogical-profile-fuentes').value.trim(),
    flashcards_ejemplo: parsePedagogicalProfileFlashcards(document.getElementById('pedagogical-profile-flashcards').value)
  };

  if (!payload.disciplina || !payload.rol_docente || !payload.tipo_fuentes) {
    setPedagogicalProfileStatus('Completa la disciplina, el rol docente y el tipo de fuentes.');
    return;
  }

  btn.disabled = true;
  setPedagogicalProfileStatus('');
  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/pedagogical-profile`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = typeof err.detail === 'string' ? err.detail : 'Revisa los campos del perfil (longitud y cantidad de secciones).';
      throw new Error(detail);
    }
    fillPedagogicalProfileForm(await res.json());
    closePedagogicalProfileModal();
    await loadRoadmapDetails(state.activeRoadmapId);
  } catch (err) {
    setPedagogicalProfileStatus("No se pudo guardar el perfil: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

// --- MODAL NUEVA RUTA ---

function openNewRoadmapModal() {
  Au.modal.abrir('modal-new-roadmap');
}

function closeNewRoadmapModal() {
  Au.modal.cerrar('modal-new-roadmap');
}

function handleTemplateSelectChange(select) {
  const promptInput = document.getElementById('new-roadmap-prompt');
  const levelSelect = document.getElementById('new-roadmap-level');
  const categorySelect = document.getElementById('new-roadmap-category');

  if (!select.value) {
    promptInput.value = '';
    return;
  }

  promptInput.value = select.value;
  if (select.value.includes("Data Engineer")) {
    levelSelect.value = "Senior";
    categorySelect.value = "data_engineering";
  } else if (select.value.includes("AI Solutions")) {
    levelSelect.value = "Staff / Principal";
    categorySelect.value = "artificial_intelligence";
  } else if (select.value.includes("Cloud Infrastructure")) {
    levelSelect.value = "Senior";
    categorySelect.value = "cloud_devops";
  } else if (select.value.includes("BI")) {
    levelSelect.value = "Senior";
    categorySelect.value = "business_intelligence";
  }
}

function handleCategorySelectChange(val) {
  const customContainer = document.getElementById('new-roadmap-custom-category-container');
  const customInput = document.getElementById('new-roadmap-custom-category');
  if (!customContainer) return;
  if (val === 'custom') {
    customContainer.classList.remove('hidden');
    if (customInput) customInput.focus();
  } else {
    customContainer.classList.add('hidden');
  }
}

async function submitCreateRoadmap() {
  const prompt = document.getElementById('new-roadmap-prompt').value.trim();
  const level = document.getElementById('new-roadmap-level').value;
  const categorySelect = document.getElementById('new-roadmap-category');
  const customCatInput = document.getElementById('new-roadmap-custom-category');
  const enfoqueSelect = document.getElementById('new-roadmap-enfoque');
  const alcanceSelect = document.getElementById('new-roadmap-alcance');
  const btn = document.getElementById('btn-submit-create-roadmap');

  if (!prompt) {
    alert("Ingresa un objetivo o selecciona una plantilla.");
    return;
  }

  let category = categorySelect ? categorySelect.value : 'general';
  if (category === 'custom' && customCatInput) {
    category = customCatInput.value.trim() || 'general';
  }
  const enfoque = enfoqueSelect ? enfoqueSelect.value : 'profesional';
  const alcance = alcanceSelect ? alcanceSelect.value : 'curso';

  btn.disabled = true;
  btn.innerHTML = '<span>⚡</span> Diseñando ruta con IA...';

  try {
    const res = await fetch('/api/roadmap/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt,
        target_role: prompt,
        experience_level: level,
        categoria: category,
        enfoque_estudio: enfoque,
        alcance: alcance
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error creando ruta");
    }

    const created = await res.json();
    closeNewRoadmapModal();
    state.activeRoadmapId = created.id;
    await loadRoadmaps();
    const aviso = created.metadata_json ? created.metadata_json.aviso : null;
    if (aviso) {
      alert(`⚠️ Ruta creada SIN IA: ${created.titulo}\n\n${aviso}`);
    } else {
      alert(`🎉 ¡Ruta creada exitosamente: ${created.titulo}!`);
    }
  } catch (err) {
    alert("Error al generar ruta: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>✨</span> Generar Ruta';
  }
}

// --- PESTAÑAS Y FUNCIONES DE INGESTA DE TEMARIOS (SYLLABUS) ---
function switchNewRoadmapTab(tab) {
  state.activeNewRoadmapTab = tab;
  const secAi = document.getElementById('section-modal-ai');
  const secIngest = document.getElementById('section-modal-ingest');
  const btnAi = document.getElementById('btn-tab-modal-ai');
  const btnIngest = document.getElementById('btn-tab-modal-ingest');
  const btnSubmit = document.getElementById('btn-submit-create-roadmap');

  if (tab === 'ingest') {
    if (secAi) secAi.classList.add('hidden');
    if (secIngest) secIngest.classList.remove('hidden');
    if (btnAi) btnAi.setAttribute('aria-selected', 'false');
    if (btnIngest) btnIngest.setAttribute('aria-selected', 'true');
    if (btnSubmit) btnSubmit.innerHTML = '<span>🚀</span> Crear Ruta desde Temario';
  } else {
    if (secAi) secAi.classList.remove('hidden');
    if (secIngest) secIngest.classList.add('hidden');
    if (btnAi) btnAi.setAttribute('aria-selected', 'true');
    if (btnIngest) btnIngest.setAttribute('aria-selected', 'false');
    if (btnSubmit) btnSubmit.innerHTML = '<span>✨</span> Generar Ruta';
  }
}

async function previewSyllabus() {
  const textInput = document.getElementById('import-syllabus-text');
  const fileInput = document.getElementById('import-syllabus-file');
  const titleInput = document.getElementById('import-syllabus-title');
  const enfoqueSelect = document.getElementById('import-syllabus-enfoque');
  const levelSelect = document.getElementById('import-syllabus-level');
  const catInput = document.getElementById('import-syllabus-category');
  const enhanceCheck = document.getElementById('import-syllabus-enhance');
  const btn = document.getElementById('btn-preview-syllabus');

  const rawText = textInput ? textInput.value.trim() : '';
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;

  if (!rawText && !file) {
    alert("Pega un temario de texto o selecciona un archivo (.pdf, .md, .txt).");
    return;
  }

  btn.disabled = true;
  btn.innerText = "Analizando...";

  try {
    let res;
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('titulo', titleInput.value.trim() || file.name.replace(/\.[^/.]+$/, ""));
      formData.append('categoria', catInput.value.trim() || 'general');
      formData.append('nivel_objetivo', levelSelect.value);
      formData.append('enfoque_estudio', enfoqueSelect.value);
      formData.append('enhance_with_ai', enhanceCheck.checked ? 'true' : 'false');
      formData.append('save_directly', 'false');

      res = await fetch('/api/roadmap/import-syllabus-file', {
        method: 'POST',
        body: formData
      });
    } else {
      res = await fetch('/api/roadmap/import-syllabus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          titulo: titleInput.value.trim() || 'Ruta desde Temario',
          categoria: catInput.value.trim() || 'general',
          nivel_objetivo: levelSelect.value,
          enfoque_estudio: enfoqueSelect.value,
          raw_text: rawText,
          enhance_with_ai: enhanceCheck.checked,
          save_directly: false
        })
      });
    }

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error previsualizando temario");
    }

    const preview = await res.json();
    state.parsedSyllabusPreview = preview;

    const previewContainer = document.getElementById('syllabus-preview-container');
    const previewTitle = document.getElementById('syllabus-preview-title');
    const previewStats = document.getElementById('syllabus-preview-stats');
    const modulesContainer = document.getElementById('syllabus-preview-modules');

    if (previewContainer && previewTitle && previewStats && modulesContainer) {
      previewContainer.classList.remove('hidden');
      previewTitle.textContent = preview.titulo;
      previewStats.textContent = `${preview.total_modulos} módulos, ${preview.total_temas} temas (${preview.duracion_total_estimada_horas}h estimadas)`;

      modulesContainer.innerHTML = preview.modulos.map(m => `
        <div class="p-2.5 bg-slate-900 border border-slate-800 rounded-xl space-y-1">
          <div class="font-bold text-white flex items-center justify-between">
            <span>📁 ${escapeHtml(m.titulo)}</span>
            <span class="text-xs text-slate-500 font-normal">${m.temas.length} temas</span>
          </div>
          <ul class="list-disc list-inside text-slate-300 space-y-0.5 pl-1">
            ${m.temas.map(t => `<li class="truncate">${escapeHtml(t.titulo)}</li>`).join('')}
          </ul>
        </div>
      `).join('');
    }
  } catch (err) {
    alert("Error al previsualizar temario: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerText = "🔍 Previsualizar";
  }
}

async function submitNewRoadmapForm() {
  if (state.activeNewRoadmapTab === 'ingest') {
    await submitImportSyllabusDirect();
  } else {
    await submitCreateRoadmap();
  }
}

async function submitImportSyllabusDirect() {
  const textInput = document.getElementById('import-syllabus-text');
  const fileInput = document.getElementById('import-syllabus-file');
  const titleInput = document.getElementById('import-syllabus-title');
  const enfoqueSelect = document.getElementById('import-syllabus-enfoque');
  const levelSelect = document.getElementById('import-syllabus-level');
  const catInput = document.getElementById('import-syllabus-category');
  const enhanceCheck = document.getElementById('import-syllabus-enhance');
  const btn = document.getElementById('btn-submit-create-roadmap');

  const rawText = textInput ? textInput.value.trim() : '';
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;

  if (!rawText && !file) {
    alert("Pega un temario de texto o selecciona un archivo (.pdf, .md, .txt).");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span>⚡</span> Procesando e importando ruta...';

  try {
    let res;
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('titulo', titleInput.value.trim() || file.name.replace(/\.[^/.]+$/, ""));
      formData.append('categoria', catInput.value.trim() || 'general');
      formData.append('nivel_objetivo', levelSelect.value);
      formData.append('enfoque_estudio', enfoqueSelect.value);
      formData.append('enhance_with_ai', enhanceCheck.checked ? 'true' : 'false');
      formData.append('save_directly', 'true');

      res = await fetch('/api/roadmap/import-syllabus-file', {
        method: 'POST',
        body: formData
      });
    } else {
      res = await fetch('/api/roadmap/import-syllabus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          titulo: titleInput.value.trim() || 'Ruta desde Temario',
          categoria: catInput.value.trim() || 'general',
          nivel_objetivo: levelSelect.value,
          enfoque_estudio: enfoqueSelect.value,
          raw_text: rawText,
          enhance_with_ai: enhanceCheck.checked,
          save_directly: true
        })
      });
    }

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error importando temario");
    }

    const created = await res.json();
    closeNewRoadmapModal();
    state.activeRoadmapId = created.id;
    await loadRoadmaps();
    alert(`🎉 ¡Ruta importada y creada exitosamente: ${created.titulo}!`);
  } catch (err) {
    alert("Error al importar temario: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>🚀</span> Crear Ruta desde Temario';
  }
}

// --- VISTAS DEL ROADMAP: ÁRBOL Y GRAFO DE PRELACIONES (DAG) ---
function switchRoadmapViewMode(mode) {
  state.roadmapViewMode = mode;
  const treeContainer = document.getElementById('roadmap-tree-container');
  const dagContainer = document.getElementById('roadmap-dag-container');
  const btnTree = document.getElementById('btn-view-tree');
  const btnDag = document.getElementById('btn-view-dag');
  const dagToolbar = document.getElementById('dag-toolbar');

  if (mode === 'dag') {
    if (treeContainer) treeContainer.classList.add('hidden');
    if (dagContainer) dagContainer.classList.remove('hidden');
    if (dagToolbar) dagToolbar.classList.remove('hidden');
    if (btnTree) btnTree.setAttribute('aria-selected', 'false');
    if (btnDag) btnDag.setAttribute('aria-selected', 'true');
    loadRoadmapGraph();
  } else {
    if (treeContainer) treeContainer.classList.remove('hidden');
    if (dagContainer) dagContainer.classList.add('hidden');
    if (dagToolbar) dagToolbar.classList.add('hidden');
    if (btnTree) btnTree.setAttribute('aria-selected', 'true');
    if (btnDag) btnDag.setAttribute('aria-selected', 'false');
  }
}

async function loadRoadmapGraph() {
  if (!state.activeRoadmapId) return;
  const nodesBoard = document.getElementById('dag-nodes-board');
  if (nodesBoard) {
    nodesBoard.innerHTML = '<div class="col-span-full py-8 text-center text-slate-500"><div class="inline-block animate-spin text-xl mb-1">⚡</div><p class="text-xs">Calculando orden topológico y ruta crítica...</p></div>';
  }

  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/graph`);
    if (!res.ok) throw new Error("Error cargando grafo de prelaciones");
    const graphData = await res.json();
    state.activeGraphData = graphData;
    renderRoadmapGraph(graphData);
    renderDagDiagram(graphData);
    updateDagInteractiveMap(state.activeRoadmapId);
  } catch (err) {
    console.error("Error en loadRoadmapGraph:", err);
    if (nodesBoard) {
      nodesBoard.innerHTML = `<div class="col-span-full p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-xs">Error: ${escapeHtml(err && err.message ? err.message : 'Error inesperado')}</div>`;
    }
  }
}

function setDagViewMode(mode) {
  state.dagViewMode = mode;
  const btnPipe = document.getElementById('btn-dag-view-pipeline');
  const btnComp = document.getElementById('btn-dag-view-compact');
  if (btnPipe && btnComp) {
    btnPipe.setAttribute('aria-selected', mode === 'pipeline' ? 'true' : 'false');
    btnComp.setAttribute('aria-selected', mode === 'compact' ? 'true' : 'false');
  }
  if (state.activeGraphData) {
    renderRoadmapGraph(state.activeGraphData);
  }
}

function renderRoadmapGraph(graphData) {
  const kpiNodes = document.getElementById('dag-kpi-nodes');
  const kpiEdges = document.getElementById('dag-kpi-edges');
  const kpiCritical = document.getElementById('dag-kpi-critical');
  const kpiStatus = document.getElementById('dag-kpi-status');

  if (kpiNodes) kpiNodes.textContent = graphData.nodes ? graphData.nodes.length : 0;
  if (kpiEdges) kpiEdges.textContent = graphData.edges ? graphData.edges.length : 0;
  if (kpiCritical) kpiCritical.textContent = `${graphData.critical_path ? graphData.critical_path.length : 0} temas`;
  if (kpiStatus) {
    if (graphData.has_cycle) {
      kpiStatus.className = "text-xs font-extrabold text-rose-400 mt-1";
      kpiStatus.textContent = "⚠️ Ciclo Detectado";
    } else {
      kpiStatus.className = "text-xs font-extrabold text-emerald-400 mt-1";
      kpiStatus.textContent = "● Acíclico (DAG Válido)";
    }
  }

  const implicitToggle = document.getElementById('dag-toggle-implicit');
  if (implicitToggle) implicitToggle.checked = graphData.secuencia_implicita !== false;

  // Secuencia pedagógica recomendada (Orden Topológico Enriquecido)
  const stepsContainer = document.getElementById('dag-topological-steps');
  const statsContainer = document.getElementById('dag-topological-stats');

  if (stepsContainer) {
    if (!graphData.topological_order || graphData.topological_order.length === 0) {
      stepsContainer.innerHTML = '<span class="text-xs text-slate-500 italic">No hay temas en esta ruta de aprendizaje.</span>';
      if (statsContainer) statsContainer.innerHTML = '';
    } else {
      const nodeMap = {};
      (graphData.nodes || []).forEach(n => { nodeMap[n.id] = n; });
      const totalNodes = graphData.topological_order.length;
      const completedCount = (graphData.nodes || []).filter(n => n.estado === 'completado').length;
      const readyCount = (graphData.nodes || []).filter(n => !n.is_blocked && n.estado !== 'completado').length;
      const blockedCount = (graphData.nodes || []).filter(n => n.is_blocked).length;
      const pct = totalNodes > 0 ? ((completedCount / totalNodes) * 100).toFixed(0) : 0;

      // Renderizar estadísticas de la secuencia
      if (statsContainer) {
        statsContainer.innerHTML = `
          <div class="flex items-center gap-4 flex-wrap">
            <span class="font-semibold text-white">Progreso: <strong class="text-emerald-400 font-mono">${completedCount}/${totalNodes}</strong> dominados (${pct}%)</span>
            <span class="text-slate-600 hidden sm:inline">|</span>
            <span class="text-sky-300 font-medium">🔓 ${readyCount} listos para estudiar</span>
            <span class="text-slate-600 hidden sm:inline">|</span>
            <span class="text-rose-300 font-medium">🔒 ${blockedCount} esperando prerrequisitos</span>
          </div>
          <div class="w-full sm:w-48 bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div class="bg-gradient-to-r from-sky-500 to-emerald-400 h-full rounded-full transition-all duration-300" style="width: ${pct}%"></div>
          </div>
        `;
      }

      const viewMode = state.dagViewMode || 'pipeline';

      if (viewMode === 'compact') {
        // Vista Compacta (Badges en hilera)
        stepsContainer.innerHTML = `
          <div class="flex flex-wrap items-center gap-2 py-1">
            ${graphData.topological_order.map((nodeId, idx) => {
              const node = nodeMap[nodeId] || { titulo: `Tema #${nodeId}`, estado: 'pendiente' };
              let badgeTone = "au-boton--suave-alerta";
              let statusIcon = "🔓";
              if (node.estado === 'completado') {
                badgeTone = "au-boton--suave-exito";
                statusIcon = "✅";
              } else if (node.estado === 'en_progreso') {
                badgeTone = "au-boton--suave-primario";
                statusIcon = "⏳";
              } else if (node.is_blocked) {
                badgeTone = "au-boton--fantasma";
                statusIcon = "🔒";
              } else {
                badgeTone = "au-boton--suave-alerta";
                statusIcon = "🔓";
              }

              return `
                <button type="button" data-accion="ruta-destacar-nodo-grafo" data-id="${Number(node.id)}" class="au-boton au-boton--chico ${badgeTone} flex items-center gap-1.5" title="${escapeHtml(node.titulo)} (${escapeHtml(node.modulo_titulo || '')})">
                  <span class="font-mono text-xs font-bold opacity-60">#${idx + 1}</span>
                  <span>${statusIcon}</span>
                  <span class="truncate max-w-[150px] font-medium">${escapeHtml(node.titulo)}</span>
                  ${node.is_critical_path ? '<span class="text-amber-400 font-black text-xs" title="Ruta Crítica">⚡</span>' : ''}
                </button>
              `;
            }).join(' <span class="text-slate-600 text-xs select-none">➔</span> ')}
          </div>
        `;
      } else {
        // Vista Pipeline (Stepper interactivo con tarjetas ricas y conectores de flujo)
        stepsContainer.innerHTML = `
          <div class="flex items-stretch gap-3 overflow-x-auto pb-3 pt-1 scroll-smooth scroll-x-pista">
            ${graphData.topological_order.map((nodeId, idx) => {
              const node = nodeMap[nodeId] || { titulo: `Tema #${nodeId}`, estado: 'pendiente' };
              
              let statusBorder = "border-slate-800 hover:border-slate-700";
              let statusPill = Au.insignia({ texto: 'Pendiente' });
              let isLocked = Boolean(node.is_blocked);

              if (node.estado === 'completado') {
                statusBorder = "border-emerald-700/80 bg-emerald-950/20 hover:border-emerald-500";
                statusPill = Au.insignia({ texto: 'Dominado', icono: '✅', tono: 'exito' });
              } else if (node.estado === 'en_progreso') {
                statusBorder = "border-sky-700/80 bg-sky-950/20 hover:border-sky-500 ring-1 ring-sky-500/20";
                statusPill = Au.insignia({ texto: 'En Curso', icono: '⏳', tono: 'primario' });
              } else if (isLocked) {
                statusBorder = "border-rose-900/60 bg-rose-950/10 hover:border-rose-700";
                statusPill = Au.insignia({ texto: 'Bloqueado', icono: '🔒', tono: 'peligro' });
              } else {
                statusBorder = "border-amber-700/60 bg-amber-950/10 hover:border-amber-500";
                statusPill = Au.insignia({ texto: 'Listo', icono: '🔓', tono: 'alerta' });
              }

              return `
                <div class="flex items-stretch gap-3 shrink-0">
                  <div data-accion="ruta-destacar-nodo-grafo" data-id="${Number(node.id)}" class="w-64 p-4 rounded-2xl bg-slate-950/90 border ${statusBorder} flex flex-col justify-between space-y-3 cursor-pointer transition hover:-translate-y-0.5 shadow-md">
                    <!-- Cabecera de la tarjeta del paso -->
                    <div class="flex items-center justify-between">
                      <span class="text-xs font-mono font-extrabold px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-sky-400">
                        PASO ${String(idx + 1).padStart(2, '0')}
                      </span>
                      ${statusPill}
                    </div>

                    <!-- Módulo y Título -->
                    <div class="space-y-1">
                      <span class="text-xs font-semibold text-slate-400 truncate block">${escapeHtml(node.modulo_titulo || 'Módulo Principal')}</span>
                      <h5 class="text-xs sm:text-sm font-bold text-white leading-snug line-clamp-2" title="${escapeHtml(node.titulo)}">
                        ${escapeHtml(node.titulo)}
                      </h5>
                    </div>

                    <!-- Dependencias y Prelaciones -->
                    <div class="pt-2 border-t border-slate-900 flex items-center justify-between text-xs text-slate-400 font-mono">
                      <span>${node.in_degree > 0 ? `📥 ${node.in_degree} previo` : '🌱 Fundamento'}</span>
                      <span>${node.out_degree > 0 ? `🔓 Desbloquea ${node.out_degree}` : '🏁 Terminal'}</span>
                    </div>

                    <!-- Tags adicionales -->
                    <div class="flex flex-wrap items-center justify-between gap-1 pt-1">
                      ${node.is_critical_path ? Au.insignia({ texto: 'Ruta Crítica', icono: '⚡', tono: 'alerta' }) : '<span></span>'}
                      <span class="toque text-xs text-sky-400 hover:underline font-semibold">
                        Ver tema ↗
                      </span>
                    </div>
                  </div>

                  ${idx < totalNodes - 1 ? `
                    <div class="text-slate-600 font-bold text-sm shrink-0 flex items-center">
                      <span class="w-5 h-0.5 bg-slate-800 inline-block"></span>
                      <span class="text-sky-500/70 text-xs">▶</span>
                    </div>
                  ` : ''}
                </div>
              `;
            }).join('')}
          </div>
        `;
      }
    }
  }

  // Tablero de Nodos
  const nodesBoard = document.getElementById('dag-nodes-board');
  if (nodesBoard) {
    if (!graphData.nodes || graphData.nodes.length === 0) {
      nodesBoard.innerHTML = '<div class="col-span-full py-8 text-center text-slate-500">No hay temas disponibles.</div>';
    } else {
      nodesBoard.innerHTML = graphData.nodes.map(n => {
        let borderClass = "border-slate-800";
        let statusBadge = Au.insignia({ texto: 'Pendiente' });
        if (n.estado === 'completado') {
          borderClass = "border-emerald-800/80 bg-emerald-950/10";
          statusBadge = Au.insignia({ texto: 'Dominado ✔', tono: 'exito' });
        } else if (n.estado === 'en_progreso') {
          borderClass = "border-sky-800/80 bg-sky-950/10";
          statusBadge = Au.insignia({ texto: 'En Progreso ⚡', tono: 'primario' });
        } else if (n.is_blocked) {
          borderClass = "border-rose-900/60 bg-rose-950/10";
          statusBadge = Au.insignia({ texto: 'Bloqueado 🔒', tono: 'peligro' });
        } else {
          borderClass = "border-amber-900/60 bg-amber-950/10";
          statusBadge = Au.insignia({ texto: 'Listo 🚀', tono: 'alerta' });
        }

        const isCritical = n.is_critical_path;
        const isSelected = state.selectedGraphNodeId === n.id;

        return `
          <div id="graph-node-card-${n.id}" data-accion="ruta-destacar-nodo-grafo" data-id="${n.id}" class="au-tarjeta au-tarjeta--hundida cursor-pointer transition ${borderClass} ${isSelected ? 'ring-2 ring-indigo-500' : ''} ${isCritical ? 'shadow-lg shadow-amber-500/10' : ''}">
            <div class="flex items-start justify-between gap-2">
              <div>
                <span class="text-xs text-slate-500 font-mono block">${escapeHtml(n.modulo_titulo || 'Módulo')}</span>
                <h5 class="text-xs font-bold text-white leading-snug">${escapeHtml(n.titulo)}</h5>
              </div>
              <div class="flex items-center gap-1">
                ${isCritical ? '<span title="Ruta Crítica - Bloqueo Principal" class="text-amber-400 text-xs">⚡</span>' : ''}
                ${statusBadge}
              </div>
            </div>

            <!-- Dependencias & Desbloqueos -->
            <div class="text-xs space-y-1 pt-1 border-t border-slate-900">
              <div class="flex items-center justify-between text-slate-400">
                <span>Requisitos previos:</span>
                <span class="font-bold text-slate-200">${n.prerequisites ? n.prerequisites.length : 0}</span>
              </div>
              <div class="flex items-center justify-between text-slate-400">
                <span>Desbloquea a:</span>
                <span class="font-bold text-slate-200">${n.dependents ? n.dependents.length : 0}</span>
              </div>
            </div>

            <!-- Acciones Rápidas -->
            <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-900" data-sin-accion>
              <button type="button" data-accion="ruta-ver-clase" data-tema-id="${n.id}" class="au-boton au-boton--fantasma au-boton--chico">
                <span>📖</span> Ver Clase
              </button>
              <button type="button" data-accion="ruta-agregar-requisito-con-defaults" data-id="${n.id}" class="au-boton au-boton--fantasma au-boton--chico" title="Añadir prelación a partir de este tema">
                <span>➕</span> Prelación
              </button>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // Mermaid Code
  const mermaidPre = document.getElementById('dag-mermaid-code');
  if (mermaidPre) {
    mermaidPre.textContent = graphData.mermaid_code || "graph LR\n  %% Sin datos";
  }

  renderDagAvailable(graphData);
  selectDagNode(state.selectedGraphNodeId);
}

// --- GRAFO DIBUJADO: DIAGRAMA, SELECCIÓN DE NODO Y EDICIÓN DE PRELACIONES ---
const DAG_NODE_HIGHLIGHT_CLASSES = ['dag-node-selected', 'dag-node-prereq', 'dag-node-dependent', 'dag-node-dimmed'];
const DAG_EDGE_TYPE_LABELS = { estricta: 'Estricta', recomendada: 'Recomendada' };
let dagRenderSeq = 0;

function dagEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = text;
  return el;
}

function findGraphNode(nodeId) {
  const nodes = (state.activeGraphData && state.activeGraphData.nodes) || [];
  return nodes.find(n => n.id === nodeId) || null;
}

function dagNodeStatusLabel(node) {
  if (node.estado === 'completado') return 'Dominado ✔';
  if (node.estado === 'en_progreso') return 'En progreso';
  if (node.is_blocked) return 'Bloqueado 🔒';
  return 'Disponible';
}

// Mermaid 10 nombra cada nodo del flowchart como `flowchart-<id del nodo>-<n>`; el nuestro es `T_<id del tema>`.
function dagNodeIdFromElement(el) {
  const match = /^flowchart-T_(\d+)-\d+$/.exec(el.id || '');
  return match ? Number(match[1]) : null;
}

function setDagDiagramNotice(message) {
  const notice = document.getElementById('dag-diagram-notice');
  if (!notice) return;
  notice.textContent = message || '';
  notice.classList.toggle('hidden', !message);
}

let mermaidPromise = null;
let mermaidInicializado = false;
// Al cambiar el tema, el próximo diagrama se dibuja con los colores nuevos.
document.addEventListener('aulento:tema', () => { mermaidInicializado = false; });

function inicializarMermaid() {
  if (mermaidInicializado) return;
  if (window.mermaid && typeof window.mermaid.initialize === 'function') {
    window.mermaid.initialize({
      startOnLoad: false,
      theme: window.aulentoTema && window.aulentoTema.esClaro() ? 'default' : 'dark',
      securityLevel: 'strict',
      maxTextSize: 500000,
      maxEdges: 5000,
    });
    mermaidInicializado = true;
  }
}

function ensureMermaidLoaded() {
  if (window.mermaid) {
    inicializarMermaid();
    return Promise.resolve(window.mermaid);
  }
  if (mermaidPromise) return mermaidPromise;

  mermaidPromise = new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = '/static/vendor/mermaid.min.js';
    script.onload = () => {
      inicializarMermaid();
      if (!window.mermaid) mermaidPromise = null;
      resolve(window.mermaid || null);
    };
    script.onerror = () => {
      mermaidPromise = null;
      resolve(null);
    };
    document.head.appendChild(script);
  });

  return mermaidPromise;
}

async function renderDagDiagram(graphData) {
  const container = document.getElementById('dag-diagram');
  if (!container) return;
  const seq = ++dagRenderSeq;
  container.replaceChildren();

  if (!graphData.nodes || graphData.nodes.length === 0) {
    setDagDiagramNotice('Esta ruta todavía no tiene temas para dibujar.');
    return;
  }
  await ensureMermaidLoaded();
  if (seq !== dagRenderSeq) return;

  if (!window.mermaid) {
    setDagDiagramNotice('No se pudo cargar Mermaid, así que el grafo no se dibuja. El tablero de tarjetas de más abajo sigue disponible.');
    return;
  }

  const renderId = `dag-diagram-svg-${seq}`;
  try {
    const { svg } = await mermaid.render(renderId, graphData.mermaid_code);
    // Una carga más nueva ya pidió su propio dibujo: este quedó viejo.
    if (seq !== dagRenderSeq) return;
    container.innerHTML = svg;
  } catch (err) {
    console.error("Error dibujando el grafo de prelaciones:", err);
    const leftover = document.getElementById(`d${renderId}`);
    if (leftover) leftover.remove();
    if (seq !== dagRenderSeq) return;
    container.replaceChildren();
    setDagDiagramNotice('No se pudo dibujar el grafo. El tablero de tarjetas de más abajo sigue disponible.');
    return;
  }

  // Mermaid ajusta el SVG al ancho disponible; se fija su ancho natural para que el contenedor haga scroll.
  const svgEl = container.querySelector('svg');
  if (svgEl && svgEl.style.maxWidth) svgEl.style.minWidth = svgEl.style.maxWidth;

  let linked = 0;
  container.querySelectorAll('g.node').forEach(el => {
    const nodeId = dagNodeIdFromElement(el);
    if (nodeId === null) return;
    linked += 1;
    el.dataset.dagNodeId = String(nodeId);
    el.setAttribute('tabindex', '0');
    el.setAttribute('role', 'button');
    el.addEventListener('click', () => selectDagNode(nodeId));
    el.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      selectDagNode(nodeId);
    });
  });
  setDagDiagramNotice(linked > 0 ? '' : 'El diagrama no se pudo dibujar con los temas de la ruta (puede ser demasiado grande): usa el tablero de tarjetas de más abajo.');
  applyDagSelectionStyles();
}

function applyDagSelectionStyles() {
  const selected = findGraphNode(state.selectedGraphNodeId);
  const prereqs = new Set(selected ? selected.prerequisites : []);
  const dependents = new Set(selected ? selected.dependents : []);

  document.querySelectorAll('#dag-diagram g.node[data-dag-node-id]').forEach(el => {
    const nodeId = Number(el.dataset.dagNodeId);
    el.classList.remove(...DAG_NODE_HIGHLIGHT_CLASSES);
    if (!selected) return;
    if (nodeId === selected.id) el.classList.add('dag-node-selected');
    else if (prereqs.has(nodeId)) el.classList.add('dag-node-prereq');
    else if (dependents.has(nodeId)) el.classList.add('dag-node-dependent');
    else el.classList.add('dag-node-dimmed');
  });

  if (!selected) return;
  state.activeGraphData.nodes.forEach(n => {
    const card = document.getElementById(`graph-node-card-${n.id}`);
    if (!card) return;

    if (n.id === selected.id) {
      card.className = "au-tarjeta au-tarjeta--hundida ring-2 ring-indigo-500/50 shadow-xl transition cursor-pointer";
    } else if (prereqs.has(n.id)) {
      card.className = "au-tarjeta au-tarjeta--hundida border-2 border-amber-500/80 transition cursor-pointer";
    } else if (dependents.has(n.id)) {
      card.className = "au-tarjeta au-tarjeta--hundida border-2 border-emerald-500/80 transition cursor-pointer";
    } else {
      card.className = "au-tarjeta au-tarjeta--hundida opacity-40 transition cursor-pointer hover:opacity-100";
    }
  });
}

function buildDagEdgeRow(edge, otherTitle) {
  const row = dagEl('div', 'p-2 bg-slate-900 border border-slate-800 rounded-lg space-y-1.5');
  row.appendChild(dagEl('div', 'text-slate-200 font-medium break-words', otherTitle));

  const meta = dagEl('div', 'flex flex-wrap items-center gap-2');
  if (edge.inferida) {
    meta.appendChild(dagEl('span', 'text-xs text-slate-500 italic', 'Inferida por la secuencia implícita (no está guardada)'));
  } else {
    const badgeColor = edge.tipo === 'estricta' ? 'bg-rose-950 text-rose-300 border-rose-800' : 'bg-sky-950 text-sky-300 border-sky-800';
    meta.appendChild(dagEl('span', `px-1.5 py-0.5 rounded border text-xs font-bold ${badgeColor}`, DAG_EDGE_TYPE_LABELS[edge.tipo] || edge.tipo));

    const nextType = edge.tipo === 'estricta' ? 'recomendada' : 'estricta';
    const typeBtn = dagEl('button', 'text-xs text-indigo-400 hover:text-indigo-300 font-medium', `Cambiar a ${nextType}`);
    typeBtn.type = 'button';
    typeBtn.addEventListener('click', () => changeDagPrerequisiteType(edge.tema_origen_id, edge.tema_destino_id, nextType));
    meta.appendChild(typeBtn);

    const removeBtn = dagEl('button', 'text-xs text-rose-400 hover:text-rose-300 font-medium', 'Quitar');
    removeBtn.type = 'button';
    removeBtn.addEventListener('click', () => removeDagPrerequisite(edge.tema_origen_id, edge.tema_destino_id));
    meta.appendChild(removeBtn);
  }
  row.appendChild(meta);
  return row;
}

function buildDagEdgeSection(title, edges, titleOf, emptyText) {
  const section = dagEl('div', 'space-y-1.5 pt-2 border-t border-slate-900');
  section.appendChild(dagEl('h6', 'text-xs font-bold text-slate-300', `${title} (${edges.length})`));
  if (edges.length === 0) {
    section.appendChild(dagEl('p', 'text-xs text-slate-500 italic', emptyText));
  }
  edges.forEach(edge => section.appendChild(buildDagEdgeRow(edge, titleOf(edge))));
  return section;
}

function renderDagNodePanel(node) {
  const panel = document.getElementById('dag-node-panel');
  if (!panel) return;
  panel.replaceChildren();

  if (!node) {
    panel.appendChild(dagEl('p', 'text-slate-500 italic', 'Selecciona un tema del grafo para ver sus datos y editar sus prelaciones.'));
    return;
  }

  const header = dagEl('div', 'space-y-1');
  header.appendChild(dagEl('span', 'text-xs text-slate-500 font-mono block break-words', node.modulo_titulo || 'Módulo'));
  header.appendChild(dagEl('h5', 'text-sm font-bold text-white leading-snug break-words', node.titulo));
  panel.appendChild(header);

  const facts = dagEl('div', 'flex flex-wrap items-center gap-2 text-xs');
  facts.appendChild(dagEl('span', 'au-insignia', dagNodeStatusLabel(node)));
  facts.appendChild(dagEl('span', 'au-insignia', `Nivel ${node.nivel_topologico}`));
  if (node.is_critical_path) {
    facts.appendChild(dagEl('span', 'au-insignia au-insignia--alerta', '⚡ Ruta crítica'));
  }
  panel.appendChild(facts);

  const edges = state.activeGraphData.edges || [];
  panel.appendChild(buildDagEdgeSection(
    'Requiere',
    edges.filter(e => e.tema_destino_id === node.id),
    e => e.origen_titulo || `Tema #${e.tema_origen_id}`,
    'No tiene prerrequisitos.'
  ));
  panel.appendChild(buildDagEdgeSection(
    'Desbloquea',
    edges.filter(e => e.tema_origen_id === node.id),
    e => e.destino_titulo || `Tema #${e.tema_destino_id}`,
    'Ningún tema depende de este.'
  ));

  const addBtn = dagEl('button', 'w-full py-2 px-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition', '➕ Añadir prelación desde aquí');
  addBtn.type = 'button';
  addBtn.addEventListener('click', () => openAddPrerequisiteWithDefaults(node.id));
  panel.appendChild(addBtn);
}

function selectDagNode(nodeId) {
  const node = findGraphNode(nodeId);
  state.selectedGraphNodeId = node ? node.id : null;
  applyDagSelectionStyles();
  renderDagNodePanel(node);
  const frame = document.getElementById('dag-interactive-frame');
  if (frame && frame.contentWindow) {
    frame.contentWindow.postMessage({ type: 'dag-highlight-topic', topicId: state.selectedGraphNodeId, center: true }, window.location.origin);
  }
}

function highlightGraphNode(nodeId) {
  selectDagNode(nodeId);
  const drawn = document.querySelector(`#dag-diagram g.node[data-dag-node-id="${Number(nodeId)}"]`);
  const target = drawn || document.getElementById('dag-node-panel');
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
}

function renderDagAvailable(graphData) {
  const list = document.getElementById('dag-available-list');
  if (!list) return;
  list.replaceChildren();

  const nodesById = new Map((graphData.nodes || []).map(n => [n.id, n]));
  const available = (graphData.disponibles || []).map(id => nodesById.get(id)).filter(Boolean);
  if (available.length === 0) {
    list.appendChild(dagEl('p', 'text-xs text-slate-500 italic', 'No hay temas disponibles: están todos dominados o bloqueados.'));
    return;
  }

  available.forEach(node => {
    const btn = dagEl('button', 'w-full text-left px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-sky-500 transition flex items-center justify-between gap-2');
    btn.type = 'button';
    const text = dagEl('span', 'min-w-0');
    text.appendChild(dagEl('span', 'block text-xs text-slate-200 font-medium truncate', node.titulo));
    text.appendChild(dagEl('span', 'block text-xs text-slate-500 truncate', node.modulo_titulo || ''));
    btn.appendChild(text);
    if (node.is_critical_path) {
      const mark = dagEl('span', 'text-amber-400 text-xs font-bold shrink-0', '⚡ Crítico');
      mark.title = 'Está en la ruta crítica';
      btn.appendChild(mark);
    }
    btn.addEventListener('click', () => highlightGraphNode(node.id));
    list.appendChild(btn);
  });
}

async function dagErrorDetail(res, fallback) {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
    // Errores de validación (422): una lista de { msg }.
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      return body.detail.map(d => (d && d.msg) || '').filter(Boolean).slice(0, 3).join(' · ') || fallback;
    }
    return fallback;
  } catch (err) {
    return fallback;
  }
}

async function changeDagPrerequisiteType(origenId, destinoId, tipo) {
  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/prerequisites`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tema_origen_id: origenId, tema_destino_id: destinoId, tipo: tipo })
    });
    if (!res.ok) throw new Error(await dagErrorDetail(res, 'No se pudo cambiar el tipo de la prelación.'));
    await loadRoadmapGraph();
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function removeDagPrerequisite(origenId, destinoId) {
  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/prerequisites/${origenId}/${destinoId}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error(await dagErrorDetail(res, 'No se pudo quitar la prelación.'));
    await loadRoadmapGraph();
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function toggleDagImplicitSequence(enabled) {
  if (!state.activeRoadmapId) return;
  const toggle = document.getElementById('dag-toggle-implicit');
  toggle.disabled = true;
  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/graph-settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secuencia_implicita: enabled })
    });
    if (!res.ok) throw new Error(await dagErrorDetail(res, 'No se pudo guardar el ajuste del grafo.'));
    await loadRoadmapGraph();
  } catch (err) {
    toggle.checked = !enabled;
    alert("Error: " + err.message);
  } finally {
    toggle.disabled = false;
  }
}

// --- SUGERENCIAS DE PRELACIONES CON IA ---
function setPrerequisiteSuggestionsStatus(message) {
  document.getElementById('prereq-suggestions-status').textContent = message || '';
}

function openPrerequisiteSuggestionsModal() {
  Au.modal.abrir('modal-prerequisite-suggestions');
}

function closePrerequisiteSuggestionsModal() {
  Au.modal.cerrar('modal-prerequisite-suggestions');
}

function renderPrerequisiteSuggestions(discarded) {
  const suggestions = state.prerequisiteSuggestions;
  const list = document.getElementById('prereq-suggestions-list');
  list.replaceChildren();

  const discardedText = discarded > 0
    ? ` Se descartaron ${discarded} por repetidas, ya guardadas, inválidas o porque cerraban un ciclo.`
    : '';
  document.getElementById('prereq-suggestions-summary').textContent =
    `${suggestions.length} prelaciones propuestas. Nada se guarda hasta que aceptes.${discardedText}`;

  if (suggestions.length === 0) {
    list.appendChild(dagEl('p', 'text-xs text-slate-500 italic', 'La IA no propuso ninguna prelación nueva que se pueda guardar.'));
  }
  suggestions.forEach((suggestion, index) => {
    const row = dagEl('label', 'flex items-start gap-3 p-3 bg-slate-950 border border-slate-800 rounded-xl cursor-pointer hover:border-violet-600 transition');
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.checked = true;
    check.className = 'prereq-suggestion-check mt-0.5 rounded bg-slate-900 border-slate-700 text-violet-600 focus:ring-0';
    check.dataset.index = String(index);
    row.appendChild(check);

    const body = dagEl('div', 'min-w-0 space-y-1 text-xs');
    const pair = dagEl('div', 'text-slate-200 font-medium break-words');
    pair.appendChild(dagEl('span', '', suggestion.origen_titulo));
    pair.appendChild(dagEl('span', 'text-slate-500 px-1.5', '➔'));
    pair.appendChild(dagEl('span', '', suggestion.destino_titulo));
    body.appendChild(pair);
    const badgeColor = suggestion.tipo === 'estricta' ? 'bg-rose-950 text-rose-300 border-rose-800' : 'bg-sky-950 text-sky-300 border-sky-800';
    body.appendChild(dagEl('span', `inline-block px-1.5 py-0.5 rounded border text-xs font-bold ${badgeColor}`, DAG_EDGE_TYPE_LABELS[suggestion.tipo] || suggestion.tipo));
    if (suggestion.motivo) {
      body.appendChild(dagEl('p', 'text-xs text-slate-400 break-words', suggestion.motivo));
    }
    row.appendChild(body);
    list.appendChild(row);
  });

  document.getElementById('prereq-suggestions-disable-implicit').checked = false;
  document.getElementById('btn-accept-prereq-suggestions').disabled = suggestions.length === 0;
  setPrerequisiteSuggestionsStatus('');
}

async function requestPrerequisiteSuggestions() {
  const roadmapId = state.activeRoadmapId;
  if (!roadmapId) return;
  const btn = document.getElementById('btn-dag-suggest');
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = '⏳ Consultando a la IA...';

  try {
    const res = await fetch(`/api/roadmap/${roadmapId}/prerequisites/suggest`, { method: 'POST' });
    if (!res.ok) throw new Error(await dagErrorDetail(res, 'No se pudieron obtener sugerencias.'));
    const data = await res.json();
    // Si mientras tanto se abrió otra ruta, estas sugerencias ya no corresponden.
    if (roadmapId !== state.activeRoadmapId) return;
    state.prerequisiteSuggestions = data.sugerencias || [];
    renderPrerequisiteSuggestions(data.descartadas || 0);
    Au.modal.abrir('modal-prerequisite-suggestions');
  } catch (err) {
    alert("No se pudieron sugerir prelaciones: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

async function acceptPrerequisiteSuggestions() {
  if (!state.activeRoadmapId) return;
  const selected = Array.from(document.querySelectorAll('#prereq-suggestions-list .prereq-suggestion-check'))
    .filter(check => check.checked)
    .map(check => state.prerequisiteSuggestions[Number(check.dataset.index)])
    .filter(Boolean);
  if (selected.length === 0) {
    setPrerequisiteSuggestionsStatus('Marca al menos una prelación para guardar.');
    return;
  }

  const btn = document.getElementById('btn-accept-prereq-suggestions');
  btn.disabled = true;
  setPrerequisiteSuggestionsStatus('');
  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/prerequisites/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prelaciones: selected.map(s => ({
          tema_origen_id: s.tema_origen_id,
          tema_destino_id: s.tema_destino_id,
          tipo: s.tipo
        })),
        secuencia_implicita: document.getElementById('prereq-suggestions-disable-implicit').checked ? false : null
      })
    });
    if (!res.ok) throw new Error(await dagErrorDetail(res, 'No se pudieron guardar las prelaciones.'));
    closePrerequisiteSuggestionsModal();
    await loadRoadmapGraph();
  } catch (err) {
    setPrerequisiteSuggestionsStatus("No se guardó ninguna prelación: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

function copyRoadmapMermaid() {
  if (!state.activeGraphData || !state.activeGraphData.mermaid_code) {
    alert("No hay código de grafo disponible para copiar.");
    return;
  }
  navigator.clipboard.writeText(state.activeGraphData.mermaid_code).then(() => {
    alert("📋 ¡Código Mermaid copiado al portapapeles! Pegalo directamente en tus notas.");
  }).catch(() => {
    alert("No se pudo copiar automáticamente. Copialo desde la sección inferior.");
  });
}

function openAddPrerequisiteModal() {
  const modal = document.getElementById('modal-add-prerequisite');
  if (!modal || !state.activeGraphData || !state.activeGraphData.nodes) return;

  const origSelect = document.getElementById('prereq-origen-select');
  const destSelect = document.getElementById('prereq-destino-select');
  if (origSelect && destSelect) {
    const optionsHtml = state.activeGraphData.nodes.map(n => 
      `<option value="${n.id}">[${escapeHtml(n.modulo_titulo || 'Módulo')}] ${escapeHtml(n.titulo)}</option>`
    ).join('');
    origSelect.innerHTML = optionsHtml;
    destSelect.innerHTML = optionsHtml;
    if (state.activeGraphData.nodes.length > 1) {
      destSelect.selectedIndex = 1;
    }
  }
  Au.modal.abrir('modal-add-prerequisite');
}

function openAddPrerequisiteWithDefaults(origNodeId) {
  openAddPrerequisiteModal();
  const origSelect = document.getElementById('prereq-origen-select');
  const destSelect = document.getElementById('prereq-destino-select');
  if (!origSelect || !destSelect) return;
  origSelect.value = String(origNodeId);
  if (destSelect.value === origSelect.value) {
    const other = Array.from(destSelect.options).find(option => option.value !== origSelect.value);
    if (other) destSelect.value = other.value;
  }
}

function closeAddPrerequisiteModal() {
  Au.modal.cerrar('modal-add-prerequisite');
}

async function submitCreatePrerequisite() {
  if (!state.activeRoadmapId) return;
  const origSelect = document.getElementById('prereq-origen-select');
  const destSelect = document.getElementById('prereq-destino-select');
  const tipoSelect = document.getElementById('prereq-tipo-select');
  const descInput = document.getElementById('prereq-desc-input');
  const btn = document.getElementById('btn-submit-prereq');

  const origenId = parseInt(origSelect.value, 10);
  const destinoId = parseInt(destSelect.value, 10);

  if (origenId === destinoId) {
    alert("El tema origen y destino no pueden ser el mismo.");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span>⏳</span> Guardando...';

  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/prerequisites`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tema_origen_id: origenId,
        tema_destino_id: destinoId,
        tipo: tipoSelect.value,
        descripcion: descInput.value.trim() || null
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error al añadir prelación");
    }

    closeAddPrerequisiteModal();
    if (descInput) descInput.value = '';
    await loadRoadmapGraph();
    alert("✔ Prelación añadida correctamente al Grafo DAG.");
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>➕</span> Guardar Prelación';
  }
}

// --- MODAL PROMPT MAESTRO ---

async function openTopicPromptModal(topicId) {
  state.activeTopicId = topicId;
  document.getElementById('prompt-copy-status').textContent = '';
  Au.modal.abrir('modal-topic-prompt');
  await refreshTopicPrompt();
}

function closeTopicPromptModal() {
  Au.modal.cerrar('modal-topic-prompt');
}

function readPromptOptions() {
  const isChecked = (id) => document.getElementById(id).checked;
  return {
    include_materials: isChecked('prompt-toggle-materiales'),
    include_web_research: isChecked('prompt-toggle-web'),
    include_fsrs_cards: isChecked('prompt-toggle-fsrs'),
    target_llm: document.getElementById('prompt-target-llm').value,
    include_visuals: isChecked('prompt-toggle-visuals'),
    include_slides: isChecked('prompt-toggle-slides'),
    include_quiz: isChecked('prompt-toggle-quiz'),
    include_glossary: isChecked('prompt-toggle-glossary'),
    include_bridge: isChecked('prompt-toggle-bridge'),
    depth: document.getElementById('prompt-depth').value,
  };
}

let promptRequestSeq = 0;

async function refreshTopicPrompt() {
  if (!state.activeTopicId) return;

  // Varias opciones cambiadas seguidas disparan pedidos en paralelo: solo se muestra el último.
  const seq = ++promptRequestSeq;
  const options = readPromptOptions();
  const textarea = document.getElementById('prompt-output-text');

  textarea.value = "Construyendo Prompt Maestro calibrado...";

  try {
    const res = await fetch(`/api/roadmap/topics/${state.activeTopicId}/build-prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options)
    });
    if (!res.ok) throw new Error("Error generando prompt");
    const data = await res.json();
    if (seq !== promptRequestSeq) return;

    document.getElementById('prompt-modal-title').textContent = `Prompt Maestro: ${data.topic_title}`;
    document.getElementById('prompt-modal-subtitle').textContent = `Ruta: ${data.roadmap_title} | Destino: ${options.target_llm.toUpperCase()}`;
    textarea.value = data.master_prompt;
  } catch (err) {
    if (seq !== promptRequestSeq) return;
    textarea.value = "Error al construir prompt: " + err.message;
  }
}

function copyMasterPrompt() {
  const textarea = document.getElementById('prompt-output-text');
  if (!textarea || !textarea.value) return;

  navigator.clipboard.writeText(textarea.value).then(() => {
    const status = document.getElementById('prompt-copy-status');
    status.textContent = "✔ ¡Prompt copiado al portapapeles! Pégalo en tu LLM.";
    setTimeout(() => { status.textContent = ''; }, 4000);
  }).catch(() => {
    alert("No se pudo copiar automáticamente. Selecciónalo y presiona Ctrl+C.");
  });
}

function switchToImportFromPrompt() {
  const topicId = state.activeTopicId;
  closeTopicPromptModal();
  openImportLessonModal(topicId);
}

// --- MODAL IMPORTAR CLASE ---

function openImportLessonModal(topicId) {
  state.activeTopicId = topicId;
  document.getElementById('import-lesson-markdown').value = '';
  Au.modal.abrir('modal-import-lesson');
}

function closeImportLessonModal() {
  Au.modal.cerrar('modal-import-lesson');
}

// Indica si el tema de la ruta activa ya tiene una clase guardada
function topicHasLesson(topicId) {
  if (!state.activeRoadmap) return false;
  return state.activeRoadmap.modulos.some(m => m.temas.some(t => t.id === topicId && t.clase));
}

const AVISO_REEMPLAZO_CLASE = "Este tema ya tiene una clase. Si seguís, la actual queda guardada como versión anterior y podés restaurarla desde el visor de la clase.";

async function submitImportLesson() {
  const topicId = state.activeTopicId;
  const markdown = document.getElementById('import-lesson-markdown').value.trim();
  const source = document.getElementById('import-lesson-source').value;
  const autoFsrs = document.getElementById('import-auto-fsrs').checked;
  const autoVault = document.getElementById('import-auto-vault').checked;
  const btn = document.getElementById('btn-submit-import-lesson');

  if (!markdown) {
    alert("Pega el texto Markdown de la clase generada.");
    return;
  }
  if (topicHasLesson(topicId) && !confirm(`${AVISO_REEMPLAZO_CLASE}\n\n¿Reemplazarla con la clase importada?`)) return;

  btn.disabled = true;
  btn.innerHTML = '<span>⏳</span> Importando clase...';

  try {
    const res = await fetch(`/api/roadmap/topics/${topicId}/import-lesson`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown_content: markdown,
        origen: source
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error importando clase");
    }

    const imported = await res.json();

    let fsrsMsg = "";
    if (autoFsrs && imported.cards_count > 0) {
      await fetch(`/api/roadmap/lessons/${imported.lesson_id}/export-fsrs`, { method: 'POST' });
      fsrsMsg = `\n✔ ${imported.cards_count} flashcards inyectadas a tu mazo de repaso.`;
    }

    let vaultMsg = "";
    if (autoVault) {
      try {
        const vRes = await fetch(`/api/roadmap/lessons/${imported.lesson_id}/export-vault`, { method: 'POST' });
        if (vRes.ok) {
          const vData = await vRes.json();
          vaultMsg = `\n✔ Guardado en Mis notas: ${vData.vault_path}`;
          if (vData.backup_path) vaultMsg += `\n⚠ En el vault había una nota distinta; se guardó una copia en: ${vData.backup_path}`;
        }
      } catch (ve) {
        console.warn("Vault sync warning:", ve);
      }
    }

    closeImportLessonModal();
    await loadRoadmapDetails(state.activeRoadmapId);
    alert(`🎉 ¡Clase importada con éxito!${fsrsMsg}${vaultMsg}`);
    viewLessonModal(topicId);
  } catch (err) {
    alert("Error al importar clase: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>📥</span> Procesar e Importar Clase';
  }
}

// --- GENERACIÓN IN-APP CON IA ---

// Quién va a generar la clase: el proveedor activo con su modelo o, sin clave, el motor local de reserva.
async function quienGeneraLasClases() {
  const nombres = { gemini: 'Gemini', anthropic: 'Claude (Anthropic)', openai: 'OpenAI' };
  try {
    const res = await fetch('/api/config/ia');
    if (res.ok) {
      const ia = await res.json();
      const activo = ia.proveedores && ia.proveedores[ia.proveedor_activo];
      const nombre = nombres[ia.proveedor_activo] || ia.proveedor_activo;
      if (activo && activo.tiene_clave) {
        return { conIA: true, corto: nombre, texto: activo.modelo ? `${nombre} (${activo.modelo})` : nombre };
      }
      const motivo = esDemoSinIA() ? 'la cuenta es compartida y no tiene clave de IA' : `no hay clave de ${nombre} cargada`;
      return { conIA: false, corto: 'El motor local', texto: `el motor local de reserva, sin IA (${motivo}).` };
    }
  } catch (e) {
    console.warn('No se pudo saber qué proveedor de IA está activo', e);
  }
  return { conIA: true, corto: 'La IA', texto: 'el proveedor de IA activo' };
}

async function generateLessonInApp(topicId) {
  const options = readPromptOptions();
  const extras = [
    options.include_visuals && 'figuras',
    options.include_slides && 'diapositivas',
    options.include_quiz && 'autoevaluación',
    options.include_glossary && 'glosario y lecturas',
    options.include_bridge && 'puente con temas vecinos',
  ].filter(Boolean);
  const summary = `Profundidad: ${options.depth}\nIncluye: ${extras.length ? extras.join(', ') : 'solo la clase y las flashcards'}`;
  const reemplazo = topicHasLesson(topicId) ? `\n\n⚠ ${AVISO_REEMPLAZO_CLASE}` : '';
  const generador = await quienGeneraLasClases();
  const confirmado = await showConfirmDialog({
    title: 'Generar la clase completa',
    message: `La genera: ${generador.texto}\n\n${summary}\n\nEstas opciones se cambian en 📋 Prompt Maestro → Opciones del Prompt.${reemplazo}`,
    confirmText: 'Generar clase',
    icon: generador.conIA ? '⚡' : '🧩',
  });
  if (!confirmado) return;

  const overlay = document.createElement('div');
  overlay.id = 'modal-generando-clase';
  overlay.className = 'au-modal';
  overlay.hidden = true;
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-labelledby', 'generando-clase-titulo');
  // Como antes de la 072: mientras genera no se cierra con Esc ni tocando el fondo
  overlay.setAttribute('data-sin-cierre', '');
  overlay.innerHTML = `
    <div class="au-modal__caja au-modal__caja--angosta">
      <div class="au-modal__cuerpo text-center" aria-live="polite">
        <div class="inline-block animate-spin text-4xl" aria-hidden="true">⚡</div>
        <h3 id="generando-clase-titulo" class="au-modal__titulo">${escapeHtml(generador.corto)} está armando la clase</h3>
        <p class="text-xs text-slate-400">Analogía Feynman, diagramas y preguntas de Active Recall para FSRS v5...</p>
      </div>
    </div>
  `;
  overlay.addEventListener('au:cerrado', () => {
    overlay.remove();
  });
  document.body.appendChild(overlay);
  Au.modal.abrir('modal-generando-clase');

  try {
    const res = await fetch(`/api/roadmap/topics/${topicId}/generate-lesson`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error generando clase");
    }
    await loadRoadmapDetails(state.activeRoadmapId);
    Au.modal.cerrar('modal-generando-clase');
    viewLessonModal(topicId);
  } catch (err) {
    Au.modal.cerrar('modal-generando-clase');
    alert("Error generando clase: " + err.message);
  }
}

// --- MODAL VISOR DE CLASE ---

const LESSON_CALLOUTS = {
  tip: '💡 Idea clave',
  warning: '⚠️ Atención',
  note: '📝 Nota',
};

const LESSON_SANITIZE_CONFIG = {
  USE_PROFILES: { html: true, svg: true, svgFilters: true },
  FORBID_TAGS: ['style', 'form', 'button', 'input', 'textarea', 'select'],
};

let lessonMarkdownParser = null;

/**
 * Separa el primer bloque ```lang del Markdown: `content` es su interior (null si no hay)
 * y `rest` es el Markdown sin ningún bloque de ese lenguaje.
 */
function extractFencedBlock(markdown, lang) {
  const source = String(markdown || '');
  const fence = '(^|\\n)[ \\t]*```' + lang + '[ \\t]*(?:\\r?\\n([\\s\\S]*?))?\\r?\\n[ \\t]*```[ \\t]*(?=\\r?\\n|$)';
  const first = source.match(new RegExp(fence, 'i'));
  return {
    content: first ? (first[2] || '').trim() : null,
    rest: source.replace(new RegExp(fence, 'gi'), '$1'),
  };
}

function splitLessonSlides(slidesBlock) {
  if (!slidesBlock) return [];
  const slides = [[]];
  slidesBlock.split(/\r?\n/).forEach((line) => {
    if (/^\s*-{3,}\s*$/.test(line)) slides.push([]);
    else slides[slides.length - 1].push(line);
  });
  return slides.map((lines) => lines.join('\n').trim()).filter(Boolean);
}

function lessonLibsReady() {
  return Boolean(
    window.marked && typeof window.marked.Marked === 'function' &&
    window.DOMPurify && typeof window.DOMPurify.sanitize === 'function'
  );
}

function getLessonMarkdownParser() {
  if (!lessonMarkdownParser) {
    lessonMarkdownParser = new window.marked.Marked({
      gfm: true,
      renderer: {
        code(code, infostring) {
          const text = typeof code === 'object' && code !== null ? code.text : code;
          const info = typeof code === 'object' && code !== null ? code.lang : infostring;
          const lang = String(info || '').trim().split(/\s+/)[0].toLowerCase();
          if (lang === 'mermaid') return `<div class="mermaid">${escapeHtml(text)}</div>\n`;
          if (lang === 'svg') return `<figure class="lesson-figure">${text}</figure>\n`;
          if (lang === 'cards-fsrs' || lang === 'slides') return '';
          return false;
        },
      },
    });
  }
  return lessonMarkdownParser;
}

function renderLessonPlainText(markdown, container) {
  const notice = document.createElement('p');
  notice.className = 'lesson-fallback-notice';
  notice.textContent = '⚠️ No se pudo cargar el render de Markdown (¿sin conexión?). Se muestra la clase como texto plano.';
  const pre = document.createElement('pre');
  pre.className = 'lesson-plain';
  pre.textContent = markdown;
  container.replaceChildren(notice, pre);
}

function decorateLessonCallouts(container) {
  container.querySelectorAll('blockquote').forEach((quote) => {
    const firstBlock = quote.firstElementChild;
    const marker = firstBlock ? firstBlock.firstChild : null;
    if (!marker || marker.nodeType !== Node.TEXT_NODE) return;
    const match = marker.nodeValue.match(/^\s*\[!(tip|warning|note)\][-+]?[ \t]*/i);
    if (!match) return;

    const kind = match[1].toLowerCase();
    const rest = marker.nodeValue.slice(match[0].length);
    const lineEnd = rest.indexOf('\n');
    const customTitle = (lineEnd === -1 ? rest : rest.slice(0, lineEnd)).trim();
    // Con salto de línea, lo que sigue al título es el cuerpo; sin él, toda la línea es el cuerpo.
    const titleIsOwnLine = lineEnd !== -1 && customTitle !== '';
    marker.nodeValue = titleIsOwnLine ? rest.slice(lineEnd + 1) : rest;
    const label = document.createElement('div');
    label.className = 'lesson-callout-label';
    label.textContent = titleIsOwnLine
      ? `${LESSON_CALLOUTS[kind].split(' ')[0]} ${customTitle}`
      : LESSON_CALLOUTS[kind];
    quote.classList.add('lesson-callout', `lesson-callout-${kind}`);
    quote.prepend(label);
  });
}

let lessonSvgCounter = 0;

/**
 * Prefija los id de una figura SVG y reescribe sus referencias internas (`url(#id)`, `href="#id"`),
 * para que marcadores y gradientes sigan funcionando sin chocar con la app ni con otras figuras.
 */
function namespaceLessonSvgIds(svg) {
  const prefix = `lesson-fig-${++lessonSvgCounter}-`;
  const renamed = new Map();
  svg.querySelectorAll('[id]').forEach((el) => {
    renamed.set(el.id, prefix + el.id);
    el.id = prefix + el.id;
  });
  if (svg.id) svg.removeAttribute('id');
  if (renamed.size === 0) return;

  [svg, ...svg.querySelectorAll('*')].forEach((el) => {
    [...el.attributes].forEach((attr) => {
      if (attr.name === 'id') return;
      let value = attr.value;
      if (attr.name === 'href' || attr.name === 'xlink:href') {
        if (value.startsWith('#') && renamed.has(value.slice(1))) value = '#' + renamed.get(value.slice(1));
      } else if (value.includes('url(')) {
        value = value.replace(/url\(\s*(['"]?)#([^'")\s]+)\1\s*\)/g, (whole, quote, id) =>
          renamed.has(id) ? `url(#${renamed.get(id)})` : whole
        );
      }
      if (value !== attr.value) el.setAttribute(attr.name, value);
    });
  });
}

/**
 * Renderiza Markdown de una clase dentro de `container`. Todo el HTML pasa por DOMPurify;
 * si falta `marked` o `DOMPurify` se muestra texto plano escapado, nunca HTML.
 */
async function renderLessonMarkdown(markdown, container) {
  const body = extractFencedBlock(extractFencedBlock(markdown, 'cards-fsrs').rest, 'slides').rest;

  if (!lessonLibsReady()) {
    renderLessonPlainText(body, container);
    return;
  }

  let html;
  try {
    html = getLessonMarkdownParser().parse(body);
  } catch (err) {
    console.warn("Markdown render error:", err);
    renderLessonPlainText(body, container);
    return;
  }

  container.innerHTML = window.DOMPurify.sanitize(html, LESSON_SANITIZE_CONFIG);

  // Los id del contenido no deben pisar los de la aplicación ni los de otra figura.
  container.querySelectorAll('[id]').forEach((el) => {
    if (!el.closest('svg')) el.removeAttribute('id');
  });
  container.querySelectorAll('svg').forEach(namespaceLessonSvgIds);
  container.querySelectorAll('a[href]').forEach((link) => {
    const href = link.getAttribute('href') || '';
    if (/^https?:/i.test(href)) {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    } else if (href.startsWith('#')) {
      // Los anclajes internos no existen en el visor (los id del contenido se quitan).
      link.removeAttribute('href');
    }
  });
  decorateLessonCallouts(container);

  const diagrams = container.querySelectorAll('.mermaid');
  if (diagrams.length > 0) {
    await ensureMermaidLoaded();
    const conectados = Array.from(diagrams).filter((el) => el.isConnected);
    if (window.mermaid && conectados.length > 0) {
      try {
        const rendering = mermaid.run({ nodes: conectados });
        if (rendering && typeof rendering.catch === 'function') {
          rendering.catch((me) => console.warn("Mermaid render error:", me));
        }
      } catch (me) {
        console.warn("Mermaid render error:", me);
      }
    }
  }
}

function renderLessonFlashcards(flashcards) {
  const cardsListDiv = document.getElementById('viewer-cards-list');
  cardsListDiv.replaceChildren();

  if (!flashcards || flashcards.length === 0) {
    const empty = document.createElement('p');
    empty.className = "text-xs text-slate-500 col-span-2";
    empty.textContent = "No se detectaron flashcards delimitadas en esta clase.";
    cardsListDiv.appendChild(empty);
    return;
  }

  flashcards.forEach((card, cIdx) => {
    const number = document.createElement('span');
    number.className = "w-4 h-4 shrink-0 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center text-xs";
    number.textContent = String(cIdx + 1);
    const question = document.createElement('span');
    question.textContent = card.pregunta;
    const header = document.createElement('div');
    header.className = "text-xs font-bold text-sky-400 flex items-center gap-1";
    header.append(number, question);

    const answer = document.createElement('p');
    answer.className = "text-xs text-slate-300 pl-5";
    answer.textContent = card.respuesta;

    const cardEl = document.createElement('div');
    cardEl.className = "au-tarjeta au-tarjeta--hundida";
    cardEl.append(header, answer);
    cardsListDiv.appendChild(cardEl);
  });
}

function switchLessonView(view) {
  const hasSlides = state.lessonSlides.length > 0;
  state.lessonView = (view === 'markdown' || (view === 'slides' && hasSlides)) ? view : 'preview';

  ['preview', 'markdown', 'slides'].forEach((name) => {
    const tab = document.getElementById(`viewer-tab-${name}`);
    tab.setAttribute('aria-selected', String(name === state.lessonView));
  });
  document.getElementById('viewer-tab-slides').classList.toggle('hidden', !hasSlides);

  const isPreview = state.lessonView === 'preview';
  document.getElementById('viewer-content-body').classList.toggle('hidden', !isPreview);
  document.getElementById('viewer-cards-section').classList.toggle('hidden', !isPreview);
  document.getElementById('viewer-markdown-panel').classList.toggle('hidden', state.lessonView !== 'markdown');
  document.getElementById('viewer-slides').classList.toggle('hidden', state.lessonView !== 'slides');

  if (state.lessonView === 'slides') renderLessonSlides();
}

function renderLessonSlides() {
  const total = state.lessonSlides.length;
  if (total === 0) return;
  state.lessonSlideIndex = Math.min(Math.max(state.lessonSlideIndex, 0), total - 1);

  renderLessonMarkdown(state.lessonSlides[state.lessonSlideIndex], document.getElementById('viewer-slide-stage'));
  document.getElementById('viewer-slide-counter').textContent = `${state.lessonSlideIndex + 1} / ${total}`;
  document.getElementById('viewer-slide-prev').disabled = state.lessonSlideIndex === 0;
  document.getElementById('viewer-slide-next').disabled = state.lessonSlideIndex === total - 1;
}

function nextLessonSlide() {
  if (state.lessonSlideIndex >= state.lessonSlides.length - 1) return;
  state.lessonSlideIndex += 1;
  renderLessonSlides();
}

function prevLessonSlide() {
  if (state.lessonSlideIndex <= 0) return;
  state.lessonSlideIndex -= 1;
  renderLessonSlides();
}

document.addEventListener('keydown', (e) => {
  if (state.lessonView !== 'slides') return;
  if (!Au.modal.abierto('modal-view-lesson')) return;
  if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
  if (e.target instanceof Element && e.target.closest('input, textarea, select, [contenteditable]')) return;
  if (e.key === 'ArrowRight') {
    e.preventDefault();
    nextLessonSlide();
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault();
    prevLessonSlide();
  }
});

function copyLessonMarkdown() {
  if (!state.currentLesson) return;
  const status = document.getElementById('viewer-copy-status');

  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    alert("No se pudo copiar automáticamente. Selecciona el texto y presiona Ctrl+C.");
    return;
  }
  navigator.clipboard.writeText(state.currentLesson.contenido_markdown || '').then(() => {
    status.textContent = "✔ Markdown copiado al portapapeles.";
    setTimeout(() => { status.textContent = ''; }, 4000);
  }).catch(() => {
    alert("No se pudo copiar automáticamente. Selecciona el texto y presiona Ctrl+C.");
  });
}

function viewLessonModal(topicId) {
  if (!state.activeRoadmap) return;

  let targetTopic = null;
  let targetModule = null;
  for (const m of state.activeRoadmap.modulos) {
    for (const t of m.temas) {
      if (t.id === topicId) {
        targetTopic = t;
        targetModule = m;
        break;
      }
    }
    if (targetTopic) break;
  }

  if (!targetTopic || !targetTopic.clase) {
    alert("Este tema aún no tiene una clase generada o importada.");
    return;
  }

  const lesson = targetTopic.clase;
  const markdown = lesson.contenido_markdown || '';
  state.currentLesson = lesson;
  state.lessonSlides = splitLessonSlides(extractFencedBlock(markdown, 'slides').content);
  state.lessonSlideIndex = 0;

  document.getElementById('viewer-class-title').textContent = lesson.titulo;
  document.getElementById('viewer-class-breadcrumbs').textContent = `${state.activeRoadmap.titulo} > ${targetModule.titulo} > ${targetTopic.titulo}`;
  document.getElementById('viewer-vault-status').textContent = lesson.vault_path ? `Mis notas: ${lesson.vault_path}` : "Mis notas: No sincronizado";
  document.getElementById('viewer-markdown-source').textContent = markdown;
  document.getElementById('viewer-copy-status').textContent = '';
  renderLessonFlashcards(lesson.flashcards_json);
  loadLessonVersions(topicId);

  // El modal se muestra antes de renderizar: Mermaid mide mal dentro de un contenedor oculto.
  Au.modal.abrir('modal-view-lesson');
  switchLessonView('preview');
  renderLessonMarkdown(markdown, document.getElementById('viewer-content-body'));
}

function closeViewLessonModal() {
  Au.modal.cerrar('modal-view-lesson');
}

async function exportCurrentLessonToFsrs() {
  if (!state.currentLesson) return;
  const btn = document.getElementById('btn-export-lesson-fsrs');
  btn.disabled = true;
  btn.textContent = "Inyectando...";

  try {
    const res = await fetch(`/api/roadmap/lessons/${state.currentLesson.id}/export-fsrs`, { method: 'POST' });
    if (!res.ok) throw new Error("Error exportando a FSRS");
    const data = await res.json();
    alert(`🎉 ¡${data.cards_exported} tarjetas añadidas exitosamente a tu mazo de repaso diario!`);
  } catch (err) {
    alert("Error al exportar a FSRS: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "✔ Enviar a Flashcards";
  }
}

async function exportCurrentLessonToVault() {
  if (!state.currentLesson) return;
  const btn = document.getElementById('btn-export-lesson-vault');
  btn.disabled = true;
  btn.textContent = "Guardando...";

  try {
    const res = await fetch(`/api/roadmap/lessons/${state.currentLesson.id}/export-vault`, { method: 'POST' });
    if (!res.ok) throw new Error("Error exportando a Mis notas");
    const data = await res.json();
    document.getElementById('viewer-vault-status').textContent = `Mis notas: ${data.vault_path}`;
    const respaldo = data.backup_path ? `\n\n⚠ En el vault había una nota distinta de la que escribió el sistema; se guardó una copia en:\n${data.backup_path}` : '';
    alert(`🎉 ¡Apunte canónico guardado con éxito en Mis notas!\n\nRuta: ${data.vault_path}${respaldo}`);
  } catch (err) {
    alert("Error al guardar en Mis notas: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "📝 Guardar en Mis notas";
  }
}

// --- VERSIONES ANTERIORES DE LA CLASE ---

let lessonVersionsRequestSeq = 0;

async function loadLessonVersions(topicId) {
  const btn = document.getElementById('btn-restore-lesson-version');
  if (!btn) return;
  const pedido = ++lessonVersionsRequestSeq;
  btn.classList.add('hidden');
  state.lessonVersions = [];
  state.lessonVersionsTopicId = topicId;
  try {
    const res = await fetch(`/api/roadmap/topics/${topicId}/lesson-versions`);
    if (!res.ok || pedido !== lessonVersionsRequestSeq) return;
    const versiones = await res.json();
    if (pedido !== lessonVersionsRequestSeq) return;
    state.lessonVersions = versiones;
    const n = versiones.length;
    btn.textContent = `🕘 Restaurar versión anterior (${n})`;
    btn.classList.toggle('hidden', n === 0);
  } catch (err) {
    console.warn("No se pudieron cargar las versiones de la clase:", err);
  }
}

async function restorePreviousLessonVersion() {
  const version = (state.lessonVersions || [])[0];
  const topicId = state.lessonVersionsTopicId;
  if (!version) return;
  if (!confirm(`¿Restaurar la versión anterior de esta clase?\n\n"${version.titulo}" (guardada el ${version.fecha_version}).\n\nLa clase que ves ahora queda guardada como versión anterior.`)) return;
  const btn = document.getElementById('btn-restore-lesson-version');
  btn.disabled = true;
  try {
    const res = await fetch(`/api/roadmap/lesson-versions/${version.id}/restore`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "No se pudo restaurar la versión");
    }
    await loadRoadmapDetails(state.activeRoadmapId);
    viewLessonModal(topicId);
  } catch (err) {
    alert("Error al restaurar la versión: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

// --- MODAL COMPARADOR DE PDFS (GAP ANALYSIS) ---

function openPdfGapModal() {
  if (!state.activeRoadmapId) {
    alert("Selecciona o crea una ruta primero.");
    return;
  }
  document.getElementById('pdf-gap-file-input').value = '';
  document.getElementById('pdf-gap-results').classList.add('hidden');
  document.getElementById('btn-merge-gap-topics').classList.add('hidden');
  Au.modal.abrir('modal-pdf-gap');
}

function closePdfGapModal() {
  Au.modal.cerrar('modal-pdf-gap');
}

async function submitPdfGapAnalysis() {
  const fileInput = document.getElementById('pdf-gap-file-input');
  if (!fileInput.files || fileInput.files.length === 0) {
    alert("Por favor selecciona un archivo PDF de temario o blueprint.");
    return;
  }

  const file = fileInput.files[0];
  const btn = document.getElementById('btn-run-gap-analysis');
  btn.disabled = true;
  btn.innerHTML = '<span>⚡</span> Analizando syllabus con Gemini...';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/compare-pdf`, {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Error procesando PDF");
    }

    const data = await res.json();
    state.pdfGapResult = data;

    // Renderizar resultados
    document.getElementById('gap-summary-text').textContent = data.summary;

    const matchedList = document.getElementById('gap-matched-list');
    matchedList.innerHTML = '';
    data.matched_topics.forEach(m => {
      const li = document.createElement('li');
      li.textContent = m;
      matchedList.appendChild(li);
    });
    if (data.matched_topics.length === 0) {
      matchedList.innerHTML = '<li class="text-slate-500 italic">No se detectaron coincidencias exactas.</li>';
    }

    const missingList = document.getElementById('gap-missing-list');
    missingList.innerHTML = '';
    data.gap_topics.forEach(g => {
      const li = document.createElement('li');
      li.innerHTML = `<strong>${escapeHtml(g.titulo)}</strong>: ${escapeHtml(g.descripcion || 'Sin descripción')}`;
      missingList.appendChild(li);
    });
    if (data.gap_topics.length === 0) {
      missingList.innerHTML = '<li class="text-emerald-400 italic">¡Tu ruta actual cubre el 100% del temario del PDF!</li>';
    }

    document.getElementById('pdf-gap-results').classList.remove('hidden');

    if (data.gap_topics && data.gap_topics.length > 0) {
      document.getElementById('btn-merge-gap-topics').classList.remove('hidden');
      document.getElementById('btn-merge-gap-topics').textContent = `Incorporar ${data.gap_topics.length} temas a la ruta (Merge)`;
    }
  } catch (err) {
    alert("Error en el Gap Analysis: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>✨</span> Iniciar Gap Analysis con IA';
  }
}

async function mergeGapTopicsToActiveRoadmap() {
  if (!state.pdfGapResult || !state.pdfGapResult.gap_topics || state.pdfGapResult.gap_topics.length === 0) return;

  const btn = document.getElementById('btn-merge-gap-topics');
  btn.disabled = true;
  btn.textContent = "Fusionando temas...";

  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gap_topics: state.pdfGapResult.gap_topics,
        default_module_title: "Especialización & Brechas Detectadas (Syllabus PDF)"
      })
    });

    if (!res.ok) throw new Error("Error fusionando brechas");
    const data = await res.json();
    closePdfGapModal();
    await loadRoadmapDetails(state.activeRoadmapId);
    alert(`🎉 ¡${data.inserted_topics} nuevos temas incorporados exitosamente a tu ruta!`);
  } catch (err) {
    alert("Error al incorporar temas: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

// --- SUGERENCIA DINÁMICA DE TEMAS EVOLUTIVOS (i+1) ---

async function suggestNextRoadmapTopics() {
  if (!state.activeRoadmapId) {
    alert("Selecciona una ruta primero.");
    return;
  }

  try {
    const res = await fetch(`/api/roadmap/${state.activeRoadmapId}/suggest-next`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error("Error obteniendo sugerencias");
    const data = await res.json();

    if (!data.suggested_topics || data.suggested_topics.length === 0) {
      alert("Aún no tienes temas dominados suficientes para proyectar el siguiente nivel. ¡Completa algunas clases primero!");
      return;
    }

    const topicsText = data.suggested_topics.map(t => `• ${t.titulo}: ${t.descripcion || ''}`).join('\n');
    const confirmed = confirm(
      `✨ Sugerencias de Evolución Curricular (Nivel i+1):\n\n${data.reasoning}\n\n${topicsText}\n\n¿Deseas incorporar estos temas avanzados a tu ruta de aprendizaje activa?`
    );

    if (confirmed) {
      const mergeRes = await fetch(`/api/roadmap/${state.activeRoadmapId}/merge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gap_topics: data.suggested_topics,
          default_module_title: "Especialización Avanzada & Evolución (i+1)"
        })
      });
      if (mergeRes.ok) {
        await loadRoadmapDetails(state.activeRoadmapId);
        alert("🎉 ¡Temas de vanguardia incorporados a tu ruta!");
      }
    }
  } catch (err) {
    alert("Error al sugerir temas: " + err.message);
  }
}

// Controles de Zoom para Grafo DAG
let currentDagZoom = 1.0;
function zoomDag(factor) {
  currentDagZoom = Math.max(0.4, Math.min(2.5, currentDagZoom * factor));
  const svg = document.querySelector('#dag-diagram svg');
  if (svg) {
    svg.style.transform = `scale(${currentDagZoom})`;
    svg.style.transformOrigin = 'top left';
    svg.style.transition = 'transform 0.15s ease';
  }
}

function resetDagZoom() {
  currentDagZoom = 1.0;
  const svg = document.querySelector('#dag-diagram svg');
  if (svg) {
    svg.style.transform = 'scale(1)';
    svg.style.transition = 'transform 0.15s ease';
  }
}

function updateDagInteractiveMap(roadmapId) {
  if (!roadmapId) return;
  const frame = document.getElementById('dag-interactive-frame');
  if (!frame) return;
  frame.src = `/api/roadmap/${encodeURIComponent(roadmapId)}/interactive-map?present=1&theme=dark&t=${Date.now()}`;
}

window.addEventListener('message', (ev) => {
  // Solo el mapa de la propia app (mismo origen) puede seleccionar un tema
  if (ev.origin !== window.location.origin || !ev.data || ev.data.type !== 'dag-select-topic') return;
  const topicId = Number(ev.data.topicId);
  if (topicId && typeof selectDagNode === 'function') {
    selectDagNode(topicId);
  }
});

function toggleDagFullscreen() {
  const diag = document.getElementById('dag-canvas-card') || document.getElementById('dag-diagram');
  const btn = document.getElementById('btn-dag-fullscreen');
  if (!diag) return;
  const isFull = diag.classList.toggle('dag-fullscreen');
  if (btn) {
    btn.innerHTML = isFull 
      ? '<span>✕</span> <span class="hidden sm:inline">Cerrar</span>' 
      : '<span>⤢</span> <span class="hidden sm:inline">Pantalla Completa</span>';
    btn.title = isFull ? 'Cerrar pantalla completa (Esc)' : 'Expandir pantalla completa';
  }
  showToast(isFull ? 'Modo pantalla completa activado (Esc para salir)' : 'Pantalla completa cerrada', 'info');
}

// Toggle masivo de módulos en Árbol de Rutas
let allRoadmapModulesExpanded = true;
function toggleAllRoadmapModules() {
  const bodies = document.querySelectorAll('#roadmap-tree-container .module-body');
  const arrows = document.querySelectorAll('#roadmap-tree-container .module-arrow');
  allRoadmapModulesExpanded = !allRoadmapModulesExpanded;
  bodies.forEach(b => {
    if (allRoadmapModulesExpanded) {
      b.classList.remove('hidden');
    } else {
      b.classList.add('hidden');
    }
  });
  arrows.forEach(a => {
    a.textContent = allRoadmapModulesExpanded ? '▼' : '▶';
  });
  showToast(allRoadmapModulesExpanded ? 'Todos los módulos expandidos' : 'Todos los módulos colapsados', 'info');
}

function toggleSingleModule(headerEl) {
  const modDiv = headerEl.closest('.roadmap-module-card');
  if (!modDiv) return;
  const body = modDiv.querySelector('.module-body');
  const arrow = modDiv.querySelector('.module-arrow');
  if (body) {
    const isHidden = body.classList.toggle('hidden');
    if (arrow) arrow.textContent = isHidden ? '▶' : '▼';
  }
}

// Dropzone interactivo de PDFs para Gap Analysis
function handleGapPdfSelected(input) {
  const file = input && input.files && input.files[0];
  const badge = document.getElementById('pdf-selected-file-badge');
  const nameEl = document.getElementById('pdf-selected-file-name');
  const dropLabel = document.getElementById('pdf-drop-label');
  const dropzone = document.getElementById('pdf-gap-dropzone');
  if (file) {
    if (badge) badge.classList.remove('hidden');
    if (nameEl) nameEl.textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
    if (dropLabel) dropLabel.textContent = 'Archivo seleccionado para análisis:';
    if (dropzone) dropzone.classList.add('border-emerald-500/80', 'bg-emerald-950/20');
  }
}

function clearSelectedGapPdf() {
  const input = document.getElementById('pdf-gap-file-input');
  if (input) input.value = '';
  const badge = document.getElementById('pdf-selected-file-badge');
  const dropLabel = document.getElementById('pdf-drop-label');
  const dropzone = document.getElementById('pdf-gap-dropzone');
  if (badge) badge.classList.add('hidden');
  if (dropLabel) dropLabel.textContent = 'Arrastrá y soltá el syllabus o temario PDF aquí';
  if (dropzone) {
    dropzone.classList.remove('border-emerald-500/80', 'bg-emerald-950/20');
  }
}

function initPdfGapDropzone() {
  const dropzone = document.getElementById('pdf-gap-dropzone');
  const fileInput = document.getElementById('pdf-gap-file-input');
  if (!dropzone || !fileInput) return;

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('border-sky-400', 'bg-sky-950/30');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('border-sky-400', 'bg-sky-950/30');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt && dt.files;
    if (files && files.length > 0 && files[0].name.toLowerCase().endsWith('.pdf')) {
      fileInput.files = files;
      handleGapPdfSelected(fileInput);
    } else {
      showToast('Por favor soltá un archivo en formato .pdf', 'warning');
    }
  });
}


