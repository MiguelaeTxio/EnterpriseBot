# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/gcs_client.py
"""Shared Google Cloud Storage client for the H28 migration agent.
---
Cliente GCS compartido para el agente de migracion H28."""

import logging

from google.cloud import storage

from config import get_service_account_key_path

logger = logging.getLogger(__name__)


class MissingCredentialsError(RuntimeError):
    """Raised when no service account key path is configured.
    ---
    Se lanza cuando no hay ruta de clave de cuenta de servicio
    configurada.
    """


def build_client():
    """Build a Storage client from the configured key file.
    ---
    Construye un cliente de Storage a partir del archivo de clave
    configurado.

    Raises
    ------
    MissingCredentialsError
        If the H28_AGENT_KEY_PATH environment variable is not set.
        ---
        Si la variable de entorno H28_AGENT_KEY_PATH no esta fijada.
    """
    key_path = get_service_account_key_path()
    if not key_path:
        raise MissingCredentialsError(
            "No se ha configurado la ruta de la clave de la cuenta "
            "de servicio (variable de entorno H28_AGENT_KEY_PATH)."
        )
    logger.info("Autenticando con la clave de servicio configurada.")
    return storage.Client.from_service_account_json(key_path)
