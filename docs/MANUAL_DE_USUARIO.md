---
type: Manual
title: "Manual de Usuario: Interfaz Web de Aulento"
description: "Guía interactiva de uso de la interfaz web de Aulento: primer ingreso, registro con invitación, modo demo interactivo, asistente de onboarding y detalle operativo de cada una de las 10 pestañas del panel lateral."
generated:
  by: process:claude-code
  at: 2026-11-05T00:00:00Z
---

# Manual de Usuario: Interfaz Web de Aulento

Bienvenido a **Aulento**, tu sistema operativo de estudio personal local-first con inteligencia artificial adaptativa, repetición espaciada inteligente, integración con Obsidian Vault y tus materiales de estudio (PDF, Markdown y textos) subidos desde la PC.

Este manual describe el funcionamiento completo de la interfaz web accesible desde cualquier navegador moderno en `http://127.0.0.1:8000` (o el host/puerto configurado en tu despliegue).

---

## Primer Ingreso y Autenticación

En tu computadora (modo local) no hay ingreso: abrís la aplicación y entrás directo a tu cuenta. Si todavía no existe, se crea sola, sin contraseña.


---

## Asistente de Onboarding

La primera vez que ingresás con una cuenta nueva, Aulento te guiará con un asistente de bienvenida (**Onboarding Wizard**) de 4 pasos:

1. **Configuración de Inteligencia Artificial:** Elegí tu proveedor preferido (Gemini, Anthropic Claude u OpenAI) e ingresá tu clave de API personal (se almacena cifrada con AES-GCM en tu base de datos privada).
2. **Materiales de Estudio:** Cargá el mazo base de inglés técnico con 1 clic o sumá tus primeras rutas, libros y cursos.
3. **Carpetas del Tutor:** Revisá las carpetas por defecto de tu vault («04 Knowledge», «06 Raw», «02 MOCs»), creá nuevas si las necesitás y elegí cuáles lee el tutor. Podés omitir este paso sin cambiar nada.
4. **Resumen y Acción Inmediata:** Revisá el estado de tu entorno y elegí por dónde empezar (armar plan de hoy, repasar inglés o explorar tu ruta).

> [!TIP]
> Podés volver a ejecutar o revisar el estado del onboarding en cualquier momento desde la pestaña de **Configuración** o desde el menú de usuario.

---

## Navegación por la Barra Lateral

La barra lateral izquierda organiza el flujo de trabajo en 4 grandes grupos, 10 pestañas especializadas y una sección dedicada a **Documentación & Ayuda**:

- **Principal:** Dashboard y Cronograma.
- **Aprendizaje:** Cursos, Libros y Rutas.
- **Retención & IA:** Inglés Técnico, Cerebro & Tutor IA y Repaso Activo.
- **Sistema:** Configuración y Administración (para administradores).
- **Documentación & Ayuda:** Manual de Usuario interactivo y Documentación técnica de la API.

---

## Dashboard

El centro de control de tu jornada diaria de aprendizaje.

- **Daily Briefing Ejecutivo:** Tarjeta superior con saludo contextual, racha de estudio, nivel de urgencia pedagógica y resumen inmediato de tarjetas pendientes, cursadas activas y libros en lectura.
- **Métricas Clave:** Tarjetas KPI con horas estudiadas en la semana, tarjetas de repaso diario para hoy, cursos activos y racha actual de estudio continuo.
- **Racha y Actividad Diaria:** Visualizador de días consecutivos de estudio y mapa de calor (*heatmap*) estilo GitHub con intensidad de sesiones de los últimos meses.
- **Acceso Rápido al Pomodoro:** Temporizador de enfoque con bloques de 25 minutos y descansos de 5 minutos, con registro automático de sesiones completadas.
- **Acciones Rápidas:** Botones directos para planificar sesión inteligente, agregar un curso, registrar avance de libro, iniciar drill de inglés o crear una nueva ruta de aprendizaje.

---

## Cronograma

Gestor semanal de bloques horarios de estudio inspirado en calendarios de alto rendimiento.

