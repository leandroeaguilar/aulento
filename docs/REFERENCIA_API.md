---
type: Reference
title: "Referencia de la API REST"
description: "Documentación exhaustiva de los endpoints de Aulento: modelo de autenticación con cookies HttpOnly, defensa de origen, lista blanca de rutas públicas, catálogo de códigos de error y operaciones agrupadas por etiqueta."
generated:
  by: process:claude-code
  at: 2026-11-05T00:00:00Z
---

# Referencia de la API REST de Aulento

Esta referencia documenta el conjunto completo de operaciones HTTP provistas por el servidor web y API REST local-first de **Aulento**.

---

## Autenticación y Seguridad

En el modo local, el del core, no hay ingreso: el servidor atiende solo a esta misma máquina y todo pedido es de la cuenta local (`GET /api/auth/me` la devuelve). Las rutas que reciben datos de otras apps se autentican con su propio token: el feed del calendario lo lleva en la ruta, y los webhooks y el servidor MCP, en un encabezado. Ninguna acepta el token en la consulta de la dirección.

El modo multiusuario (`AULENTO_MODE=saas`) necesita una extensión que aporte las cuentas; sin ella el servidor no arranca.


### Defensa de Origen (CSRF)

Para cualquier petición que cambie estado (`POST`, `PUT`, `DELETE`, `PATCH`):
- El servidor verifica que la cabecera `Origin` o `Referer` coincida con los hosts permitidos (configurados automáticamente para loopback local o ampliados mediante `AULENTO_ALLOWED_HOSTS` y `AULENTO_ALLOWED_ORIGINS`).
- Si el servidor se encuentra detrás de un proxy inverso de confianza (declarado en `AULENTO_TRUSTED_PROXIES`), se respetan las cabeceras `X-Forwarded-Host` y `X-Forwarded-Proto` de dicho proxy. Peticiones de proxies no autorizados son descartadas.

---

## Rutas Públicas (Sin Sesión)

En el modo multiusuario, todas las rutas de la API exigen sesión válida salvo las que integran la lista blanca declarada en `RUTAS_PUBLICAS`. Cualquier solicitud sin sesión dirigida a endpoints fuera de esta lista responderá con `401 Unauthorized`.

Las rutas públicas son:

| Método y Ruta | Descripción |
|---|---|
| `GET /api/health` | Verificación de estado de salud del servidor y conectividad de base de datos. En la nube informa además el estado del índice de búsqueda. |
| `GET /api/capacidades` | Modo del servidor, capacidades activas (`carpeta_local`, `mcp_escritorio`, `mcp_web`, `google_libros`, `atajo_libros` y las que sume una extensión) y textos de reemplazo para la interfaz. |
| `GET /api/books/google/oauth-callback` | Callback de autorización OAuth 2.0 para Google Play Libros (redirección pública desde Google). |
| `GET /api/schedule/feed/{token}.ics` | Feed del cronograma para suscribirse desde un calendario. La cuenta sale del token de la ruta, que solo sirve para leer ese calendario y se puede revocar; uno inexistente, revocado o de otro alcance responde `404`. |

> Los recursos estáticos montados bajo `/static` son accesibles públicamente.


---

## Códigos de Error y Formato de Respuesta

Cuando una petición no puede completarse exitosamente, la API responde con un código de estado HTTP estándar y un cuerpo JSON con el detalle del error:

```json
{
  "detail": "Descripción clara del error ocurrido"
}
```

Para errores de validación de esquema (código `422`), `detail` contiene la lista de campos observados por Pydantic:

