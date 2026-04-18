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

    Resilient multi-contact flow:
        1. Look up the TransferAttempt record by call_sid.
        2. If DialCallStatus=completed → mark COMPLETED → return empty TwiML.
        3. If failed/no-answer/busy:
             a. Increment contact_index on the TransferAttempt record.
             b. Check whether a next contact exists in SectionContact ordered by priority.
             c. If yes → reconnect Alia via new <Connect><Stream> so she can inform
                the caller and offer to transfer to the next contact or leave a message.
             d. If no more contacts → reconnect Alia → she informs the caller that no
                one is available and offers to record a voice message. A
                PendingNotification record is created in the database for manual
                follow-up and future Celery processing (Hito 4).

    Twilio does not carry session context in the action webhook POST body.
    The TransferAttempt record persisted by _execute_transfer() is the only
    viable mechanism to correlate this webhook with the correct call state.
    ---
    Webhook invocado por Twilio cuando el <Dial> de la Conference de transferencia
    termina (action URL del Paso 39). Ocurre cuando:
        - El contacto contestó y luego colgó (DialCallStatus=completed).
        - El contacto no contestó en el timeout (DialCallStatus=no-answer).
        - La línea del contacto estaba ocupada (DialCallStatus=busy).
        - El contacto rechazó la llamada (DialCallStatus=failed).

    Flujo resiliente multi-contacto:
        1. Buscar el registro TransferAttempt por call_sid.
        2. Si DialCallStatus=completed → marcar COMPLETED → devolver TwiML vacío.
        3. Si failed/no-answer/busy:
             a. Incrementar contact_index en el registro TransferAttempt.
             b. Comprobar si existe un contacto siguiente en SectionContact por priority.
             c. Si sí → reconectar a Alia vía nuevo <Connect><Stream> para que informe
                al llamante y ofrezca transferir al siguiente contacto o dejar un mensaje.
             d. Si no hay más contactos → reconectar a Alia → informa al llamante de que
                nadie está disponible y ofrece grabar un mensaje de voz. Se crea un
                registro PendingNotification en BD para seguimiento manual y procesamiento
                futuro por Celery (Hito 4).

    Twilio no transporta contexto de sesión en el body del POST del webhook action.
    El registro TransferAttempt persistido por _execute_transfer() es el único
    mecanismo viable para correlacionar este webhook con el estado de llamada correcto.
    """

    # DialCallStatus values that indicate the contact did not answer.
    # Valores de DialCallStatus que indican que el contacto no contestó.
    FAILED_STATUSES = {"no-answer", "busy", "failed", "canceled"}

    def _get_wss_url(self) -> str:
        """
        Reads the active ngrok HTTPS URL from the shared session file and
        converts it to a WSS URL for the <Stream> TwiML verb.
        Falls back to a hardcoded default if the file cannot be read.
        ---
        Lee la URL HTTPS activa de ngrok del archivo de sesión compartido y
        la convierte en URL WSS para el verbo TwiML <Stream>.
        Usa un valor por defecto hardcodeado si el archivo no puede leerse.
        """
        ngrok_file = (
            "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt"
        )
        try:
            with open(ngrok_file, "r") as _f:
                raw_url = _f.read().strip().rstrip("/")
            return raw_url.replace("https://", "wss://")
        except Exception:
            fallback = "wss://enterprisebot.ngrok-free.app"
            logger.warning(
                "[TRANSFER-STATUS] No se pudo leer NGROK_URL.txt. "
                f"Usando wss_url por defecto: {fallback}"
            )
            return fallback

    def _twiml_reconnect_alia(self, wss_url: str) -> str:
        """
        Returns TwiML that opens a new bidirectional Media Stream to reconnect
        Alia to the caller after a failed transfer attempt.
        ---
        Devuelve TwiML que abre un nuevo Media Stream bidireccional para reconectar
        a Alia con el llamante tras un intento de transferencia fallido.
        """
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Connect>'
            f'<Stream url="{wss_url}/media" />'
            '</Connect>'
            '</Response>'
        )

    def _twiml_end_call(self) -> str:
        """
        Returns empty TwiML to end the call gracefully after a completed transfer.
        ---
        Devuelve TwiML vacío para finalizar la llamada de forma elegante
        tras una transferencia completada con éxito.
        """
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

    def post(self, request, *args, **kwargs):
        """
        Handles the Twilio action webhook after the <Dial> Conference ends.
        Implements the resilient multi-contact transfer flow using the
        TransferAttempt record as the cross-process state bridge.
        ---
        Gestiona el webhook action de Twilio tras el fin de la Conference <Dial>.
        Implementa el flujo de transferencia resiliente multi-contacto usando el
        registro TransferAttempt como puente de estado entre procesos.
        """
        from ivr_config.models import (
            SectionContact      as _SectionContact,
            TransferAttempt     as _TransferAttempt,
            PendingNotification as _PendingNotification,
        )

        dial_status = request.POST.get("DialCallStatus", "unknown")
        call_sid    = kwargs.get("call_sid", "")

        logger.info(
            f"[TRANSFER-STATUS] Webhook recibido — call_sid={call_sid} "
            f"| DialCallStatus='{dial_status}'."
        )

        # ------------------------------------------------------------------
        # Step 1: Resolve the TransferAttempt record for this call.
        # Paso 1: Resolver el registro TransferAttempt para esta llamada.
        # ------------------------------------------------------------------
        try:
            attempt = _TransferAttempt.objects.select_related("section").get(
                call_sid=call_sid
            )
        except _TransferAttempt.DoesNotExist:
            # No record found — this should not happen in normal flow.
            # Reconnect Alia as a safe fallback so the caller is not abandoned.
            # No se encontró registro — esto no debería ocurrir en el flujo normal.
            # Reconectar a Alia como fallback seguro para no abandonar al llamante.
            logger.error(
                f"[TRANSFER-STATUS] TransferAttempt no encontrado para "
                f"call_sid={call_sid}. Reconectando a Alia como fallback."
            )
            return HttpResponse(
                self._twiml_reconnect_alia(self._get_wss_url()),
                content_type="text/xml",
            )

        # ------------------------------------------------------------------
        # Step 2: Handle completed transfer — both parties spoke successfully.
        # Paso 2: Gestionar transferencia completada — ambas partes hablaron.
        # ------------------------------------------------------------------
        if dial_status == "completed":
            attempt.status = _TransferAttempt.STATUS_COMPLETED
            attempt.save(update_fields=["status", "updated_at"])
            logger.info(
                f"[TRANSFER-STATUS] Transferencia completada con éxito — "
                f"call_sid={call_sid}. Finalizando llamada."
            )
            return HttpResponse(self._twiml_end_call(), content_type="text/xml")

        # ------------------------------------------------------------------
        # Step 3: Handle failed transfer — attempt next contact if available.
        # Paso 3: Gestionar transferencia fallida — intentar siguiente contacto.
        # ------------------------------------------------------------------
        if dial_status in self.FAILED_STATUSES:

            next_index = attempt.contact_index + 1

            # Update the attempt record with the new index and FAILED status.
            # Actualizar el registro de intento con el nuevo índice y estado FAILED.
            attempt.contact_index = next_index
            attempt.status        = _TransferAttempt.STATUS_FAILED
            attempt.save(update_fields=["contact_index", "status", "updated_at"])

            logger.info(
                f"[TRANSFER-STATUS] Intento fallido (status='{dial_status}') — "
                f"call_sid={call_sid} | próximo contact_index={next_index}."
            )

            # Check whether a next contact exists at the updated index.
            # Comprobar si existe un contacto siguiente en el índice actualizado.
            next_contacts = (
                _SectionContact.objects.select_related("contact")
                .filter(section=attempt.section)
                .exclude(contact__phone_number="")
                .order_by("priority", "contact__name")
            )
            next_contacts_list = list(next_contacts)

            if next_index < len(next_contacts_list):
                # A next contact exists — reconnect Alia so she can offer
                # the caller the option to try the next contact.
                # Existe un contacto siguiente — reconectar a Alia para que ofrezca
                # al llamante la opción de intentar con el siguiente contacto.
                next_contact = next_contacts_list[next_index].contact
                logger.info(
                    f"[TRANSFER-STATUS] Siguiente contacto disponible: "
                    f"'{next_contact.name}' — reconectando a Alia."
                )
            else:
                # No more contacts — reconnect Alia to inform the caller and
                # create a PendingNotification for manual follow-up (Hito 4 stub).
                # Sin más contactos — reconectar a Alia para informar al llamante
                # y crear PendingNotification para seguimiento manual (stub Hito 4).
                logger.info(
                    f"[TRANSFER-STATUS] Sin más contactos disponibles para "
                    f"call_sid={call_sid}. Creando PendingNotification y reconectando a Alia."
                )
                try:
                    _PendingNotification.objects.create(
                        company=attempt.section.company if attempt.section else None,
                        section=attempt.section,
                        caller_number=attempt.caller_number,
                        call_sid=call_sid,
                        channel=_PendingNotification.CHANNEL_PENDING,
                    )
                    logger.info(
                        f"[TRANSFER-STATUS] PendingNotification creada — "
                        f"caller={attempt.caller_number} | call_sid={call_sid}."
                    )
                except Exception as notify_exc:
                    logger.error(
                        f"[TRANSFER-STATUS] Error al crear PendingNotification: "
                        f"{type(notify_exc).__name__}: {notify_exc}",
                        exc_info=True,
                    )

            # In both cases (next contact or no contacts), reconnect Alia.
            # She will handle the conversation based on the updated context
            # injected by build_live_config() on the new Media Stream.
            # En ambos casos (siguiente contacto o sin contactos), reconectar a Alia.
            # Ella gestionará la conversación según el contexto actualizado
            # inyectado por build_live_config() en el nuevo Media Stream.
            wss_url = self._get_wss_url()
            logger.info(
                f"[TRANSFER-STATUS] Reconectando a Alia — wss_url: {wss_url}/media"
            )
            return HttpResponse(
                self._twiml_reconnect_alia(wss_url),
                content_type="text/xml",
            )

        # ------------------------------------------------------------------
        # Step 4: Unexpected DialCallStatus — log and reconnect Alia as fallback.
        # Paso 4: DialCallStatus inesperado — registrar y reconectar a Alia.
        # ------------------------------------------------------------------
        logger.warning(
            f"[TRANSFER-STATUS] DialCallStatus inesperado: '{dial_status}' "
            f"para call_sid={call_sid}. Reconectando a Alia como fallback."
        )
        return HttpResponse(
            self._twiml_reconnect_alia(self._get_wss_url()),
            content_type="text/xml",
        )


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
