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
             c. If yes → reconnect María via new <Connect><Stream> so she can inform
                the caller and offer to transfer to the next contact or leave a message.
             d. If no more contacts → reconnect María → she informs the caller that no
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
             c. Si sí → reconectar a María vía nuevo <Connect><Stream> para que informe
                al llamante y ofrezca transferir al siguiente contacto o dejar un mensaje.
             d. Si no hay más contactos → reconectar a María → informa al llamante de que
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
        María to the caller after a failed transfer attempt.
        ---
        Devuelve TwiML que abre un nuevo Media Stream bidireccional para reconectar
        a María con el llamante tras un intento de transferencia fallido.
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
        Handles the Twilio action webhook fired when the caller leaves the
        <Dial><Conference> room (i.e. when the caller hangs up or the
        Conference ends on the caller side).

        IMPORTANT — Twilio behaviour for <Dial><Conference>:
            When the noun inside <Dial> is <Conference>, Twilio always sends
            DialCallStatus='answered' to the action URL, regardless of whether
            the contact answered or not. This is documented behaviour (Twilio
            Dial reference, 2026). The actual outcome of the outbound call to
            the section contact is reported by a separate statusCallback webhook
            registered on that outbound call by _execute_transfer() in
            vox_bridge/services.py → handled by ContactStatusView below.

        Responsibility of THIS view (action URL of the caller <Dial>):
            1. Receive the 'answered' POST from Twilio when the caller exits
               the Conference room (caller hung up or Conference ended).
            2. Look up the TransferAttempt record by call_sid to determine the
               final transfer outcome already resolved by ContactStatusView.
            3. If status=COMPLETED → the contact answered and the conversation
               finished normally → return empty TwiML (call ends).
            4. If status=PENDING or FAILED → the contact never answered or the
               contact status webhook has not yet arrived → reconnect María as
               a safe fallback so the caller is not abandoned.
            5. If no TransferAttempt record exists → reconnect María as fallback.
        ---
        Gestiona el webhook action de Twilio disparado cuando el llamante
        abandona la sala <Dial><Conference> (el llamante cuelga o la Conference
        termina en su lado).

        IMPORTANTE — comportamiento de Twilio para <Dial><Conference>:
            Cuando el noun dentro de <Dial> es <Conference>, Twilio envía
            siempre DialCallStatus='answered' al action URL, independientemente
            de si el contacto contestó o no. Es comportamiento documentado (ref.
            Twilio Dial, 2026). El resultado real de la llamada saliente al
            contacto de sección lo notifica un webhook statusCallback separado
            registrado en esa llamada saliente por _execute_transfer() en
            vox_bridge/services.py → gestionado por ContactStatusView (abajo).

        Responsabilidad de ESTA vista (action URL del <Dial> del llamante):
            1. Recibir el POST 'answered' de Twilio cuando el llamante sale
               de la sala Conference (colgó o la Conference terminó).
            2. Consultar el registro TransferAttempt por call_sid para conocer
               el resultado final de la transferencia ya resuelto por
               ContactStatusView.
            3. Si status=COMPLETED → el contacto contestó y la conversación
               terminó normalmente → devolver TwiML vacío (llamada termina).
            4. Si status=PENDING o FAILED → el contacto nunca contestó o el
               webhook de estado del contacto no ha llegado aún → reconectar
               a María como fallback para no abandonar al llamante.
            5. Si no existe registro TransferAttempt → reconectar a María.
        """
        from ivr_config.models import TransferAttempt as _TransferAttempt

        dial_status = request.POST.get("DialCallStatus", "unknown")
        call_sid    = kwargs.get("call_sid", "")

        logger.info(
            f"[TRANSFER-STATUS] Webhook recibido — call_sid={call_sid} "
            f"| DialCallStatus='{dial_status}' (siempre 'answered' "
            f"para <Dial><Conference>, según documentación Twilio)."
        )

        # ------------------------------------------------------------------
        # Step 1: Resolve the TransferAttempt record for this call.
        # Paso 1: Resolver el registro TransferAttempt para esta llamada.
        # ------------------------------------------------------------------
        try:
            attempt = _TransferAttempt.objects.get(call_sid=call_sid)
        except _TransferAttempt.DoesNotExist:
            logger.error(
                f"[TRANSFER-STATUS] TransferAttempt no encontrado para "
                f"call_sid={call_sid}. Reconectando a María como fallback."
            )
            return HttpResponse(
                self._twiml_reconnect_alia(self._get_wss_url()),
                content_type="text/xml",
            )

        # ------------------------------------------------------------------
        # Step 2: Transfer completed — contact answered and conversation ended.
        # The TransferAttempt.status was already set to COMPLETED by
        # ContactStatusView when the outbound call to the contact finished.
        # Return empty TwiML — the call ends naturally.
        # ------------------------------------------------------------------
        # Paso 2: Transferencia completada — el contacto contestó y la
        # conversación terminó. ContactStatusView ya actualizó el status a
        # COMPLETED cuando finalizó la llamada saliente. TwiML vacío → fin.
        # ------------------------------------------------------------------
        if attempt.status == _TransferAttempt.STATUS_COMPLETED:
            logger.info(
                f"[TRANSFER-STATUS] Transferencia confirmada como COMPLETADA "
                f"por ContactStatusView — call_sid={call_sid}. "
                f"Finalizando llamada con TwiML vacío."
            )
            return HttpResponse(self._twiml_end_call(), content_type="text/xml")

        # ------------------------------------------------------------------
        # Step 3: Transfer pending or failed — contact did not answer or the
        # ContactStatusView webhook has not yet been processed. Reconnect María
        # as a safe fallback so the caller is not left in silence.
        # ------------------------------------------------------------------
        # Paso 3: Transferencia pendiente o fallida — el contacto no contestó
        # o el webhook de ContactStatusView aún no ha llegado. Reconectar a
        # María como fallback seguro para no dejar al llamante en silencio.
        # ------------------------------------------------------------------
        logger.info(
            f"[TRANSFER-STATUS] Transferencia no completada "
            f"(attempt.status='{attempt.status}') — call_sid={call_sid}. "
            f"Reconectando a María como fallback."
        )
        wss_url = self._get_wss_url()
        return HttpResponse(
            self._twiml_reconnect_alia(wss_url),
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
class ContactStatusView(View):
    """
    Receives the Twilio statusCallback webhook for the outbound call placed
    to the section contact during a transfer (Paso 39). This is the canonical
    mechanism to determine whether the section contact actually answered the
    call — the <Dial><Conference> action URL on the caller side always reports
    DialCallStatus='answered', making it unsuitable for outcome detection.

    Flow:
        _execute_transfer() in vox_bridge/services.py creates an outbound call
        to the section contact and registers THIS endpoint as status_callback.
        Twilio calls this endpoint when the outbound call reaches a terminal
        state (completed, no-answer, busy, failed, canceled).

        - CallStatus='completed':
            The contact answered and the conference ended normally.
            Mark TransferAttempt.status=COMPLETED.
            No further action needed — TransferStatusView (caller action URL)
            will receive 'answered' and check the COMPLETED status to end
            the call cleanly.

        - CallStatus in FAILED_STATUSES (no-answer, busy, failed, canceled):
            The contact did not answer.
            Increment TransferAttempt.contact_index.
            Check if a next contact exists (ordered by SectionContact.priority).
            If yes → update the caller's live call with a new <Connect><Stream>
                     so María reconects and offers the next contact option.
            If no  → create PendingNotification + update caller call with
                     <Connect><Stream> so María informs and offers voice message.

        - Any other status → log and ignore (non-terminal intermediate states).
    ---
    Recibe el webhook statusCallback de Twilio para la llamada saliente al
    contacto de sección durante una transferencia (Paso 39). Este es el
    mecanismo canónico para determinar si el contacto contestó realmente —
    el action URL de <Dial><Conference> en el lado del llamante siempre
    reporta DialCallStatus='answered', lo que lo hace inadecuado para
    detectar el resultado.

    Flujo:
        _execute_transfer() en vox_bridge/services.py crea una llamada saliente
        al contacto de sección y registra ESTE endpoint como status_callback.
        Twilio llama a este endpoint cuando la llamada saliente alcanza un
        estado terminal (completed, no-answer, busy, failed, canceled).

        - CallStatus='completed':
            El contacto contestó y la conferencia terminó normalmente.
            Marcar TransferAttempt.status=COMPLETED.
            No se requiere acción adicional — TransferStatusView (action URL
            del llamante) recibirá 'answered' y comprobará el status COMPLETED
            para finalizar la llamada limpiamente.

        - CallStatus en FAILED_STATUSES (no-answer, busy, failed, canceled):
            El contacto no contestó.
            Incrementar TransferAttempt.contact_index.
            Comprobar si existe un contacto siguiente (ordenado por
            SectionContact.priority).
            Si sí → actualizar la llamada del llamante con nuevo
                    <Connect><Stream> para que María reconecte y ofrezca
                    la opción del siguiente contacto.
            Si no → crear PendingNotification + actualizar llamada del
                    llamante con <Connect><Stream> para que María informe
                    y ofrezca dejar un mensaje de voz.

        - Cualquier otro estado → registrar e ignorar (estados intermedios
          no terminales).
    """

    FAILED_STATUSES = {"no-answer", "busy", "failed", "canceled"}

    def _get_wss_url(self) -> str:
        """
        Reads the active ngrok HTTPS URL from the shared session file and
        converts it to a WSS URL for the <Stream> TwiML verb.
        ---
        Lee la URL HTTPS activa de ngrok del archivo de sesión compartido y
        la convierte en URL WSS para el verbo TwiML <Stream>.
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
                "[CONTACT-STATUS] No se pudo leer NGROK_URL.txt. "
                f"Usando wss_url por defecto: {fallback}"
            )
            return fallback

    def _twiml_reconnect_alia(self, wss_url: str) -> str:
        """
        Returns TwiML that opens a new bidirectional Media Stream to reconnect
        María to the caller after a failed transfer attempt.
        ---
        Devuelve TwiML que abre un nuevo Media Stream bidireccional para
        reconectar a María con el llamante tras un intento de transferencia fallido.
        """
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Connect>'
            f'<Stream url="{wss_url}/media" />'
            '</Connect>'
            '</Response>'
        )

    def post(self, request, *args, **kwargs):
        """
        Processes the terminal status of the outbound call to the section
        contact and drives the resilient multi-contact transfer flow.
        ---
        Procesa el estado terminal de la llamada saliente al contacto de
        sección y dirige el flujo de transferencia resiliente multi-contacto.
        """
        import os
        from twilio.rest import Client as _TwilioClient
        from ivr_config.models import (
            SectionContact      as _SectionContact,
            TransferAttempt     as _TransferAttempt,
            PendingNotification as _PendingNotification,
        )

        call_status     = request.POST.get("CallStatus", "unknown")
        caller_call_sid = kwargs.get("caller_call_sid", "")

        logger.info(
            f"[CONTACT-STATUS] Webhook recibido — caller_call_sid={caller_call_sid} "
            f"| CallStatus='{call_status}'."
        )

        terminal_states = {"completed"} | self.FAILED_STATUSES
        if call_status not in terminal_states:
            logger.info(
                f"[CONTACT-STATUS] Estado no terminal '{call_status}' — ignorado."
            )
            return HttpResponse("", status=200)

        try:
            attempt = _TransferAttempt.objects.select_related("section").get(
                call_sid=caller_call_sid
            )
        except _TransferAttempt.DoesNotExist:
            logger.error(
                f"[CONTACT-STATUS] TransferAttempt no encontrado para "
                f"caller_call_sid={caller_call_sid}. No se puede procesar."
            )
            return HttpResponse("", status=200)

        if call_status == "completed":
            attempt.status = _TransferAttempt.STATUS_COMPLETED
            attempt.save(update_fields=["status", "updated_at"])
            logger.info(
                f"[CONTACT-STATUS] Llamada saliente completada — "
                f"TransferAttempt marcado COMPLETED para call_sid={caller_call_sid}."
            )
            return HttpResponse("", status=200)

        next_index = attempt.contact_index + 1
        attempt.contact_index = next_index
        attempt.status        = _TransferAttempt.STATUS_FAILED
        attempt.save(update_fields=["contact_index", "status", "updated_at"])

        logger.info(
            f"[CONTACT-STATUS] Contacto no contestó (status='{call_status}') — "
            f"caller_call_sid={caller_call_sid} | próximo contact_index={next_index}."
        )

        next_contacts_list = list(
            _SectionContact.objects.select_related("contact")
            .filter(section=attempt.section)
            .exclude(contact__phone_number="")
            .order_by("priority", "contact__name")
        )

        if next_index < len(next_contacts_list):
            next_contact = next_contacts_list[next_index].contact
            logger.info(
                f"[CONTACT-STATUS] Siguiente contacto disponible: "
                f"'{next_contact.name}' — reconectando a María vía calls.update()."
            )
        else:
            logger.info(
                f"[CONTACT-STATUS] Sin más contactos para "
                f"caller_call_sid={caller_call_sid}. "
                f"Creando PendingNotification y reconectando a María."
            )
            try:
                _PendingNotification.objects.create(
                    company=attempt.section.company if attempt.section else None,
                    section=attempt.section,
                    caller_number=attempt.caller_number,
                    call_sid=caller_call_sid,
                    channel=_PendingNotification.CHANNEL_PENDING,
                )
                logger.info(
                    f"[CONTACT-STATUS] PendingNotification creada — "
                    f"caller={attempt.caller_number} | call_sid={caller_call_sid}."
                )
            except Exception as notify_exc:
                logger.error(
                    f"[CONTACT-STATUS] Error al crear PendingNotification: "
                    f"{type(notify_exc).__name__}: {notify_exc}",
                    exc_info=True,
                )

        try:
            twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
            twilio_api_key     = os.environ.get("TWILIO_API_KEY_SID_IE1", "")
            twilio_api_secret  = os.environ.get("TWILIO_API_KEY_SECRET_IE1", "")
            twilio_client      = _TwilioClient(
                twilio_api_key,
                twilio_api_secret,
                account_sid=twilio_account_sid,
            )
            twilio_client.calls(caller_call_sid).update(
                twiml=self._twiml_reconnect_alia(self._get_wss_url()),
            )
            logger.info(
                f"[CONTACT-STATUS] Llamada {caller_call_sid} actualizada con "
                f"TwiML de reconexión de María vía REST API."
            )
        except Exception as twilio_exc:
            logger.error(
                f"[CONTACT-STATUS] Error al actualizar llamada via REST API: "
                f"{type(twilio_exc).__name__}: {twilio_exc}",
                exc_info=True,
            )

        return HttpResponse("", status=200)


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
