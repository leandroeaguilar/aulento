---
type: Guia
title: "Guía de Gestión de Base de Datos, Backups y Demos"
description: "Manual de administración de la base de datos local SQLite: qué respaldar (base, clave maestra y carpeta de cuentas con vaults y materiales subidos), migraciones y sus respaldos, datos por cuenta y herencia a la primera cuenta, importación de los archivos anteriores, restauración, mazo FSRS de fábrica y entornos de demostración."
generated:
  by: process:claude-code
  at: 2026-11-05T00:00:00Z
---

# Guía de Gestión de Base de Datos, Backups y Demos

Este documento resume la arquitectura de almacenamiento de datos de **Aulento**, los procedimientos de respaldo y restauración, y las instrucciones para manejar entornos de demostración o compartir el software con terceros.

---

## 1. Dónde residen tus datos personales

Aulento es un sistema **Local-First**. Todo lo que guarda vive en un único **directorio de datos**: el de la variable `AULENTO_DATA_DIR` o, si no está definida, `~/.aulento` (en Windows, `C:\Users\<tu_usuario>\.aulento`).

| Dentro del directorio de datos | Qué es |
| :--- | :--- |
| `study_engine.db` | La base: datos de estudio, cuentas, ajustes de cada cuenta y sus secretos cifrados. `AULENTO_DB_PATH` la lleva a otro lugar. |
| `clave_maestra.key` | La clave con la que se cifran los secretos de todas las cuentas. No existe si definiste `AULENTO_SECRET_KEY`. Se genera restringida a quien corre el servidor (ver «Permisos de la clave maestra»). |
| `usuarios/<id>/vault/` | El vault de cada cuenta: sus notas, clases y resúmenes. |
| `usuarios/<id>/materiales/` | Los materiales que subió cada cuenta (PDF, Markdown y texto), con nombres que genera el servidor. Hasta 200 MB por cuenta. Su texto extraído está en la tabla `materiales` de la base. |
| `importado-<fecha>/` | Los archivos de una instalación anterior, ya importados (ver la sección 2). |

- **Seguridad en Git:** La base de datos y la carpeta `.aulento/` están ignoradas en `.gitignore`. Tus datos **nunca** se envían a GitHub ni se comparten al pasar el código del repositorio.

### Qué respaldar

Un respaldo completo son **tres cosas**, copiadas con el servidor detenido:

1. **La base** (`study_engine.db`).
2. **La clave maestra:** el archivo `clave_maestra.key` o, si la definiste por variable, el valor de `AULENTO_SECRET_KEY`.
3. **La carpeta `usuarios/`**, con el vault y los materiales subidos de cada cuenta. La base y esta carpeta van juntas: una base restaurada sin `usuarios/<id>/materiales/` lista materiales cuyo archivo ya no está.

Un administrador que apuntó su vault a una carpeta de fuera del directorio de datos la respalda aparte: no está en `usuarios/`. Esa carpeta no puede ser, contener ni estar dentro del directorio de datos ni de la carpeta donde vive la base (también si moviste la base con `AULENTO_DB_PATH`); si más adelante pasa a llevar a una de ellas —por ejemplo porque se la reemplazó por una unión o un enlace— el vault deja de usarse y las operaciones lo informan.

Guardá la clave maestra en un lugar distinto del de la base. Con las dos juntas, quien se lleve el respaldo lee los secretos; con la base sola, no.

### Permisos de la clave maestra

Al generar `clave_maestra.key`, el servidor deja el archivo accesible solo para el usuario que lo corre:

- **Linux y macOS:** permisos `0600`.
- **Windows:** quita los permisos heredados de la carpeta y deja una sola entrada, de control total para ese usuario (`icacls <archivo> /inheritance:r /grant:r <usuario>:F`). Lo comprueba `tests/test_secretos.py::test_en_windows_el_archivo_de_la_clave_queda_solo_para_quien_corre_el_proceso`.

Si no se pudo restringir (un sistema de archivos sin permisos, una herramienta del sistema que falta), la clave se genera igual y el servidor **lo avisa** en el registro y en la consola: restringilo a mano o pasá la clave a `AULENTO_SECRET_KEY`. Tené en cuenta además que:

