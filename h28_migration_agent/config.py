# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/config.py
"""Configuration constants for the H28 migration agent.
---
Constantes de configuracion del agente de migracion H28."""

import logging
import os
import shutil
import sys

logger = logging.getLogger(__name__)

# Cubo unico de GCS. Confirmado por Miguel Angel en S031; la
# cuarentena dejo de ser un cubo aparte en S036.
# ---
# Single GCS bucket. Confirmed by Miguel Angel in S031; quarantine
# stopped being a separate bucket in S036.
DIRTY_BUCKET_NAME = "cgs_grupo_alvarez"

# Prefijo de cuarentena DENTRO del cubo sucio (decision 1 de S036,
# sustituye al cubo dedicado `cgs_grupo_alvarez_cuarentena` de S031).
#
# Motivo: verificado en linea en S035 que renombrar y mover DENTRO de
# un cubo con Namespace Jerarquico es una operacion solo de
# metadatos, atomica y sin coste de copia. Cruzar frontera de cubo no
# lo es -- es copia real mas borrado, con coste por cada archivo
# clasificado. Con la cuarentena dentro, todo el movimiento de la
# Fase 2 es gratis. Ademas, la documentacion oficial exige
# `storage.folders.rename` en el cubo ORIGEN y
# `storage.folders.create` en el DESTINO: con un solo cubo basta un
# binding, y `enterprisebot-vertex@` ya lo tiene sobre este
# (verificado en S036 con `get-iam-policy`).
#
# **Debe vivir en la RAIZ del cubo**, como hermano de las carpetas
# migradas, nunca dentro de ninguna de ellas: el reconciliador lista
# el arbol espejo con `prefix=f"{carpeta}/"`, y si la cuarentena
# colgara de una carpeta migrada sus blobs entrarian en ese mismo
# listado y contaminarian la comparacion local-contra-cubo.
#
# El guion bajo inicial hace la colision imposible: las carpetas
# reales de OneDrive son `DOC. MAQUINAS`, `DOC. PERSONAL`,
# `LAVADO NAVARRO`... ninguna empieza por `_`. En castellano y sin
# tildes por el mismo criterio que fijo Miguel Angel en S035 para los
# nombres de archivo: son datos visibles por personas, no
# identificadores de codigo, asi que la Regla de Oro del Idioma no
# aplica, y el ASCII evita problemas de codificacion entre Windows y
# GCS.
# ---
# Quarantine prefix INSIDE the dirty bucket (S036 decision 1). Moving
# within an HNS bucket is a metadata-only, atomic, free operation;
# crossing a bucket boundary is a real copy plus delete. It MUST live
# at the bucket root, never inside a migrated folder, or its blobs
# would pollute the reconciler's prefix listing.
QUARANTINE_PREFIX = "_CUARENTENA/"

# Real (truncated) service account email — see H28 annex, S031
# incident. GCP truncated the proposed 34-character name to 30.
# ---
# Email real (truncado) de la cuenta de servicio — ver anexo H28,
# incidencia S031. GCP trunco a 30 caracteres el nombre propuesto
# de 34.
SERVICE_ACCOUNT_EMAIL = (
    "enterprisebot-h28-migration-ag"
    "@gen-lang-client-0961484137.iam.gserviceaccount.com"
)

# Environment variable that, if set, overrides the default key
# location below. Kept for flexibility (e.g. a key stored
# elsewhere), but no longer required for normal use.
# ---
# Variable de entorno que, si esta fijada, sobreescribe la ubicacion
# por defecto de la clave de abajo. Se mantiene por flexibilidad
# (ej. una clave guardada en otro sitio), pero ya no es obligatoria
# para el uso normal.
SERVICE_ACCOUNT_KEY_ENV_VAR = "H28_AGENT_KEY_PATH"

# Name of the local, never-committed folder that holds both the
# service account key and the watched-folders state file — always
# right next to the agent, never scattered in an unrelated download
# folder (S031, incidencia de la carpeta "sdcard").
# ---
# Nombre de la carpeta local, nunca commiteada, que guarda tanto la
# clave de la cuenta de servicio como el archivo de estado de
# carpetas vigiladas — siempre junto al agente, nunca perdida en una
# carpeta de descargas ajena (S031, incidencia de la carpeta
# "sdcard").
AGENT_DATA_FOLDER_NAME = "agent_data"
SERVICE_ACCOUNT_KEY_FILE_NAME = "service_account_key.json"
WATCHED_FOLDERS_STATE_FILE_NAME = "watched_folders.json"

