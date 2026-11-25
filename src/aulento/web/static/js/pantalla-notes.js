// --- ACCIONES DELEGADAS DE MIS NOTAS (072 T5) ---
[
  ['guardar-ubicacion-notas', () => saveNotesLocation()],
  ['restablecer-ubicacion-notas', () => resetNotesLocation()],
  ['buscar-notas', (el) => onNotesSearchInput(el.value)],
  ['seleccionar-nota', (el, datos) => selectNote(datos.id)],
  ['modal-copiar-resumen-semanal', () => copyWeeklyDigestMarkdown()],
  ['modal-guardar-resumen-semanal-vault', () => saveWeeklyDigestToVault()],
  ['modal-generar-apunte-curso', (el, datos, ev) => handleGenerateCourseNote(ev)],
  ['modal-guardar-apunte-curso-directo', () => handleSaveCourseNoteDirect()],
  ['modal-copiar-apunte-curso', () => copyCourseNoteMarkdown()],
  ['modal-guardar-apunte-curso-vault', () => handleSaveCourseNoteDirect()],
  ['modal-elegir-material-apunte', () => handleNoteMaterialSelect()],
  ['modal-previsualizar-apunte-material', () => previewMaterialNote()],
  ['modal-guardar-apunte-material-vault', () => saveMaterialNoteToVault()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

// --- FEATURE 008: WEEKLY DIGEST & APUNTES SOP ---
let currentWeeklyDigestData = null;

async function openWeeklyDigestModal() {
  const modal = document.getElementById('weekly-digest-modal');
  const metricsEl = document.getElementById('weekly-digest-metrics');
  const contentEl = document.getElementById('weekly-digest-content');
  const pathEl = document.getElementById('weekly-digest-path');
  const statusEl = document.getElementById('weekly-digest-status');

  Au.modal.abrir('weekly-digest-modal');
  contentEl.value = 'Compilando métricas y generando resumen...';
  metricsEl.innerHTML = '';
  statusEl.textContent = 'Cargando...';

  try {
    const res = await fetch('/api/vault/digest/weekly');
    if (res.ok) {
      const data = await res.json();
      currentWeeklyDigestData = data;
      contentEl.value = data.content;
      pathEl.textContent = data.relative_path;
      statusEl.textContent = `Semana: ${data.week_label}`;

      const m = data.metrics || {};
      metricsEl.innerHTML = `
        <div class="p-2.5 bg-slate-950 border border-slate-800 rounded-xl">
          <div class="text-slate-400">Racha FSRS</div>
          <div class="text-base font-bold text-amber-400">${Au.icono('racha')} ${m.streak || 0} días</div>
        </div>
        <div class="p-2.5 bg-slate-950 border border-slate-800 rounded-xl">
          <div class="text-slate-400">Retención</div>
          <div class="text-base font-bold text-emerald-400">${Au.icono('objetivo')} ${(m.retention || 0).toFixed(1)}%</div>
        </div>
        <div class="p-2.5 bg-slate-950 border border-slate-800 rounded-xl">
          <div class="text-slate-400">Cursos Activos</div>
          <div class="text-base font-bold text-sky-400">${Au.icono('cursos')} ${m.courses_count || 0}</div>
        </div>
        <div class="p-2.5 bg-slate-950 border border-slate-800 rounded-xl">
          <div class="text-slate-400">Libros Monitoreados</div>
          <div class="text-base font-bold text-purple-400">${Au.icono('lectura')} ${m.books_count || 0}</div>
        </div>
      `;
    } else {
      const err = await res.json();
      contentEl.value = `Error al generar digest: ${err.detail || 'Error desconocido'}`;
    }
  } catch (err) {
    console.error("Error al cargar Weekly Digest:", err);
    contentEl.value = 'Error de conexión al cargar Weekly Digest.';
  }
}

function closeWeeklyDigestModal() {
  Au.modal.cerrar('weekly-digest-modal');
}

function copyWeeklyDigestMarkdown() {
  const content = document.getElementById('weekly-digest-content').value;
  if (!content) return;
  navigator.clipboard.writeText(content).then(() => {
    alert("Markdown copiado al portapapeles.");
  }).catch(() => {
    prompt("Copia el texto:", content);
  });
}

async function saveWeeklyDigestToVault() {
  const btn = document.getElementById('btn-save-weekly-vault');
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = Au.icono('cargando') + ' Guardando...';

  try {
    const weekLabel = currentWeeklyDigestData ? currentWeeklyDigestData.week_label : null;
    const url = weekLabel ? `/api/vault/digest/weekly/save?week_label=${encodeURIComponent(weekLabel)}` : '/api/vault/digest/weekly/save';
    const res = await fetch(url, { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      alert(`Resumen Semanal guardado exitosamente en Mis notas:\n${data.saved_path}`);
    } else {
      const err = await res.json();
      alert(`Error al guardar en Mis notas: ${err.detail || 'Fallo desconocido'}`);
    }
  } catch (err) {
    console.error("Error al guardar Weekly Digest:", err);
    alert("Error de red al guardar en Mis notas.");
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

function openCourseNoteModal(courseId) {
  let foundCourse = null;
  for (const p of state.platforms) {
    const c = p.cursos.find(x => x.id === courseId);
    if (c) {
      foundCourse = c;
      break;
    }
  }
  const courseName = foundCourse ? foundCourse.nombre_curso : `Curso #${courseId}`;
  document.getElementById('course-note-id').value = courseId;
  document.getElementById('course-note-coursename').textContent = `Curso: ${courseName}`;
  document.getElementById('course-note-topic').value = '';
  document.getElementById('course-note-tldr').value = '';
  document.getElementById('course-note-concepts').value = '';
  document.getElementById('course-note-code').value = '';
  document.getElementById('course-note-feedback').textContent = '';
  document.getElementById('course-note-preview-container').classList.add('hidden');
  Au.modal.abrir('course-note-modal');
}

function closeCourseNoteModal() {
  Au.modal.cerrar('course-note-modal');
}

function getCourseNotePayload() {
  const courseId = parseInt(document.getElementById('course-note-id').value, 10);
  const topic = document.getElementById('course-note-topic').value.trim();
  const tldr = document.getElementById('course-note-tldr').value.trim() || null;
  const conceptsRaw = document.getElementById('course-note-concepts').value.trim();
  const key_concepts = conceptsRaw ? conceptsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
  const code_example = document.getElementById('course-note-code').value.trim() || null;

  return {
    course_id: courseId,
    topic: topic,
    tldr: tldr,
    key_concepts: key_concepts,
    code_example: code_example,
  };
}

async function handleGenerateCourseNote(e) {
  e.preventDefault();
  const payload = getCourseNotePayload();
  if (!payload.topic) {
    alert("Ingresa un tema o título para la nota.");
    return;
  }

  const container = document.getElementById('course-note-preview-container');
  const previewText = document.getElementById('course-note-preview-text');
  const pathEl = document.getElementById('course-note-path');
  const feedbackEl = document.getElementById('course-note-feedback');

  container.classList.remove('hidden');
  previewText.value = 'Generando plantilla estructurada SOP...';
  feedbackEl.textContent = '';

  try {
    const res = await fetch('/api/vault/notes/course-template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const data = await res.json();
      previewText.value = data.content;
      pathEl.textContent = data.relative_path;
      feedbackEl.textContent = 'Plantilla generada (Previsualización)';
    } else {
      const err = await res.json();
      previewText.value = `Error: ${err.detail || 'No se pudo generar'}`;
    }
  } catch (err) {
    console.error("Error al generar plantilla:", err);
    previewText.value = 'Error de red al generar plantilla.';
  }
}

async function handleSaveCourseNoteDirect() {
  const payload = getCourseNotePayload();
  if (!payload.topic) {
    alert("Ingresa un tema o título para la nota.");
    return;
  }

  const container = document.getElementById('course-note-preview-container');
  const previewText = document.getElementById('course-note-preview-text');
  const pathEl = document.getElementById('course-note-path');
  const feedbackEl = document.getElementById('course-note-feedback');

  container.classList.remove('hidden');
  feedbackEl.textContent = 'Guardando en Mis notas...';

  try {
    const res = await fetch('/api/vault/notes/course-template?save_to_vault=true', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const data = await res.json();
      previewText.value = data.content;
      pathEl.textContent = data.relative_path;
      feedbackEl.innerHTML = `${Au.icono('ok')} Guardado exitoso en 04 Knowledge/Cursos/`;

      // Auto-vincular la nota en el curso si aún no tiene ruta_obsidian
      if (data.relative_path && payload.course_id) {
        try {
          await fetch(`/api/hub/courses/${payload.course_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ruta_obsidian: data.relative_path }),
          });
          await loadPlatforms();
        } catch (linkErr) {
          console.warn("No se pudo autovincular la nota al curso:", linkErr);
        }
      }

      alert(`Apunte SOP creado y guardado físicamente en:\n${data.saved_path || data.relative_path}\n\nVinculado automáticamente a la tarjeta del curso.`);
    } else {
      const err = await res.json();
      feedbackEl.textContent = `Error: ${err.detail || 'Fallo al guardar'}`;
      alert(`Error al guardar en Mis notas: ${err.detail || 'Fallo al guardar'}`);
    }
  } catch (err) {
    console.error("Error al guardar nota en vault:", err);
    alert("Error de red al guardar en Mis notas.");
  }
}

function copyCourseNoteMarkdown() {
  const content = document.getElementById('course-note-preview-text').value;
  if (!content) return;
  navigator.clipboard.writeText(content).then(() => {
    alert("Apunte copiado al portapapeles.");
  }).catch(() => {
    prompt("Copia el texto:", content);
  });
}

// --- GENERADOR DE APUNTES SOP DESDE UN MATERIAL ---
async function openMaterialNoteModal() {
  Au.modal.abrir('material-note-modal');
  await Promise.all([loadNoteCoursesForSelect(), loadMaterialNoteOptions()]);
}

function closeMaterialNoteModal() {
  Au.modal.cerrar('material-note-modal');
}

async function loadNoteCoursesForSelect() {
  const select = document.getElementById('material-note-course-select');
  if (!select) return;
  select.innerHTML = '<option value="">Elegir automáticamente por el nombre del material</option>';
  try {
    const res = await fetch('/api/hub/courses');
    if (res.ok) {
      const courses = await res.json();
      courses.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.nombre_curso} (${c.estado})`;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("No se pudieron cargar los cursos para el apunte:", e);
  }
}

// Los materiales de la cuenta para elegir de cuál sale el apunte; el nombre va como texto, no como HTML
async function loadMaterialNoteOptions() {
  const select = document.getElementById('material-note-material-select');
  const statusInfo = document.getElementById('material-note-status-info');
  if (!select) return;

  select.innerHTML = '<option value="">Cargando tus materiales...</option>';
  try {
    const res = await fetch('/api/vault/notes/materials');
    if (!res.ok) throw new Error();
    const materiales = await res.json();
    if (materiales.length === 0) {
      select.innerHTML = '<option value="">Todavía no subiste materiales</option>';
      statusInfo.textContent = "Subí un PDF, Markdown o texto en «Mis materiales» y volvé acá.";
      return;
    }
    select.innerHTML = '<option value="">-- Elegí un material --</option>';
    materiales.forEach(m => {
      const opt = document.createElement('option');
      opt.value = String(m.id);
      opt.textContent = m.name;
      select.appendChild(opt);
    });
    statusInfo.textContent = `${materiales.length} material${materiales.length === 1 ? '' : 'es'} para elegir.`;
  } catch (err) {
    select.innerHTML = '<option value="">No se pudieron cargar tus materiales</option>';
    statusInfo.textContent = "No se pudieron cargar tus materiales. Probá de nuevo en un rato.";
  }
}

// Propone como título el nombre del material sin la extensión
function handleNoteMaterialSelect() {
  const select = document.getElementById('material-note-material-select');
  const topicInput = document.getElementById('material-note-topic-input');
  if (!select || !select.value || !topicInput) return;
  const nombre = select.options[select.selectedIndex].textContent;
  topicInput.value = nombre.replace(/\.(pdf|md|markdown|txt)$/i, '').trim();
}

// El pedido del apunte con lo que eligió el usuario, o null si falta el material
function materialNotePayload() {
  const select = document.getElementById('material-note-material-select');
  if (!select || !select.value) return null;
  const courseSelect = document.getElementById('material-note-course-select');
  const topic = document.getElementById('material-note-topic-input').value.trim();
  const customNotes = document.getElementById('material-note-custom-notes').value.trim();
  return {
    material_id: Number(select.value),
    course_id: courseSelect && courseSelect.value ? parseInt(courseSelect.value) : null,
    topic: topic || null,
    custom_notes: customNotes || null,
  };
}

async function previewMaterialNote() {
  const previewBox = document.getElementById('material-note-preview-container');
  const pathBadge = document.getElementById('material-note-path-badge');
  const statusInfo = document.getElementById('material-note-status-info');
  const payload = materialNotePayload();
  if (!payload) {
    alert("Elegí un material.");
    return;
  }

  statusInfo.textContent = "Armando el apunte...";
  previewBox.textContent = "Generando el resumen, los enlaces y los diagramas...";

  try {
    const res = await fetch('/api/vault/notes/from-material', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, save_to_vault: false })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "No se pudo armar el apunte");

    previewBox.textContent = data.content;
    pathBadge.textContent = data.relative_path;
    statusInfo.innerHTML = `${Au.icono('ok')} Apunte listo para revisar: "${Au.escapar(data.title)}" en el curso "${Au.escapar(data.course)}".`;
  } catch (e) {
    previewBox.textContent = "Error: " + e.message;
    statusInfo.textContent = "No se pudo armar el apunte.";
  }
}

async function saveMaterialNoteToVault() {
  const previewBox = document.getElementById('material-note-preview-container');
  const pathBadge = document.getElementById('material-note-path-badge');
  const statusInfo = document.getElementById('material-note-status-info');
  const payload = materialNotePayload();
  if (!payload) {
    alert("Elegí un material.");
    return;
  }

  statusInfo.textContent = "Guardando el apunte en Mis notas (04 Knowledge/Cursos/)...";

  try {
    const res = await fetch('/api/vault/notes/from-material?save_to_vault=true', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, save_to_vault: true })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "No se pudo guardar el apunte");

    previewBox.textContent = data.content;
    pathBadge.textContent = data.saved_path || data.relative_path;
    statusInfo.innerHTML = `${Au.icono('ok')} Apunte guardado en: ${Au.escapar(data.saved_path || data.relative_path)}`;
    alert(`¡Apunte guardado en Mis notas!\n\nRuta: ${data.saved_path || data.relative_path}\nCurso: ${data.course}\nPlataforma: ${data.platform}`);
  } catch (e) {
    statusInfo.textContent = "Error al guardar el apunte: " + e.message;
    alert("Error al guardar en Mis notas: " + e.message);
  }
}

// --- MIS NOTAS (057) ---

function renderNoteMarkdown(text) {
  if (!text) return '';
  // 1. Escapar TODO primero: previene cualquier ejecución de HTML o scripts
  let str = escapeHtml(text);

  // 2 y 3. El código se aparta en marcadores: el formato de abajo no debe tocar su contenido
  const apartados = [];
  const apartar = (html) => `\u0000${apartados.push(html) - 1}\u0000`;
  str = str.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/gi, (match, lang, code) => apartar(
    `<pre class="p-3 my-2.5 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-sky-300 overflow-x-auto"><code>${code.trim()}</code></pre>`
  ));
  str = str.replace(/`([^`]+)`/g, (match, code) => apartar(
    `<code class="bg-slate-900 text-sky-300 border border-slate-800/80 px-1.5 py-0.5 rounded text-xs font-mono">${code}</code>`
  ));

  // 4. Encabezados
  str = str.replace(/^### (.*$)/gim, '<h4 class="text-sm font-bold text-white mt-4 mb-1.5 flex items-center gap-1.5"><span class="text-sky-400">' + Au.icono('punto') + '</span> $1</h4>');
  str = str.replace(/^## (.*$)/gim, '<h3 class="text-base font-bold text-sky-400 mt-4 mb-2 pb-1 border-b border-slate-800/80">$1</h3>');
  str = str.replace(/^# (.*$)/gim, '<h2 class="text-lg font-extrabold text-white mt-3 mb-2">$1</h2>');

  // 5. Negrita e itálica
  str = str.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-white">$1</strong>');
  str = str.replace(/\*([^*]+)\*/g, '<em class="italic text-slate-300">$1</em>');

  // 6. Citas / Callouts
  str = str.replace(/^>\s?(.*$)/gim, '<blockquote class="border-l-4 border-sky-500 pl-3 py-1 my-2 bg-sky-950/20 text-slate-300 italic text-xs rounded-r-lg">$1</blockquote>');

  // 7. Listas
  str = str.replace(/^[-*]\s+(.*$)/gim, '<div class="flex items-start gap-2 my-1 text-slate-300 text-xs sm:text-sm"><span class="text-sky-400 mt-1 shrink-0">•</span><span>$1</span></div>');
  str = str.replace(/^(\d+)\.\s+(.*$)/gim, '<div class="flex items-start gap-2 my-1 text-slate-300 text-xs sm:text-sm"><span class="font-bold text-sky-400 shrink-0">$1.</span><span>$2</span></div>');

  // 8. Enlaces http(s) sanitizados con sanitizeUrl
  str = str.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, url) => {
    // La URL llega escapada: se desescapa para validarla (sanitizeUrl ya la escapa para el atributo)
    const cruda = url.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
    return `<a href="${sanitizeUrl(cruda)}" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 underline">${label}</a>`;
  });

  // 9. Wikilinks estilo Obsidian [[Destino]] o [[Destino|Alias]]
  str = str.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (match, target, alias) => {
    const textToShow = alias || target;
    return `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono bg-purple-950/60 text-purple-300 border border-purple-800/50">${Au.icono('documento')} ${textToShow}</span>`;
  });

  // 10. Separación de párrafos
  str = str.replace(/\n\n/g, '<div class="h-2"></div>');

  str = str.replace(/\u0000(\d+)\u0000/g, (m, i) => apartados[Number(i)]);
  return str;
}

