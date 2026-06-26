
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/views.py
"""
Views for the whatsapp channel app.
Implements two CSRF-exempt webhook endpoints:
  - IncomingWhatsAppView: handles inbound user messages (text and location) and
    dispatches chatbot replies. Location messages (Latitude/Longitude in Twilio POST)
    are detected, stored in WhatsAppMessage with message_type='location', and
    propagated to WhatsAppSession for context enrichment in the Gemini system prompt.
    Gemini replies are parsed for the [TARGET_SECTION:{...}] marker (Paso 21):
    when detected, WhatsAppSession.target_section is updated and the marker is
    stripped from the reply before dispatching to the user.
  - PresenceWhatsAppView: handles presence reminder responses (1h / 2h / disponible).
Both views are synchronous Django WSGI views — no aiohttp or WebSocket required.

Updated in Paso 19 (2026-04-16): location message detection and propagation.
Updated in Paso 21 (2026-04-20): target section detection and registration.
---
Vistas para la app del canal WhatsApp.
Implementa dos endpoints webhook exentos de CSRF:
  - IncomingWhatsAppView: gestiona mensajes entrantes del usuario (texto y ubicación)
    y despacha respuestas del chatbot. Los mensajes de ubicación (Latitude/Longitude
    en el POST de Twilio) se detectan, se almacenan en WhatsAppMessage con
    message_type='location' y se propagan a WhatsAppSession para enriquecer el
    contexto en el system prompt de Gemini.
    Las respuestas de Gemini se analizan en busca del marcador
    [TARGET_SECTION:{...}] (Paso 21): cuando se detecta, se actualiza
    WhatsAppSession.target_section y el marcador se elimina de la respuesta
    antes de despacharla al usuario.
  - PresenceWhatsAppView: gestiona respuestas a recordatorios de presencia (1h / 2h / disponible).
Ambas vistas son vistas síncronas Django WSGI — no se requiere aiohttp ni WebSocket.

Actualizado en el Paso 19 (2026-04-16): detección y propagación de mensajes de ubicación.
Actualizado en el Paso 21 (2026-04-20): detección y registro de sección destino.
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


# ---------------------------------------------------------------------------
# INCOMING WHATSAPP VIEW
# Handles inbound user messages and dispatches chatbot replies via Gemini.
# Gestiona mensajes entrantes del usuario y despacha respuestas del chatbot vía Gemini.
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class IncomingWhatsAppView(View):
    """
    Webhook endpoint: POST /api/whatsapp/incoming/
    Receives inbound WhatsApp messages from Twilio, resolves the target company
    from the destination number, manages the WhatsAppSession and message history,
    invokes WhatsAppChatService to obtain a Gemini reply, persists both the
    inbound and outbound messages, and dispatches the reply via Twilio.
    Returns HTTP 200 with an empty body on success — Twilio does not require
    a TwiML response for WhatsApp messaging webhooks.
    ---
    Endpoint webhook: POST /api/whatsapp/incoming/
    Recibe mensajes entrantes de WhatsApp de Twilio, resuelve la empresa destino
    desde el número de destino, gestiona la WhatsAppSession y el historial de
    mensajes, invoca WhatsAppChatService para obtener una respuesta de Gemini,
    persiste los mensajes entrante y saliente, y despacha la respuesta vía Twilio.
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
        # Twilio envía Latitude y Longitude como campos POST separados cuando el
        # usuario comparte un mensaje de ubicación nativo de WhatsApp. En ese caso
        # Body puede estar vacío o contener solo el texto de etiqueta del usuario.
        # Clasificamos el mensaje como 'location' cuando Latitude está presente y
        # no está vacío.
        from_number      = request.POST.get("From", "").replace("whatsapp:", "")
        to_number        = request.POST.get("To", "").replace("whatsapp:", "")
        body             = request.POST.get("Body", "").strip()
        raw_latitude     = request.POST.get("Latitude", "").strip()
        raw_longitude    = request.POST.get("Longitude", "").strip()
        is_location_msg  = bool(raw_latitude)

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

        # A message must have either a body or location coordinates to be processed.
        # Un mensaje debe tener cuerpo o coordenadas de ubicación para ser procesado.
        if not from_number or not to_number or (not body and not is_location_msg):
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
                "# [WHATSAPP] Número destino no registrado o sin capacidad WhatsApp: %s",
                to_number,
            )
            return HttpResponse(status=200)

        except PhoneNumber.MultipleObjectsReturned:
            logger.error(
                "# [WHATSAPP] Múltiples PhoneNumber activos para: %s",
                to_number,
            )
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
        # For location messages, latitude and longitude are stored on the message
        # record in addition to the body label (which may be empty).
        # --- Paso 4: Persistir mensaje entrante con tipo y coordenadas. ---
        # Para mensajes de ubicación, latitude y longitude se almacenan en el
        # registro de mensaje además de la etiqueta de cuerpo (que puede estar vacía).
        msg_latitude  = None
        msg_longitude = None

        if is_location_msg:
            try:
                msg_latitude  = Decimal(raw_latitude)
                msg_longitude = Decimal(raw_longitude)
            except InvalidOperation:
                logger.warning(
                    "# [WHATSAPP] Coordenadas de ubicación con formato inválido: "
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
        # caller's coordinates and timestamp. Existing coordinates are overwritten
        # with the most recent location shared by the user during the session.
        # The location_address field is left blank here — it may be resolved by
        # Grounding with Google Maps in Paso 20.
        # --- Paso 4b: Propagar ubicación a WhatsAppSession (Paso 19). ---
        # Cuando se recibe un mensaje de ubicación, actualizar la sesión con las
        # coordenadas del llamante y la marca de tiempo. Las coordenadas existentes
        # se sobreescriben con la ubicación más reciente compartida por el usuario
        # durante la sesión. El campo location_address se deja en blanco aquí —
        # puede resolverse mediante Grounding con Google Maps en el Paso 20.
        if is_location_msg and msg_latitude is not None:
            session.latitude             = msg_latitude
            session.longitude            = msg_longitude
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

        # --- Step 4b-bis: Handle ButtonPayload for chat_session_renewal — Hito 13, Paso 10. ---
        # Intercepts Quick Reply button presses from the chat_session_renewal template
        # BEFORE the IRC dispatcher and the Hito 4 chatbot pipeline. Two payloads:
        #   opt_in  — reactivates the WhatsApp session window for the contact.
        #   opt_out — sets contact.opt_out_broadcast = True to exclude from broadcasts.
        # Both branches return HTTP 200 immediately, consuming the message.
        # EXCEPTION: if the contact is in AWAITING_BREAKDOWN_CONFIRM state, the
        # opt_in payload is the breakdown confirmation Quick Reply — do NOT intercept
        # here; let the IRC dispatcher handle it via _resolve_pending_routing.
        # --- Paso 4b-bis: Gestionar ButtonPayload para chat_session_renewal — Hito 13, Paso 10. ---
        # Intercepta pulsaciones de botón Quick Reply del template chat_session_renewal
        # ANTES del despachador IRC y del pipeline del chatbot del Hito 4. Dos payloads:
        #   opt_in  — reactiva la ventana de sesión WhatsApp del contacto.
        #   opt_out — establece contact.opt_out_broadcast = True para excluirle de broadcasts.
        # Ambas ramas devuelven HTTP 200 inmediatamente, consumiendo el mensaje.
        # EXCEPCIÓN: si el contacto está en estado AWAITING_BREAKDOWN_CONFIRM, el payload
        # opt_in corresponde al Quick Reply de confirmación de avería — NO interceptar aquí;
        # dejar que el despachador IRC lo gestione a través de _resolve_pending_routing.
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
        if _button_payload in ("opt_in", "opt_out") and not _skip_opt_for_breakdown:
            if _button_payload == "opt_in":
                # Reactivate the WhatsApp session window for this operator.
                # Reactivar la ventana de sesión WhatsApp para este operario.
                WhatsAppSession.objects.filter(
                    company=company,
                    phone_number=from_number,
                ).update(is_active=True, last_message_at=now())

                # Deliver pending albarán links if any are queued for this operator.
                # Entregar los enlaces de albarán pendientes si hay alguno en cola.
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
                    from django.urls import reverse as _reverse

                    # Build and send one message per pending unit.
                    # Construir y enviar un mensaje por cada unidad pendiente.
                    _delivered_pks = []
                    for _unit_pk in _pending_units:
                        try:
                            _unit = _WAU.objects.select_related(
                                "work_order__insurer",
                            ).get(pk=_unit_pk)
                            _albaran_url = (
                                f"{os.environ.get('PLATFORM_BASE_URL', '').rstrip('/')}"
                                f"/panel/budgets/work-orders/units/{_unit.pk}/albaran/"
                            )
                            _msg = (
                                "\U0001f4cb Albar\u00e1n asignado:\n"
                                f"Orden: {_unit.work_order.work_order_number}"
                                f"-{_unit.unit_number:02d}\n"
                                f"Aseguradora: {_unit.work_order.insurer.name}\n"
                                f"Accede aqu\u00ed: {_albaran_url}"
                            )
                            WhatsAppChatService.send_reply(
                                from_number=to_number,
                                to_number=from_number,
                                reply_text=_msg,
                            )
                            # Mark unit as DOWNLOADED when operator receives the link.
                            # Marcar la unidad como DOWNLOADED cuando el operario recibe el enlace.
                            _unit.status        = _WAU.STATUS_DOWNLOADED
                            _unit.downloaded_at = now()
                            _unit.save(update_fields=["status", "downloaded_at"])
                            _delivered_pks.append(_unit_pk)
                            logger.info(
                                "# [ALBARAN NOTIFY] Enlace albarán pk=%s entregado a %s.",
                                _unit_pk,
                                from_number,
                            )
                        except _WAU.DoesNotExist:
                            logger.warning(
                                "# [ALBARAN NOTIFY] Unidad pk=%s no encontrada — "
                                "ignorada en entrega opt_in.",
                                _unit_pk,
                            )
                        except Exception as _exc:
                            logger.error(
                                "# [ALBARAN NOTIFY] Error entregando albarán pk=%s "
                                "a %s: %s",
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
                # Deliver pending broadcast messages queued while outside 24h window.
                # Messages older than 48h are discarded — considered expired.
                # ---
                # Entregar mensajes de circular pendientes encolados fuera de la ventana.
                # Los mensajes con más de 48h se descartan — se consideran expirados.
                if _active_session:
                    import json as _json_bc_opt
                    from datetime import timedelta as _td_bc_opt, datetime as _dt_bc_opt
                    _pending_bc = list(
                        _active_session.pending_broadcast_messages or []
                    )
                    if _pending_bc:
                        _expiry_threshold = now() - _td_bc_opt(hours=48)
                        _bc_remaining = []
                        for _bc_msg in _pending_bc:
                            _bc_body       = _bc_msg.get("body", "")
                            _bc_created_raw = _bc_msg.get("created_at", "")
                            # Parse created_at and check expiry.
                            # Parsear created_at y comprobar expiración.
                            try:
                                _bc_created = _dt_bc_opt.fromisoformat(_bc_created_raw)
                                # Make offset-naive for comparison if needed.
                                if _bc_created.tzinfo is None:
                                    from django.utils.timezone import make_aware as _make_aware
                                    _bc_created = _make_aware(_bc_created)
                            except (ValueError, TypeError):
                                _bc_created = now()  # Unknown age — treat as fresh.
                            if _bc_created < _expiry_threshold:
                                logger.info(
                                    "# [WHATSAPP] Mensaje de circular expirado (>48h) "
                                    "para %s — descartado.",
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
                                    "# [WHATSAPP] Mensaje de circular entregado a %s "
                                    "tras opt_in.",
                                    from_number,
                                )
                            except Exception as _bc_exc:
                                logger.error(
                                    "# [WHATSAPP] Error entregando circular a %s: %s",
                                    from_number, _bc_exc,
                                )
                                _bc_remaining.append(_bc_msg)  # Keep for retry.
                        # Clear delivered messages; keep only failed ones.
                        # Vaciar mensajes entregados; conservar solo los fallidos.
                        _active_session.pending_broadcast_messages = _bc_remaining
                        _active_session.save(
                            update_fields=["pending_broadcast_messages"]
                        )

                logger.info(
                    "# [WHATSAPP] opt_in procesado para %s — sesión reactivada.",
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
                        reply_text="De acuerdo, no recibirás más mensajes del grupo.",
                    )
                except Exception as _exc:
                    logger.error(
                        "# [WHATSAPP] Error enviando confirmación opt_out a %s: %s",
                        from_number, _exc,
                    )
                logger.info(
                    "# [WHATSAPP] opt_out procesado para %s — excluido de broadcasts.",
                    from_number,
                )
            return HttpResponse(status=200)

        # =======================================================================
        # --- Step 5 (H17): Route by sender identity. ---
        # Bifurcación H17: enrutar según identidad del remitente.
        #
        # Three branches:
        #   A) Internal Contact with open ticket → breakdown agent (continue)
        #   B) Internal Contact without open ticket → breakdown agent (new)
        #      or help branch (Gemini decides from message intent)
        #   C) Unknown number with onboarding in progress → onboarding step
        #   D) Unknown number → generic chatbot OR onboarding trigger
        # =======================================================================

        from ivr_config.models import Contact as _Contact
        from chat.models import BreakdownTicket as _BT

        _internal_contact = _Contact.objects.filter(
            company=company,
            phone_number=from_number,
        ).select_related("company_user").first()

        # -----------------------------------------------------------------------
        # BRANCH A/B — Internal Contact: breakdown agent or help chatbot.
        # RAMA A/B — Contact interno: agente de averías o chatbot de ayuda.
        # -----------------------------------------------------------------------
        if _internal_contact is not None:

            # Resolve open ticket for this contact (OPEN or IN_PROGRESS).
            # Resolver ticket abierto para este contacto (OPEN o IN_PROGRESS).
            _open_ticket = _BT.objects.filter(
                contact=_internal_contact,
                company=company,
                status__in=[_BT.STATUS_OPEN, _BT.STATUS_IN_PROGRESS],
            ).order_by("-created_at").first()

            # Effective user message — synthesise for pure location messages.
            # Mensaje de usuario efectivo — sintetizar para mensajes de ubicación puros.
            _effective_msg = body if body else (
                "El trabajador acaba de compartir su ubicación geográfica."
                if is_location_msg else ""
            )

            if _open_ticket is not None:
                # --- Branch A: continue breakdown conversation. ---
                # --- Rama A: continuar conversación de avería. ---
                logger.info(
                    "# [WHATSAPP H17] Contact interno %s — ticket abierto pk=%s. "
                    "Rama: BREAKDOWN AGENT (continuar).",
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
                            "# [WHATSAPP H17] GPS persistido en ticket pk=%s: "
                            "lat=%s lng=%s.",
                            _open_ticket.pk,
                            msg_latitude,
                            msg_longitude,
                        )

                _system_prompt = BreakdownAgentService.build_system_prompt(
                    contact=_internal_contact,
                    ticket=_open_ticket,
                    company=company,
                )
                _history = BreakdownAgentService.build_history_from_log(_open_ticket)
                try:
                    _reply_raw = BreakdownAgentService.get_gemini_reply(
                        system_prompt=_system_prompt,
                        history=_history,
                        user_message=_effective_msg,
                    )
                except Exception as _exc:
                    logger.error(
                        "# [WHATSAPP H17] Error Gemini avería (ticket pk=%s): %s",
                        _open_ticket.pk, _exc,
                    )
                    _reply_raw = (
                        "Lo sentimos, ha habido un problema al procesar tu mensaje. "
                        "Por favor, inténtalo de nuevo."
                    )
                # Persist USER turn in conversation_log.
                # Persistir turno USER en conversation_log.
                BreakdownAgentService.append_log(
                    _open_ticket, "USER", _effective_msg,
                )
                # Parse and apply TICKET_DATA marker; get clean reply.
                # Parsear y aplicar marcador TICKET_DATA; obtener respuesta limpia.
                reply_text = BreakdownAgentService.parse_and_apply_ticket_data(
                    _reply_raw, _open_ticket,
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
                    "# [WHATSAPP H17] Contact interno %s — sin ticket abierto. "
                    "Rama: BREAKDOWN/HELP decision.",
                    from_number,
                )
                _sections_list = ", ".join(
                    s.name for s in company.sections.filter(is_active=True)
                )
                _b_system_prompt = (
                    f"Eres Alia, asistente de {company.name} especializada en "
                    "maquinaria pesada. Hablas con un trabajador interno de la empresa.\n\n"
                    f"Trabajador: {_internal_contact.name}\n\n"
                    "INSTRUCCIONES:\n"
                    "- Si el trabajador menciona una avería, problema mecánico, "
                    "fallo en una máquina o vehículo → responde como agente de averías: "
                    "recoge los datos del problema de forma natural (máquina, descripción, "
                    "ubicación en la máquina, ubicación física, urgencia). "
                    "Cuando tengas suficientes datos, confirma que vas a abrir un ticket.\n"
                    "- Si el trabajador pide ayuda con el panel, su contraseña, acceso "
                    "u otro tema de soporte → responde de forma concisa y útil.\n"
                    "- Si el mensaje es un saludo o no está claro → pregunta de forma "
                    "natural qué necesita.\n"
                    "- Mantén un tono profesional, directo y conciso.\n"
                    f"Secciones de la empresa: {_sections_list}."
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
                        "# [WHATSAPP H17] Error Gemini Branch B contact %s: %s",
                        from_number, _exc,
                    )
                    reply_text = (
                        "Lo sentimos, ha habido un problema. "
                        "Por favor, inténtalo de nuevo."
                    )

                # If Gemini's reply signals enough breakdown data, create ticket.
                # Si la respuesta de Gemini tiene datos de avería, crear ticket.
                # We check for TICKET_DATA marker even in Branch B.
                # Comprobamos marcador TICKET_DATA también en Rama B.
                _ticket_b = BreakdownAgentService.get_or_create_ticket(
                    _internal_contact, company,
                ) if "[TICKET_DATA:" in reply_text else None

                if _ticket_b is not None:
                    BreakdownAgentService.append_log(
                        _ticket_b, "USER", _effective_msg,
                    )
                    reply_text = BreakdownAgentService.parse_and_apply_ticket_data(
                        reply_text, _ticket_b,
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
                    "# [WHATSAPP H17] Error enviando respuesta a Contact interno %s: %s",
                    from_number, _exc,
                )
                WhatsAppMessage.objects.create(
                    session=session,
                    direction=WhatsAppMessage.DIRECTION_OUT,
                    body=reply_text,
                    message_sid="",
                )
            return HttpResponse(status=200)

        # -----------------------------------------------------------------------
        # BRANCH C — Unknown number: onboarding in progress.
        # RAMA C — Número desconocido: onboarding en curso.
        # -----------------------------------------------------------------------
        _onboarding_state = OnboardingService.get_state(session)
        if _onboarding_state is not None:
            logger.info(
                "# [WHATSAPP H17] Número desconocido %s — onboarding en curso "
                "(step=%s).",
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
                    "# [WHATSAPP H17] Error enviando respuesta onboarding a %s: %s",
                    from_number, _exc,
                )
                WhatsAppMessage.objects.create(
                    session=session,
                    direction=WhatsAppMessage.DIRECTION_OUT,
                    body=_ob_reply,
                    message_sid="",
                )
            return HttpResponse(status=200)

        # -----------------------------------------------------------------------
        # BRANCH D — Unknown number: generic chatbot or onboarding trigger.
        # Gemini detects employee self-identification and starts onboarding.
        # RAMA D — Número desconocido: chatbot genérico o trigger de onboarding.
        # Gemini detecta auto-identificación de empleado e inicia el onboarding.
        # -----------------------------------------------------------------------

        # --- Step 5: Build dynamic system prompt enriched with session context. ---
        # The session object is now passed to build_system_prompt so the agent
        # can include the client's location in the context when available.
        # --- Paso 5: Construir system prompt dinámico enriquecido con el contexto de sesión. ---
        # El objeto session se pasa ahora a build_system_prompt para que el agente
        # pueda incluir la ubicación del cliente en el contexto cuando esté disponible.
        system_prompt = WhatsAppChatService.build_system_prompt(
            company=company,
            to_number=to_number,
            session=session,
        )

        # Inject onboarding trigger detection into the generic system prompt.
        # Inyectar detección de trigger de onboarding en el system prompt genérico.
        system_prompt += (
            "\n\nDETECCIÓN DE EMPLEADO:"
            "\nSi el mensaje indica que quien escribe es un empleado o trabajador "
            "de la empresa (frases como 'soy empleado', 'trabajo aquí', 'soy de "
            "la empresa', 'me acaban de contratar', o similares), responde "
            "EXACTAMENTE con el siguiente texto y nada más:"
            "\n[EMPLOYEE_ONBOARDING]"
            "\nNo añadas ningún texto antes ni después de este marcador."
        )

        # --- Step 6: Reconstruct Gemini chat history from session messages. ---
        # --- Paso 6: Reconstruir historial de chat de Gemini desde mensajes de sesión. ---
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
                "Lo sentimos, en este momento no podemos procesar tu consulta. "
                "Por favor, inténtalo de nuevo en unos instantes."
            )

        # --- Step 7b: Detect [EMPLOYEE_ONBOARDING] marker → start onboarding. ---
        # --- Paso 7b: Detectar marcador [EMPLOYEE_ONBOARDING] → iniciar onboarding. ---
        if "[EMPLOYEE_ONBOARDING]" in reply_text:
            logger.info(
                "# [WHATSAPP H17] Marcador EMPLOYEE_ONBOARDING detectado "
                "para número %s. Iniciando onboarding.",
                from_number,
            )
            reply_text = OnboardingService.start(session=session, company=company)
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
                    "# [WHATSAPP H17] Error enviando inicio de onboarding a %s: %s",
                    from_number, _exc,
                )
            return HttpResponse(status=200)

        # --- Step 7c: Parse and strip TARGET_SECTION marker from reply. ---
        # --- Paso 7c: Parsear y eliminar marcador TARGET_SECTION de la respuesta. ---
        _TARGET_SECTION_PATTERN = re.compile(
            r'\[TARGET_SECTION:\s*(\{[^}]+\})\s*\]',
            re.IGNORECASE,
        )
        target_match = _TARGET_SECTION_PATTERN.search(reply_text)
        if target_match:
            raw_json = target_match.group(1)
            reply_text = _TARGET_SECTION_PATTERN.sub("", reply_text).strip()
            try:
                marker_data  = json.loads(raw_json)
                section_name = marker_data.get("name", "").strip()
                if section_name:
                    target_section = Section.objects.filter(
                        company=company,
                        name=section_name,
                        is_active=True,
                    ).first()
                    if target_section is not None:
                        session.target_section = target_section
                        session.save(update_fields=["target_section", "last_message_at"])
                        logger.info(
                            "# [WHATSAPP] Sección destino registrada para sesión %s: "
                            "'%s' (pk=%s)",
                            session.pk,
                            target_section.name,
                            target_section.pk,
                        )
                    else:
                        logger.warning(
                            "# [WHATSAPP] Sección destino '%s' no encontrada en "
                            "empresa '%s' — marcador ignorado.",
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

        # --- Step 8: Dispatch reply via Twilio and persist outbound message. ---
        # --- Paso 8: Despachar respuesta vía Twilio y persistir mensaje saliente. ---
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
            # Persistir el mensaje saliente aunque el despacho Twilio haya fallado,
            # para que el historial de conversación permanezca coherente para el contexto de Gemini.
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
# Gestiona respuestas entrantes a recordatorios de presencia de CompanyUsers internos.
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class PresenceWhatsAppView(View):
    """
    Webhook endpoint: POST /api/whatsapp/presence/
    Receives inbound WhatsApp messages from internal CompanyUsers responding
    to presence reminders sent by the check_in_meeting_reminders Celery task.
    Delegates all processing logic to PresenceResponseService, which resolves
    the user, parses the response and updates the PresenceStatus accordingly.
    Sends a plain-text confirmation reply within the open 24-hour session window.
    Returns HTTP 200 with an empty body — Twilio does not require TwiML for
    WhatsApp messaging webhooks.
    ---
    Endpoint webhook: POST /api/whatsapp/presence/
    Recibe mensajes entrantes de WhatsApp de CompanyUsers internos respondiendo
    a recordatorios de presencia enviados por la tarea Celery check_in_meeting_reminders.
    Delega toda la lógica de procesamiento a PresenceResponseService, que resuelve
    el usuario, analiza la respuesta y actualiza el PresenceStatus en consecuencia.
    Envía una respuesta de confirmación en texto plano dentro de la ventana abierta
    de sesión de 24 horas. Devuelve HTTP 200 con cuerpo vacío — Twilio no requiere
    TwiML para webhooks de mensajería WhatsApp.
    """

    def post(self, request, *args, **kwargs):
        """
        Main POST handler for presence reminder responses.
        Extracts From and Body from the Twilio webhook, delegates to
        PresenceResponseService and dispatches the confirmation reply.
        ---
        Manejador POST principal para respuestas a recordatorios de presencia.
        Extrae From y Body del webhook de Twilio, delega a PresenceResponseService
        y despacha la respuesta de confirmación.
        """
        # --- Step 1: Extract Twilio webhook parameters. ---
        # --- Paso 1: Extraer parámetros del webhook de Twilio. ---
        from_number = request.POST.get("From", "").replace("whatsapp:", "")
        to_number   = request.POST.get("To", "").replace("whatsapp:", "")
        body        = request.POST.get("Body", "").strip()

        logger.info(
            "# [PRESENCE] Respuesta de presencia de %s: '%s'",
            from_number,
            body,
        )

        if not from_number or not body:
            logger.warning(
                "# [PRESENCE] Parámetros incompletos en webhook de presencia. "
                "From=%s Body=%s",
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
                "# [PRESENCE] Error enviando confirmación de presencia a %s: %s",
                from_number,
                exc,
            )

        return HttpResponse(status=200)



