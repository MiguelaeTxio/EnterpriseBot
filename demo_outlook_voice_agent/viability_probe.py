"""
Minimal viability probe for the Outlook voice demo agent (S142).

Checks, one by one and independently, the four building blocks the
real agent needs on Miguel Angel's Windows PC: (1) finding the
Outlook window and its maximised state, (2) recording from the
microphone, (3) transcribing that recording with Gemini on Vertex AI,
and (4) locating the "new mail" button on a screenshot with Gemini
vision, moving the cursor onto it without clicking. Nothing is sent.

---

Prueba minima de viabilidad del agente demo de voz para Outlook (S142).

Comprueba, uno a uno y por separado, los cuatro bloques que necesita
el agente real en el PC Windows de Miguel Angel: (1) encontrar la
ventana de Outlook y si esta maximizada, (2) grabar del microfono,
(3) transcribir esa grabacion con Gemini en Vertex AI, y (4) localizar
el boton de correo nuevo en una captura con la vision de Gemini,
llevando el cursor encima sin hacer clic. No se envia nada.
"""

import ctypes
import json
import os
import sys
import time
import wave
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / 'viability_probe.log'
WAV_PATH = BASE_DIR / 'viability_probe.wav'
PNG_PATH = BASE_DIR / 'viability_probe.png'

GEMINI_MODEL = 'gemini-3.5-flash'
GEMINI_LOCATION = 'global'
RECORD_SECONDS = 6
SAMPLE_RATE = 16000
SCREENSHOT_COUNTDOWN = 6
OUTLOOK_EXES = ('outlook.exe', 'olk.exe')
DEFAULT_KEY_PATH = (
    Path(os.environ.get('LOCALAPPDATA', ''))
    / 'EnterpriseBot' / 'H28MigrationAgent' / 'service_account_key.json'
)


def _log(message):
    """
    Writes a timestamped line to screen and to the probe log file.

    ---

    Escribe una linea con hora en pantalla y en el log de la prueba.
    """
    line = '[%s] %s' % (datetime.now().strftime('%H:%M:%S'), message)
    print(line, flush=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as handle:
        handle.write(line + '\n')
        handle.flush()


def _log_plain(message):
    """
    Writes a line without timestamp to screen and log (final summary).

    ---

    Escribe una linea sin hora en pantalla y log (resumen final).
    """
    print(message, flush=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as handle:
        handle.write(message + '\n')
        handle.flush()


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


def _set_dpi_awareness():
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


def find_outlook_windows():
    """
    Lists visible top-level windows owned by classic or new Outlook.

    ---

    Lista las ventanas visibles de primer nivel de Outlook clasico o
    del nuevo Outlook.
    """
    user32 = ctypes.windll.user32
    found = []
    enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_exe(pid.value)
        if exe in OUTLOOK_EXES:
            found.append({
                'hwnd': hwnd,
                'title': title.value,
                'exe': exe,
                'maximized': bool(user32.IsZoomed(hwnd)),
            })
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    return found


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


def step_windows():
    """
    Step 1: detect the Outlook window and whether it is maximised.

    ---

    Paso 1: detectar la ventana de Outlook y si esta maximizada.
    """
    _log('PASO 1/4 -- Buscando ventanas de Outlook (OUTLOOK.EXE / olk.exe)')
    windows = find_outlook_windows()
    if not windows:
        _log('  Ninguna ventana de Outlook visible.')
        return False, 'Outlook no encontrado', None
    for index, item in enumerate(windows, start=1):
        _log('  Ventana %d: exe=%s maximizada=%s titulo="%s"' % (
            index, item['exe'], 'SI' if item['maximized'] else 'NO',
            item['title']))
    maximized = [item for item in windows if item['maximized']]
    if maximized:
        return True, '%s maximizado' % maximized[0]['exe'], maximized[0]
    return False, 'Outlook visible pero no maximizado', windows[0]


def step_record():
    """
    Step 2: record a few seconds from the default microphone.

    ---

    Paso 2: grabar unos segundos del microfono por defecto.
    """
    import numpy
    import sounddevice

    _log('PASO 2/4 -- Grabacion de microfono')
    device = sounddevice.query_devices(kind='input')
    _log('  Microfono por defecto: %s' % device['name'])
    for remaining in (3, 2, 1):
        _log('  Empieza a hablar en %d...' % remaining)
        time.sleep(1)
    _log('  GRABANDO %d segundos: di una frase corta en voz alta.'
         % RECORD_SECONDS)
    audio = sounddevice.rec(
        int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE,
        channels=1, dtype='int16')
    sounddevice.wait()
    peak = int(numpy.abs(audio).max())
    with wave.open(str(WAV_PATH), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(audio.tobytes())
    _log('  Grabacion guardada en %s (pico=%d de 32767)' % (WAV_PATH, peak))
    if peak < 300:
        return False, 'grabacion casi muda (pico %d)' % peak
    return True, 'pico %d' % peak


def build_client():
    """
    Builds a Vertex AI Gemini client from the local service key.

    ---

    Construye un cliente Gemini de Vertex AI con la clave local.
    """
    from google import genai
    from google.genai import types

    key_path = Path(os.environ.get('H28_AGENT_KEY_PATH', DEFAULT_KEY_PATH))
    _log('  Clave de servicio: %s' % key_path)
    if not key_path.is_file():
        raise FileNotFoundError('no existe la clave %s' % key_path)
    with open(key_path, encoding='utf-8') as handle:
        key_data = json.load(handle)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_path)
    _log('  Proyecto: %s | cuenta: %s' % (
        key_data.get('project_id'), key_data.get('client_email')))
    return genai.Client(
        vertexai=True,
        project=key_data.get('project_id'),
        location=GEMINI_LOCATION,
        http_options=types.HttpOptions(api_version='v1'),
    )


def step_transcribe(client):
    """
    Step 3: transcribe the recording with Gemini.

    ---

    Paso 3: transcribir la grabacion con Gemini.
    """
    from google.genai import types

    _log('PASO 3/4 -- Transcripcion con %s' % GEMINI_MODEL)
    audio = WAV_PATH.read_bytes()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=audio, mime_type='audio/wav'),
            'Transcribe literalmente este audio en castellano. Devuelve '
            'solo el texto transcrito, sin comentarios. Si no se oye '
            'voz, devuelve exactamente: (sin voz)',
        ],
    )
    text = (response.text or '').strip()
    _log('  Transcripcion: "%s"' % text)
    if not text or text == '(sin voz)':
        return False, 'transcripcion vacia'
    return True, 'texto recibido (%d caracteres)' % len(text)


