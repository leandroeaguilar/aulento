---
type: Especificacion
title: "Lista Maestra de Verificación de Seguridad y Auditoría Defensiva (AppSec & SecOps)"
description: "Checklist exhaustivo de seguridad para Aulento: OWASP Top 10, OWASP LLM Top 10, cuentas y sesiones, control de acceso, aislamiento de datos por cuenta, secretos y configuración por cuenta, sandboxing de archivos, aislamiento de red y pruebas automatizadas."
generated:
  by: process:claude-code
  at: 2026-11-05T00:00:00Z
---

# Lista Maestra de Verificación de Seguridad (Security Verification Checklist)

Esta lista de verificación constituye el marco formal de auditoría y hardening para **Aulento**. Cubre todas las capas de la arquitectura: API REST FastAPI, cuentas y sesiones de la interfaz web, almacenamiento relacional SQLite (WAL), base de datos vectorial PostgreSQL (`pgvector` en Docker), materiales que sube cada cuenta, servidor MCP, secretos y configuración de cada cuenta, vault por cuenta y el motor de IA basado en Google Gemini.

> [!WARNING]
> Desde la feature 033 cada cuenta ve y modifica solo sus datos de estudio (ADR 007) y desde la 034 también es de cada cuenta lo que vivía en archivos: claves de IA, prompts de sistema, Duolingo y vault (ADR 008); los conectores de Drive y OneDrive, que también eran por cuenta, se quitaron en la 048 (ADR 015). **Si la clave maestra se generó junto a la base, el cifrado no protege a quien copie todo el directorio de datos**: por eso, desde la 039, el servidor no arranca fuera del bucle local sin `AULENTO_SECRET_KEY` (CHK-13.38; ADR 013). Los demás riesgos abiertos están en las secciones 10, 11 y 12.

La columna de prueba nombra el test que verifica cada control. Un nombre suelto vive en `tests/test_deep_security_audit.py`; el resto lleva su archivo de `tests/` como `archivo.py::test`.

---

## Matriz de Dominios y Controles de Seguridad

