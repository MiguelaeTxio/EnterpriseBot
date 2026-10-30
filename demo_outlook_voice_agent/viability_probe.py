"""
Minimal viability probe for the Outlook voice demo agent (S142).

Follows the real agent flow: it watches the screen and does nothing
until Outlook goes from not maximised to maximised. Only then it shows
a modal with start and stop recording buttons. When recording stops,
it transcribes the message with Gemini on Vertex AI and, with Gemini
vision, locates the "new mail" button and moves the cursor onto it
without clicking. Nothing is sent. Afterwards it goes back to
watching. Ctrl+C in the console stops it.

---

Prueba minima de viabilidad del agente demo de voz para Outlook (S142).

Sigue el flujo real del agente: vigila la pantalla y no hace nada
hasta que Outlook pasa de no maximizado a maximizado. Solo entonces
muestra un modal con botones de iniciar y detener grabacion. Al
detener, transcribe el mensaje con Gemini en Vertex AI y, con la
vision de Gemini, localiza el boton de correo nuevo y lleva el cursor
encima sin hacer clic. No se envia nada. Despues vuelve a vigilar.
Ctrl+C en la consola lo detiene.
"""

import ctypes
import json
import os
import queue
import sys
import threading
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
SAMPLE_RATE = 16000
WATCH_INTERVAL_SECONDS = 1.0
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
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_exe(pid.value)
        if exe in OUTLOOK_EXES:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            found.append({'hwnd': hwnd, 'exe': exe, 'title': title.value})
            return False
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    return found[0] if found else None


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


def build_client():
    """
    Builds a Vertex AI Gemini client from the local service key.

    ---

    Construye un cliente Gemini de Vertex AI con la clave local.
    """
    from google import genai
    from google.genai import types

    key_path = Path(os.environ.get('H28_AGENT_KEY_PATH', DEFAULT_KEY_PATH))
    _log('Clave de servicio: %s' % key_path)
    if not key_path.is_file():
        raise FileNotFoundError('no existe la clave %s' % key_path)
    with open(key_path, encoding='utf-8') as handle:
        key_data = json.load(handle)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_path)
    _log('Proyecto: %s | cuenta: %s' % (
        key_data.get('project_id'), key_data.get('client_email')))
    return genai.Client(
        vertexai=True,
        project=key_data.get('project_id'),
        location=GEMINI_LOCATION,
        http_options=types.HttpOptions(api_version='v1'),
    )


def save_wav(chunks):
    """
    Joins the recorded int16 chunks and writes them as a mono WAV.

    ---

    Une los bloques int16 grabados y los guarda como WAV mono.
    """
    import numpy

    audio = numpy.concatenate(chunks) if chunks else numpy.zeros(
        (0, 1), dtype='int16')
    with wave.open(str(WAV_PATH), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(audio.tobytes())
    peak = int(numpy.abs(audio).max()) if audio.size else 0
    seconds = audio.shape[0] / SAMPLE_RATE
    _log('Grabacion guardada en %s (%.1f s, pico=%d de 32767)' % (
        WAV_PATH, seconds, peak))
    return seconds


def transcribe(client):
    """
    Transcribes the saved recording with Gemini.

    ---

    Transcribe la grabacion guardada con Gemini.
    """
    from google.genai import types

    _log('Transcribiendo con %s' % GEMINI_MODEL)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(
                data=WAV_PATH.read_bytes(), mime_type='audio/wav'),
            'Transcribe literalmente este audio en castellano. Devuelve '
            'solo el texto transcrito, sin comentarios. Si no se oye '
            'voz, devuelve exactamente: (sin voz)',
        ],
    )
    text = (response.text or '').strip()
    _log('Transcripcion: "%s"' % text)
    return text


