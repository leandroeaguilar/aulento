// --- ACCIONES DELEGADAS DE CEREBRO DE ESTUDIO (072 T7) ---
[
  ['abrir-apunte-material', () => openMaterialNoteModal()],
  ['sincronizar-catalogo-vectores', () => syncAllCatalogToVectors()],
  ['abrir-indice-selectivo', () => openSelectiveIndexModal()],
  ['refrescar-estado-cerebro', () => refreshBrainStatus()],
  ['limpiar-foco-material', () => clearAgentFileFocus()],
  ['preguntar-tutor-cerebro', () => askCloudAgent()],
  ['seleccionar-modo-tutor', (el, datos) => selectAgentMode(datos.modo)],
  ['consulta-rapida-tutor', (el, datos) => runQuickAgentQuery(datos.consulta)],
  ['copiar-respuesta-tutor', () => copyAgentResponseMarkdown()],
  ['guardar-nota-tutor', () => saveCloudAgentNoteToVault()],
  ['cosechar-tarjetas-tutor', () => harvestCloudAgentCards()],
  ['ocultar-resultados-vectoriales', () => ocultarResultadosVectoriales()],
  ['subir-materiales-elegidos', (el) => subirMaterialesElegidos(el)],
  ['abrir-selector-materiales', () => abrirSelectorMateriales()],
  ['filtrar-materiales', () => renderMisMateriales()],
  ['preguntar-material-tutor', (el, datos) => askAgentAboutMaterial(Number(datos.id))],
  ['ver-texto-material', (el, datos) => verTextoDeMaterial(Number(datos.id))],
  ['indexar-material', (el, datos) => indexarMaterial(Number(datos.id), el)],
  ['borrar-material', (el, datos) => borrarMaterial(Number(datos.id))],
  ['actualizar-conteo-indice-selectivo', () => updateSelectiveIndexCount()],
  ['abrir-carpetas-tutor', () => openTutorFoldersConfig()],
  ['modal-seleccionar-todo-indice', () => toggleSelectAllIndexItems(true)],
  ['modal-deseleccionar-todo-indice', () => toggleSelectAllIndexItems(false)],
  ['modal-ejecutar-indice-selectivo', () => executeSelectiveIndexing()],
].forEach(([nombre, fn]) => Au.acciones.registrar(nombre, fn));

function ocultarResultadosVectoriales() {
  const el = document.getElementById('vector-search-results');
  if (el) el.classList.add('hidden');
}

function abrirSelectorMateriales() {
  document.getElementById('materiales-input')?.click();
}

// --- CARPETAS DEL TUTOR (vault de la cuenta) ---
// state.vaultFolders es la última respuesta de /api/vault/folders; state.tutorFoldersSelected, lo marcado sin guardar
function openTutorFoldersConfig() {
  switchTab('config');
  switchConfigSection('vault');
}

function setVaultFoldersMessage(texto, esError = false) {
  const box = document.getElementById('vault-folders-message');
  if (!box) return;
  box.textContent = texto || '';
  box.className = texto
    ? `text-xs rounded-xl px-3 py-2 border ${esError ? 'text-rose-200 bg-rose-950/40 border-rose-800/60' : 'text-emerald-200 bg-emerald-950/40 border-emerald-800/60'}`
    : 'hidden';
}

async function loadVaultFolders() {
  const lista = document.getElementById('vault-folders-list');
  if (!lista) return;
  const donde = document.getElementById('vault-folders-where');
  if (donde) {
    const tieneCarpetaLocal = typeof seTiene === 'function' ? seTiene('carpeta_local') : true;
    donde.textContent = tieneCarpetaLocal
      ? 'Están en Mis notas.'
      : 'Están en tu cuenta, dentro del servidor: se ven y se crean desde acá.';
  }
  try {
    const res = await fetch('/api/vault/folders');
    const datos = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorText(datos, 'No se pudieron leer las carpetas del vault.'));
    aplicarCarpetasDelVault(datos);
  } catch (err) {
    lista.innerHTML = `<p class="text-xs text-rose-300 py-4 text-center">${escapeHtml(err.message || 'Error de red al leer las carpetas.')}</p>`;
  }
}

// Con `conservarSeleccion`, lo marcado y sin guardar sobrevive a la recarga (por ejemplo, al crear una carpeta)
function aplicarCarpetasDelVault(datos, conservarSeleccion = false) {
  const previa = conservarSeleccion ? state.tutorFoldersSelected : null;
  state.vaultFolders = datos;
  state.tutorFoldersSelected = previa || new Set(datos.del_tutor);
  renderVaultFolders();
}

function carpetasExistentes() {
  return new Set(((state.vaultFolders && state.vaultFolders.carpetas) || []).map(c => c.ruta));
}

// Lo marcado que existe en el vault. El listado tiene un tope de profundidad y de cantidad: una carpeta del
// tutor que no entra en él igual existe (no está en `faltan`) y no se pierde al guardar.
function carpetasElegidasQueExisten() {
  const faltan = new Set((state.vaultFolders && state.vaultFolders.faltan) || []);
  return [...(state.tutorFoldersSelected || [])].filter(r => !faltan.has(r));
}

function renderFolderItems(containerId, countId) {
  const datos = state.vaultFolders;
  const lista = document.getElementById(containerId);
  if (!datos || !lista) return;

  if (!datos.carpetas.length) {
    lista.innerHTML = `
      <div class="text-center py-6 space-y-1">
        <p class="text-sm text-slate-300">Todavía no hay carpetas creadas en Mis notas.</p>
        <p class="text-xs text-slate-500">Creá las del tutor con el botón de arriba o escribí el nombre de una abajo.</p>
      </div>`;
  } else {
    lista.innerHTML = datos.carpetas.map(c => {
      const partes = c.ruta.split('/');
      const nivel = partes.length - 1;
      const marcada = state.tutorFoldersSelected.has(c.ruta);
      const desc = c.descripcion || (datos.descripciones && datos.descripciones[c.ruta]) || '';
      return `
        <label class="flex items-start gap-3 pr-3 py-2 rounded-xl hover:bg-slate-800/60 cursor-pointer transition ${marcada ? 'bg-emerald-950/30' : ''}" style="padding-left: ${0.75 + nivel * 1.25}rem">
          <input type="checkbox" data-ruta="${escapeHtml(c.ruta)}" ${marcada ? 'checked' : ''} class="mt-1 rounded bg-slate-900 border-slate-700 text-emerald-500 focus:ring-0">
          <span class="text-sm mt-0.5">${nivel ? '📂' : '📁'}</span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm text-slate-200 truncate" title="${escapeHtml(c.ruta)}">${escapeHtml(partes[nivel])}</span>
              <span class="text-xs text-slate-500 shrink-0">${c.notas} ${c.notas === 1 ? 'nota' : 'notas'}</span>
            </div>
            ${desc ? `<p class="text-xs text-slate-400 mt-0.5 leading-tight">${escapeHtml(desc)}</p>` : ''}
          </div>
        </label>`;
    }).join('');

    lista.querySelectorAll('input[type="checkbox"][data-ruta]').forEach(cb => {
      cb.addEventListener('change', () => {
        const ruta = cb.getAttribute('data-ruta');
        if (cb.checked) {
          state.tutorFoldersSelected.add(ruta);
        } else {
          state.tutorFoldersSelected.delete(ruta);
        }
        renderVaultFolders();
      });
    });
  }

  const contador = document.getElementById(countId);
  if (contador && state.vaultFolders) {
    const faltan = new Set(state.vaultFolders.faltan || []);
    const elegidas = carpetasElegidasQueExisten();
    const guardadas = state.vaultFolders.del_tutor.filter(r => !faltan.has(r));
    const cambio = elegidas.length !== guardadas.length || elegidas.some(r => !guardadas.includes(r));
    contador.textContent = `${elegidas.length} ${elegidas.length === 1 ? 'carpeta marcada' : 'carpetas marcadas'} para el tutor${cambio ? ' · sin guardar' : ''}`;
  }
}