| ID Control | Dominio | Amenaza Mitigada / Estándar | Estado | Prueba Automatizada Asociada |
|---|---|---|---|---|
| **CHK-01.1** | Inyección & Sanitización | SQL Injection clásico en SQLite (OWASP A03:2021) | 🟢 Verificado | `test_deep_sec_01_sqlite_sqli_immunity` |
| **CHK-01.2** | Inyección & Sanitización | SQL Injection en pgvector / cosine search (OWASP A03) | 🟢 Verificado | `test_deep_sec_02_pgvector_sqli_immunity` |
| **CHK-01.3** | Inyección & Sanitización | Prompt Injection Indirecto en Gemini Tutor (OWASP LLM01) | 🟢 Verificado | `test_deep_sec_03_gemini_tutor_prompt_injection` |
| **CHK-01.4** | Inyección & Sanitización | Prompt Injection en Agente MCP RAG (OWASP LLM01) | 🟢 Verificado | `test_deep_sec_04_mcp_agent_prompt_injection_defense` |
| **CHK-02.1** | Red & Fronteras | Exposición de PostgreSQL en LAN (0.0.0.0 vs 127.0.0.1) | 🟢 Verificado | `test_deep_sec_05_docker_postgres_local_binding` |
| **CHK-02.2** | Red & Fronteras | DNS Rebinding & Host Header Injection (OWASP A01:2021) | 🟢 Verificado | `test_deep_sec_06_trusted_host_dns_rebinding_defense` |
| **CHK-02.3** | Red & Fronteras | CSRF & Secuestro Cross-Origin (LocalOriginAuthMiddleware) | 🟢 Verificado | `test_deep_sec_07_cors_and_csrf_origin_blocking` |
| **CHK-02.4** | Red & Fronteras | Mutaciones de estado Cross-Site (`Sec-Fetch-Site`) | 🟢 Verificado | `test_deep_sec_08_cross_site_fetch_mutation_blocked` |
| **CHK-03.1** | Sandbox & Sistema de Archivos | Path Traversal en creación de notas (`..` / directory escape) | 🟢 Verificado | `test_deep_sec_09_vault_path_traversal_confinement` |
| **CHK-03.2** | Sandbox & Sistema de Archivos | Directory Escape en lectura de Vault (`VaultReader`) | 🟢 Verificado | `test_deep_sec_10_vault_reader_directory_escape` |
| **CHK-03.3** | Sandbox & Sistema de Archivos | Ejecución Arbitraria en `/open-local` (`os.path.isdir`) | 🟢 Verificado | `test_deep_sec_11_open_local_directory_only_check` |
| **CHK-03.4** | Sandbox & Sistema de Archivos | Evasión de directorio estático (`/static/../secrets`) | 🟢 Verificado | `test_deep_sec_12_static_directory_traversal_blocked` |
| **CHK-04.1** | Secretos & Criptografía | Timing Attacks en Bearer Tokens (`hmac.compare_digest`) | 🟢 Verificado | `test_deep_sec_13_timing_attack_resistant_tokens` |
| **CHK-04.2** | Secretos & Criptografía | Eco de una clave en la API: de lo cargado vuelve solo si está y sus últimos cuatro caracteres | 🟢 Verificado | `test_deep_sec_14_api_credentials_masking` |
| **CHK-04.3** | Secretos & Criptografía | Filtración de API Keys en URL (`?key=` prohibido) | 🟢 Verificado | `test_deep_sec_15_api_keys_strictly_in_headers` |
| **CHK-04.4** | Secretos & Criptografía | Conectores de nube que guardaban credenciales y autorizaciones de Drive y OneDrive: se retiraron en la 048 y sus módulos ya no existen | 🟢 Verificado | `test_deep_sec_16_no_quedan_conectores_de_nube_que_guarden_credenciales` |
| **CHK-04.5** | Secretos & Criptografía | Integridad de `.gitignore` contra fugas a Git | 🟢 Verificado | `test_deep_sec_17_gitignore_protection_integrity` |
| **CHK-05.1** | DoS & Validación de Carga | Búsqueda semántica con queries gigantes (límite 2000 chars) | 🟢 Verificado | `test_deep_sec_18_vector_search_payload_bounds` |
| **CHK-05.2** | DoS & Validación de Carga | Límite de lote en `/index-selection` (máx. 100 ítems) | 🟢 Verificado | `test_deep_sec_19_selection_index_batch_limits` |
| **CHK-05.3** | DoS & Validación de Carga | Validación estricta de IDs en rutas REST (`ge=1`) | 🟢 Verificado | `test_deep_sec_20_path_id_validation_and_errors` |
| **CHK-05.4** | DoS & Validación de Carga | Validación de avance de páginas en libros (`1 <= pages <= 5000`) | 🟢 Verificado | `test_deep_sec_21_advance_pages_bounds_validation` |
| **CHK-06.1** | Seguridad del Navegador | Content Security Policy (CSP) restrictivo (`object-src none`) | 🟢 Verificado | `test_deep_sec_22_hardened_csp_headers` |
| **CHK-06.2** | Seguridad del Navegador | Prevención de Clickjacking (`X-Frame-Options: DENY`) | 🟢 Verificado | `test_deep_sec_23_clickjacking_defense_header` |
| **CHK-06.3** | Seguridad del Navegador | Prevención de MIME-Sniffing (`nosniff`) | 🟢 Verificado | `test_deep_sec_24_mime_sniffing_defense_header` |
| **CHK-07.1** | Manejo de Errores | Sanitización de errores 404/400 (sin fugas de stack traces) | 🟢 Verificado | `test_deep_sec_25_clean_error_handling_no_leaks` |
| **CHK-11.1** | Integridad de Datos | Pérdida de datos al migrar: respaldo previo de la base en archivo | 🟢 Verificado | `test_migrations.py::test_base_en_archivo_con_datos_deja_respaldo_con_los_datos_previos` |
| **CHK-11.2** | Integridad de Datos | Base a medio migrar: la migración que falla revierte y no avanza la versión | 🟢 Verificado | `test_migrations.py::test_migracion_que_falla_revierte_y_no_avanza_la_version` |
| **CHK-11.3** | Integridad de Datos | Arranque silencioso sobre un esquema roto: el servidor no arranca si la migración falla | 🟢 Verificado | `test_migrations.py::test_el_arranque_del_servidor_no_traga_el_error_de_migracion` |
| **CHK-12.1** | Aislamiento por Cuenta | Repositorio o servicio de datos construido sin cuenta: falla en el acto, sin valor por defecto (OWASP A01:2021) | 🟢 Verificado | `test_aislamiento_repos.py::test_r6_la_cuenta_no_tiene_valor_por_defecto` |
| **CHK-12.2** | Aislamiento por Cuenta | Fuga por un filtro olvidado: ninguna sentencia SQL de `src/` toca una tabla raíz sin `user_id`, salvo una lista de excepciones justificadas | 🟢 Verificado | `test_aislamiento_sql.py::test_r6_ninguna_sentencia_toca_una_tabla_raiz_sin_la_cuenta` |
| **CHK-12.3** | Aislamiento por Cuenta | Sentencia nueva sin filtro que pasa inadvertida: el recorrido estático la marca | 🟢 Verificado | `test_aislamiento_sql.py::test_el_recorrido_muerde_una_sentencia_sin_filtro_agregada_a_un_repositorio_real` |
| **CHK-12.18** | Aislamiento por Cuenta | Búsqueda semántica cruzada: buscar, contar y borrar fragmentos alcanzan solo los de la cuenta | 🟢 Verificado | `test_vector_postgres.py::test_r11_buscar_contar_y_borrar_alcanzan_solo_los_fragmentos_de_la_cuenta` |
| **CHK-12.19** | Aislamiento por Cuenta | Indexar un libro o un curso ajeno en el almacén de vectores: responde 404 y no indexa nada | 🟢 Verificado | `test_vector_postgres.py::test_r11_reindexar_un_libro_o_un_curso_ajeno_responde_404` |
| **CHK-12.21** | Aislamiento por Cuenta | Pérdida de filas al agregar el dueño: la migración conserva cada fila de cada tabla y sus referencias | 🟢 Verificado | `test_migrations.py::test_base_en_version_2_con_filas_en_todas_las_tablas_migra_conservando_cada_fila` |
| **CHK-13.1** | Secretos & Configuración por Cuenta | Robo de la base: los secretos de cada cuenta se guardan cifrados (Fernet) y el archivo de la base no los tiene en claro (OWASP A02:2021) | 🟢 Verificado | `test_secretos.py::test_lo_guardado_persiste_y_el_archivo_de_la_base_no_tiene_el_valor_en_claro` |
| **CHK-13.2** | Secretos & Configuración por Cuenta | Fila cifrada copiada a otra cuenta: no descifra como propia | 🟢 Verificado | `test_secretos.py::test_una_fila_copiada_a_otra_cuenta_no_descifra` |
| **CHK-13.3** | Secretos & Configuración por Cuenta | Clave maestra perdida o cambiada: leer falla con un error visible y la fila queda intacta | 🟢 Verificado | `test_secretos.py::test_con_otra_clave_maestra_leer_falla_y_la_fila_sigue_igual` |
| **CHK-13.4** | Secretos & Configuración por Cuenta | Clave maestra generada junto a los datos: una sola vez, con aviso, y el archivo solo lo lee su dueño (`0o600`; en Windows, por ACL: CHK-13.32) | 🟢 Verificado | `test_secretos.py::test_el_archivo_de_la_clave_solo_lo_lee_su_dueno` |
| **CHK-13.5** | Secretos & Configuración por Cuenta | Clave maestra mal formada: el arranque falla y no se genera otra ni se pisa la existente | 🟢 Verificado | `test_secretos.py::test_un_archivo_mal_formado_falla_y_queda_como_estaba` |
| **CHK-13.13** | Secretos & Configuración por Cuenta | Inyección en la consulta a Drive por la carpeta raíz: la consulta, sus rutas y su configuración se retiraron en la 048 | 🟢 Verificado | `test_web_api.py::test_las_rutas_de_drive_y_onedrive_ya_no_existen` |
| **CHK-13.25** | Secretos & Configuración por Cuenta | SQL sobre los almacenes de secretos y ajustes sin la cuenta: vive en un solo módulo y pasa el recorrido sin excepciones | 🟢 Verificado | `test_aislamiento_sql.py::test_las_tablas_de_secretos_y_ajustes_se_tocan_solo_con_la_cuenta_y_sin_excepciones` |
| **CHK-13.32** | Secretos & Configuración por Cuenta | Clave maestra generada en Windows con los permisos heredados de su carpeta: la ACL queda con una sola entrada, la de quien corre el proceso | 🟢 Verificado | `test_secretos.py::test_en_windows_el_archivo_de_la_clave_queda_solo_para_quien_corre_el_proceso` |
| **CHK-13.33** | Secretos & Configuración por Cuenta | Autorizaciones y ajustes de Drive y OneDrive guardados: la migración 7 los borra de cada cuenta y conserva el cliente OAuth de Google que usa Google Books | 🟢 Verificado | `test_materiales.py::test_la_migracion_7_crea_materiales_y_borra_drive_y_onedrive_salvo_el_cliente_de_google` |
| **CHK-13.34** | Secretos & Configuración por Cuenta | Comandos de Drive y OneDrive en la CLI (autorizar, desconectar, configurar, buscar): se retiraron en la 048 | 🟢 Verificado | `test_mcp_cli.py::test_los_comandos_de_drive_y_onedrive_ya_no_existen` |
| **CHK-13.37** | Secretos & Configuración por Cuenta | Dependencias de Google Drive (`google-api-python-client`, `google-auth-oauthlib`): se quitaron, sin extra `cloud` en la imagen ni en la verificación | 🟢 Verificado | `test_pdf_text.py::test_pypdf_es_dependencia_base_y_no_queda_el_extra_de_drive` |
| **CHK-13.38** | Secretos & Configuración por Cuenta | Clave maestra junto a los datos en un servidor expuesto: fuera del bucle local, sin `AULENTO_SECRET_KEY` válida el servidor web y el MCP por red no arrancan, nombran la variable sin mostrar ninguna clave y no generan ni leen `clave_maestra.key` | 🟢 Verificado | `test_exposicion.py::test_sin_clave_se_rechaza_nombrando_la_variable_y_sin_crear_el_archivo` |
| **CHK-14.4** | Materiales Subidos | Cuota de 200 MB por cuenta esquivada con subidas simultáneas: se vuelve a comprobar al registrar y el archivo no queda | 🟢 Verificado | `test_materiales.py::test_r2_la_cuota_se_vuelve_a_comprobar_al_registrar_y_el_archivo_no_queda` |
| **CHK-14.5** | Materiales Subidos | Archivo disfrazado (extensión no admitida, un «PDF» que no empieza con `%PDF-`, texto con bytes NUL, PDF sin texto o roto): 415 o 422 sin guardar nada | 🟢 Verificado | `test_materiales.py::test_r3_lo_que_no_es_un_material_legible_se_rechaza_sin_guardar_nada` |
| **CHK-14.6** | Materiales Subidos | Path traversal con el nombre del archivo (`../../x.pdf`): el disco usa un nombre que genera el servidor dentro de `usuarios/<id>/materiales/`; el original solo se muestra (OWASP A01:2021) | 🟢 Verificado | `test_materiales.py::test_r5_el_nombre_que_manda_el_navegador_no_sale_de_la_carpeta_de_materiales` |
| **CHK-14.7** | Materiales Subidos | Una cuenta que ve, busca, lee o borra los materiales de otra: el almacén filtra por dueño | 🟢 Verificado | `test_materiales.py::test_r7_una_cuenta_no_ve_lee_busca_ni_borra_los_materiales_de_otra` |
| **CHK-14.9** | Materiales Subidos | Prompt injection desde el texto de un material que intenta cerrar la etiqueta del documento ante el tutor (OWASP LLM01): queda neutralizado | 🟢 Verificado | `test_mcp_agent.py::test_r9_un_cierre_de_etiqueta_en_el_material_queda_neutralizado` |

