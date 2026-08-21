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

## ⛔ REGLA VINCULANTE — CAJAS SFTP SIEMPRE COMPLETAS Y AUTOCONTENIDAS
## (S61, 2026-08-21, tras incidencia real de fricción repetida)

**Origen real:** en S61, para subir tres archivos a `SWAP` por sftp, el
modelo entregó los `put` sueltos sin la caja de apertura de la conexión
(`sftp usuario@host`), obligando a Miguel Ángel a intervenir con un
prompt adicional solo para preguntar dónde se pegaban. Además, la
omisión de `exit` en entorno `PC` (ver tabla PEE de
`com-bash-commands`/`com-file-request`) dejaba la sesión sftp abierta,
obligando a cerrarla a mano. Ambas cosas, sumadas al incidente ya
documentado más abajo de `gcloud compute scp`, generaron una fricción
real y repetida que Miguel Ángel señaló explícitamente como excesiva.

**Regla, de obligado cumplimiento en este proyecto, PREVALECE sobre la
tabla PEE genérica de `com-bash-commands`/`com-file-request` en cuanto
a `exit`:**

1. **Toda operación sftp se entrega en exactamente DOS cajas, nunca
   una caja sftp "suelta" sin su apertura:**
   - Caja 1 (comando de consola normal, no caja `sftp`): el comando de
     apertura de la conexión, tal cual se pega en PowerShell/cmd --
     `sftp {usuario}@{host}` (ver `SFTP_CONNECTION` arriba para los
     valores reales de este proyecto).
   - Caja 2 (caja `sftp`): todas las operaciones (`get`/`put`/`!rm`/lo
     que corresponda) y, **siempre, en cualquier entorno PEE, incluido
     PC**, un `exit` final. Dejar la sesión sftp abierta genera más
     fricción que un `exit` de sobra -- la tabla PEE que omitía `exit`
     en `PC`/`PCv` queda **sin efecto en este proyecto** a partir de
     S61; se mantiene el uso de barra inicial sí/no según PEE, pero
     `exit` se incluye siempre.
2. Nunca dar una caja de código a medias esperando que Miguel Ángel
   adivine dónde se pega o con qué se completa -- si una operación
   necesita más de un paso (abrir conexión + operar + cerrar), los
   pasos necesarios van TODOS en la misma respuesta, nunca repartidos
   en turnos sucesivos por descuido.

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

⛔ **DIRECTIVA VINCULANTE, SIN EXCEPCIÓN (fijada S54, 2026-08-17, tras
incidente real de galimatías de sincronización)** — flujo único y
obligatorio para CUALQUIER cambio de código del agente H28:

1. Claude clona/actualiza el repo en su propio workspace al empezar
   la sesión (como ya hace siempre, `nfs-enterprisebot-edit`).
2. **Todos** los cambios de código (`.py`, `config.py`, lo que sea)
   se editan **únicamente** en ese clon de Claude -- nunca pidiendo a
   Miguel Ángel que edite, cree o pegue nada directamente en su
   `C:\EnterpriseBot` local.
3. Claude comitea y empuja a GitHub.
4. A Miguel Ángel se le da **únicamente** `git pull` (más, si aplica,
   el procedimiento estándar de recompilación ya documentado más
   abajo) -- nunca un comando que genere o modifique archivos de
   código en su local por otra vía.

**Terminantemente prohibido:** dar a Miguel Ángel comandos que creen,
editen o parcheen archivos directamente en su máquina fuera de
`git pull`. Si algo necesita cambiar en `h28_migration_agent/`, ese
cambio nace en el clon de Claude, se empuja, y llega a Miguel Ángel
solo por `git pull`. Sin excepción, sin atajos, aunque parezca más
rápido en el momento.

