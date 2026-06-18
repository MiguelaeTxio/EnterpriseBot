# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/views.py
"""
View definitions for the chat module.
Implements IRC-style section chat room views with HTMX polling support,
and BREAKDOWNS management views for Hito 13 / Hito 14.

ChatRoomView                — full room page with message history (last 7 days).
ChatMessagesPollingView     — HTMX polling fragment every 3 seconds.
ChatRoomListView            — list of active rooms scoped to the user role.
ChatSendView                — POST broadcast to section contacts via WhatsApp.
ChatAliasSetView            — POST alias setup for CompanyUser.



BreakdownRoomManageView     — manage breakdown_sections and breakdown_contacts M2M.

Access control: CompanyUserRequiredMixin on all views.
WORKSHOP role: read-only in chat rooms.
ADMIN / SUPERVISOR / WORKSHOPBOSS: access to ticket management.
ADMIN only: BREAKDOWNS room membership management.
---
Definiciones de vistas para el módulo de chat.
Implementa vistas de sala IRC con polling HTMX y vistas de gestión de
averías para el Hito 13 / Hito 14.

ChatRoomView                — página completa de sala con historial 7 días.
ChatMessagesPollingView     — fragmento HTMX cada 3 segundos.
ChatRoomListView            — lista de salas activas acotada al rol del usuario.
ChatSendView                — POST broadcast a contactos de sección vía WhatsApp.
ChatAliasSetView            — POST para establecer alias del CompanyUser.



BreakdownRoomManageView     — gestión de breakdown_sections y breakdown_contacts M2M.

Control de acceso: CompanyUserRequiredMixin en todas las vistas.
Rol WORKSHOP: solo lectura en salas de chat.
ADMIN / SUPERVISOR / WORKSHOPBOSS: acceso a gestión de tickets.
Solo ADMIN: gestión de membresía de sala BREAKDOWNS.
"""

import logging

from django.shortcuts import render, get_object_or_404
from django.views import View
from django.utils.timezone import now
from datetime import timedelta

from panel.mixins import CompanyUserRequiredMixin
from chat.models import ChatRoom, ChatMessage

logger = logging.getLogger(__name__)


