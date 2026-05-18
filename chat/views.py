# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/views.py
"""
View definitions for the chat module.
Implements IRC-style section chat room views with HTMX polling support,
and BREAKDOWNS management views for Paso 12 (Hito 13).

ChatRoomView              — full room page with message history (last 7 days).
ChatMessagesPollingView   — HTMX polling fragment every 3 seconds.
ChatRoomListView          — list of active rooms (ADMIN / SUPERVISOR).
ChatSendView              — POST broadcast to section contacts via WhatsApp.
ChatAliasSetView          — POST alias setup for CompanyUser.
BreakdownTicketListView   — list of all BreakdownTickets for the company.
BreakdownTicketDetailView — detail + actions (convert to repair order, close).
BreakdownRoomManageView   — manage breakdown_sections and breakdown_contacts M2M.

Access control: CompanyUserRequiredMixin on all views.
WORKSHOP role: read-only in chat rooms.
ADMIN / SUPERVISOR: full access including BREAKDOWNS management.
---
Definiciones de vistas para el módulo de chat.
Implementa vistas de sala IRC con polling HTMX y vistas de gestión de
averías para el Paso 12 (Hito 13).

ChatRoomView              — página completa de sala con historial 7 días.
ChatMessagesPollingView   — fragmento HTMX cada 3 segundos.
ChatRoomListView          — lista de salas activas (ADMIN / SUPERVISOR).
ChatSendView              — POST broadcast a contactos de sección vía WhatsApp.
ChatAliasSetView          — POST para establecer alias del CompanyUser.
BreakdownTicketListView   — lista de todos los BreakdownTickets de la empresa.
BreakdownTicketDetailView — detalle + acciones (convertir en OT, cerrar).
BreakdownRoomManageView   — gestión de breakdown_sections y breakdown_contacts M2M.

Control de acceso: CompanyUserRequiredMixin en todas las vistas.
Rol WORKSHOP: solo lectura en salas de chat.
ADMIN / SUPERVISOR: acceso completo incluida gestión de BREAKDOWNS.
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

        # WORKSHOP role is read-only — cannot send messages.
        # El rol WORKSHOP es de solo lectura — no puede enviar mensajes.
        can_send = company_user.role in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
        )

        # Detect missing alias — modal will be shown in the template.
        # Detectar alias ausente — se mostrará el modal en la plantilla.
        alias_required = not bool(company_user.alias)

        # Resolve section members for the side panel — CompanyUser records
        # assigned to the room's section, ordered by alias.
        # Only populated for SECTION rooms; BREAKDOWNS rooms have no section.
        # Resolver miembros de la sección para el panel lateral — registros
        # CompanyUser asignados a la sección de la sala, ordenados por alias.
        # Solo se rellena para salas SECTION; las salas BREAKDOWNS no tienen sección.
        section_members = []
        if room.section is not None:
            from ivr_config.models import CompanyUser
            section_members = list(
                CompanyUser.objects.filter(
                    company=company,
                    is_active=True,
                    contact_profile__sections=room.section,
                ).select_related("user")
                .order_by("alias", "user__username")
                .distinct()
            )

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

        # Restrict to ADMIN and SUPERVISOR — WORKSHOP has no chat list access.
        # Restringir a ADMIN y SUPERVISOR — WORKSHOP no tiene acceso a la lista.
        if company_user.role not in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        rooms = (
            ChatRoom.objects
            .filter(company=company, is_active=True)
            .select_related("section")
            .order_by("room_type", "name")
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

        # --- Step 1: Role guard — only ADMIN and SUPERVISOR can send. ---
        # --- Paso 1: Guardia de rol — solo ADMIN y SUPERVISOR pueden enviar. ---
        if company_user.role not in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
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

        sent    = 0
        skipped = 0
        out_of_window = []

        for phone_number, alias in section_contacts:
            if phone_number == sender_phone:
                continue

            # A session is considered active only if last_message_at
            # is within the last 24 hours — Twilio's conversation window.
            # Una sesión se considera activa solo si last_message_at
            # está dentro de las últimas 24 horas — ventana de Twilio.
            _window_cutoff = now() - timedelta(hours=24)
            has_active_session = WhatsAppSession.objects.filter(
                company=company,
                phone_number=phone_number,
                is_active=True,
                last_message_at__gte=_window_cutoff,
            ).exists()

            # Resolve contact alias — check CompanyUser.alias if linked.
            # Resolver alias del contacto — comprobar CompanyUser.alias si está vinculado.
            _contact_obj = section.contacts.filter(phone_number=phone_number).first()
            _receiver_alias = ""
            if _contact_obj:
                if _contact_obj.company_user_id and _contact_obj.company_user:
                    _receiver_alias = _contact_obj.company_user.alias.strip()
                if not _receiver_alias:
                    _receiver_alias = _contact_obj.alias.strip()
            _contact_name = (
                _contact_obj.name if _contact_obj and _contact_obj.name
                else phone_number
            )

            # If receiver has no alias OR is outside 24h window — send chat_onboarding.
            # Si el receptor no tiene alias O está fuera de ventana 24h — enviar chat_onboarding.
            needs_onboarding = not _receiver_alias or not has_active_session
            if needs_onboarding:
                try:
                    import json as _json
                    from whatsapp.models import WhatsAppTemplate
                    _onboarding_template = WhatsAppTemplate.objects.filter(
                        company=company,
                        name="chat_onboarding",
                        is_active=True,
                    ).first()
                    if _onboarding_template:
                        _twilio_client = __import__(
                            "whatsapp.services", fromlist=["_build_twilio_client"]
                        )._build_twilio_client()
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
                            "# [CHAT SEND] Template chat_onboarding enviado a %s (sin alias o fuera de ventana).",
                            phone_number,
                        )
                        out_of_window.append(_receiver_alias or _contact_name)
                    else:
                        logger.warning(
                            "# [CHAT SEND] Template chat_onboarding no encontrado "
                            "para empresa %s. Contacto %s omitido.",
                            company.name,
                            phone_number,
                        )
                        out_of_window.append(_receiver_alias or _contact_name)
                except Exception as _exc:
                    logger.error(
                        "# [CHAT SEND] Error enviando template chat_onboarding a %s: %s",
                        phone_number,
                        _exc,
                    )
                    out_of_window.append(_receiver_alias or _contact_name)
                skipped += 1
                continue

            try:
                sid = WhatsAppChatService.send_reply(
                    from_number=from_number,
                    to_number=phone_number,
                    reply_text=prefixed_body,
                )
                # Update whatsapp_sid with the last successful SID.
                # Actualizar whatsapp_sid con el último SID exitoso.
                chat_message.whatsapp_sid = sid or ""
                sent += 1
            except Exception as exc:
                import logging as _logging
                _logging.getLogger(__name__).error(
                    "# [CHAT SEND] Error enviando a %s (%s): %s",
                    alias, phone_number, exc,
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


class BreakdownTicketListView(CompanyUserRequiredMixin, View):
    """
    Lists all BreakdownTickets for the authenticated user's company,
    ordered by created_at descending. Supports optional filters:
    status, is_repair_order.
    Accessible to ADMIN and SUPERVISOR roles only.

    URL: GET /panel/chat/breakdowns/tickets/
    ---
    Lista todos los BreakdownTickets de la empresa del usuario autenticado,
    ordenados por created_at descendente. Soporta filtros opcionales:
    status, is_repair_order.
    Accesible solo para los roles ADMIN y SUPERVISOR.

    URL: GET /panel/chat/breakdowns/tickets/
    """

    template_name = "panel/chat/breakdown_ticket_list.html"

    def get(self, request, *args, **kwargs):
        """
        Resolves and filters BreakdownTickets scoped to the company.
        ---
        Resuelve y filtra BreakdownTickets acotados a la empresa.
        """
        from django.db.models import Q
        from ivr_config.models import PresenceStatus
        from chat.models import BreakdownTicket

        company_user = request.user.company_user
        company      = company_user.company

        if company_user.role not in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        qs = (
            BreakdownTicket.objects
            .filter(room__company=company)
            .select_related("contact", "machine", "section", "resolved_by__user")
            .order_by("-created_at")
        )

        status_filter = request.GET.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        repair_filter = request.GET.get("is_repair_order", "").strip()
        if repair_filter in ("1", "true"):
            qs = qs.filter(is_repair_order=True)
        elif repair_filter in ("0", "false"):
            qs = qs.filter(is_repair_order=False)

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        return render(request, self.template_name, {
            "tickets":       qs,
            "company":       company,
            "company_user":  company_user,
            "own_presence":  own_presence,
            "active_nav":    "chat",
            "status_filter": status_filter,
            "repair_filter": repair_filter,
            "STATUS_CHOICES": BreakdownTicket.STATUS_CHOICES,
        })


class BreakdownTicketDetailView(CompanyUserRequiredMixin, View):
    """
    Displays a single BreakdownTicket with its conversation turns and photos.
    Provides two POST actions:
      action=convert_repair — sets is_repair_order=True.
      action=close          — sets status=RESOLVED, resolved_by, resolved_at.
    Accessible to ADMIN and SUPERVISOR roles only.

    URL: GET/POST /panel/chat/breakdowns/tickets/<pk>/
    ---
    Muestra un BreakdownTicket individual con sus turnos de conversación y fotos.
    Proporciona dos acciones POST:
      action=convert_repair — establece is_repair_order=True.
      action=close          — establece status=RESOLVED, resolved_by, resolved_at.
    Accesible solo para los roles ADMIN y SUPERVISOR.

    URL: GET/POST /panel/chat/breakdowns/tickets/<pk>/
    """

    template_name = "panel/chat/breakdown_ticket_detail.html"

    def _get_ticket(self, request, pk):
        """
        Resolves the BreakdownTicket scoped to the company. Returns 404 if not found.
        ---
        Resuelve el BreakdownTicket acotado a la empresa. Devuelve 404 si no existe.
        """
        from chat.models import BreakdownTicket
        return get_object_or_404(
            BreakdownTicket,
            pk=pk,
            room__company=request.user.company_user.company,
        )

    def get(self, request, pk, *args, **kwargs):
        """
        Renders the ticket detail page.
        ---
        Renderiza la página de detalle del ticket.
        """
        from django.db.models import Q
        from ivr_config.models import PresenceStatus
        from chat.models import BreakdownConversationTurn

        company_user = request.user.company_user

        if company_user.role not in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        ticket = self._get_ticket(request, pk)
        turns  = BreakdownConversationTurn.objects.filter(
            ticket=ticket,
        ).order_by("created_at")

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        return render(request, self.template_name, {
            "ticket":       ticket,
            "turns":        turns,
            "company_user": company_user,
            "own_presence": own_presence,
            "active_nav":   "chat",
        })

    def post(self, request, pk, *args, **kwargs):
        """
        Handles convert_repair and close actions on the ticket.
        ---
        Gestiona las acciones convert_repair y close sobre el ticket.
        """
        from django.http import HttpResponseForbidden
        from django.shortcuts import redirect
        from chat.models import BreakdownTicket

        company_user = request.user.company_user

        if company_user.role not in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
            return HttpResponseForbidden()

        ticket = self._get_ticket(request, pk)
        action = request.POST.get("action", "").strip()

        if action == "convert_repair":
            ticket.is_repair_order = True
            ticket.save(update_fields=["is_repair_order"])
            logger.info(
                "# [BREAKDOWN] Ticket pk=%s convertido en orden de reparacion por usuario pk=%s.",
                ticket.pk, company_user.pk,
            )

        elif action == "close":
            ticket.status      = BreakdownTicket.STATUS_RESOLVED
            ticket.resolved_by = company_user
            ticket.resolved_at = now()
            ticket.save(update_fields=["status", "resolved_by", "resolved_at"])
            logger.info(
                "# [BREAKDOWN] Ticket pk=%s cerrado por usuario pk=%s.",
                ticket.pk, company_user.pk,
            )

        return redirect("panel:breakdown_ticket_detail", pk=ticket.pk)


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

        all_sections = Section.objects.filter(company=company, is_active=True).order_by("name")
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

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        return render(request, self.template_name, {
            "breakdown_room":     breakdown_room,
            "all_sections":       all_sections,
            "all_contacts":       all_contacts,
            "member_section_pks": member_section_pks,
            "member_contact_pks": member_contact_pks,
            "company_user":       company_user,
            "own_presence":       own_presence,
            "active_nav":         "chat",
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

        if company_user.role not in (company_user.ROLE_ADMIN, company_user.ROLE_SUPERVISOR):
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
                logger.info(
                    "# [BREAKDOWN] Seccion pk=%s anadida a sala BREAKDOWNS pk=%s.",
                    section.pk, breakdown_room.pk,
                )
            except Section.DoesNotExist:
                pass

        elif action == "remove_section" and section_pk:
            try:
                section = Section.objects.get(pk=section_pk, company=company)
                breakdown_room.breakdown_sections.remove(section)
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