- Un archivo de clave que ya existía, o uno que restauraste de un respaldo, **no se toca**: revisá sus permisos vos.
- Una copia del archivo toma los permisos de la carpeta donde la dejes, no los del original.
- Si otro usuario de Windows tiene que correr el servidor, hay que darle acceso al archivo a mano.

Una clave maestra mal formada (la variable o el archivo) no se reemplaza por otra: la web responde 503 con la forma de resolverlo, las pantallas de estado siguen cargando y la CLI termina con el mensaje, sin tocar los secretos guardados.

### Si se pierde la clave maestra

Los secretos guardados (claves de IA y autorización de Google Play Libros de cada cuenta) no se pueden recuperar. Nada más se pierde: los datos de estudio, los ajustes, los vaults y los materiales subidos no están cifrados.

- El servidor arranca igual y, si falta el archivo, genera una clave nueva y lo avisa.
- Lo que necesita un secreto anterior responde que no se pudo leer (en la API, 503). El secreto guardado no se borra ni se pisa: si recuperás la clave original, vuelve a leerse.
- Para seguir sin ella, cada cuenta vuelve a cargar sus claves de IA y vuelve a vincular Google Play Libros. Cargar un secreto reemplaza al ilegible.

Una clave mal formada (un archivo dañado, una variable mal copiada) detiene el arranque con un mensaje que lo dice. No se genera otra: restaurala desde tu respaldo.

---

## 2. Migraciones, datos por cuenta y herencia

El esquema tiene versión (`PRAGMA user_version`) y se actualiza solo: al arrancar el servidor o al correr un comando de la CLI se aplican, en orden, las migraciones que falten. No hay que ejecutar nada a mano.

### Respaldo previo

Antes de aplicar migraciones sobre una base en archivo que ya tiene tablas, Aulento deja una copia completa junto a ella:

```text
~/.aulento/study_engine.db.respaldo-v<versión anterior>-<fecha y hora>
```

Cada migración corre en su propia transacción: si falla, se revierte, la versión no avanza y el servidor no arranca. Para volver atrás se usa esa copia igual que cualquier otro respaldo (ver la sección 3). Los respaldos no se borran solos: eliminá los viejos cuando ya no los necesites.

### Migración 3: cada fila tiene dueño

La migración 3 (feature 033, ADR 007) separa los datos por cuenta:

- Agrega la columna `user_id` a las ocho tablas raíz: `plataformas`, `libros_lectura`, `bloques_horarios`, `fsrs_items`, `sesiones_estudio`, `rutas_aprendizaje`, `api_usage_logs` y `mcp_audit_logs`. Las tablas que dependen de ellas (cursos, módulos, temas, clases, repasos...) no llevan la columna: su dueño es el de la fila raíz de la que cuelgan.
- Reconstruye `plataformas`, `rutas_aprendizaje` y `fsrs_items` para que sus unicidades valgan por cuenta: dos cuentas pueden tener una plataforma, una ruta o una tarjeta con el mismo nombre; una misma cuenta, no.
- Crea la tabla `mcp_tokens` para los tokens del servidor MCP ([guía MCP](GUIA_MCP.md)).
- Conserva todas las filas de todas las tablas y sus identificadores. Antes de confirmar comprueba que no quede ninguna referencia rota; si queda, revierte.

### Herencia de los datos existentes

Los datos cargados antes de la migración no se pierden ni quedan a la vista de cualquiera:

- **Si al migrar no hay ninguna cuenta** (una instalación anterior a las cuentas), las filas quedan **sin dueño**. Una fila sin dueño no la ve ni la modifica ninguna cuenta: ni la web, ni la CLI, ni el servidor MCP. **La primera cuenta que se crea las recibe todas**: la cuenta local, que crean la web o el asistente de inicio (`aulento onboarding`), o la primera que se registra en un servidor con varias cuentas. La segunda cuenta y las siguientes empiezan vacías.
- **Si al migrar ya hay cuentas**, las filas sin dueño pasan al administrador activo más antiguo. Si no hubiera ningún administrador activo quedan sin dueño hasta que se crea una cuenta administradora: la que queda como único administrador activo las recibe. Esa cuenta recibe las filas, **no los archivos anteriores** (ver la sección 2): los pide con `user import-files`.

