// --- ACTIVE RECALL & FEYNMAN EXAMS ---

// Acciones del Repaso Activo (072): cada una llama a la función que antes llamaba su manejador en línea
[
  ['cambiar-vista-examen', (el, datos) => switchExamView(datos.vista)],
  ['generar-examen-vault', () => generateExamFromVault()],
  ['evaluar-feynman', () => submitFeynmanEvaluation()],
  ['cargar-preset-feynman', (el, datos) => setFeynmanConceptPreset(datos.concepto, datos.explicacion)],
  ['revelar-respuesta-cloze', (el, datos) => toggleClozeAnswer(datos.target)],
  ['elegir-opcion-quiz', (el) => handleQuizOptionClick(el)],
  ['evaluar-respuesta-abierta', (el) => handleEvaluateOpenAnswer(el)],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

function setFeynmanConceptPreset(concept, exampleExplanation = '') {
  const conceptInput = document.getElementById('feynman-concept-input');
  const explanationInput = document.getElementById('feynman-explanation-input');
  if (conceptInput) conceptInput.value = concept;
  if (explanationInput && exampleExplanation) {
    explanationInput.value = exampleExplanation;
  }
  showToast(`Tema cargado: ${concept}`, 'info');
  if (explanationInput) explanationInput.focus();
}

async function loadFeynmanExamples() {
  const container = document.getElementById('feynman-presets-container');
  if (!container) return;
  try {
    const res = await fetch('/api/exams/feynman-examples');
    if (res.ok) {
      const examples = await res.json();
      if (Array.isArray(examples) && examples.length > 0) {
        container.innerHTML = `
          <span class="text-xs text-slate-500">Ejemplos rápidos:</span>
          ${examples.map(ex => `
            <button type="button" 
              data-accion="cargar-preset-feynman" 
              data-concepto="${escapeHtml(ex.concept)}" 
              data-explicacion="${escapeHtml(ex.explanation || '')}" 
              class="au-boton au-boton--secundario au-boton--chico">
              ${escapeHtml(ex.concept)}
            </button>
          `).join('')}
        `;
      }
    }
  } catch (err) {
    console.warn("No se pudieron cargar ejemplos dinámicos de Feynman:", err);
  }
}

function switchExamView(view) {
  const btnQuiz = document.getElementById('subtab-btn-quiz');
  const btnFeynman = document.getElementById('subtab-btn-feynman');
  const viewQuiz = document.getElementById('view-exam-quiz');
  const viewFeynman = document.getElementById('view-exam-feynman');

  if (view === 'quiz') {
    if (btnQuiz) btnQuiz.setAttribute('aria-selected', 'true');
    if (btnFeynman) btnFeynman.setAttribute('aria-selected', 'false');
    if (viewQuiz) viewQuiz.classList.remove('hidden');
    if (viewFeynman) viewFeynman.classList.add('hidden');
  } else {
    if (btnFeynman) btnFeynman.setAttribute('aria-selected', 'true');
    if (btnQuiz) btnQuiz.setAttribute('aria-selected', 'false');
    if (viewFeynman) viewFeynman.classList.remove('hidden');
    if (viewQuiz) viewQuiz.classList.add('hidden');
    loadFeynmanExamples();
    loadFeynmanNotes();
  }
}

// Notas de la cuenta para que el Simulador Feynman contraste la explicación con la elegida (060 R4)
async function loadFeynmanNotes() {
  const select = document.getElementById('feynman-note-select');
  if (!select) return;
  try {
    const res = await fetch('/api/vault/notes');
    if (!res.ok) return;
    const notes = await res.json();
    const elegida = select.value;
    select.innerHTML = '<option value="">Buscar la nota por el nombre del concepto</option>' + notes.map(n => `
      <option value="${escapeHtml(n.id)}">[${escapeHtml(n.folder)}] ${escapeHtml(n.title)}</option>
    `).join('');
    select.value = elegida;
  } catch (err) {
    console.warn("No se pudieron cargar las notas para Feynman:", err);
  }
}

// Notas de Mis notas y materiales subidos: un material va como `material:<id>`, que el examen reconoce (060 R1)
async function loadVaultNotesForExams() {
  const select = document.getElementById('exam-note-select');
  if (!select) return;

  const [notesRes, materialesRes] = await Promise.allSettled([fetch('/api/vault/notes'), fetch('/api/materiales')]);
  let notes = [];
  let materiales = [];
  try {
    if (notesRes.status === 'fulfilled' && notesRes.value.ok) notes = await notesRes.value.json();
    if (materialesRes.status === 'fulfilled' && materialesRes.value.ok) materiales = (await materialesRes.value.json()).materiales || [];
  } catch (err) {
    console.error("Error al cargar notas y materiales para exámenes:", err);
  }
  state.vaultNotes = notes;

  if (notes.length === 0 && materiales.length === 0) {
    select.innerHTML = '<option value="" disabled selected>-- No hay notas ni materiales --</option>';
    return;
  }

  const opcionesDeNotas = notes.map(n => `
    <option value="${escapeHtml(n.id)}" class="bg-slate-900 text-white">[${escapeHtml(n.folder)}] ${escapeHtml(n.title)}</option>
  `).join('');
  const opcionesDeMateriales = materiales.map(m => `
    <option value="material:${Number(m.id)}" class="bg-slate-900 text-white">${escapeHtml(m.nombre)}</option>
  `).join('');
  select.innerHTML =
    (notes.length ? `<optgroup label="Mis notas">${opcionesDeNotas}</optgroup>` : '') +
    (materiales.length ? `<optgroup label="Mis materiales">${opcionesDeMateriales}</optgroup>` : '');
}

async function generateExamFromVault() {
  const noteId = document.getElementById('exam-note-select').value;
  const qType = document.getElementById('exam-type-select').value;
  const container = document.getElementById('exam-questions-container');

  if (!noteId) {
    alert("Elegí una nota o un material.");
    return;
  }

  container.innerHTML = '<p class="text-sm text-sky-400">Generando examen adaptativo de Active Recall...</p>';

  try {
    const res = await fetch('/api/exams/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        note_id: noteId,
        question_type: qType,
        count: 3
      })
    });

    if (res.ok) {
      const exam = await res.json();
      state.currentExam = exam;

      if (!exam.questions || exam.questions.length === 0) {
        container.innerHTML = '<p class="text-sm text-slate-400">No se pudieron generar preguntas para esta nota.</p>';
        return;
      }

      const sinIaBadge = exam.sin_ia ? Au.insignia({ texto: exam.rotulo || 'sin IA', tono: 'alerta' }) : '';

      const avisoBox = exam.aviso ? Au.aviso({ texto: exam.aviso, tono: 'alerta' }) : '';

      container.innerHTML = `
        <div class="space-y-6">
          <div class="au-seccion au-seccion--suave flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-white text-base">${escapeHtml(exam.title)}</h3>
                ${sinIaBadge}
              </div>
              <p class="text-xs text-sky-300">Modo Testing Effect: Intenta responder mentalmente antes de verificar la solución.</p>
            </div>
            <span class="au-insignia au-insignia--primario shrink-0">${Number(exam.total_questions)} preguntas</span>
          </div>

          ${avisoBox}

          ${exam.questions.map((q, idx) => `
            <div class="au-tarjeta" id="q-card-${idx}">
              <div class="flex items-center justify-between text-xs">
                <span class="font-bold text-sky-400 uppercase tracking-wider">Pregunta ${idx + 1} • ${escapeHtml(q.question_type ? q.question_type.replace('_', ' ') : '')}</span>
                <span class="text-slate-500 font-mono text-xs">${escapeHtml(q.topic)}</span>
              </div>

              <p class="text-base text-white font-medium leading-relaxed">${escapeHtml(q.prompt)}</p>

              ${q.fragmento ? `
                <div class="au-tarjeta au-tarjeta--hundida text-xs text-slate-400">
                  <span class="font-semibold text-slate-300">${Au.icono('lectura')} Fragmento de referencia:</span>
                  <span class="italic">"${escapeHtml(q.fragmento)}"</span>
                  ${q.source_reference ? `<span class="block mt-1 text-xs text-slate-500">De: ${escapeHtml(q.source_reference)}</span>` : ''}
                </div>
              ` : ''}

              ${q.options && q.options.length > 0 ? `
                <div class="space-y-2 pt-2">
                  ${q.options.map((opt, optIdx) => `
                    <button 
                      type="button" 
                      data-accion="elegir-opcion-quiz" 
                      data-q="${idx}" 
                      data-opt="${optIdx}" 
                      class="au-boton au-boton--secundario au-boton--bloque quiz-option-btn justify-start text-left"
                    >
                      <span class="w-6 h-6 rounded-lg bg-slate-800 text-slate-400 text-xs flex items-center justify-center font-bold group-hover:bg-sky-600 group-hover:text-white transition">
                        ${String.fromCharCode(65 + optIdx)}
                      </span>
                      <span class="flex-1">${escapeHtml(opt)}</span>
                    </button>
                  `).join('')}
                </div>
              ` : (q.question_type === 'open' || q.question_type === 'open_reasoning') ? `
                <div class="space-y-3 pt-2">
                  <textarea id="q-open-input-${idx}" rows="3" placeholder="Escribe tu razonamiento o respuesta aquí..." class="au-campo__control"></textarea>
                  <button 
                    type="button" 
                    data-accion="evaluar-respuesta-abierta" 
                    data-q="${idx}" 
                    class="au-boton au-boton--primario au-boton--chico flex items-center gap-1.5"
                  >
                    <span>${Au.icono('examen')}</span> Evaluar Respuesta
                  </button>
                  <div id="q-open-feedback-${idx}" class="hidden au-seccion au-seccion--con-linea au-seccion--apretada text-xs"></div>
                </div>
              ` : `
                <div class="pt-2">
                  <button 
                    type="button" 
                    data-accion="revelar-respuesta-cloze" 
                    data-target="q-cloze-${idx}" 
                    class="au-boton au-boton--secundario au-boton--chico"
                  >
                    ${Au.icono('ver')} Revelar Respuesta y Fundamento
                  </button>
                  <div id="q-cloze-${idx}" class="hidden mt-3 au-tarjeta au-tarjeta--hundida">
                    <p class="text-sm font-bold text-emerald-400">Respuesta: ${escapeHtml(q.correct_answer)}</p>
                    <p class="text-xs text-slate-300 leading-relaxed">${escapeHtml(q.explanation)}</p>
                  </div>
                </div>
              `}

              <div id="q-feedback-${idx}" class="hidden pt-3 border-t border-slate-800/80 text-xs leading-relaxed"></div>
            </div>
          `).join('')}
        </div>
      `;
    } else {
      const err = await res.json();
      container.innerHTML = `<p class="text-sm text-rose-400">Error al generar examen: ${escapeHtml(err.detail) || 'Verifique la nota seleccionada'}</p>`;
    }
  } catch (err) {
    console.error("Error al generar examen:", err);
    container.innerHTML = '<p class="text-sm text-rose-400">Error de conexión al generar examen.</p>';
  }
}