```json
{
  "detail": [
    {
      "loc": ["body", "username"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Catálogo de Códigos de Error

| Código | Estado | Significado y Causa Típica |
|---|---|---|
| `400` | Bad Request | Parámetros inválidos, datos mal formados o inconsistencias lógicas en el pedido. |
| `401` | Unauthorized | Falta la cookie de sesión `se_sesion`, la sesión ha expirado o las credenciales provistas son inválidas. |
| `403` | Forbidden | La cuenta autenticada carece de permisos (ej. usuario estándar intentando acceder a rutas de administración, o cuenta demo intentando modificar configuraciones bloqueadas). |
| `404` | Not Found | El recurso solicitado (curso, libro, tarjeta FSRS, tema de ruta, usuario, etc.) no existe en la base de datos de la cuenta. |
| `409` | Conflict | Conflicto con el estado actual (ej. nombre de usuario ya registrado, código de invitación ya utilizado, duplicación de identificadores, coincidencia ambigua en el webhook de libros o un material que la cuenta ya subió). |
| `413` | Content Too Large | La subida de un material pasa el tope de 25 MB por archivo o el espacio libre de la cuenta (200 MB en total). El mensaje dice el tope y cuánto queda libre. Detrás de Caddy, un cuerpo de más de 30 MB se corta antes de llegar a la aplicación. |
| `415` | Unsupported Media Type | El material no es PDF, Markdown ni texto, por extensión o por contenido. |
| `422` | Unprocessable Entity | Error en la validación semántica del payload JSON (tipos de datos incorrectos, campos requeridos omitidos), o un material sin texto legible (PDF escaneado, cifrado o roto). |
| `429` | Too Many Requests | Límite de tasa excedido (rate limiting activado en endpoints de autenticación o llamadas de IA). |
| `503` | Service Unavailable | Servicio externo temporalmente no disponible (proveedor de IA no responde, índice vectorial no disponible o falla de conexión). |

---

## Catálogo de Operaciones por Etiqueta

A continuación se listan todas las operaciones de la API REST, agrupadas por etiqueta. El total exacto lo da `docs/api/openapi.json`, del que `tests/test_documentacion.py` controla que no falte ninguna acá.


### Actividad

> Métricas de consistencia diaria, racha de estudio y mapa de calor de actividad.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/activity/heatmap` | Get Activity Heatmap |
| `GET /api/activity/streak` | Get Streak Info |


### Analytics & Config

> Métricas de uso de tokens, costos estimados, logs de API y configuración de claves duales.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/analytics/logs` | Get Recent Api Logs |
| `GET /api/analytics/tokens` | Get Token Usage Summary |
| `GET /api/config/gemini-keys` | Get Gemini Keys Status |
| `POST /api/config/gemini-keys` | Update Gemini Keys Config |

### Books

> Seguimiento de lectura de libros técnicos (capítulos, páginas y porcentaje de avance).

| Método y Ruta | Resumen |
|---|---|
| `DELETE /api/books/{book_id}` | Delete Book |
| `GET /api/books` | List Books |
| `PATCH /api/books/{book_id}/progress` | Update Book Progress |
| `POST /api/books` | Create Book |
| `POST /api/books/{book_id}/advance` | Advance Book Chapter |
| `POST /api/books/{book_id}/advance-pages` | Advance Book Pages |
| `PUT /api/books/{book_id}` | Update Book |
| `DELETE /api/books/google/authorize` | Desconectar cuenta de Google Play Libros |
| `GET /api/books/google/oauth-callback` | Callback de redirección OAuth 2.0 Google Play Libros |
| `GET /api/books/google/status` | Consultar estado de conexión con Google Play Libros |
| `POST /api/books/google/authorize` | Iniciar flujo de autorización OAuth 2.0 con Google Books |
| `POST /api/books/google/sync` | Sincronizar estantes y progreso de lectura con Google Play Libros |
| `GET /api/books/sync/webhook-info` | Obtener URL y configuración del webhook para Atajos de Apple Libros |
| `POST /api/books/sync/webhook` | Webhook para recibir actualizaciones de lectura desde Apple Libros / Atajos. Acepta el token de libros en `Authorization: Bearer` (y, por compatibilidad, la sesión o un token MCP); responde `409` si el título coincide con varios libros |
| `GET /api/books/sync/token` | Estado del token de libros de la cuenta (nunca lo devuelve) |
| `POST /api/books/sync/token` | Crear el token de libros para Atajos; revoca el anterior. Es la única respuesta que lo trae en claro |
| `DELETE /api/books/sync/token` | Revocar el token de libros |
| `POST /api/books/{book_id}/active-recall/generate` | Generar cuestionario conceptual de Active Recall con IA sobre el tramo leído |
| `POST /api/books/{book_id}/active-recall/evaluate` | Evaluar formativamente respuestas del estudiante y registrar sesión de estudio |
| `POST /api/books/{book_id}/harvest/preview` | Previsualizar tarjetas FSRS y vocabulario técnico extraído con IA |
| `POST /api/books/{book_id}/harvest/commit` | Incorporar tarjetas cosechadas al mazo FSRS evitando duplicados |

### Cuenta

> La cuenta que hace el pedido: en local, la cuenta única; con la nube, la de la sesión.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/auth/me` | Quien Soy: `id`, `nombre_usuario`, `rol`, `activo` y `compartida` (una extensión la declara compartida, como la demo: no guarda claves ni conecta servicios). |


