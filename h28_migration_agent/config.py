# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/config.py
"""Configuration constants for the H28 migration agent.
---
Constantes de configuracion del agente de migracion H28."""

import os

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

# Path to the downloaded service account JSON key, read from an
# environment variable so the key value itself never lives in this
# repository (see com-standards, section "Secretos").
# ---
# Ruta a la clave JSON descargada de la cuenta de servicio, leida de
# una variable de entorno para que el valor de la clave nunca viva
# en este repositorio (ver com-standards, seccion "Secretos").
SERVICE_ACCOUNT_KEY_ENV_VAR = "H28_AGENT_KEY_PATH"

# Number of parallel upload workers used for the initial bulk copy.
# ---
# Numero de workers paralelos para la copia inicial en bruto.
UPLOAD_MAX_WORKERS = 8

# Local log file, written next to the executable.
# ---
# Archivo de log local, escrito junto al ejecutable.
LOG_FILE_NAME = "h28_migration_agent.log"


def get_service_account_key_path():
    """Return the configured service account key path, or None.
    ---
    Devuelve la ruta configurada de la clave de la cuenta de
    servicio, o None si no esta configurada.
    """
    return os.environ.get(SERVICE_ACCOUNT_KEY_ENV_VAR)
