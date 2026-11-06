# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/onedrive_watchdog.py
"""Keep OneDrive syncing: detect a pause, restart it, alert (S146).
---
Vigilante de OneDrive (H24, S146). Miguel Angel: "OneDrive entra muchas
veces en pausa [...] ponerlo en marcha" -- con el agente, sin clics en
pantalla (funciona con la sesion de Windows bloqueada).

Como funciona, cada 5 minutos:

- Testigo: `_testigo_onedrive.txt` en la carpeta de las copias de la BD
  (fuera de las carpetas vigiladas). Se reescribe cada hora, solo si la
  version anterior ya subio.
- Estado: lo da Windows (Cloud Files API, `CfGetPlaceholderInfo` de
  CldApi.dll). Subido = el archivo es un "placeholder" de OneDrive con
  InSyncState IN_SYNC; un archivo nuevo que OneDrive aun no ha
  procesado no lo es.
- Si el testigo sigue sin subir 10 minutos despues de escribirlo,
  OneDrive esta parado: se reinicia (`OneDrive.exe /shutdown` y
  `/background`), una vez por testigo.
- Latido `onedrive_sync` al servidor mientras OneDrive sube (o mientras
  el testigo esta dentro de esos 10 minutos). Si deja de latir 15
  minutos, el servidor avisa por WhatsApp con las plantillas de agentes
  de sistema ya aprobadas, y otra vez cuando vuelve.
---
Every 5 minutes: a witness file in the backup folder, rewritten hourly
once uploaded; if it is still not in sync 10 minutes after writing,
OneDrive is restarted (once per witness). A `onedrive_sync` heartbeat is
sent while it syncs, so the server alerts by WhatsApp when it stops.
"""
import ctypes
import logging
import os
import subprocess
import threading
import time
from ctypes import wintypes

from heartbeat import send_heartbeat

logger = logging.getLogger(__name__)

AGENT_NAME = "onedrive_sync"
WITNESS_NAME = "_testigo_onedrive.txt"
CHECK_EVERY_SECONDS = 5 * 60
REWRITE_EVERY_SECONDS = 60 * 60
GRACE_SECONDS = 10 * 60
RESTART_WAIT_SECONDS = 15
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


CF_PLACEHOLDER_INFO_BASIC = 0
CF_IN_SYNC_STATE_IN_SYNC = 1
FILE_READ_ATTRIBUTES = 0x80
FILE_SHARE_ALL = 0x1 | 0x2 | 0x4
OPEN_EXISTING = 3
# HRESULT_FROM_WIN32(ERROR_NOT_A_CLOUD_FILE): archivo normal, que
# OneDrive todavia no ha convertido en placeholder (no ha subido).
HRESULT_NOT_A_CLOUD_FILE = 0x80070178
# HRESULT_FROM_WIN32(ERROR_MORE_DATA): la parte fija ya esta escrita.
HRESULT_MORE_DATA = 0x800700EA


class _PlaceholderBasicInfo(ctypes.Structure):
    """CF_PLACEHOLDER_BASIC_INFO (cfapi.h), fixed part.
    ---
    Parte fija de CF_PLACEHOLDER_BASIC_INFO.
    """

    _fields_ = [
        ("PinState", ctypes.c_int),
        ("InSyncState", ctypes.c_int),
        ("FileId", ctypes.c_longlong),
        ("SyncRootFileId", ctypes.c_longlong),
        ("FileIdentityLength", wintypes.ULONG),
    ]


