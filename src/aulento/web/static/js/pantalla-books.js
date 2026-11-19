// --- ACCIONES DELEGADAS DE LIBROS (072 T5) ---
[
  ['sincronizar-google-libros', () => syncGoogleBooks()],
  ['abrir-atajos-apple', () => openAppleShortcutsModal()],
  ['abrir-registro-libro', () => openAddBookModal()],
  ['buscar-libros', () => filterBooksGrid()],
  ['filtrar-libros', (el, datos) => setBookFilter(datos.valor)],
  ['restablecer-filtros-libros', () => resetBookFilters()],
  ['abrir-quiz-libro', (el, datos) => openBookActiveRecallModal(Number(datos.bookId), datos.bookTitulo || '')],
  ['cosechar-libro', (el, datos) => openBookHarvestModal(Number(datos.bookId), datos.bookTitulo || '')],
  ['indexar-libro', (el, datos) => indexSingleBook(Number(datos.id), el)],
  ['editar-libro', (el, datos) => openEditBookModal(Number(datos.id))],
  ['eliminar-libro', (el, datos) => deleteBook(Number(datos.bookId), datos.bookTitulo || '')],
  ['avanzar-paginas-libro', (el, datos) => advanceBookPages(Number(datos.id), Number(datos.paginas || 10))],
  ['ajustar-pagina-libro', (el, datos) => promptEditBookPage(Number(datos.id), Number(datos.pagina || 0))],
  ['avanzar-capitulo-libro', (el, datos) => advanceBookChapter(Number(datos.id))],
  ['modal-crear-libro', (el, datos, ev) => handleCreateBook(ev)],
  ['modal-editar-libro', (el, datos, ev) => handleEditBook(ev)],
  ['modal-eliminar-libro', () => deleteBookFromModal()],
  ['modal-generar-preguntas-repaso-libro', () => generateBookActiveRecallQuestions()],
  ['modal-evaluar-respuestas-repaso-libro', () => submitBookActiveRecallEvaluation()],
  ['modal-previsualizar-tarjetas-libro', () => previewBookHarvestCards()],
  ['modal-alternar-tarjetas-libro', () => toggleAllBookHarvestCheckboxes()],
  ['modal-incorporar-tarjetas-libro', () => commitBookHarvestCards()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

// --- READING TRACKER (LIBROS) ---
async function loadBooks() {
  try {
    const res = await fetch('/api/books');
    if (res.ok) {
      state.books = await res.json();
      renderBooks();
    }
  } catch (err) {
    console.error("Error al cargar libros:", err);
  }
}

function renderBooks() {
  const container = document.getElementById('books-grid');
  if (!container) return;

  if (state.books.length === 0) {
    container.innerHTML = `
      <div class="col-span-full">${Au.vacio({
        icono: '📚',
        titulo: 'Tu Biblioteca Técnica está vacía',
        texto: 'Llevá un registro exacto de capítulos y páginas en libros de Arquitectura de Datos, Machine Learning y Sistemas Distribuidos con soporte para Active Recall y FSRS.',
        accionHtml: `
          <div class="flex flex-wrap items-center justify-center gap-3 pt-2">
            ${Au.boton({ texto: 'Registrar Libro', variante: 'primario', icono: '➕', accion: 'abrir-registro-libro' })}
            ${window.seTiene && window.seTiene('google_libros') ? Au.boton({ texto: 'Sincronizar Google Play Libros', variante: 'secundario', icono: '📱', accion: 'sincronizar-google-libros' }) : ''}
          </div>
        `,
      })}</div>
    `;
    return;
  }

  const searchQuery = (state.bookSearchQuery || '').toLowerCase().trim();
  const statusFilter = state.bookFilter || 'todos';

  let filteredBooks = state.books;
  if (statusFilter !== 'todos') {
    filteredBooks = filteredBooks.filter(b => b.estado === statusFilter);
  }
  if (searchQuery) {
    filteredBooks = filteredBooks.filter(b => 
      (b.titulo || '').toLowerCase().includes(searchQuery) ||
      (b.autor || '').toLowerCase().includes(searchQuery)
    );
  }

  if (filteredBooks.length === 0 && state.books.length > 0) {
    container.innerHTML = `
      <div class="col-span-full">${Au.vacio({
        icono: '🔍',
        titulo: 'No se encontraron libros con el filtro aplicado.',
        accionHtml: Au.boton({ texto: 'Restablecer filtros', variante: 'fantasma', chico: true, accion: 'restablecer-filtros-libros' }),
      })}</div>
    `;
    return;
  }

  container.innerHTML = filteredBooks.map(b => `
    <section class="au-tarjeta au-tarjeta--interactiva justify-between">
      <div>
        <div class="flex items-center justify-between text-xs text-slate-400 mb-1">
          <div class="flex items-center gap-1.5">
            <span>${Au.escapar(b.autor || 'Libro Técnico')}</span>
            ${b.fuente_sincronizacion === 'google_books' ? Au.insignia({ texto: '📚 Google', tono: 'exito', mono: true, attrs: { title: 'Sincronizado con Google Play Libros' } }) : ''}
            ${b.fuente_sincronizacion === 'apple_books' ? Au.insignia({ texto: '🍎 Apple', mono: true, attrs: { title: 'Sincronizado vía Atajo de Apple Libros' } }) : ''}
          </div>
          ${Au.insignia({ texto: b.estado, tono: b.estado === 'completado' ? 'exito' : 'primario' })}
        </div>
        <h3 class="font-bold text-white text-base leading-snug">${Au.escapar(b.titulo)}</h3>
      </div>

      <div class="space-y-3 pt-2">
        <div class="space-y-1">
          <div class="flex justify-between text-xs text-slate-300">
            <span>${b.total_paginas ? `Pág. ${Number(b.pagina_actual || 0)} / ${Number(b.total_paginas)} • Cap. ${Number(b.capitulo_actual)}/${Number(b.total_capitulos)}` : `Capítulo ${Number(b.capitulo_actual)} de ${Number(b.total_capitulos)}`}</span>
            <span class="font-bold text-sky-400">${b.porcentaje_leido.toFixed(0)}%</span>
          </div>
          ${Au.progreso({ valor: b.porcentaje_leido, maximo: 100, tono: b.estado === 'completado' ? 'exito' : undefined, etiqueta: 'Progreso de lectura' })}
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800">
          <div class="flex flex-wrap items-center gap-1.5">
            ${Au.boton({ texto: 'Quiz', icono: '🧠', chico: true, accion: 'abrir-quiz-libro', datos: { bookId: b.id, bookTitulo: b.titulo }, attrs: { title: 'Active Recall con Mentor de IA' } })}
            ${Au.boton({ texto: 'Cosechar', icono: '🃏', chico: true, accion: 'cosechar-libro', datos: { bookId: b.id, bookTitulo: b.titulo }, attrs: { title: 'Cosechar vocabulario técnico para FSRS' } })}
            ${Au.boton({ texto: 'Indexar', icono: '⚡', chico: true, accion: 'indexar-libro', datos: { id: b.id }, attrs: { title: 'Indexar este libro en el índice de búsqueda' } })}
            ${Au.boton({ texto: 'Editar', icono: '✏️', chico: true, accion: 'editar-libro', datos: { id: b.id }, attrs: { title: 'Editar libro' } })}
            ${Au.boton({ icono: '🗑️', soloIcono: true, etiqueta: 'Eliminar libro', variante: 'peligro', chico: true, accion: 'eliminar-libro', datos: { bookId: b.id, bookTitulo: b.titulo } })}
          </div>
          <div class="flex flex-wrap items-center gap-1.5">
            ${b.total_paginas ? `
              ${Au.boton({ texto: '+10', icono: '📄', chico: true, deshabilitado: b.pagina_actual >= b.total_paginas, accion: 'avanzar-paginas-libro', datos: { id: b.id, paginas: 10 } })}
              ${Au.boton({ texto: 'Pág.', chico: true, accion: 'ajustar-pagina-libro', datos: { id: b.id, pagina: b.pagina_actual || 0 }, attrs: { title: 'Ajustar página' } })}
            ` : ''}
            ${Au.boton({ texto: '+1 Cap.', icono: '📖', chico: true, deshabilitado: b.capitulo_actual >= b.total_capitulos, accion: 'avanzar-capitulo-libro', datos: { id: b.id } })}
          </div>
        </div>
      </div>
    </section>
  `).join('');
}

async function advanceBookChapter(bookId) {
  try {
    const res = await fetch(`/api/books/${bookId}/advance`, { method: 'POST' });
    if (res.ok) {
      await loadBooks();
      renderDashboard();
    }
  } catch (err) {
    console.error("Error al avanzar libro:", err);
  }
}

async function advanceBookPages(bookId, pages = 10) {
  try {
    const res = await fetch(`/api/books/${bookId}/advance-pages?pages=${pages}`, { method: 'POST' });
    if (res.ok) {
      await loadBooks();
      renderDashboard();
    }
  } catch (err) {
    console.error("Error al avanzar páginas:", err);
  }
}

async function promptEditBookPage(bookId, currentPage) {
  const input = await showPromptDialog({
    title: 'Ajustar Página de Lectura',
    message: 'Ingresá el número de página actual en la que te encontrás:',
    defaultValue: String(currentPage || 0),
    placeholder: 'Ej. 142',
    confirmText: 'Actualizar Página',
    icon: '📖'
  });
  if (input === null || input.trim() === '') return;
  const newPage = parseInt(input.trim(), 10);
  if (isNaN(newPage) || newPage < 0) {
    showToast('Número de página inválido. Ingresá un número mayor o igual a 0.', 'error');
    return;
  }
  try {
    const res = await fetch(`/api/books/${bookId}/progress`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pagina_actual: newPage }),
    });
    if (res.ok) {
      showToast(`Página de lectura actualizada a la ${newPage}`, 'success');
      await loadBooks();
      renderDashboard();
    } else {
      showToast('Error al actualizar página del libro.', 'error');
    }
  } catch (err) {
    console.error("Error al actualizar página:", err);
    showToast('Error de conexión al actualizar página.', 'error');
  }
}

