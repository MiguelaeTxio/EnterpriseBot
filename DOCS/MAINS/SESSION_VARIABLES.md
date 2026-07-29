# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/SESSION_VARIABLES.md
# VARIABLES DE SESIÓN DE PROYECTO: EnterpriseBot
# Este archivo centraliza la configuración para la sesión actual.

---

## ENTERPRISEBOT

- **PROJECT_ID**: EnterpriseBot
- **GEN_SERVER_ROOT**: /home/MiguelAeTxio/
- **APP_SERVER_ROOT**: PROJECTS/EnterpriseBot/
- **SERVER_ROOT**: {GEN_SERVER_ROOT}{APP_SERVER_ROOT}
- **LOCAL_SWAP**: SWAP/
- **LOCAL_VENV**: "N/A - Remote Server Development"
- **SERVER_VENV**: EnterpriseBot_venv
- **SFTP_CONNECTION**: MiguelAeTxio@ssh.pythonanywhere.com:PROJECTS/EnterpriseBot
- **DB_NAME**: MiguelAeTxio$enterprisebot
- **PROJECT_MASTER_DOC_PATH**: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_MASTER_DOCUMENT.md
- **PROJECT_DIRECTORY_PATH**: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/ENTERPRISEBOT_PROJECT_DIRECTORY.txt
- **PROJECT_ATTACHMENTS_PATH**: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/
- **PROJECT_SESSION_DATA_PATH**: {SERVER_ROOT}DOCS/SESSION/
- **PROJECT_GEMINI_HISTORY**: {PROJECT_SESSION_DATA_PATH}GEMINI_SESSIONS_HISTORY.md
- **PROJECT_TEMP_HISTORY**: {PROJECT_SESSION_DATA_PATH}TEMP_SESSIONS_HISTORY.md
- **PROJECT_COMPLETED_SESSIONS_DIR**: {PROJECT_SESSION_DATA_PATH}COMPLETED/

---

## LOGS — ARCHIVOS NO VERSIONADOS DEL SERVIDOR

**No viven en GitHub.** Son artefactos de ejecución en el servidor
(procesos always-on y logs web estándar de PythonAnywhere). Para
solicitarlos usar `com-file-request` citando la línea exacta de esta
tabla — nunca `doc-project-directory-enterprisebot` (manifiesto de
árbol de código fuente, no cubre `/var/log/` ni rutas fuera del
proyecto).

**Mecanismo de descarga: sftp GET con ruta absoluta.** Verificado que
PythonAnywhere sí permite sftp sobre `/var/log/` (no solo sobre
`/home/MiguelAeTxio/`) — confirmado por Miguel Ángel y por evidencia
pública (usuarios de PythonAnywhere descargando access logs desde
`/var/log/` vía SFTP/paramiko). La caja sftp usa la ruta absoluta tal
cual, sin prefijo de proyecto — ver `com-file-request`.

**Nota de reparación (2026-07-06):** esta tabla estaba anotada como
"actualizada" en el registro de S057 (anexo H17) pero no existía en
este archivo — reparado en esta sesión tras detectar la discrepancia
empíricamente. Confirmado con Miguel Ángel el mismo día: de las
cuatro URLs de tareas always-on de su cuenta, solo dos pertenecen a
EnterpriseBot — ver tabla.

| Variable | Ruta | Tarea / Log |
|---|---|---|
| `LOG_VOICE_ORCHESTRATOR` | `/var/log/alwayson-log-234987.log` | EnterpriseBot — Bridge de Voz Conversacional (Twilio + gemini-live-2.5-flash-native-audio) |
| `LOG_CELERY_WORKER` | `/var/log/alwayson-log-242133.log` | EnterpriseBot — Worker Celery, procesamiento de partes de trabajo PDF |
| `LOG_BRIDGE` | `{SERVER_ROOT}logs/bridge.log` | EnterpriseBot — bridge.log permanente (movido de SWAP en S057), sí versionable por sftp normal (está dentro del proyecto, no en `/var/log/`) |
| `LOG_WEB_ACCESS` | `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.access.log` | EnterpriseBot — access log estándar de la web app (confirmado por captura del dashboard, 2026-07-06) |
| `LOG_WEB_ERROR` | `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.error.log` | EnterpriseBot — error log estándar de la web app (ídem) |
| `LOG_WEB_SERVER` | `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.server.log` | EnterpriseBot — server log estándar de la web app (ídem) |

