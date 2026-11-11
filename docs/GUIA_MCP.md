---
type: guide
title: Guía de Integración y Configuración del Servidor MCP de Aulento
description: Manual integral para conectar clientes LLM (Claude Desktop, Cursor, Antigravity, Claude Code) al servidor Model Context Protocol de Aulento para creación de clases, actualización de cursos por enlace, lectura por páginas y repaso FSRS.
generated:
  by: process:claude-code
  at: 2026-11-05T00:00:00Z
---

# Guía de Conexión del Servidor MCP de Aulento

El **Servidor MCP de Aulento** permite que modelos de lenguaje avanzados (Claude 3.5 Sonnet / Opus, GPT-4o, Gemini 1.5 Pro) actúen como mentores de estudio directamente conectados a tu base de datos local SQLite, al vault de tu cuenta y a los materiales que subiste.

---

## 👤 El servidor opera siempre como una cuenta

Desde la feature 033 cada cuenta tiene sus propios cursos, libros, agenda, tarjetas, rutas y fragmentos de búsqueda semántica, y el servidor MCP nunca actúa "en general": cada pedido se resuelve como una cuenta y solo ve y modifica lo de esa cuenta. Un identificador o un nombre de otra cuenta se responde igual que uno que no existe. La decisión está en el ADR 007.

Cómo se decide la cuenta depende del transporte:

| Transporte | Cuenta con la que opera |
|---|---|
| **STDIO** (`mcp serve`) | La indicada con la opción global `--user <nombre>` o con la variable `AULENTO_USER` (la opción gana). Sin indicarla, la única cuenta activa si hay exactamente una. |
| **Red** (`mcp serve --transport http`) | La dueña del token que trae cada pedido. |

Por STDIO, si no se indica la cuenta y hay cero o varias cuentas activas, o la indicada no existe o está desactivada, el servidor **no arranca**: termina con un error que dice cómo indicarla. La cuenta se resuelve una sola vez, al arrancar.

También son de cada cuenta los materiales subidos, las claves de IA, los prompts de sistema y el vault (ADR 008): una herramienta que busca en los materiales, llama a la IA o guarda una nota usa lo de la cuenta que opera y nada de otra.

---

## 📚 Materiales subidos por cuenta

Aulento no se conecta con Google Drive ni con OneDrive (ADR 015). Cada cuenta sube sus PDF, Markdown y textos desde la web (pestaña «Cerebro & Tutor IA», «Mis materiales»), hasta 25 MB por archivo y 200 MB en total. Lo que está en la nube se descarga y se sube. Las herramientas MCP de nube (búsqueda y lectura en Drive y OneDrive) se reemplazaron por `materials_search` y `materials_read`, sin compatibilidad hacia atrás: un cliente que llamaba a las viejas tiene que pasar a estas.

### Las herramientas de materiales operan sobre la cuenta del token

`materials_search` y `materials_read` trabajan con los materiales que subió la cuenta que opera: la del token por red, la resuelta al arrancar por STDIO.

- `materials_search(query)` busca por palabras clave en el texto y el nombre de los materiales de esa cuenta.
- `materials_read(material_id, query)` devuelve, con `query`, los pasajes que tratan el tema, de cualquier parte del texto; sin ella, el principio del material. Nunca más de 40.000 caracteres.
- El id de un material de otra cuenta se responde como inexistente.
- Sin cuenta fijada no operan.

Las variables `GDRIVE_CREDENTIALS_PATH`, `GDRIVE_ROOT_FOLDER_ID` y `AULENTO_MCP_CONFIG_PATH`, y los archivos `mcp_config.json` y `gdrive_token.json` del directorio de datos **ya no se leen** ni se importan: si venís de una versión anterior, quedan donde están y se pueden borrar.

---

## 🚀 Capacidades Disponibles para el LLM