---

## Detalle Técnico por Dominio

### 1. Inyección y Sanitización (SQLi & Prompt Injection)
- **SQLite:** Todas las operaciones de base de datos en `src/aulento/db/repository/` utilizan parámetros posicionales (`?`) provistos por `sqlite3`. Nunca se concatenan cadenas SQL con variables del usuario.
- **PostgreSQL / pgvector:** En `src/aulento/db/vector_repository.py`, las inserciones y búsquedas de distancia coseno (`1.0 - (embedding <=> %s::vector)`) emplean parámetros `%s` de `psycopg`, previniendo inyecciones de segundo orden o desbordamiento sintáctico.
- **Prompt Injection (OWASP LLM01):**
  - En `GeminiTutorClient` (voz) y `TutorDeMateriales` (materiales subidos y pgvector), las entradas de fuentes externas o estudiantes son encapsuladas con etiquetas semánticas (`<student_speech>`, `<target_phrase>`, `<documento>`, `<student_query>`).
  - Las etiquetas de cierre maliciosas en el texto del usuario son neutralizadas (reemplazadas por corchetes `[...]`) para evitar que rompan el contenedor de contexto.
  - El `system_instruction` incorpora una directiva explícita de `SECURITY RULE` que obliga al LLM a tratar los textos encapsulados exclusivamente como datos y nunca como instrucciones.