function renderVaultFolders() {
  const datos = state.vaultFolders;
  if (!datos) return;

  const renderMissingBox = (boxId) => {
    const faltanBox = document.getElementById(boxId);
    const faltan = datos.faltan || [];
    if (faltanBox) {
      faltanBox.innerHTML = faltan.length ? `
        <div class="min-w-0">
          <p class="text-sm font-semibold text-amber-200">${faltan.length === 1 ? 'Una carpeta del tutor todavía no existe' : `${faltan.length} carpetas del tutor todavía no existen`}</p>
          <p class="text-xs text-amber-200/70 truncate" title="${escapeHtml(faltan.join(' · '))}">${escapeHtml(faltan.join(' · '))}</p>
        </div>
        <button type="button" class="au-boton au-boton--suave-alerta au-boton--chico btn-create-missing-folders shrink-0">📁 Crear las que faltan</button>` : '';
      faltanBox.classList.toggle('hidden', !faltan.length);
      const btn = faltanBox.querySelector('.btn-create-missing-folders');
      if (btn) {
        btn.addEventListener('click', () => createMissingTutorFolders(btn));
      }
    }
  };

  renderMissingBox('vault-folders-missing');
  renderMissingBox('wizard-vault-folders-missing');

  renderFolderItems('vault-folders-list', 'vault-folders-count');
  renderFolderItems('wizard-vault-folders-list', 'wizard-vault-folders-count');

  bindWizardFolderEvents();
}

function bindWizardFolderEvents() {
  const form = document.getElementById('wizard-folder-form');
  if (form && !form.dataset.bound) {
    form.dataset.bound = 'true';
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('wizard-new-folder');
      const ruta = (input?.value || '').trim();
      if (!ruta) {
        setWizardFoldersMessage('Escribí el nombre de la carpeta.', true);
        input?.focus();
        return;
      }
      const boton = document.getElementById('wizard-btn-create-folder');
      if (boton) boton.disabled = true;
      try {
        const datos = await postVaultFolder(ruta);
        const creada = ruta.replace(/\\/g, '/').split('/').map(p => p.trim()).filter(Boolean).join('/');
        aplicarCarpetasDelVault(datos, true);
        if (carpetasExistentes().has(creada)) state.tutorFoldersSelected.add(creada);
        renderVaultFolders();
        if (input) input.value = '';
        setWizardFoldersMessage(`Carpeta «${creada}» creada y marcada. Guardá la selección para que el tutor la lea.`);
      } catch (err) {
        setWizardFoldersMessage(err.message || 'Error de red al crear la carpeta.', true);
      } finally {
        if (boton) boton.disabled = false;
      }
    });
  }

  const btnSave = document.getElementById('wizard-btn-save-folders');
  if (btnSave && !btnSave.dataset.bound) {
    btnSave.dataset.bound = 'true';
    btnSave.addEventListener('click', async () => {
      await saveTutorFolders(true);
    });
  }
}

function setWizardFoldersMessage(texto, esError = false) {
  const elem = document.getElementById('wizard-vault-folders-message');
  if (!elem) return;
  elem.textContent = texto;
  elem.className = `text-xs rounded-xl px-3 py-2 border ${
    esError
      ? 'bg-rose-950/40 text-rose-300 border-rose-800/60'
      : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/60'
  }`;
  elem.classList.remove('hidden');
}



async function postVaultFolder(ruta) {
  const res = await fetch('/api/vault/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ruta }),
  });
  const datos = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorText(datos, `No se pudo crear la carpeta «${ruta}».`));
  return datos;
}

async function createVaultFolder(event) {
  event.preventDefault();
  const input = document.getElementById('vault-new-folder');
  const ruta = input.value.trim();
  if (!ruta) {
    setVaultFoldersMessage('Escribí el nombre de la carpeta.', true);
    input.focus();
    return;
  }
  const boton = document.getElementById('btn-create-vault-folder');
  boton.disabled = true;
  try {
    const datos = await postVaultFolder(ruta);
    const creada = ruta.replace(/\\/g, '/').split('/').map(p => p.trim()).filter(Boolean).join('/');
    aplicarCarpetasDelVault(datos, true);
    // La carpeta nueva queda marcada: casi siempre se crea para que el tutor la lea
    if (carpetasExistentes().has(creada)) state.tutorFoldersSelected.add(creada);
    renderVaultFolders();
    input.value = '';
    setVaultFoldersMessage(`Carpeta «${creada}» creada y marcada. Guardá la selección para que el tutor la lea.`);
  } catch (err) {
    setVaultFoldersMessage(err.message || 'Error de red al crear la carpeta.', true);
  } finally {
    boton.disabled = false;
  }
}

async function createMissingTutorFolders(boton) {
  const faltan = (state.vaultFolders && state.vaultFolders.faltan) || [];
  if (!faltan.length) return;
  if (boton) boton.disabled = true;
  try {
    const res = await fetch('/api/vault/folders/create-missing', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const datos = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorText(datos, 'No se pudieron crear las carpetas faltantes.'));
    aplicarCarpetasDelVault(datos, true);
    const msg = faltan.length === 1 ? 'Se creó la carpeta del tutor.' : `Se crearon ${faltan.length} carpetas del tutor.`;
    setVaultFoldersMessage(msg);
    setWizardFoldersMessage(msg);
  } catch (err) {
    setVaultFoldersMessage(err.message || 'Error de red al crear las carpetas.', true);
    setWizardFoldersMessage(err.message || 'Error de red al crear las carpetas.', true);
    await loadVaultFolders();
  } finally {
    if (boton) boton.disabled = false;
  }
}

async function saveTutorFolders(fromWizard = false) {
  if (!state.vaultFolders) return;
  const carpetas = carpetasElegidasQueExisten();
  const setMsg = fromWizard ? setWizardFoldersMessage : setVaultFoldersMessage;
  if (!carpetas.length) {
    setMsg('Marcá al menos una carpeta para el tutor.', true);
    return;
  }
  const boton = document.getElementById(fromWizard ? 'wizard-btn-save-folders' : 'btn-save-vault-folders');
  if (boton) boton.disabled = true;
  try {
    const res = await fetch('/api/vault/tutor-folders', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ carpetas }),
    });
    const datos = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorText(datos, 'No se pudo guardar la selección.'));
    aplicarCarpetasDelVault(datos);
    const mensaje = datos.del_tutor.length === 1 ? 'Listo: el tutor lee 1 carpeta.' : `Listo: el tutor lee ${datos.del_tutor.length} carpetas.`;
    setMsg(mensaje);
    if (fromWizard) {
      const chk3 = document.getElementById('wizard-check-3');
      if (chk3) chk3.classList.remove('hidden');
    }
  } catch (err) {
    setMsg(err.message || 'Error de red al guardar la selección.', true);
  } finally {
    if (boton) boton.disabled = false;
  }
}

