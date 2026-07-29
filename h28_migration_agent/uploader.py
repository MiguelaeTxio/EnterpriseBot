# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/uploader.py
"""Upload logic for the H28 migration agent.
---
Logica de subida del agente de migracion H28.

Fase 1 punto 2 (anexo H28): el cubo sucio no se transforma nada, se
sube tal cual, con toda la suciedad real, en forma recursiva y
completa.
---
Phase 1 point 2 (H28 annex): the dirty bucket is never transformed,
everything is uploaded as-is, recursively and completely.
"""

import logging
import os

from google.cloud.storage import transfer_manager

from config import QUARANTINE_PREFIX, UPLOAD_MAX_WORKERS
from fs_utils import (
    is_cloud_only,
    is_transient_file,
    make_walk_error_handler,
    request_hydration,
    to_long_path,
)

logger = logging.getLogger(__name__)


def iter_relative_file_paths(
    root_folder, context_label="Escaneo local"
):
    """Yield every file path under root_folder, recursively.
    ---
    Genera cada ruta de archivo bajo root_folder, de forma
    recursiva.

    Un directorio ilegible NO se descarta en silencio: se registra
    via `fs_utils.make_walk_error_handler`. Sin ese manejador,
    `os.walk` se traga el error y esta funcion devuelve menos
    archivos sin que nada lo delate -- y como de ella parten tanto la
    copia inicial (`upload_folder_recursive`) como la reconciliacion
    (`reconciler._find_mismatches`), el hueco quedaba invisible en
    los dos sitios a la vez: lo que el recorrido no ve, la
    reconciliacion tampoco puede repararlo. Es exactamente el fallo
    documentado en el anexo H28 (S032-S033), donde 4 archivos de
    `DOC. PERSONAL` nunca llegaron al cubo sin dejar rastro. El
    blindaje se escribio en S034 pero se quedo solo en `auditor.py`;
    aqui se cierra el hueco (S036).

    Parameters
    ----------
    root_folder : str
    context_label : str, optional
        Operacion que recorre el arbol, para el log de errores.
        ---
        Operation walking the tree, used in the error log line.

    Returns
    -------
    Iterator[str]
        Paths relative to root_folder, with forward slashes — safe
        both for local lookup (Windows accepts "/") and as part of
        a GCS blob name.
        ---
        Rutas relativas a root_folder, con barra "/" — validas
        tanto para la busqueda local (Windows acepta "/") como para
        formar parte de un nombre de blob de GCS.
    ---
    An unreadable directory is NOT silently discarded: it is logged
    through `fs_utils.make_walk_error_handler`. Without that handler
    `os.walk` swallows the error and this function returns fewer
    files with nothing giving it away -- and since both the initial
    copy and reconciliation start from it, the gap was invisible in
    both at once.
    """
    walk_error_handler = make_walk_error_handler(context_label)
    skipped_transient_count = 0
    for current_dir, _dirs, file_names in os.walk(
        root_folder, onerror=walk_error_handler,
    ):
        for file_name in file_names:
            # Los temporales de Office/OneDrive no son documentacion y
            # no deben llegar ni al cubo ni a la cola de cuarentena
            # (anexo H28, S036). Se filtran en el UNICO recorrido del
            # que beben la copia, la reconciliacion y el barrido, para
            # que los tres compartan exactamente el mismo criterio.
            # ---
            # Office/OneDrive temporaries are not documentation.
            # Filtered in the SINGLE walk that the copy, the
            # reconciliation and the sweep all draw from, so the three
            # share exactly the same criterion.
            if is_transient_file(file_name):
                skipped_transient_count += 1
                continue
            full_path = os.path.join(current_dir, file_name)
            relative_path = os.path.relpath(full_path, root_folder)
            yield relative_path.replace(os.sep, "/")

    if skipped_transient_count:
        # A DEBUG: el barrido corre cada minuto y esto seria ruido en
        # INFO. Pero se registra, porque un numero anormalmente alto
        # significaria que el filtro esta descartando algo que no
        # deberia.
        # ---
        # DEBUG: the sweep runs every minute. Logged all the same,
        # because an abnormally high number would mean the filter is
        # discarding something it should not.
        logger.debug(
            "%s: %d archivo(s) temporal(es) omitido(s).",
            context_label, skipped_transient_count,
        )


