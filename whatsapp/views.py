
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/views.py
"""
Views for the whatsapp channel app.
Implements two CSRF-exempt webhook endpoints:
  - IncomingWhatsAppView: handles inbound user messages (text and location)
    and dispatches chatbot replies. Location messages (Latitude/Longitude in
    Twilio POST) are detected, stored in WhatsAppMessage with
    message_type='location', and propagated to WhatsAppSession for context
    enrichment in the Gemini system prompt.
    Gemini replies are parsed for the [TARGET_SECTION:{...}] marker (Paso 21):
    when detected, WhatsAppSession.target_section is updated and the marker is
    stripped from the reply before dispatching to the user.
  - PresenceWhatsAppView: handles presence reminder responses
    (1h / 2h / disponible).
Both views are synchronous Django WSGI views — no aiohttp or WebSocket
required.

Updated in Paso 19 (2026-04-16): location message detection and propagation.
Updated in Paso 21 (2026-04-20): target section detection and registration.
---
Vistas para la app del canal WhatsApp.
Implementa dos endpoints webhook exentos de CSRF:
  - IncomingWhatsAppView: gestiona mensajes entrantes del usuario (texto y
    ubicación) y despacha respuestas del chatbot. Los mensajes de ubicación
    (Latitude/Longitude en el POST de Twilio) se detectan, se almacenan en
    WhatsAppMessage con
    message_type='location' y se propagan a WhatsAppSession para enriquecer el
    contexto en el system prompt de Gemini.
    Las respuestas de Gemini se analizan en busca del marcador
    [TARGET_SECTION:{...}] (Paso 21): cuando se detecta, se actualiza
    WhatsAppSession.target_section y el marcador se elimina de la respuesta
    antes de despacharla al usuario.
  - PresenceWhatsAppView: gestiona respuestas a recordatorios de presencia
    (1h / 2h / disponible).
Ambas vistas son vistas síncronas Django WSGI — no se requiere aiohttp ni
WebSocket.

Actualizado en el Paso 19 (2026-04-16): detección y propagación de mensajes
de ubicación.
Actualizado en el Paso 21 (2026-04-20): detección y registro de sección
destino.
"""

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ivr_config.models import PhoneNumber, Section
from .models import WhatsAppMessage, WhatsAppSession
from .services import (
    BreakdownAgentService,
    OnboardingService,
    PresenceResponseService,
    WhatsAppChatService,
)

logger = logging.getLogger(__name__)