// --- MIS MATERIALES ---
// Los PDF, Markdown y textos que la cuenta sube desde la PC. El servidor los guarda en el espacio de la cuenta
// (25 MB por archivo, 200 MB en total) y el tutor, la cosecha y los apuntes los leen enteros.
const EXTENSIONES_DE_MATERIAL = ['.pdf', '.md', '.markdown', '.txt'];
const MEGABYTE = 1024 * 1024;
const MAX_BYTES_POR_MATERIAL = 25 * MEGABYTE;
const misMateriales = { lista: [], uso: null, subiendo: false };

function esCuentaCompartida() {
  return Boolean(state.currentUser && state.currentUser.compartida);
}

function describirBytes(bytes) {
  const valor = Number(bytes) || 0;
  if (valor === 0) return '0 MB';
  if (valor < MEGABYTE) return `${Math.max(1, Math.round(valor / 1024))} KB`;
  const megas = valor / MEGABYTE;
  const texto = megas >= 10 || Number.isInteger(megas) ? megas.toFixed(0) : megas.toFixed(1).replace('.', ',');
  return `${texto} MB`;
}

function describirFechaDeMaterial(fecha) {
  const d = new Date(fecha);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function materialPorId(id) {
  return misMateriales.lista.find(m => m.id === Number(id)) || null;
}

async function loadMisMateriales() {
  const lista = document.getElementById('materiales-lista');
  try {
    const res = await fetch('/api/materiales');
    if (!res.ok) throw new Error();
    const data = await res.json();
    misMateriales.lista = data.materiales || [];
    misMateriales.uso = data.uso || null;
  } catch (err) {
    if (lista) lista.innerHTML = '<p class="text-sm text-rose-300">No se pudieron cargar tus materiales. Probá de nuevo en un rato.</p>';
    return;
  }
  renderMisMateriales();
}

function renderBarraDeEspacio() {
  const uso = misMateriales.uso;
  const texto = document.getElementById('materiales-espacio-texto');
  const barra = document.getElementById('materiales-espacio-barra');
  if (!uso || !texto || !barra) return;
  const porcentaje = uso.tope > 0 ? Math.min(100, (uso.usado / uso.tope) * 100) : 0;
  texto.textContent = `${describirBytes(uso.usado)} de ${describirBytes(uso.tope)}`;
  barra.style.width = `${porcentaje.toFixed(1)}%`;
  // El tono va en el contenedor (au-progreso--*): la barra conserva su clase de componente
  barra.parentElement.className = `au-progreso${porcentaje >= 90 ? ' au-progreso--peligro' : (porcentaje >= 70 ? ' au-progreso--alerta' : '')}`;
}

function renderMisMateriales() {
  renderBarraDeEspacio();
  const demo = esCuentaCompartida();
  document.getElementById('materiales-aviso-demo')?.classList.toggle('hidden', !demo);
  const botonSubir = document.getElementById('btn-subir-materiales');
  if (botonSubir) {
    botonSubir.classList.toggle('hidden', demo);
    botonSubir.disabled = misMateriales.subiendo;
  }

  const lista = document.getElementById('materiales-lista');
  const cantidad = document.getElementById('materiales-cantidad');
  if (!lista) return;
  const filtro = (document.getElementById('materiales-filtro')?.value || '').trim().toLowerCase();
  const visibles = misMateriales.lista.filter(m => !filtro || m.nombre.toLowerCase().includes(filtro));
  if (cantidad) {
    const total = misMateriales.lista.length;
    cantidad.textContent = filtro ? `${visibles.length} de ${total} materiales` : `${total} material${total === 1 ? '' : 'es'}`;
  }

  if (misMateriales.lista.length === 0) {
    lista.innerHTML = Au.vacio({
      icono: '📚',
      titulo: 'Todavía no subiste materiales.',
      texto: demo ? 'En una cuenta compartida no se suben archivos.' : 'Usá «Subir materiales» para sumar tus PDF, Markdown o textos.'
    });
    return;
  }
  if (visibles.length === 0) {
    lista.innerHTML = Au.vacio({
      icono: '🔍',
      titulo: 'Sin resultados',
      texto: 'Ningún material tiene ese nombre.'
    });
    return;
  }

  lista.innerHTML = visibles.map(m => {
    const id = Number(m.id);
    const icono = m.extension === '.pdf' ? '📕' : '📝';
    return `
      <div class="au-tarjeta flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <span class="text-xl shrink-0" aria-hidden="true">${icono}</span>
          <div class="min-w-0">
            <p class="text-sm font-semibold text-white truncate" title="${escapeHtml(m.nombre)}">${escapeHtml(m.nombre)}</p>
            <p class="text-xs text-slate-400">${escapeHtml(describirBytes(m.bytes))} · ${escapeHtml(describirFechaDeMaterial(m.creado_en))}</p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-1.5 shrink-0">
          <button type="button" data-accion="preguntar-material-tutor" data-id="${id}" class="au-boton au-boton--secundario au-boton--chico"><span>🎯</span> Preguntar al tutor</button>
          <button type="button" data-accion="ver-texto-material" data-id="${id}" class="au-boton au-boton--secundario au-boton--chico"><span>📄</span> Ver texto</button>
          ${state.vectorOnline ? `<button type="button" data-accion="indexar-material" data-id="${id}" class="au-boton au-boton--secundario au-boton--chico"><span>⚡</span> Indexar</button>` : ''}
          ${demo ? '' : `<button type="button" data-accion="borrar-material" data-id="${id}" class="au-boton au-boton--peligro au-boton--chico"><span>🗑️</span> Borrar</button>`}
        </div>
      </div>`;
  }).join('');
}

// Fila de progreso de una subida; el nombre del archivo va como texto, nunca como HTML
function filaDeSubida(nombre) {
  const contenedor = document.getElementById('materiales-subidas');
  const fila = document.createElement('div');
  fila.className = 'au-tarjeta au-tarjeta--hundida flex-row items-center justify-between gap-3 text-xs';
  const nombreEl = document.createElement('span');
  nombreEl.className = 'text-slate-300 truncate';
  nombreEl.textContent = nombre;
  const estadoEl = document.createElement('span');
  fila.append(nombreEl, estadoEl);
  if (contenedor) {
    contenedor.classList.remove('hidden');
    contenedor.appendChild(fila);
  }
  return (texto, tipo = 'info') => {
    const color = { ok: 'text-emerald-400', error: 'text-rose-300', aviso: 'text-amber-300', info: 'text-slate-400' }[tipo];
    estadoEl.textContent = texto;
    estadoEl.className = `${color} shrink-0 text-right`;
  };
}

// El motivo de un rechazo, tal como lo explica el servidor (tope, tipo, PDF sin texto o repetido)
function motivoDelRechazo(xhr) {
  let detalle = '';
  try {
    detalle = JSON.parse(xhr.responseText).detail || '';
  } catch (e) {
    detalle = '';
  }
  if (detalle) return String(detalle);
  if (xhr.status === 413) return 'El archivo no entra en el espacio que te queda.';
  return 'No se pudo subir el archivo. Probá de nuevo.';
}

// Sube un archivo con XMLHttpRequest para poder mostrar el avance; resuelve con el pedido terminado, o null si se cortó
function enviarMaterial(archivo, avisarAvance) {
  return new Promise(resolve => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/materiales');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) avisarAvance(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => resolve(xhr);
    xhr.onerror = () => resolve(null);
    const formulario = new FormData();
    formulario.append('archivo', archivo);
    xhr.send(formulario);
  });
}