def sync_state(path):
    """OneDrive state of one file: "al dia", "pendiente" or "sin subir".
    ---
    Estado de un archivo en OneDrive con CfGetPlaceholderInfo (Cloud
    Files API): placeholder con InSyncState = IN_SYNC -> "al dia";
    placeholder sin sincronizar -> "pendiente"; archivo normal que
    OneDrive aun no ha convertido -> "sin subir". Corregido en S146:
    la primera version usaba CfGetPlaceholderStateFromAttributeTag, que
    con solo atributos y reparse tag nunca puede saber IN_SYNC (en la
    prueba real daba siempre "sin subir" con OneDrive al dia).
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cldapi = ctypes.WinDLL("CldApi.dll")
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    cldapi.CfGetPlaceholderInfo.restype = ctypes.c_long
    cldapi.CfGetPlaceholderInfo.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD)]
    handle = kernel32.CreateFileW(
        path, FILE_READ_ATTRIBUTES, FILE_SHARE_ALL, None, OPEN_EXISTING,
        0, None)
    if handle in (None, INVALID_HANDLE_VALUE):
        raise OSError(ctypes.get_last_error(), "CreateFileW: %s" % path)
    try:
        buffer = ctypes.create_string_buffer(4096)
        returned = wintypes.DWORD(0)
        result = cldapi.CfGetPlaceholderInfo(
            handle, CF_PLACEHOLDER_INFO_BASIC, buffer, len(buffer),
            ctypes.byref(returned)) & 0xFFFFFFFF
    finally:
        kernel32.CloseHandle(handle)
    if result == HRESULT_NOT_A_CLOUD_FILE:
        return "sin subir"
    if result not in (0, HRESULT_MORE_DATA):
        raise OSError(result, "CfGetPlaceholderInfo: 0x%08X" % result)
    info = _PlaceholderBasicInfo.from_buffer_copy(
        buffer.raw[:ctypes.sizeof(_PlaceholderBasicInfo)])
    if info.InSyncState == CF_IN_SYNC_STATE_IN_SYNC:
        return "al dia"
    return "pendiente"


def _onedrive_exe():
    local = os.environ.get("LOCALAPPDATA", "")
    for candidate in (
            os.path.join(local, "Microsoft", "OneDrive", "OneDrive.exe"),
            r"C:\Program Files\Microsoft OneDrive\OneDrive.exe",
            r"C:\Program Files (x86)\Microsoft OneDrive\OneDrive.exe"):
        if candidate and os.path.isfile(candidate):
            return candidate
    return ""


def restart_onedrive():
    """Restart OneDrive in the background. Returns a text for the log.
    ---
    Reinicia OneDrive: `/shutdown`, espera y `/background` (sin ventana).
    """
    exe = _onedrive_exe()
    if not exe:
        return "no se encuentra OneDrive.exe"
    subprocess.run([exe, "/shutdown"], timeout=60, check=False)
    time.sleep(RESTART_WAIT_SECONDS)
    subprocess.Popen(
        [exe, "/background"], close_fds=True,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return "OneDrive reiniciado (%s)" % exe


class OneDriveWatchdog:
    """State of the witness between checks.
    ---
    Estado del testigo entre comprobaciones.
    """

    def __init__(self, folder_resolver, notify=None):
        self._folder_resolver = folder_resolver
        self._notify = notify
        self._restarted_for = None

    def check_once(self):
        """One check: rewrite, restart if stuck, heartbeat if syncing.
        ---
        Una comprobacion. Devuelve el texto de lo que ha hecho. La edad
        del testigo es la de su fecha de modificacion, asi que sobrevive
        a un reinicio del agente; se reinicia OneDrive una sola vez por
        version del testigo.
        """
        folder = self._folder_resolver()
        witness = os.path.join(folder, WITNESS_NAME)
        now = time.time()
        if not os.path.isfile(witness):
            self._write(witness)
            return "testigo creado"
        written = os.path.getmtime(witness)
        age = now - written
        state = sync_state(witness)
        if state == "al dia":
            send_heartbeat(AGENT_NAME)
            if age >= REWRITE_EVERY_SECONDS:
                self._write(witness)
            return "al dia"
        if age < GRACE_SECONDS:
            send_heartbeat(AGENT_NAME)
            return "testigo subiendo (%s)" % state
        if self._restarted_for != written:
            self._restarted_for = written
            text = restart_onedrive()
            logger.warning("OneDrive: testigo %s hace %d min; %s",
                           state, age // 60, text)
            if self._notify:
                self._notify("OneDrive parado: %s" % text)
            return text
        return "sigue parado tras reiniciarlo (%s; aviso por WhatsApp)" % (
            state)

    @staticmethod
    def _write(witness):
        with open(witness, "w", encoding="ascii") as handle:
            handle.write("Testigo del agente H28: %s\n" % time.strftime(
                "%Y-%m-%d %H:%M:%S"))


def start_watchdog_thread(folder_resolver, notify=None):
    """Start the OneDrive watchdog daemon thread.
    ---
    Arranca el hilo demonio del vigilante de OneDrive. Nunca es fatal:
    un fallo se registra y se reintenta en la siguiente vuelta.
    """
    watchdog = OneDriveWatchdog(folder_resolver, notify)
    stop_event = threading.Event()

    def _loop():
        last = None
        while not stop_event.is_set():
            try:
                text = watchdog.check_once()
            except Exception as error:  # noqa: BLE001 -- nunca fatal
                text = "fallo en la comprobacion: %s" % error
                if text != last:
                    logger.exception("OneDrive: %s", text)
            else:
                # Solo los cambios de estado, para no llenar el log
                # con un "al dia" cada 5 minutos.
                if text != last:
                    logger.info("OneDrive: %s", text)
            last = text
            stop_event.wait(CHECK_EVERY_SECONDS)

    threading.Thread(target=_loop, name="h28-onedrive", daemon=True).start()
    return stop_event