# Aviso instantaneo al servidor tras cada subida a cuarentena (H29,
# S040 -- decision explicita de Miguel Angel): "cuando el agente sube
# el archivo a cuarentena, inmediatamente se de una senal (...) para
# que esa subida quede registrada en base de datos (...) deberia ser
# instantanea." No sustituye ni contradice la decision 4 de S030
# (subida directa a GCS, nunca a traves del servidor) -- el archivo en
# si sigue subiendo directo a GCS con la libreria de Cloud Storage,
# esto es solo un aviso aparte, sin contenido, de que ya termino.
#
# Mismo patron que la clave de cuenta de servicio: variable de entorno
# tiene prioridad, si no hay, se lee un archivo dentro de agent_data/.
# ---
# Instant notification to the server after every quarantine upload
# (H29, S040 -- Miguel Angel's explicit decision): "when the agent
# uploads the file to quarantine, immediately a signal should fire
# (...) so that upload is registered in the database (...) it should
# be instant." Does not replace or contradict S030 decision 4 (direct
# upload to GCS, never through the server) -- the file itself still
# uploads straight to GCS with the Cloud Storage library; this is a
# separate, contentless notification that it finished.
#
# Same pattern as the service account key: environment variable takes
# priority, otherwise a file inside agent_data/ is read.
SERVER_BASE_URL = "https://enterprisebot-miguelaetxio.pythonanywhere.com"
SERVER_API_TOKEN_ENV_VAR = "H28_AGENT_API_TOKEN"
SERVER_API_TOKEN_FILE_NAME = "server_api_token.txt"
SERVER_NOTIFY_TIMEOUT_SECONDS = 15

# Visor de historial (S033, decision de Miguel Angel: "el propio
# agente" da el visor de tareas, no la plataforma web -- agente y
# plataforma quedan separados). Guarda los ultimos eventos (copias y
# reconciliaciones) para poder verlos desde una ventana del agente,
# sin tirar de logs.
# ---
# History viewer (S033, Miguel Angel's decision: "the agent itself"
# provides the task viewer, not the web platform -- agent and
# platform stay separate). Stores the latest events (copies and
# reconciliations) so they can be seen from an agent window, without
# digging through logs.
HISTORY_STATE_FILE_NAME = "history.json"
HISTORY_MAX_EVENTS = 200

# S51, Miguel Angel: "Vamos a quitar de en medio estas notificaciones
# cada minuto, porque es que se vuelve uno loco." -- un archivo
# solo-en-nube que nunca termina de hidratar (carpeta duplicada con
# marcadores sincronizados desde otro puesto, S035) generaba un aviso
# nuevo en CADA barrido (cada minuto) para siempre, sin limite. Se
# guarda cuando se avisó por ultima vez de cada ruta pendiente, para
# no repetir el aviso hasta que pase este umbral -- la peticion de
# hidratacion en si (`request_hydration`) NO cambia, se sigue pidiendo
# en cada barrido igual que antes, solo se calla el aviso repetido.
# ---
# S51, Miguel Angel: "Let's get rid of these notifications every
# minute, it's driving me crazy." A cloud-only file that never
# finishes hydrating (duplicate folder with placeholders synced from
# another workstation, S035) produced a new notification on EVERY
# sweep (every minute) forever, with no limit. Stores when each
# pending path was last notified, so the notification does not repeat
# until this threshold passes -- the hydration request itself
# (`request_hydration`) is unchanged, still requested every sweep,
# only the repeated notification is silenced.
HYDRATION_NOTIFY_STATE_FILE_NAME = "hydration_notify_state.json"
HYDRATION_NOTIFY_INTERVAL_MINUTES = 30

# Number of parallel upload workers used for the initial bulk copy.
# ---
# Numero de workers paralelos para la copia inicial en bruto.
UPLOAD_MAX_WORKERS = 8