def locate_new_mail(client, outlook):
    """
    Screenshots the Outlook monitor, asks Gemini where the new-mail
    button is and moves the cursor there without clicking.

    ---

    Captura el monitor de Outlook, pregunta a Gemini donde esta el
    boton de correo nuevo y lleva alli el cursor sin hacer clic.
    """
    import mss
    from google.genai import types
    from PIL import Image

    left, top, width, height = monitor_rect_for(outlook['hwnd'])
    with mss.mss() as grabber:
        shot = grabber.grab(
            {'left': left, 'top': top, 'width': width, 'height': height})
    Image.frombytes('RGB', shot.size, shot.rgb).save(PNG_PATH)
    _log('Captura %dx%d guardada en %s' % (width, height, PNG_PATH))
    schema = {
        'type': 'OBJECT',
        'properties': {
            'found': {'type': 'BOOLEAN'},
            'label': {'type': 'STRING'},
            'box_2d': {'type': 'ARRAY', 'items': {'type': 'INTEGER'}},
        },
        'required': ['found'],
    }
    _log('Preguntando a Gemini por el boton de correo nuevo')
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
    _log('Respuesta de Gemini: %s' % json.dumps(result, ensure_ascii=False))
    box = result.get('box_2d') or []
    if not result.get('found') or len(box) != 4:
        return None
    center_x = left + int((box[1] + box[3]) / 2 / 1000 * width)
    center_y = top + int((box[0] + box[2]) / 2 / 1000 * height)
    ctypes.windll.user32.SetCursorPos(center_x, center_y)
    _log('Cursor llevado a (%d, %d) SIN clic, sobre "%s"' % (
        center_x, center_y, result.get('label')))
    return result.get('label'), center_x, center_y