# Nombre de archivo que WhatsApp pone en Body al enviar un adjunto como
# documento (S127): una sola línea terminada en extensión de foto o PDF.
_ATTACHMENT_NAME_RE = re.compile(
    r"^[^\r\n]{1,200}\.(jpe?g|png|gif|webp|heic|heif|bmp|tiff?|pdf)$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# INCOMING WHATSAPP VIEW
# Handles inbound user messages and dispatches chatbot replies via Gemini.
# Gestiona mensajes entrantes del usuario y despacha respuestas del chatbot
# vía Gemini.
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class IncomingWhatsAppView(View):
    """
    Webhook endpoint: POST /api/whatsapp/incoming/
    Receives inbound WhatsApp messages from Twilio, resolves the target
    company from the destination number, manages the WhatsAppSession and
    message history, invokes WhatsAppChatService to obtain a Gemini reply,
    persists both the inbound and outbound messages, and dispatches the reply
    via Twilio.
    Returns HTTP 200 with an empty body on success — Twilio does not require
    a TwiML response for WhatsApp messaging webhooks.
    ---
    Endpoint webhook: POST /api/whatsapp/incoming/
    Recibe mensajes entrantes de WhatsApp de Twilio, resuelve la empresa
    destino desde el número de destino, gestiona la WhatsAppSession y el
    historial de mensajes, invoca WhatsAppChatService para obtener una
    respuesta de Gemini, persiste los mensajes entrante y saliente, y
    despacha la respuesta vía Twilio.
    Devuelve HTTP 200 con cuerpo vacío en caso de éxito — Twilio no requiere
    una respuesta TwiML para los webhooks de mensajería WhatsApp.
    """

    def post(self, request, *args, **kwargs):
        """
        Main POST handler for inbound WhatsApp messages.
        Orchestrates the full chatbot pipeline: resolve → session → prompt →
        history → gemini → persist → dispatch.
        ---
        Manejador POST principal para mensajes entrantes de WhatsApp.
        Orquesta el pipeline completo del chatbot: resolver → sesión → prompt →
        historial → gemini → persistir → despachar.
        """
        # --- Step 1: Extract Twilio webhook parameters. ---
        # Twilio sends Latitude and Longitude as separate POST fields when the
        # user shares a native WhatsApp location message. In that case Body may
        # be empty or contain only the label text set by the user. We classify
        # the message as 'location' when Latitude is present and non-empty.
        # --- Paso 1: Extraer parámetros del webhook de Twilio. ---
        # Twilio envía Latitude y Longitude como campos POST separados cuando
        # el usuario comparte un mensaje de ubicación nativo de WhatsApp. En
        # ese caso Body puede estar vacío o contener solo el texto de etiqueta
        # del usuario. Clasificamos el mensaje como 'location' cuando Latitude
        # está presente y no está vacío.
        from_number = request.POST.get("From", "").replace("whatsapp:", "")
        to_number = request.POST.get("To", "").replace("whatsapp:", "")
        body = request.POST.get("Body", "").strip()
        raw_latitude = request.POST.get("Latitude", "").strip()
        raw_longitude = request.POST.get("Longitude", "").strip()
        is_location_msg = bool(raw_latitude)
        # H30 (S125): adjunto (foto o PDF). WhatsApp manda uno por mensaje.
        try:
            num_media = int(request.POST.get("NumMedia", "0") or 0)
        except ValueError:
            num_media = 0

        logger.info(
            "# [WHATSAPP] Mensaje entrante de %s a %s: '%s' "
            "[location=%s lat=%s lon=%s]",
            from_number,
            to_number,
            body[:80],
            is_location_msg,
            raw_latitude,
            raw_longitude,
        )

        # A message must have either a body or location coordinates to be
        # processed.
        # Un mensaje debe tener cuerpo o coordenadas de ubicación para ser
        # procesado.
        if not from_number or not to_number or (
            not body and not is_location_msg and not num_media
        ):
            logger.warning(
                "# [WHATSAPP] Parámetros incompletos en webhook entrante. "
                "From=%s To=%s Body=%s Latitude=%s",
                from_number,
                to_number,
                repr(body),
                repr(raw_latitude),
            )
            return HttpResponse(status=200)

        # --- Step 2: Resolve company from destination number. ---
        # --- Paso 2: Resolver empresa desde el número de destino. ---
        try:
            phone_number_record = PhoneNumber.objects.select_related(
                "company",
            ).get(
                number=to_number,
                is_active=True,
                capabilities__in=[
                    PhoneNumber.CAPABILITY_WHATSAPP,
                    PhoneNumber.CAPABILITY_BOTH,
                ],
            )
            company = phone_number_record.company

        except PhoneNumber.DoesNotExist:
            logger.error(
                "# [WHATSAPP] Número destino no registrado o sin capacidad "
                "WhatsApp: %s",
                to_number,
            )
            return HttpResponse(status=200)

        except PhoneNumber.MultipleObjectsReturned:
            logger.error(
                "# [WHATSAPP] Múltiples PhoneNumber activos para: %s",
                to_number,
            )
            return HttpResponse(status=200)

        # --- Step 2a (H30, S127): 24-hour window, for EVERY inbound
        # message. ---
        # Before any early return (attachments never reach WhatsAppMessage):
        # notifications read it to send plain text instead of a template.
        # --- Paso 2a (H30, S127): ventana de 24 h, para TODO entrante. ---
        # Antes de cualquier salida temprana (los adjuntos nunca llegan a
        # WhatsAppMessage): las notificaciones la leen para enviar texto
        # libre en vez de plantilla.
        from whatsapp.window_service import record_inbound

        record_inbound(company, from_number)

        # --- Step 2a-bis (H37, S133): giving a service. ---
        # An assistance supervisor (or admin) giving a service by
        # WhatsApp: text or photo of the service. Decided here, answered
        # in Celery (budgets.service_intake).
        # --- Paso 2a-bis (H37, S133): dar un servicio. ---
        # Un supervisor de asistencia (o administrador) que da un servicio
        # por WhatsApp: texto o foto del servicio. Se decide aquí y se
        # contesta en Celery (budgets.service_intake).
        from budgets.service_intake import claim_whatsapp, service_giver
        from ivr_config.models import Contact as _ServiceContact

        _service_contact = _ServiceContact.objects.filter(
            company=company, phone_number=from_number,
        ).select_related("company_user").first()
        _service_body = (
            "" if body and _ATTACHMENT_NAME_RE.match(body) else body
        )
        _intake = (
            claim_whatsapp(company, _service_contact, from_number)
            if _service_contact is not None else None
        )
        _service_media = (
            request.POST.get("MediaContentType0", "") if num_media else ""
        )
        _service_doc = (
            _service_media.startswith("image/")
            or _service_media == "application/pdf"
        )
        if (
            _intake is None and _service_contact is not None
            and service_giver(_service_contact.company_user)
            and _service_doc
        ):
            # A photo or PDF of whoever gives services opens the service
            # conversation at once (so a text sent right after waits for
            # it); the same Gemini read says if it is a service or a
            # document for Documentación. Never by keywords.
            # Foto o PDF de quien da servicios: abre la conversación ya
            # (un texto mandado justo después espera a su lectura) y la
            # misma lectura de Gemini dice si es un servicio o un
            # documento para Documentación. Nunca por palabras clave.
            from budgets.service_intake import start_from_assistant

            _intake = start_from_assistant(
                _service_contact.company_user, from_number,
            )
            _service_decide = True
        else:
            _service_decide = False
        if _intake is not None and _service_doc:
            from budgets.service_intake import mark_reading

            mark_reading(_intake)
        if _intake is not None:
            from whatsapp.tasks import service_intake_reply

            _service_session = WhatsAppSession.objects.filter(
                company=company, phone_number=from_number, is_active=True,
            ).order_by("-session_start").first()
            if _service_session is None:
                _service_session = WhatsAppSession.objects.create(
                    company=company, phone_number=from_number,
                    is_active=True,
                )
            WhatsAppMessage.objects.create(
                session=_service_session,
                direction=WhatsAppMessage.DIRECTION_IN,
                body=_service_body or "[adjunto]",
                message_type=WhatsAppMessage.MESSAGE_TYPE_TEXT,
            )
            service_intake_reply.delay(
                _intake.pk, _service_body,
                request.POST.get("MediaUrl0", "") if num_media else "",
                request.POST.get("MediaContentType0", "") if num_media
                else "",
                to_number, from_number, decide=_service_decide,
            )
            return HttpResponse(status=200)

        # --- Step 2b (H30, S125): worker attachments, before anything
        # else. ---
        # Every attachment from a phone that belongs to a worker is recorded
        # and checked (Celery) against the documents asked to that worker,
        # whatever the conversation state: late answer, other messages in
        # between, breakdown ticket opened before. Any text that comes with
        # it follows the normal flow below.
        # --- Paso 2b (H30, S125): adjuntos de trabajadores, antes que
        # nada. ---
        # Todo adjunto de un teléfono que es de un trabajador se registra y
        # se comprueba (Celery) contra lo que se le ha pedido, en cualquier
        # estado de la conversación. El texto que lo acompañe sigue el
        # camino normal de abajo.
        if num_media:
            from document_explorer.person_phone_service import (
                resolve_person_by_phone,
            )
            from document_explorer.worker_request_service import (
                expects_media, register_incoming_media,
            )

            # Con acceso al panel, siempre; sin acceso, solo si responde
            # a algo que le hemos pedido (S126, corrige S125).
            _media_person = resolve_person_by_phone(company, from_number)
            if _media_person is not None and expects_media(_media_person):
                register_incoming_media(
                    _media_person, from_number, request.POST
                )
            else:
                logger.warning(
                    "# [WHATSAPP] Adjunto de %s: %s -- no se procesa.",
                    from_number,
                    "trabajador sin acceso al panel y sin nada pedido"
                    if _media_person
                    else "el teléfono no es de ningún trabajador",
                )
            # S127, incidente real: un adjunto enviado como documento trae
            # su nombre de archivo en Body ("anverso.jpg"), y ese "texto"
            # llegaba al chatbot, que contestaba "¿a qué máquina
            # corresponden estas imágenes?" encima de la solicitud. El
            # nombre de archivo no es texto del trabajador: se descarta.
            if body and _ATTACHMENT_NAME_RE.match(body):
                logger.info(
                    "# [WHATSAPP] Body de %s es el nombre del adjunto (%r) "
                    "-- no se pasa al chatbot.", from_number, body,
                )
                body = ""
            if not body and not is_location_msg:
                return HttpResponse(status=200)

        # --- Step 3: Resolve or create active WhatsAppSession. ---
        # --- Paso 3: Resolver o crear WhatsAppSession activa. ---
        session = WhatsAppSession.objects.filter(
            company=company,
            phone_number=from_number,
            is_active=True,
        ).order_by("-session_start").first()

        if session is None:
            session = WhatsAppSession.objects.create(
                company=company,
                phone_number=from_number,
                is_active=True,
            )
            logger.info(
                "# [WHATSAPP] Nueva sesión creada para %s — empresa: %s",
                from_number,
                company.name,
            )
        else:
            # Touch the session to refresh last_message_at (auto_now=True).
            # Tocar la sesión para refrescar last_message_at (auto_now=True).
            session.save(update_fields=["last_message_at"])

        # --- Step 4: Persist inbound message with type and coordinates. ---
        # For location messages, latitude and longitude are stored on the
        # message record in addition to the body label (which may be empty).
        # --- Paso 4: Persistir mensaje entrante con tipo y coordenadas. ---
        # Para mensajes de ubicación, latitude y longitude se almacenan en el
        # registro de mensaje además de la etiqueta de cuerpo (que puede estar
        # vacía).
        msg_latitude = None
        msg_longitude = None

        if is_location_msg:
            try:
                msg_latitude = Decimal(raw_latitude)
                msg_longitude = Decimal(raw_longitude)
            except InvalidOperation:
                logger.warning(
                    "# [WHATSAPP] Coordenadas de ubicación con formato "
                    "inválido: "
                    "lat=%s lon=%s — se almacenan como None.",
                    raw_latitude,
                    raw_longitude,
                )

        WhatsAppMessage.objects.create(
            session=session,
            direction=WhatsAppMessage.DIRECTION_IN,
            body=body,
            message_type=(
                WhatsAppMessage.MESSAGE_TYPE_LOCATION
                if is_location_msg
                else WhatsAppMessage.MESSAGE_TYPE_TEXT
            ),
            latitude=msg_latitude,
            longitude=msg_longitude,
        )

        # --- Step 4b: Propagate location to WhatsAppSession (Paso 19). ---
        # When a location message is received, update the session with the
        # caller's coordinates and timestamp. Existing coordinates are
        # overwritten with the most recent location shared by the user during
        # the session. The location_address field is left blank here — it may
        # be resolved by Grounding with Google Maps in Paso 20.
        # --- Paso 4b: Propagar ubicación a WhatsAppSession (Paso 19). ---
        # Cuando se recibe un mensaje de ubicación, actualizar la sesión con
        # las coordenadas del llamante y la marca de tiempo. Las coordenadas
        # existentes se sobreescriben con la ubicación más reciente compartida
        # por el usuario durante la sesión. El campo location_address se deja
        # en blanco aquí — puede resolverse mediante Grounding con Google Maps
        # en el Paso 20.
        if is_location_msg and msg_latitude is not None:
            session.latitude = msg_latitude
            session.longitude = msg_longitude
            session.location_captured_at = now()
            session.save(update_fields=[
                "latitude",
                "longitude",
                "location_captured_at",
                "last_message_at",
            ])
            logger.info(
                "# [WHATSAPP] Ubicación propagada a sesión %s: lat=%s lon=%s",
                session.pk,
                msg_latitude,
                msg_longitude,
            )

        # --- Step 4b-bis: Handle ButtonPayload for chat_session_renewal —
        # Hito 13, Paso 10. ---
        # Intercepts Quick Reply button presses from the chat_session_renewal
        # template BEFORE the IRC dispatcher and the Hito 4 chatbot pipeline.
        # Two payloads:
        #   opt_in  — reactivates the WhatsApp session window for the contact.
        #   opt_out — sets contact.opt_out_broadcast = True to exclude from
        #             broadcasts.
        # Both branches return HTTP 200 immediately, consuming the message.
        # EXCEPTION: if the contact is in AWAITING_BREAKDOWN_CONFIRM state, the
        # opt_in payload is the breakdown confirmation Quick Reply — do NOT
        # intercept here; let the IRC dispatcher handle it via
        # _resolve_pending_routing.
        # --- Paso 4b-bis: Gestionar ButtonPayload para chat_session_renewal —
        # Hito 13, Paso 10. ---
        # Intercepta pulsaciones de botón Quick Reply del template
        # chat_session_renewal ANTES del despachador IRC y del pipeline del
        # chatbot del Hito 4. Dos payloads:
        #   opt_in  — reactiva la ventana de sesión WhatsApp del contacto.
        #   opt_out — establece contact.opt_out_broadcast = True para
        #             excluirle de broadcasts.
        # Ambas ramas devuelven HTTP 200 inmediatamente, consumiendo el
        # mensaje.
        # EXCEPCIÓN: si el contacto está en estado AWAITING_BREAKDOWN_CONFIRM,
        # el payload opt_in corresponde al Quick Reply de confirmación de
        # avería — NO interceptar aquí; dejar que el despachador IRC lo
        # gestione a través de _resolve_pending_routing.
        _button_payload = request.POST.get("ButtonPayload", "").strip()
        _skip_opt_for_breakdown = False
        if _button_payload == "opt_in":
            from ivr_config.models import Contact as _ContactCheck
            _contact_check = _ContactCheck.objects.filter(
                company=company, phone_number=from_number,
            ).only("routing_state").first()
            if (_contact_check is not None
                    and _contact_check.routing_state
                    == _ContactCheck.ROUTING_STATE_AWAITING_BREAKDOWN_CONFIRM):
                _skip_opt_for_breakdown = True
        if (
            _button_payload in ("opt_in", "opt_out")
            and not _skip_opt_for_breakdown
        ):
            if _button_payload == "opt_in":
                # Reactivate the WhatsApp session window for this operator.
                # Reactivar la ventana de sesión WhatsApp para este operario.
                WhatsAppSession.objects.filter(
                    company=company,
                    phone_number=from_number,
                ).update(is_active=True, last_message_at=now())

                # Deliver pending albarán links if any are queued for this
                # operator.
                # Entregar los enlaces de albarán pendientes si hay alguno en
                # cola.
                _active_session = WhatsAppSession.objects.filter(
                    company=company,
                    phone_number=from_number,
                    is_active=True,
                ).order_by("-session_start").first()

                _pending_units = (
                    _active_session.pending_albaran_units
                    if _active_session
                    else []
                ) or []

                if _pending_units:
                    from budgets.models import WorkOrderAssistanceUnit as _WAU

                    # Build and send one message per pending unit.
                    # Construir y enviar un mensaje por cada unidad pendiente.
                    _delivered_pks = []
                    for _unit_pk in _pending_units:
                        try:
                            _unit = _WAU.objects.select_related(
                                "work_order__insurer",
                            ).get(pk=_unit_pk)
                            from whatsapp.services import albaran_link_text
                            _msg = albaran_link_text(_unit)
                            WhatsAppChatService.send_reply(
                                from_number=to_number,
                                to_number=from_number,
                                reply_text=_msg,
                            )
                            # Mark unit as DOWNLOADED when operator receives
                            # the link.
                            # Marcar la unidad como DOWNLOADED cuando el
                            # operario recibe el enlace.
                            _previous_status = _unit.status
                            _unit.status = _WAU.STATUS_DOWNLOADED
                            _unit.downloaded_at = now()
                            _unit.save(
                                update_fields=["status", "downloaded_at"]
                            )
                            # H37 (S133): audit trail of the change.
                            # Registro de auditoría del cambio.
                            from budgets.models import (
                                WorkOrderAssistanceUnitEvent as _WAUE,
                            )
                            _WAUE.status_change(
                                _unit, _previous_status, _unit.status,
                                detail="Enlace del albarán entregado.",
                            )
                            _delivered_pks.append(_unit_pk)
                            logger.info(
                                "# [ALBARAN NOTIFY] Enlace albarán pk=%s "
                                "entregado a %s.",
                                _unit_pk,
                                from_number,
                            )
                        except _WAU.DoesNotExist:
                            logger.warning(
                                "# [ALBARAN NOTIFY] Unidad pk=%s no "
                                "encontrada — ignorada en entrega opt_in.",
                                _unit_pk,
                            )
                        except Exception as _exc:
                            logger.error(
                                "# [ALBARAN NOTIFY] Error entregando "
                                "albarán pk=%s a %s: %s",
                                _unit_pk,
                                from_number,
                                _exc,
                            )

                    # Clear delivered units from the queue.
                    # Vaciar las unidades entregadas de la cola.
                    if _active_session and _delivered_pks:
                        remaining = [
                            pk for pk in _pending_units
                            if pk not in _delivered_pks
                        ]
                        _active_session.pending_albaran_units = remaining
                        _active_session.save(
                            update_fields=["pending_albaran_units"]
                        )
                # Deliver pending broadcast messages queued while outside 24h
                # window. Messages older than 48h are discarded — considered
                # expired.
                # ---
                # Entregar mensajes de circular pendientes encolados fuera de
                # la ventana. Los mensajes con más de 48h se descartan — se
                # consideran expirados.
                if _active_session:
                    from datetime import (
                        timedelta as _td_bc_opt,
                        datetime as _dt_bc_opt,
                    )
                    _pending_bc = list(
                        _active_session.pending_broadcast_messages or []
                    )
                    if _pending_bc:
                        _expiry_threshold = now() - _td_bc_opt(hours=48)
                        _bc_remaining = []
                        for _bc_msg in _pending_bc:
                            _bc_body = _bc_msg.get("body", "")
                            _bc_created_raw = _bc_msg.get("created_at", "")
                            # Parse created_at and check expiry.
                            # Parsear created_at y comprobar expiración.
                            try:
                                _bc_created = _dt_bc_opt.fromisoformat(
                                    _bc_created_raw
                                )
                                # Make offset-naive for comparison if needed.
                                if _bc_created.tzinfo is None:
                                    from django.utils.timezone import (
                                        make_aware as _make_aware,
                                    )
                                    _bc_created = _make_aware(_bc_created)
                            except (ValueError, TypeError):
                                # Unknown age — treat as fresh.
                                _bc_created = now()
                            if _bc_created < _expiry_threshold:
                                logger.info(
                                    "# [WHATSAPP] Mensaje de circular "
                                    "expirado (>48h) para %s — descartado.",
                                    from_number,
                                )
                                continue  # Discard expired message.
                            if not _bc_body:
                                continue
                            # Deliver the broadcast message and persist
                            # it as OUTBOUND in the section's ChatRoom.
                            # Entregar el mensaje de circular y persistirlo
                            # como OUTBOUND en la ChatRoom de la sección.
                            try:
                                WhatsAppChatService.send_reply(
                                    from_number=to_number,
                                    to_number=from_number,
                                    reply_text=_bc_body,
                                )
                                logger.info(
                                    "# [WHATSAPP] Mensaje de circular "
                                    "entregado a %s tras opt_in.",
                                    from_number,
                                )
                            except Exception as _bc_exc:
                                logger.error(
                                    "# [WHATSAPP] Error entregando circular "
                                    "a %s: %s",
                                    from_number, _bc_exc,
                                )
                                # Keep for retry.
                                _bc_remaining.append(_bc_msg)
                        # Clear delivered messages; keep only failed ones.
                        # Vaciar mensajes entregados; conservar solo los
                        # fallidos.
                        _active_session.pending_broadcast_messages = (
                            _bc_remaining
                        )
                        _active_session.save(
                            update_fields=["pending_broadcast_messages"]
                        )

                logger.info(
                    "# [WHATSAPP] opt_in procesado para %s — sesión "
                    "reactivada.",
                    from_number,
                )
            else:  # opt_out
                from ivr_config.models import Contact as _Contact
                _opt_contact = _Contact.objects.filter(
                    company=company,
                    phone_number=from_number,
                ).first()
                if _opt_contact is not None:
                    _opt_contact.opt_out_broadcast = True
                    _opt_contact.save(update_fields=["opt_out_broadcast"])
                try:
                    WhatsAppChatService.send_reply(
                        from_number=to_number,
                        to_number=from_number,
                        reply_text=(
                            "De acuerdo, no recibirás más mensajes del grupo."
                        ),
                    )
                except Exception as _exc:
                    logger.error(
                        "# [WHATSAPP] Error enviando confirmación opt_out a "
                        "%s: %s",
                        from_number, _exc,
                    )
                logger.info(
                    "# [WHATSAPP] opt_out procesado para %s — excluido de "
                    "broadcasts.",
                    from_number,
                )
            return HttpResponse(status=200)

        # --- Step 4b-ter: Handle ButtonPayload for circular_notification —
        # H31, S115. ---
        # Intercepts the "Leer aquí" Quick Reply of the circular_notification
        # template BEFORE the IRC dispatcher, same principle as opt_in/opt_out
        # above. Resolves the most recent unconfirmed WhatsApp
        # DocumentAcknowledgment for the sender's PersonIdentity (matched by
        # phone), replies with the plain-text content of the circular, and
        # marks it as read (whatsapp_read_at). If no pending circular is
        # found (button pressed twice, or after the 24h window), replies with
        # a short explanatory message instead of failing silently.
        # --- Paso 4b-ter: Gestionar ButtonPayload de circular_notification —
        # H31, S115. ---
        # Intercepta el Quick Reply "Leer aquí" de la plantilla
        # circular_notification ANTES del despachador IRC, mismo principio
        # que opt_in/opt_out arriba. Resuelve el DocumentAcknowledgment de
        # WhatsApp más reciente sin confirmar de la PersonIdentity del
        # remitente (emparejada por teléfono), responde con el texto plano de
        # la circular y lo marca como leído (whatsapp_read_at). Si no hay
        # ninguna circular pendiente (botón pulsado dos veces, o fuera de la
        # ventana de 24h), responde con un mensaje explicativo breve en vez
        # de fallar en silencio.
        if _button_payload == "leer_aqui_circular":
            from bs4 import BeautifulSoup
            from document_explorer.models import (
                DocumentAcknowledgment as _DocAck,
            )
            from document_explorer.person_phone_service import (
                resolve_person_by_phone,
            )
            from panel.views_circulars_h31 import _render_document_variables

            # S125: por los 9 dígitos normalizados -- la ficha guarda el
            # móvil sin +34 y la comparación literal no casaba nunca.
            _person = resolve_person_by_phone(company, from_number)
            _pending_ack = (
                _DocAck.objects.filter(
                    person=_person,
                    channel=_DocAck.CHANNEL_WHATSAPP,
                    whatsapp_read_at__isnull=True,
                ).select_related(
                    "document_type", "worksite"
                ).order_by("-created_at").first()
                if _person is not None else None
            )
            if _pending_ack is not None:
                from document_explorer.epi_delivery_document_service import (
                    resolve_company_fiscal_profile,
                )

                _company_profile = resolve_company_fiscal_profile(
                    _person.employer_company
                )
                _rendered_html = _render_document_variables(
                    _pending_ack.document_type.content_html,
                    worker=_person,
                    administrator=(
                        _company_profile.administrator
                        if _company_profile else None
                    ),
                    company=_company_profile,
                    worksite=_pending_ack.worksite,
                )
                _plain_text = BeautifulSoup(
                    _rendered_html, "html.parser",
                ).get_text(separator="\n").strip()
                _reply_text = (
                    f"*{_pending_ack.document_type.label}*\n\n{_plain_text}"
                )
                _pending_ack.whatsapp_read_at = now()
                _pending_ack.save(update_fields=["whatsapp_read_at"])
            else:
                _reply_text = (
                    "No he encontrado ninguna circular pendiente de lectura "
                    "asociada a este número. Si crees que es un error, "
                    "contacta con tu responsable."
                )
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=_reply_text,
                )
            except Exception as _exc:
                logger.error(
                    "# [WHATSAPP] Error enviando circular a %s: %s",
                    from_number, _exc,
                )
            logger.info(
                "# [WHATSAPP] leer_aqui_circular procesado para %s — "
                "ack pk=%s.",
                from_number,
                _pending_ack.pk if _pending_ack is not None else None,
            )
            return HttpResponse(status=200)

        # ==================================================================
        # --- Step 5 (H17): Route by sender identity. ---
        # Bifurcación H17: enrutar según identidad del remitente.
        #
        # Three branches:
        #   A) Internal Contact with open ticket → breakdown agent (continue)
        #   B) Internal Contact without open ticket → breakdown agent (new)
        #      or help branch (Gemini decides from message intent)
        #   C) Unknown number with onboarding in progress → onboarding step
        #   D) Unknown number → generic chatbot OR onboarding trigger
        # ==================================================================

        from ivr_config.models import Contact as _Contact
        from chat.models import BreakdownTicket as _BT

        _internal_contact = _Contact.objects.filter(
            company=company,
            phone_number=from_number,
        ).select_related("company_user").first()

        # ------------------------------------------------------------------
        # BRANCH A/B — Internal Contact: breakdown agent or help chatbot.
        # RAMA A/B — Contact interno: agente de averías o chatbot de ayuda.
        # ------------------------------------------------------------------
        if _internal_contact is not None:

            # Resolve open ticket for this contact (OPEN or IN_PROGRESS).
            # Resolver ticket abierto para este contacto (OPEN o IN_PROGRESS).
            _open_ticket = _BT.objects.filter(
                contact=_internal_contact,
                company=company,
                status__in=[_BT.STATUS_OPEN, _BT.STATUS_IN_PROGRESS],
            ).order_by("-created_at").first()

            # Effective user message — synthesise for pure location messages.
            # Mensaje de usuario efectivo — sintetizar para mensajes de
            # ubicación puros.
            _effective_msg = body if body else (
                "El trabajador acaba de compartir su ubicación geográfica."
                if is_location_msg else ""
            )

            if _open_ticket is not None:
                # --- Branch A: continue breakdown conversation. ---
                # --- Rama A: continuar conversación de avería. ---
                logger.info(
                    "# [WHATSAPP H17] Contact interno %s — ticket abierto "
                    "pk=%s. Rama: BREAKDOWN AGENT (continuar).",
                    from_number,
                    _open_ticket.pk,
                )

                # H17 Paso 5 — Persist GPS location on ticket when received.
                # If the inbound message is a location share and the ticket
                # does not yet have coordinates, store geo_lat/geo_lng and
                # append a SYSTEM entry to conversation_log.
                # H17 Paso 5 — Persistir ubicación GPS en ticket al recibirla.
                # Si el mensaje entrante es una ubicación y el ticket aún no
                # tiene coordenadas, guardar geo_lat/geo_lng y añadir entrada
                # SYSTEM al conversation_log.
                if is_location_msg and msg_latitude is not None:
                    _geo_fields = []
                    if _open_ticket.geo_lat is None:
                        _open_ticket.geo_lat = msg_latitude
                        _geo_fields.append("geo_lat")
                    if _open_ticket.geo_lng is None:
                        _open_ticket.geo_lng = msg_longitude
                        _geo_fields.append("geo_lng")
                    if _geo_fields:
                        _geo_fields.append("updated_at")
                        _open_ticket.save(update_fields=_geo_fields)
                        BreakdownAgentService.append_log(
                            _open_ticket,
                            "SYSTEM",
                            (
                                f"Ubicación GPS recibida vía WhatsApp: "
                                f"lat={msg_latitude}, lng={msg_longitude}."
                            ),
                        )
                        logger.info(
                            "# [WHATSAPP H17] GPS persistido en ticket "
                            "pk=%s: lat=%s lng=%s.",
                            _open_ticket.pk,
                            msg_latitude,
                            msg_longitude,
                        )

                _system_prompt = BreakdownAgentService.build_system_prompt(
                    contact=_internal_contact,
                    ticket=_open_ticket,
                    company=company,
                )
                _history = BreakdownAgentService.build_history_from_log(
                    _open_ticket
                )
                try:
                    _reply_raw = BreakdownAgentService.get_gemini_reply(
                        system_prompt=_system_prompt,
                        history=_history,
                        user_message=_effective_msg,
                    )
                except Exception as _exc:
                    logger.error(
                        "# [WHATSAPP H17] Error Gemini avería (ticket pk=%s): "
                        "%s",
                        _open_ticket.pk, _exc,
                    )
                    _reply_raw = (
                        "Lo sentimos, ha habido un problema al procesar tu "
                        "mensaje. "
                        "Por favor, inténtalo de nuevo."
                    )
                # Persist USER turn in conversation_log.
                # Persistir turno USER en conversation_log.
                BreakdownAgentService.append_log(
                    _open_ticket, "USER", _effective_msg,
                )
                # Parse and apply TICKET_DATA marker; get clean reply.
                # Parsear y aplicar marcador TICKET_DATA; obtener respuesta
                # limpia.
                reply_text = (
                    BreakdownAgentService.parse_and_apply_ticket_data(
                        _reply_raw, _open_ticket,
                    )
                )
                # Persist MODEL turn in conversation_log.
                # Persistir turno MODEL en conversation_log.
                BreakdownAgentService.append_log(
                    _open_ticket, "MODEL", reply_text,
                )

            else:
                # --- Branch B: no open ticket. ---
                # Gemini decides from message intent: breakdown or help.
                # Gemini decide por intención del mensaje: avería o ayuda.
                # Build a unified prompt that handles both intents naturally.
                # Construir un prompt unificado que gestione ambas intenciones.
                logger.info(
                    "# [WHATSAPP H17] Contact interno %s — sin ticket "
                    "abierto. Rama: BREAKDOWN/HELP decision.",
                    from_number,
                )
                _sections_list = ", ".join(
                    s.name for s in company.sections.filter(is_active=True)
                )
                _b_system_prompt = (
                    f"Eres Alia, asistente de {company.name} especializada en "
                    "maquinaria pesada. Hablas con un trabajador interno de "
                    "la empresa.\n\n"
                    f"Trabajador: {_internal_contact.name}\n\n"
                    "INSTRUCCIONES:\n"
                    "- Si el trabajador menciona una avería, problema "
                    "mecánico, "
                    "fallo en una máquina o vehículo → responde como agente "
                    "de averías: "
                    "recoge los datos del problema de forma natural "
                    "(máquina, descripción, "
                    "ubicación en la máquina, ubicación física, urgencia). "
                    "Cuando tengas suficientes datos, confirma que vas a "
                    "abrir un ticket.\n"
                    "- Si el trabajador pide ayuda con el panel, su "
                    "contraseña, acceso "
                    "u otro tema de soporte → responde de forma concisa y "
                    "útil.\n"
                    "- Si el mensaje es un saludo o no está claro → pregunta "
                    "de forma "
                    "natural qué necesita.\n"
                    "- Mantén un tono profesional, directo y conciso.\n"
                    f"Secciones de la empresa: {_sections_list}.\n\n"
                    "MARCADOR DE DATOS (uso interno — el trabajador no lo "
                    "ve):\n"
                    "Cuando estés en el caso de avería y tengas suficiente "
                    "información "
                    "confirmada por el trabajador para abrir el ticket, "
                    "añade AL FINAL "
                    "de tu respuesta — y SOLO al final — el siguiente "
                    "marcador JSON:\n"
                    '[TICKET_DATA:{"machine": "...", "fault": "...", '
                    '"fault_location": "...", "location": "...", '
                    '"urgency": "LOW|MEDIUM|HIGH|CRITICAL", '
                    '"category": "...", '
                    '"reported_by": "nombre completo del '
                    'conductor/maquinista o null"}]\n'
                    "Categorías válidas: MECHANICAL, ELECTRICAL_ELECTRONIC, "
                    "HYDRAULIC, "
                    "PNEUMATIC, BODYWORK, TYRES, OTHER.\n"
                    "Sin este marcador el ticket NO se crea en el sistema, "
                    "aunque le "
                    "confirmes verbalmente al trabajador que se ha abierto — "
                    "inclúyelo "
                    "siempre que confirmes la apertura de un ticket. Si el "
                    "caso es de "
                    "ayuda/soporte (no avería), omite el marcador por "
                    "completo. "
                    "NUNCA muestres el marcador al trabajador — será "
                    "procesado "
                    "internamente."
                )
                # H37 (S133): whoever gives services can ask for one in
                # any words; Gemini decides and answers with the marker.
                # Quien da servicios puede pedirlo con cualquier palabra:
                # Gemini lo decide y contesta con el marcador.
                from budgets import service_intake as _si

                _gives_services = _si.service_giver(
                    _internal_contact.company_user,
                )
                if _gives_services:
                    _b_system_prompt += (
                        "\n\nDAR SERVICIOS:\n"
                        + _si.general_assistant_instruction()
                    )
                _b_history = WhatsAppChatService.build_history(session)
                try:
                    reply_text = WhatsAppChatService.get_gemini_reply(
                        system_prompt=_b_system_prompt,
                        history=_b_history,
                        user_message=_effective_msg,
                        session=session,
                    )
                except Exception as _exc:
                    logger.error(
                        "# [WHATSAPP H17] Error Gemini Branch B contact %s: "
                        "%s",
                        from_number, _exc,
                    )
                    reply_text = (
                        "Lo sentimos, ha habido un problema. "
                        "Por favor, inténtalo de nuevo."
                    )

                if _gives_services and _si.SERVICE_MARKER in reply_text:
                    from whatsapp.tasks import service_intake_reply

                    _handover = _si.start_from_assistant(
                        _internal_contact.company_user, from_number,
                    )
                    logger.info(
                        "# [WHATSAPP H37] %s quiere dar un servicio: pasa "
                        "a la conversación de servicio pk=%s.",
                        from_number, _handover.pk,
                    )
                    service_intake_reply.delay(
                        _handover.pk, _effective_msg, "", "",
                        to_number, from_number,
                    )
                    return HttpResponse(status=200)

                # If Gemini's reply signals enough breakdown data, create
                # ticket.
                # Si la respuesta de Gemini tiene datos de avería, crear
                # ticket.
                # We check for TICKET_DATA marker even in Branch B.
                # Comprobamos marcador TICKET_DATA también en Rama B.
                _ticket_b = BreakdownAgentService.get_or_create_ticket(
                    _internal_contact, company,
                ) if "[TICKET_DATA:" in reply_text else None

                if _ticket_b is not None:
                    BreakdownAgentService.append_log(
                        _ticket_b, "USER", _effective_msg,
                    )
                    reply_text = (
                        BreakdownAgentService.parse_and_apply_ticket_data(
                            reply_text, _ticket_b,
                        )
                    )
                    BreakdownAgentService.append_log(
                        _ticket_b, "MODEL", reply_text,
                    )
                    logger.info(
                        "# [WHATSAPP H17] Ticket creado desde Rama B: pk=%s",
                        _ticket_b.pk,
                    )

            # Dispatch reply (common to A and B).
            # Despachar respuesta (común a A y B).
            try:
                _msg_sid = WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=reply_text,
                )
                WhatsAppMessage.objects.create(
                    session=session,
                    direction=WhatsAppMessage.DIRECTION_OUT,
                    body=reply_text,
                    message_sid=_msg_sid,
                )
            except Exception as _exc:
                logger.error(
                    "# [WHATSAPP H17] Error enviando respuesta a Contact "
                    "interno %s: %s",
                    from_number, _exc,
                )
                WhatsAppMessage.objects.create(
                    session=session,
                    direction=WhatsAppMessage.DIRECTION_OUT,
                    body=reply_text,
                    message_sid="",
                )
            return HttpResponse(status=200)

        # ------------------------------------------------------------------
        # BRANCH C — Unknown number: onboarding in progress.
        # RAMA C — Número desconocido: onboarding en curso.
        # ------------------------------------------------------------------
        _onboarding_state = OnboardingService.get_state(session)
        if _onboarding_state is not None:
            logger.info(
                "# [WHATSAPP H17] Número desconocido %s — onboarding en "
                "curso (step=%s).",
                from_number,
                _onboarding_state.get("step"),
            )
            _ob_reply = OnboardingService.handle(
                session=session,
                company=company,
                body=body,
            )
            try:
                _ob_sid = WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=_ob_reply,
                )
                WhatsAppMessage.objects.create(
                    session=session,
                    direction=WhatsAppMessage.DIRECTION_OUT,
                    body=_ob_reply,
                    message_sid=_ob_sid,
                )
            except Exception as _exc:
                logger.error(
                    "# [WHATSAPP H17] Error enviando respuesta onboarding a "
                    "%s: %s",
                    from_number, _exc,
                )
                WhatsAppMessage.objects.create(
                    session=session,
                    direction=WhatsAppMessage.DIRECTION_OUT,
                    body=_ob_reply,
                    message_sid="",
                )
            return HttpResponse(status=200)

        # ------------------------------------------------------------------
        # BRANCH D — Unknown number: generic chatbot or onboarding trigger.
        # Gemini detects employee self-identification and starts onboarding.
        # RAMA D — Número desconocido: chatbot genérico o trigger de
        # onboarding.
        # Gemini detecta auto-identificación de empleado e inicia el
        # onboarding.
        # ------------------------------------------------------------------

        # --- Step 5: Build dynamic system prompt enriched with session
        # context. ---
        # The session object is now passed to build_system_prompt so the agent
        # can include the client's location in the context when available.
        # --- Paso 5: Construir system prompt dinámico enriquecido con el
        # contexto de sesión. ---
        # El objeto session se pasa ahora a build_system_prompt para que el
        # agente pueda incluir la ubicación del cliente en el contexto cuando
        # esté disponible.
        system_prompt = WhatsAppChatService.build_system_prompt(
            company=company,
            to_number=to_number,
            session=session,
        )

        # Inject onboarding trigger detection into the generic system prompt.
        # Inyectar detección de trigger de onboarding en el system prompt
        # genérico.
        system_prompt += (
            "\n\nDETECCIÓN DE EMPLEADO:"
            "\nSi el mensaje indica que quien escribe es un empleado o "
            "trabajador "
            "de la empresa (frases como 'soy empleado', 'trabajo aquí', "
            "'soy de "
            "la empresa', 'me acaban de contratar', o similares), responde "
            "EXACTAMENTE con el siguiente texto y nada más:"
            "\n[EMPLOYEE_ONBOARDING]"
            "\nNo añadas ningún texto antes ni después de este marcador."
        )

        # --- Step 6: Reconstruct Gemini chat history from session
        # messages. ---
        # --- Paso 6: Reconstruir historial de chat de Gemini desde mensajes
        # de sesión. ---
        history = WhatsAppChatService.build_history(session)

        # --- Step 7: Obtain Gemini reply. ---
        # --- Paso 7: Obtener respuesta de Gemini. ---
        effective_user_message = body if body else (
            "El cliente acaba de compartir su ubicación geográfica."
            if is_location_msg
            else ""
        )
        try:
            reply_text = WhatsAppChatService.get_gemini_reply(
                system_prompt=system_prompt,
                history=history,
                user_message=effective_user_message,
                session=session,
            )
        except Exception as exc:
            logger.error(
                "# [WHATSAPP] Error obteniendo respuesta de Gemini: %s",
                exc,
            )
            reply_text = (
                "Lo sentimos, en este momento no podemos procesar tu "
                "consulta. "
                "Por favor, inténtalo de nuevo en unos instantes."
            )

        # --- Step 7b: Detect [EMPLOYEE_ONBOARDING] marker → start
        # onboarding. ---
        # --- Paso 7b: Detectar marcador [EMPLOYEE_ONBOARDING] → iniciar
        # onboarding. ---
        if "[EMPLOYEE_ONBOARDING]" in reply_text:
            logger.info(
                "# [WHATSAPP H17] Marcador EMPLOYEE_ONBOARDING detectado "
                "para número %s. Iniciando onboarding.",
                from_number,
            )
            reply_text = OnboardingService.start(
                session=session, company=company
            )
            try:
                _ob_sid = WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=reply_text,
                )
                WhatsAppMessage.objects.create(
                    session=session,
                    direction=WhatsAppMessage.DIRECTION_OUT,
                    body=reply_text,
                    message_sid=_ob_sid,
                )
            except Exception as _exc:
                logger.error(
                    "# [WHATSAPP H17] Error enviando inicio de onboarding a "
                    "%s: %s",
                    from_number, _exc,
                )
            return HttpResponse(status=200)

        # --- Step 7c: Parse and strip TARGET_SECTION marker from reply. ---
        # --- Paso 7c: Parsear y eliminar marcador TARGET_SECTION de la
        # respuesta. ---
        _TARGET_SECTION_PATTERN = re.compile(
            r'\[TARGET_SECTION:\s*(\{[^}]+\})\s*\]',
            re.IGNORECASE,
        )
        target_match = _TARGET_SECTION_PATTERN.search(reply_text)
        if target_match:
            raw_json = target_match.group(1)
            reply_text = _TARGET_SECTION_PATTERN.sub("", reply_text).strip()
            try:
                marker_data = json.loads(raw_json)
                section_name = marker_data.get("name", "").strip()
                if section_name:
                    target_section = Section.objects.filter(
                        company=company,
                        name=section_name,
                        is_active=True,
                    ).first()
                    if target_section is not None:
                        session.target_section = target_section
                        session.save(
                            update_fields=["target_section", "last_message_at"]
                        )
                        logger.info(
                            "# [WHATSAPP] Sección destino registrada para "
                            "sesión %s: '%s' (pk=%s)",
                            session.pk,
                            target_section.name,
                            target_section.pk,
                        )
                    else:
                        logger.warning(
                            "# [WHATSAPP] Sección destino '%s' no encontrada "
                            "en empresa '%s' — marcador ignorado.",
                            section_name,
                            company.name,
                        )
            except (json.JSONDecodeError, AttributeError, TypeError) as exc:
                logger.warning(
                    "# [WHATSAPP] Error parseando marcador TARGET_SECTION: %s "
                    "— raw_json=%s",
                    exc,
                    raw_json,
                )

        # --- Step 8: Dispatch reply via Twilio and persist outbound
        # message. ---
        # --- Paso 8: Despachar respuesta vía Twilio y persistir mensaje
        # saliente. ---
        try:
            message_sid = WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=reply_text,
            )
            WhatsAppMessage.objects.create(
                session=session,
                direction=WhatsAppMessage.DIRECTION_OUT,
                body=reply_text,
                message_sid=message_sid,
            )

        except Exception as exc:
            logger.error(
                "# [WHATSAPP] Error enviando respuesta vía Twilio: %s",
                exc,
            )
            # Persist the outbound message even if Twilio dispatch failed,
            # so the conversation history remains coherent for Gemini context.
            # Persistir el mensaje saliente aunque el despacho Twilio haya
            # fallado, para que el historial de conversación permanezca
            # coherente para el contexto de Gemini.
            WhatsAppMessage.objects.create(
                session=session,
                direction=WhatsAppMessage.DIRECTION_OUT,
                body=reply_text,
                message_sid="",
            )

        return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# PRESENCE WHATSAPP VIEW