- **Vista Semanal de Bloques:** Grilla de Lunes a Domingo con franjas horarias configurables y códigos de color según la materia o disciplina.
- **Alta y Edición de Bloques:** Añadí bloques especificando día, hora de inicio, hora de fin, materia/tópico y notas adicionales.
- **Exportar a Google Calendar:** el botón abre tres opciones. Un enlace por bloque que crea el evento semanal en Google Calendar; la descarga del archivo `.ics` para importarlo una vez; y la **suscripción**, que se actualiza sola.
- **Suscripción al calendario:** tocá **Crear mi dirección**, copiala y pegala en Google Calendar en *Otros calendarios → Desde URL* (en Apple Calendar: *Archivo → Nueva suscripción*). La dirección se muestra una sola vez y quien la tenga ve tu cronograma: si la compartiste sin querer, creá una nueva y la anterior deja de funcionar. Google puede tardar unas horas en traer los cambios. En la instalación local, Google no llega a tu PC: usá la descarga.
- **Zona horaria:** cada evento lleva la zona de tu cuenta (por defecto, Buenos Aires), así el calendario muestra la hora que cargaste y no la corre.
- **Planificador Adaptativo Inteligente:** Motor de optimización diaria que cruza tarjetas de repaso vencidas, cursos prioritarios del Hub y tramos pendientes de lectura técnica. Permite seleccionar los minutos disponibles (15 a 120 min) y genera un plan estructurado en 3 fases pedagógicas (Warmup, Deep Work Académico y Lectura Activa con descansos Pomodoro), con inserción automática en 1 clic en la agenda del día.

> [!TIP]
> Si te suscribís desde el calendario del teléfono, podés configurar ahí mismo un aviso unos minutos antes de cada bloque.

---

## Cursos

Hub de seguimiento de plataformas educativas (Digital House, Coursera, Google Cloud Skills Boost, Humai, Platzi, Anthropic Academy, etc.).

- **Catálogo de Plataformas:** Organización jerárquica de plataformas y cursos asociados.
- **Control de Avance:** Barra de progreso porcentual interactiva (0% a 100%), cantidad de módulos completados y estado del curso (`en_curso`, `pausado`, `completado`).
- **Apertura de Carpeta Local:** Botón para abrir la carpeta de archivos y código del curso directamente en el explorador de tu sistema operativo.
- **Vinculación con Obsidian:** Generación automática de notas de clase estructuradas para el curso en tu Vault.
- **Sincronización Automática de Progreso:**
  - **Google Cloud Skills Boost:** Botón "Sync" en la tarjeta del curso o comando CLI `aulento hub sync-google-skills <perfil_url>` para consultar perfiles públicos (`https://www.cloudskillsboost.google/public_profiles/<id>`), detectar insignias ganadas y cursos completados, con opción `--auto-import` para dar de alta automáticamente insignias como cursos completados.
  - **Coursera, Humai y Digital House:** Adaptadores específicos para calcular avances basados en módulos aprobados, checkpoints o clases dictadas (`modulos_completados / total_modulos * 100`).
  - **Webhook Universal de Cursos:** Endpoint `POST /api/hub/sync/webhook` autenticado con Bearer tokens (`mcp_tokens`) para que extensiones de navegador (Tampermonkey), Atajos o scripts cURL reporten avances en tiempo real.
  - **Registro Reactivo de Hábitos:** Cada avance positivo registrado por sincronización o webhook genera una sesión de estudio automática en el `ActivityTracker`, incrementando la racha diaria y el mapa de calor.

---

## Libros

Reading Tracker para libros técnicos y manuales de referencia profesional.

- **Seguimiento por Páginas y Capítulos:** Registrá la página actual y el capítulo por el que vas para que el sistema calcule tu velocidad de lectura y fecha estimada de finalización.
- **Estados de Lectura:** Marcá libros como `leyendo`, `pausado`, `por_leer` o `completado`.
- **Indexación Vectorial:** Botón para vectorizar fragmentos clave del libro en el almacén de vectores y consultarlos con búsqueda semántica desde el Tutor de IA (local en SQLite con sqlite-vec, o PostgreSQL en la nube).
- **Sincronización en la Nube con Google Play Libros:** Vinculá tu cuenta de Google mediante OAuth 2.0 para sincronizar automáticamente estantes de lectura (`Leyendo actualmente` y `Leídos`) y posiciones exactas de lectura en porcentaje o capítulos.
- **Anotar lo que leés con Atajos de Apple:** la pantalla de Atajos explica paso a paso cómo armar un atajo en el iPhone, iPad o Mac. Atajos no puede leer la página de la app Libros: el atajo te la pregunta y vos la escribís. El atajo usa un **código de libros** que creás en esa misma pantalla y que solo sirve para anotar páginas (no abre nada más de tu cuenta); se muestra una vez y lo podés desactivar o reemplazar. Si el servidor tiene publicado un atajo listo, aparece el botón **Agregar atajo**. En la versión local el atajo no llega a la PC; desde el iPhone hace falta la versión en la nube.
- **Active Recall Conceptual con IA:** Botón "Quiz" en la tarjeta del libro o comando `aulento books quiz <id>` para generar cuestionarios conceptuales adaptados al tramo leído (capítulos y páginas actuales). Tras responder, el mentor de IA emite una evaluación formativa con aciertos, áreas de mejora, explicación de referencia y registra automáticamente una sesión de estudio de 10 minutos en tu historial.
- **Cosecha Automatizada de Tarjetas:** Botón "Cosechar" o comando `aulento books harvest <id>` para extraer términos de inglés técnico y conceptos de arquitectura del tramo leído, previsualizar las tarjetas generadas e incorporarlas con un clic al mazo de repaso diario evitando duplicados.