function handleQuizOptionClick(btn) {
  const qIdx = parseInt(btn.dataset.q, 10);
  const optIdx = parseInt(btn.dataset.opt, 10);
  const q = state.currentExam && state.currentExam.questions ? state.currentExam.questions[qIdx] : null;
  if (!q) return;

  const container = btn.parentElement;
  if (container) {
    container.querySelectorAll('button').forEach(b => {
      b.disabled = true;
      b.classList.add('opacity-60');
    });
  }

  btn.classList.remove('opacity-60');
  const feedbackEl = document.getElementById(`q-feedback-${qIdx}`);
  const chosenOpt = q.options ? q.options[optIdx] : null;
  const isCorrect = (chosenOpt === q.correct_answer);
  const explanation = q.explanation || '';

  if (isCorrect) {
    btn.classList.remove('au-boton--secundario');
    btn.classList.add('au-boton--suave-exito');
    if (feedbackEl) {
      feedbackEl.classList.remove('hidden');
      feedbackEl.innerHTML = `
        <span class="text-emerald-400 font-bold block mb-1">${Au.icono('ok')} ¡Correcto!</span>
        <span class="text-slate-300">${escapeHtml(explanation)}</span>
      `;
    }
  } else {
    btn.classList.remove('au-boton--secundario');
    btn.classList.add('au-boton--suave-peligro');
    if (feedbackEl) {
      feedbackEl.classList.remove('hidden');
      feedbackEl.innerHTML = `
        <span class="text-rose-400 font-bold block mb-1">${Au.icono('cerrar')} Incorrecto</span>
        <span class="text-slate-300">${escapeHtml(explanation)}</span>
      `;
    }
  }
}