async function subirUnMaterial(archivo) {
  const avisar = filaDeSubida(archivo.name);
  const punto = archivo.name.lastIndexOf('.');
  const extension = punto >= 0 ? archivo.name.slice(punto).toLowerCase() : '';
  if (!EXTENSIONES_DE_MATERIAL.includes(extension)) {
    avisar('Solo se aceptan .pdf, .md, .markdown y .txt.', 'error');
    return;
  }
  if (archivo.size > MAX_BYTES_POR_MATERIAL) {
    avisar(`Pesa ${describirBytes(archivo.size)} y el tope por archivo es 25 MB.`, 'error');
    return;
  }
  avisar('Subiendo… 0%');
  const xhr = await enviarMaterial(archivo, (porcentaje) => {
    avisar(porcentaje < 100 ? `Subiendo… ${porcentaje}%` : 'Leyendo el texto…');
  });
  if (!xhr) {
    avisar('Se cortó la conexión. Probá de nuevo.', 'error');
    return;
  }
  if (xhr.status === 401) {
    window.location.assign(LOGIN_PATH);
    return;
  }
  if (xhr.status === 201) {
    avisar('Listo', 'ok');
    return;
  }
  if (xhr.status === 403 && xhr.getResponseHeader('X-Cuenta-Compartida')) mostrarAvisoDemoDestacado();
  // 409: ya estaba subido; el servidor dice con qué nombre
  avisar(motivoDelRechazo(xhr), xhr.status === 409 ? 'aviso' : 'error');
}

// Sube los archivos elegidos de a uno, para que cada uno muestre su avance y su resultado
async function subirMaterialesElegidos(input) {
  const archivos = Array.from(input.files || []);
  input.value = '';
  if (archivos.length === 0 || misMateriales.subiendo) return;
  document.getElementById('materiales-subidas')?.replaceChildren();
  misMateriales.subiendo = true;
  renderMisMateriales();
  try {
    for (const archivo of archivos) {
      await subirUnMaterial(archivo);
    }
  } finally {
    misMateriales.subiendo = false;
    await loadMisMateriales();
  }
}