class RecordingModal:
    """
    Topmost modal shown when Outlook is maximised: start and stop
    recording buttons, then transcription and button location run in
    a worker thread while the modal reports progress.

    ---

    Modal siempre encima que aparece al maximizar Outlook: botones de
    iniciar y detener grabacion; despues la transcripcion y la
    localizacion del boton corren en un hilo mientras el modal informa.
    """

    def __init__(self, client, outlook):
        """
        Builds the modal window.

        ---

        Construye la ventana modal.
        """
        import tkinter

        self._client = client
        self._outlook = outlook
        self._chunks = []
        self._stream = None
        self._events = queue.Queue()
        self.root = tkinter.Tk()
        self.root.title('Agente demo -- mensaje de voz')
        self.root.attributes('-topmost', True)
        self.root.resizable(False, False)
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self._status = tkinter.Label(
            self.root, text='Outlook maximizado. Pulsa Iniciar para '
            'grabar tu mensaje.', wraplength=380, justify='left',
            padx=16, pady=12)
        self._status.pack()
        buttons = tkinter.Frame(self.root, padx=16, pady=12)
        buttons.pack()
        self._start = tkinter.Button(
            buttons, text='Iniciar grabacion', width=18,
            command=self._start_recording)
        self._start.pack(side='left', padx=6)
        self._stop = tkinter.Button(
            buttons, text='Detener', width=12, state='disabled',
            command=self._stop_recording)
        self._stop.pack(side='left', padx=6)
        self.root.update_idletasks()
        width = self.root.winfo_width()
        x_pos = (self.root.winfo_screenwidth() - width) // 2
        self.root.geometry('+%d+%d' % (x_pos, 120))
        self.root.after(200, self._poll_events)

    def _set_status(self, text):
        """
        Shows a message in the modal and logs it.

        ---

        Muestra un mensaje en el modal y lo registra en el log.
        """
        self._status.config(text=text)
        _log('Modal: %s' % text)

    def _start_recording(self):
        """
        Opens the microphone stream and starts collecting audio.

        ---

        Abre el flujo del microfono y empieza a acumular audio.
        """
        import sounddevice

        self._chunks = []

        def _callback(data, _frames, _time_info, status):
            if status:
                _log('Aviso de audio: %s' % status)
            self._chunks.append(data.copy())

        device = sounddevice.query_devices(kind='input')
        _log('Microfono por defecto: %s' % device['name'])
        self._stream = sounddevice.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='int16',
            callback=_callback)
        self._stream.start()
        self._start.config(state='disabled')
        self._stop.config(state='normal')
        self._set_status('GRABANDO... habla y pulsa Detener al acabar.')

    def _stop_recording(self):
        """
        Stops the microphone and launches the processing thread.

        ---

        Detiene el microfono y lanza el hilo de procesamiento.
        """
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._stop.config(state='disabled')
        self._set_status('Grabacion detenida. Transcribiendo...')
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        """
        Worker: saves, transcribes and locates the new-mail button.

        ---

        Hilo: guarda, transcribe y localiza el boton de correo nuevo.
        """
        try:
            if save_wav(self._chunks) < 0.5:
                self._events.put(('done', 'Grabacion demasiado corta.'))
                return
            text = transcribe(self._client)
            self._events.put(('status', 'Transcripcion: "%s"\n\nBuscando '
                              'el boton de correo nuevo...' % text))
            self._events.put(('hide', None))
            time.sleep(0.8)
            found = locate_new_mail(self._client, self._outlook)
            if found:
                summary = ('Transcripcion: "%s"\n\nBoton "%s" localizado: '
                           'el cursor esta encima (sin clic).' % (
                               text, found[0]))
            else:
                summary = ('Transcripcion: "%s"\n\nGemini NO localizo el '
                           'boton de correo nuevo.' % text)
            self._events.put(('show', None))
            self._events.put(('done', summary))
        except Exception as exc:  # noqa: BLE001 -- shown in the modal
            _log('ERROR en el procesamiento: %r' % exc)
            self._events.put(('show', None))
            self._events.put(('done', 'ERROR: %r' % exc))

    def _poll_events(self):
        """
        Applies worker events to the UI from the Tk thread.

        ---

        Aplica en la interfaz los eventos del hilo, desde el hilo de Tk.
        """
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == 'status':
                    self._set_status(payload)
                elif kind == 'hide':
                    self.root.withdraw()
                elif kind == 'show':
                    self.root.deiconify()
                elif kind == 'done':
                    self._set_status(payload + '\n\nCierra esta ventana '
                                     'para volver a vigilar.')
        except queue.Empty:
            pass
        self.root.after(200, self._poll_events)

    def _close(self):
        """
        Closes the modal, stopping the microphone if still open.

        ---

        Cierra el modal, deteniendo el microfono si seguia abierto.
        """
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        _log('Modal cerrado.')
        self.root.destroy()

    def run(self):
        """
        Runs the modal until the user closes it.

        ---

        Ejecuta el modal hasta que el usuario lo cierra.
        """
        self.root.mainloop()


def main():
    """
    Watches for Outlook becoming maximised and shows the modal only
    at that transition.

    ---

    Vigila cuando Outlook pasa a maximizado y muestra el modal solo en
    esa transicion.
    """
    if sys.platform != 'win32':
        print('Esta prueba solo funciona en Windows.', flush=True)
        return 1
    _log('=== PRUEBA DE VIABILIDAD -- agente demo de voz para Outlook ===')
    _log('DPI: %s' % _set_dpi_awareness())
    client = build_client()
    was_maximized = find_maximized_outlook() is not None
    if was_maximized:
        _log('Outlook ya esta maximizado al arrancar: no cuenta. '
             'Restauralo o minimizalo y vuelve a maximizarlo.')
    _log('Vigilando la pantalla (Ctrl+C para salir)...')
    try:
        while True:
            outlook = find_maximized_outlook()
            if outlook and not was_maximized:
                _log('Outlook MAXIMIZADO detectado (%s, "%s"): '
                     'mostrando el modal' % (outlook['exe'],
                                             outlook['title']))
                RecordingModal(client, outlook).run()
                outlook = find_maximized_outlook()
                _log('Vuelvo a vigilar. Para repetir, restaura o '
                     'minimiza Outlook y vuelve a maximizarlo.')
            was_maximized = outlook is not None
            time.sleep(WATCH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        _log('Detenido por el usuario.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