async function handleEvaluateOpenAnswer(btn) {
  const qIdx = parseInt(btn.dataset.q, 10);
  const exam = state.currentExam;
  const q = exam && exam.questions ? exam.questions[qIdx] : null;
  if (!q) return;

  const input = document.getElementById(`q-open-input-${qIdx}`);
  const feedbackEl = document.getElementById(`q-open-feedback-${qIdx}`);
  const userAnswer = input ? input.value.trim() : '';

  if (!userAnswer) {
    alert("Por favor escribe tu respuesta antes de evaluarla.");
    return;
  }

  btn.disabled = true;
  const originalHtml = btn.innerHTML;
  btn.innerHTML = '<span>' + Au.icono('cargando') + '</span> Evaluando...';

  try {
    const payload = {
      note_id: q.note_id || (document.getElementById('exam-note-select') ? document.getElementById('exam-note-select').value : null),
      question_prompt: q.prompt,
      user_answer: userAnswer,
      expected_answer: q.correct_answer || ''
    };

    const res = await fetch('/api/exams/evaluate-answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      feedbackEl.classList.remove('hidden');

      const isCorrect = data.is_correct;
      const statusColor = isCorrect ? 'text-emerald-400' : 'text-rose-400';
      const statusIcon = isCorrect ? (Au.icono('ok') + ' ¡Correcto!') : (Au.icono('cerrar') + ' Requiere Ajuste');
      const rotuloBadge = data.sin_ia ? Au.insignia({ texto: 'sin IA', tono: 'alerta' }) : '';

      feedbackEl.innerHTML = `
        <div class="flex items-center justify-between pb-2 border-b border-slate-800">
          <div class="flex items-center gap-2">
            <span class="font-bold ${statusColor}">${statusIcon}</span>
            ${rotuloBadge}
          </div>
          <span class="font-mono font-bold text-white">${Number(data.score)}/100</span>
        </div>
        <div class="text-slate-300 leading-relaxed">${escapeHtml(data.feedback)}</div>
        ${data.what_was_missing ? `
          <div class="au-aviso au-aviso--alerta">
            <span class="font-bold">Qué faltó:</span> ${escapeHtml(data.what_was_missing)}
          </div>
        ` : ''}
        ${data.aviso ? `
          <div class="text-xs text-slate-400 italic">${escapeHtml(data.aviso)}</div>
        ` : ''}
      `;
    } else {
      const err = await res.json().catch(() => ({}));
      feedbackEl.classList.remove('hidden');
      feedbackEl.innerHTML = `<span class="text-rose-400">Error al evaluar respuesta: ${escapeHtml(err.detail || 'Error desconocido')}</span>`;
    }
  } catch (err) {
    console.error("Error al evaluar respuesta abierta:", err);
    feedbackEl.classList.remove('hidden');
    feedbackEl.innerHTML = `<span class="text-rose-400">Error de red al evaluar respuesta.</span>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

function selectQuizOption(btn, isCorrect, explanationOrEncoded, feedbackId) {
  let explanation = explanationOrEncoded || '';
  try {
    if (explanation.includes('%')) explanation = decodeURIComponent(explanation);
  } catch (e) {}

  const container = btn.parentElement;
  if (container) {
    container.querySelectorAll('button').forEach(b => {
      b.disabled = true;
      b.classList.add('opacity-60');
    });
  }

  btn.classList.remove('opacity-60');
  const feedbackEl = document.getElementById(feedbackId);

  if (isCorrect) {
    btn.classList.remove('au-boton--secundario');
    btn.classList.add('au-boton--suave-exito');
    if (feedbackEl) {
      feedbackEl.classList.remove('hidden');
      feedbackEl.innerHTML = `
        <span class="text-emerald-400 font-bold block mb-1">${Au.icono('ok')} ¡Correcto!</span>
        <span class="text-slate-300">${escapeHtml(explanation)}</span>
      `;
    }
  } else {
    btn.classList.remove('au-boton--secundario');
    btn.classList.add('au-boton--suave-peligro');
    if (feedbackEl) {
      feedbackEl.classList.remove('hidden');
      feedbackEl.innerHTML = `
        <span class="text-rose-400 font-bold block mb-1">${Au.icono('cerrar')} Incorrecto</span>
        <span class="text-slate-300">${escapeHtml(explanation)}</span>
      `;
    }
  }
}

function toggleClozeAnswer(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.classList.toggle('hidden');
}

async function submitFeynmanEvaluation() {
  const concept = document.getElementById('feynman-concept-input').value.trim();
  const explanation = document.getElementById('feynman-explanation-input').value.trim();
  const container = document.getElementById('feynman-result-container');

  if (!concept || !explanation) {
    alert("Por favor ingresa tanto el concepto como tu explicación.");
    return;
  }

  container.classList.remove('hidden');
  container.innerHTML = '<p class="text-sm text-emerald-400">Analizando explicación con los 4 principios de la Técnica Feynman...</p>';

  try {
    const res = await fetch('/api/exams/evaluate-feynman', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        concept,
        explanation,
        target_audience: 'principiante',
        note_id: (document.getElementById('feynman-note-select') || {}).value || null
      })
    });

    if (res.ok) {
      const data = await res.json();
      const badgeColor = data.score >= 75 ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : (data.score >= 50 ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' : 'bg-rose-500/20 text-rose-400 border-rose-500/30');

      const sinIaBadge = data.sin_ia ? Au.insignia({ texto: data.rotulo || 'sin IA', tono: 'alerta' }) : '';

      const queMideBox = data.que_mide ? Au.aviso({ texto: `Qué mide esta evaluación: ${data.que_mide}` }) : '';

      const avisoBox = data.aviso ? Au.aviso({ texto: data.aviso, tono: 'alerta' }) : '';

      const criteriosLabels = {
        precision: 'Exactitud y Precisión Conceptual',
        simplicidad: 'Simplicidad y Estructura',
        jerga: 'Manejo de Jerga y Tecnicismos',
        analogia: 'Analogía y Ejemplo Cotidiano',
        huecos: 'Completitud y Ausencia de Huecos'
      };

      const criteriosHtml = data.criterios ? `
        <div class="space-y-3">
          <h5 class="text-xs font-bold uppercase tracking-wider text-slate-300">Evaluación por Criterios Feynman</h5>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            ${Object.entries(data.criterios).map(([k, crit]) => `
              <div class="au-tarjeta au-tarjeta--hundida flex flex-col justify-between gap-1.5">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-semibold text-slate-200">${criteriosLabels[k] || escapeHtml(k)}</span>
                  <span class="font-mono font-bold text-sky-400">${Number(crit.puntaje)}/100</span>
                </div>
                <p class="text-xs text-slate-400 leading-relaxed">${escapeHtml(crit.justificacion)}</p>
              </div>
            `).join('')}
          </div>
        </div>
      ` : '';

      container.innerHTML = `
        <div class="au-seccion au-seccion--suave">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-xl">${Au.icono('examen')}</span>
                <h4 class="font-extrabold text-white text-lg">Diagnóstico Feynman: ${escapeHtml(data.concept)}</h4>
                ${sinIaBadge}
              </div>
              <p class="text-xs text-slate-400 mt-1">${escapeHtml(data.feedback_summary)}</p>
            </div>
            <div class="flex items-center gap-3">
              <span class="au-insignia ${data.score >= 75 ? 'au-insignia--exito' : (data.score >= 50 ? 'au-insignia--alerta' : 'au-insignia--peligro')}">
                ${escapeHtml(data.mastery_level)}
              </span>
              <span class="text-3xl font-extrabold text-white">${Number(data.score)}<span class="text-sm text-slate-400">/100</span></span>
            </div>
          </div>

          ${queMideBox}
          ${avisoBox}

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div class="au-tarjeta au-tarjeta--hundida">
              <div class="flex justify-between text-xs">
                <span class="font-bold text-slate-300">Claridad & Sencillez (Sin Jerga)</span>
                <span class="font-mono text-sky-400 font-bold">${Number(data.clarity_score)}%</span>
              </div>
              ${Au.progreso({ valor: Number(data.clarity_score), maximo: 100, etiqueta: 'Claridad y sencillez' })}
            </div>

            <div class="au-tarjeta au-tarjeta--hundida">
              <div class="flex justify-between text-xs">
                <span class="font-bold text-slate-300">Exactitud Técnica del Concepto</span>
                <span class="font-mono text-emerald-400 font-bold">${Number(data.precision_score)}%</span>
              </div>
              ${Au.progreso({ valor: Number(data.precision_score), maximo: 100, tono: 'exito', etiqueta: 'Exactitud técnica' })}
            </div>
          </div>

          ${criteriosHtml}

          ${data.strengths && data.strengths.length > 0 ? `
            <div class="space-y-2">
              <h5 class="text-xs font-bold uppercase tracking-wider text-emerald-400">Puntos Fuertes Identificados</h5>
              <div class="au-aviso au-aviso--exito text-xs">
                ${data.strengths.map(s => `<p>${Au.icono('ok')} ${escapeHtml(s)}</p>`).join('')}
              </div>
            </div>
          ` : ''}

          ${data.knowledge_gaps && data.knowledge_gaps.length > 0 ? `
            <div class="space-y-2">
              <h5 class="text-xs font-bold uppercase tracking-wider text-amber-400">Lagunas o Puntos Ciegos (Knowledge Gaps)</h5>
              <div class="au-aviso au-aviso--alerta">
                ${data.knowledge_gaps.map(g => `<p>${Au.icono('alerta')} ${escapeHtml(g)}</p>`).join('')}
              </div>
            </div>
          ` : ''}

          ${data.jargon_used && data.jargon_used.length > 0 ? `
            <div class="au-aviso au-aviso--peligro">
              <span class="font-bold">Tecnicismos no explicados:</span>
              <span class="font-mono">${escapeHtml(data.jargon_used.join(', '))}</span>
            </div>
          ` : ''}

          <div class="au-tarjeta au-tarjeta--hundida">
            <h5 class="text-xs font-bold uppercase tracking-wider text-sky-400">Analogía Sugerida al Estilo Feynman</h5>
            <p class="text-xs text-slate-200 italic leading-relaxed">"${escapeHtml(data.suggested_simplification)}"</p>
          </div>
        </div>
      `;
    } else {
      const err = await res.json();
      container.innerHTML = `<p class="text-sm text-rose-400">Error al evaluar: ${escapeHtml(err.detail) || 'Ocurrió un error'}</p>`;
    }
  } catch (err) {
    console.error("Error al evaluar con Feynman:", err);
    container.innerHTML = '<p class="text-sm text-rose-400">Error de red al evaluar explicación.</p>';
  }
}

