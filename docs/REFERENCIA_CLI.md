---
type: Reference
title: "Referencia de la Línea de Comandos (CLI)"
description: "Documentación completa de la CLI de Aulento: sintaxis general, opción global --user para selección de cuenta activa y catálogo exhaustivo de todos los comandos disponibles."
generated:
  by: process:claude-code
  at: 2026-11-05T00:00:00Z
---

# Referencia de la Línea de Comandos (CLI) de Aulento

Aulento dispone de una potente interfaz de línea de comandos (CLI) construida sobre Python y Typer. Permite operar todos los subsistemas del motor de estudio: gestión de cursos, lectura de libros, drills de FSRS, interacción con modelos de inteligencia artificial, servidores MCP y administración de usuarios.

---

## Sintaxis General y Opción Global `--user`

```bash
python -m aulento [OPCIONES_GLOBALES] COMANDO [ARGUMENTOS]
# o directamente:
aulento [OPCIONES_GLOBALES] COMANDO [ARGUMENTOS]
```

### Selección de Cuenta Activa (`--user` y `AULENTO_USER`)

Dado que Aulento es un sistema multiusuario donde cada estudiante cuenta con su propia base de datos SQLite y almacén de claves cifradas:

- **Opción Global `--user <nombre_usuario>`:**
  Permite indicar explícitamente sobre qué cuenta de usuario debe actuar el comando ejecutado:
  ```bash
  aulento --user juan books list
  aulento --user maria fsrs study
  ```
- **Variable de Entorno `AULENTO_USER`:**
  Si no se especifica el parámetro `--user`, la CLI verificará si existe la variable de entorno `AULENTO_USER`:
  ```bash
  export AULENTO_USER=juan
  aulento books list
  ```
- **Resolución Automática:**
  Si existe **una única cuenta activa** en el sistema, la CLI la seleccionará automáticamente sin requerir `--user`. Si existen múltiples cuentas y no se especifica usuario, los comandos que requieran datos abortarán solicitando la selección explícita de la cuenta.

---

## Catálogo Exhaustivo de Comandos

### 1. Actividad y Seguimiento (`activity`)

| Comando | Descripción |
|---|---|
| `aulento activity due-topics` | Lista los temas de estudio pendientes de repaso o que vencen en el día. |
| `aulento activity heatmap` | Muestra en terminal la matriz de calor y frecuencia de estudio de los últimos meses. |
| `aulento activity streak` | Consulta la racha de días consecutivos de estudio y el total de sesiones registradas. |

### 2. Libros Técnicos (`books`)

| Comando | Descripción |
|---|---|
| `aulento books add` | Registra un nuevo libro técnico en el catálogo de lectura. |
| `aulento books advance` | Actualiza la página o capítulo actual de lectura para un libro. |
| `aulento books google-status` | Muestra el estado de la vinculación con Google Play Libros. |
| `aulento books list` | Lista todos los libros en seguimiento con sus porcentajes y páginas leídas. |
| `aulento books sync-google` | Sincroniza estantes y avance de lectura bidireccional con Google Play Libros. |
| `aulento books webhook-info` | Muestra la URL y configuración del webhook para Atajos de Apple Libros. |
| `aulento books quiz` | Inicia una sesión interactiva de Active Recall con preguntas conceptuales de IA sobre el tramo leído. |
| `aulento books harvest` | Cosecha términos en inglés y conceptos técnicos del libro para volcarlos al mazo FSRS v5. |

### 3. Base de Datos (`db`)

| Comando | Descripción |
|---|---|
| `aulento db init` | Inicializa el esquema de tablas en la base de datos SQLite del usuario. |
| `aulento db status` | Verifica el estado de las tablas, versión de migraciones e integridad de la base. |

### 4. Duolingo (`duolingo`)

| Comando | Descripción |
|---|---|
| `aulento duolingo set-user` | Asocia el nombre de usuario de Duolingo a la cuenta activa. |
| `aulento duolingo status` | Muestra el estado de vinculación y última sincronización con Duolingo. |
| `aulento duolingo sync` | Sincroniza racha, experiencia (XP) y vocabulario aprendido desde Duolingo. |

### 5. Evaluaciones y Método Feynman (`exam` / `feynman`)

| Comando | Descripción |
|---|---|
| `aulento exam create` | Genera una evaluación de preguntas conceptuales sobre un tema o módulo. |
| `aulento feynman evaluate` | Evalúa una explicación conceptual provista por el estudiante usando el método Feynman y un LLM. |