**Excepción explícita, la única que existe:** configuración
puramente local de una máquina concreta, que nunca debe vivir en git
porque rompería otras máquinas si se subiera activa. Hoy hay dos
casos reales, ambos deliberados:
- `agent_data\` (clave de servicio, estado persistido) -- ya fuera de
  git por diseño desde S031.
- `TESSERACT_CMD`/`pytesseract.pytesseract.tesseract_cmd` en
  `local_ocr_classify.py` (líneas 96-97) -- comentadas por defecto en
  el repo porque en Linux (la VM `h28-ocr-batch` de S51) Tesseract ya
  está en el `PATH` del sistema y no hacen falta; en el PC Windows de
  Miguel Ángel sí hace falta descomentarlas y apuntarlas a
  `C:\Program Files\Tesseract-OCR\tesseract.exe` (instalación real de
  S50, motivo: sin permisos de administrador para que Tesseract
  escriba en `Program Files`, por eso también existe
  `h28_migration_agent\tessdata\`, carpeta local propia junto al
  script, sin trackear -- ver `_TESSDATA_DIR` en el propio archivo).
  **Esta descommentado local en Windows es intencional y correcto,
  nunca debe commitearse activo** -- si Claude necesita tocar algo
  MÁS de ese archivo, edita alrededor de esas dos líneas sin
  activarlas ni desactivarlas, y si por error `git status` las marca
  como conflicto, se resuelven con `git stash`/`git stash pop`
  exactamente como cualquier configuración local -- nunca hay que
  "arreglarlas" ni preguntarse de quién son.

Cualquier configuración local nueva de este tipo que aparezca en el
futuro debe documentarse aquí mismo, con el mismo detalle, en el
momento en que se descubra -- no dejarla como una sorpresa sin
explicar en un `git status` de una sesión futura.

**Motivo real, verbatim (Miguel Ángel, S54):** *"si tenemos
diferentes formas de hacerlo, pasa lo que está pasando. Que tenemos
copias que no están en GitHub, el GitHub no está sincronizado, ahora
tenemos un archivo corriendo que no sabemos lo que es... Galimatías."*
Incidente real que lo disparó: un `git pull` que Claude dio en el
mismo bloque que la recompilación, sin comprobar que el pull tuviera
éxito -- el pull falló en silencio (había un cambio local sin
commitear, `TESSERACT_CMD` en `local_ocr_classify.py`, que bloqueaba
el merge), y PowerShell siguió ejecutando las líneas siguientes
igualmente, compilando el `.exe` con el código VIEJO sin que apareciera
ningún error visible. Consecuencia: casi una hora de diagnóstico en
círculos (crash fantasma, doble proceso, bloqueo de log...) por una
causa que era, en realidad, muy simple: el pull nunca se había hecho.

**Corolario obligatorio:** cuando Claude dé una secuencia de comandos
donde un paso dependa de que el anterior haya tenido éxito real
(`git pull` antes de compilar, por ejemplo), **cada paso debe
confirmarse explícitamente con la salida real antes de dar el
siguiente** -- nunca encadenar en un mismo bloque un paso que pueda
fallar en silencio con el siguiente que dependa de él.

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

  ⛔ **`gcloud compute scp` EN WINDOWS/PUTTY -- INCIDENCIAS REALES S61,
  SOLUCIÓN FINAL YA VERIFICADA -- leer esto ANTES de proponer nada,
  nunca repetir el tanteo:**

  **Lo que NO funciona en Windows (pscp), confirmado real:**
  - Comodines en la ruta remota (`archivo*.ext`) -- `unable to
    identify RUTA: no such file or directory`.
  - Varios orígenes remotos en un mismo comando, aunque se listen
    explícitos uno a uno -- `Multiple remote sources not supported by
    PuTTY`.
  - Ruta remota con `~` -- falla igual con `unable to identify`,
    incluso con UN solo archivo. `pscp` no expande `~`, hace falta la
    ruta absoluta real (confirmar con `echo "$HOME"` dentro de la VM
    si no se conoce).
  - Ejecutar el comando dentro de la propia sesión SSH de la VM --
    `insufficient authentication scopes` (la cuenta de servicio de la
    VM no tiene alcance de Compute Engine; hace falta la cuenta de
    usuario de Miguel Ángel, desde su PC).

  **SOLUCIÓN REAL, un solo comando, verificada de verdad (S61):**
  agrupar los archivos en una carpeta dentro de la VM y descargar la
  carpeta entera con `--recurse` -- eso sí admite un único origen
  remoto sin problema:
  ```bash
  # Dentro de la VM:
  mkdir -p carpeta_salida && cp archivo1.ext archivo2.ext archivo3.ext carpeta_salida/
  ```
  ```
  # En el PC de Miguel Ángel (PowerShell, ruta absoluta, nunca ~):
  gcloud compute scp --recurse h28-ocr-batch:/home/Usuario/RUTA/carpeta_salida . --project=gen-lang-client-0961484137 --zone=europe-west1-b
  ```
  **Esta es la forma por defecto a partir de ahora para bajar varios
  archivos de esta VM desde Windows -- no volver a proponer comandos
  sueltos por archivo, ni comodines, ni `~`.**

  (El comodín de `sample*_output.txt` de la sección de arriba, S53,
  funcionó porque aquella sesión se hizo desde el Termux del móvil de
  Miguel Ángel -- Linux real, `scp` de OpenSSH -- no desde su PC
  Windows. El entorno real de la consola importa tanto como el PEE del
  proyecto; confirmar ambos antes de dar el comando, no solo el
  segundo.)



### BOOTSTRAP DE UNA VM NUEVA DESDE CERO (registrado S54, tras un
### incidente real -- ver más abajo)

**Incidente que originó esto:** en S54 se crearon 3 VMs nuevas
(`h28-ocr-batch-1/2/3`, mismas specs que `h28-ocr-batch`) y se
montaron con `pip install pymysql sshtunnel pytesseract PyMuPDF
python-docx google-cloud-storage` sueltos, sin `requirements.in`/
`.txt` -- pese a que `com-environment-management` sección 1.1 ya
prohíbe explícitamente esto **incluso para entornos efímeros**. La
sesión siguiente no encontró ningún registro del bootstrap exacto (la
VM que lo usó ya estaba borrada) y tuvo que reconstruirlo adivinando
desde las dependencias del propio código. Corregido retroactivamente:
ahora hay dos pares `requirements.in`/`.txt` reales, versionados en
`h28_migration_agent/`, y el bootstrap los usa en vez de una lista
escrita a mano.

**Para las VMs Linux de OCR/extracción** (`local_ocr_classify.py`,
`extract_training_dataset.py`, `report_ocr_gaps.py`) -- candado:
`h28_migration_agent/requirements-ocr-vm.txt`:

```bash
sudo apt-get update -y && sudo apt-get install -y tesseract-ocr tesseract-ocr-spa python3-venv git tmux
git clone https://x-access-token:TOKEN@github.com/MiguelaeTxio/EnterpriseBot.git
cd EnterpriseBot/h28_migration_agent
python3 -m venv ocr_venv
source ocr_venv/bin/activate
pip install pip-tools
pip-sync requirements-ocr-vm.txt
mkdir -p agent_data
```

Después, la clave de servicio (ver más abajo cómo copiarla) antes de
lanzar cualquier script.

**Para `train_document_classifier.py`** (corre en el PC de Miguel
Ángel, sin túnel ni GCS) -- candado:
`h28_migration_agent/requirements-classifier.txt`:

```bash
python -m venv classifier_venv
classifier_venv\Scripts\activate
pip install pip-tools
pip-sync requirements-classifier.txt
```

⛔ **Regla permanente de aquí en adelante (directriz ampliada de
`com-environment-management`):** ningún entorno Python de este
proyecto, sea VM efímera, PC o servidor, se monta con `pip install`
sueltos sin `requirements.in`/`.txt` versionado. Si aparece una
dependencia nueva que no está en ninguno de los candados existentes,
se añade al `.in` correspondiente, se recompila y se comitea **antes**
de usarla en cualquier máquina -- nunca al revés.


  archivo ni copiarlas fuera de la VM antes de cerrarla.

  **Ruta real final, confirmada con `ls -la` (S54, 2026-08-17):**
  `/home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/sample{0,1,2}_output.txt`
  (202078/159413/154330 bytes, 14 ago 16:24 -- las 185 muestras
  reales de los 77 tipos, S51/S53, todavía sin convertir en
  `CONTENT_MARKERS`). No están en git.

---

## Termux (Android) + gcloud — YA MONTADO Y VERIFICADO (S53, 2026-08-14)

Cuenta autenticada: `nummenor@gmail.com`. Proyecto y zona fijados:
`gen-lang-client-0961484137` / `europe-west1-b`. Verificado con
`gcloud compute instances list` -- funciona.

⛔ **CONFIRMADO S54 (2026-08-17): la app móvil de Google Cloud
Console (SSH desde la propia app, no Termux) conecta a las VMs con
usuario `nummenor` -- distinto del usuario `Usuario` que se usa desde
PowerShell/PC.** Son la misma VM, pero dos carpetas personales
completamente separadas (`/home/nummenor/` vs `/home/Usuario/`) --
si el entorno (`git clone`, `venv`, `agent_data/`) se montó desde PC,
**no existe** para la sesión de la app móvil, hay que montarlo de
nuevo ahí. La clave de servicio no hace falta volver a copiarla desde
cero: se puede duplicar localmente en la propia VM con
`sudo cp /home/Usuario/EnterpriseBot/h28_migration_agent/agent_data/service_account_key.json agent_data/service_account_key.json`
-- el permiso por defecto (`-rw-r--r--`) ya es legible por cualquier
usuario del sistema, no hace falta tocar el propietario ni los
permisos aunque `ls -la` muestre `root` como dueño.

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

---

## Cloud Shell como alternativa a la VM — INVESTIGADO Y DESCARTADO
## para barridos largos (S53, 2026-08-14)

Miguel Ángel preguntó si se podía lanzar el clasificador desde la app
de Google Cloud (Cloud Shell) en vez de crear una VM de Compute
Engine cada vez. Investigado contra la documentación oficial de
Google -- **descartado para este uso concreto, con motivo claro:**

- Cloud Shell está pensada solo para uso interactivo: **las sesiones
  no interactivas se cortan automáticamente a los 40 minutos.** Un
  barrido de horas sin supervisión (como el de hoy, ~5h45) se
  cortaría mucho antes de terminar.
- Sesión máxima 12h, cupo semanal gratis de 50h.
- Lo instalado fuera de `$HOME` (p.ej. Tesseract vía `apt-get`) se
  pierde al reciclarse la máquina de fondo tras esos 40 min de
  inactividad -- solo `$HOME` (5GB) persiste de verdad.
- Máquina de fondo con recursos modestos, más lenta que el
  `e2-standard-8` usado hasta ahora.

**Sí vale la pena para:** comandos `gcloud` puntuales, comprobar
coste, administración rápida con alguien delante -- ya está todo
instalado, sin montar nada. **No vale para:** barridos largos sin
supervisión -- para eso sigue siendo mejor una VM de Compute Engine
real (~$0,30/h, sin límite de tiempo por inactividad).
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

**RESUELTO EN S54 (2026-08-17), fix de raíz:** confirmado con
`git log --follow` que es un bug de origen, no una regresión --
`get_agent_root_dir()` nació el 24 de julio (`47b4550`) ya con esta
lógica, nunca hubo una versión anterior que escribiera bien
`watched_folders.json`. Confirmado también con datos reales de la
propia máquina (`Get-ScheduledTask ... | Actions`) que la Tarea
Programada apunta a
`C:\EnterpriseBot\h28_migration_agent\dist\AgenteMigracionH28.exe`,
con `WorkingDirectory` también en `dist\` -- por eso `agent_data\`
siempre se resolvía ahí, vacío, nunca en la raíz real del checkout.

Miguel Ángel pidió explícitamente una solución de raíz, no un parche
de despliegue: `get_agent_data_dir()` ya **no** depende de dónde esté
el `.exe` en cada momento. Ahora vive de forma fija en
`%LOCALAPPDATA%\EnterpriseBot\H28MigrationAgent\` (estándar de
Windows para datos de aplicación por usuario) -- sobrevive a
recompilaciones, a mover el `.exe`, y a cualquier cambio futuro de
estructura de `dist\`. Incluye migración automática y no destructiva
(nunca borra el origen, nunca sobrescribe el destino) de cualquier
archivo real que pudiera existir en las ubicaciones antiguas
(`dist\agent_data\` o la raíz `h28_migration_agent\agent_data\`),
para no perder nada si algún día hubo estado real ahí.

**NUEVA UBICACIÓN REAL de `agent_data\` desde S54** (clave de
servicio, `watched_folders.json`, `history.json`,
`hydration_notify_state.json`):
`C:\Users\Usuario\AppData\Local\EnterpriseBot\H28MigrationAgent\`

El archivo de log (`h28_migration_agent.log`) **sigue** junto al
`.exe` en ejecución (`dist\`) -- deliberado, no es parte de este fix,
ver docstring de `get_agent_root_dir()` en `config.py`.

**Pendiente real, sin resolver todavía:** confirmar cuál es la
variable de entorno que hace que la clave de servicio siga
autenticando pese a que `dist\agent_data\` estaba vacía
(`get_service_account_key_path()` la resuelve por variable de
entorno con prioridad sobre el archivo) -- y dónde está fijada esa
variable en esta máquina. No bloquea nada mientras siga funcionando,
pero hay que documentarlo antes de que alguien la borre sin saber
para qué era.

---

## CRITERIO REAL: paralelo vs. un solo proceso en la VM (S53,
## 2026-08-14) -- según contexto, NO preguntar, ya está decidido

El coste de la VM es por hora encendida (~$0,30/h), casi
independiente de cuántos procesos corran dentro -- repartir en varios
`tmux` en paralelo no ahorra dinero, solo ahorra tiempo de espera.
Por eso el criterio depende de si Miguel Ángel tiene prisa en ese
momento, no de ahorrar coste:

- **En la oficina (tiene que esperar delante, sin poder hacer otra
  cosa mientras corre):** varios procesos en paralelo, para que acabe
  antes.
- **Fuera de la oficina, con tiempo para hacer otra cosa mientras
  corre:** un solo proceso, sin prisa, aunque tarde más -- menos
  ventanas, menos sitios donde algo puede salir mal.

Preguntar por el contexto (¿tienes prisa ahora o no?) antes de decidir
cuántos procesos lanzar, en vez de asumir paralelo por defecto.

---

## CLONAR EL REPO EN UNA VM/CONSOLA SSH REMOTA -- `git clone` CON
## PROMPT INTERACTIVO DE USUARIO/CONTRASEÑA **FALLA SIEMPRE**, NUNCA
## VOLVER A PROPONERLO (confirmado S59, van ya 4 veces reales)

**QUEDA TERMINANTEMENTE PROHIBIDO** proponer `git clone
https://github.com/...` a secas esperando que Git pida usuario/
contraseña de forma interactiva en una consola SSH remota (VM de GCE,
Termux, cualquier sesión abierta vía `gcloud compute ssh`). Ese prompt
interactivo falla de forma sistemática en este tipo de consola --
confirmado real la 4ª vez en S59.

**Método que SÍ funciona siempre, verificado S59:** capturar el token
en una variable de entorno con `read -s` (oculta lo que se pega, nunca
aparece en pantalla ni en el historial de la propia caja de comando),
y usarlo inline en la URL de clonado, en la MISMA sesión de terminal
(la variable no sobrevive a una consola nueva):

```bash
cd {RUTA_DESTINO} && read -s -p "Pega aqui el token de GitHub (no se vera en pantalla): " GH_TOKEN && echo
```

Miguel Ángel pega el token cuando se le pide (sin salida visible, es
lo esperado). Caja siguiente, mismo terminal:

```bash
git clone https://x-access-token:${GH_TOKEN}@github.com/MiguelaeTxio/EnterpriseBot.git
```

Nunca combinar ambas cajas en un solo bloque -- el `read -s` necesita
su propio turno para que Miguel Ángel pegue el valor antes de que siga
el resto del script.