async function verTextoDeMaterial(id) {
  try {
    const res = await fetch(`/api/materiales/${Number(id)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'No se pudo leer el material.');
    document.getElementById('modal-material-name').textContent = data.nombre;
    document.getElementById('modal-material-subtitle').textContent =
      `${describirBytes(data.bytes)} · ${Number(data.caracteres).toLocaleString('es-AR')} caracteres · subido el ${describirFechaDeMaterial(data.creado_en)}`;
    document.getElementById('modal-material-cortado').classList.toggle('hidden', !data.texto_cortado);
    document.getElementById('modal-material-content').textContent = data.texto;
    Au.modal.abrir('material-texto-modal');
  } catch (err) {
    showToast(err.message || 'No se pudo leer el material.', 'error');
  }
}

function closeMaterialTextoModal() {
  Au.modal.cerrar('material-texto-modal');
}

async function indexarMaterial(id, btn = null) {
  const original = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Indexando...';
  }
  try {
    const res = await fetch('/api/vectors/index-selection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: [{ type: 'material', id: String(id) }] }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'No se pudo indexar el material.');
    showToast('Material sumado al índice de apuntes.', 'success');
    checkVectorStatus();
  } catch (err) {
    showToast(err.message || 'No se pudo indexar el material.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = original;
    }
  }
}

async function borrarMaterial(id) {
  const material = materialPorId(id);
  if (!material) return;
  const confirmado = await showConfirmDialog({
    title: 'Borrar material',
    message: `¿Borrar «${material.nombre}»? Se borra el archivo y el tutor deja de usarlo. Libera ${describirBytes(material.bytes)}.`,
    confirmText: 'Borrar',
    icon: '🗑️',
    danger: true,
  });
  if (!confirmado) return;
  try {
    const res = await fetch(`/api/materiales/${Number(id)}`, { method: 'DELETE' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'No se pudo borrar el material.');
    }
    if (state.cloudAgent.selectedMaterialId === Number(id)) clearAgentFileFocus();
    showToast('Material borrado.', 'success');
  } catch (err) {
    showToast(err.message || 'No se pudo borrar el material.', 'error');
  }
  await loadMisMateriales();
}

// --- TUTOR SOBRE TUS MATERIALES Y APUNTES ---

function selectAgentMode(mode) {
  state.cloudAgent.mode = mode;
  const modes = ['explain', 'summarize', 'quiz', 'flashcards'];
  modes.forEach(m => {
    const btn = document.getElementById(`btn-agent-mode-${m}`);
    if (btn) {
      if (m === mode) {
        btn.className = 'agent-mode-btn au-boton au-boton--primario au-boton--chico';
      } else {
        btn.className = 'agent-mode-btn au-boton au-boton--secundario au-boton--chico';
      }
    }
  });
}

function runQuickAgentQuery(query) {
  const inputEl = document.getElementById('cloud-agent-input');
  if (inputEl) {
    inputEl.value = query;
  }
  askCloudAgent(query);
}

// Fija el foco del tutor en un material: la próxima pregunta se responde con ese material
function askAgentAboutMaterial(id) {
  const material = materialPorId(id);
  if (!material) return;
  const fileName = material.nombre;
  state.cloudAgent.selectedMaterialId = material.id;
  state.cloudAgent.selectedMaterialName = fileName;

  const badge = document.getElementById('agent-focus-file-badge');
  const nameEl = document.getElementById('agent-focus-file-name');
  if (badge && nameEl) {
    nameEl.textContent = fileName;
    nameEl.title = fileName;
    badge.classList.remove('hidden');
  }

  const inputEl = document.getElementById('cloud-agent-input');
  if (inputEl) {
    if (!inputEl.value.trim() || inputEl.value.startsWith('Explicar los conceptos clave')) {
      inputEl.value = `Explicar los conceptos clave de '${fileName}' y sus aplicaciones prácticas`;
    }
    inputEl.focus();
    inputEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function clearAgentFileFocus() {
  state.cloudAgent.selectedMaterialId = null;
  state.cloudAgent.selectedMaterialName = null;
  const badge = document.getElementById('agent-focus-file-badge');
  if (badge) {
    badge.classList.add('hidden');
  }
}

async function askCloudAgent(overrideQuery = null) {
  if (state.cloudAgent.isAsking) return;

  const inputEl = document.getElementById('cloud-agent-input');
  const query = overrideQuery || (inputEl ? inputEl.value.trim() : '');
  if (!query) {
    alert("Ingresá una pregunta o tema para consultar a tu biblioteca.");
    if (inputEl) inputEl.focus();
    return;
  }

  const providerSelect = document.getElementById('agent-provider-select');
  const provider = providerSelect ? providerSelect.value : 'all';
  const mode = state.cloudAgent.mode || 'explain';
  const materialId = state.cloudAgent.selectedMaterialId || null;

  const btnAsk = document.getElementById('btn-ask-cloud-agent');
  const iconAsk = document.getElementById('agent-ask-icon');
  const textAsk = document.getElementById('agent-ask-text');
  const resultContainer = document.getElementById('cloud-agent-result');

  state.cloudAgent.isAsking = true;
  if (btnAsk) btnAsk.disabled = true;
  if (iconAsk) iconAsk.innerText = '⏳';
  if (textAsk) textAsk.innerText = 'Preguntando...';

  try {
    const payload = {
      query: query,
      mode: mode,
      provider: provider,
      material_id: materialId,
      historial: (state.cloudAgent.history || [])
        .slice(-10)
        .map(m => ({
          rol: m.rol,
          contenido: typeof m.contenido === 'string' ? m.contenido.slice(0, 4000) : ''
        }))
    };

    const res = await fetch('/api/mcp/agent/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      state.cloudAgent.lastResult = data;
      if (!state.cloudAgent.history) {
        state.cloudAgent.history = [];
      }
      state.cloudAgent.history.push({ rol: 'usuario', contenido: typeof query === 'string' ? query.slice(0, 4000) : '' });
      if (data.answer) {
        state.cloudAgent.history.push({ rol: 'asistente', contenido: typeof data.answer === 'string' ? data.answer.slice(0, 4000) : '' });
      }
      if (state.cloudAgent.history.length > 20) {
        state.cloudAgent.history = state.cloudAgent.history.slice(-20);
      }
      renderCloudAgentResult(data);
      if (resultContainer) {
        resultContainer.classList.remove('hidden');
        resultContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    } else {
      const err = await res.json().catch(() => ({}));
      alert("Error al consultar al agente: " + (err.detail || "Verificá la conexión con el servidor."));
    }
  } catch (err) {
    console.error("Error en askCloudAgent:", err);
    alert("Error de red al consultar el agente de estudio.");
  } finally {
    state.cloudAgent.isAsking = false;
    if (btnAsk) btnAsk.disabled = false;
    if (iconAsk) iconAsk.innerText = '⚡';
    if (textAsk) textAsk.innerText = 'Preguntar';
  }
}

function renderAgentMarkdown(text) {
  if (!text) return '';
  let str = escapeHtml(text);

  // Bloques de código
  str = str.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/gi, (match, lang, code) => {
    return `<pre class="p-3 my-2.5 bg-slate-900 border border-slate-800 rounded-xl font-mono text-xs text-sky-300 overflow-x-auto"><code>${code.trim()}</code></pre>`;
  });

  // Código inline
  str = str.replace(/`([^`]+)`/g, '<code class="bg-slate-900 text-sky-300 border border-slate-800/80 px-1.5 py-0.5 rounded text-xs font-mono">$1</code>');

  // Encabezados
  str = str.replace(/^### (.*$)/gim, '<h4 class="text-sm font-bold text-white mt-4 mb-1.5 flex items-center gap-1.5"><span>🔹</span> $1</h4>');
  str = str.replace(/^## (.*$)/gim, '<h3 class="text-base font-bold text-sky-400 mt-4 mb-2 pb-1 border-b border-slate-800/80">$1</h3>');
  str = str.replace(/^# (.*$)/gim, '<h2 class="text-lg font-extrabold text-white mt-3 mb-2">$1</h2>');

  // Negrita e itálica
  str = str.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-white">$1</strong>');
  str = str.replace(/\*([^*]+)\*/g, '<em class="italic text-slate-300">$1</em>');

  // Citas / Callouts
  str = str.replace(/^>\s?(.*$)/gim, '<blockquote class="border-l-4 border-sky-500 pl-3 py-1 my-2 bg-sky-950/20 text-slate-300 italic text-xs rounded-r-lg">$1</blockquote>');

  // Listas con viñetas
  str = str.replace(/^[-*]\s+(.*$)/gim, '<div class="flex items-start gap-2 my-1 text-slate-300 text-xs sm:text-sm"><span class="text-sky-400 mt-1 shrink-0">•</span><span>$1</span></div>');

  // Listas numeradas
  str = str.replace(/^(\d+)\.\s+(.*$)/gim, '<div class="flex items-start gap-2 my-1 text-slate-300 text-xs sm:text-sm"><span class="font-bold text-sky-400 shrink-0">$1.</span><span>$2</span></div>');

  // Saltos de línea de párrafos
  str = str.replace(/\n\n/g, '<div class="h-2"></div>');

  return str;
}

function renderCloudAgentResult(data) {
  const titleEl = document.getElementById('agent-result-title');
  const modelEl = document.getElementById('agent-result-model');
  const timeEl = document.getElementById('agent-result-time');
  const bodyEl = document.getElementById('agent-response-body');
  const sourcesContainer = document.getElementById('agent-sources-container');
  const sourcesList = document.getElementById('agent-sources-list');
  const conceptsContainer = document.getElementById('agent-concepts-container');
  const conceptsList = document.getElementById('agent-concepts-list');

  const modeLabels = {
    explain: '💡 Explicación Académica',
    summarize: '📋 Resumen Estructurado (SOP)',
    quiz: '🎯 Autoevaluación Feynman',
    flashcards: '🇬🇧 Vocabulario Técnico FSRS'
  };

  if (titleEl) titleEl.innerText = modeLabels[data.mode] || 'Respuesta del Agente';
  if (modelEl) {
    const isHeuristic = data.is_fallback || (data.model_used && (data.model_used.includes('heuristic') || data.model_used.includes('offline')));
    modelEl.innerText = isHeuristic ? (data.rotulo || 'sin IA') : (data.model_used || 'Gemini AI');
    modelEl.className = isHeuristic ? 'au-insignia au-insignia--alerta au-insignia--mono' : 'text-sky-400 font-mono text-xs';
  }
  if (timeEl) timeEl.innerText = `${(data.elapsed_seconds || 0.1).toFixed(2)}s`;

  if (bodyEl) {
    let html = '';
    if (data.encontrado_en_tus_notas === false) {
      html += '<p class="text-xs text-amber-300 font-medium mb-2 flex items-center gap-1.5"><span>ℹ️</span> No lo encontré en tus notas.</p>';
    }
    html += renderAgentMarkdown(data.answer);
    bodyEl.innerHTML = html;
  }

  // Fuentes citadas
  if (sourcesList && data.sources) {
    if (data.sources.length === 0) {
      if (sourcesContainer) sourcesContainer.classList.add('hidden');
    } else {
      if (sourcesContainer) sourcesContainer.classList.remove('hidden');
      sourcesList.innerHTML = data.sources.map(s => {
        const esMaterial = s.provider === 'materiales' || s.material_id != null;
        const icon = esMaterial ? '📚' : (s.name.includes('[CURSO]') ? '🎓' : (s.name.includes('[LIBRO]') ? '📖' : '🧠'));
        const cursoOOrigen = s.course_hint || (esMaterial ? 'tus materiales' : 'tus apuntes');
        const simBadge = s.similitud != null ? ` • ${Math.round(s.similitud * 100)}% similitud` : '';
        const detalle = `${cursoOOrigen}${simBadge}`;
        return `
          <div class="au-insignia ${esMaterial ? 'au-insignia--primario' : ''}">
            <span aria-hidden="true">${icon}</span>
            <span class="font-bold">${escapeHtml(s.name)}</span>
            <span class="text-slate-400 text-xs">(${escapeHtml(detalle)})</span>
          </div>
        `;
      }).join('');
    }
  }

  // Conceptos clave
  if (conceptsList && data.key_concepts) {
    if (data.key_concepts.length === 0) {
      if (conceptsContainer) conceptsContainer.classList.add('hidden');
    } else {
      if (conceptsContainer) conceptsContainer.classList.remove('hidden');
      conceptsList.innerHTML = data.key_concepts.map(c => `
        <span class="au-insignia au-insignia--mono">
          #${escapeHtml(c)}
        </span>
      `).join('');
    }
  }
}

async function saveCloudAgentNoteToVault() {
  const result = state.cloudAgent.lastResult;
  if (!result) {
    alert("No hay ninguna respuesta generada para guardar.");
    return;
  }

  const btn = document.getElementById('btn-agent-save-note');
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Guardando...';
  }

  try {
    const payload = {
      title: result.suggested_note_title || result.query.slice(0, 50),
      content: result.suggested_note_markdown || result.answer,
      folder: (result.sources && result.sources.length > 0 && result.sources[0].course_hint) 
        ? result.sources[0].course_hint 
        : 'Tutor'
    };

    const res = await fetch('/api/mcp/agent/save-note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      alert(`✅ ¡Apunte guardado exitosamente en Mis notas!\n\nRuta: ${data.relative_path}`);
    } else {
      const err = await res.json().catch(() => ({}));
      alert("Error al guardar en Mis notas: " + (err.detail || "Error desconocido"));
    }
  } catch (err) {
    console.error("Error al guardar apunte en Mis notas:", err);
    alert("Error de red al guardar apunte en Mis notas.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }
}

async function harvestCloudAgentCards() {
  const result = state.cloudAgent.lastResult;
  if (!result || !result.key_concepts || result.key_concepts.length === 0) {
    alert("No se detectaron conceptos técnicos clave en esta respuesta para cosechar.");
    return;
  }

  const btn = document.getElementById('btn-agent-harvest-cards');
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Cosechando...';
  }

  try {
    const sourcesList = (result.sources && result.sources.length > 0) ? result.sources.map(s => s.name) : [];
    const payload = {
      concepts: result.key_concepts,
      source: sourcesList.length > 0 ? sourcesList[0] : "Tutor de Aulento",
      sources: sourcesList,
      context: result.answer || ""
    };

    const res = await fetch('/api/mcp/agent/harvest-cards', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      const rotuloInfo = data.rotulo ? ` [${data.rotulo}]` : '';
      alert(`🌾 Cosecha FSRS completada${rotuloInfo}:\n\n• Tarjetas nuevas agregadas: ${data.harvested_count}\n• Conceptos procesados: ${data.total_submitted}\n• Duplicadas descartadas: ${data.duplicates}`);
      // Actualizar contador del mazo en UI
      if (typeof loadFsrsStatus === 'function') {
        loadFsrsStatus();
      }
    } else {
      const err = await res.json().catch(() => ({}));
      alert("Error al cosechar tarjetas: " + (err.detail || "Error desconocido"));
    }
  } catch (err) {
    console.error("Error al cosechar flashcards:", err);
    alert("Error de red al cosechar tarjetas para FSRS.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }
}

function copyAgentResponseMarkdown() {
  const result = state.cloudAgent.lastResult;
  if (!result || !result.answer) {
    alert("No hay respuesta para copiar.");
    return;
  }
  const textToCopy = result.suggested_note_markdown || result.answer;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(textToCopy).then(() => {
      alert("📋 Respuesta y apunte copiado al portapapeles.");
    }).catch(() => {
      fallbackCopyText(textToCopy);
    });
  } else {
    fallbackCopyText(textToCopy);
  }
}

function fallbackCopyText(text) {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  document.body.appendChild(textArea);
  textArea.select();
  try {
    document.execCommand('copy');
    alert("📋 Respuesta copiada al portapapeles.");
  } catch (err) {
    prompt("Copiá el texto manualmente:", text);
  }
  document.body.removeChild(textArea);
}

// ==========================================
// SECCIÓN 8: MOTOR VECTORIAL & RAG (POSTGRESQL + PGVECTOR)
// ==========================================

async function checkVectorStatus() {
  const badge = document.getElementById('vector-status-badge');
  const tabStatusBadge = document.getElementById('vector-tab-status-badge');
  const tabBadge = document.getElementById('tab-brain-badge') || document.getElementById('tab-vectors-badge');
  const dashPill = document.getElementById('dash-vector-pill');
  const hdrVector = document.getElementById('hdr-vector');
  const kpiConn = document.getElementById('vector-kpi-connected');
  const kpiExt = document.getElementById('vector-kpi-extension');
  const kpiEmb = document.getElementById('vector-kpi-embeddings');
  const kpiModel = document.getElementById('vector-kpi-model');

  try {
    const res = await fetch('/api/vectors/status');
    if (!res.ok) throw new Error('No se pudo consultar el índice de apuntes');
    const data = await res.json();
    const indiceEncendido = !!(data.indice_disponible ?? data.postgres_connected);
    state.vectorOnline = indiceEncendido;

    const nombreAlmacen = (data.almacen === 'sqlite-vec' || data.almacen === 'sqlite')
      ? 'Índice local'
      : (data.almacen === 'pgvector' || data.almacen === 'postgres')
        ? 'Índice del servidor'
        : 'Índice local';

    if (indiceEncendido) {
      if (badge) {
        badge.className = 'au-insignia au-insignia--exito';
        badge.innerText = `🟢 ${nombreAlmacen} activo`;
      }
      if (tabStatusBadge) {
        tabStatusBadge.className = 'au-insignia au-insignia--exito';
        tabStatusBadge.innerText = `🟢 ${nombreAlmacen} activo`;
      }
      if (tabBadge) {
        tabBadge.className = 'au-insignia au-insignia--exito au-insignia--mono';
        tabBadge.innerText = 'Activo';
      }
      if (dashPill) {
        dashPill.className = 'au-insignia au-insignia--exito au-insignia--mono';
        dashPill.innerText = `${nombreAlmacen} activo (${data.total_embeddings} fragmentos)`;
      }
      if (hdrVector) {
        hdrVector.className = 'au-insignia au-insignia--primario cursor-pointer';
        hdrVector.innerText = `🧠 ${nombreAlmacen}: ${data.total_embeddings} fragmentos`;
      }
      if (kpiConn) {
        kpiConn.innerHTML = '<span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span> Encendido';
      }
      if (kpiExt) kpiExt.innerText = nombreAlmacen;
      if (kpiEmb) kpiEmb.innerText = data.total_embeddings || 0;
      if (kpiModel) kpiModel.innerText = String(data.embedding_model || '').startsWith('local') ? 'Local, sin IA' : (data.embedding_model || '—');
    } else {
      const motivoTexto = data.motivo_no_disponible || 'solo datos locales';
      const motivoEscapado = escapeHtml(motivoTexto);
      if (badge) {
        badge.className = 'au-insignia';
        badge.innerText = `⚪ ${nombreAlmacen} apagado`;
      }
      if (tabStatusBadge) {
        tabStatusBadge.className = 'au-insignia';
        tabStatusBadge.innerText = `⚪ ${nombreAlmacen} apagado`;
      }
      if (tabBadge) {
        tabBadge.className = 'au-insignia au-insignia--mono';
        tabBadge.innerText = 'Apagado';
      }
      if (dashPill) {
        dashPill.className = 'au-insignia au-insignia--mono';
        dashPill.innerText = `${nombreAlmacen} apagado`;
      }
      if (hdrVector) {
        hdrVector.className = 'au-insignia cursor-pointer';
        hdrVector.innerText = `🧠 ${nombreAlmacen}: apagado`;
      }
      if (kpiConn) {
        kpiConn.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span> Apagado: ${motivoEscapado}`;
      }
      if (kpiExt) kpiExt.innerText = data.motivo_no_disponible ? motivoTexto : 'Inactivo';
      if (kpiEmb) kpiEmb.innerText = '0';
      if (kpiModel) kpiModel.innerText = '—';
    }
  } catch (err) {
    if (badge) {
      badge.className = 'au-insignia au-insignia--peligro';
      badge.innerText = '⚠️ Desconectado';
    }
    if (hdrVector) {
      hdrVector.className = 'au-insignia au-insignia--peligro';
      hdrVector.innerText = '🧠 Índice: sin conexión';
    }
    state.vectorOnline = false;
  }
  actualizarAvisoTutorDemo();
}

// En la cuenta demo sin base vectorial, el tutor muestra un aviso en lugar de fallar, y la cabecera y el panel
// no muestran "pgvector: Offline". Con la base conectada (como en la grabación del video) no cambia nada.
function actualizarAvisoTutorDemo() {
  const esDemo = esCuentaCompartida();
  const apagado = esDemo && state.vectorOnline === false;
  const aviso = document.getElementById('demo-tutor-aviso');
  // Sin base vectorial o sin clave de IA, el tutor de la demo no puede responder
  if (aviso) aviso.classList.toggle('hidden', !(apagado || esDemoSinIA()));
  ['hdr-vector', 'dash-vector-pill', 'tab-brain-badge'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden', apagado);
  });
}

function goToVectorSection() {
  switchTab('brain');
  setTimeout(() => {
    const input = document.getElementById('cloud-agent-input');
    if (input) input.focus();
  }, 100);
}

async function refreshBrainStatus() {
  await Promise.all([
    checkVectorStatus(),
    loadMisMateriales(),
  ]);
  renderMisMateriales();
  renderSystemHealth();
}

function executeVectorSearchFromInput() {
  const mainInput = document.getElementById('cloud-agent-input');
  const vecInput = document.getElementById('vector-search-input');
  if (mainInput && vecInput) {
    vecInput.value = mainInput.value;
  }
  executeVectorSearch();
}

// El tablero no busca por su cuenta: le pasa la pregunta al tutor, que combina palabras y vectores y cita (059 R4)
function askTutorFromDashboard() {
  const input = document.getElementById('dash-vector-input');
  const query = input ? input.value.trim() : '';
  if (!query) {
    alert('Escribí una pregunta.');
    return;
  }
  switchTab('brain');
  runQuickAgentQuery(query);
}

async function syncAllCatalogToVectors() {
  const btn = document.getElementById('btn-sync-vectors');
  const originalText = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Indexando...';
  }

  try {
    const res = await fetch('/api/vectors/sync-catalog', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Error en indexación de vectores');
    }

    alert(`🎉 ¡Indexación completada!\n\n• Indexados: ${data.indexados ?? data.indexed_materials ?? 0}\n• Salteados (sin cambios): ${data.salteados ?? 0}\n• Fallidos: ${data.fallidos ?? 0}\n• Fragmentos totales: ${data.total_chunks ?? 0}`);
    await checkVectorStatus();
  } catch (err) {
    alert(`⚠️ No se pudo indexar el catálogo:\n${err.message}\n\nEl servicio de vectores no está disponible en este momento.`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }
}

async function executeVectorSearch() {
  let input = document.getElementById('vector-search-input');
  let query = input ? input.value.trim() : '';
  if (!query) {
    const mainInput = document.getElementById('cloud-agent-input');
    if (mainInput && mainInput.value.trim()) {
      query = mainInput.value.trim();
      if (input) input.value = query;
    }
  }
  if (!query) {
    alert('Ingresa una consulta en lenguaje natural.');
    return;
  }
  const resultsContainer = document.getElementById('vector-search-results');
  const resultsList = document.getElementById('vector-search-results-list');

  if (resultsContainer) resultsContainer.classList.remove('hidden');
  if (resultsList) resultsList.innerHTML = '<div class="text-xs text-slate-400 italic py-2">Buscando en tus apuntes...</div>';

  try {
    const res = await fetch('/api/vectors/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query, limit: 5, min_similarity: 0.25 })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Error en búsqueda semántica');
    }

    if (!data.matches || data.matches.length === 0) {
      resultsList.innerHTML = '<div class="p-3 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-400">No se encontraron fragmentos con suficiente similitud semántica. Prueba indexando el catálogo primero.</div>';
      return;
    }

    resultsList.innerHTML = data.matches.map(m => {
      const pct = Math.round(m.similarity * 100);
      const isCourse = m.source_type === 'course';
      return `
        <div class="p-3.5 bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-xl space-y-2 transition">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="text-sm">${isCourse ? '🎓' : '📖'}</span>
              <span class="font-bold text-white text-xs">${escapeHtml(m.source_title)}</span>
              <span class="au-insignia au-insignia--mono">${escapeHtml(m.source_type)}</span>
            </div>
            <span class="au-insignia au-insignia--mono ${pct >= 70 ? 'au-insignia--exito' : 'au-insignia--primario'}">
              ${pct}% match
            </span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-2.5 rounded-lg font-mono border border-slate-900">
            ${escapeHtml(m.chunk_text)}
          </p>
        </div>
      `;
    }).join('');
  } catch (err) {
    if (resultsList) {
      resultsList.innerHTML = `<div class="p-3 bg-rose-950/40 border border-rose-900/60 rounded-xl text-xs text-rose-300 space-y-1">
        <p class="font-bold">⚠️ La búsqueda en tus apuntes no está disponible</p>
        <p>${escapeHtml(err.message)}</p>
        <p class="text-xs text-slate-400 mt-1">El servicio de búsqueda vectorial no está disponible en este momento.</p>
      </div>`;
    }
  }
}

// ==========================================
// INDEXACIÓN SELECTIVA VECTORIAL (PGVECTOR + GEMINI)
// ==========================================

async function indexSingleBook(bookId, btn = null) {
  const origHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> ...';
  }
  try {
    const res = await fetch(`/api/vectors/index-book/${bookId}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'No se pudo indexar el libro');
    alert(`🎉 ¡Libro "${data.title}" sumado al índice de apuntes!\n• Fragmentos: ${data.chunks}`);
    if (btn) btn.innerHTML = '<span>✅</span> Listo';
    await checkVectorStatus();
  } catch (err) {
    alert(`⚠️ No se pudo indexar el libro: ${err.message}`);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

async function indexSingleCourse(courseId, btn = null) {
  const origHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> ...';
  }
  try {
    const res = await fetch(`/api/vectors/index-course/${courseId}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'No se pudo indexar el curso');
    alert(`🎉 ¡Curso "${data.title}" sumado al índice de apuntes!\n• Fragmentos: ${data.chunks}`);
    if (btn) btn.innerHTML = '<span>✅</span> Listo';
    await checkVectorStatus();
  } catch (err) {
    alert(`⚠️ No se pudo indexar el curso: ${err.message}`);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

async function openSelectiveIndexModal() {
  const modal = document.getElementById('selective-index-modal');
  const listEl = document.getElementById('selective-index-list');
  if (!modal || !listEl) return;

  Au.modal.abrir('selective-index-modal');
  listEl.innerHTML = '<p class="text-slate-400 text-xs italic py-4 text-center animate-pulse">Cargando catálogo y materiales...</p>';

  try {
    let books = state.books || [];
    let platforms = state.platforms || [];
    await loadMisMateriales();
    const materiales = misMateriales.lista;

    let courses = [];
    platforms.forEach(p => {
      if (p.cursos) {
        p.cursos.forEach(c => courses.push({ ...c, platform_name: p.nombre }));
      }
    });

    let html = '';

    // Sección 1: Cursos
    html += `
      <div class="space-y-3 pt-1">
        <h4 class="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center gap-1.5">
          <span>🎓</span> Cursos Académicos (${courses.length})
        </h4>
        <div class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
          ${courses.length === 0 ? '<p class="text-xs text-slate-500 italic">No hay cursos registrados.</p>' : courses.map(c => `
            <label class="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 hover:border-slate-700 cursor-pointer transition text-xs">
              <div class="flex items-center gap-2.5 truncate">
                <input type="checkbox" name="selective-item" data-type="course" data-id="${c.id}" data-accion="actualizar-conteo-indice-selectivo" class="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0">
                <span class="font-medium text-white truncate">${escapeHtml(c.nombre_curso)}</span>
              </div>
              <span class="text-xs text-slate-400 font-mono shrink-0 ml-2">${escapeHtml(c.platform_name || 'Curso')}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `;

    // Sección 2: Libros Técnicos
    html += `
      <div class="space-y-3 pt-4">
        <h4 class="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
          <span>📖</span> Libros Técnicos (${books.length})
        </h4>
        <div class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
          ${books.length === 0 ? '<p class="text-xs text-slate-500 italic">No hay libros registrados.</p>' : books.map(b => `
            <label class="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 hover:border-slate-700 cursor-pointer transition text-xs">
              <div class="flex items-center gap-2.5 truncate">
                <input type="checkbox" name="selective-item" data-type="book" data-id="${b.id}" data-accion="actualizar-conteo-indice-selectivo" class="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0">
                <span class="font-medium text-white truncate">${escapeHtml(b.titulo)}</span>
              </div>
              <span class="text-xs text-slate-400 font-mono shrink-0 ml-2">${escapeHtml(b.autor || 'Técnico')}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `;

    // Sección 3: Mis materiales
    if (materiales.length > 0) {
      html += `
        <div class="space-y-3 pt-4">
          <h4 class="text-xs font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
            <span>📚</span> Mis materiales (${materiales.length})
          </h4>
          <div class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            ${materiales.map(m => `
              <label class="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 hover:border-slate-700 cursor-pointer transition text-xs">
                <div class="flex items-center gap-2.5 truncate">
                  <input type="checkbox" name="selective-item" data-type="material" data-id="${Number(m.id)}" data-accion="actualizar-conteo-indice-selectivo" class="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0">
                  <span class="font-medium text-white truncate">${escapeHtml(m.nombre)}</span>
                </div>
                <span class="text-xs text-slate-400 font-mono shrink-0 ml-2">${escapeHtml(describirBytes(m.bytes))}</span>
              </label>
            `).join('')}
          </div>
        </div>
      `;
    }

    listEl.innerHTML = html;
    updateSelectiveIndexCount();
  } catch (err) {
    listEl.innerHTML = `<p class="text-xs text-rose-400 py-3">Error al cargar elementos para selección: ${escapeHtml(err.message)}</p>`;
  }
}

function closeSelectiveIndexModal() {
  Au.modal.cerrar('selective-index-modal');
}

function toggleSelectAllIndexItems(check) {
  const checkboxes = document.querySelectorAll('input[name="selective-item"]');
  checkboxes.forEach(cb => { cb.checked = check; });
  updateSelectiveIndexCount();
}

function updateSelectiveIndexCount() {
  const checked = document.querySelectorAll('input[name="selective-item"]:checked');
  const countEl = document.getElementById('selective-index-count');
  const btnSubmit = document.getElementById('btn-submit-selective-index');
  if (countEl) {
    countEl.innerText = `${checked.length} ${checked.length === 1 ? 'seleccionado' : 'seleccionados'}`;
  }
  if (btnSubmit) {
    btnSubmit.disabled = (checked.length === 0);
    btnSubmit.innerHTML = `<span>⚡</span> Indexar (${checked.length})`;
  }
}

async function executeSelectiveIndexing() {
  const checked = document.querySelectorAll('input[name="selective-item"]:checked');
  if (checked.length === 0) {
    alert("Elegí al menos un curso, libro o material para indexar.");
    return;
  }

  const items = Array.from(checked).map(cb => ({
    type: cb.getAttribute('data-type'),
    id: cb.getAttribute('data-id')
  }));

  const btn = document.getElementById('btn-submit-selective-index');
  const origHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Indexando...';
  }

  try {
    const res = await fetch('/api/vectors/index-selection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Error en indexación selectiva');

    alert(`🎉 ¡Indexación selectiva completada con éxito!\n\n• Ítems procesados: ${data.total_indexed}\n• Fragmentos indexados: ${data.total_chunks}`);
    closeSelectiveIndexModal();
    await checkVectorStatus();
  } catch (err) {
    alert(`⚠️ No se pudo completar la indexación selectiva:\n${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

