# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/mail_reader_agent/main.py
"""Outlook mail reader agent: tray app for Yolanda's PC (S156).
---
Agente lector de correos de Outlook: aplicacion de bandeja para el PC
de Yolanda (H31, S156). Se prepara y se prueba primero en el PC de
Miguel Angel.

- La primera vez pide la carpeta de Outlook con el selector del propio
  Outlook (y se puede cambiar desde el menu "Elegir carpeta de
  Outlook"); se recuerda en settings.json.
- Cada minuto sube al cubo los correos nuevos de esa carpeta
  (outlook_reader.py) sin marcarlos como leidos ni moverlos.
- Una sola instancia (mutex de Windows, como los demas agentes).
"""
import ctypes
import json
import logging
import logging.handlers
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import pystray
import pythoncom
from google.cloud import storage
from PIL import Image, ImageDraw

from config import (
    APP_NAME, LOG_BACKUP_COUNT, LOG_FILE_NAME, LOG_MAX_BYTES,
    LOOKBACK_DAYS, SCAN_INTERVAL_SECONDS, SETTINGS_FILE_NAME, get_data_dir,
    get_key_path,
)
from outlook_reader import pick_folder, scan_and_upload

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_wake_event = threading.Event()
_tk_root = None
_recent_events = []
_MAX_RECENT_EVENTS = 50

_SINGLE_INSTANCE_MUTEX_NAME = (
    "Global\\EnterpriseBot_MailReaderAgent_SingleInstance"
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


def load_settings():
    """Chosen Outlook folder ({} if none).
    ---
    Carpeta de Outlook elegida ({} si no hay).
    """
    try:
        with open(_settings_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not data.get("entry_id"):
        return {}
    return data


def save_settings(settings):
    with open(_settings_path(), "w", encoding="utf-8") as handle:
        json.dump(settings, handle, ensure_ascii=False)


def _log_event(text):
    """Record an event for the "Estado" window and the log.
    ---
    Anota un suceso para la ventana de estado y el log.
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
    COM se inicia en este hilo: Outlook se usa desde aqui.
    """
    pythoncom.CoInitialize()
    try:
        while not _stop_event.is_set():
            settings = load_settings()
            if settings:
                try:
                    uploaded = scan_and_upload(
                        _build_client(), settings, _log_event)
                    if uploaded:
                        icon.notify(
                            "%d correo(s) leídos y enviados." % uploaded,
                            title=APP_NAME,
                        )
                except Exception as error:  # noqa: BLE001
                    logger.exception("Fallo en la revision")
                    _log_event("Error en la revisión: %s" % error)
            _wake_event.wait(SCAN_INTERVAL_SECONDS)
            _wake_event.clear()
    finally:
        pythoncom.CoUninitialize()


def _choose_folder_now():
    """Ask for the Outlook folder with Outlook's picker and save it.
    ---
    Pide la carpeta con el selector de Outlook y la guarda.
    """
    pythoncom.CoInitialize()
    try:
        chosen = pick_folder()
    finally:
        pythoncom.CoUninitialize()
    if chosen:
        save_settings(chosen)
        _log_event("Carpeta de Outlook: %s" % chosen["path"])
    return chosen


def _choose_folder(icon, _item=None):
    chosen = _choose_folder_now()
    if chosen:
        icon.notify("Leyendo:\n%s" % chosen["path"], title=APP_NAME)
        _wake_event.set()


def _read_now(_icon, _item):
    _wake_event.set()


def _show_status(_icon, _item):
    root = _get_tk_root()
    folder = load_settings().get("path") or "(ninguna, elige una en el menú)"
    recent = "\n".join(_recent_events[-15:]) or "Nada todavía."
    messagebox.showinfo(
        APP_NAME,
        "Carpeta de Outlook:\n%s\n(se miran los correos de los últimos "
        "%d días; nunca se marcan como leídos)\n\nÚltimos sucesos:\n%s"
        % (folder, LOOKBACK_DAYS, recent),
        parent=root,
    )


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
    Antes de arrancar la bandeja: avisa si falta la clave y, si no hay
    carpeta de Outlook elegida, la pide.
    """
    root = _get_tk_root()
    if not os.path.isfile(get_key_path()):
        messagebox.showerror(
            APP_NAME,
            "Falta la clave de la cuenta de servicio en:\n%s"
            % get_key_path(),
            parent=root,
        )
    if not load_settings():
        _choose_folder_now()


def _tray_image():
    image = Image.new("RGB", (64, 64), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), fill="#2b6cb0")
    draw.text((14, 24), "MAIL", fill="white")
    return image


def main():
    _configure_logging()
    logger.info("Agente de correos arrancado.")
    _first_run_checks()
    menu = pystray.Menu(
        pystray.MenuItem("Elegir carpeta de Outlook", _choose_folder),
        pystray.MenuItem("Leer ahora", _read_now),
        pystray.MenuItem("Estado y últimos correos", _show_status),
        pystray.MenuItem("Salir", _quit),
    )
    pystray.Icon(
        "mail_reader_agent", _tray_image(),
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
            None, "El agente de correos ya está en marcha.", APP_NAME,
            0x40,
        )
        sys.exit(0)
    main()