### 2. Aislamiento de Red y Fronteras del Navegador
- **Enlace Local Exclusivo:** El archivo `docker-compose.yml` mapea el puerto de PostgreSQL como `127.0.0.1:5432:5432`, impidiendo que otros dispositivos en la red LAN o Wi-Fi puedan sondear o atacar el contenedor.
- **TrustedHostMiddleware:** FastAPI rechaza cualquier petición cuyo `Host` HTTP no corresponda a `localhost`, `127.0.0.1` o `[::1]`, neutralizando vectores de DNS Rebinding.
- **LocalOriginAuthMiddleware:** Si un sitio web malicioso en otra pestaña del navegador intenta hacer peticiones `fetch()` hacia `http://localhost:8000`, la cabecera `Origin` es evaluada y bloqueada con HTTP 403 Forbidden. Asimismo, cabeceras `Sec-Fetch-Site: cross-site` impiden mutaciones de estado no deseadas.

### 3. Sandbox de Archivos y Sistema Operativo
- **Confinamiento al vault de la cuenta:** toda lectura y escritura de notas pasa por `vault/rutas.py::resolver_en_vault`, que resuelve la ruta y comprueba que quede dentro del vault de la cuenta. Un identificador, un título o una carpeta que sale de él (`..`, ruta absoluta, unidad de Windows, enlace) responde 404, igual que una nota que no existe (sección 11).
- **Apertura de Carpetas Locales Segura:** El endpoint `/api/hub/courses/{id}/open-local` comprueba `os.path.isdir(path)` antes de invocar `os.startfile(path)` o `subprocess.run(["xdg-open", path])`. Esto garantiza que solo puedan abrirse carpetas en el explorador y nunca ejecutarse binarios o scripts (`.exe`, `.bat`, `.cmd`).