def build_blob_name(selected_folder, relative_path):
    """Build the destination blob name inside the dirty bucket.
    ---
    Construye el nombre del blob de destino dentro del cubo sucio.

    Confirmado por Miguel Angel (S031): la carpeta elegida es
    siempre la raiz de la ruta dentro del cubo — nunca se incluye lo
    que hay por encima de ella en la ruta local de Windows (unidad,
    OneDrive, DOCUMENTOS GRUPO ALVAREZ, etc.).
    ---
    Confirmed by Miguel Angel (S031): the chosen folder is always
    the root of the path inside the bucket — whatever sits above it
    in the local Windows path (drive, OneDrive, DOCUMENTOS GRUPO
    ALVAREZ, etc.) is never included.
    """
    folder_name = os.path.basename(os.path.normpath(selected_folder))
    posix_relative = relative_path.replace(os.sep, "/")
    return f"{folder_name}/{posix_relative}"



def build_quarantine_blob_name(selected_folder, relative_path):
    """Build the destination blob name inside the quarantine prefix.
    ---
    Construye el nombre del blob de destino dentro del prefijo de
    cuarentena.

    Desde S036 la cuarentena es un prefijo en la raiz del MISMO cubo,
    no un cubo aparte: el arbol espejo vive en `{carpeta}/...` y su
    cola de revision en `_CUARENTENA/{carpeta}/...`. Se conserva la
    ruta relativa completa para que, al clasificar, se sepa de donde
    salio cada archivo.

    Que sean hermanos en la raiz y no anidados es lo que mantiene
    separados los dos listados por prefijo del reconciliador -- ver
    `config.QUARANTINE_PREFIX`.
    ---
    Since S036 quarantine is a prefix at the root of the SAME bucket:
    the mirror tree lives at `{folder}/...` and its review queue at
    `_CUARENTENA/{folder}/...`. Being siblings at the root is what
    keeps the reconciler's two prefix listings apart.
    """
    return QUARANTINE_PREFIX + build_blob_name(
        selected_folder, relative_path
    )


def request_hydration_for_cloud_only(selected_folder, relative_paths):
    """Pin every cloud-only file under selected_folder for download.

    ---
    Ancla para su descarga todos los archivos solo-en-nube bajo
    selected_folder.

    Se ejecuta ANTES de la copia. Un marcador de posicion de OneDrive
    no se puede abrir, luego no se sube ni se hashea, y hasta S035 eso
    no dejaba constancia en ningun sitio salvo si pasaba el auditor
    (anexo H28, defecto 3 de S035). Detectarlos es gratis -- solo
    metadatos -- asi que la pasada previa no penaliza de forma
    apreciable.

    La descarga que dispara OneDrive es asincrona: esta funcion no la
    espera. Los que no lleguen a tiempo fallaran la subida, quedaran
    registrados como fallo, y la reconciliacion -- que ahora tambien
    los detecta -- los recogera despues. El barrido con espera activa
    es el modo "puesta al dia" del punto 2 de la hoja de ruta, y no se
    inventa aqui.
    ---
    Runs BEFORE the copy. A OneDrive placeholder cannot be opened, so
    it is neither uploaded nor hashed, and until S035 that left no
    trace anywhere unless the auditor happened to run. Detection is
    free -- metadata only. The download OneDrive triggers is
    asynchronous and is not awaited here.

    Returns
    -------
    int
        Numero de archivos para los que se pidio la descarga.
        ---
        Number of files hydration was requested for.
    """
    requested_count = 0
    for relative_path in relative_paths:
        absolute_path = os.path.join(selected_folder, relative_path)
        if is_cloud_only(absolute_path) and request_hydration(
            absolute_path
        ):
            requested_count += 1
    if requested_count:
        logger.warning(
            "%d archivo(s) estaban solo en la nube y se han anclado "
            "para su descarga. Los que no se materialicen a tiempo "
            "fallaran en esta copia y los recogera la "
            "reconciliacion.", requested_count,
        )
    return requested_count


