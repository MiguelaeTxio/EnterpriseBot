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

## AGENTE H28 — ENTORNO REAL EN EL PC DE MIGUEL ÁNGEL (registrado S51,
## 2026-08-13, tras confirmar los datos tirando de tres sesiones
## anteriores tras un fallo real: se preguntó por esta ruta en vez de
## buscarla, pese a estar ya documentada en el propio historial de
## chats desde S031-S038)

**QUEDA CONFIRMADO Y REGISTRADO** para no volver a preguntarlo nunca:

- **Ruta del checkout local:** `C:\EnterpriseBot` (repo completo, el
  agente vive en `C:\EnterpriseBot\h28_migration_agent`).
- **Entorno virtual:** `h28_agent_venv`, sobre Python 3.14.6, dentro de
  `h28_migration_agent\`. **Nunca se activa con `Activate.ps1`** — la
  política de ejecución de PowerShell de esa máquina lo bloquea sin
  avisar (S035). Se invoca siempre el intérprete directamente:
  `.\h28_agent_venv\Scripts\python.exe -m ...`.
- **Ejecutable:** `AgenteMigracionH28.exe`, compilado con
  `python -m PyInstaller --onefile --windowed --name AgenteMigracionH28
  main.py` desde el intérprete del venv (nunca `pyinstaller` a secas
  invocado fuera de él). Sale en `h28_migration_agent\dist\`.
- **Tarea programada de arranque:** `EnterpriseBot_H28_MigrationAgent`
  (Task Scheduler de Windows). Reiniciar tras reconstruir con
  `Start-ScheduledTask -TaskName "EnterpriseBot_H28_MigrationAgent"`.
- **Antes de recompilar:** cerrar cualquier instancia en marcha del
  `.exe` (`Get-Process AgenteMigracionH28 | Stop-Process -Force`) --
  PyInstaller no puede sobrescribir un `.exe` con el proceso abierto
  (incidente real, S035).
- **Clave de cuenta de servicio y estado local:** dentro de
  `h28_migration_agent\agent_data\` (`service_account_key.json`,
  `history.json`, `watched_folders.json`, `hydration_notify_state.json`
  desde S51) -- carpeta puramente local, nunca commiteada, sin
  cobertura de `.gitignore` explícita pero jamás trackeada en git en la
  práctica (verificado S51: `git ls-files` sin resultados bajo
  `agent_data/`).
- **Dependencias:** `h28_migration_agent/requirements.in`/
  `requirements.txt` propios, independientes del entorno Django del
  servidor (`com-environment-management`, un par de archivos por
  entorno). El candado se compila siempre en esa misma máquina Windows
  con Python 3.14.6 -- nunca válido un candado generado en otra
  plataforma (ruedas `pywin32-ctypes`, `pefile`, `watchdog` win_amd64).
- **Procedimiento estándar de actualización tras un `git push` que
  toque `h28_migration_agent/`:**

```powershell
cd C:\EnterpriseBot
git pull

cd h28_migration_agent
Get-Process AgenteMigracionH28 -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -Recurse -Force .\build -ErrorAction SilentlyContinue
Remove-Item -Force .\AgenteMigracionH28.spec -ErrorAction SilentlyContinue

.\h28_agent_venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name AgenteMigracionH28 main.py