async function loadNotesLocation() {
  const statusEl = document.getElementById('notes-location-status');
  const inputEl = document.getElementById('notes-location-path');
  if (!statusEl || !inputEl) return;
  try {
    const res = await fetch('/api/vault/location');
    if (!res.ok) return;
    const data = await res.json();
    if (data.externo && data.ruta) {
      statusEl.innerHTML = `<span class="text-emerald-400">● Carpeta externa:</span> <span class="text-slate-200">${escapeHtml(data.ruta)}</span>${data.disponible ? '' : ' <span class="text-rose-400 font-bold">(no disponible)</span>'}`;
      inputEl.value = data.ruta;
    } else {
      statusEl.innerHTML = `<span class="text-sky-400">● Carpeta propia de la cuenta</span>`;
      inputEl.value = '';
    }
  } catch (err) {
    console.error('Error cargando ubicación de notas:', err);
  }
}

async function saveNotesLocation() {
  const inputEl = document.getElementById('notes-location-path');
  const feedbackEl = document.getElementById('notes-location-feedback');
  if (!inputEl) return;
  const ruta = inputEl.value.trim();
  if (!ruta) {
    if (feedbackEl) {
      feedbackEl.className = 'text-xs text-amber-400';
      feedbackEl.textContent = 'Escribí la ruta absoluta de la carpeta que querés usar.';
      feedbackEl.classList.remove('hidden');
    }
    return;
  }
  try {
    const res = await fetch('/api/vault/location', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ruta }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || 'No se pudo cambiar la carpeta de notas.';
      if (feedbackEl) {
        feedbackEl.className = 'text-xs text-rose-400';
        feedbackEl.textContent = msg;
        feedbackEl.classList.remove('hidden');
      }
      return;
    }
    if (feedbackEl) {
      feedbackEl.className = 'text-xs text-emerald-400';
      feedbackEl.textContent = 'Carpeta actualizada con éxito.';
      feedbackEl.classList.remove('hidden');
    }
    await loadNotesLocation();
    await loadMisNotas();
  } catch (err) {
    if (feedbackEl) {
      feedbackEl.className = 'text-xs text-rose-400';
      feedbackEl.textContent = err.message || 'Error de conexión al cambiar la carpeta.';
      feedbackEl.classList.remove('hidden');
    }
  }
}