### 4. Criptografía, Secretos y Privacidad
- **Comparación en Tiempo Constante:** Los Bearer Tokens se validan utilizando `hmac.compare_digest()`, eliminando diferencias medibles en microsegundos que permitirían a un atacante adivinar el token byte a byte.
- **Sin eco de credenciales:** la API nunca devuelve un secreto cargado. De cada uno informa solo si está cargado y, a lo sumo, cuatro caracteres: los últimos de una clave de IA o del identificador del cliente OAuth (sección 11).
- **Canal de API Keys:** Las llamadas hacia la API de Google Gemini transmiten la clave en la cabecera HTTP `x-goog-api-key`, previniendo que quede almacenada en proxies intermedios o logs de acceso HTTP.

### 5. Resiliencia contra Denegación de Servicio (DoS)
- Se añadieron límites en los esquemas Pydantic (`max_length=2000` en búsquedas vectoriales, `min_length=1, max_length=100` en indexaciones por selección).
- Los IDs de rutas REST emplean `Path(..., ge=1)` para garantizar que no se procesen enteros negativos ni entradas arbitrarias.
- El avance de lectura de libros valida `1 <= pages <= 5000` vía `Query()`.


### 9. Integridad de Datos en las Migraciones
Las decisiones están en el ADR 005.
- La versión del esquema vive en `PRAGMA user_version`; cada migración de `src/aulento/db/migrations.py` corre en su propia transacción.
- Antes de avanzar una base en archivo que ya tiene datos se deja una copia `<archivo>.respaldo-v<versión>-<fecha>` junto a ella.
- Una migración que falla revierte, no avanza la versión y el servidor no arranca.
- La migración 3 reconstruye tres tablas con las claves foráneas apagadas; antes de confirmar corre `PRAGMA foreign_key_check` y, si encuentra una referencia rota, revierte. Las claves vuelven a encenderse siempre, también si la migración falla.