class ChatRoomView(CompanyUserRequiredMixin, View):
    """
    Renders the full IRC-style chat room page for a given ChatRoom.
    Loads the message history for the last 7 days ordered by created_at
    ascending. The template includes an HTMX polling block that refreshes
    the message fragment every 3 seconds via ChatMessagesPollingView.

    URL: GET /panel/chat/<room_pk>/

    Context variables:
      room         — ChatRoom instance.
      messages     — QuerySet of ChatMessage for the last 7 days.
      company      — Company of the authenticated user.
      company_user — CompanyUser of the authenticated user.
      own_presence — Current PresenceStatus (for base.html top bar).
      active_nav   — "chat" (drives sidebar active state).
      can_send     — True if the user role allows sending messages.
    ---
    Renderiza la página completa de la sala de chat IRC para una ChatRoom.
    Carga el historial de mensajes de los últimos 7 días ordenado por
    created_at ascendente. La plantilla incluye un bloque de polling HTMX
    que refresca el fragmento de mensajes cada 3 segundos mediante
    ChatMessagesPollingView.

    URL: GET /panel/chat/<room_pk>/

    Variables de contexto:
      room         — Instancia de ChatRoom.
      messages     — QuerySet de ChatMessage de los últimos 7 días.
      company      — Company del usuario autenticado.
      company_user — CompanyUser del usuario autenticado.
      own_presence — PresenceStatus activo (para la barra superior de base.html).
      active_nav   — "chat" (controla el estado activo del sidebar).
      can_send     — True si el rol del usuario permite enviar mensajes.
    """

    template_name = "panel/chat/room.html"

    def get(self, request, room_pk, *args, **kwargs):
        """
        Resolves the ChatRoom scoped to the authenticated user's company,
        loads the 7-day message history and renders the full room page.
        Returns HTTP 404 if the room does not belong to the user's company.
        ---
        Resuelve la ChatRoom acotada a la empresa del usuario autenticado,
        carga el historial de 7 días y renderiza la página completa de sala.
        Devuelve HTTP 404 si la sala no pertenece a la empresa del usuario.
        """
        from django.db.models import Q
        from ivr_config.models import PresenceStatus

        company_user = request.user.company_user
        company      = company_user.company

        # Scope room to authenticated user's company — security boundary.
        # Acotar sala a la empresa del usuario autenticado — frontera de seguridad.
        room = get_object_or_404(ChatRoom, pk=room_pk, company=company, is_active=True)

        # Load messages from the last 7 days ordered chronologically.
        # Cargar mensajes de los últimos 7 días ordenados cronológicamente.
        cutoff   = now() - timedelta(days=7)
        messages = (
            ChatMessage.objects
            .filter(room=room, created_at__gte=cutoff)
            .select_related("sender_contact", "sender_user__user")
            .order_by("created_at")
        )

        # Resolve current presence for the top bar.
        # Resolver la presencia actual para la barra superior.
        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        # BREAKDOWNS room is a read-only admin visor for all panel roles.
        # The bot-to-driver 1:1 conversation flow writes to it automatically.
        # In SECTION rooms all authorised roles may send panel messages.
        # La sala BREAKDOWNS es un visor de solo lectura para todos los roles
        # del panel — el flujo 1:1 bot-chofer escribe en ella automaticamente.
        # En salas SECTION todos los roles autorizados pueden enviar mensajes.
        if room.room_type == ChatRoom.ROOM_TYPE_BREAKDOWNS:
            can_send = False
        else:
            can_send = company_user.role in (
                company_user.ROLE_ADMIN,
                company_user.ROLE_SUPERVISOR,
                company_user.ROLE_WORKSHOPBOSS,
                company_user.ROLE_WORKSHOP,
                company_user.ROLE_DRIVER,
            )

        # Detect missing alias — modal will be shown in the template.
        # Detectar alias ausente — se mostrará el modal en la plantilla.
        alias_required = not bool(company_user.alias)

        # Resolve section members for the side panel.
        # For SECTION rooms: resolve Contact records assigned to the section
        # via the Section.contacts M2M, then collect their display names
        # (alias from linked CompanyUser, or Contact.name for external contacts).
        # For BREAKDOWNS rooms: collect members from breakdown_sections and
        # breakdown_contacts of the company BREAKDOWNS room.
        # Para salas SECTION: resolver Contact del M2M Section.contacts y
        # obtener su alias (CompanyUser vinculado) o nombre de Contact externo.
        # Para salas BREAKDOWNS: recoger miembros de breakdown_sections y
        # breakdown_contacts de la sala BREAKDOWNS de la empresa.
        section_members = []
        if room.room_type == ChatRoom.ROOM_TYPE_SECTION and room.section is not None:
            from ivr_config.models import Contact as _SectionContact
            _contacts = (
                _SectionContact.objects
                .filter(sections=room.section, company=company)
                .select_related("company_user__user")
                .order_by("name")
            )
            for _c in _contacts:
                if _c.company_user and _c.company_user.is_active:
                    _display = _c.company_user.alias or _c.company_user.user.username
                else:
                    _display = _c.alias if hasattr(_c, "alias") and _c.alias else _c.name
                section_members.append({"display": _display, "is_internal": _c.is_internal})

        elif room.room_type == ChatRoom.ROOM_TYPE_BREAKDOWNS:
            from chat.models import ChatRoom as _CR
            _bd_room = _CR.objects.filter(
                company=company,
                room_type=_CR.ROOM_TYPE_BREAKDOWNS,
                is_active=True,
            ).prefetch_related(
                "breakdown_sections__contacts__company_user__user",
                "breakdown_contacts__company_user__user",
            ).first()
            if _bd_room:
                _seen = set()
                for _sec in _bd_room.breakdown_sections.all():
                    for _c in _sec.contacts.filter(company=company):
                        if _c.pk in _seen:
                            continue
                        _seen.add(_c.pk)
                        if _c.company_user and _c.company_user.is_active:
                            _display = _c.company_user.alias or _c.company_user.user.username
                        else:
                            _display = _c.alias if hasattr(_c, "alias") and _c.alias else _c.name
                        section_members.append({"display": _display, "is_internal": _c.is_internal})
                for _c in _bd_room.breakdown_contacts.all():
                    if _c.pk in _seen:
                        continue
                    _seen.add(_c.pk)
                    if _c.company_user and _c.company_user.is_active:
                        _display = _c.company_user.alias or _c.company_user.user.username
                    else:
                        _display = _c.alias if hasattr(_c, "alias") and _c.alias else _c.name
                    section_members.append({"display": _display, "is_internal": _c.is_internal})
                section_members.sort(key=lambda m: m["display"].lower())

        return render(request, self.template_name, {
            "room":            room,
            "chat_messages":   messages,
            "company":         company,
            "company_user":    company_user,
            "own_presence":    own_presence,
            "active_nav":      "chat",
            "can_send":        can_send,
            "alias_required":  alias_required,
            "section_members": section_members,
        })