async function resetNotesLocation() {
  const feedbackEl = document.getElementById('notes-location-feedback');
  try {
    const res = await fetch('/api/vault/location', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ruta: null }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || 'No se pudo restablecer la carpeta propia.';
      if (feedbackEl) {
        feedbackEl.className = 'text-xs text-rose-400';
        feedbackEl.textContent = msg;
        feedbackEl.classList.remove('hidden');
      }
      return;
    }
    if (feedbackEl) {
      feedbackEl.className = 'text-xs text-emerald-400';
      feedbackEl.textContent = 'Volviste a usar la carpeta propia de tu cuenta.';
      feedbackEl.classList.remove('hidden');
    }
    await loadNotesLocation();
    await loadMisNotas();
  } catch (err) {
    if (feedbackEl) {
      feedbackEl.className = 'text-xs text-rose-400';
      feedbackEl.textContent = err.message || 'Error de conexión.';
      feedbackEl.classList.remove('hidden');
    }
  }
}

async function loadMisNotas(searchQuery) {
  const listEl = document.getElementById('notes-list-container');
  if (!listEl) return;
  try {
    const url = searchQuery
      ? `/api/vault/notes?search=${encodeURIComponent(searchQuery)}`
      : '/api/vault/notes';
    const res = await fetch(url);
    if (!res.ok) {
      listEl.innerHTML = `<div class="p-6 text-center text-xs text-rose-400">Error al cargar las notas.</div>`;
      return;
    }
    const notes = await res.json();
    state.vaultNotes = notes;
    renderNotesList(notes);
    if (notes.length > 0) {
      const exists = state.selectedNoteId && notes.some(n => n.id === state.selectedNoteId);
      if (!exists) {
        selectNote(notes[0].id);
      }
    } else {
      renderEmptyNoteDetail();
    }
  } catch (err) {
    listEl.innerHTML = `<div class="p-6 text-center text-xs text-rose-400">Error de conexión: ${escapeHtml(err.message)}</div>`;
  }
}

