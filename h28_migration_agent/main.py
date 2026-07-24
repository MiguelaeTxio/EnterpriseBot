# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/main.py
"""Entry point of the H28 migration agent (Windows tray app).
---
Punto de entrada del agente de migracion H28 (app de bandeja de
Windows).

Fase 1 punto 1 (anexo H28): la seleccion de carpetas es dinamica,
elegida desde esta interfaz en el momento de usarla — nunca una
lista fija en configuracion. Cada carpeta elegida se copia siempre
de forma recursiva y completa (decision verbatim de Miguel Angel,
S031).
---
Phase 1 point 1 (H28 annex): folder selection is dynamic, chosen
from this interface at the moment of use — never a fixed list in
configuration. Every chosen folder is always copied recursively and
completely (Miguel Angel's verbatim decision, S031).
"""

import logging
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import pystray
from PIL import Image, ImageDraw

from config import DIRTY_BUCKET_NAME, LOG_FILE_NAME
from gcs_client import MissingCredentialsError, build_client
from state import load_watched_folders, save_watched_folders
from uploader import upload_folder_recursive
from watcher import start_watching

logger = logging.getLogger(__name__)

# Folders being watched in this run, keyed by local path. Persisted
# to disk (state.py) so the agent resumes them automatically on the
# next restart — decision from Miguel Angel, S031.
# ---
# Carpetas vigiladas en esta ejecucion, indexadas por ruta local.
# Se persisten en disco (state.py) para que el agente las retome
# automaticamente en el siguiente reinicio — decision de Miguel
# Angel, S031.
_active_observers = {}