Start-ScheduledTask -TaskName "EnterpriseBot_H28_MigrationAgent"
```

Si el cambio añadió dependencias nuevas, insertar entre el `git pull`
y el `PyInstaller` (ver `com-environment-management`):

```powershell
.\h28_agent_venv\Scripts\python.exe -m piptools compile requirements.in
.\h28_agent_venv\Scripts\python.exe -m piptools sync requirements.txt
.\h28_agent_venv\Scripts\python.exe -m pip check
```

---

**QUEDA TERMINANTEMENTE PROHIBIDO usar estas dos rutas para EnterpriseBot** —
pertenecen a otro proyecto de la cuenta (Campus Studio Online), no a
esta plataforma. Anotadas aquí únicamente para que nunca se confundan:

- `/var/log/alwayson-log-182748.log` — Campus Studio Online, NO EnterpriseBot.
- `/var/log/alwayson-log-209547.log` — Campus Studio Online, NO EnterpriseBot.

---

## VM h28-ocr-batch — ENTORNO REAL (registrado S53, 2026-08-14, tras
## descubrirlo a tientas paso a paso -- no volver a redescubrirlo)

**Conexión (PowerShell, comando suelto, ver `com-gcloud-windows`):**
```
gcloud compute ssh h28-ocr-batch --project=gen-lang-client-0961484137 --zone=europe-west1-b
```
(sin `--command`, para sesión interactiva -- necesaria porque los
scripts de este directorio piden contraseñas por teclado, `getpass`,
no aceptan flags ni variables de entorno).

- **Checkout real:** `~/EnterpriseBot/h28_migration_agent` (usuario
  `Usuario`, mismo nombre que en el PC Windows -- ojo, no es
  `MiguelAeTxio` ni ningún otro).
- **Python:** el binario se llama `python3` en esta VM, **no**
  `python` (Ubuntu 24.04 no tiene el alias `python-is-python3`
  instalado). Usar siempre `python3 nombre_script.py`.
- **Entorno virtual:** `ocr_venv/`, dentro del propio directorio del
  checkout. **Obligatorio activarlo antes de correr cualquier script
  de esta carpeta** (`local_ocr_classify.py`, `sample_type_patterns.py`,
  `report_ocr_gaps.py` -- todos dependen de `pymysql`/`sshtunnel`, que
  solo están instalados dentro del venv, no en el Python del sistema):
  ```
  source ocr_venv/bin/activate
  ```
  El prompt cambia a `(ocr_venv) Usuario@h28-ocr-batch:...$` cuando
  está activo. Sin este paso, `ModuleNotFoundError: No module named
  'pymysql'` (error real visto en S53).
- **tmux:** cada script de barrido/muestreo largo se lanza dentro de
  una sesión `tmux` propia (`tmux new -s NOMBRE`). Listar sesiones
  vivas: `tmux ls`. Matar una sesión terminada: `tmux kill-session -t
  NOMBRE`.
  ⛔ **`Ctrl+B` seguido de `D` para desconectar (detach) SIN matar el
  proceso NO FUNCIONA en la consola de Miguel Ángel** (PowerShell →
  `gcloud compute ssh`) -- confirmado real dos veces (sesión anterior
  y S53). **Nunca volver a proponerlo.** Para tener varios procesos en
  paralelo, la vía que sí funciona es abrir una ventana de PowerShell
  nueva por cada proceso y conectar con `gcloud compute ssh` otra vez
  desde ahí (cada ventana de PowerShell es una sesión SSH
  independiente) -- dentro de esa sesión nueva, `tmux attach -t
  NOMBRE` si hace falta reconectar a una ya creada, o `tmux new -s
  NOMBRE` para una nueva.
- **Coste real confirmado (S53):** `e2-standard-8` en `europe-west1-b`,
  sin descuento por uso sostenido (la familia E2 no lo tiene). Sesión
  de ~5h45 de uso real costó en torno a $1,70-1,85 -- los datos de
  Billing tardan hasta 24h en aparecer en la consola, así que para
  saber el gasto real en caliente hay que calcularlo a mano:
  `gcloud compute instances describe h28-ocr-batch --project=gen-lang-client-0961484137 --zone=europe-west1-b --format="value(creationTimestamp)"`
  da la hora de creación real, y de ahí horas transcurridas × ~$0,30/h.
- **Borrado cuando ya no haga falta:**
  ```
  gcloud compute instances delete h28-ocr-batch --project=gen-lang-client-0961484137 --zone=europe-west1-b --quiet
  ```
  ⛔ **ANTES de borrar, copiar siempre `~/EnterpriseBot/h28_migration_agent/sample*_output.txt`
  (o cualquier archivo de resultado real generado en la sesión) a
  local -- el disco se borra con la instancia.**
  ```
  gcloud compute scp h28-ocr-batch:~/EnterpriseBot/h28_migration_agent/sample*_output.txt . --project=gen-lang-client-0961484137 --zone=europe-west1-b
  ```
  Origen: ya se perdieron una vez 185 muestras reales (S51) por
  quedar solo en la terminal de una sesión previa sin guardarlas en
  archivo ni copiarlas fuera de la VM antes de cerrarla.

---

## Termux (Android) + gcloud — YA MONTADO Y VERIFICADO (S53, 2026-08-14)

Cuenta autenticada: `nummenor@gmail.com`. Proyecto y zona fijados:
`gen-lang-client-0961484137` / `europe-west1-b`. Verificado con
`gcloud compute instances list` -- funciona.

**Si hay que rehacerlo en un Termux nuevo, el instalador oficial
(`curl https://sdk.cloud.google.com | bash`) falla al final con
`ERROR: (gcloud.components.update) The following components are
unknown [gcloud, gcloud-crc32c]`** -- es un fallo conocido y
documentado en varias fuentes independientes, no es un problema real:
el SDK ya quedó instalado en `$PREFIX/google-cloud-sdk/`, solo falta
terminar de configurarlo. Solución, en orden:
```bash
pkg update -y && pkg upgrade -y
curl https://sdk.cloud.google.com | bash
# ignorar el ERROR de components.update, es esperado
$PREFIX/google-cloud-sdk/install.sh --override-components
# responder Y a "Modify profile to update your $PATH..."
exec bash
gcloud version
gcloud auth login --no-launch-browser
# abrir la URL en el navegador del telefono, pegar el codigo de vuelta
gcloud config set project gen-lang-client-0961484137
gcloud config set compute/zone europe-west1-b
```
## (registrado S53, 2026-08-14) — retomar el lunes