### Duolingo

> Sincronización de perfil de idioma, racha y experiencia (XP) con Duolingo.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/duolingo/config` | Get Duolingo Config |
| `GET /api/duolingo/profile` | Get Duolingo Profile |
| `POST /api/duolingo/sync` | Sync Duolingo |
| `PUT /api/duolingo/config` | Set Duolingo Config |

### Exams

> Generación adaptativa de exámenes con Active Recall y evaluación conceptual con Técnica Feynman.

| Método y Ruta | Resumen |
|---|---|
| `POST /api/exams/evaluate-answer` | Evaluate Open Answer |
| `POST /api/exams/evaluate-feynman` | Evaluate Feynman |
| `GET /api/exams/feynman-examples` | Get Feynman Examples |
| `POST /api/exams/generate` | Generate Exam |

### FSRS

> Motor de repetición espaciada FSRS v5 para inglés técnico, pronunciación, audio y drills de consultoría.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/fsrs/audio/config` | Get Audio Config |
| `GET /api/fsrs/audio/gemini-status` | Get Gemini Tutor Status |
| `GET /api/fsrs/consulting/scenarios` | Get Consulting Scenarios |
| `GET /api/fsrs/decks` | Get Roadmap Decks |
| `GET /api/fsrs/due` | Get Due Cards |
| `GET /api/fsrs/evolution/status` | Get Evolution Status |
| `GET /api/fsrs/export/anki` | Export Cards To Anki |
| `GET /api/fsrs/levels` | Get Progressive Levels |
| `GET /api/fsrs/status` | Get Fsrs Status |
| `POST /api/fsrs/audio/evaluate-pronunciation` | Evaluate Pronunciation |
| `POST /api/fsrs/audio/gemini-evaluate` | Evaluate With Gemini Tutor |
| `POST /api/fsrs/audio/gemini-key` | Set Gemini Api Key |
| `POST /api/fsrs/audio/gemini-test` | Test Gemini Api Connection |
| `POST /api/fsrs/audio/speak` | Speak Technical Term |
| `POST /api/fsrs/consulting/evaluate` | Evaluate Consulting Submission |
| `POST /api/fsrs/evolution/diagnose` | Diagnose Student Evolution |
| `POST /api/fsrs/harvest/commit` | Commit Harvest Cards |
| `POST /api/fsrs/harvest/preview` | Previsualiza tarjetas desde el vault, los materiales subidos (`source: materiales`, con `material_id` o `topic`) o la IA |
| `POST /api/fsrs/review` | Review Card |
| `POST /api/fsrs/seed` | Seed Deck |
| `POST /api/fsrs/translate` | Translate Technical Text |

### Focus Timer

> Temporizador de sesiones de estudio Pomodoro y registro de minutos estudiados.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/focus/sessions` | List Focus Sessions |
| `GET /api/focus/stats` | Get Focus Stats |
| `POST /api/focus/sessions` | Record Focus Session |

### Frontend

> Páginas HTML principales de la aplicación web.

| Método y Ruta | Resumen |
|---|---|
| `GET /` | Get Index |
| `GET /api/docs/manual` | Get User Manual: devuelve un manual del proyecto en Markdown (`doc=manual\|api\|mcp\|cli`) |

### Health

> Comprobación de estado y disponibilidad del servidor.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/health` | Health Check |