class ChatMessagesPollingView(CompanyUserRequiredMixin, View):
    """
    HTMX polling endpoint. Returns the messages fragment for the given room,
    containing all ChatMessage records from the last 7 days ordered by
    created_at ascending. Called every 3 seconds by the hx-trigger in room.html.
    Returns HTTP 404 if the room does not belong to the user's company.

    URL: GET /panel/chat/<room_pk>/messages/
    ---
    Endpoint de polling HTMX. Devuelve el fragmento de mensajes para la sala
    indicada, con todos los registros ChatMessage de los últimos 7 días
    ordenados por created_at ascendente. Llamado cada 3 segundos por el
    hx-trigger en room.html.
    Devuelve HTTP 404 si la sala no pertenece a la empresa del usuario.

    URL: GET /panel/chat/<room_pk>/messages/
    """

    template_name = "panel/chat/_messages_fragment.html"

    def get(self, request, room_pk, *args, **kwargs):
        """
        Returns the messages fragment for HTMX swap.
        ---
        Devuelve el fragmento de mensajes para el swap de HTMX.
        """
        company_user = request.user.company_user
        company      = company_user.company

        room = get_object_or_404(ChatRoom, pk=room_pk, company=company, is_active=True)

        cutoff   = now() - timedelta(days=7)
        messages = (
            ChatMessage.objects
            .filter(room=room, created_at__gte=cutoff)
            .select_related("sender_contact", "sender_user__user")
            .order_by("created_at")
        )

        return render(request, self.template_name, {
            "chat_messages": messages,
            "company_user":  company_user,
        })


class ChatRoomListView(CompanyUserRequiredMixin, View):
    """
    Lists all active ChatRoom instances belonging to the authenticated user's
    company. Used as the entry point for the "Chat de Secciones" sidebar section.
    Accessible to ADMIN and SUPERVISOR roles only.

    URL: GET /panel/chat/
    ---
    Lista todas las instancias ChatRoom activas pertenecientes a la empresa
    del usuario autenticado. Punto de entrada de la sección "Chat de Secciones"
    del sidebar. Accesible solo para los roles ADMIN y SUPERVISOR.

    URL: GET /panel/chat/
    """

    template_name = "panel/chat/room_list.html"

    def get(self, request, *args, **kwargs):
        """
        Resolves the company's active rooms and renders the room list page.
        ---
        Resuelve las salas activas de la empresa y renderiza la lista de salas.
        """
        from django.db.models import Q
        from ivr_config.models import PresenceStatus

        company_user = request.user.company_user
        company      = company_user.company

        # ADMIN and SUPERVISOR see all active rooms.
        # WORKSHOP and DRIVER see only their own section room and the BREAKDOWNS room.
        # Any other role is forbidden.
        # ADMIN y SUPERVISOR ven todas las salas activas.
        # WORKSHOP y DRIVER ven solo su sala de seccion y la sala BREAKDOWNS.
        # Cualquier otro rol recibe 403.
        # Any other role receives HTTP 403.
        _allowed_roles = (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
            company_user.ROLE_WORKSHOP,
            company_user.ROLE_DRIVER,
        )
        if company_user.role not in _allowed_roles:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        if company_user.role in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
            rooms = (
                ChatRoom.objects
                .filter(company=company, is_active=True)
                .select_related("section")
                .order_by("room_type", "name")
            )
        else:
            # Resolve the section assigned to this WORKSHOPBOSS/WORKSHOP/DRIVER contact.
            # WORKSHOPBOSS sees their own SECTION room plus the BREAKDOWNS room.
            # WORKSHOP and DRIVER see only their own SECTION room.
            # Resolver la seccion asignada al contacto WORKSHOPBOSS/WORKSHOP/DRIVER.
            # WORKSHOPBOSS ve su sala SECTION y la sala BREAKDOWNS.
            # WORKSHOP y DRIVER ven solo su sala SECTION.
            from ivr_config.models import Contact
            from django.db.models import Q
            _contact = Contact.objects.filter(
                company=company,
                company_user=company_user,
            ).first()
            _section = (
                _contact.sections.filter(company=company).first()
                if _contact else None
            )
            if company_user.role == company_user.ROLE_WORKSHOPBOSS:
                rooms = (
                    ChatRoom.objects
                    .filter(company=company, is_active=True)
                    .filter(
                        Q(room_type=ChatRoom.ROOM_TYPE_BREAKDOWNS) |
                        Q(room_type=ChatRoom.ROOM_TYPE_SECTION, section=_section)
                    )
                    .select_related("section")
                    .order_by("room_type", "name")
                )
            else:
                # WORKSHOP and DRIVER — own SECTION room only.
                # WORKSHOP y DRIVER — solo su sala SECTION.
                rooms = (
                    ChatRoom.objects
                    .filter(
                        company=company,
                        is_active=True,
                        room_type=ChatRoom.ROOM_TYPE_SECTION,
                        section=_section,
                    )
                    .select_related("section")
                    .order_by("name")
                )

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        return render(request, self.template_name, {
            "rooms":        rooms,
            "company":      company,
            "company_user": company_user,
            "own_presence": own_presence,
            "active_nav":   "chat",
        })