def _configure_logging():
    """Configure file logging, and console logging when available.
    ---
    Configura el log de archivo, y el de consola cuando esta
    disponible.

    Nota (S031): empaquetado con PyInstaller --windowed no da
    consola a la app — sys.stdout/sys.stderr quedan en None. Anadir
    un StreamHandler en ese caso hace petar el primer log.write().
    Se comprueba antes de anadirlo.
    ---
    Note (S031): PyInstaller --windowed packaging gives the app no
    console — sys.stdout/sys.stderr are None. Adding a
    StreamHandler in that case crashes on the first log.write().
    Checked before adding it.
    """
    log_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.argv[0])), LOG_FILE_NAME
    )
    handlers = [logging.FileHandler(log_path, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _build_tray_image():
    """Build a simple placeholder tray icon image.
    ---
    Construye una imagen de icono de bandeja de marcador de
    posicion.

    Nota (S031): icono provisional generado por codigo — pendiente
    de que Miguel Angel entregue un icono .ico definitivo para
    sustituirlo antes de empaquetar con PyInstaller.
    """
    image = Image.new("RGB", (64, 64), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), fill="#2b6cb0")
    draw.text((18, 24), "H28", fill="white")
    return image


def _select_folder_and_copy(icon, _menu_item):
    """Open the folder picker, then copy and watch it.
    ---
    Abre el selector de carpetas, y la copia y vigila.
    """
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected_folder = filedialog.askdirectory(
        title="Selecciona la carpeta a migrar (H28)",
        parent=root,
    )
    root.destroy()

    if not selected_folder:
        return
    selected_folder = os.path.normpath(selected_folder)

    if selected_folder in _active_observers:
        messagebox.showinfo(
            "Agente H28",
            f"Esta carpeta ya se esta vigilando:\n{selected_folder}",
        )
        return

    try:
        client = build_client()
    except MissingCredentialsError as error:
        messagebox.showerror("Agente H28", str(error))
        return

    icon.notify(f"Copiando {selected_folder}...", title="Agente H28")
    logger.info("Inicio de copia inicial: %s", selected_folder)

    def _log_progress(uploaded_count, total_count):
        logger.info(
            "Progreso copia %s: %d/%d",
            selected_folder,
            uploaded_count,
            total_count,
        )

    uploaded_count, failed_paths = upload_folder_recursive(
        client, DIRTY_BUCKET_NAME, selected_folder, _log_progress
    )

    if failed_paths:
        icon.notify(
            f"Copia terminada con {len(failed_paths)} fallos. "
            "Ver el log para el detalle.",
            title="Agente H28",
        )
    else:
        icon.notify(
            f"Copia completada: {uploaded_count} archivos.",
            title="Agente H28",
        )

    observer = start_watching(client, selected_folder)
    _active_observers[selected_folder] = observer
    save_watched_folders(_active_observers.keys())
    icon.notify(
        f"Vigilancia continua activa sobre:\n{selected_folder}",
        title="Agente H28",
    )


def _resume_watched_folders(icon):
    """Resume watching every folder persisted from a previous run.
    ---
    Retoma la vigilancia de cada carpeta persistida de una
    ejecución anterior.

    Called once, right after the tray icon becomes visible (pystray
    ``setup`` callback) — decision from Miguel Ángel (S031): "el
    agente tiene que recordar qué estaba haciendo y seguir
    haciéndolo".

    Known gap (documented, not solved in S031): this only resumes
    *watching* — it does not redo the initial bulk copy, and it does
    not scan for files that appeared while the agent was closed
    between runs. Only watchdog's live events (while the agent is
    running) reach the quarantine bucket.
    ---
    Hueco conocido (documentado, no resuelto en S031): esto solo
    retoma la *vigilancia* — no repite la copia inicial, y no
    escanea archivos que hayan aparecido mientras el agente estaba
    cerrado entre ejecuciones. Solo los eventos en vivo de watchdog
    (con el agente corriendo) llegan al cubo de cuarentena.
    """
    # pystray exige que, al sustituir el setup por defecto, este
    # mismo lo deje visible explicitamente -- si no, el icono nunca
    # aparece (verificado en la documentacion oficial de pystray).
    # ---
    # pystray requires that, when the default setup is replaced,
    # this one makes the icon visible itself -- otherwise it never
    # shows (verified against the official pystray documentation).
    icon.visible = True

    persisted_folders = load_watched_folders()
    if not persisted_folders:
        return

    missing_folders = [
        folder for folder in persisted_folders
        if not os.path.isdir(folder)
    ]
    valid_folders = [
        folder for folder in persisted_folders
        if os.path.isdir(folder)
    ]
    for missing_folder in missing_folders:
        logger.warning(
            "Carpeta persistida ya no existe, se descarta: %s",
            missing_folder,
        )

    if not valid_folders:
        save_watched_folders([])
        return

    try:
        client = build_client()
    except MissingCredentialsError as error:
        logger.error(
            "No se pudieron retomar %d carpetas persistidas: %s",
            len(valid_folders),
            error,
        )
        icon.notify(
            "No se pudo retomar la vigilancia de sesiones "
            "anteriores: falta la clave de la cuenta de servicio.",
            title="Agente H28",
        )
        return

    for folder in valid_folders:
        observer = start_watching(client, folder)
        _active_observers[folder] = observer
        logger.info("Vigilancia retomada sobre: %s", folder)

    if missing_folders:
        save_watched_folders(_active_observers.keys())

    icon.notify(
        f"Vigilancia retomada sobre {len(valid_folders)} "
        "carpeta(s) de la sesión anterior.",
        title="Agente H28",
    )


def _quit_agent(icon, _menu_item):
    """Stop every observer and exit the agent.
    ---
    Detiene todos los observadores y sale del agente.
    """
    logger.info("Cerrando el agente: deteniendo %d vigilantes.",
                len(_active_observers))
    for observer in _active_observers.values():
        observer.stop()
    for observer in _active_observers.values():
        observer.join()
    icon.stop()


def main():
    """Start the tray icon and block until the user exits.
    ---
    Arranca el icono de bandeja y bloquea hasta que el usuario
    salga.
    """
    _configure_logging()
    logger.info("Agente H28 arrancado.")

    menu = pystray.Menu(
        pystray.MenuItem(
            "Seleccionar carpeta y copiar", _select_folder_and_copy
        ),
        pystray.MenuItem("Salir", _quit_agent),
    )
    icon = pystray.Icon(
        "h28_migration_agent",
        _build_tray_image(),
        "EnterpriseBot — Agente de Migracion H28",
        menu=menu,
    )
    icon.run(setup=_resume_watched_folders)


if __name__ == "__main__":
    main()