# Handles inbound presence reminder responses from internal CompanyUsers.
# Gestiona respuestas entrantes a recordatorios de presencia de CompanyUsers
# internos.
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class PresenceWhatsAppView(View):
    """
    Webhook endpoint: POST /api/whatsapp/presence/
    Receives inbound WhatsApp messages from internal CompanyUsers responding
    to presence reminders sent by the check_in_meeting_reminders Celery task.
    Delegates all processing logic to PresenceResponseService, which resolves
    the user, parses the response and updates the PresenceStatus accordingly.
    Sends a plain-text confirmation reply within the open 24-hour session
    window. Returns HTTP 200 with an empty body — Twilio does not require
    TwiML for WhatsApp messaging webhooks.
    ---
    Endpoint webhook: POST /api/whatsapp/presence/
    Recibe mensajes entrantes de WhatsApp de CompanyUsers internos
    respondiendo a recordatorios de presencia enviados por la tarea Celery
    check_in_meeting_reminders. Delega toda la lógica de procesamiento a
    PresenceResponseService, que resuelve el usuario, analiza la respuesta y
    actualiza el PresenceStatus en consecuencia. Envía una respuesta de
    confirmación en texto plano dentro de la ventana abierta de sesión de 24
    horas. Devuelve HTTP 200 con cuerpo vacío — Twilio no requiere TwiML para
    webhooks de mensajería WhatsApp.
    """

    def post(self, request, *args, **kwargs):
        """
        Main POST handler for presence reminder responses.
        Extracts From and Body from the Twilio webhook, delegates to
        PresenceResponseService and dispatches the confirmation reply.
        ---
        Manejador POST principal para respuestas a recordatorios de presencia.
        Extrae From y Body del webhook de Twilio, delega a
        PresenceResponseService y despacha la respuesta de confirmación.
        """
        # --- Step 1: Extract Twilio webhook parameters. ---
        # --- Paso 1: Extraer parámetros del webhook de Twilio. ---
        from_number = request.POST.get("From", "").replace("whatsapp:", "")
        to_number = request.POST.get("To", "").replace("whatsapp:", "")
        body = request.POST.get("Body", "").strip()

        logger.info(
            "# [PRESENCE] Respuesta de presencia de %s: '%s'",
            from_number,
            body,
        )

        if not from_number or not body:
            logger.warning(
                "# [PRESENCE] Parámetros incompletos en webhook de "
                "presencia. From=%s Body=%s",
                from_number,
                repr(body),
            )
            return HttpResponse(status=200)

        # --- Step 2: Delegate processing to PresenceResponseService. ---
        # --- Paso 2: Delegar procesamiento a PresenceResponseService. ---
        confirmation_message = PresenceResponseService.process_response(
            from_number=from_number,
            body=body,
        )

        # --- Step 3: Send confirmation reply via Twilio. ---
        # --- Paso 3: Enviar respuesta de confirmación vía Twilio. ---
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=confirmation_message,
            )
        except Exception as exc:
            logger.error(
                "# [PRESENCE] Error enviando confirmación de presencia a "
                "%s: %s",
                from_number,
                exc,
            )

        return HttpResponse(status=200)