class ChatSendView(CompanyUserRequiredMixin, View):
    """
    POST endpoint for sending a message from the panel to all active section
    members via WhatsApp broadcast.

    Workflow:
      1. Validate that the CompanyUser has ADMIN or SUPERVISOR role.
      2. Resolve the sender alias from the linked Contact (is_internal=True).
         If no alias is configured, return HTTP 400 with an error message.
      3. Validate the message body (non-empty, max 2000 chars).
      4. Create ChatMessage(OUTBOUND) with the prefixed body "{alias}: {body}".
      5. Broadcast to all section contacts with alias and active WhatsApp
         session (24-hour window) via Twilio, excluding the sender.
      6. Return HTTP 200 JSON on success or HTTP 4xx on validation error.

    URL: POST /panel/chat/<room_pk>/send/
    ---
    Endpoint POST para enviar un mensaje desde el panel a todos los miembros
    activos de la sección vía broadcast WhatsApp.

    Flujo:
      1. Validar que el CompanyUser tiene rol ADMIN o SUPERVISOR.
      2. Resolver el alias del remitente desde el Contact vinculado (is_internal=True).
         Si no hay alias configurado, devolver HTTP 400 con mensaje de error.
      3. Validar el cuerpo del mensaje (no vacío, máx. 2000 chars).
      4. Crear ChatMessage(OUTBOUND) con el cuerpo prefijado "{alias}: {cuerpo}".
      5. Broadcast a todos los contactos de la sección con alias y sesión WhatsApp
         activa (ventana de 24h) vía Twilio, excluyendo al remitente.
      6. Devolver HTTP 200 JSON en caso de éxito o HTTP 4xx en error de validación.

    URL: POST /panel/chat/<room_pk>/send/
    """

    def post(self, request, room_pk, *args, **kwargs):
        """
        Validates, persists and broadcasts an outbound chat message.
        ---
        Valida, persiste y difunde un mensaje de chat saliente.
        """
        import json
        from django.http import JsonResponse
        from ivr_config.models import PhoneNumber
        from whatsapp.models import WhatsAppSession
        from whatsapp.services import WhatsAppChatService

        company_user = request.user.company_user
        company      = company_user.company

        # --- Step 1: Role guard — ADMIN, SUPERVISOR, WORKSHOP and DRIVER can send. ---
        # --- Step 1: Role guard — ADMIN, SUPERVISOR, WORKSHOPBOSS, WORKSHOP and DRIVER can send. ---
        # --- Paso 1: Guardia de rol — ADMIN, SUPERVISOR, WORKSHOPBOSS, WORKSHOP y DRIVER pueden enviar. ---
        if company_user.role not in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
            company_user.ROLE_WORKSHOP,
            company_user.ROLE_DRIVER,
        ):
            return JsonResponse(
                {"error": "Tu rol no permite enviar mensajes en el chat."},
                status=403,
            )

        # --- Step 2: Resolve sender alias from CompanyUser.alias (canonical source). ---
        # --- Paso 2: Resolver alias del remitente desde CompanyUser.alias (fuente canónica). ---
        sender_alias = company_user.alias.strip()

        if not sender_alias:
            return JsonResponse(
                {
                    "error": (
                        "No tienes un alias configurado. "
                        "Configúralo desde la sala de chat antes de enviar mensajes."
                    )
                },
                status=400,
            )

        # --- Step 3: Resolve room scoped to company. ---
        # --- Paso 3: Resolver sala acotada a la empresa. ---
        room = get_object_or_404(ChatRoom, pk=room_pk, company=company, is_active=True)

        # --- Step 4: Validate message body. ---
        # --- Paso 4: Validar el cuerpo del mensaje. ---
        try:
            payload = json.loads(request.body)
            body    = payload.get("body", "").strip()
        except (json.JSONDecodeError, AttributeError):
            body = request.POST.get("body", "").strip()

        if not body:
            return JsonResponse(
                {"error": "El mensaje no puede estar vacío."},
                status=400,
            )
        if len(body) > 2000:
            return JsonResponse(
                {"error": "El mensaje supera el límite de 2000 caracteres."},
                status=400,
            )

        # --- Step 5: Persist outbound ChatMessage. ---
        # --- Paso 5: Persistir ChatMessage saliente. ---
        prefixed_body = f"{sender_alias}: {body}"
        chat_message  = ChatMessage.objects.create(
            room=room,
            direction=ChatMessage.DIRECTION_OUTBOUND,
            sender_user=company_user,
            body=prefixed_body,
            whatsapp_sid="",
        )

        # --- Step 6: Broadcast to section contacts via Twilio. ---
        # --- Paso 6: Broadcast a contactos de la sección vía Twilio. ---
        section = room.section
        if section is None:
            # BREAKDOWNS room — no section broadcast.
            # Sala BREAKDOWNS — sin broadcast de sección.
            return JsonResponse({"ok": True, "message_pk": chat_message.pk})

        phone_record = PhoneNumber.objects.filter(
            company=company,
            is_active=True,
            capabilities__in=[
                PhoneNumber.CAPABILITY_WHATSAPP,
                PhoneNumber.CAPABILITY_BOTH,
            ],
        ).first()

        if phone_record is None:
            return JsonResponse(
                {"error": "No hay número WhatsApp activo para esta empresa."},
                status=500,
            )

        from_number = phone_record.number

        # Exclude the sender's own contact from the broadcast.
        # Excluir el propio contacto del remitente del broadcast.
        internal_contact = (
            company_user.contact_profile
            .filter(is_internal=True, company=company)
            .first()
        )
        sender_phone = internal_contact.phone_number if internal_contact else None

        # Broadcast to ALL section contacts with a phone number,
        # regardless of alias — contacts without alias receive the message
        # and are prompted to set their alias when they reply.
        # Broadcast a TODOS los contactos de la sección con número de teléfono,
        # independientemente del alias — los contactos sin alias reciben el mensaje
        # y se les pide que configuren su alias cuando respondan.
        section_contacts = (
            section.contacts
            .filter(phone_number__gt="")
            .values_list("phone_number", "alias")
        )

        sent          = 0
        skipped       = 0
        out_of_window = []

        import json as _json
        from whatsapp.models import WhatsAppTemplate

        # Resolve onboarding and renewal templates once — reused per contact.
        # Resolver templates de onboarding y renewal una vez — reutilizados por contacto.
        _onboarding_template = WhatsAppTemplate.objects.filter(
            company=company, name="chat_onboarding", is_active=True,
        ).first()
        _renewal_template = WhatsAppTemplate.objects.filter(
            company=company, name="chat_session_renewal", is_active=True,
        ).first()
        _twilio_client = __import__(
            "whatsapp.services", fromlist=["_build_twilio_client"]
        )._build_twilio_client()

        for phone_number, alias in section_contacts:
            if phone_number == sender_phone:
                continue

            # Resolve contact object and canonical alias.
            # Resolver objeto de contacto y alias canónico.
            _contact_obj = section.contacts.filter(phone_number=phone_number).first()
            _receiver_alias = ""
            if _contact_obj:
                if _contact_obj.company_user_id and _contact_obj.company_user:
                    _receiver_alias = (_contact_obj.company_user.alias or "").strip()
                if not _receiver_alias:
                    _receiver_alias = (_contact_obj.alias or "").strip()
            _contact_name = (
                _contact_obj.name if _contact_obj and _contact_obj.name
                else phone_number
            )

            # Check 24h session window.
            # Comprobar ventana de sesión de 24h.
            _window_cutoff = now() - timedelta(hours=24)
            has_active_session = WhatsAppSession.objects.filter(
                company=company,
                phone_number=phone_number,
                is_active=True,
                last_message_at__gte=_window_cutoff,
            ).exists()

            # --- Case 1: No alias — send chat_onboarding. ---
            # The message is stored in the room; the contact will receive it
            # automatically after completing the onboarding flow.
            # --- Caso 1: Sin alias — enviar chat_onboarding. ---
            # El mensaje queda almacenado en la sala; el contacto lo recibirá
            # automáticamente al completar el flujo de onboarding.
            if not _receiver_alias:
                try:
                    if _onboarding_template:
                        _twilio_client.messages.create(
                            from_=f"whatsapp:{from_number}",
                            to=f"whatsapp:{phone_number}",
                            content_sid=_onboarding_template.content_sid,
                            content_variables=_json.dumps({
                                "1": _contact_name,
                                "2": company.name,
                            }),
                        )
                        logger.info(
                            "# [CHAT SEND] chat_onboarding enviado a %s (sin alias).",
                            phone_number,
                        )
                    else:
                        logger.warning(
                            "# [CHAT SEND] Template chat_onboarding no encontrado "
                            "para empresa %s — contacto %s omitido.",
                            company.name, phone_number,
                        )
                except Exception as _exc:
                    logger.error(
                        "# [CHAT SEND] Error enviando chat_onboarding a %s: %s",
                        phone_number, _exc,
                    )
                out_of_window.append(_contact_name)
                skipped += 1
                continue

            # --- Case 2: Alias present, outside 24h window — send chat_session_renewal. ---
            # The message body is queued in pending_broadcast_messages so that
            # when the contact accepts the renewal (opt_in), the original message
            # is delivered automatically.
            # --- Caso 2: Alias presente, fuera de ventana 24h — enviar chat_session_renewal. ---
            # El cuerpo del mensaje se encola en pending_broadcast_messages para que,
            # cuando el contacto acepte el renewal (opt_in), el mensaje original se
            # entregue automáticamente.
            if not has_active_session:
                try:
                    if _renewal_template:
                        _twilio_client.messages.create(
                            from_=f"whatsapp:{from_number}",
                            to=f"whatsapp:{phone_number}",
                            content_sid=_renewal_template.content_sid,
                            content_variables=_json.dumps({"1": _receiver_alias}),
                        )
                        logger.info(
                            "# [CHAT SEND] chat_session_renewal enviado a %s (%s) — fuera de ventana.",
                            _receiver_alias, phone_number,
                        )
                        # Queue the message for delivery on opt_in.
                        # Encolar el mensaje para entrega al hacer opt_in.
                        try:
                            _pending_session = WhatsAppSession.objects.filter(
                                company=company,
                                phone_number=phone_number,
                            ).order_by("-session_start").first()
                            if _pending_session is not None:
                                _existing = list(
                                    _pending_session.pending_broadcast_messages or []
                                )
                                _existing.append({
                                    "body": prefixed_body,
                                    "created_at": now().isoformat(),
                                })
                                _pending_session.pending_broadcast_messages = _existing
                                _pending_session.save(
                                    update_fields=["pending_broadcast_messages"]
                                )
                                logger.info(
                                    "# [CHAT SEND] Mensaje encolado en pending_broadcast_messages "
                                    "para %s (%s).",
                                    _receiver_alias, phone_number,
                                )
                        except Exception as _queue_exc:
                            logger.error(
                                "# [CHAT SEND] Error encolando mensaje pendiente para %s: %s",
                                phone_number, _queue_exc,
                            )
                        out_of_window.append(_receiver_alias)
                        skipped += 1
                        continue
                    else:
                        logger.warning(
                            "# [CHAT SEND] Template chat_session_renewal no encontrado "
                            "para empresa %s — contacto %s omitido.",
                            company.name, phone_number,
                        )
                        out_of_window.append(_receiver_alias)
                        skipped += 1
                        continue
                except Exception as _exc:
                    logger.error(
                        "# [CHAT SEND] Error enviando chat_session_renewal a %s: %s",
                        phone_number, _exc,
                    )
                    out_of_window.append(_receiver_alias)
                    skipped += 1
                    continue

            # --- Case 3: Alias present, within 24h window — send message directly. ---
            # Also reached after a successful renewal (window reopened by the template). ---
            # --- Caso 3: Alias presente, dentro de ventana 24h — enviar mensaje directamente. ---
            # También se alcanza tras un renewal exitoso (ventana reabierta por el template). ---
            try:
                sid = WhatsAppChatService.send_reply(
                    from_number=from_number,
                    to_number=phone_number,
                    reply_text=prefixed_body,
                )
                chat_message.whatsapp_sid = sid or ""
                sent += 1
                logger.info(
                    "# [CHAT SEND] Mensaje enviado a %s (%s).",
                    _receiver_alias, phone_number,
                )
            except Exception as _exc:
                logger.error(
                    "# [CHAT SEND] Error enviando mensaje a %s (%s): %s",
                    _receiver_alias, phone_number, _exc,
                )
                skipped += 1

        if sent > 0:
            chat_message.save(update_fields=["whatsapp_sid"])

        return JsonResponse({
            "ok":           True,
            "message_pk":   chat_message.pk,
            "sent":         sent,
            "skipped":      skipped,
            "out_of_window": out_of_window,
        })


