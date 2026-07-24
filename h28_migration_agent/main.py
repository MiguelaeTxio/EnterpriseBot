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
from uploader import upload_folder_recursive
from watcher import start_watching

logger = logging.getLogger(__name__)

# Folders already being watched in this run, keyed by local path.
# Not persisted across restarts yet — pendiente de confirmar con
# Miguel Angel en la sesion siguiente de H28 si hace falta
# persistencia entre reinicios del agente.
# ---
# Carpetas ya vigiladas en esta ejecucion, indexadas por ruta local.
# No se persisten entre reinicios todavia — pendiente de confirmar
# con Miguel Angel en la sesion siguiente de H28 si hace falta
# persistencia entre reinicios del agente.
_active_observers = {}


def _configure_logging():
    """Configure console and file logging for the agent.
    ---
    Configura el log de consola y de archivo del agente.
    """
    log_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.argv[0])), LOG_FILE_NAME
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
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
    icon.notify(
        f"Vigilancia continua activa sobre:\n{selected_folder}",
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
    icon.run()


if __name__ == "__main__":
    main()