### 10. Aislamiento de Datos por Cuenta
Las decisiones están en el ADR 007; el detalle operativo, en la [guía de base de datos](GUIA_BASE_DE_DATOS_Y_BACKUPS.md) y la [guía MCP](GUIA_MCP.md).
- **Dueño por fila:** las ocho tablas raíz (`plataformas`, `libros_lectura`, `bloques_horarios`, `fsrs_items`, `sesiones_estudio`, `rutas_aprendizaje`, `api_usage_logs`, `mcp_audit_logs`) llevan `user_id`; las dependientes se resuelven hasta su raíz con `JOIN` o `EXISTS`.
- **Repositorios y servicios:** reciben la cuenta al construirse, sin valor por defecto, y `db/cuenta.py::exigir_cuenta` rechaza cualquier cosa que no sea un id entero positivo. El constructor no escribe el filtro: lo lleva cada sentencia.
- **SQL estático:** `tests/test_aislamiento_sql.py` lee el código con `ast`, reconstruye cada sentencia (también las armadas con f-strings, concatenación, `+=` o listas de condiciones) y falla si una nombra una tabla raíz, `knowledge_embeddings`, `secretos_usuario` o `ajustes_usuario` sin compararla con `user_id`. Las excepciones son cinco sentencias exactas, cada una con su motivo: las dos de la migración 3, las dos de la herencia a la primera cuenta y los totales de `db status`. Ninguna alcanza a los almacenes de secretos y ajustes. No ve si el valor comparado es el correcto ni las tablas dependientes leídas sin subir a su raíz: eso lo cubren las baterías de dos cuentas.
- **CLI:** los comandos de datos operan como la cuenta de `--user` o `AULENTO_USER`, o como la única activa. Sin una cuenta determinada terminan con error antes de tocar la base.
- **Servidor MCP:** por red, la cuenta es la del token de cada pedido y la sesión del transporte queda atada a ella; por STDIO, la que se resuelve al arrancar. Sin cuenta fijada ninguna herramienta opera. Cada registro de auditoría y de consumo de IA lleva la cuenta que lo originó.
- **Tokens MCP:** 256 bits por token, uno o varios por cuenta, guardados solo como huella SHA-256 y mostrados una única vez. Un token revocado o de una cuenta desactivada responde 401. El token global de `mcp_auth_token.txt` ya no se acepta.
- **Carpetas del servidor:** `POST /api/hub/courses/{id}/open-local` abre una carpeta en la máquina que hospeda el servidor; responde 403 salvo a un administrador cuyo pedido llega desde esa misma máquina, y el 403 no revela si el curso existe.
- **Almacén de vectores:** cada fragmento de `knowledge_embeddings` lleva `user_id`; indexar, buscar, contar y borrar se limitan a la cuenta. Los fragmentos anteriores quedan sin dueño e invisibles hasta reindexarlos.
- **Datos anteriores a las cuentas:** quedan sin dueño, invisibles para todas las cuentas, y los recibe la primera cuenta que se crea.
- **Siembras:** el arranque no carga datos; sembrar plataformas, plantillas o el mazo es una operación de una cuenta.

