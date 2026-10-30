"""
Windows desktop helpers for the demo agent: Outlook window detection,
monitor geometry, screenshots and synthetic mouse and keyboard input
(SendInput), all through ctypes.

---

Utilidades de escritorio Windows del agente demo: deteccion de la
ventana de Outlook, geometria de monitores, capturas y entrada
sintetica de raton y teclado (SendInput), todo por ctypes.
"""

import ctypes
import time
from ctypes import wintypes
from pathlib import Path

from common import OUTLOOK_EXES

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D


class _Rect(ctypes.Structure):
    """
    Win32 RECT structure.

    ---

    Estructura RECT de Win32.
    """

    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long),
    ]


class _MonitorInfo(ctypes.Structure):
    """
    Win32 MONITORINFO structure.

    ---

    Estructura MONITORINFO de Win32.
    """

    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('rcMonitor', _Rect),
        ('rcWork', _Rect),
        ('dwFlags', wintypes.DWORD),
    ]


class _MouseInput(ctypes.Structure):
    """
    Win32 MOUSEINPUT structure.

    ---

    Estructura MOUSEINPUT de Win32.
    """

    _fields_ = [
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_size_t),
    ]


class _KeybdInput(ctypes.Structure):
    """
    Win32 KEYBDINPUT structure.

    ---

    Estructura KEYBDINPUT de Win32.
    """

    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_size_t),
    ]


class _HardwareInput(ctypes.Structure):
    """
    Win32 HARDWAREINPUT structure.

    ---

    Estructura HARDWAREINPUT de Win32.
    """

    _fields_ = [
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD),
    ]


class _InputUnion(ctypes.Union):
    """
    Union inside the Win32 INPUT structure.

    ---

    Union dentro de la estructura INPUT de Win32.
    """

    _fields_ = [
        ('mi', _MouseInput),
        ('ki', _KeybdInput),
        ('hi', _HardwareInput),
    ]


class _Input(ctypes.Structure):
    """
    Win32 INPUT structure.

    ---

    Estructura INPUT de Win32.
    """

    _fields_ = [('type', wintypes.DWORD), ('union', _InputUnion)]


def set_dpi_awareness():
    """
    Makes the process per-monitor DPI aware so that screenshot pixels
    and cursor coordinates share the same physical scale.

    ---

    Hace el proceso consciente del DPI por monitor para que los pixeles
    de la captura y las coordenadas del cursor compartan escala fisica.
    """
    try:
        ok = ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4))
        if ok:
            return 'per-monitor v2'
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return 'per-monitor'
    except (AttributeError, OSError):
        return 'no aplicado'


def _process_exe(pid):
    """
    Returns the lower-case executable name of a process id.

    ---

    Devuelve el nombre del ejecutable, en minusculas, de un PID.
    """
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ''
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name.lower()
        return ''
    finally:
        kernel32.CloseHandle(handle)


def window_info(hwnd):
    """
    Returns title and executable of a window handle.

    ---

    Devuelve titulo y ejecutable de un manejador de ventana.
    """
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return {'hwnd': hwnd, 'title': title.value, 'exe': _process_exe(pid.value)}


def find_maximized_outlook():
    """
    Returns the first visible, maximised Outlook window (classic or
    new Outlook), or None.

    ---

    Devuelve la primera ventana visible y maximizada de Outlook
    (clasico o nuevo), o None.
    """
    user32 = ctypes.windll.user32
    found = []
    enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or not user32.IsZoomed(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        info = window_info(hwnd)
        if info['exe'] in OUTLOOK_EXES:
            found.append(info)
            return False
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    return found[0] if found else None


def foreground_window():
    """
    Returns title and executable of the current foreground window.

    ---

    Devuelve titulo y ejecutable de la ventana en primer plano.
    """
    return window_info(ctypes.windll.user32.GetForegroundWindow())


def monitor_rect_for(hwnd):
    """
    Returns (left, top, width, height) of the monitor holding a window.

    ---

    Devuelve (izquierda, arriba, ancho, alto) del monitor de la ventana.
    """
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    monitor = user32.MonitorFromWindow(hwnd, 2)
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info))
    rect = info.rcMonitor
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def screenshot(region, path):
    """
    Saves a PNG of a (left, top, width, height) screen region.

    ---

    Guarda un PNG de una region de pantalla (izq., arriba, ancho, alto).
    """
    import mss
    from PIL import Image

    left, top, width, height = region
    with mss.mss() as grabber:
        shot = grabber.grab(
            {'left': left, 'top': top, 'width': width, 'height': height})
    Image.frombytes('RGB', shot.size, shot.rgb).save(path)
    return path


def _send(inputs):
    """
    Sends a list of INPUT structures with SendInput.

    ---

    Envia una lista de estructuras INPUT con SendInput.
    """
    array = (_Input * len(inputs))(*inputs)
    ctypes.windll.user32.SendInput(
        len(inputs), array, ctypes.sizeof(_Input))


def click(x_pos, y_pos):
    """
    Moves the cursor to physical screen coordinates and left-clicks.

    ---

    Lleva el cursor a coordenadas fisicas de pantalla y hace clic
    izquierdo.
    """
    ctypes.windll.user32.SetCursorPos(x_pos, y_pos)
    time.sleep(0.15)
    down = _Input(type=INPUT_MOUSE)
    down.union.mi = _MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0)
    up = _Input(type=INPUT_MOUSE)
    up.union.mi = _MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0)
    _send([down, up])


def _key_event(vk, scan, flags):
    """
    Builds one keyboard INPUT structure.

    ---

    Construye una estructura INPUT de teclado.
    """
    event = _Input(type=INPUT_KEYBOARD)
    event.union.ki = _KeybdInput(vk, scan, flags, 0, 0)
    return event


def type_text(text):
    """
    Types text as Unicode key events (accents included); line breaks
    are sent as the Enter key.

    ---

    Escribe texto como pulsaciones Unicode (con tildes); los saltos de
    linea se envian como la tecla Intro.
    """
    for char in text:
        if char == '\n':
            _send([_key_event(VK_RETURN, 0, 0),
                   _key_event(VK_RETURN, 0, KEYEVENTF_KEYUP)])
        else:
            data = char.encode('utf-16-le')
            for index in range(0, len(data), 2):
                unit = int.from_bytes(data[index:index + 2], 'little')
                _send([
                    _key_event(0, unit, KEYEVENTF_UNICODE),
                    _key_event(0, unit,
                               KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
                ])
        time.sleep(0.01)
