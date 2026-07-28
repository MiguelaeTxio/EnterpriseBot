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

import base64
import hashlib
import logging
import os
import time

from config import (
    HASH_CHUNK_SIZE_BYTES,
    QUARANTINE_BUCKET_NAME,
    RECONCILE_MAX_RETRIES,
    RECONCILE_RETRY_DELAYS_SECONDS,
)
from fs_utils import is_cloud_only, request_hydration, to_long_path
from uploader import build_blob_name, iter_relative_file_paths

logger = logging.getLogger(__name__)


def compute_md5_base64(local_path):
    """Return the base64-encoded MD5 of a local file, GCS style.

    ---
    Devuelve el MD5 en base64 de un archivo local, en el mismo
    formato que usa GCS.

    Verificado en linea el 2026-07-27 (directriz 4.4) contra la
    documentacion oficial de google-cloud-storage: `blob.md5_hash`
    viene codificado en BASE64, no en hexadecimal -- comparar contra
    un `hexdigest()` daria distinto siempre, aunque el contenido
    fuese identico.
    ---
    Verified online on 2026-07-27 (directive 4.4) against the
    official google-cloud-storage documentation: `blob.md5_hash` is
    BASE64-encoded, not hexadecimal -- comparing it against a
    `hexdigest()` would always differ, even for identical content.
    """
    digest = hashlib.md5()
    with open(to_long_path(local_path), "rb") as file_handle:
        while True:
            chunk = file_handle.read(HASH_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def _list_remote_info(bucket, blob_name_prefix):
    """Return blob_name -> (size, md5_base64) for every blob under
    blob_name_prefix.
    ---
    Devuelve blob_name -> (tamano, md5_base64) para cada blob bajo
    blob_name_prefix.

    El MD5 llega en el mismo listado paginado, sin ninguna llamada
    extra a la API -- por eso la comparacion por hash del lado
    remoto es gratis, y solo cuesta leer el archivo local.

    `md5_hash` puede ser None (objetos compuestos, segun la
    documentacion oficial); quien llama debe preverlo.
    ---
    The MD5 arrives in the same paginated listing, with no extra API
    call -- which is why hash comparison is free on the remote side.
    `md5_hash` may be None (composite objects, per the official
    documentation); callers must handle that.
    """
    remote_info = {}
    for blob in bucket.list_blobs(prefix=blob_name_prefix):
        remote_info[blob.name] = (blob.size, blob.md5_hash)
    return remote_info


def _find_mismatches(selected_folder, remote_info):
    """Return files absent from the dirty bucket, or present with
    different content.
    ---
    Devuelve los archivos ausentes del cubo sucio, o presentes con
    contenido distinto.

    Comparacion hibrida, decision de Miguel Angel (S034), por coste
    asimetrico: primero el tamano, que es gratis; y solo cuando el
    tamano coincide se calcula el MD5 local para descartar el falso
    negativo de un documento revisado que pese exactamente lo mismo
    que el original (p.ej. un permiso de circulacion reexpedido). La
    alternativa de comparar siempre por hash obligaria a leer los
    28 GB enteros en cada arranque del agente.

    Si el blob remoto no expone MD5 (objetos compuestos, ver
    `_list_remote_info`), no hay nada contra lo que comparar: se da
    por bueno el tamano y se registra, para no mandar a cuarentena un
    archivo entero por falta de metadato.
    ---
    Hybrid comparison, Miguel Angel's decision (S034), driven by
    asymmetric cost: size first, which is free; the local MD5 is
    computed only when sizes match, to rule out the false negative of
    a revised document weighing exactly the same as the original.

    Un archivo solo-en-nube NO entra en la lista de diferencias. No se
    puede leer, luego no se puede subir ni hashear: intentarlo quema
    los tres reintentos y lo marca `IRRECUPERABLE`, que es exactamente
    lo que ocurrio en S033. Se ancla para su descarga y se devuelve
    aparte, para que la pasada siguiente -- ya con el contenido en
    disco -- lo trate con normalidad.

    Returns
    -------
    tuple[list[tuple[str, str, str, int]], list[str]]
        (diferencias, rutas_relativas_pendientes_de_descarga), donde
        cada diferencia es
        (relative_path, blob_name, local_path, local_size).
        ---
        (mismatches, relative paths awaiting hydration).
    """
    mismatches = []
    pending_hydration_paths = []
    for relative_path in iter_relative_file_paths(
        selected_folder, "Reconciliacion"
    ):
        blob_name = build_blob_name(selected_folder, relative_path)
        local_path = os.path.join(selected_folder, relative_path)

        # Se comprueba ANTES que nada: de un marcador de posicion,
        # `getsize` devuelve el tamano logico real y enganaria a la
        # comparacion de tamano, mientras que `open()` -- y por tanto
        # el MD5 y la subida -- falla con `[Errno 22]`.
        # ---
        # Checked first: for a placeholder, `getsize` returns the real
        # logical size and would fool the size comparison, while
        # `open()` -- and hence the MD5 and the upload -- fails.
        if is_cloud_only(local_path):
            request_hydration(local_path)
            pending_hydration_paths.append(relative_path)
            continue

        try:
            local_size = os.path.getsize(to_long_path(local_path))
        except OSError as error:
            logger.error(
                "No se pudo leer el tamano local de %s: %s",
                local_path, error,
            )
            continue

        remote_size, remote_md5 = remote_info.get(
            blob_name, (None, None),
        )

        if remote_size != local_size:
            mismatches.append(
                (relative_path, blob_name, local_path, local_size)
            )
            continue

        if remote_md5 is None:
            logger.info(
                "El blob %s no expone MD5; se acepta la coincidencia "
                "de tamano.", blob_name,
            )
            continue

        try:
            local_md5 = compute_md5_base64(local_path)
        except OSError as error:
            logger.error(
                "No se pudo calcular el MD5 local de %s: %s",
                local_path, error,
            )
            continue

        if local_md5 != remote_md5:
            logger.info(
                "Mismo tamano pero distinto contenido: %s",
                relative_path,
            )
            mismatches.append(
                (relative_path, blob_name, local_path, local_size)
            )
    return mismatches, pending_hydration_paths


def _is_same_content(local_path, local_size, remote_size, remote_md5):
    """Return True if a local file matches a remote blob's content.

    ---
    Devuelve True si el archivo local coincide en contenido con el
    blob remoto.

    Mismo criterio hibrido que `_find_mismatches`: el tamano decide
    cuando difiere, y solo si coincide se recurre al MD5. Si el blob
    no expone MD5, la coincidencia de tamano se da por buena.
    ---
    Same hybrid criterion as `_find_mismatches`: size decides when it
    differs, and only when it matches is the MD5 consulted.
    """
    if remote_size != local_size:
        return False
    if remote_md5 is None:
        return True
    try:
        return compute_md5_base64(local_path) == remote_md5
    except OSError as error:
        logger.error(
            "No se pudo calcular el MD5 local de %s: %s",
            local_path, error,
        )
        return True


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
    """Compare selected_folder against the dirty bucket and send any
    gap to quarantine.
    ---
    Compara selected_folder contra el cubo sucio y manda a cuarentena
    cualquier hueco.

    Cambio de destino, decision explicita de Miguel Angel (S034): lo
    que la reconciliacion encuentra ya NO se sube al cubo sucio, se
    sube al cubo de CUARENTENA, y la copia del cubo sucio no se toca
    jamas. Motivo: el reconciliador no puede distinguir un hueco del
    escaneo inicial de un archivo nuevo o revisado aparecido despues,
    y el punto 3 de la seccion 3 del anexo H28 exige que todo lo
    posterior a la copia inicial pase por revision. Consecuencia
    querida: el cubo sucio queda como foto fija de la copia inicial,
    base estable para la Fase 2, y la cuarentena se convierte en cola
    de proceso para la tarea clasificadora asincrona de la Fase 3.

    Criterio verbatim de Miguel Angel sobre nombres repetidos: "no
    estamos hablando del mismo archivo, sino de un archivo con el
    mismo nombre... Miramos hash, son dos archivos diferentes. Tiene
    que clasificarse." Dos documentos con el mismo nombre y distinto
    contenido son dos documentos reales -- se conservan ambos y se
    diferencian al clasificar (00, 01); la decision final de borrar
    es de la supervisora de documentacion desde el explorador de la
    plataforma, nunca automatica.
    ---
    Destination change, Miguel Angel's explicit decision (S034):
    whatever reconciliation finds is NO LONGER uploaded to the dirty
    bucket but to the QUARANTINE bucket, and the dirty bucket's copy
    is never touched. The dirty bucket becomes a fixed snapshot of
    the initial copy, and quarantine becomes the processing queue for
    Phase 3's asynchronous classifier task.

    Parameters
    ----------
    client : google.cloud.storage.Client
    bucket_name : str
        The dirty bucket -- read only, used as the reference to
        compare against. Never written to.
        ---
        El cubo sucio -- solo lectura, referencia contra la que se
        compara. Nunca se escribe en el.
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
    tuple[int, int, list[str], list[str], list[str]]
        (quarantined_count, already_queued_count,
        needs_decision_relative_paths,
        pending_hydration_relative_paths,
        unrecoverable_relative_paths)
    """
    bucket = client.bucket(bucket_name)
    quarantine_bucket = client.bucket(QUARANTINE_BUCKET_NAME)
    folder_name = os.path.basename(os.path.normpath(selected_folder))
    blob_name_prefix = f"{folder_name}/"

    logger.info(
        "Reconciliacion: listando cubo sucio para %s", selected_folder,
    )
    remote_info = _list_remote_info(bucket, blob_name_prefix)

    logger.info(
        "Reconciliacion: listando cubo de cuarentena para %s",
        selected_folder,
    )
    quarantine_info = _list_remote_info(
        quarantine_bucket, blob_name_prefix,
    )

    mismatches, pending_hydration_paths = _find_mismatches(
        selected_folder, remote_info,
    )
    total_count = len(mismatches)
    logger.info(
        "Reconciliacion: %d archivo(s) ausente(s) o con tamano "
        "distinto en %s", total_count, selected_folder,
    )
    if pending_hydration_paths:
        logger.warning(
            "Reconciliacion: %d archivo(s) estaban solo en la nube y "
            "se han anclado para su descarga en %s. No se han podido "
            "comprobar en esta pasada; la siguiente los tratara con "
            "normalidad.",
            len(pending_hydration_paths), selected_folder,
        )

    quarantined_count = 0
    already_queued_count = 0
    needs_decision_paths = []
    unrecoverable_relative_paths = []
    for checked_count, (
        relative_path, blob_name, local_path, local_size
    ) in enumerate(mismatches, start=1):
        quarantined_size, quarantined_md5 = quarantine_info.get(
            blob_name, (None, None),
        )

        if quarantined_size is not None and _is_same_content(
            local_path, local_size, quarantined_size, quarantined_md5,
        ):
            # Ya esta en la cola de cuarentena, con el mismo tamano:
            # no hay nada que hacer, la tarea clasificadora lo
            # recogera cuando le toque.
            # ---
            # Already queued in quarantine at the same size: nothing
            # to do, the classifier task will pick it up.
            already_queued_count += 1
            logger.info(
                "Reconciliacion: %s ya esta en cola de cuarentena.",
                relative_path,
            )
        elif quarantined_size is not None:
            # Hay una version distinta esperando en cuarentena.
            # Subir encima la destruiria, y el criterio de Miguel
            # Angel (S034) es que dos documentos con el mismo nombre
            # y distinto contenido son dos documentos reales que hay
            # que conservar y diferenciar (00, 01) al clasificarlos,
            # nunca uno que pisa al otro. No se toca nada: se
            # registra para decision explicita.
            # ---
            # A different version is already waiting in quarantine.
            # Uploading over it would destroy it, and Miguel Angel's
            # criterion (S034) is that two documents sharing a name
            # with different content are two real documents to be
            # kept and told apart (00, 01) at classification time,
            # never one overwriting the other. Nothing is touched:
            # recorded for an explicit decision.
            needs_decision_paths.append(relative_path)
            logger.warning(
                "PENDIENTE DE DECISION: %s ya tiene una version "
                "distinta en cuarentena (local %d bytes, en "
                "cuarentena %d bytes). No se sobrescribe.",
                relative_path, local_size, quarantined_size,
            )
        elif _upload_with_retries(
            quarantine_bucket, relative_path, blob_name, local_path,
        ):
            quarantined_count += 1
        else:
            unrecoverable_relative_paths.append(relative_path)
            logger.error(
                "IRRECUPERABLE: %s (agotados %d reintentos)",
                relative_path, RECONCILE_MAX_RETRIES,
            )
        if progress_callback is not None:
            progress_callback(checked_count, total_count)

    logger.info(
        "Reconciliacion completada en %s: %d a cuarentena, %d ya en "
        "cola, %d pendientes de decision, %d pendientes de descarga, "
        "%d irrecuperables. El cubo sucio no se ha modificado.",
        selected_folder, quarantined_count, already_queued_count,
        len(needs_decision_paths), len(pending_hydration_paths),
        len(unrecoverable_relative_paths),
    )
    return (
        quarantined_count, already_queued_count, needs_decision_paths,
        pending_hydration_paths, unrecoverable_relative_paths,
    )