function renderNotesList(notes) {
  const listEl = document.getElementById('notes-list-container');
  const countEl = document.getElementById('notes-count-badge');
  if (!listEl) return;
  if (countEl) countEl.textContent = `${notes.length} notas`;

  if (!notes || notes.length === 0) {
    listEl.innerHTML = Au.vacio({
      icono: 'notas',
      titulo: 'No se encontraron notas',
      texto: 'Las notas generadas por el tutor o desde materiales aparecerán acá.',
    });
    return;
  }

  const groups = {};
  for (const n of notes) {
    const folder = n.folder || 'Otras';
    if (!groups[folder]) groups[folder] = [];
    groups[folder].push(n);
  }

  let html = '';
  for (const folder of Object.keys(groups).sort()) {
    const folderNotes = groups[folder];
    html += `
      <div class="notes-folder-group mb-3">
        <div class="px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-slate-400 bg-slate-900/60 rounded-lg flex items-center justify-between mb-1">
          <span class="flex items-center gap-1.5">${Au.icono('carpeta')} <span>${Au.escapar(folder)}</span></span>
          ${Au.insignia({ texto: String(folderNotes.length), mono: true })}
        </div>
        <div class="space-y-1">`;
    for (const note of folderNotes) {
      const isSelected = note.id === state.selectedNoteId;
      html += Au.fila({
        titulo: note.title,
        detalle: note.summary || '',
        activa: isSelected,
        accion: 'seleccionar-nota',
        datos: { id: note.id },
        attrs: { 'data-note-id': note.id },
      });
    }
    html += `
        </div>
      </div>`;
  }
  listEl.innerHTML = html;
}