---

## Rutas

Motor pedagógico de Rutas de Aprendizaje adaptativas estructuradas en módulos y temas.

- **Diseñador de Rutas:** Creá rutas desde cero, utilizando plantillas precargadas o importando sílabos en formato JSON o PDF universitario.
- **Grafo de Prerrequisitos Interactivo:** Visualización gráfica e interactiva de dependencias entre temas, con detección de cuellos de botella y sugerencia algorítmica del "siguiente tema óptimo a estudiar". Cuenta con motor SVG nativo en memoria con zoom suave anclado al cursor y navegación fluida.
- **Generador de Clases Magistrales:** Con un solo clic, el motor de IA redacta la lección técnica completa del tema seleccionado aplicando el perfil pedagógico de la ruta.
- **Historial de Versiones:** Comparador y restaurador de versiones anteriores de lecciones generadas.
- **Exportación Dual:** Exportá el contenido de la lección directamente a tu Obsidian Vault como nota canónica o extraé automáticamente tarjetas para memorizar conceptos clave.

---

## Inglés Técnico

Espacio de estudio y retención de colocaciones técnicas profesionales en BI, Machine Learning y Cloud Computing con diseño panorámico sin scroll.

- **Espacio de Estudio Panorámico:** Área de flashcard optimizada para lectura a distancia, con respuesta esperada nítida, traducción al español y contexto de uso profesional con traducción opcional del ejemplo.
- **Sistema de Puntaje Siempre Visible:** Panel de calificación anclado directamente al pie de la tarjeta con cuatro botones ergonómicos:
  - `Again` ([1]): Olvido completo, reprogramación inmediata.
  - `Hard` ([2]): Recordado con esfuerzo notable.
  - `Good` ([3]): Recuerdo correcto con intervalo balanceado.
  - `Easy` ([4]): Dominio total, espaciado prolongado.
- **Barra de Audio & Shadowing:** Reproducción de audio nativo (`[R]`), selector de acentos (US/UK), control de velocidad (0.75x a 1.25x), modo Listening y evaluación de voz por micrófono con Gemini AI.
- **Companion Sidebar:** Panel lateral con cola de tarjetas de la sesión actual (con salto directo por clic), métricas de retención estimadas en vivo, racha de días y desglose cognitivo de memoria.
- **Niveles Progresivos:** Banco de tarjetas organizado por niveles temáticos (A1 Bases, A2 Standups & Sync, B1 Data Storytelling, B2 Tech & Cloud AI, C1 Consulting & Discovery).
- **Exportación a Anki:** Descarga de mazos en formato TSV tabulado compatible con Anki Desktop y AnkiMobile.

> [!TIP]
> Podés operar toda la sesión de inglés enteramente desde el teclado con `[Espacio]` para voltear/avanzar, `[1..4]` para calificar y `[R]` para escuchar la pronunciación nativa.

---

## Cerebro & Tutor IA

Tu asistente cognitivo unificado conectado a tu base de conocimientos personal con RAG federado y embeddings de alta dimensionalidad.

- **Búsqueda Semántica Vectorial (768d):** Consultá dudas en lenguaje natural sobre todas tus notas de Obsidian, fragmentos de libros técnicos y apuntes de cursos simultáneamente. En local corre sobre SQLite con sqlite-vec sin necesidad de Docker; en la nube utiliza PostgreSQL con pgvector. Quien usaba PostgreSQL en local pasa al índice local y la app reindexa sola (puede tardar la primera vez).
- **Chat Pedagógico con Contexto:** El tutor IA responde con tus materiales subidos. Si elegís un material, usa ese; si no, busca los más relevantes («Todo» o «Solo mis materiales»). Lee el documento entero: toma los pasajes que tienen que ver con tu pregunta de cualquier parte del texto, no solo de las primeras páginas.
- **Cosecha de Tarjetas desde tus Materiales:** En la cosecha de tarjetas, elegí «Desde mis materiales» para sacar flashcards de un PDF o apunte que subiste.
- **Apuntes al Vault:** Generá una nota estructurada para tu Vault a partir de un material.

