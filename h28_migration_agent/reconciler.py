# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/reconciler.py
"""Reconciliation logic for the H28 migration agent.
---
Logica de reconciliacion del agente de migracion H28.

S033 (anexo H28): el agente carecia de cualquier mecanismo de
recuperacion tras la copia inicial -- un archivo que el escaneo
local se saltara, o que fallara al subir, se perdia en silencio
salvo revision manual del log. Confirmado por Miguel Angel: el
sistema debe poder afrontar errores y recuperarse solo, sin
intervencion por consola.

Este modulo vuelve a comparar la carpeta local contra lo que hay
realmente en el cubo (usando la propia libreria
google-cloud-storage, nunca gcloud CLI), reintenta con backoff lo
que falte o no coincida en tamano, y deja constancia clara de lo
que siga sin poder subirse.
---
Phase 1 point 2 (H28 annex, S033): the agent had no recovery
mechanism after the initial copy -- a file skipped by the local
scan, or one that failed to upload, was silently lost unless the
log was checked by hand. Confirmed by Miguel Angel: the system must
be able to handle errors and recover on its own, without console
intervention.

This module re-compares the local folder against what actually
exists in the bucket (using the google-cloud-storage library itself,
never the gcloud CLI), retries with backoff whatever is missing or
size-mismatched, and clearly records whatever still cannot be
uploaded.
"""

import logging
import os
import time

from config import RECONCILE_MAX_RETRIES, RECONCILE_RETRY_DELAYS_SECONDS
from uploader import build_blob_name, iter_relative_file_paths

logger = logging.getLogger(__name__)


def _list_remote_sizes(bucket, blob_name_prefix):
    """Return a dict of blob_name -> size for every blob under
    blob_name_prefix.
    ---
    Devuelve un diccionario blob_name -> tamano para cada blob bajo
    blob_name_prefix.
    """
    remote_sizes = {}
    for blob in bucket.list_blobs(prefix=blob_name_prefix):
        remote_sizes[blob.name] = blob.size
    return remote_sizes


def _find_mismatches(selected_folder, remote_sizes):
    """Return the list of (relative_path, blob_name) not present in
    remote_sizes, or present with a different size.
    ---
    Devuelve la lista de (relative_path, blob_name) ausentes en
    remote_sizes, o presentes con un tamano distinto.
    """
    mismatches = []
    for relative_path in iter_relative_file_paths(selected_folder):
        blob_name = build_blob_name(selected_folder, relative_path)
        local_path = os.path.join(selected_folder, relative_path)
        try:
            local_size = os.path.getsize(local_path)
        except OSError as error:
            logger.error(
                "No se pudo leer el tamano local de %s: %s",
                local_path, error,
            )
            continue
        remote_size = remote_sizes.get(blob_name)
        if remote_size != local_size:
            mismatches.append((relative_path, blob_name, local_path))
    return mismatches


def _upload_with_retries(bucket, relative_path, blob_name, local_path):
    """Retry a single upload with growing delays between attempts.
    ---
    Reintenta la subida de un solo archivo con esperas crecientes
    entre intentos.

    Returns
    -------
    bool
        True if the file ended up uploaded, False if every retry
        failed.
        ---
        True si el archivo termino subido, False si fallaron todos
        los reintentos.
    """
    blob = bucket.blob(blob_name)
    for attempt in range(1, RECONCILE_MAX_RETRIES + 1):
        try:
            blob.upload_from_filename(local_path)
            logger.info(
                "Reconciliacion: subido en el intento %d/%d -> %s",
                attempt, RECONCILE_MAX_RETRIES, relative_path,
            )
            return True
        except Exception as error:  # noqa: BLE001 -- see docstring
            # Se captura cualquier excepcion porque una subida de
            # red puede fallar de formas muy distintas (timeout,
            # conexion perdida, error de la API) y todas deben
            # tratarse igual: reintentar, no propagar.
            # ---
            # Any exception is caught because a network upload can
            # fail in many different ways (timeout, dropped
            # connection, API error) and all of them are handled the
            # same way: retry, do not propagate.
            logger.warning(
                "Reconciliacion: fallo intento %d/%d de %s: %s",
                attempt, RECONCILE_MAX_RETRIES, relative_path, error,
            )
            if attempt < RECONCILE_MAX_RETRIES:
                delay = RECONCILE_RETRY_DELAYS_SECONDS[attempt - 1]
                time.sleep(delay)
    return False


def reconcile_folder(client, bucket_name, selected_folder,
                      progress_callback=None):
    """Compare selected_folder against the bucket and repair gaps.
    ---
    Compara selected_folder contra el cubo y repara los huecos.

    Parameters
    ----------
    client : google.cloud.storage.Client
    bucket_name : str
    selected_folder : str
        Local folder to reconcile -- must be the same folder
        originally passed to upload_folder_recursive.
        ---
        Carpeta local a reconciliar -- debe ser la misma carpeta
        pasada originalmente a upload_folder_recursive.
    progress_callback : callable, optional
        Called with (checked_count, total_count) while comparing.
        ---
        Se llama con (comprobados, total) durante la comparacion.

    Returns
    -------
    tuple[int, list[str]]
        (repaired_count, unrecoverable_relative_paths)
    """
    bucket = client.bucket(bucket_name)
    folder_name = os.path.basename(os.path.normpath(selected_folder))
    blob_name_prefix = f"{folder_name}/"

    logger.info(
        "Reconciliacion: listando cubo para %s", selected_folder,
    )
    remote_sizes = _list_remote_sizes(bucket, blob_name_prefix)

    mismatches = _find_mismatches(selected_folder, remote_sizes)
    total_count = len(mismatches)
    logger.info(
        "Reconciliacion: %d archivo(s) ausente(s) o con tamano "
        "distinto en %s", total_count, selected_folder,
    )

    repaired_count = 0
    unrecoverable_relative_paths = []
    for checked_count, (relative_path, blob_name, local_path) in (
        enumerate(mismatches, start=1)
    ):
        if _upload_with_retries(
            bucket, relative_path, blob_name, local_path,
        ):
            repaired_count += 1
        else:
            unrecoverable_relative_paths.append(relative_path)
            logger.error(
                "IRRECUPERABLE: %s (agotados %d reintentos)",
                relative_path, RECONCILE_MAX_RETRIES,
            )
        if progress_callback is not None:
            progress_callback(checked_count, total_count)

    logger.info(
        "Reconciliacion completada en %s: %d reparados, %d "
        "irrecuperables.",
        selected_folder, repaired_count,
        len(unrecoverable_relative_paths),
    )
    return repaired_count, unrecoverable_relative_paths