# Reconciliation retries after the initial copy (S033, Miguel Angel's
# decision): local vs. bucket is compared, and any missing/mismatched
# file is retried this many times, waiting RECONCILE_RETRY_DELAYS[i]
# seconds before retry i. Whatever still fails after all retries is
# logged as unrecoverable.
# ---
# Reintentos de reconciliacion tras la copia inicial (S033, decision
# de Miguel Angel): se compara local contra el cubo, y cualquier
# archivo ausente o con tamano distinto se reintenta este numero de
# veces, esperando RECONCILE_RETRY_DELAYS[i] segundos antes del
# reintento i. Lo que siga fallando tras todos los reintentos se
# registra como irrecuperable.
RECONCILE_MAX_RETRIES = 3
RECONCILE_RETRY_DELAYS_SECONDS = (5, 15, 45)

# Cada cuantos archivos informa de progreso la FASE DE COMPARACION de
# la reconciliacion (la del hash, no la de reparacion). Medido en
# produccion en S035: 11,5 minutos por carpeta, con `DOC. MAQUINAS` y
# `DOC. PERSONAL` sumando 23 minutos en cada arranque de sesion de
# Windows. Hasta ahora esa fase no emitia ni una sola linea entre
# "listando cubo de cuarentena" y el recuento final, y durante la
# sesion hubo que recurrir al `ReadTransferCount` del proceso para
# saber si seguia viva. Mismo criterio que
# AUDIT_PROGRESS_EVERY_FILES.
# ---
# How often the reconciliation's COMPARISON phase (the hashing one,
# not the repair one) reports progress. Measured in production in
# S035: 11.5 minutes per folder, 23 minutes total on every Windows
# logon. Until now that phase emitted no log line at all, and the
# process's `ReadTransferCount` had to be inspected to tell whether it
# was still alive.
RECONCILE_PROGRESS_EVERY_FILES = 500

# Auditoria local de la Fase 2 (S034, decision de Miguel Angel: "lo
# integramos en el agente"). Solo lectura sobre la copia local: es el
# paso 1 de la secuencia de la seccion 8 del anexo H28, el dataset
# con el que se calibran las reglas de limpieza con datos reales
# delante en vez de a ciegas.
# ---
# Phase 2 local audit (S034, Miguel Angel's decision to integrate it
# into the agent). Read-only over the local copy: step 1 of the
# sequence in section 8 of the H28 annex, the dataset used to
# calibrate the cleanup rules against real data instead of blindly.
AUDIT_FOLDER_NAME = "audits"

# Modo "puesta al dia" (S036, punto 2 de la hoja de ruta de S035).
#
# Barrido PERIODICO, no por evento: watchdog no reacciono a la
# llegada sincronizada de los 22 archivos de LAVADO NAVARRO, que
# entraron a las 11:01:30 y no se detectaron hasta la auditoria
# (anexo H28, S035). Un vigilante de eventos no basta cuando el
# origen del cambio es la sincronizacion de OneDrive desde otro
# puesto.
#
# 30 segundos. La cadencia inicial fue de 30 minutos, Miguel Angel la
# rechazo el 29-07-2026 ("cada 30 segundos o un minuto como mucho") y
# se puso en 60 a la espera de medir. Medido ya sobre el arbol de
# produccion -- 4,7 s para 16.039 archivos de `DOC. MAQUINAS` y 6,5 s
# para 21.511 de `DOC. PERSONAL`, 11,2 s el ciclo completo -- se baja
# a 30 por instruccion suya. A 30 s el periodo real ronda los 41 s y
# el barrido ocupa el disco un 27% del tiempo, solo leyendo
# metadatos.
#
# Matiz sobre la medida: 11,2 s es en CALIENTE, con el agente llevando
# horas barriendo cada minuto y los metadatos del directorio en cache.
# Un barrido en frio, justo tras arrancar el equipo, sera mas lento.
# Por eso el bucle vigila su propia duracion y avisa si un ciclo
# excede el intervalo.
#
# Motivo de Miguel Angel, registrado tal cual: un minuto de espera
# entre soltar un archivo y verlo disponible en la cuarentena "puede
# ser desesperante", mas aun si se anade la posibilidad de
# clasificarlo a mano antes de disparar la llamada a Gemini.
#
# Precision tecnica que conviene no perder: para un archivo que se
# suelta LOCALMENTE en la carpeta, el vigilante reacciona al evento y
# lo sube en el acto -- la cadencia no interviene. Los 30 segundos
# gobiernan el caso que de verdad fallo: archivos que llegan por
# sincronizacion de OneDrive desde otro puesto, que no generan evento
# alguno (los 22 de LAVADO NAVARRO, S035).
#
# La cadencia del consumidor de la cuarentena es INDEPENDIENTE de
# esta: aquella corre en una tarea always-on de PythonAnywhere y
# tiene su propio ritmo, gobernado por CELERY_BEAT_SCHEDULE.
# ---
# 30 seconds, measured against the production tree: 11.2 s for a full
# cycle over both folders. Note the measurement is WARM; a cold sweep
# right after boot will be slower, which is why the loop watches its
# own duration.
#
# Technical precision worth keeping: for a file dropped LOCALLY the
# watcher reacts to the filesystem event and uploads at once -- the
# cadence plays no part. The 30 seconds govern the case that actually
# failed: files arriving by OneDrive sync from another workstation,
# which raise no event at all.
CATCHUP_INTERVAL_SECONDS = 30
CATCHUP_INDEX_FOLDER_NAME = "catchup_index"