### Mis materiales

Aulento no se conecta con Google Drive ni con OneDrive: lo que tengas ahí, bajalo de Drive (o de OneDrive, o de un USB) y subilo acá.

- **Cómo subir:** tocá **Subir materiales** y elegí uno o varios archivos. Se suben de a uno, con su progreso.
- **Formatos:** PDF (`.pdf`), Markdown (`.md`, `.markdown`) y texto (`.txt`).
- **Límites:** hasta **25 MB por archivo** y **200 MB en total por cuenta**. La barra de espacio muestra cuánto usaste (por ejemplo, «35 MB de 200 MB»). Si un archivo no entra, el aviso dice el tope y cuánto te queda libre.
- **Lo que no se admite:** PDFs escaneados (son imágenes, sin texto que leer), PDFs con contraseña o rotos, y archivos de Word (`.docx`), PowerPoint o imágenes. Exportalos a PDF con texto antes de subirlos: desde Word o Google Docs, «Descargar como PDF» alcanza.
- **Repetidos:** si subís el mismo archivo dos veces, se avisa y no ocupa lugar de nuevo.
- **Acciones de cada material:** **Preguntar al tutor**, **Ver texto** (el texto que se extrajo), **Indexar** (solo con la búsqueda semántica activa) y **Borrar**, que pide confirmación. Borrar un material **libera su espacio**.
- **Sin sincronización:** si editás el original, volvé a subirlo.
- **Cuenta demo:** muestra la lista pero no deja subir ni borrar.

---

## Mis notas

Acá están las notas que guardan el tutor, los apuntes y el examen.

- **Buscar y leer:** la lista agrupa las notas por carpeta. El buscador filtra por texto y, al tocar una nota, se lee con su formato.
- **Descargar:** "Descargar nota" baja el archivo `.md` tal cual está guardado. "Descargar todo (ZIP)" baja todas, con sus carpetas.
- **Carpeta de notas (solo en la versión local):** muestra la carpeta que se usa y permite cambiarla escribiendo una ruta. Puede ser una bóveda de Obsidian. En la nube las notas viven en tu cuenta y no hay carpeta para elegir.
- **Demo:** se pueden ver y descargar notas, pero no cambiar la carpeta.

## Repaso Activo

Módulo de evaluación activa del aprendizaje mediante preguntas conceptuales y método Feynman.

- **Cuestionarios de Práctica:** Creación automática de preguntas de auto-evaluación basadas en los temas completados de tus rutas de estudio.
- **Evaluación Feynman:** Escribí una explicación con tus propias palabras de un concepto complejo como si se lo enseñaras a un principiante. El evaluador de IA analizará tu explicación, detectará lagunas conceptuales, premiará analogías acertadas y te calificará del 1 al 10.
- **Retención a Largo Plazo:** Seguimiento continuo de materias completadas mediante preguntas breves periódicas para prevenir la curva del olvido.

---

## Configuración

Panel de personalización y control de privacidad de tu cuenta de usuario.

- **Proveedores de Inteligencia Artificial:**
  - Configuración y cambio dinámico entre **Google Gemini**, **Anthropic Claude** y **OpenAI**.
  - Carga segura de claves de API (`API Keys`) con almacenamiento cifrado individual por cuenta mediante AES-GCM.
  - Selector del modelo específico a emplear (ej. `gemini-1.5-pro`, `claude-3-5-sonnet-20241022`, `gpt-4o`).
  - Prueba de conectividad instantánea para verificar saldo y validez de la clave.
- **Carpetas del Tutor:** Las carpetas por defecto del tutor («04 Knowledge», «06 Raw», «02 MOCs») ya vienen creadas en tu vault propio con su descripción. Las ves como un árbol con la cantidad de notas de cada una; marcás las que querés y guardás la selección. También se crean desde acá (con `/` para subcarpetas), sin entrar al servidor. Si usás un vault externo y falta alguna carpeta del tutor, el botón **Crear las que faltan** las crea en tu carpeta. Se llega también desde **📒 Carpetas del tutor**, junto al selector de notas de los exámenes.
- **Duolingo:** Conectás tu usuario público (o pegás el enlace de tu perfil) y la racha, el XP y el curso actual aparecen en la cabecera y en esta sección, con un botón para sincronizar. No pide contraseña; si tu perfil es privado, Duolingo no deja ver la racha. Tocar la racha de la cabecera abre la misma ventana cuando todavía no hay un perfil leído.
- **Respaldo y Exportación:** Descarga en ZIP de todo tu historial de estudio, notas y tarjetas de repaso.