### 6. Temporizador Pomodoro / Focus (`focus`)

| Comando | Descripción |
|---|---|
| `aulento focus start` | Inicia una sesión interactiva de enfoque Pomodoro con temporizador en terminal. |
| `aulento focus stats` | Muestra estadísticas acumuladas de tiempo de enfoque y sesiones completadas. |

### 7. Repetición Espaciada FSRS v5 (`fsrs`)

| Comando | Descripción |
|---|---|
| `aulento fsrs add` | Agrega manualmente una nueva tarjeta de estudio al mazo FSRS de la cuenta. |
| `aulento fsrs consulting` | Inicia un drill de simulación de consultoría técnica en inglés con evaluación por IA. |
| `aulento fsrs evaluate-pronunciation` | Evalúa la pronunciación de una frase o término técnico en audio. |
| `aulento fsrs gemini-config` | Configura los parámetros del tutor de pronunciación y audio con Google Gemini. |
| `aulento fsrs gemini-evaluate` | Ejecuta la evaluación interactiva de fonética con el tutor Gemini. |
| `aulento fsrs harvest` | Cosecha tarjetas desde las notas del vault, los materiales subidos (`--source materiales`, con `--topic` o `--material-id`) o la IA. |
| `aulento fsrs levels` | Lista los niveles progresivos de dificultad y vocabulario en FSRS. |
| `aulento fsrs list` | Lista todas las tarjetas del banco de memoria con sus parámetros de estabilidad y dificultad. |
| `aulento fsrs seed` | Siembra tarjetas iniciales de vocabulario y expresiones técnicas en inglés. |
| `aulento fsrs speak` | Pronuncia un término técnico o colocación en inglés utilizando síntesis de voz (TTS). |
| `aulento fsrs status` | Muestra un resumen de tarjetas vencidas hoy, aprendidas y en retención a largo plazo. |
| `aulento fsrs study` | Inicia una sesión interactiva de repaso en terminal respondiendo tarjetas pendientes. |

### 8. Hub de Plataformas Educativas (`hub`)

| Comando | Descripción |
|---|---|
| `aulento hub add-course` | Registra un nuevo curso asociándolo a una plataforma académica. |
| `aulento hub add-platform` | Da de alta una nueva plataforma educativa (Coursera, Humai, etc.). |
| `aulento hub list` | Muestra el catálogo jerárquico de plataformas y cursos con sus porcentajes de avance. |
| `aulento hub sync` | Sincroniza el avance de un curso registrado mediante adaptadores o webhook. |
| `aulento hub sync-google-skills` | Sincroniza cursos asociados a Google Cloud Skills Boost con un perfil público. |
| `aulento hub sync-status` | Muestra el estado general de sincronización de cursos y fecha de última actualización. |
| `aulento hub update-progress` | Actualiza el avance porcentual y estado de un curso. |
| `aulento hub webhook-info` | Muestra la configuración, instrucciones y URL del webhook universal de cursos. |

### 9. Proveedores de Inteligencia Artificial (`ia`)

| Comando | Descripción |
|---|---|
| `aulento ia models` | Lista los modelos disponibles para el proveedor configurado (Gemini, Claude, OpenAI). |
| `aulento ia remove-key` | Elimina la clave de API guardada para un proveedor de IA. |
| `aulento ia set-key` | Almacena y cifra con AES-GCM la clave de API de un proveedor para la cuenta activa. |
| `aulento ia set-model` | Fija el modelo de lenguaje predeterminado para la cuenta activa. |
| `aulento ia set-provider` | Selecciona el proveedor de IA activo (`gemini`, `anthropic`, `openai`). |
| `aulento ia status` | Muestra el proveedor actual, modelo seleccionado y estado de la clave de API. |
| `aulento ia test` | Realiza una llamada de prueba al proveedor configurado para verificar conectividad y saldo. |

### 10. Servidor MCP (`mcp`)

Los comandos de Google Drive y OneDrive (`mcp status`, `toggle`, `config`, `search`, `inspect`, `auth-gdrive` y `disconnect-gdrive`) se quitaron con los conectores (ADR 015). Los materiales se suben desde la web; desde la CLI se consultan con `vault list-materials` y se usan con `vault note-from-material` y `fsrs harvest --source materiales`.