async function selectNote(noteId) {
  state.selectedNoteId = noteId;
  if (state.vaultNotes) {
    renderNotesList(state.vaultNotes);
  }

  const detailEl = document.getElementById('note-detail-container');
  if (!detailEl) return;

  let note = (state.vaultNotes || []).find(n => n.id === noteId);
  if (!note || !note.content) {
    try {
      const res = await fetch(`/api/vault/notes/${encodeURIComponent(noteId)}`);
      if (res.ok) {
        note = await res.json();
      }
    } catch (err) {
      console.error(err);
    }
  }

  if (!note) {
    detailEl.innerHTML = `<div class="p-8 text-center text-xs text-rose-400">No se pudo cargar la nota.</div>`;
    return;
  }

  renderNoteDetail(note);
}

function renderNoteDetail(note) {
  const detailEl = document.getElementById('note-detail-container');
  if (!detailEl) return;

  const downloadUrl = `/api/vault/notes/${encodeURIComponent(note.id)}/download`;

  detailEl.innerHTML = `
    <div class="space-y-4">
      <div class="au-cabecera au-cabecera--con-linea">
        <div class="au-cabecera__principal">
          <div class="au-cabecera__textos">
            <div class="flex items-center gap-2 text-xs text-slate-400 font-mono mb-1">
              <span>${Au.icono('carpeta')} ${Au.escapar(note.folder || '')}</span>
              <span>•</span>
              <span class="truncate">${Au.escapar(note.path || '')}</span>
            </div>
            <h2 class="au-cabecera__titulo"><span>${Au.escapar(note.title)}</span></h2>
          </div>
        </div>
        <div class="au-cabecera__acciones">
          ${Au.boton({ texto: 'Descargar nota', variante: 'primario', icono: 'descargar', href: downloadUrl, attrs: { download: true, title: 'Descargar este archivo .md' } })}
        </div>
      </div>

      ${note.tags && note.tags.length ? `
        <div class="flex flex-wrap gap-1.5">
          ${note.tags.map(t => Au.insignia({ texto: `#${t}`, mono: true })).join('')}
        </div>
      ` : ''}

      <div class="note-markdown-body au-tarjeta au-tarjeta--hundida block text-sm text-slate-200 leading-relaxed overflow-x-auto">
        ${renderNoteMarkdown(note.content || note.clean_text || '')}
      </div>
    </div>`;
}

function renderEmptyNoteDetail() {
  const detailEl = document.getElementById('note-detail-container');
  if (!detailEl) return;
  detailEl.innerHTML = Au.vacio({
    icono: 'documento',
    titulo: 'Seleccioná una nota para leerla',
    texto: 'Elegí una nota de la lista de la izquierda para ver su contenido.',
  });
}

let notesSearchTimeout = null;
function onNotesSearchInput(val) {
  clearTimeout(notesSearchTimeout);
  notesSearchTimeout = setTimeout(() => {
    loadMisNotas(val.trim());
  }, 250);
}