def step_vision(client, outlook):
    """
    Step 4: screenshot the Outlook monitor, ask Gemini where the
    new-mail button is, and move the cursor there without clicking.

    ---

    Paso 4: capturar el monitor de Outlook, preguntar a Gemini donde
    esta el boton de correo nuevo y llevar alli el cursor sin clic.
    """
    import mss
    from google.genai import types
    from PIL import Image

    _log('PASO 4/4 -- Vision: localizar el boton de correo nuevo')
    for remaining in range(SCREENSHOT_COUNTDOWN, 0, -1):
        _log('  Pon Outlook maximizado delante de todo: captura en %d...'
             % remaining)
        time.sleep(1)
    if outlook:
        left, top, width, height = monitor_rect_for(outlook['hwnd'])
    else:
        left, top, width, height = 0, 0, 0, 0
    with mss.mss() as grabber:
        if width and height:
            region = {'left': left, 'top': top,
                      'width': width, 'height': height}
        else:
            region = grabber.monitors[1]
            left, top = region['left'], region['top']
            width, height = region['width'], region['height']
        shot = grabber.grab(region)
    image = Image.frombytes('RGB', shot.size, shot.rgb)
    image.save(PNG_PATH)
    _log('  Captura %dx%d guardada en %s' % (width, height, PNG_PATH))
    schema = {
        'type': 'OBJECT',
        'properties': {
            'found': {'type': 'BOOLEAN'},
            'label': {'type': 'STRING'},
            'box_2d': {'type': 'ARRAY', 'items': {'type': 'INTEGER'}},
        },
        'required': ['found'],
    }
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(
                data=PNG_PATH.read_bytes(), mime_type='image/png'),
            'Esta es una captura de pantalla de Microsoft Outlook. '
            'Localiza el boton que crea un correo nuevo (suele decir '
            '"Correo nuevo", "Nuevo correo", "Nuevo mensaje" o "New '
            'mail"). Devuelve found, el texto visible del boton en '
            'label y su caja en box_2d como [ymin, xmin, ymax, xmax] '
            'normalizada de 0 a 1000.',
        ],
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=schema,
        ),
    )
    result = json.loads(response.text)
    _log('  Respuesta de Gemini: %s' % json.dumps(result, ensure_ascii=False))
    box = result.get('box_2d') or []
    if not result.get('found') or len(box) != 4:
        return False, 'boton no localizado'
    center_x = left + int((box[1] + box[3]) / 2 / 1000 * width)
    center_y = top + int((box[0] + box[2]) / 2 / 1000 * height)
    ctypes.windll.user32.SetCursorPos(center_x, center_y)
    _log('  Cursor llevado a (%d, %d) SIN hacer clic: comprueba que esta '
         'encima de "%s".' % (center_x, center_y, result.get('label')))
    return True, 'boton "%s" en (%d, %d)' % (
        result.get('label'), center_x, center_y)


def main():
    """
    Runs the four probe steps and prints an OK/FAILED summary.

    ---

    Ejecuta los cuatro pasos y muestra un resumen OK/FALLO.
    """
    if sys.platform != 'win32':
        print('Esta prueba solo funciona en Windows.', flush=True)
        return 1
    _log('=== PRUEBA DE VIABILIDAD -- agente demo de voz para Outlook ===')
    _log('DPI: %s' % _set_dpi_awareness())
    results = []
    outlook = None
    client = None
    detail_client = 'sin cliente'
    try:
        ok, detail, outlook = step_windows()
    except Exception as exc:  # noqa: BLE001 -- probe reports, never stops
        ok, detail = False, 'error: %r' % exc
    results.append(('1. Ventana de Outlook maximizada', ok, detail))
    try:
        ok, detail = step_record()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, 'error: %r' % exc
    results.append(('2. Grabacion de microfono', ok, detail))
    try:
        _log('Conectando con Vertex AI')
        client = build_client()
    except Exception as exc:  # noqa: BLE001
        _log('  ERROR creando el cliente: %r' % exc)
        detail_client = 'error: %r' % exc
    if client and WAV_PATH.is_file():
        try:
            ok, detail = step_transcribe(client)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, 'error: %r' % exc
    elif client:
        ok, detail = False, 'no hay grabacion que transcribir'
    else:
        ok, detail = False, detail_client
    results.append(('3. Transcripcion con Gemini', ok, detail))
    if client:
        try:
            ok, detail = step_vision(client, outlook)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, 'error: %r' % exc
    else:
        ok, detail = False, detail_client
    results.append(('4. Vision y posicion del boton', ok, detail))
    _log_plain('')
    _log_plain('=== RESUMEN ===')
    for name, ok, detail in results:
        _log_plain('%s: %s -- %s' % (name, 'OK' if ok else 'FALLO', detail))
    _log_plain('Log completo: %s' % LOG_PATH)
    return 0 if all(item[1] for item in results) else 2


if __name__ == '__main__':
    sys.exit(main())