| Comando | Descripción |
|---|---|
| `aulento mcp serve` | Inicia el servidor MCP local para conectar clientes como Claude Desktop o Cursor. |
| `aulento mcp token create` | Genera un nuevo token de acceso para autenticar clientes en el servidor MCP. |
| `aulento mcp token list` | Lista los tokens de acceso MCP emitidos para la cuenta activa. |
| `aulento mcp token revoke` | Revoca de forma inmediata un token de acceso MCP. |

### 11. Asistente de Inicio (`onboarding`)

| Comando | Descripción |
|---|---|
| `aulento onboarding` | Ejecuta el asistente interactivo por terminal: base de datos, mazo inicial y clave de IA. Si todavía no hay ninguna cuenta, crea la cuenta local, sin contraseña. |

### 12. Rutas de Aprendizaje (`roadmap`)

| Comando | Descripción |
|---|---|
| `aulento roadmap compare` | Compara los temas de una ruta existente frente al programa de estudios de un PDF externo. |
| `aulento roadmap create` | Crea una nueva ruta de aprendizaje definiendo título, categoría y perfil pedagógico. |
| `aulento roadmap import` | Importa una ruta de aprendizaje completa desde un archivo de sílabo estructurado. |
| `aulento roadmap list` | Lista todas las rutas de estudio registradas con su avance y cantidad de módulos. |
| `aulento roadmap prompt` | Genera el Master Prompt pedagógico adaptativo para un tema específico de la ruta. |
| `aulento roadmap restore` | Restaura una versión histórica previa de la lección magistral de un tema. |
| `aulento roadmap seed` | Siembra plantillas de rutas prediseñadas (Software Architecture, Data/AI, Cloud). |
| `aulento roadmap show` | Muestra el desglose detallado de módulos, temas y prerrequisitos de una ruta. |
| `aulento roadmap versions` | Lista el historial de versiones guardadas de la clase de un tema. |

### 13. Agenda y Cronograma Semanal (`schedule`)

| Comando | Descripción |
|---|---|
| `aulento schedule add` | Añade un bloque horario de estudio semanal a la agenda. |
| `aulento schedule list` | Lista todos los bloques horarios semanales programados de Lunes a Domingo. |

### 14. Cuentas (`user`)

El core es de una sola persona: no crea cuentas con contraseña ni invitaciones. La cuenta local la crean la web o el asistente de inicio.

| Comando | Descripción |
|---|---|
| `aulento user import-files` | Importa notas, tarjetas y configuración desde un directorio legado hacia la cuenta. Los archivos viejos de Drive (`mcp_config.json`, `gdrive_token.json`) ya no se importan. |
| `aulento user list` | Lista todos los usuarios registrados en el sistema con su estado y rol. |

### 15. Bóveda de Notas Obsidian (`vault`)

| Comando | Descripción |
|---|---|
| `aulento vault export-weekly` | Genera y exporta el informe consolidado Weekly Digest en formato Markdown hacia el Vault. |
| `aulento vault inspect` | Muestra el contenido y metadatos de una nota específica del Vault. |
| `aulento vault list` | Lista las notas académicas indexadas dentro de la carpeta del Vault. |
| `aulento vault list-materials` | Lista los materiales subidos por la cuenta con los que se puede generar un apunte. |
| `aulento vault location` | Muestra la ruta física configurada para la carpeta del Obsidian Vault. |
| `aulento vault note-from-material` | Genera un apunte SOP para el Vault a partir de un material subido (`--material-id`). |
| `aulento vault note-template` | Genera una plantilla de nota estructurada para una clase o tema determinado. |
| `aulento vault seed-samples` | Siembra notas y apuntes de ejemplo en la estructura del Vault. |
| `aulento vault stats` | Muestra estadísticas del Vault: cantidad total de notas, enlaces y tamaño ocupado. |

### 16. Servidor Web y Dashboard (`web` / `serve`)

| Comando | Descripción |
|---|---|
| `aulento web openapi` | Exporta el esquema OpenAPI canónico serializado en JSON hacia un archivo o stdout. |
| `aulento web start` | Inicia el servidor web local con Uvicorn y FastAPI para acceder al dashboard web. |


### 17. Planificador Adaptativo de Estudio (`planner`)

| Comando | Descripción |
|---|---|
| `aulento planner briefing` | Muestra el resumen ejecutivo matutino y estado de urgencia pedagógica. |
| `aulento planner plan` | Calcula un plan de estudio adaptativo estructurado en fases y permite aplicarlo a la agenda. |