**Riesgos abiertos:**
- **Rechazos de autenticación del servidor MCP:** Los rechazos de autenticación del servidor MCP se auditan con tope: como máximo 10 por dirección por minuto (el contador vive en la memoria del proceso y recuerda hasta 1000 direcciones); el 401 se responde siempre. Muchas direcciones distintas todavía pueden hacer crecer `mcp_audit_logs`, a razón de 10 filas por minuto cada una.
- **Reactivar una cuenta reactiva sus tokens MCP:** desactivarla los deja sin efecto pero no los revoca. Ante un token comprometido hay que revocarlo antes de reactivar la cuenta.

### 11. Secretos y Configuración por Cuenta
Las decisiones, los desvíos y los riesgos están en el ADR 008; qué respaldar, en la [guía de base de datos](GUIA_BASE_DE_DATOS_Y_BACKUPS.md).
- **Cifrado en reposo:** claves de IA, el cliente OAuth y la autorización de Google Play Libros se guardan en `secretos_usuario` cifrados con Fernet. El texto cifrado incluye la cuenta y el nombre del secreto: una fila copiada a otra cuenta o a otro nombre no descifra.
- **Clave maestra:** sale de `AULENTO_SECRET_KEY` o, si no está, de `clave_maestra.key` en el directorio de datos, que se genera una vez con un aviso y restringida a quien corre el proceso: permisos `0o600` o, en Windows, una ACL sin entradas heredadas y con ese único usuario (`icacls /inheritance:r /grant:r`, sin shell). Si no se pudo restringir, la clave se genera igual y se avisa. Nunca se genera otra sobre una existente.
- **Secreto ilegible:** con otra clave maestra la operación responde 503 con un mensaje propio y la fila no se borra ni se pisa. Volver a cargar el secreto lo reemplaza.
- **Google Drive y OneDrive:** se retiraron en la 048. Los materiales se suben desde la PC y la migración 7 borra de cada cuenta las autorizaciones y los ajustes que guardaban.
- **Vault por cuenta:** cada cuenta lee y escribe en `usuarios/<id>/vault/`. La descarga en `.zip` no sigue enlaces ni uniones. Solo un administrador puede apuntar su propio vault a una carpeta del servidor, que no puede ser, contener ni estar dentro del directorio de datos ni de la carpeta de la base; se vuelve a validar cada vez que se resuelve. Las respuestas informan lo guardado con su ruta relativa al vault: solo `GET /api/vault/location` muestra una carpeta del servidor, y solo la externa de su dueño.
- **Variables y archivos globales:** el servidor no lee claves, credenciales, conectores, prompts ni notas de los archivos anteriores ni de las variables retiradas. El único módulo que los nombra es la importación, como origen y una vez.

**Riesgos abiertos:**
- **Clave maestra junto a la base:** protege un respaldo de la base sola, no a quien copie todo el directorio de datos. La protección completa llega al definir `AULENTO_SECRET_KEY`, que es obligatoria al escuchar fuera del bucle local (sección 12); en bucle local se sigue generando el archivo.
- **La carpeta `importado-<fecha>/` guarda secretos en claro** hasta que el dueño la borre. Un archivo anterior que no se pudo leer queda en su lugar, también en claro.
- **Permisos de un archivo de clave que el servidor no generó:** uno que ya existía, uno restaurado de un respaldo o una copia conservan los permisos que tengan; el servidor solo restringe el que genera. En Windows la restricción depende de `whoami` e `icacls`: si fallan, queda el aviso.
- **«Desconectar» desde la CLI no cancela un flujo lanzado desde la web:** corren en procesos distintos. Si hay una autorización en curso en el servidor, al terminar la cuenta queda conectada otra vez; desconectar desde la web sí la cancela.
- **Mensajes de error con texto del sistema:** una operación del vault que falla por un error del sistema de archivos puede devolver el texto de ese error. La batería de CHK-13.31 recorre las respuestas correctas, no cada fallo posible.
- **`GET /api/duolingo/profile?username=`** consulta el perfil público de cualquier usuario de Duolingo, no solo el de la cuenta.