En la práctica: actualizás, arrancás el servidor, creás tu cuenta con el código de invitación que imprime la consola y encontrás todos tus datos.

`db status` muestra primero los totales de la instalación (todas las cuentas juntas, incluidas las filas sin dueño) y después los de la cuenta con la que opera la CLI. Si el total del sistema es mayor que el de tu cuenta y sos la única persona, todavía hay filas sin dueño: aparecen cuando se crea la primera cuenta.

### La CLI opera como una cuenta

Los comandos que tocan datos de estudio (`books`, `hub`, `schedule`, `fsrs`, `roadmap`, `focus`, `activity`...) operan como una cuenta: la indicada con la opción global `--user <nombre>` (va antes del comando) o con la variable `AULENTO_USER`; si no se indica, la única cuenta activa cuando hay exactamente una. Con cero o varias cuentas activas, o si la indicada no existe o está desactivada, el comando termina con un error que explica cómo indicarla y no toca nada. `db`, `user` y `web` funcionan sin cuenta.

### Almacén de vectores (opcional)

Si usás la búsqueda semántica con PostgreSQL y pgvector, cada fragmento indexado también lleva su dueño (`knowledge_embeddings.user_id`):

- En un contenedor creado antes de esta versión la columna no existe: el servidor la agrega solo la primera vez que usa el almacén (el usuario de PostgreSQL necesita permiso para alterar la tabla). Los fragmentos anteriores quedan sin dueño e invisibles: hay que volver a indexar. `POST /api/vectors/init` crea el almacén desde cero y es solo para administradores.
- Los fragmentos indexados antes quedan sin dueño y no aparecen en ninguna búsqueda. Se recuperan reindexando: **Indexar todo** en la interfaz o `POST /api/vectors/sync-catalog`.

### Migración 4: secretos y ajustes por cuenta

La migración 4 (feature 034, ADR 008) crea dos tablas, las dos con la cuenta como parte de su clave:

- `secretos_usuario`: claves de IA y autorizaciones OAuth, cifradas con la clave maestra.
- `ajustes_usuario`: nivel y modelo de IA, prompts de sistema, usuario y caché de Duolingo y vault externo.

Borrar una cuenta se lleva sus filas de las dos.

### Migración 7: materiales subidos y retiro de Drive y OneDrive

La migración 7 (feature 048, ADR 015):

- Crea la tabla `materiales`, con dueño por fila (`user_id`): nombre original, extensión, tipo, tamaño, hash, el nombre del archivo en `usuarios/<id>/materiales/`, el texto extraído completo y su cantidad de caracteres. El mismo contenido no se guarda dos veces en una cuenta.
- **Borra** de `secretos_usuario` las autorizaciones de Google Drive y OneDrive y el cliente de OneDrive, y de `ajustes_usuario` los ajustes de los conectores (activos, carpetas raíz, autorizaciones rechazadas). Quien tenía Drive u OneDrive conectado baja sus archivos y los sube como materiales.
- **Conserva** `gdrive_cliente`, el cliente OAuth propio de Google, porque lo usa Google Play Libros.

La copia del «Respaldo previo» de la base conserva lo que esta migración borra.

### Migración 10: lo que «Indexar todo» ya indexó

La migración 10 (feature 059) crea `hashes_indexados`: por cuenta, la huella de cada material y nota que «Indexar todo» mandó a pgvector (su texto y el modelo de embeddings con que se indexó). Con ella la siguiente corrida saltea lo que no cambió. Se borra con la cuenta. No guarda los vectores: si se vacía pgvector o se cambia de modelo, la siguiente corrida vuelve a indexar todo.

### Migración 11: tokens de alcance limitado

La migración 11 (feature 061) crea `tokens_de_alcance`: por cuenta, la huella (nunca el token en claro) de la dirección de suscripción al calendario y del código de libros para Atajos. Cada uno sirve para una sola cosa y no abre el resto de la API. Crear uno nuevo deja revocado el anterior, que queda en la tabla con su fecha de revocación. Se borra con la cuenta.

### Importación de los archivos anteriores