### Hub

> Gestión de plataformas académicas (Digital House, Coursera, etc.) y cursos de estudio.

| Método y Ruta | Resumen |
|---|---|
| `DELETE /api/hub/courses/{course_id}` | Delete Course |
| `DELETE /api/hub/platforms/{platform_id}` | Delete Platform |
| `GET /api/hub/courses` | List Courses |
| `GET /api/hub/platforms` | List Platforms With Courses |
| `POST /api/hub/courses` | Create Course |
| `POST /api/hub/courses/{course_id}/open-local` | Open Course Local Folder |
| `POST /api/hub/courses/{course_id}/progress` | Update Course Progress |
| `POST /api/hub/courses/{course_id}/sync` | Sync Course |
| `POST /api/hub/platforms` | Create Platform |
| `POST /api/hub/sync/platforms/google-skills` | Sync Google Skills Platform |
| `POST /api/hub/sync/webhook` | Webhook Course Sync |
| `GET /api/hub/sync/status` | Get Course Sync Status |
| `GET /api/hub/sync/webhook-info` | Get Course Webhook Info |
| `PUT /api/hub/courses/{course_id}` | Update Course |
| `PUT /api/hub/platforms/{platform_id}` | Update Platform |

### IA & Providers

> Gestión de proveedores de IA (Gemini, Anthropic, OpenAI), claves cifradas, modelos y pruebas de conexión.

| Método y Ruta | Resumen |
|---|---|
| `DELETE /api/config/ia/{proveedor}/key` | Remove Provider Key |
| `GET /api/config/ia` | Get Ia Config |
| `GET /api/config/ia/{proveedor}/models` | Get Provider Models |
| `POST /api/config/ia/{proveedor}/test` | Test Provider Connection |
| `PUT /api/config/ia` | Update Ia Config |
| `PUT /api/config/ia/{proveedor}/key` | Save Provider Key |

### MCP

> Tutor sobre los materiales de la cuenta (preguntas, apuntes y cosecha de tarjetas) y tokens MCP por cuenta.

| Método y Ruta | Resumen |
|---|---|
| `DELETE /api/mcp/tokens/{token_id}` | Revocar un token MCP de la cuenta |
| `GET /api/mcp/connection-info` | Datos para conectar un asistente al servidor MCP (rutas locales solo para administradores; rechazado en la demo) |
| `GET /api/mcp/tokens` | Listar los tokens MCP de la cuenta |
| `POST /api/mcp/agent/ask` | Pregunta al tutor sobre los materiales subidos y notas (`historial` opcional de seguimiento; `material_id` opcional; `provider`: `all`, `vector`, `materiales` o `notas`) |
| `POST /api/mcp/agent/harvest-cards` | Harvest Agent Cards To Fsrs |
| `POST /api/mcp/agent/save-note` | Save Agent Note To Vault |
| `POST /api/mcp/tokens` | Crear un token MCP para la cuenta |

### Materiales

> Materiales de estudio que cada cuenta sube desde la PC (PDF, Markdown y texto): hasta 25 MB por archivo y 200 MB por cuenta. La subida es `multipart/form-data` con el archivo en el campo `archivo`; responde `413` si pasa un tope, `415` si no es un tipo admitido, `422` si no tiene texto legible y `409` (con el material existente en `material`) si la cuenta ya lo subió. La cuenta demo recibe `403` al subir o borrar.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/materiales` | Materiales de la cuenta con el espacio usado, el tope y lo libre |
| `POST /api/materiales` | Subir un material; lo indexa en el índice vectorial si está disponible (`indexado`) |
| `GET /api/materiales/{material_id}` | Datos y texto de un material (cortado a 200.000 caracteres, `texto_cortado`) |
| `DELETE /api/materiales/{material_id}` | Borrar un material: archivo, texto y fragmentos en el índice vectorial |

### Macro-FSRS

> Repaso espaciado de alto nivel para temas completados del roadmap y micro-quizzes Feynman.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/macro-fsrs/all` | Get All Retention Topics |
| `GET /api/macro-fsrs/due` | Get Due Topics |
| `GET /api/macro-fsrs/quiz/{tema_id}` | Get Feynman Microquiz |
| `POST /api/macro-fsrs/review` | Review Topic |