### 12. Exposición y despliegue
Las decisiones están en el ADR 013; los pasos, en la guía de despliegue.
- **Clave maestra al exponerse (CHK-13.38):** escuchando en una dirección que no es de bucle local, el servidor web y el MCP por red exigen `AULENTO_SECRET_KEY` válida, sin caer al archivo aunque exista (`test_exposicion.py::test_un_archivo_de_clave_existente_no_reemplaza_a_la_variable`), y ningún mensaje repite la clave (`test_exposicion.py::test_ningun_mensaje_ni_aviso_contiene_la_clave`). Además exigen un certificado, un proxy de confianza o `--insecure-http` explícito (`test_arranque_expuesto.py::test_expuesto_con_clave_y_sin_cifrado_sale_con_1`).

**Riesgos abiertos:**
- **El límite de cuerpo vive en el proxy de `deploy/`:** en el VPS compartido, Aulento corre detrás del Caddy del portafolio, que necesita su propio `request_body`. Sin él, la aplicación igual corta en el tope (CHK-14.1 y CHK-14.2).
- **La imagen no se construye en la suite:** el `Dockerfile`, el `.dockerignore` y los compose se verifican leyéndolos. Que la imagen construida no tenga `.env`, `tests/`, `.venv/` ni bases, y corra sin `root`, se comprueba con `docker build` en la verificación de cierre de la 039.
- **`--insecure-http` sigue disponible** para una red de confianza: avisa, pero no lo impide.
- **Las reglas de exposición viven en la CLI:** `aulento web start` y `mcp serve` exigen la clave y el cifrado, pero un `uvicorn aulento.web.app:app --host 0.0.0.0` lanzado a mano se saltea esa comprobación. La imagen arranca siempre por la CLI. Los proxies de confianza, en cambio, sí se aplican dentro de la aplicación.
- **La imagen se arma con las versiones de `requirements.txt` (`--constraint`)**, pero la dependencia opcional que ese archivo no fija (`postgres`) sale de los rangos de `pyproject.toml`: dos construcciones del mismo commit pueden diferir en ellas.

### 13. Materiales subidos
Las decisiones están en el ADR 015.
- **Nombres del servidor (CHK-14.6):** el archivo se escribe con un nombre aleatorio y la extensión admitida, a un `.parcial` que se renombra al terminar.

---

## Verificación Continua
Los controles CHK-01 a CHK-07.1 se ejecutan con la suite de auditoría:
```bash
pytest tests/test_deep_security_audit.py -v
```
Los controles de aislamiento por cuenta (CHK-12.1 a CHK-12.21), con las baterías de dos cuentas y el recorrido estático del SQL:
```bash
pytest tests/test_aislamiento_sql.py tests/test_aislamiento_repos.py tests/test_vector_postgres.py -v
```
Los controles de secretos y configuración por cuenta (CHK-13.1 a CHK-13.37), con las baterías de la 034:
```bash
pytest tests/test_secretos.py -v
```
Los controles de exposición y despliegue (CHK-13.38 a CHK-13.40), con las baterías de la 039:
```bash
pytest tests/test_exposicion.py tests/test_arranque_expuesto.py -v
```
Los controles de materiales subidos (CHK-14.1 a CHK-14.9), con las baterías de la 048:
```bash
pytest tests/test_materiales.py tests/test_mcp_agent.py -v
```
Todos los 51 controles están formalmente cubiertos y deben permanecer en verde en cada ciclo de integración. `tests/test_security_checklist.py` comprueba que existe cada prueba que este documento nombra, en la matriz o fuera de ella.
