# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/views.py
import os
import logging
from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# Internal developer context logger
# Logger de contexto para el desarrollador
logger = logging.getLogger("VoxViews")

@method_decorator(csrf_exempt, name='dispatch')
class InboundCallView(View):
    """
    Handles inbound TwiML requests from Twilio to establish a WebSocket Media Stream.
    Retrieves the active ngrok URL from a shared session file and performs protocol upgrade to WSS.
    ---
    Gestiona las peticiones TwiML entrantes de Twilio para establecer un flujo de medios por WebSocket.
    Recupera la URL activa de ngrok desde un archivo de sesión compartido y realiza la actualización de protocolo a WSS.
    """
    
    def get_active_wss_url(self):
        """
        Reads the NGROK_URL.txt file and converts the HTTPS schema to WSS.
        ---
        Lee el archivo NGROK_URL.txt y convierte el esquema HTTPS a WSS.
        """
        shared_file = "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt"
        default_url = "wss://enterprisebot.ngrok-free.app"
        
        if os.path.exists(shared_file):
            with open(shared_file, 'r') as f:
                raw_url = f.read().strip().rstrip('/')
                if raw_url:
                    return raw_url.replace("https://", "wss://")
        
        return default_url

    def post(self, request, *args, **kwargs):
        """
        Responds with the TwiML <Connect><Stream> instruction to redirect audio to the sidecar.
        ---
        Responde con la instrucción TwiML <Connect><Stream> para redireccionar el audio al sidecar.
        """
        wss_url = self.get_active_wss_url()
        
        # Twilio standard XML payload / Payload XML estándar de Twilio
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '    <Connect>'
            f'        <Stream url="{wss_url}" />'
            '    </Connect>'
            '</Response>'
        )
        
        return HttpResponse(twiml, content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class HoldMusicView(View):
    """
    Serves TwiML with a looping <Play> instruction for the hold music audio
    file. Used as waitUrl in the <Dial><Conference> TwiML for transfer calls
    (Paso 39). The caller hears this music while waiting for the section
    contact to answer the outbound call.
    ---
    Sirve TwiML con una instrucción <Play> en bucle para el archivo de audio
    de música de espera. Se usa como waitUrl en el TwiML <Dial><Conference>
    para transferencias de llamada (Paso 39). El llamante escucha esta música
    mientras espera que el contacto de sección conteste la llamada saliente.
    """

    # Relative static URL for the hold music file.
    # URL estática relativa del archivo de música de espera.
    HOLD_MUSIC_PATH = "/static/vox_bridge/audio/hold.mp3"

    def get(self, request, *args, **kwargs):
        """
        Returns TwiML <Play loop="0"> with the hold music file URL.
        Twilio calls this endpoint as the waitUrl while the caller waits
        in the Conference room. loop="0" plays it indefinitely.
        ---
        Devuelve TwiML <Play loop="0"> con la URL del archivo de música de espera.
        Twilio llama a este endpoint como waitUrl mientras el llamante espera
        en la sala Conference. loop="0" lo reproduce indefinidamente.
        """
        host = request.build_absolute_uri(self.HOLD_MUSIC_PATH)
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            f'<Play loop="0">{host}</Play>'
            '</Response>'
        )
        logger.info(
            f"[HOLD-MUSIC] TwiML de música de espera servido. URL: {host}"
        )
        return HttpResponse(twiml, content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class TransferStatusView(View):
    """
    Webhook called by Twilio when the <Dial> in the transfer Conference ends
    (Paso 39 action URL). This happens when:
        - The section contact answered and then hung up (DialCallStatus=completed).
        - The section contact did not answer within the timeout (DialCallStatus=no-answer).
        - The section contact's line was busy (DialCallStatus=busy).
        - The section contact rejected the call (DialCallStatus=failed).

    On any non-completed status (no-answer, busy, failed), the endpoint
    responds with TwiML that reconnects Alia via a new <Connect><Stream>
    so she can inform the caller and offer to take a voice message.

    On completed status, both parties have already spoken and the call
    flow ends normally — no reconnection is needed.
    ---
    Webhook invocado por Twilio cuando el <Dial> de la Conference de
    transferencia termina (action URL del Paso 39). Ocurre cuando:
        - El contacto de sección contestó y luego colgó (DialCallStatus=completed).
        - El contacto no contestó en el timeout (DialCallStatus=no-answer).
        - La línea del contacto estaba ocupada (DialCallStatus=busy).
        - El contacto rechazó la llamada (DialCallStatus=failed).

    En cualquier estado no completado (no-answer, busy, failed), el endpoint
    responde con TwiML que reconecta a Alia vía un nuevo <Connect><Stream>
    para que informe al llamante y ofrezca tomar un mensaje de voz.

    En estado completed, ambas partes ya hablaron y el flujo termina
    normalmente — no se necesita reconexión.
    """

    def post(self, request, *args, **kwargs):
        """
        Handles the Twilio action webhook after the <Dial> ends.
        Reads DialCallStatus and reconnects Alia if the transfer failed.
        ---
        Gestiona el webhook action de Twilio tras el fin del <Dial>.
        Lee DialCallStatus y reconecta a Alia si la transferencia falló.
        """
        dial_status = request.POST.get("DialCallStatus", "unknown")
        call_sid    = kwargs.get("call_sid", "")

        logger.info(
            f"[TRANSFER-STATUS] Webhook recibido para call_sid={call_sid}. "
            f"DialCallStatus: '{dial_status}'."
        )

        if dial_status == "completed":
            # Transfer was successful — caller and contact spoke directly.
            # No further action needed; return empty TwiML to end the call.
            # Transferencia exitosa — llamante y contacto hablaron directamente.
            # No se necesita ninguna acción adicional; devolver TwiML vacío.
            logger.info(
                f"[TRANSFER-STATUS] Transferencia completada con éxito "
                f"para call_sid={call_sid}. Finalizando llamada."
            )
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Response></Response>'
            )
        else:
            # Transfer failed — reconnect Alia via a new Media Stream so she
            # can inform the caller and offer a voice message option.
            # Transferencia fallida — reconectar a Alia vía nuevo Media Stream
            # para que informe al llamante y ofrezca un mensaje de voz.
            logger.info(
                f"[TRANSFER-STATUS] Transferencia fallida (status='{dial_status}') "
                f"para call_sid={call_sid}. Reconectando a Alia..."
            )
            # Read ngrok URL from shared session file.
            # Leer URL ngrok del archivo de sesión compartido.
            ngrok_file = (
                "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt"
            )
            try:
                with open(ngrok_file, "r") as _f:
                    raw_url = _f.read().strip().rstrip("/")
                wss_url = raw_url.replace("https://", "wss://")
            except Exception:
                wss_url = "wss://enterprisebot.ngrok-free.app"
                logger.warning(
                    "[TRANSFER-STATUS] No se pudo leer NGROK_URL.txt. "
                    f"Usando wss_url por defecto: {wss_url}"
                )
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Response>'
                '<Connect>'
                f'<Stream url="{wss_url}/media" />'
                '</Connect>'
                '</Response>'
            )

        return HttpResponse(twiml, content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class TransferAcceptView(View):
    """
    Called when the section contact accepts the transfer by pressing 1
    on their keypad (Paso 39). Responds with TwiML that joins the contact
    into the Conference room as the moderator, starting the conference and
    ending the caller's hold music.

    NOTE: In the current implementation (Paso 39) the outbound call TwiML
    joins the contact directly without a DTMF confirmation step. This view
    is reserved for a future iteration that adds the confirm-before-connect
    interaction pattern.
    ---
    Invocado cuando el contacto de sección acepta la transferencia pulsando 1
    en su teclado (Paso 39). Responde con TwiML que une al contacto en la
    sala Conference como moderador, iniciando la conferencia y terminando la
    música de espera del llamante.

    NOTA: En la implementación actual (Paso 39) el TwiML de la llamada
    saliente une al contacto directamente sin paso de confirmación DTMF.
    Esta vista queda reservada para una iteración futura que añada el
    patrón de interacción confirmar-antes-de-conectar.
    """

    def post(self, request, *args, **kwargs):
        """
        Joins the section contact into the named Conference room.
        startConferenceOnEnter=true causes the conference to start and
        the caller's hold music to stop.
        ---
        Une al contacto de sección en la sala Conference con nombre.
        startConferenceOnEnter=true hace que la conferencia comience y
        la música de espera del llamante se detenga.
        """
        conference_name = kwargs.get("conference_name", "")
        logger.info(
            f"[TRANSFER-ACCEPT] Contacto acepta transferencia. "
            f"Uniéndose a la sala: '{conference_name}'."
        )
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            f'<Dial><Conference startConferenceOnEnter="true" '
            f'endConferenceOnExit="false" beep="false">'
            f'{conference_name}</Conference></Dial>'
            '</Response>'
        )
        return HttpResponse(twiml, content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class ForwardToMobileView(View):
    """
    Handles inbound calls from external sources (e.g. Meta/WhatsApp verification)
    and responds with TwiML to forward the call to the configured mobile number.
    No Twilio signature validation is applied — this endpoint must remain publicly
    accessible for third-party verification flows.
    ---
    Gestiona llamadas entrantes de fuentes externas (p. ej. verificación Meta/WhatsApp)
    y responde con TwiML para reenviar la llamada al número móvil configurado.
    No se aplica validación de firma Twilio — este endpoint debe permanecer accesible
    públicamente para flujos de verificación de terceros.
    """

    # Número de destino del reenvío / Forwarding destination number
    MOBILE_TARGET = "+34711509585"

    def get(self, request, *args, **kwargs):
        """
        Responds with a TwiML <Dial> instruction to forward the call to MOBILE_TARGET.
        Accepts GET to allow direct URL invocation from Twilio Voice Configuration.
        ---
        Responde con la instrucción TwiML <Dial> para reenviar la llamada a MOBILE_TARGET.
        Acepta GET para permitir la invocación directa desde la configuración de voz de Twilio.
        """
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            f'    <Dial callerId="+34951799117">{self.MOBILE_TARGET}</Dial>'
            '</Response>'
        )
        return HttpResponse(twiml, content_type='text/xml')

    def post(self, request, *args, **kwargs):
        """
        Accepts POST as well for compatibility with Twilio webhook configurations
        that use HTTP POST method.
        ---
        Acepta POST también para compatibilidad con configuraciones de webhook de Twilio
        que usan el método HTTP POST.
        """
        return self.get(request, *args, **kwargs)
