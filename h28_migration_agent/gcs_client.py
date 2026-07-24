# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/gcs_client.py
"""Shared Google Cloud Storage client for the H28 migration agent.
---
Cliente GCS compartido para el agente de migracion H28."""

import logging
import os

from google.cloud import storage

from config import get_service_account_key_path

logger = logging.getLogger(__name__)


class MissingCredentialsError(RuntimeError):
    """Raised when the service account key file cannot be found.
    ---
    Se lanza cuando no se encuentra el archivo de clave de la
    cuenta de servicio.
    """


def build_client():
    """Build a Storage client from the configured key file.
    ---
    Construye un cliente de Storage a partir del archivo de clave
    configurado.

    Raises
    ------
    MissingCredentialsError
        If the resolved key path does not point to an existing
        file.
        ---
        Si la ruta de clave resuelta no apunta a un archivo
        existente.
    """
    key_path = get_service_account_key_path()
    if not key_path or not os.path.isfile(key_path):
        raise MissingCredentialsError(
            "No se encuentra el archivo de la clave de la cuenta de "
            f"servicio en:\n{key_path}\n\n"
            "Copia ahi el JSON descargado de Google Cloud (o fija la "
            "variable de entorno H28_AGENT_KEY_PATH apuntando a otra "
            "ubicacion)."
        )
    logger.info("Autenticando con la clave de servicio configurada.")
    return storage.Client.from_service_account_json(key_path)