async function handleCreateBook(e) {
  e.preventDefault();
  const title = document.getElementById('new-book-title').value.trim();
  const author = document.getElementById('new-book-author').value.trim();
  const current = parseInt(document.getElementById('new-book-current').value) || 0;
  const total = parseInt(document.getElementById('new-book-total').value) || 10;
  const curPageVal = document.getElementById('new-book-current-page').value;
  const totPageVal = document.getElementById('new-book-total-pages').value;

  const curPage = curPageVal ? parseInt(curPageVal, 10) : 0;
  const totPage = totPageVal ? parseInt(totPageVal, 10) : null;

  try {
    const payload = {
      titulo: title,
      autor: author || null,
      capitulo_actual: current,
      total_capitulos: total,
      pagina_actual: curPage,
    };
    if (totPage) {
      payload.total_paginas = totPage;
    }

    const res = await fetch('/api/books', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      closeAddBookModal();
      await loadBooks();
      renderDashboard();
    }
  } catch (err) {
    console.error("Error al registrar libro:", err);
  }
}

// --- MODAL EDITAR LIBRO ---
function openEditBookModal(bookId) {
  const b = state.books.find(x => x.id === bookId);
  if (!b) return;

  document.getElementById('edit-book-id').value = b.id;
  document.getElementById('edit-book-title').value = b.titulo;
  document.getElementById('edit-book-author').value = b.autor || '';
  document.getElementById('edit-book-current-chapter').value = b.capitulo_actual;
  document.getElementById('edit-book-total-chapters').value = b.total_capitulos;
  document.getElementById('edit-book-current-page').value = b.pagina_actual || 0;
  document.getElementById('edit-book-total-pages').value = b.total_paginas || '';
  document.getElementById('edit-book-status').value = b.estado || 'leyendo';

  Au.modal.abrir('edit-book-modal');
}