### Onboarding

> Diagnóstico de configuración y progreso del asistente de primer ingreso.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/config/onboarding-status` | Obtener el estado de configuración y onboarding |
| `POST /api/config/onboarding-status` | Marcar el estado de onboarding |

### Roadmaps

> Rutas de aprendizaje, árbol de módulos/temas, grafo DAG de prelaciones y diseño pedagógico.

| Método y Ruta | Resumen |
|---|---|
| `DELETE /api/roadmap/{roadmap_id}` | Delete Roadmap |
| `DELETE /api/roadmap/{roadmap_id}/prerequisites/{orig_id}/{dest_id}` | Delete Prerequisite |
| `GET /api/roadmap` | List Roadmaps |
| `GET /api/roadmap/system-prompts` | Get System Prompts |
| `GET /api/roadmap/templates` | List Templates |
| `GET /api/roadmap/topics/{topic_id}/lesson-versions` | List Lesson Versions |
| `GET /api/roadmap/{roadmap_id}` | Get Roadmap |
| `GET /api/roadmap/{roadmap_id}/graph` | Get Roadmap Graph |
| `GET /api/roadmap/{roadmap_id}/interactive-map` | Get Roadmap Interactive Map: el mapa interactivo de la ruta, en HTML |
| `GET /api/roadmap/{roadmap_id}/pedagogical-profile` | Get Pedagogical Profile |
| `POST /api/roadmap` | Create Roadmap |
| `POST /api/roadmap/generate` | Generate Roadmap |
| `POST /api/roadmap/import-syllabus` | Import Syllabus Json |
| `POST /api/roadmap/import-syllabus-file` | Import Syllabus File |
| `POST /api/roadmap/lesson-versions/{version_id}/restore` | Restore Lesson Version |
| `POST /api/roadmap/lessons/{lesson_id}/export-fsrs` | Export Lesson To Fsrs |
| `POST /api/roadmap/lessons/{lesson_id}/export-vault` | Export Lesson To Vault |
| `POST /api/roadmap/modules/{module_id}/expand` | Expand Module |
| `POST /api/roadmap/system-prompts` | Update System Prompt |
| `POST /api/roadmap/system-prompts/reset` | Reset System Prompts |
| `POST /api/roadmap/templates/seed` | Seed Templates |
| `POST /api/roadmap/topics/{topic_id}/build-prompt` | Build Lesson Prompt |
| `POST /api/roadmap/topics/{topic_id}/generate-lesson` | Generate Lesson In App |
| `POST /api/roadmap/topics/{topic_id}/import-lesson` | Import External Lesson |
| `POST /api/roadmap/topics/{topic_id}/status` | Update Topic Status |
| `POST /api/roadmap/{roadmap_id}/compare-pdf` | Compare Pdf Syllabus |
| `POST /api/roadmap/{roadmap_id}/merge` | Merge Gap Topics |
| `POST /api/roadmap/{roadmap_id}/prerequisites` | Add Prerequisite |
| `POST /api/roadmap/{roadmap_id}/prerequisites/bulk` | Add Prerequisites Bulk |
| `POST /api/roadmap/{roadmap_id}/prerequisites/suggest` | Suggest Prerequisites |
| `POST /api/roadmap/{roadmap_id}/suggest-next` | Suggest Next Topics |
| `PUT /api/roadmap/{roadmap_id}/graph-settings` | Update Graph Settings |
| `PUT /api/roadmap/{roadmap_id}/pedagogical-profile` | Update Pedagogical Profile |

### Schedule

> Cronograma de bloques horarios semanales, exportación iCalendar y enlaces de Google Calendar.

| Método y Ruta | Resumen |
|---|---|
| `DELETE /api/schedule/{block_id}` | Delete Schedule Block |
| `GET /api/schedule` | List Schedule |
| `GET /api/schedule/export/calendar.ics` | Descargar el cronograma como `.ics`, con la zona horaria de la cuenta en cada evento |
| `GET /api/schedule/feed` | Estado de la suscripción al calendario (nunca devuelve la dirección) |
| `POST /api/schedule/feed` | Crear la dirección de suscripción; revoca la anterior. Es la única respuesta que la trae |
| `DELETE /api/schedule/feed` | Revocar la dirección de suscripción |
| `GET /api/schedule/feed/{token}.ics` | Feed del cronograma para la app de calendario (pública, ver lista blanca) |
| `GET /api/schedule/google-calendar/link/{block_id}` | Get Google Calendar Link For Block |
| `GET /api/schedule/google-calendar/links` | Get Google Calendar Links |
| `GET /api/schedule/google-calendar/status` | Get Google Calendar Status |
| `PATCH /api/schedule/{block_id}` | Update Schedule Block |
| `POST /api/schedule` | Create Schedule Block |
| `PUT /api/schedule/{block_id}` | Update Schedule Block |

### Vault

> Integración con notas Markdown del vault de Obsidian, generación de apuntes y digest semanal.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/vault/digest/weekly` | Get Weekly Digest |
| `GET /api/vault/export.zip` | Export Vault As Zip |
| `GET /api/vault/folders` | List Vault Folders |
| `GET /api/vault/location` | Get Vault Location |
| `GET /api/vault/notes` | List Vault Notes |
| `GET /api/vault/notes/materials` | Lista los materiales subidos con los que se puede generar un apunte |
| `GET /api/vault/notes/{note_id}` | Get Single Vault Note |
| `GET /api/vault/notes/{note_id}/download` | Download Vault Note |
| `GET /api/vault/stats` | Get Vault Statistics |
| `POST /api/vault/digest/weekly/save` | Save Weekly Digest |
| `POST /api/vault/folders` | Create Vault Folder |
| `POST /api/vault/folders/create-missing` | Create Missing Vault Folders |
| `POST /api/vault/notes/course-template` | Generate Course Note Template |
| `POST /api/vault/notes/from-material` | Genera un apunte SOP desde un material subido (`material_id`); uno de otra cuenta responde 404 |
| `POST /api/vault/sample-notes` | Seed Sample Notes |
| `PUT /api/vault/location` | Set Vault Location |
| `PUT /api/vault/tutor-folders` | Set Tutor Folders |

