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

from config import UPLOAD_MAX_WORKERS

logger = logging.getLogger(__name__)


def _iter_relative_file_paths(root_folder):
    """Yield every file path under root_folder, recursively.
    ---
    Genera cada ruta de archivo bajo root_folder, de forma
    recursiva.

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
    """
    for current_dir, _dirs, file_names in os.walk(root_folder):
        for file_name in file_names:
            full_path = os.path.join(current_dir, file_name)
            relative_path = os.path.relpath(full_path, root_folder)
            yield relative_path.replace(os.sep, "/")


def build_blob_name(selected_folder, relative_path):
    """Build the destination blob name inside the dirty bucket.
    ---
    Construye el nombre del blob de destino dentro del cubo sucio.

    Nota de implementacion (S031, pendiente de confirmar en la
    sesion siguiente de H28): se usa el nombre de la carpeta
    seleccionada como raiz dentro del cubo, seguido de la ruta
    relativa interna — no la ruta absoluta completa de Windows
    (unidad, OneDrive, etc.), que no aporta valor real dentro del
    cubo y complica la lectura humana. Confirmar con Miguel Angel si
    esto coincide con lo que se entendia por "replicar la ruta local
    completa".
    """
    folder_name = os.path.basename(os.path.normpath(selected_folder))
    posix_relative = relative_path.replace(os.sep, "/")
    return f"{folder_name}/{posix_relative}"


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
    relative_paths = list(_iter_relative_file_paths(selected_folder))
    total_count = len(relative_paths)
    logger.info(
        "Copia inicial: %d archivos encontrados bajo %s",
        total_count,
        selected_folder,
    )

    folder_name = os.path.basename(os.path.normpath(selected_folder))
    blob_name_prefix = f"{folder_name}/"

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
    """Upload one new file to the quarantine bucket.
    ---
    Sube un archivo nuevo al cubo de cuarentena.

    Used by the watchdog handler for files that appear after the
    initial copy — never written to the dirty bucket mirror tree
    (Fase 1 punto 3 del anexo H28).
    ---
    Usado por el manejador de watchdog para archivos que aparecen
    despues de la copia inicial — nunca se escriben en el arbol
    espejo del cubo sucio (Fase 1 punto 3 del anexo H28).
    """
    bucket = client.bucket(bucket_name)
    relative_path = os.path.relpath(absolute_file_path, selected_folder)
    blob_name = build_blob_name(selected_folder, relative_path)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(absolute_file_path)
    logger.info("Cuarentena: %s -> gs://%s/%s",
                absolute_file_path, bucket_name, blob_name)
    return blob_name