# Cada cuantos barridos sin novedades se emite un latido en el log.
# A cadencia de 30 segundos, registrar "sin novedades" en cada pasada
# serian mas de 2.000 lineas al dia de ruido puro que acabarian
# haciendo el log inservible. Las pasadas mudas van a DEBUG y cada N
# se emite un resumen en INFO, que es lo que prueba que el hilo sigue
# vivo. Con 40 barridos y un periodo real de ~41 s, el latido sale
# cada ~27 minutos.
# ---
# How many uneventful sweeps between log heartbeats. At a 30-second
# cadence, logging "nothing new" every pass would be over 2,000 lines
# of pure noise per day. Silent passes go to DEBUG and every N a
# summary is emitted at INFO, which is what proves the thread is
# alive.
CATCHUP_HEARTBEAT_EVERY_SWEEPS = 40

# Chunk size used when hashing a file. 1 MiB balances syscall
# overhead against memory for the several-hundred-MB scanned manuals
# present in the real tree.
# ---
# Tamano de trozo al calcular el hash. 1 MiB equilibra el coste de
# syscalls contra la memoria, dados los manuales escaneados de
# varios cientos de MB que hay en el arbol real.
HASH_CHUNK_SIZE_BYTES = 1024 * 1024

# How often the audit reports progress to the log/tray. The audit
# runs over ~37.500 files, so silence for minutes would look like a
# hang -- same lesson as the gcloud commands of S033.
# ---
# Cada cuantos archivos informa de progreso la auditoria. Recorre
# ~37.500 archivos, asi que varios minutos en silencio pareceria un
# cuelgue -- misma leccion que los comandos gcloud de S033.
AUDIT_PROGRESS_EVERY_FILES = 500

# Local log file, written next to the executable.
# ---
# Archivo de log local, escrito junto al ejecutable.
LOG_FILE_NAME = "h28_migration_agent.log"


def get_agent_root_dir():
    """Return the directory the agent (script or .exe) runs from.
    Only meaningful for things that SHOULD stay tied to the running
    binary (currently just the log file, via LOG_FILE_NAME in
    main.py) -- never use this for persistent state, see
    get_agent_data_dir() below.
    ---
    Devuelve el directorio desde el que corre el agente (script o
    .exe). Solo tiene sentido para lo que SI debe depender del
    binario en ejecucion (hoy, solo el archivo de log, via
    LOG_FILE_NAME en main.py) -- nunca usar esto para estado
    persistente, ver get_agent_data_dir() mas abajo.
    """
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def _legacy_agent_data_candidates():
    """Yield legacy agent_data folder locations that existed before
    the S54 fix, for one-time best-effort migration into the new
    fixed location. Never assumes which one (if any) has real data.
    ---
    Genera las ubicaciones heredadas de agent_data anteriores al fix
    de S54, para una migracion automatica de mejor esfuerzo hacia la
    nueva ubicacion fija. Nunca asume cual (si alguna) tiene datos
    reales.
    """
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    # Junto al ejecutable actual (dist\ para el .exe empaquetado).
    yield os.path.join(exe_dir, AGENT_DATA_FOLDER_NAME)
    # Un nivel por encima (la raiz real del checkout, si el .exe
    # vive dentro de dist\).
    yield os.path.join(exe_dir, os.pardir, AGENT_DATA_FOLDER_NAME)