### Vectors / Semantic Search

> Almacén vectorial, embeddings y búsqueda semántica de documentos y notas (SQLite con sqlite-vec en local; PostgreSQL con pgvector en la nube).

| Método y Ruta | Resumen |
|---|---|
| `GET /api/vectors/status` | Get Vector Status |
| `POST /api/vectors/index` | Index Document |
| `POST /api/vectors/index-book/{book_id}` | Index Single Book |
| `POST /api/vectors/index-course/{course_id}` | Index Single Course |
| `POST /api/vectors/index-selection` | Indexa un lote de cursos, libros y materiales (`type`: `course`, `book` o `material`) |
| `POST /api/vectors/init` | Initialize Vector Database |
| `POST /api/vectors/search` | Semantic Search |
| `POST /api/vectors/sync-catalog` | Sync Catalog To Vectors |


### Planificador Adaptativo

> Motor de recomendación y planificación adaptativa de estudio diario y semanal balanceando FSRS, Deep Work y Lectura Activa.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/planner/daily-briefing` | Get Daily Briefing |
| `POST /api/planner/recommendations` | Get Study Recommendations |
| `POST /api/planner/apply-today` | Apply Study Plan To Schedule |


### Diagnostics

> Diagnóstico del motor, comprobaciones de salud del sistema, logs y exportación de reportes.

| Método y Ruta | Resumen |
|---|---|
| `GET /api/diagnostics/export-markdown` | Exportar reporte de diagnóstico en Markdown para GitHub Issues |
| `GET /api/diagnostics/summary` | Resumen de salud del sistema y diagnóstico |