class ChatAliasSetView(CompanyUserRequiredMixin, View):
    """
    POST endpoint for setting the alias of the authenticated CompanyUser.
    Called from the alias modal in room.html when the user submits their
    chosen alias for the first time.
    URL: POST /panel/chat/alias/set/
    ---
    Endpoint POST para establecer el alias del CompanyUser autenticado.
    Llamado desde el modal de alias en room.html cuando el usuario envia
    su alias elegido por primera vez.
    URL: POST /panel/chat/alias/set/
    """

    def post(self, request, *args, **kwargs):
        """
        Validates and persists the chosen alias for the authenticated CompanyUser.
        ---
        Valida y persiste el alias elegido para el CompanyUser autenticado.
        """
        import json
        from django.http import JsonResponse

        company_user = request.user.company_user

        try:
            payload = json.loads(request.body)
            alias   = payload.get("alias", "").strip()
        except (json.JSONDecodeError, AttributeError):
            alias = request.POST.get("alias", "").strip()

        if not alias:
            return JsonResponse(
                {"error": "El alias no puede estar vacio."},
                status=400,
            )

        if len(alias) > 50:
            return JsonResponse(
                {"error": "El alias no puede superar los 50 caracteres."},
                status=400,
            )

        company_user.alias = alias
        company_user.save(update_fields=["alias"])

        return JsonResponse({"ok": True, "alias": alias})



