# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/invoice_upload_agent/main.py
"""Supplier invoice upload agent: tray app for Ani's PC (S151).
---
Agente de subida de facturas de proveedor: aplicacion de bandeja para
el PC de Ani (H28, S151, sesion invasora).

Miguel Angel: "crear un agente analogo al H28 que vigile la carpeta que
Ani le indique y que este suba las facturas al cubo, a una carpeta de
Facturacion Proveedores". Lo hace asi:

- La primera vez pide la carpeta a vigilar (y se puede cambiar desde el
  menu "Elegir carpeta de facturas"); se recuerda en settings.json.
- Cada minuto sube al cubo, a FACTURACION PROVEEDORES/FACTURAS NUEVAS,
  las facturas (PDF o imagen) de esa carpeta que todavia no esten
  (scanner.py). El servidor las indexa, las procesa y las pasa a
  FACTURAS PROCESADAS: el agente no hace nada mas.
- Nunca borra ni mueve nada de la carpeta de Ani.
- Una sola instancia (mutex de Windows, como el H28, incidente S66).
"""
import ctypes
import json
import logging
import logging.handlers
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import pystray
from google.cloud import storage
from PIL import Image, ImageDraw

from config import (
    APP_NAME, LOG_BACKUP_COUNT, LOG_FILE_NAME, LOG_MAX_BYTES,
    SCAN_INTERVAL_SECONDS, SETTINGS_FILE_NAME, get_data_dir, get_key_path,
)
from scanner import scan_and_upload

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_wake_event = threading.Event()
_tk_root = None
_recent_events = []
_MAX_RECENT_EVENTS = 50

_SINGLE_INSTANCE_MUTEX_NAME = (
    "Global\\EnterpriseBot_InvoiceUploadAgent_SingleInstance"
)
_ERROR_ALREADY_EXISTS = 183


