"""
Outlook voice demo agent (S142). Resident on Miguel Angel's PC, it
watches the screen and, only when Outlook goes from not maximised to
maximised, shows a modal with start and stop recording buttons. When
recording stops it transcribes the message with Gemini and sends it
by mail to the demo recipient, driving Outlook with Gemini vision and
on-screen clicks: new mail, To, Subject, body, visual check, Send.

---

Agente demo de voz para Outlook (S142). Residente en el PC de Miguel
Angel, vigila la pantalla y, solo cuando Outlook pasa de no maximizado
a maximizado, muestra un modal con botones de iniciar y detener
grabacion. Al detener, transcribe el mensaje con Gemini y lo envia por
correo al destinatario de la demo manejando Outlook con la vision de
Gemini y clics en pantalla: correo nuevo, Para, Asunto, cuerpo,
comprobacion visual, Enviar.
"""

import queue
import sys
import threading
import time
import wave

import desktop
import gemini_ops
from common import DATA_DIR
from common import RECIPIENT
from common import SAMPLE_RATE
from common import SUBJECT
from common import WATCH_INTERVAL_SECONDS
from common import WAV_PATH
from common import log

LOCATE_ATTEMPTS = 2


def save_wav(chunks):
    """
    Joins the recorded int16 chunks, writes them as a mono WAV and
    returns the duration in seconds.

    ---

    Une los bloques int16 grabados, los guarda como WAV mono y devuelve
    la duracion en segundos.
    """
    import numpy

    DATA_DIR.mkdir(exist_ok=True)
    audio = numpy.concatenate(chunks) if chunks else numpy.zeros(
        (0, 1), dtype='int16')
    with wave.open(str(WAV_PATH), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(audio.tobytes())
    seconds = audio.shape[0] / SAMPLE_RATE
    peak = int(numpy.abs(audio).max()) if audio.size else 0
    log('Grabacion guardada en %s (%.1f s, pico=%d de 32767)' % (
        WAV_PATH, seconds, peak))
    return seconds


def _shot_of(hwnd, name):
    """
    Screenshots the monitor holding a window into demo_data.

    ---

    Captura el monitor de una ventana en demo_data.
    """
    region = desktop.monitor_rect_for(hwnd)
    path = DATA_DIR / name
    desktop.screenshot(region, path)
    log('Captura %s (%dx%d)' % (path.name, region[2], region[3]))
    return path, region


def _find_and_click(client, hwnd, step_name, description):
    """
    Screenshots, asks Gemini for an element and clicks its centre,
    retrying once with a fresh screenshot.

    ---

    Captura, pide a Gemini un elemento y hace clic en su centro,
    reintentando una vez con una captura nueva.
    """
    for attempt in range(1, LOCATE_ATTEMPTS + 1):
        path, region = _shot_of(hwnd, '%s_%d.png' % (step_name, attempt))
        target = gemini_ops.locate(client, path, region, description)
        if target:
            log('Clic en (%d, %d) sobre "%s"' % (
                target['x'], target['y'], target['label']))
            desktop.click(target['x'], target['y'])
            return True
        log('Intento %d/%d sin localizar el elemento' % (
            attempt, LOCATE_ATTEMPTS))
        time.sleep(1.5)
    return False


def send_mail(client, outlook, body, report):
    """
    Drives Outlook on screen to send the transcription. Returns a
    human-readable result. Stops without sending if any step fails or
    the visual check does not match.

    ---

    Maneja Outlook en pantalla para enviar la transcripcion. Devuelve
    un resultado legible. Se detiene sin enviar si falla algun paso o
    la comprobacion visual no cuadra.
    """
    report('Paso 1/6: abriendo correo nuevo')
    if not _find_and_click(
            client, outlook['hwnd'], 'paso1_correo_nuevo',
            'el boton que crea un correo nuevo ("Correo nuevo", "Nuevo '
            'correo", "Nuevo mensaje" o "New mail")'):
        return 'No encontre el boton de correo nuevo. No se envio nada.'
    time.sleep(3)
    compose = desktop.foreground_window()
    log('Ventana en primer plano tras correo nuevo: %s "%s"' % (
        compose['exe'], compose['title']))
    steps = (
        ('Paso 2/6: destinatario', 'paso2_para',
         'el campo de texto del destinatario "Para" (To) de la ventana '
         'de redaccion del correo nuevo', RECIPIENT),
        ('Paso 3/6: asunto', 'paso3_asunto',
         'el campo de texto "Asunto" (Subject) de la ventana de '
         'redaccion del correo nuevo', SUBJECT),
        ('Paso 4/6: cuerpo', 'paso4_cuerpo',
         'la zona grande en blanco del cuerpo del mensaje, debajo del '
         'campo Asunto, en la ventana de redaccion del correo nuevo',
         body),
    )
    for status, step_name, description, text in steps:
        report(status)
        if not _find_and_click(
                client, compose['hwnd'], step_name, description):
            return '%s: elemento no encontrado. No se envio nada.' % status
        time.sleep(0.4)
        desktop.type_text(text)
        log('Escrito en %s (%d caracteres)' % (step_name, len(text)))
        time.sleep(0.6)
    report('Paso 5/6: comprobando el correo antes de enviar')
    path, _region = _shot_of(compose['hwnd'], 'paso5_comprobacion.png')
    check = gemini_ops.verify_compose(client, path, RECIPIENT, SUBJECT, body)
    if not (check.get('to_ok') and check.get('subject_ok')
            and check.get('body_ok')):
        return ('La comprobacion visual no cuadra (%s). El borrador queda '
                'abierto SIN enviar.' % check.get('notes', ''))
    report('Paso 6/6: enviando')
    if not _find_and_click(
            client, compose['hwnd'], 'paso6_enviar',
            'el boton "Enviar" (Send) de la ventana de redaccion'):
        return 'No encontre el boton Enviar. El borrador queda abierto.'
    time.sleep(3)
    after = desktop.foreground_window()
    log('Ventana en primer plano tras Enviar: %s "%s"' % (
        after['exe'], after['title']))
    _shot_of(after['hwnd'], 'paso6_despues_de_enviar.png')
    return 'Correo enviado a %s con asunto "%s".' % (RECIPIENT, SUBJECT)


class RecordingModal:
    """
    Topmost modal shown when Outlook is maximised: start and stop
    recording buttons; after stopping, transcription and sending run
    in a worker thread while the modal reports progress.

    ---

    Modal siempre encima que aparece al maximizar Outlook: botones de
    iniciar y detener grabacion; al detener, la transcripcion y el
    envio corren en un hilo mientras el modal informa.
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
            'grabar el mensaje para %s.' % RECIPIENT, wraplength=380,
            justify='left', padx=16, pady=12)
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
        log('Modal: %s' % text)

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
                log('Aviso de audio: %s' % status)
            self._chunks.append(data.copy())

        device = sounddevice.query_devices(kind='input')
        log('Microfono por defecto: %s' % device['name'])
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
        Worker: saves, transcribes and sends the mail through Outlook.

        ---

        Hilo: guarda, transcribe y envia el correo a traves de Outlook.
        """
        try:
            if save_wav(self._chunks) < 0.5:
                self._events.put(('done', 'Grabacion demasiado corta. '
                                  'No se envio nada.'))
                return
            text = gemini_ops.transcribe(self._client, WAV_PATH)
            if not text:
                self._events.put(('done', 'No se entendio ninguna voz. '
                                  'No se envio nada.'))
                return
            self._events.put(('hide', None))
            time.sleep(0.8)
            result = send_mail(
                self._client, self._outlook, text,
                lambda message: log('Progreso: %s' % message))
            log('Resultado: %s' % result)
            self._events.put(('show', None))
            self._events.put(('done', 'Transcripcion: "%s"\n\n%s' % (
                text, result)))
        except Exception as exc:  # noqa: BLE001 -- shown in the modal
            log('ERROR en el procesamiento: %r' % exc)
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
        log('Modal cerrado.')
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
        print('Este agente solo funciona en Windows.', flush=True)
        return 1
    log('=== AGENTE DEMO DE VOZ PARA OUTLOOK ===')
    log('DPI: %s' % desktop.set_dpi_awareness())
    client = gemini_ops.build_client()
    was_maximized = desktop.find_maximized_outlook() is not None
    if was_maximized:
        log('Outlook ya esta maximizado al arrancar: no cuenta. '
            'Restauralo o minimizalo y vuelve a maximizarlo.')
    log('Vigilando la pantalla (Ctrl+C para salir)...')
    try:
        while True:
            outlook = desktop.find_maximized_outlook()
            if outlook and not was_maximized:
                log('Outlook MAXIMIZADO detectado (%s, "%s"): mostrando '
                    'el modal' % (outlook['exe'], outlook['title']))
                RecordingModal(client, outlook).run()
                outlook = desktop.find_maximized_outlook()
                log('Vuelvo a vigilar. Para repetir, restaura o minimiza '
                    'Outlook y vuelve a maximizarlo.')
            was_maximized = outlook is not None
            time.sleep(WATCH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log('Detenido por el usuario.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