# H37 (S132). Twilio delivery statuses meaning the notice never arrived,
# and those confirming it reached the phone.
# Estados de entrega de Twilio que significan que el aviso no llegó, y
# los que confirman que ha llegado al móvil.
_NOTICE_FAILED_STATUSES = ("failed", "undelivered")
_NOTICE_DELIVERED_STATUSES = ("delivered", "read")


@method_decorator(csrf_exempt, name="dispatch")
class AlbaranNoticeStatusView(View):
    """
    Twilio status callback for the albarán notice of a unit.

    ---

    H37 (S132). Informe de entrega de Twilio del aviso del albarán de
    una unidad (POST /api/whatsapp/albaran-status/<token>/). Miguel
    Ángel, S132: la unidad salía como avisada aunque el WhatsApp no
    llegaba (plantilla sin aprobar), porque solo se miraba que Twilio
    aceptara el envío. Ahora la unidad espera en NOTIFY_SENDING: si
    Twilio confirma la entrega (delivered o read) pasa a NOTIFIED con la
    hora de entrega; si informa de que ha fallado o no se ha entregado,
    pasa a NOTIFY_FAILED con el código de error. Solo cuenta el informe
    del último aviso
    (`notify_message_sid`), y el token de la URL lleva la unidad
    firmada, así que nadie puede tocar otra unidad.
    """

    def post(self, request, token):
        """
        Apply a delivery status to the unit.

        ---

        Aplica a la unidad el estado de entrega del aviso.
        """
        from budgets.models import (
            WorkOrderAssistanceUnit,
            WorkOrderAssistanceUnitEvent,
        )

        from .services import unit_pk_from_notice_token

        unit_pk = unit_pk_from_notice_token(token)
        if unit_pk is None:
            logger.warning("# [ALBARAN STATUS] Token no válido.")
            return HttpResponse(status=403)

        message_sid = request.POST.get("MessageSid", "")
        message_status = request.POST.get("MessageStatus", "")
        error_code = request.POST.get("ErrorCode", "")
        logger.info(
            "# [ALBARAN STATUS] Unidad pk=%s, mensaje %s: %s %s",
            unit_pk, message_sid, message_status, error_code,
        )
        if not message_sid:
            return HttpResponse(status=204)
        last_notice = WorkOrderAssistanceUnit.objects.filter(
            pk=unit_pk, notify_message_sid=message_sid,
        )
        # H37 (S133): each change is recorded (WorkOrderAssistanceUnit
        # Event, no panel user: WhatsApp reported it). The previous
        # status is read first so the event says where it came from.
        # Cada cambio queda registrado (sin usuario del panel: lo
        # informa WhatsApp). Se lee antes el estado de partida.
        unit = last_notice.first()
        if unit is None:
            return HttpResponse(status=204)
        previous_status = unit.status
        if message_status in _NOTICE_DELIVERED_STATUSES:
            updated = last_notice.filter(
                status=WorkOrderAssistanceUnit.STATUS_NOTIFY_SENDING,
            ).update(
                status=WorkOrderAssistanceUnit.STATUS_NOTIFIED,
                notified_at=now(),
            )
            if updated:
                WorkOrderAssistanceUnitEvent.status_change(
                    unit, previous_status,
                    WorkOrderAssistanceUnit.STATUS_NOTIFIED,
                    detail="WhatsApp confirma la entrega (%s)."
                    % message_status,
                )
            return HttpResponse(status=204)
        if message_status not in _NOTICE_FAILED_STATUSES:
            return HttpResponse(status=204)

        notify_error = (
            "WhatsApp no entregado (Twilio: %s, error %s)"
            % (message_status, error_code or "sin código")
        )[:255]
        updated = last_notice.filter(
            status__in=(
                WorkOrderAssistanceUnit.STATUS_NOTIFY_SENDING,
                WorkOrderAssistanceUnit.STATUS_NOTIFIED,
            ),
        ).update(
            status=WorkOrderAssistanceUnit.STATUS_NOTIFY_FAILED,
            notify_error=notify_error,
        )
        if updated:
            WorkOrderAssistanceUnitEvent.status_change(
                unit, previous_status,
                WorkOrderAssistanceUnit.STATUS_NOTIFY_FAILED,
                detail=notify_error,
            )
            logger.warning(
                "# [ALBARAN STATUS] Unidad pk=%s: aviso no entregado "
                "(%s, error %s).",
                unit_pk, message_status, error_code,
            )
        return HttpResponse(status=204)