Antes de la 034 las claves, los prompts, la caché de Duolingo y el vault eran archivos sueltos del directorio de datos, compartidos por todas las cuentas. El servidor ya no los lee. Se cargan, una vez, en una cuenta:

- **Sola**, cuando se crea la primera cuenta de la instalación, y solo entonces. Un administrador que se crea después, aunque quede como el único activo y herede las filas sin dueño, no la dispara: los archivos y el vault podrían ser de quien estaba antes.
- **A pedido**, para la cuenta que indiques:
  ```powershell
  .\.venv\Scripts\python.exe -m aulento user import-files tu_usuario
  .\.venv\Scripts\python.exe -m aulento user import-files tu_usuario --vault "D:\Obsidian\MiVault"
  .\.venv\Scripts\python.exe -m aulento user import-files tu_usuario --from "D:\copia-de-los-datos"
  ```
  `--vault` registra una carpeta existente de la máquina del servidor como vault de la cuenta, sin moverla. Solo vale para una cuenta administradora, y la carpeta no puede ser, contener ni estar dentro del directorio de datos ni de la carpeta de la base.

  `--from` recorre esa carpeta (tiene que existir) en vez del directorio de datos del servidor; el respaldo `importado-<fecha>/` queda dentro de ella. Sirve para ensayar sobre una copia: **conviene hacerlo antes de importar en la instalación real**, porque los archivos de cada instalación tienen sus particularidades.

Qué hace:

- Carga solo lo que la cuenta no tiene. Se puede repetir: no duplica ni pisa nada.
- Muda el vault anterior (`vault/`) al de la cuenta, si el de la cuenta está vacío. Lo hace archivo por archivo y sin pisar ninguno: si se corta a mitad (un archivo abierto, el disco lleno, una ruta demasiado larga), el informe dice cuántos faltaron y **otra pasada termina la mudanza**. Mientras dura, el vault anterior lleva la marca `.mudanza-a-la-cuenta.json` con la cuenta de destino; es lo que permite retomarla aunque el vault de la cuenta ya tenga las notas que se alcanzaron a mover. Sin esa marca, un vault de cuenta que ya tiene notas no se mezcla con el anterior: se deja y se informa.
- Una nota que ya existe en el vault de la cuenta con otro contenido no se pisa ni se borra: queda en el vault anterior y el informe la nombra para que la resuelvas a mano. Si existe idéntica, solo se quita la copia del vault anterior.
- Lee también `AULENTO_VAULT_PATH` y `OBSIDIAN_VAULT_PATH` si siguen definidas, y avisa que ya se pueden quitar. Las claves de IA salen solo de sus archivos, no de variables.
- Los archivos de Google Drive (`mcp_config.json`, `gdrive_token.json`, el cliente OAuth) y las variables `GDRIVE_CREDENTIALS_PATH` y `GDRIVE_ROOT_FOLDER_ID` ya no se importan: los conectores de nube se quitaron en la 048. Quedan donde están y se pueden borrar.
- Si la cuenta termina sin ninguna clave de IA, lo avisa: una clave que vivía solo en una variable de entorno no se importa y hay que cargarla desde Configuración.
- Muestra un informe elemento por elemento, sin el contenido de ningún archivo. Uno que no se pudo leer queda informado, en su lugar, y no frena al resto.

### La carpeta `importado-<fecha>/`

Cada archivo cuyo dato quedó en la cuenta se mueve a `importado-<fecha>/`, dentro del directorio de datos (o de la carpeta indicada con `--from`). Nada se borra.

**Esa carpeta guarda los archivos tal como estaban, con las claves en claro.** Cuando compruebes que todo funciona (la IA responde, tus notas están), borrala. El servidor no la usa: borrarla no cambia nada. El aviso sale en el informe de la CLI y, cuando la importación corrió sola al registrarse la primera cuenta por la web, en el registro del servidor (nivel WARNING).

Un archivo que estaba fuera del directorio de datos se importa pero no se mueve: el informe avisa y lo borrás vos.

---

## 3. Registro del Respaldo Histórico (Backup)

Antes del reinicio a cero del 30 de septiembre de 2026, se generó un respaldo completo de la base de datos previa (que contenía las 8 rutas de prueba y las 188 tarjetas FSRS con 28 repasos de test).