class BreakdownRoomManageView(CompanyUserRequiredMixin, View):
    """
    Manages the breakdown_sections and breakdown_contacts M2M membership of the
    company's BREAKDOWNS ChatRoom. Allows ADMIN and SUPERVISOR to add or remove
    sections and individual contacts from the room's access list.

    GET  — renders the management form with current membership.
    POST — processes add/remove actions for sections and contacts.

    URL: GET/POST /panel/chat/breakdowns/manage/
    ---
    Gestiona la membresía M2M breakdown_sections y breakdown_contacts de la
    ChatRoom BREAKDOWNS de la empresa. Permite a ADMIN y SUPERVISOR añadir o
    quitar secciones y contactos individuales de la lista de acceso.

    GET  — renderiza el formulario de gestión con la membresía actual.
    POST — procesa acciones de añadir/quitar secciones y contactos.

    URL: GET/POST /panel/chat/breakdowns/manage/
    """

    template_name = "panel/chat/breakdown_room_manage.html"

    def _get_breakdown_room(self, company):
        """
        Returns the BREAKDOWNS ChatRoom for the company, or None if not found.
        ---
        Devuelve la ChatRoom BREAKDOWNS de la empresa, o None si no existe.
        """
        return ChatRoom.objects.filter(
            company=company,
            room_type=ChatRoom.ROOM_TYPE_BREAKDOWNS,
            is_active=True,
        ).first()

    def get(self, request, *args, **kwargs):
        """
        Renders the breakdown room management page.
        ---
        Renderiza la página de gestión de la sala de averías.
        """
        from django.db.models import Q
        from ivr_config.models import PresenceStatus, Section, Contact

        company_user = request.user.company_user
        company      = company_user.company

        if company_user.role not in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        breakdown_room = self._get_breakdown_room(company)

        all_sections = Section.objects.filter(company=company).order_by("name")
        all_contacts = (
            Contact.objects.filter(company=company)
            .exclude(phone_number="")
            .order_by("name")
        )

        member_section_pks = set(
            breakdown_room.breakdown_sections.values_list("pk", flat=True)
        ) if breakdown_room else set()

        member_contact_pks = set(
            breakdown_room.breakdown_contacts.values_list("pk", flat=True)
        ) if breakdown_room else set()

        # Detect incomplete sections: sections in member_section_pks that have
        # at least one contact individually excluded (not in breakdown_contacts)
        # but whose section IS in breakdown_sections.
        # For each added section, retrieve its contacts and check whether any
        # of them has been individually removed (i.e. not in member_contact_pks
        # AND the contact is a member of that section but was never added back).
        # Detectar secciones incompletas: secciones añadidas que tienen algún
        # contacto individual excluido (eliminado manualmente de breakdown_contacts).
        incomplete_section_pks = set()
        if breakdown_room and member_section_pks:
            from ivr_config.models import Contact as _Contact
            for _sec in all_sections:
                if _sec.pk not in member_section_pks:
                    continue
                # Contacts of this section that have a phone number.
                # Contactos de esta sección con número de teléfono.
                _sec_contact_pks = set(
                    _Contact.objects
                    .filter(sections=_sec)
                    .exclude(phone_number="")
                    .values_list("pk", flat=True)
                )
                # If any section contact is not in breakdown_contacts, the section
                # is incomplete (some members were individually removed).
                # Si algún contacto de la sección no está en breakdown_contacts,
                # la sección está incompleta (algunos miembros se quitaron individualmente).
                if _sec_contact_pks and not _sec_contact_pks.issubset(member_contact_pks):
                    incomplete_section_pks.add(_sec.pk)

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        return render(request, self.template_name, {
            "breakdown_room":         breakdown_room,
            "all_sections":           all_sections,
            "all_contacts":           all_contacts,
            "member_section_pks":     member_section_pks,
            "member_contact_pks":     member_contact_pks,
            "incomplete_section_pks": incomplete_section_pks,
            "company_user":           company_user,
            "own_presence":           own_presence,
            "active_nav":             "chat",
        })

    def post(self, request, *args, **kwargs):
        """
        Adds or removes sections/contacts from the BREAKDOWNS room membership.
        ---
        Añade o quita secciones/contactos de la membresía de la sala BREAKDOWNS.
        """
        from django.http import HttpResponseForbidden
        from django.shortcuts import redirect
        from ivr_config.models import Section, Contact

        company_user = request.user.company_user
        company      = company_user.company

        if company_user.role not in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
        ):
            return HttpResponseForbidden()

        breakdown_room = self._get_breakdown_room(company)
        if breakdown_room is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound()

        action      = request.POST.get("action", "").strip()
        section_pk  = request.POST.get("section_pk", "").strip()
        contact_pk  = request.POST.get("contact_pk", "").strip()

        if action == "add_section" and section_pk:
            try:
                section = Section.objects.get(pk=section_pk, company=company)
                breakdown_room.breakdown_sections.add(section)
                # Sync: add all contacts of this section with a phone number
                # to breakdown_contacts so member_contact_pks is consistent.
                # Sincronizar: añadir todos los contactos de la sección con teléfono
                # a breakdown_contacts para que member_contact_pks sea consistente.
                _section_contacts = Contact.objects.filter(
                    sections=section,
                ).exclude(phone_number="")
                for _sc in _section_contacts:
                    breakdown_room.breakdown_contacts.add(_sc)
                logger.info(
                    "# [BREAKDOWN] Seccion pk=%s anadida a sala BREAKDOWNS pk=%s (%d contactos sincronizados).",
                    section.pk, breakdown_room.pk, _section_contacts.count(),
                )
            except Section.DoesNotExist:
                pass

        elif action == "remove_section" and section_pk:
            try:
                section = Section.objects.get(pk=section_pk, company=company)
                breakdown_room.breakdown_sections.remove(section)
                # Sync: remove all contacts of this section from breakdown_contacts
                # unless they belong to another added section.
                # Sincronizar: quitar los contactos de la sección de breakdown_contacts
                # salvo que pertenezcan a otra sección añadida.
                _remaining_section_pks = set(
                    breakdown_room.breakdown_sections.values_list("pk", flat=True)
                )
                _section_contacts = Contact.objects.filter(
                    sections=section,
                ).exclude(phone_number="")
                for _sc in _section_contacts:
                    # Keep contact if it belongs to another remaining section.
                    # Conservar el contacto si pertenece a otra sección restante.
                    _other_sections = set(
                        _sc.sections.values_list("pk", flat=True)
                    ) & _remaining_section_pks
                    if not _other_sections:
                        breakdown_room.breakdown_contacts.remove(_sc)
                logger.info(
                    "# [BREAKDOWN] Seccion pk=%s eliminada de sala BREAKDOWNS pk=%s.",
                    section.pk, breakdown_room.pk,
                )
            except Section.DoesNotExist:
                pass

        elif action == "add_contact" and contact_pk:
            try:
                contact = Contact.objects.get(pk=contact_pk, company=company)
                breakdown_room.breakdown_contacts.add(contact)
                logger.info(
                    "# [BREAKDOWN] Contacto pk=%s anadido a sala BREAKDOWNS pk=%s.",
                    contact.pk, breakdown_room.pk,
                )
            except Contact.DoesNotExist:
                pass

        elif action == "remove_contact" and contact_pk:
            try:
                contact = Contact.objects.get(pk=contact_pk, company=company)
                breakdown_room.breakdown_contacts.remove(contact)
                logger.info(
                    "# [BREAKDOWN] Contacto pk=%s eliminado de sala BREAKDOWNS pk=%s.",
                    contact.pk, breakdown_room.pk,
                )
            except Contact.DoesNotExist:
                pass

        return redirect("panel:breakdown_room_manage")