function closeEditBookModal() {
  Au.modal.cerrar('edit-book-modal');
}

async function handleEditBook(e) {
  e.preventDefault();
  const id = document.getElementById('edit-book-id').value;
  const title = document.getElementById('edit-book-title').value.trim();
  const author = document.getElementById('edit-book-author').value.trim();
  const cap = parseInt(document.getElementById('edit-book-current-chapter').value, 10);
  const totCap = parseInt(document.getElementById('edit-book-total-chapters').value, 10);
  const pag = parseInt(document.getElementById('edit-book-current-page').value, 10) || 0;
  const totPagVal = document.getElementById('edit-book-total-pages').value.trim();
  const totPag = totPagVal ? parseInt(totPagVal, 10) : null;
  const st = document.getElementById('edit-book-status').value;

  try {
    const res = await fetch(`/api/books/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        titulo: title,
        autor: author || null,
        capitulo_actual: cap,
        total_capitulos: totCap,
        pagina_actual: pag,
        total_paginas: totPag,
        estado: st,
      }),
    });
    if (res.ok) {
      closeEditBookModal();
      await loadBooks();
      renderDashboard();
    } else {
      const err = await res.json();
      alert("Error al actualizar libro: " + (err.detail || "Verificá los datos ingresados"));
    }
  } catch (err) {
    console.error("Error al actualizar libro:", err);
  }
}

async function deleteBook(id, title) {
  const confirmed = await showConfirmDialog({
    title: '¿Eliminar libro?',
    message: `¿Estás seguro de eliminar el libro "${title}" del seguimiento de lectura?`,
    confirmText: 'Eliminar Libro',
    cancelText: 'Cancelar',
    icon: '🗑️',
    danger: true
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/books/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast(`Libro "${title}" eliminado`, 'success');
      await loadBooks();
      renderDashboard();
    } else {
      showToast('Error al eliminar el libro.', 'error');
    }
  } catch (err) {
    console.error("Error al eliminar libro:", err);
    showToast('Error de conexión al eliminar libro.', 'error');
  }
}

function deleteBookFromModal() {
  const id = document.getElementById('edit-book-id').value;
  const title = document.getElementById('edit-book-title').value;
  closeEditBookModal();
  deleteBook(id, title);
}

// ----------------------------------------------------------------------
// Sincronización Google Books y Atajos Apple
// ----------------------------------------------------------------------

async function syncGoogleBooks() {
  const btn = document.getElementById('btn-sync-google-books');
  try {
    const stRes = await fetch('/api/books/google/status');
    if (!stRes.ok) return;
    const st = await stRes.json();
    if (!st.conectado) {
      const confirmed = await showConfirmDialog({
        title: 'Vincular Google Play Libros',
        message: 'Google Play Libros no está vinculado todavía a tu cuenta.\n\n¿Deseás iniciar la vinculación con tu cuenta de Google ahora para sincronizar tus estanterías y progreso de lectura?',
        confirmText: 'Vincular cuenta',
        cancelText: 'Cancelar',
        icon: '📚'
      });
      if (confirmed) {
        const authRes = await fetch('/api/books/google/authorize', { method: 'POST' });
        if (authRes.ok) {
          const authData = await authRes.json();
          window.open(authData.auth_url, '_blank', 'width=600,height=700');
        } else {
          const err = await authRes.json();
          showToast('No se pudo iniciar la autorización: ' + (err.detail || 'Probá de nuevo en un rato.'), 'error');
        }
      }
      return;
    }

    if (btn) btn.disabled = true;
    showNotification('Sincronizando con Google Play Libros...', 'info');
    const syncRes = await fetch('/api/books/google/sync', { method: 'POST' });
    if (syncRes.ok) {
      const resData = await syncRes.json();
      const r = resData.resultado || {};
      showNotification(`Sincronización exitosa: ${r.sincronizados || 0} libros procesados (+${r.creados || 0} nuevos)`, 'success');
      await loadBooks();
      renderDashboard();
    } else {
      const err = await syncRes.json();
      showNotification('Error al sincronizar: ' + (err.detail || syncRes.statusText), 'error');
    }
  } catch (err) {
    console.error('Error en syncGoogleBooks:', err);
    showNotification('Error al conectar con Google Books', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openAppleShortcutsModal() {
  const input = document.getElementById('shortcut-webhook-url');
  if (input) {
    input.value = `${window.location.origin}/api/books/sync/webhook`;
  }
  Au.modal.abrir('modal-apple-shortcuts');
  cargarAtajoDeLibros();
}

// ==========================================
// FEATURE 042: ACTIVE RECALL & COSECHA FSRS DE LIBROS
// ==========================================
let currentBookAR = { bookId: null, title: '', questions: [], tramo: '' };
let currentBookHarvest = { bookId: null, title: '', cards: [], tramo: '' };

function openBookActiveRecallModal(bookId, title) {
  currentBookAR = { bookId, title, questions: [], tramo: '' };
  const modal = document.getElementById('modal-book-active-recall');
  if (!modal) return;
  document.getElementById('book-ar-modal-title').textContent = `Repaso Activo: ${title}`;
  document.getElementById('book-ar-modal-subtitle').textContent = 'Mentor de IA socrático para afianzar conceptos clave';
  document.getElementById('book-ar-step-config').classList.remove('hidden');
  document.getElementById('book-ar-loading').classList.add('hidden');
  document.getElementById('book-ar-step-quiz').classList.add('hidden');
  document.getElementById('book-ar-step-results').classList.add('hidden');
  Au.modal.abrir('modal-book-active-recall');
}

function closeBookActiveRecallModal() {
  Au.modal.cerrar('modal-book-active-recall');
}

async function generateBookActiveRecallQuestions() {
  const count = parseInt(document.getElementById('book-ar-count').value || '3', 10);
  document.getElementById('book-ar-step-config').classList.add('hidden');
  document.getElementById('book-ar-loading').classList.remove('hidden');
  document.getElementById('book-ar-loading-text').textContent = 'Generando preguntas de repaso activo sobre tu lectura...';

  try {
    const res = await fetch(`/api/books/${currentBookAR.bookId}/active-recall/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cantidad: count }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Error al generar preguntas');
    }

    const data = await res.json();
    currentBookAR.questions = data.preguntas || [];
    currentBookAR.tramo = data.tramo_evaluado || '';

    document.getElementById('book-ar-modal-subtitle').textContent = `Tramo evaluado: ${currentBookAR.tramo}`;
    const container = document.getElementById('book-ar-questions-container');
    container.innerHTML = currentBookAR.questions.map((q, idx) => `
      <div class="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2">
        <div class="flex items-center justify-between text-xs font-semibold text-sky-400">
          <span>Pregunta ${q.id || (idx + 1)}</span>
          <span class="text-xs text-slate-500 font-mono">${escapeHtml(q.objetivo_conceptual || '')}</span>
        </div>
        <p class="text-slate-100 font-medium text-xs leading-relaxed">${escapeHtml(q.pregunta)}</p>
        <textarea id="book-ar-ans-${q.id}" rows="3" placeholder="Escribí tu respuesta conceptual con tus propias palabras..." class="au-campo__control"></textarea>
      </div>
    `).join('');

    document.getElementById('book-ar-loading').classList.add('hidden');
    document.getElementById('book-ar-step-quiz').classList.remove('hidden');
  } catch (err) {
    alert(`Error: ${err.message}`);
    document.getElementById('book-ar-loading').classList.add('hidden');
    document.getElementById('book-ar-step-config').classList.remove('hidden');
  }
}

