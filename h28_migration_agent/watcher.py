# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/watcher.py
"""Continuous folder watching for the H28 migration agent.
---
Vigilancia continua de carpetas del agente de migracion H28.

Fase 1 punto 3 (anexo H28): tras la copia inicial, los archivos
nuevos NO se escriben directamente en el arbol espejo del cubo
sucio. Van al cubo de cuarentena.
---
Phase 1 point 3 (H28 annex): after the initial copy, new files are
NOT written directly into the dirty bucket mirror tree. They go to
the quarantine bucket.
"""

import logging
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import QUARANTINE_BUCKET_NAME
from uploader import upload_single_file_to_quarantine

logger = logging.getLogger(__name__)


class QuarantineEventHandler(FileSystemEventHandler):
    """Uploads newly created files to the quarantine bucket.
    ---
    Sube a cuarentena los archivos recien creados.
    """

    def __init__(self, client, selected_folder):
        super().__init__()
        self._client = client
        self._selected_folder = selected_folder

    def on_created(self, event):
        """Handle a file (or directory) creation event.
        ---
        Maneja un evento de creacion de archivo (o carpeta).
        """
        if event.is_directory:
            return
        # Run the upload on a separate thread so the observer
        # thread is never blocked waiting on network I/O.
        # ---
        # La subida se hace en un hilo aparte para no bloquear el
        # hilo del observador esperando I/O de red.
        upload_thread = threading.Thread(
            target=self._upload_new_file,
            args=(event.src_path,),
            daemon=True,
        )
        upload_thread.start()

    def _upload_new_file(self, absolute_file_path):
        try:
            upload_single_file_to_quarantine(
                self._client,
                QUARANTINE_BUCKET_NAME,
                self._selected_folder,
                absolute_file_path,
            )
        except OSError as error:
            # The file may still be mid-write (e.g. Explorer copy
            # in progress) — logged, not raised, watcher keeps
            # running.
            # ---
            # El archivo puede seguir escribiendose (ej. copia en
            # curso del Explorador) — se registra, no se relanza, el
            # vigilante sigue funcionando.
            logger.warning(
                "No se pudo subir %s a cuarentena todavia: %s",
                absolute_file_path,
                error,
            )


def start_watching(client, selected_folder):
    """Start an indefinite watcher over selected_folder.
    ---
    Arranca un vigilante indefinido sobre selected_folder.

    Returns
    -------
    watchdog.observers.Observer
        Running observer — call .stop() and .join() to shut it
        down cleanly.
        ---
        Observador en marcha — llamar a .stop() y .join() para
        detenerlo de forma ordenada.
    """
    event_handler = QuarantineEventHandler(client, selected_folder)
    observer = Observer()
    observer.schedule(event_handler, selected_folder, recursive=True)
    observer.start()
    logger.info("Vigilancia continua iniciada sobre %s", selected_folder)
    return observer