---

## GCLOUD — ENTORNO REAL EN EL PC DE MIGUEL ÁNGEL (verificado S038, 2026-07-29)

**QUEDA CONFIRMADO Y REGISTRADO** tras dos incidencias reales de sintaxis
equivocada en la misma sesión: cuando la directriz 4.10 del documento
maestro pide "comandos `gcloud`/`gcloud storage` listos para pegar en
Cloud Shell", el destino real **no es el Cloud Shell del navegador** —
es el **SDK de Google Cloud instalado en local sobre Windows**, usado
desde una ventana de **`cmd.exe`** (Windows Command Processor) anclada a
la barra de tareas desde la instalación del SDK.

**Consecuencias de obligado cumplimiento a partir de ahora:**

1. **Nunca entregar sintaxis bash** (`$VAR`, `for ... do ... done` con
   continuación de línea `\`, heredoc `<< EOF`) para comandos `gcloud`
   de este proyecto — falla con errores confusos de `cmd.exe` ("no se
   reconoce como un comando interno o externo") y en versiones antiguas
   del SDK, con errores de PowerShell mezclados
   (`gcloud.ps1`/política de ejecución deshabilitada) si el lanzador cae
   por debajo a PowerShell.
2. **Sintaxis correcta:** batch de Windows (`set VAR=...`,
   `for %%X in (...) do (...)` con `%%` doblado — dentro de un archivo
   `.bat`, nunca en la línea de comandos interactiva, donde sería `%X`
   simple).
3. **Para cualquier comando con bucle o multilínea:** entregar como
   contenido de un archivo `.bat` a crear vía `notepad archivo.bat` (el
   pegado en el Bloc de notas es fiable; pegar bucles multilínea
   directamente en `cmd.exe` no lo es), guardar y ejecutar
   `archivo.bat`.
4. **El directorio de arranque por defecto de esa ventana es
   `C:\Windows\SysWOW64`** — carpeta protegida del sistema, deniega
   escritura de archivos nuevos sin elevación. **Siempre `cd /d
   %USERPROFILE%\Desktop`** (o directorio de trabajo equivalente) antes
   de crear cualquier archivo `.bat` o de salida.
5. `gcloud --version` verificado en S038: SDK `577.0.0`, `core
   2026.07.17` — el SDK en sí funciona con normalidad; los fallos
   previos eran de sintaxis/entorno, no de instalación rota.
6. **`gcloud storage buckets get-iam-policy` NO admite `--filter`**
   (verificado en línea en S038 contra la referencia oficial actual:
   solo admite las GCLOUD WIDE FLAGS — `--flatten`, `--format`, etc. —
   a diferencia de `gcloud projects get-iam-policy`, que sí soporta
   `--filter` por ser comando de tipo lista). Para acotar la salida a
   un principal concreto: `--flatten="bindings[].members"` +
   `--format="table(bindings.role,bindings.members)"` y filtrar con
   `findstr` (Windows) o `grep` (bash) sobre la salida ya obtenida,
   nunca con `--filter` en este comando.

**Origen:** dos incidencias seguidas en S038 (bucle bash pegado en
`cmd.exe`, y antes de eso una captura histórica con error de política de
ejecución de PowerShell) antes de que Miguel Ángel aclarara
explícitamente que la ventana usada desde el principio es la del propio
`cmd.exe` local, nunca el Cloud Shell del navegador.

---

**QUEDA TERMINANTEMENTE PROHIBIDO usar estas dos rutas para EnterpriseBot** —
pertenecen a otro proyecto de la cuenta (Campus Studio Online), no a
esta plataforma. Anotadas aquí únicamente para que nunca se confundan:

- `/var/log/alwayson-log-182748.log` — Campus Studio Online, NO EnterpriseBot.
- `/var/log/alwayson-log-209547.log` — Campus Studio Online, NO EnterpriseBot.