def upload_folder_recursive(
    client, bucket_name, selected_folder, progress_callback=None
):
    """Upload every file under selected_folder, unmodified.
    ---
    Sube cada archivo bajo selected_folder, sin modificarlo.

    Parameters
    ----------
    client : google.cloud.storage.Client
    bucket_name : str
    selected_folder : str
        Local folder chosen by Miguel Angel in the agent dialog.
        ---
        Carpeta local elegida por Miguel Angel en el dialogo.
    progress_callback : callable, optional
        Called with (uploaded_count, total_count) after each batch.
        ---
        Se llama con (subidos, total) tras cada lote.
    """
    bucket = client.bucket(bucket_name)
    relative_paths = list(
        iter_relative_file_paths(selected_folder, "Copia inicial")
    )
    total_count = len(relative_paths)
    logger.info(
        "Copia inicial: %d archivos encontrados bajo %s",
        total_count,
        selected_folder,
    )

    folder_name = os.path.basename(os.path.normpath(selected_folder))
    blob_name_prefix = f"{folder_name}/"

    request_hydration_for_cloud_only(selected_folder, relative_paths)

    # worker_type="thread": la carga es de I/O de red, no de CPU, y
    # el tipo por defecto ("process") requiere
    # multiprocessing.freeze_support() para funcionar bien
    # empaquetado con PyInstaller --onefile — se evita el problema
    # usando hilos, mas apropiados aqui de todos modos.
    # ---
    # worker_type="thread": the workload is network I/O, not CPU,
    # and the default ("process") requires
    # multiprocessing.freeze_support() to work correctly when
    # packaged with PyInstaller --onefile — using threads avoids the
    # problem and fits this I/O-bound case better anyway.
    results = transfer_manager.upload_many_from_filenames(
        bucket,
        relative_paths,
        source_directory=selected_folder,
        blob_name_prefix=blob_name_prefix,
        max_workers=UPLOAD_MAX_WORKERS,
        worker_type=transfer_manager.THREAD,
    )

    uploaded_count = 0
    failed_paths = []
    for relative_path, result in zip(relative_paths, results):
        if isinstance(result, Exception):
            failed_paths.append((relative_path, result))
            logger.error(
                "Fallo al subir %s: %s", relative_path, result
            )
        else:
            uploaded_count += 1
        if progress_callback is not None:
            progress_callback(uploaded_count, total_count)

    logger.info(
        "Copia inicial completada: %d/%d subidos, %d fallos.",
        uploaded_count,
        total_count,
        len(failed_paths),
    )
    return uploaded_count, failed_paths


def upload_single_file_to_quarantine(
    client, bucket_name, selected_folder, absolute_file_path
):
    """Upload one new file to the quarantine prefix.
    ---
    Sube un archivo nuevo al prefijo de cuarentena.

    Usado por el vigilante (`watcher.py`) para archivos que aparecen
    despues de la copia inicial, y por el barrido de puesta al dia
    (`catchup.py`) para los que llegan por sincronizacion sin generar
    evento -- nunca se escriben en el arbol espejo (Fase 1 punto 3
    del anexo H28).

    `bucket_name` es ahora el cubo UNICO: desde S036 la cuarentena es
    un prefijo dentro de el, no un cubo aparte.
    ---
    Used by the watcher for files appearing after the initial copy,
    and by the catch-up sweep for those arriving by sync without
    raising an event -- never written into the mirror tree.

    `bucket_name` is now the single bucket: since S036 quarantine is
    a prefix inside it, not a separate bucket.
    """
    bucket = client.bucket(bucket_name)
    relative_path = os.path.relpath(absolute_file_path, selected_folder)
    blob_name = build_quarantine_blob_name(
        selected_folder, relative_path
    )
    blob = bucket.blob(blob_name)
    # El nombre del blob se calcula SIEMPRE con la ruta original: el
    # prefijo de ruta larga es un detalle de la API de Windows y no
    # debe filtrarse jamas al arbol del cubo. Solo se usa en el
    # momento de abrir el archivo (anexo H28, S033).
    # ---
    # The blob name is ALWAYS computed from the original path: the
    # long-path prefix is a Windows API detail and must never leak
    # into the bucket tree. It is used only when opening the file.
    blob.upload_from_filename(to_long_path(absolute_file_path))
    logger.info("Cuarentena: %s -> gs://%s/%s",
                absolute_file_path, bucket_name, blob_name)
    return blob_name