- **Ubicación del archivo de respaldo:**
  ```text
  ~/.aulento/aulento_backup_20260930.db
  ```

### ¿Cómo restaurar el respaldo si lo necesitas en el futuro?
Si alguna vez deseas volver al estado previo o consultar alguna ruta anterior:

1. **Detén** cualquier proceso activo del servidor web (`aulento serve`).
2. **Copia y reemplaza** el archivo en PowerShell:
   ```powershell
   Copy-Item "$HOME\.aulento\aulento_backup_20260930.db" "$HOME\.aulento\study_engine.db" -Force
   ```
3. Verifica el estado:
   ```powershell
   .\.venv\Scripts\python.exe -m aulento db status
   ```

Una base restaurada trae los secretos cifrados con la clave maestra de cuando se hizo la copia: restaurá también esa clave (ver la sección 1). Las notas vuelven con la carpeta `usuarios/`.

---

## 4. Mazo Inicial de Fábrica FSRS (Inglés Técnico)

El repositorio incluye un mazo de colocaciones profesionales de inglés (159 tarjetas de Cloud, Data, IA y Standups) en `src/aulento/fsrs/deck_seed.py`.

Sembrar es una operación de una cuenta: ni el arranque del servidor ni la migración cargan datos iniciales, y una cuenta nueva empieza sin plataformas ni tarjetas. Lo que se siembra queda a nombre de la cuenta con la que opera la CLI (ver la sección 2) y no toca a las demás.

- Para cargar las 5 plataformas y el mazo de fábrica en tu cuenta, ejecuta `db init` (si no hay una cuenta que usar, crea las tablas, avisa que no sembró y termina bien; si indicaste con `--user` una cuenta que no existe o está desactivada, termina con error):
  ```powershell
  .\.venv\Scripts\python.exe -m aulento --user tu_usuario db init
  ```
- Si en el futuro deseas inyectar solo el mazo de fábrica, ejecuta:
  ```powershell
  .\.venv\Scripts\python.exe -m aulento fsrs seed
  ```
- Si deseas agregar tus propias tarjetas personalizadas:
  ```powershell
  .\.venv\Scripts\python.exe -m aulento fsrs add
  ```

---

## 5. Cómo levantar una Demo o probar sin ensuciar tus datos

Para montar una demo pública, grabar un video o compartir una instancia de prueba con un amigo sin exponer tus métricas reales:

1. Define la variable de entorno `AULENTO_DB_PATH` apuntando a una base alternativa:
   ```powershell
   # En la sesión de PowerShell de la demo:
   $env:AULENTO_DB_PATH = "$PWD\demo.db"
   # Otro directorio de datos: la demo no comparte la clave maestra ni los vaults con tu instalación
   $env:AULENTO_DATA_DIR = "$PWD\demo-datos"
   
   # Crear las tablas y la cuenta local, con el mazo de fábrica si lo elegís
   .\.venv\Scripts\python.exe -m aulento onboarding
   
   # Levantar el servidor web para la demo
   .\.venv\Scripts\python.exe -m aulento serve
   ```
2. Al cerrar esa terminal o ejecutar `$env:AULENTO_DB_PATH = $null` y `$env:AULENTO_DATA_DIR = $null`, Aulento vuelve a usar de forma transparente tu base de datos personal.

---

## 6. Comandos de Mantenimiento Frecuentes

Los comandos de datos aceptan la opción global `--user <nombre>` antes del comando; con una sola cuenta activa no hace falta.

| Comando | Acción |
| :--- | :--- |
| `python -m aulento db status` | Muestra el recuento de registros en SQLite: totales de la instalación y de la cuenta |
| `python -m aulento user list` | Lista las cuentas y si están activas |
| `python -m aulento user import-files <usuario>` | Importa a esa cuenta los archivos anteriores del directorio de datos (o de la carpeta de `--from`) |
| `python -m aulento vault location` | Dice si la cuenta usa su vault propio o una carpeta externa |
| `python -m aulento fsrs status` | Muestra racha, tarjetas vencidas hoy y retención FSRS v5 |
| `python -m aulento roadmap list` | Lista las rutas de estudio activas y su porcentaje |
| `python -m aulento activity streak` | Muestra la racha y consistencia diaria |
