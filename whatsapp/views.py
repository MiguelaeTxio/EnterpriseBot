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
from .services import PresenceResponseService, WhatsAppChatService

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
        # --- Paso 4b-bis: Gestionar ButtonPayload para chat_session_renewal — Hito 13, Paso 10. ---
        # Intercepta pulsaciones de botón Quick Reply del template chat_session_renewal
        # ANTES del despachador IRC y del pipeline del chatbot del Hito 4. Dos payloads:
        #   opt_in  — reactiva la ventana de sesión WhatsApp del contacto.
        #   opt_out — establece contact.opt_out_broadcast = True para excluirle de broadcasts.
        # Ambas ramas devuelven HTTP 200 inmediatamente, consumiendo el mensaje.
        _button_payload = request.POST.get("ButtonPayload", "").strip()
        if _button_payload in ("opt_in", "opt_out"):
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
                                # Persist in the section ChatRoom for panel history.
                                # Persistir en la ChatRoom de la sección para historial.
                                _bc_section = _active_session.target_section
                                if _bc_section is not None:
                                    from chat.models import ChatRoom as _CR_BC
                                    from chat.models import ChatMessage as _CM_BC
                                    _bc_room = _CR_BC.objects.filter(
                                        company=company,
                                        room_type=_CR_BC.ROOM_TYPE_SECTION,
                                        section=_bc_section,
                                        is_active=True,
                                    ).first()
                                    if _bc_room is not None:
                                        _CM_BC.objects.create(
                                            room=_bc_room,
                                            direction=_CM_BC.DIRECTION_OUTBOUND,
                                            body=_bc_body,
                                            whatsapp_sid="",
                                        )
                                        logger.info(
                                            "# [WHATSAPP] Circular registrada en sala '%s'.",
                                            _bc_room.name,
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

        # --- Step 4c: Chat IRC dispatcher — Hito 13. ---
        # Evaluates the inbound message against the chat dispatch rules before
        # the Hito 4 chatbot pipeline. If the message is consumed by the chat
        # dispatcher (contact belongs to a section with an active ChatRoom),
        # the Hito 4 pipeline is bypassed entirely for this message.
        # --- Paso 4c: Despachador de chat IRC — Hito 13. ---
        # Evalúa el mensaje entrante contra las reglas de despacho de chat antes
        # del pipeline del chatbot del Hito 4. Si el mensaje es consumido por el
        # despachador de chat (el contacto pertenece a una sección con ChatRoom
        # activa), el pipeline del Hito 4 se omite completamente para este mensaje.
        from chat.services import dispatch_inbound_message
        dispatch_result = dispatch_inbound_message(
            company=company,
            from_number=from_number,
            body=body,
            to_number=to_number,
        )
        if dispatch_result.consumed:
            logger.info(
                "# [WHATSAPP] Mensaje de %s consumido por despachador IRC. "
                "Pipeline Hito 4 omitido.",
                from_number,
            )
            return HttpResponse(status=200)

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

        # --- Step 6: Reconstruct Gemini chat history from session messages. ---
        # --- Paso 6: Reconstruir historial de chat de Gemini desde mensajes de sesión. ---
        history = WhatsAppChatService.build_history(session)

        # --- Step 7: Obtain Gemini reply. ---
        # For pure location messages (no body text), synthesise a user_message
        # so Gemini has a meaningful turn to process. The agent's system prompt
        # already contains the location context injected in Step 5.
        # The session object is passed so get_gemini_reply() can activate Maps
        # Grounding when coordinates are available (Paso 20).
        # --- Paso 7: Obtener respuesta de Gemini. ---
        # Para mensajes de ubicación puros (sin texto de cuerpo), sintetizar un
        # user_message para que Gemini tenga un turno significativo que procesar.
        # El system prompt del agente ya contiene el contexto de ubicación
        # inyectado en el Paso 5.
        # El objeto session se pasa para que get_gemini_reply() pueda activar
        # Maps Grounding cuando haya coordenadas disponibles (Paso 20).
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

        # --- Step 7b: Parse and strip TARGET_SECTION marker from reply. ---
        # The Gemini agent may append a [TARGET_SECTION:{"name": "..."}] marker
        # at the end of its response when it detects that the client intends to
        # be directed to a specific company section (Paso 21). This step:
        #   1. Searches for the marker using a strict regex pattern.
        #   2. If found, resolves the Section by name within the company.
        #   3. Updates WhatsAppSession.target_section with the resolved Section.
        #   4. Strips the marker from reply_text so the user never sees it.
        # The marker is silently ignored when the section name is not found in
        # the database — the reply is still dispatched without the marker.
        # --- Paso 7b: Parsear y eliminar marcador TARGET_SECTION de la respuesta. ---
        # El agente Gemini puede añadir un marcador [TARGET_SECTION:{"name": "..."}]
        # al final de su respuesta cuando detecta que el cliente desea ser dirigido
        # a una sección concreta de la empresa (Paso 21). Este paso:
        #   1. Busca el marcador usando un patrón regex estricto.
        #   2. Si se encuentra, resuelve la Section por nombre dentro de la empresa.
        #   3. Actualiza WhatsAppSession.target_section con la Section resuelta.
        #   4. Elimina el marcador de reply_text para que el usuario nunca lo vea.
        # El marcador se ignora silenciosamente cuando el nombre de sección no se
        # encuentra en la base de datos — la respuesta se despacha igualmente sin el marcador.
        _TARGET_SECTION_PATTERN = re.compile(
            r'\[TARGET_SECTION:\s*(\{[^}]+\})\s*\]',
            re.IGNORECASE,
        )
        target_match = _TARGET_SECTION_PATTERN.search(reply_text)
        if target_match:
            raw_json = target_match.group(1)
            # Strip the marker from the reply regardless of JSON parse success.
            # Eliminar el marcador de la respuesta independientemente del éxito
            # del parseo JSON.
            reply_text = _TARGET_SECTION_PATTERN.sub("", reply_text).strip()
            try:
                marker_data    = json.loads(raw_json)
                section_name   = marker_data.get("name", "").strip()
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