async function submitBookActiveRecallEvaluation() {
  const respuestas = [];
  for (const q of currentBookAR.questions) {
    const textarea = document.getElementById(`book-ar-ans-${q.id}`);
    const ansText = textarea ? textarea.value.trim() : '';
    if (!ansText) {
      alert(`Por favor completá la respuesta a la Pregunta ${q.id}`);
      return;
    }
    respuestas.push({
      question_id: q.id,
      pregunta: q.pregunta,
      respuesta_usuario: ansText,
    });
  }

  document.getElementById('book-ar-step-quiz').classList.add('hidden');
  document.getElementById('book-ar-loading').classList.remove('hidden');
  document.getElementById('book-ar-loading-text').textContent = 'El mentor de IA está evaluando formativamente tus respuestas...';

  try {
    const res = await fetch(`/api/books/${currentBookAR.bookId}/active-recall/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tramo_evaluado: currentBookAR.tramo || 'Lectura actual',
        respuestas: respuestas,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Error al evaluar respuestas');
    }

    const data = await res.json();
    document.getElementById('book-ar-loading').classList.add('hidden');

    const summary = document.getElementById('book-ar-results-summary');
    const tonoVeredicto = data.score_global >= 80 ? 'exito' : (data.score_global >= 60 ? 'alerta' : 'peligro');

    summary.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="font-bold text-white text-sm">Calificación Global:</span>
        <div class="flex items-center gap-2">
          ${Au.insignia({ texto: `${data.veredicto} (${data.score_global}/100)`, tono: tonoVeredicto })}
        </div>
      </div>
      <p class="text-xs text-slate-300 leading-relaxed pt-1">${escapeHtml(data.resumen_pedagogico || '')}</p>
      <div class="text-xs text-emerald-400 font-semibold pt-1 flex items-center gap-1">
        <span>⏱️</span> Sesión de estudio de 10 min registrada automáticamente en tu historial.
      </div>
    `;

    const detail = document.getElementById('book-ar-results-detail');
    detail.innerHTML = (data.evaluaciones || []).map(ev => `
      <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-3.5 space-y-2">
        <div class="flex items-center justify-between text-xs font-bold">
          <span class="text-slate-200">Pregunta ${ev.question_id}</span>
          <span class="text-sky-400">${ev.puntaje}/100</span>
        </div>
        ${ev.aciertos ? `<div class="text-xs text-emerald-300"><strong class="text-emerald-400">Aciertos:</strong> ${escapeHtml(ev.aciertos)}</div>` : ''}
        ${ev.mejoras ? `<div class="text-xs text-amber-300"><strong class="text-amber-400">Oportunidad de mejora:</strong> ${escapeHtml(ev.mejoras)}</div>` : ''}
        ${ev.explicacion_optima ? `<div class="text-xs text-slate-300 bg-slate-900 p-2.5 rounded-lg border border-slate-800"><strong class="text-slate-400 block mb-0.5 font-semibold">Explicación conceptual de referencia:</strong> ${escapeHtml(ev.explicacion_optima)}</div>` : ''}
      </div>
    `).join('');

    document.getElementById('book-ar-step-results').classList.remove('hidden');
  } catch (err) {
    alert(`Error: ${err.message}`);
    document.getElementById('book-ar-loading').classList.add('hidden');
    document.getElementById('book-ar-step-quiz').classList.remove('hidden');
  }
}

function openBookHarvestModal(bookId, title) {
  currentBookHarvest = { bookId, title, cards: [], tramo: '' };
  const modal = document.getElementById('modal-book-harvest');
  if (!modal) return;
  document.getElementById('book-harvest-modal-title').textContent = `Crear Tarjetas: ${title}`;
  document.getElementById('book-harvest-modal-subtitle').textContent = 'Extracción automatizada de vocabulario técnico y conceptos';
  document.getElementById('book-harvest-step-config').classList.remove('hidden');
  document.getElementById('book-harvest-loading').classList.add('hidden');
  document.getElementById('book-harvest-step-preview').classList.add('hidden');
  document.getElementById('book-harvest-step-results').classList.add('hidden');
  Au.modal.abrir('modal-book-harvest');
}

function closeBookHarvestModal() {
  Au.modal.cerrar('modal-book-harvest');
}

async function previewBookHarvestCards() {
  const count = parseInt(document.getElementById('book-harvest-count').value || '5', 10);
  document.getElementById('book-harvest-step-config').classList.add('hidden');
  document.getElementById('book-harvest-loading').classList.remove('hidden');
  document.getElementById('book-harvest-loading-text').textContent = 'Extrayendo vocabulario técnico y conceptos clave...';

  try {
    const res = await fetch(`/api/books/${currentBookHarvest.bookId}/harvest/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cantidad: count }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Error al cosechar tarjetas');
    }

    const data = await res.json();
    currentBookHarvest.cards = data.cards || [];
    currentBookHarvest.tramo = data.tramo || '';

    document.getElementById('book-harvest-modal-subtitle').textContent = `Tramo: ${currentBookHarvest.tramo}`;
    const container = document.getElementById('book-harvest-cards-container');
    container.innerHTML = currentBookHarvest.cards.map((c, idx) => `
      <label class="flex items-start gap-2.5 bg-slate-950/70 border border-slate-800 rounded-xl p-3 cursor-pointer hover:border-slate-700 transition">
        <input type="checkbox" id="book-harvest-cb-${idx}" checked class="mt-1 rounded bg-slate-900 border-slate-700 text-purple-600 focus:ring-0">
        <div class="space-y-1 flex-1">
          <div class="flex items-center justify-between text-xs">
            <span class="font-bold text-white">${escapeHtml(c.item_pregunta)}</span>
            ${Au.insignia({ texto: c.categoria || 'ingles_tecnico', mono: true })}
          </div>
          <p class="text-slate-300 text-xs">${escapeHtml(c.respuesta_esperada)}</p>
          ${c.contexto_uso ? `<p class="text-slate-500 italic text-xs">“${escapeHtml(c.contexto_uso)}”</p>` : ''}
        </div>
      </label>
    `).join('');

    document.getElementById('book-harvest-loading').classList.add('hidden');
    document.getElementById('book-harvest-step-preview').classList.remove('hidden');
  } catch (err) {
    alert(`Error: ${err.message}`);
    document.getElementById('book-harvest-loading').classList.add('hidden');
    document.getElementById('book-harvest-step-config').classList.remove('hidden');
  }
}

function toggleAllBookHarvestCheckboxes() {
  const cbs = document.querySelectorAll('#book-harvest-cards-container input[type="checkbox"]');
  const allChecked = Array.from(cbs).every(cb => cb.checked);
  cbs.forEach(cb => { cb.checked = !allChecked; });
}

async function commitBookHarvestCards() {
  const selectedCards = [];
  currentBookHarvest.cards.forEach((c, idx) => {
    const cb = document.getElementById(`book-harvest-cb-${idx}`);
    if (cb && cb.checked) {
      selectedCards.push(c);
    }
  });

  if (selectedCards.length === 0) {
    alert('Seleccioná al menos una tarjeta para incorporar al mazo.');
    return;
  }

  document.getElementById('book-harvest-step-preview').classList.add('hidden');
  document.getElementById('book-harvest-loading').classList.remove('hidden');
  document.getElementById('book-harvest-loading-text').textContent = 'Guardando tarjetas en tu mazo de repaso...';

  try {
    const res = await fetch(`/api/books/${currentBookHarvest.bookId}/harvest/commit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cards: selectedCards }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Error al guardar tarjetas');
    }

    const data = await res.json();
    document.getElementById('book-harvest-loading').classList.add('hidden');

    const resBox = document.getElementById('book-harvest-results-box');
    resBox.innerHTML = `
      <div class="space-y-1.5">
        <h4 class="font-bold text-white text-sm">🎉 ¡Tarjetas de repaso creadas con éxito!</h4>
        <p class="text-xs text-emerald-300">
          Se añadieron <strong>${data.guardadas}</strong> tarjetas nuevas a tu mazo de estudio.
          ${data.omitidas_duplicadas > 0 ? `<br><span class="text-slate-400">Se omitieron ${data.omitidas_duplicadas} tarjetas porque ya existían en tu mazo.</span>` : ''}
        </p>
      </div>
    `;
    document.getElementById('book-harvest-step-results').classList.remove('hidden');
    if (typeof loadFSRSDueCards === 'function') {
      loadFSRSDueCards();
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
    document.getElementById('book-harvest-loading').classList.add('hidden');
    document.getElementById('book-harvest-step-preview').classList.remove('hidden');
  }
}


async function syncCourseProgressModal(courseId) {
  const currentPlatform = state.platforms.find(p => p.cursos && p.cursos.some(c => c.id === courseId));
  const course = currentPlatform ? currentPlatform.cursos.find(c => c.id === courseId) : null;
  const courseName = course ? course.nombre_curso : `Curso #${courseId}`;

  const input = prompt(`Sincronizar avance para '${courseName}':\nDejá vacío para sincronizar según la configuración del curso o ingresá el nuevo % (0-100):`, "");
  if (input === null) return;

  const payload = {};
  if (input.trim() !== "") {
    const num = parseFloat(input);
    if (!isNaN(num) && num >= 0 && num <= 100) {
      payload.progreso_pct = num;
    }
  }

  try {
    const res = await fetch(`/api/hub/courses/${courseId}/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const data = await res.json();
      alert(`✅ ${data.mensaje || 'Curso sincronizado con éxito.'}\nNuevo avance: ${data.progreso_pct}% (${data.estado})`);
      await loadPlatforms();
      renderDashboard();
    } else {
      const err = await res.json();
      alert(`❌ Error al sincronizar: ${err.detail || 'Ocurrió un error inesperado.'}`);
    }
  } catch (err) {
    console.error("Error al sincronizar curso:", err);
    alert("Error de red al sincronizar el curso.");
  }
}

async function showCourseWebhookModal() {
  // El modal está en index.html (lo controla test_r4_cada_au_modal_cumple_el_contrato)
  Au.modal.abrir('modal-course-webhook');

  try {
    const res = await fetch('/api/hub/sync/webhook-info');
    if (res.ok) {
      const info = await res.json();
      const urlInput = document.getElementById('course-webhook-url');
      if (urlInput) urlInput.value = info.webhook_url;
      const authEl = document.getElementById('course-webhook-auth');
      if (authEl) authEl.textContent = info.autenticacion;
      const payloadEl = document.getElementById('course-webhook-payload');
      if (payloadEl && info.ejemplo_payload) payloadEl.textContent = JSON.stringify(info.ejemplo_payload, null, 2);
      const instEl = document.getElementById('course-webhook-instrucciones');
      if (instEl && info.instrucciones) {
        instEl.textContent = info.instrucciones;
        const instBloque = document.getElementById('course-webhook-instrucciones-bloque');
        if (instBloque) instBloque.classList.remove('hidden');
      }
      const contentEl = document.getElementById('course-webhook-info-content');
      if (contentEl) {
        contentEl.innerHTML = `
          <div class="text-slate-300 font-sans space-y-1 mb-2">
            <p class="font-bold text-sky-400">¿Cómo funciona?</p>
            <p class="text-xs text-slate-300">${escapeHtml(info.instrucciones || 'Envía un POST al endpoint con el avance del curso.')}</p>
          </div>
          <div class="space-y-1">
            <span class="text-slate-500 text-xs uppercase font-bold tracking-wider block">Endpoint</span>
            <code class="text-sky-300 text-xs break-all block bg-slate-900 p-1.5 rounded">${escapeHtml(info.webhook_url)}</code>
          </div>
          <div class="space-y-1 pt-1">
            <span class="text-slate-500 text-xs uppercase font-bold tracking-wider block">Autenticación</span>
            <span class="text-slate-300 text-xs block">${escapeHtml(info.autenticacion)}</span>
          </div>
        `;
      }
    }
  } catch (err) {
    console.error("Error al obtener webhook-info:", err);
  }
}


// Filtros en tiempo real para Biblioteca de Libros
function filterBooksGrid() {
  const input = document.getElementById('book-search-input');
  state.bookSearchQuery = input ? input.value : '';
  renderBooks();
}

function setBookFilter(filter) {
  state.bookFilter = filter;
  ['todos', 'progreso', 'completado'].forEach(f => {
    const btn = document.getElementById(`btn-book-filter-${f}`);
    if (btn) {
      const active = (f === 'progreso' && filter === 'en_progreso') || (f === filter);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    }
  });
  renderBooks();
}

function resetBookFilters() {
  state.bookSearchQuery = '';
  state.bookFilter = 'todos';
  const input = document.getElementById('book-search-input');
  if (input) input.value = '';
  setBookFilter('todos');
}

