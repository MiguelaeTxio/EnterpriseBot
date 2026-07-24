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

# Number of parallel upload workers used for the initial bulk copy.
# ---
# Numero de workers paralelos para la copia inicial en bruto.
UPLOAD_MAX_WORKERS = 8

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