**Síntoma real reportado por Miguel Ángel:** copia un archivo nuevo a
una carpeta vigilada (`DOC. MAQUINAS`) y no sube nunca a cuarentena,
pese a que el agente está corriendo (proceso único, limpio, `10584`
arrancado 14:08:14 13:01:12).

**Causa raíz confirmada con datos reales, no adivinada:**
`get_agent_root_dir()` (`config.py`) usa
`os.path.dirname(os.path.abspath(sys.argv[0]))` -- para el `.exe`
empaquetado con PyInstaller, eso es la carpeta `dist\`, **no**
`C:\EnterpriseBot\h28_migration_agent\`. Mismo patrón exacto que ya
causó el problema del log (ver más arriba). Consecuencia real,
verificada:

- `dist\agent_data\watched_folders.json` **no existe** -- de hecho
  `dist\agent_data\` está **completamente vacía**.
- `_resume_watched_folders()` (`main.py` línea 583-585) hace
  `if not persisted_folders: return` -- en silencio, sin aviso, sin
  notificación de bandeja. El agente arranca vigilando CERO carpetas
  y no hay ningún síntoma visible de que esto está pasando.
- Las subidas reales que sí funcionaron esta mañana (06:44-07:22,
  `DOC. PERSONAL`/`DOC. MAQUINAS`) fueron con carpetas vigiladas **en
  memoria** de esa ejecución concreta (seleccionadas a mano en algún
  punto anterior) -- nunca llegaron a persistirse en el sitio correcto,
  así que se perdieron en el reinicio limpio de las 13:01.
- La clave de servicio sí sigue autenticando pese a que
  `dist\agent_data\` está vacía -- indica que `get_service_account_key_path()`
  la está resolviendo por la variable de entorno (tiene prioridad
  sobre el archivo, ver `config.py`), no por el archivo. **Sin
  confirmar todavía cuál es esa variable ni dónde está fijada** --
  pendiente de mirar el lunes, no bloquea nada mientras siga
  funcionando.

**Pendiente de decidir el lunes, no resuelto todavía:** cómo corregir
`get_agent_root_dir()` para que separe correctamente "carpeta del
ejecutable" (`dist\`, válida para el log y estado real) de cualquier
otra referencia -- y, más importante, **por qué la carpeta empaquetada
nunca ha tenido `watched_folders.json`**: si es la primera vez que se
empaqueta así, o si hubo una versión anterior que sí escribía bien y
se rompió en algún commit. Antes de arreglar nada, revisar con `git
log` los cambios reales de `config.py`/`state.py`/`main.py` entre
la versión que sí funcionaba (si la hubo) y la actual -- directriz
4.8/4.9, verificar antes de proponer diseño.
