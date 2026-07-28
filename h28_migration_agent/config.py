# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/config.py
"""Configuration constants for the H28 migration agent.
---
Constantes de configuracion del agente de migracion H28."""

import os
import sys

# GCS bucket names, confirmed by Miguel Angel in S031.
# ---
# Nombres de los cubos GCS, confirmados por Miguel Angel en S031.
DIRTY_BUCKET_NAME = "cgs_grupo_alvarez"
QUARANTINE_BUCKET_NAME = "cgs_grupo_alvarez_cuarentena"

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
    ---
    Devuelve el directorio desde el que corre el agente (script o
    .exe).
    """
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def get_agent_data_dir():
    """Return the local agent_data folder path, creating it if
    needed.
    ---
    Devuelve la ruta de la carpeta local agent_data, creandola si
    hace falta.
    """
    data_dir = os.path.join(get_agent_root_dir(), AGENT_DATA_FOLDER_NAME)
    os.makedirs(data_dir, exist_ok=True)
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

