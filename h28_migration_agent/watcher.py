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

from config import DIRTY_BUCKET_NAME
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
        # Se registra la RECEPCION del evento, no solo su resultado.
        # Sin esta linea, "no hay nada en el log" es ambiguo: no
        # distingue que watchdog no viera el archivo de que lo viera y
        # la subida fallara en silencio. La diferencia es real y ya se
        # ha dado -- los 22 archivos de LAVADO NAVARRO llegaron por
        # sincronizacion de OneDrive y watchdog no reacciono (anexo
        # H28, S035).
        # ---
        # The RECEIPT of the event is logged, not just its outcome.
        # Without this line, "nothing in the log" is ambiguous: it
        # cannot tell watchdog never seeing the file from watchdog
        # seeing it and the upload failing silently. That difference
        # is real and has already happened.
        logger.info(
            "Vigilante: detectado archivo nuevo en %s", event.src_path,
        )
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
        """Upload one detected file, never letting the thread die mute.

        ---
        Sube un archivo detectado, sin dejar que el hilo muera mudo.

        Se captura `Exception` y no solo `OSError` (anexo H28, defecto
        4 de S035): esto corre en un hilo demonio de una aplicacion
        compilada con `--windowed`, sin consola donde imprimir. Una
        excepcion del SDK de GCS, de la capa de red o de
        autenticacion no es `OSError`, y hasta ahora desaparecia sin
        dejar rastro alguno -- ni en el log, ni en pantalla, ni en
        ningun sitio. El hilo moria y nadie se enteraba.

        No se captura `BaseException` a proposito: `KeyboardInterrupt`
        y `SystemExit` deben propagarse para que el agente pueda
        cerrarse de forma ordenada.

        Tampoco se reintenta aqui. Si la subida falla, la
        reconciliacion es la red de seguridad y la recogera --
        anadir reintentos en el vigilante seria una decision de
        diseno que nadie ha tomado.
        ---
        `Exception` is caught rather than only `OSError` (H28 annex,
        S035 defect 4): this runs on a daemon thread of a
        `--windowed` build with no console. A GCS SDK, network or
        auth error is not an `OSError` and used to vanish without a
        trace. `BaseException` is deliberately not caught, so
        `KeyboardInterrupt` and `SystemExit` still propagate.
        """
        try:
            blob_name = upload_single_file_to_quarantine(
                self._client,
                DIRTY_BUCKET_NAME,
                self._selected_folder,
                absolute_file_path,
            )
        except OSError as error:
            # El archivo puede seguir escribiendose (ej. copia en
            # curso del Explorador) — se registra, no se relanza, el
            # vigilante sigue funcionando.
            # ---
            # The file may still be mid-write (e.g. Explorer copy in
            # progress) — logged, not raised, watcher keeps running.
            logger.warning(
                "Vigilante: no se pudo subir %s a cuarentena "
                "todavia: %s",
                absolute_file_path,
                error,
            )
        except Exception as error:  # noqa: BLE001 -- ver docstring
            logger.exception(
                "Vigilante: fallo inesperado al subir %s a "
                "cuarentena: %s",
                absolute_file_path,
                error,
            )
        else:
            logger.info(
                "Vigilante: %s subido a cuarentena como %s",
                absolute_file_path,
                blob_name,
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