def _migrate_legacy_agent_data(new_dir):
    """Best-effort, non-destructive copy of any file found in a
    legacy agent_data location into the new fixed location. Never
    overwrites an existing file in new_dir, never deletes anything
    from the legacy location. Safe to call on every startup --
    becomes a no-op once migrated.
    ---
    Copia de mejor esfuerzo, no destructiva, de cualquier archivo
    encontrado en una ubicacion heredada de agent_data hacia la
    nueva ubicacion fija. Nunca sobrescribe un archivo ya existente
    en new_dir, nunca borra nada de la ubicacion heredada. Seguro de
    llamar en cada arranque -- se vuelve un no-op en cuanto ya se
    migro.
    """
    for legacy_dir in _legacy_agent_data_candidates():
        legacy_dir = os.path.abspath(legacy_dir)
        if legacy_dir == os.path.abspath(new_dir):
            continue
        if not os.path.isdir(legacy_dir):
            continue
        for name in os.listdir(legacy_dir):
            src = os.path.join(legacy_dir, name)
            dst = os.path.join(new_dir, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                logger.info(
                    '# Migracion S54: %s -> %s', src, dst,
                )


def get_agent_data_dir():
    """Return the persistent agent_data folder, creating it if
    needed. Lives under the current Windows user's LOCALAPPDATA,
    completely decoupled from wherever the executable happens to
    run from (dist\\, the project root, or any future location).

    This is the root-cause fix for the bug documented in
    SESSION_VARIABLES.md (S51/S53): the previous implementation
    joined AGENT_DATA_FOLDER_NAME onto get_agent_root_dir(), which
    resolves differently between dev-mode script execution and the
    packaged .exe running from PyInstaller's dist\\ output -- so
    watched_folders.json (and the rest of the persisted state) was
    never found by the version that actually runs under the
    Scheduled Task. Anchoring to LOCALAPPDATA removes the coupling
    entirely: rebuilding, moving the .exe, or renaming folders can
    never break this again.
    ---
    Devuelve la carpeta persistente agent_data, creandola si hace
    falta. Vive bajo el LOCALAPPDATA del usuario de Windows actual,
    completamente desacoplada de donde este corriendo el ejecutable
    (dist\\, la raiz del proyecto, o cualquier ubicacion futura).

    Este es el fix de raiz del bug documentado en
    SESSION_VARIABLES.md (S51/S53): la implementacion anterior unia
    AGENT_DATA_FOLDER_NAME a get_agent_root_dir(), que resuelve
    distinto entre ejecucion en modo script (desarrollo) y el .exe
    empaquetado corriendo desde la salida dist\\ de PyInstaller --
    asi que watched_folders.json (y el resto del estado persistido)
    nunca lo encontraba la version que de verdad corre bajo la
    Tarea Programada. Anclarlo a LOCALAPPDATA elimina el
    acoplamiento del todo: recompilar, mover el .exe, o renombrar
    carpetas ya no puede volver a romper esto.

    Especifico de Windows a proposito (S54, bug real detectado en
    local_ocr_classify.py corriendo en una VM Linux): en Linux este
    problema nunca existio -- el script SIEMPRE corre como
    `python3 local_ocr_classify.py` desde su propia carpeta, nunca
    empaquetado, asi que get_agent_root_dir() ya resuelve bien y
    agent_data/ vive relativo al checkout, tal como documenta
    SESSION_VARIABLES.md para las VMs de OCR. Sin este `if`, el fix
    de Windows rompia la ruta de la clave de servicio en Linux
    (buscaba en ~/EnterpriseBot/H28MigrationAgent/, que no existe).
    """
    if os.name != 'nt':
        data_dir = os.path.join(get_agent_root_dir(), AGENT_DATA_FOLDER_NAME)
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    data_dir = os.path.join(base, 'EnterpriseBot', 'H28MigrationAgent')
    os.makedirs(data_dir, exist_ok=True)
    _migrate_legacy_agent_data(data_dir)
    return data_dir


def get_service_account_key_path():
    """Return the service account key path to use.
    ---
    Devuelve la ruta de la clave de la cuenta de servicio a usar.

    Priority: the environment variable, if set; otherwise the
    default location inside agent_data/.
    ---
    Prioridad: la variable de entorno, si esta fijada; si no, la
    ubicacion por defecto dentro de agent_data/.
    """
    env_value = os.environ.get(SERVICE_ACCOUNT_KEY_ENV_VAR)
    if env_value:
        return env_value
    return os.path.join(
        get_agent_data_dir(), SERVICE_ACCOUNT_KEY_FILE_NAME
    )


def get_server_api_token():
    """Return the shared token for the server upload-notification webhook.
    ---
    Devuelve el token compartido para el webhook de aviso de subida
    al servidor.

    Priority: the environment variable, if set; otherwise a plain
    text file inside agent_data/ (never committed, same folder as the
    service account key). Returns None if neither exists -- callers
    must treat that as "cannot notify this time", never raise and
    never block the upload itself.
    ---
    Prioridad: la variable de entorno, si esta fijada; si no, un
    archivo de texto plano dentro de agent_data/ (nunca commiteado,
    misma carpeta que la clave de la cuenta de servicio). Devuelve
    None si no existe ninguno de los dos -- quien llama debe tratarlo
    como "no se puede avisar esta vez", nunca lanzar excepcion ni
    bloquear la propia subida.
    """
    env_value = os.environ.get(SERVER_API_TOKEN_ENV_VAR)
    if env_value:
        return env_value.strip()
    token_path = os.path.join(
        get_agent_data_dir(), SERVER_API_TOKEN_FILE_NAME
    )
    if not os.path.isfile(token_path):
        return None
    with open(token_path, "r", encoding="utf-8") as f:
        return f.read().strip() or None


def get_watched_folders_state_path():
    """Return the path of the watched-folders persistence file.
    ---
    Devuelve la ruta del archivo de persistencia de carpetas
    vigiladas.
    """
    return os.path.join(
        get_agent_data_dir(), WATCHED_FOLDERS_STATE_FILE_NAME
    )


def get_history_state_path():
    """Return the path of the history persistence file.
    ---
    Devuelve la ruta del archivo de persistencia del historial.
    """
    return os.path.join(
        get_agent_data_dir(), HISTORY_STATE_FILE_NAME
    )


def get_hydration_notify_state_path():
    """Return the path of the hydration-notification throttle file.
    ---
    Devuelve la ruta del archivo de control de aviso de hidratación.
    """
    return os.path.join(
        get_agent_data_dir(), HYDRATION_NOTIFY_STATE_FILE_NAME
    )


def get_catchup_index_dir():
    """Return the catch-up index folder, creating it if needed.
    ---
    Devuelve la carpeta del indice de puesta al dia, creandola si
    hace falta.

    Cuelga de agent_data/, ya cubierta por .gitignore: el indice
    contiene rutas reales de la documentacion de la empresa y nunca
    debe poder acabar en un commit.
    ---
    Hangs off agent_data/, already covered by .gitignore: the index
    holds real paths of company documentation.
    """
    index_dir = os.path.join(
        get_agent_data_dir(), CATCHUP_INDEX_FOLDER_NAME
    )
    os.makedirs(index_dir, exist_ok=True)
    return index_dir


def get_audit_output_dir():
    """Return the audit output folder, creating it if needed.
    ---
    Devuelve la carpeta de salida de auditorias, creandola si hace
    falta.

    Cuelga de agent_data/, que ya esta en .gitignore: el inventario
    contiene la estructura documental real de la empresa y nunca
    debe poder acabar en un commit por descuido.
    ---
    Hangs off agent_data/, already in .gitignore: the inventory
    holds the company's real document structure and must never be
    able to end up in a commit by accident.
    """
    audit_dir = os.path.join(get_agent_data_dir(), AUDIT_FOLDER_NAME)
    os.makedirs(audit_dir, exist_ok=True)
    return audit_dir