0. **Meta-Herramienta de Intención Única (`study_copilot`):**
   - Procesa lenguaje natural y descompone intenciones compuestas en una sola llamada:
     - *"Hoy leí 20 páginas de Designing Data-Intensive y estudié 45 min, ¿qué tema sigue en mi ruta?"*
     - *"Dame un resumen de mi día y cómo va mi progreso".*
   - Orquesta internamente la actualización de libros, cursos, tiempo y consultas de FSRS/Roadmap, devolviendo las acciones ejecutadas, el estado del estudiante y la **Próxima Mejor Acción Recomendada (NBA)**.
1. **Creación Quirúrgica de Clases con tus Materiales:**
   - Consulta el **Master Prompt pedagógico** adaptativo del tema (`study_get_topic_master_prompt`).
   - Busca en los materiales que subió la cuenta (`materials_search`) y lee los pasajes del tema (`materials_read`).
   - Redacta la clase magistral y la guarda en la plataforma con 1 invocación (`study_create_or_update_lesson`), extrayendo flashcards para FSRS v5 y exportando el apunte canónico al vault de la cuenta (`04 Knowledge/Cursos/...`). La respuesta nombra la nota, y su respaldo si lo hubo, por la ruta dentro del vault: nunca por la del disco del servidor.
2. **Actualización Inteligente de Cursos por Link:**
   - Actualiza el porcentaje y estado de cursos del Hub de Plataformas (`study_update_course_progress`) resolviendo el curso por URL de aula, ID o nombre.
3. **Reading Tracker por Páginas y Capítulos:**
   - Registra y actualiza el avance de libros técnicos por número de página o capítulo (`study_update_book_progress`).
4. **Drill de Repetición Espaciada (FSRS v5):**
   - Extrae tarjetas vencidas para active recall interactivo (`study_get_fsrs_due_cards`) y registra calificaciones (`study_review_fsrs_card`).
5. **Agenda y Registro de Tiempo:**
   - Consulta la agenda de hoy (`study_get_today_schedule`) y registra sesiones reales de estudio (`study_log_study_session`).

---

## 🛠️ Configuración en Clientes MCP

### 1. Claude Desktop (Recomendado — Modo Local STDIO Seguro)

Edita tu archivo de configuración de Claude Desktop:
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Agrega el servidor dentro de la sección `"mcpServers"`:

```json
{
  "mcpServers": {
    "aulento": {
      "command": "C:\\ruta\\a\\aulento\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "aulento",
        "--user",
        "tu_usuario",
        "mcp",
        "serve"
      ],
      "cwd": "C:\\ruta\\a\\aulento"
    }
  }
}
```

`--user` es una opción global: va **antes** de `mcp serve`. Si la instalación tiene una sola cuenta activa podés omitirla. La alternativa es dejar los argumentos como estaban y agregar `"env": {"AULENTO_USER": "tu_usuario"}`.

> [!NOTE]
> En modo STDIO no se abre ningún puerto de red. La comunicación ocurre de forma segura por tuberías locales (`stdin`/`stdout`) bajo tu propia sesión de Windows.

---

### 2. Cursor IDE

En Cursor, dirígete a **Settings → Features → MCP Servers → Add New MCP Server**:
- **Name:** `aulento`
- **Type:** `command`
- **Command:** `C:\ruta\a\aulento\.venv\Scripts\python.exe -m aulento --user tu_usuario mcp serve`

O en tu archivo `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "aulento": {
      "command": "C:\\ruta\\a\\aulento\\.venv\\Scripts\\python.exe",
      "args": ["-m", "aulento", "--user", "tu_usuario", "mcp", "serve"],
      "cwd": "C:\\ruta\\a\\aulento"
    }
  }
}
```

---

### 3. Modo Red (Streamable HTTP con Autenticación Bearer Token)

Si deseas conectar un cliente por red o ejecutar el servidor en un puerto TCP:

1. **Crear un token para tu cuenta** (ver [Tokens por cuenta](#-tokens-por-cuenta)):
   ```powershell
   python -m aulento mcp token create tu_usuario --name "Claude Desktop"
   ```
2. **Iniciar el servidor en Streamable HTTP** (solo en esta máquina). Por red no hace falta `--user`: la cuenta la da el token de cada pedido.
   ```powershell
   python -m aulento mcp serve --transport http --port 8000
   ```
3. **Configuración del cliente MCP:**
   ```json
   {
     "mcpServers": {
       "aulento": {
         "url": "http://127.0.0.1:8000/mcp",
         "headers": {
           "Authorization": "Bearer <TU_BEARER_AUTH_TOKEN>"
         }
       }
     }
   }
   ```
4. **Acceso desde otros equipos:** `--allow-remote` (o un `--host` que no sea local) exige un certificado TLS propio y conviene limitar los hosts aceptados:
   ```powershell
   python -m aulento mcp serve --transport http --allow-remote --ssl-certfile <certificado> --ssl-keyfile <clave> --allowed-host mi-pc.local
   ```
   Sin certificado el comando no arranca, salvo con `--insecure-http` (solo en una red de confianza o detrás de un túnel cifrado).

> **Sobre `--transport sse`:** con la versión instalada de la librería MCP (2.2.0) el transporte SSE contesta los mensajes del cliente con una respuesta HTTP mal formada y los clientes estrictos cortan la sesión. Usá `--transport http`.

---

## 🔑 Tokens por cuenta

El acceso por red se autentica con un token que pertenece a **una** cuenta. Cada cuenta puede tener varios (uno por cliente, por ejemplo) y revocar uno no afecta a los demás.

**Desde una terminal del servidor** (administración: alcanza a los tokens de cualquier cuenta):

```powershell
python -m aulento mcp token create <usuario> [--name "Etiqueta"]   # crea y muestra el token
python -m aulento mcp token list [<usuario>]                       # sin usuario, los de todas las cuentas
python -m aulento mcp token revoke <id>                            # el id es el que muestra list
```

**Desde la API web**, con la sesión iniciada (cada cuenta alcanza solo sus propios tokens):

| Operación | Qué hace |
|---|---|
| `POST /api/mcp/tokens` | Crea un token de la cuenta. Cuerpo opcional `{"nombre": "Claude Desktop"}`. Responde 201 con `id`, `token`, `nombre` y `creado_en`. |
| `GET /api/mcp/tokens` | Lista los tokens de la cuenta: `id`, nombre, creación, último uso y revocación. Nunca el token. |
| `DELETE /api/mcp/tokens/{id}` | Revoca uno. Si es de otra cuenta, no existe o ya estaba revocado, responde 404. |

Todavía no hay pantalla para esto en la interfaz web (llega con la feature 038).

Lo que conviene saber:

- **El token se ve una sola vez**, en la respuesta de `create` o del `POST`. La base guarda solo su huella SHA-256: si lo perdés no se puede recuperar, se revoca y se crea otro.
- **Qué deja de valer:** un token revocado, o el de una cuenta desactivada, recibe 401.
- **Último uso:** se anota a lo sumo una vez cada 5 minutos, así que `list` puede mostrar un valor algo atrasado.
- **La sesión queda atada a la cuenta:** la sesión que abre un cliente pertenece a la cuenta de su token. Un pedido que presente esa sesión con el token de otra cuenta recibe 404, y cada mensaje opera como la cuenta del token que trae.

### El token global `mcp_auth_token.txt` dejó de valer

Antes de la feature 033 había un único token para toda la instalación, guardado en `~/.aulento/mcp_auth_token.txt` y gestionado con `mcp token --show`. Ese token no identificaba a nadie y **ya no se acepta**: el servidor no lee el archivo y los clientes que lo sigan enviando reciben 401. El comando `mcp token --show` tampoco existe.

Para reponer el acceso:

1. Creá un token para tu cuenta: `python -m aulento mcp token create tu_usuario --name "Mi cliente"`.
2. Copialo en ese momento y reemplazá el valor de `Authorization: Bearer ...` en la configuración de cada cliente que se conecte por red.
3. Borrá `~/.aulento/mcp_auth_token.txt`: ya no cumple ninguna función.

Los clientes por STDIO (Claude Desktop, Cursor) nunca usaron ese token: solo necesitan `--user` o `AULENTO_USER` si la instalación tiene más de una cuenta activa.

### Riesgos abiertos

- **Los rechazos de autenticación se auditan con tope.** Cada pedido con un token ausente o inválido recibe 401, y se registran en `mcp_audit_logs` (sin cuenta, con la IP) como máximo 10 por dirección por minuto. Muchas direcciones distintas todavía pueden hacer crecer esa tabla: no expongas el puerto fuera de una red de confianza.
- **Reactivar una cuenta reactiva sus tokens.** Desactivar una cuenta deja sin efecto sus tokens pero no los revoca. Si la cuenta se reactiva, los que no se hayan revocado vuelven a valer. Si la desactivación fue por un token comprometido, revocalo con `mcp token revoke <id>` antes de reactivar.

---

## Referencia de Herramientas

El servidor MCP de Aulento expone 30 herramientas especializadas conectadas a la base de datos local y almacenamiento de la cuenta activa:

| Herramienta | Propósito y Capacidades |
|---|---|
| `materials_read` | Lee un material subido por la cuenta: con `query`, los pasajes que tratan el tema; sin ella, el principio. |
| `materials_search` | Busca por palabras clave entre los materiales (PDF, Markdown y texto) que subió la cuenta. |
| `study_add_book` | Da de alta un nuevo libro técnico en el Reading Tracker con seguimiento por páginas y capítulos. |
| `study_book_active_recall_generate` | Genera preguntas conceptuales de Active Recall con IA sobre el tramo leído de un libro técnico. |
| `study_book_active_recall_evaluate` | Evalúa formativamente las respuestas del estudiante a un cuestionario de Active Recall y registra la sesión de estudio. |
| `study_book_harvest_cards` | Cosecha términos en inglés y conceptos técnicos del libro volcándolos directamente al mazo FSRS v5. |
| `study_add_course` | Registra un nuevo curso en el Hub de Plataformas Educativas. |
| `study_sync_google_books` | Sincroniza estantes y avance de lectura bidireccional con Google Play Libros. |
| `study_copilot` | Asistente inteligente unificado y router de intención en lenguaje natural (lectura, cursos, briefing). |
| `study_create_flashcard` | Crea una nueva tarjeta de memoria en el banco FSRS v5 con contexto y categoría. |
| `study_create_or_update_lesson` | Guarda la lección magistral generada por el LLM, extrae tarjetas FSRS y sincroniza con el Vault. |
| `study_get_fsrs_due_cards` | Recupera las tarjetas de repaso de inglés técnico que vencen hoy según el algoritmo FSRS v5. |
| `study_get_roadmap_topics` | Obtiene la lista completa de módulos y temas de una ruta de aprendizaje activa. |
| `study_get_today_schedule` | Consulta los bloques horarios de estudio planificados para el día de hoy según la agenda. |
| `study_get_topic_lesson` | Recupera el contenido Markdown completo de una clase magistral existente para un tema dado. |
| `study_get_topic_master_prompt` | Construye el Master Prompt pedagógico adaptativo con directivas para generar la clase del tema. |
| `study_list_books` | Lista los libros técnicos en seguimiento con páginas leídas, totales y estado actual. |
| `study_get_course_sync_status` | Consulta el resumen y estado de sincronización de cursos (total, sincronizados y fecha). |
| `study_list_courses` | Lista los cursos de plataformas académicas (Digital House, Coursera, etc.) con sus avances. |
| `study_list_roadmaps` | Lista todas las rutas de estudio registradas en el sistema. |
| `study_log_study_session` | Registra una sesión real de estudio completada (minutos dedicados, tema y notas). |
| `study_review_fsrs_card` | Califica el repaso de una tarjeta FSRS (1=Again, 2=Hard, 3=Good, 4=Easy) y recalcula su intervalo. |
| `study_semantic_search` | Realiza búsquedas semánticas sobre fragmentos vectorizados de notas, libros y cursos con `pgvector`. |
| `study_update_book_progress` | Actualiza el progreso de lectura de un libro por número de página o capítulo. |
| `study_sync_course_progress` | Sincroniza el avance porcentual y estado de un curso externo por identificador o nombre. |
| `study_sync_google_skills` | Sincroniza todos los cursos de Google Cloud Skills Boost a partir de un perfil público. |
| `study_update_course_progress` | Actualiza el porcentaje de avance (0% a 100%) y estado de un curso en el Hub. |
| `study_get_daily_briefing` | Obtiene el resumen matutino holístico y puntuación de urgencia pedagógica de la cuenta. |
| `study_generate_adaptive_study_plan` | Genera un plan de estudio adaptativo estructurado en fases según minutos disponibles. |
| `study_apply_study_plan_to_schedule` | Vuelca e inserta los bloques de un plan de estudio directamente en la agenda de la cuenta. |

---

## 🔒 Arquitectura de Seguridad en 7 Capas

| Capa | Mecanismo | Protección Garantizada |
|---|---|---|
| **1. Aislamiento de Red** | STDIO local por defecto | Cero puertos abiertos; inalcanzable desde WiFi o internet |
| **2. Autenticación Bearer por cuenta** | Token de 256 bits por cuenta; la base guarda solo su huella SHA-256 | Rechazo inmediato (HTTP 401) ante un token ausente, inválido, revocado o de una cuenta desactivada |
| **3. Anti Path Traversal** | Toda ruta de nota se resuelve y se confina al vault de la cuenta | Impide leer o escribir fuera del vault de la cuenta que opera |
| **4. Blindaje SQL & Shell** | 100% consultas parametrizadas, cero tools de bash/cmd | Inmune a SQL injection y ejecución de comandos remotos |
| **5. Audit Trail & Read-Only** | Tabla SQLite `mcp_audit_logs` + flag `--read-only` | Auditoría forense de cada herramienta invocada por el modelo, con la cuenta que la originó |
| **6. Aislamiento por cuenta** | Cada herramienta, recurso y el copilot operan con la cuenta del token o de STDIO | Una cuenta no lee ni modifica datos de otra; lo ajeno responde como inexistente |
| **7. Secretos cifrados por cuenta** | Claves de IA y autorización de Google Play Libros cifradas en la base con la clave maestra | Ninguna herramienta devuelve un secreto ni usa el de otra cuenta |

---

## 💡 Ejemplos de Prompts para Usar con Claude o Cursor

### A. Crear una Clase Magistral con tus Materiales
> *"Hola Claude. Consulta el temario de mi ruta activa con `study_get_roadmap_topics`. Para el primer tema pendiente, obtén su master prompt con `study_get_topic_master_prompt`. Luego busca en mis materiales con `materials_search`, lee los pasajes del tema con `materials_read` y redacta la clase completa. Finalmente guárdala en Aulento usando `study_create_or_update_lesson`."*

### B. Actualizar Progreso de un Curso por Enlace
> *"Acabo de terminar el módulo 3 en mi curso de GCP en Digital House. Este es el link del aula: `https://digitalhouse.com/aula/gcp-data-engineer`. Actualiza mi progreso al 65% en Aulento."*

### C. Registrar Lectura de un Libro por Páginas
> *"Hoy leí hasta la página 145 del libro Designing Data-Intensive Applications. Actualiza mi avance en Aulento."*

### D. Sesión Socrática de Repaso FSRS
> *"Quiero hacer mi sesión de active recall de inglés técnico. Consulta mis tarjetas pendientes con `study_get_fsrs_due_cards` y hazme una pregunta a la vez."*