def _configure_logging():
    """Rotating log file in the data folder (and console if any).
    ---
    Log rotativo en la carpeta de datos (y en consola si la hay: con
    --windowed no hay, y un StreamHandler sin consola revienta).
    """
    handlers = [logging.handlers.RotatingFileHandler(
        os.path.join(get_data_dir(), LOG_FILE_NAME),
        maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _get_tk_root():
    """Single hidden Tk root (same reason as the H28 agent, S035).
    ---
    Raiz Tk unica y oculta (mismo motivo que en el agente H28, S035:
    sin raiz viva, Tkinter fabrica ventanas vacias que no se cierran).
    """
    global _tk_root
    if _tk_root is not None:
        try:
            _tk_root.winfo_exists()
            return _tk_root
        except tk.TclError:
            _tk_root = None
    _tk_root = tk.Tk()
    _tk_root.withdraw()
    _tk_root.attributes("-topmost", True)
    return _tk_root


def _settings_path():
    return os.path.join(get_data_dir(), SETTINGS_FILE_NAME)


def load_folder():
    """Watched folder from settings.json ("" if none or missing).
    ---
    Carpeta vigilada guardada ("" si no hay o ya no existe).
    """
    try:
        with open(_settings_path(), "r", encoding="utf-8") as handle:
            folder = json.load(handle).get("folder", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return folder if folder and os.path.isdir(folder) else ""


def save_folder(folder):
    with open(_settings_path(), "w", encoding="utf-8") as handle:
        json.dump({"folder": folder}, handle, ensure_ascii=False)


def _log_event(text):
    """Record an event for the "Ultimas subidas" window and the log.
    ---
    Anota un suceso para la ventana "Ultimas subidas" y el log.
    """
    logger.info(text)
    _recent_events.append(text)
    del _recent_events[:-_MAX_RECENT_EVENTS]


def _build_client():
    key_path = get_key_path()
    if not os.path.isfile(key_path):
        raise FileNotFoundError(
            "No se encuentra la clave de la cuenta de servicio en:\n%s"
            % key_path
        )
    return storage.Client.from_service_account_json(key_path)


def _scan_loop(icon):
    """Background thread: one review per minute (or on demand).
    ---
    Hilo de fondo: una revision por minuto (o al pedirla en el menu).
    """
    while not _stop_event.is_set():
        folder = load_folder()
        if folder:
            try:
                uploaded = scan_and_upload(_build_client(), folder, _log_event)
                if uploaded:
                    icon.notify(
                        "%d factura(s) subidas para procesar." % uploaded,
                        title=APP_NAME,
                    )
            except Exception as error:  # noqa: BLE001
                logger.exception("Fallo en la revision")
                _log_event("Error en la revision: %s" % error)
        _wake_event.wait(SCAN_INTERVAL_SECONDS)
        _wake_event.clear()


def _choose_folder(icon, _item=None):
    """Ask Ani for the folder to watch.
    ---
    Pide a Ani la carpeta a vigilar y la guarda.
    """
    root = _get_tk_root()
    folder = filedialog.askdirectory(
        title="Elige la carpeta de facturas a vigilar", parent=root,
    )
    if not folder:
        return
    folder = os.path.normpath(folder)
    save_folder(folder)
    _log_event("Carpeta vigilada: %s" % folder)
    icon.notify("Vigilando:\n%s" % folder, title=APP_NAME)
    _wake_event.set()


def _upload_now(_icon, _item):
    _wake_event.set()


def _show_status(_icon, _item):
    root = _get_tk_root()
    folder = load_folder() or "(ninguna, elige una en el menú)"
    recent = "\n".join(_recent_events[-15:]) or "Nada todavía."
    messagebox.showinfo(
        APP_NAME,
        "Carpeta vigilada:\n%s\n\nÚltimos sucesos:\n%s" % (folder, recent),
        parent=root,
    )


def _open_folder(_icon, _item):
    folder = load_folder()
    if folder:
        os.startfile(folder)


def _quit(icon, _item):
    _stop_event.set()
    _wake_event.set()
    icon.stop()


def _setup(icon):
    """Show the icon and start the periodic review.
    ---
    Muestra el icono y arranca la revision periodica.
    """
    icon.visible = True
    threading.Thread(target=_scan_loop, args=(icon,), daemon=True).start()


def _first_run_checks():
    """Key present and a folder chosen, before the tray starts.
    ---
    Antes de arrancar la bandeja, en el hilo principal (el mismo en el
    que pystray ejecuta los menus en Windows, para no usar Tk desde dos
    hilos): avisa si falta la clave y, si no hay carpeta, la pide.
    """
    root = _get_tk_root()
    if not os.path.isfile(get_key_path()):
        messagebox.showerror(
            APP_NAME,
            "Falta la clave de la cuenta de servicio en:\n%s"
            % get_key_path(),
            parent=root,
        )
    if not load_folder():
        folder = filedialog.askdirectory(
            title="Elige la carpeta de facturas a vigilar", parent=root,
        )
        if folder:
            save_folder(os.path.normpath(folder))
            _log_event("Carpeta vigilada: %s" % os.path.normpath(folder))


def _tray_image():
    image = Image.new("RGB", (64, 64), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), fill="#2f855a")
    draw.text((16, 24), "FAC", fill="white")
    return image


def main():
    _configure_logging()
    logger.info("Agente de facturas arrancado.")
    _first_run_checks()
    menu = pystray.Menu(
        pystray.MenuItem("Elegir carpeta de facturas", _choose_folder),
        pystray.MenuItem("Abrir carpeta vigilada", _open_folder),
        pystray.MenuItem("Subir ahora", _upload_now),
        pystray.MenuItem("Estado y últimas subidas", _show_status),
        pystray.MenuItem("Salir", _quit),
    )
    pystray.Icon(
        "invoice_upload_agent", _tray_image(),
        "EnterpriseBot — %s" % APP_NAME, menu=menu,
    ).run(setup=_setup)


def _acquire_single_instance_lock():
    mutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, _SINGLE_INSTANCE_MUTEX_NAME,
    )
    if ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        return None
    return mutex


if __name__ == "__main__":
    _instance_lock = _acquire_single_instance_lock()
    if _instance_lock is None:
        ctypes.windll.user32.MessageBoxW(
            None, "El agente de facturas ya está en marcha.", APP_NAME, 0x40,
        )
        sys.exit(0)
    main()
