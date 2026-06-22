# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/views_tickets.py
"""
Ticket management views for the chat module (Hito 14).
Extracted from chat/views.py to keep the module focused and maintainable.

H17 — Paso 1: room__company lookups replaced by company. BreakdownConversationTurn
import removed. ChatRoom dependency eliminated.

BreakdownTicketListView   — list of all BreakdownTickets for the company.
BreakdownTicketDetailView — detail + actions (assign, self_assign, set_urgency, pause, close).
BreakdownTicketCreateView — manual creation of BreakdownTicket from the panel.

Access control: CompanyUserRequiredMixin on all views.
ADMIN / SUPERVISOR / WORKSHOPBOSS: access to ticket management.
---
Vistas de gestión de tickets del módulo de chat (Hito 14).
Extraídas de chat/views.py para mantener el módulo enfocado y mantenible.

H17 — Paso 1: lookups room__company sustituidos por company. Import de
BreakdownConversationTurn eliminado. Dependencia de ChatRoom eliminada.

BreakdownTicketListView   — lista de todos los BreakdownTickets de la empresa.
BreakdownTicketDetailView — detalle + acciones (asignar, autoasignar, urgencia, pausar, cerrar).
BreakdownTicketCreateView — creación manual de BreakdownTicket desde el panel.

Control de acceso: CompanyUserRequiredMixin en todas las vistas.
ADMIN / SUPERVISOR / WORKSHOPBOSS: acceso a gestión de tickets.
"""

import logging

from django.shortcuts import render, get_object_or_404
from django.views import View
from django.utils.timezone import now

from panel.mixins import CompanyUserRequiredMixin

logger = logging.getLogger(__name__)


class BreakdownTicketListView(CompanyUserRequiredMixin, View):
    """
    Lists all BreakdownTickets for the authenticated user's company,
    ordered by created_at descending. Supports optional filter: status.
    Accessible to ADMIN, SUPERVISOR and WORKSHOPBOSS roles only.

    URL: GET /panel/chat/breakdowns/tickets/
    ---
    Lista todos los BreakdownTickets de la empresa del usuario autenticado,
    ordenados por created_at descendente. Soporta filtro opcional: status.
    Accesible solo para los roles ADMIN, SUPERVISOR y WORKSHOPBOSS.

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
        from ivr_config.models import CompanyUser as CU

        company_user = request.user.company_user
        company      = company_user.company

        if company_user.role not in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
        ):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        qs = (
            BreakdownTicket.objects
            .filter(company=company)
            .select_related("contact", "machine", "section", "resolved_by__user",
                            "assigned_to__user")
            .order_by("-created_at")
        )

        status_filter = request.GET.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        # Operators panel: all WORKSHOPBOSS/WORKSHOP of the company with their active ticket.
        # Panel de operarios: todos los WORKSHOPBOSS/WORKSHOP de la empresa con su ticket activo.
        operators_qs = (
            CU.objects
            .filter(
                company=company,
                role__in=[CU.ROLE_WORKSHOP, CU.ROLE_WORKSHOPBOSS],
                is_active=True,
            )
            .select_related("user")
            .order_by("user__last_name", "user__first_name")
        )
        active_tickets = {
            bt.assigned_to_id: bt
            for bt in BreakdownTicket.objects.filter(
                company=company,
                status=BreakdownTicket.STATUS_IN_PROGRESS,
                assigned_to__isnull=False,
            ).select_related("machine")
        }
        for op in operators_qs:
            op.active_ticket = active_tickets.get(op.pk)

        # Assignable tickets panel: OPEN and PAUSED tickets available for assignment.
        # Panel de tickets asignables: tickets OPEN y PAUSED disponibles para asignar.
        assignable_tickets = (
            BreakdownTicket.objects
            .filter(
                company=company,
                status__in=[
                    BreakdownTicket.STATUS_OPEN,
                    BreakdownTicket.STATUS_PAUSED,
                    BreakdownTicket.STATUS_IN_PROGRESS,
                ],
            )
            .select_related("machine", "assigned_to__user")
            .order_by("-urgency", "created_at")
        )

        return render(request, self.template_name, {
            "tickets":            qs,
            "company":            company,
            "company_user":       company_user,
            "own_presence":       own_presence,
            "active_nav":         "breakdown_ticket_list",
            "status_filter":      status_filter,
            "STATUS_CHOICES":     BreakdownTicket.STATUS_CHOICES,
            "operators":          operators_qs,
            "assignable_tickets": assignable_tickets,
        })


class BreakdownTicketDetailView(CompanyUserRequiredMixin, View):
    """
    Displays a single BreakdownTicket with its photos.
    Provides POST actions:
      action=assign         — assigns/unassigns a WORKSHOPBOSS; sets IN_PROGRESS.
      action=self_assign    — operator self-assigns; sets IN_PROGRESS.
      action=set_urgency    — updates urgency level.
      action=pause          — sets status=PAUSED, clears assigned_to, sets paused_at.
      action=close          — sets status=CLOSED, resolved_by, resolved_at.
    Accessible to ADMIN, SUPERVISOR and WORKSHOPBOSS roles only.

    URL: GET/POST /panel/chat/breakdowns/tickets/<pk>/
    ---
    Muestra un BreakdownTicket individual con sus fotos.
    Proporciona acciones POST:
      action=assign         — asigna/desasigna un WORKSHOPBOSS; pone IN_PROGRESS.
      action=self_assign    — el operario se autoasigna; pone IN_PROGRESS.
      action=set_urgency    — actualiza el nivel de urgencia.
      action=pause          — pone PAUSED, limpia assigned_to, registra paused_at.
      action=close          — pone CLOSED, resolved_by, resolved_at.
    Accesible solo para los roles ADMIN, SUPERVISOR y WORKSHOPBOSS.

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
            company=request.user.company_user.company,
        )

    def get(self, request, pk, *args, **kwargs):
        """
        Renders the ticket detail page.
        ---
        Renderiza la página de detalle del ticket.
        """
        from django.db.models import Q
        from ivr_config.models import PresenceStatus, CompanyUser as CU

        company_user = request.user.company_user

        if company_user.role not in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
        ):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        ticket = self._get_ticket(request, pk)

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        workshopboss_users = (
            CU.objects
            .filter(
                company=company_user.company,
                role=CU.ROLE_WORKSHOPBOSS,
                is_active=True,
            )
            .select_related("user")
            .order_by("user__username")
        )

        return render(request, self.template_name, {
            "ticket":             ticket,
            "company_user":       company_user,
            "own_presence":       own_presence,
            "active_nav":         "breakdown_ticket_list",
            "workshopboss_users": workshopboss_users,
            "URGENCY_CHOICES":    ticket.URGENCY_CHOICES,
        })

    def post(self, request, pk, *args, **kwargs):
        """
        Handles assign, self_assign, set_urgency, pause and close actions.
        ---
        Gestiona las acciones assign, self_assign, set_urgency, pause y close.
        """
        from django.http import HttpResponseForbidden
        from django.shortcuts import redirect
        from chat.models import BreakdownTicket

        company_user = request.user.company_user
        company      = company_user.company

        if company_user.role not in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
        ):
            return HttpResponseForbidden()

        ticket = self._get_ticket(request, pk)
        action = request.POST.get("action", "").strip()

        if action == "assign":
            if company_user.role not in (
                company_user.ROLE_ADMIN,
                company_user.ROLE_SUPERVISOR,
            ):
                return HttpResponseForbidden()
            from ivr_config.models import CompanyUser as CU
            assignee_pk = request.POST.get("assignee_pk", "").strip()
            if assignee_pk:
                try:
                    assignee = CU.objects.get(
                        pk=assignee_pk,
                        company=company,
                        role__in=[CU.ROLE_WORKSHOP, CU.ROLE_WORKSHOPBOSS],
                        is_active=True,
                    )
                    # If assignee already has an IN_PROGRESS ticket, pause it.
                    # Si el asignado ya tiene un ticket IN_PROGRESS, pausarlo.
                    CU_active = BreakdownTicket.objects.filter(
                        company=company,
                        assigned_to=assignee,
                        status=BreakdownTicket.STATUS_IN_PROGRESS,
                    ).exclude(pk=ticket.pk)
                    for prev in CU_active:
                        prev.status      = BreakdownTicket.STATUS_PAUSED
                        prev.assigned_to = None
                        prev.paused_at   = now()
                        prev.save(update_fields=["status", "assigned_to", "paused_at"])
                        logger.info(
                            "# [BREAKDOWN] Ticket pk=%s pausado por reasignacion de CU pk=%s.",
                            prev.pk, assignee.pk,
                        )
                    ticket.assigned_to = assignee
                    ticket.status      = BreakdownTicket.STATUS_IN_PROGRESS
                    ticket.paused_at   = None
                    ticket.save(update_fields=["assigned_to", "status", "paused_at"])
                    logger.info(
                        "# [BREAKDOWN] Ticket pk=%s asignado a CU pk=%s (IN_PROGRESS) por usuario pk=%s.",
                        ticket.pk, assignee.pk, company_user.pk,
                    )
                except CU.DoesNotExist:
                    logger.warning(
                        "# [BREAKDOWN] assign fallido: assignee_pk=%s no valido empresa pk=%s.",
                        assignee_pk, company.pk,
                    )
            else:
                ticket.assigned_to = None
                ticket.status      = BreakdownTicket.STATUS_OPEN
                ticket.save(update_fields=["assigned_to", "status"])
                logger.info(
                    "# [BREAKDOWN] Ticket pk=%s desasignado (OPEN) por usuario pk=%s.",
                    ticket.pk, company_user.pk,
                )

        elif action == "self_assign":
            # Operator self-assigns. Sets IN_PROGRESS. Pauses previous active ticket.
            # El operario se autoasigna. Pone IN_PROGRESS. Pausa su ticket activo previo.
            prev_active = BreakdownTicket.objects.filter(
                company=company,
                assigned_to=company_user,
                status=BreakdownTicket.STATUS_IN_PROGRESS,
            ).exclude(pk=ticket.pk)
            for prev in prev_active:
                prev.status      = BreakdownTicket.STATUS_PAUSED
                prev.assigned_to = None
                prev.paused_at   = now()
                prev.save(update_fields=["status", "assigned_to", "paused_at"])
                logger.info(
                    "# [BREAKDOWN] Ticket pk=%s pausado por autoasignacion de CU pk=%s.",
                    prev.pk, company_user.pk,
                )
            ticket.assigned_to = company_user
            ticket.status      = BreakdownTicket.STATUS_IN_PROGRESS
            ticket.paused_at   = None
            ticket.save(update_fields=["assigned_to", "status", "paused_at"])
            logger.info(
                "# [BREAKDOWN] Ticket pk=%s autoasignado por CU pk=%s (IN_PROGRESS).",
                ticket.pk, company_user.pk,
            )

        elif action == "pause":
            ticket.status      = BreakdownTicket.STATUS_PAUSED
            ticket.assigned_to = None
            ticket.paused_at   = now()
            ticket.save(update_fields=["status", "assigned_to", "paused_at"])
            logger.info(
                "# [BREAKDOWN] Ticket pk=%s pausado por usuario pk=%s.",
                ticket.pk, company_user.pk,
            )

        elif action == "set_urgency":
            urgency_value   = request.POST.get("urgency", "").strip()
            valid_urgencies = {u[0] for u in BreakdownTicket.URGENCY_CHOICES}
            if urgency_value in valid_urgencies:
                ticket.urgency = urgency_value
                ticket.save(update_fields=["urgency"])
                logger.info(
                    "# [BREAKDOWN] Ticket pk=%s urgencia=%s por usuario pk=%s.",
                    ticket.pk, urgency_value, company_user.pk,
                )
            else:
                logger.warning(
                    "# [BREAKDOWN] set_urgency valor=%s invalido ticket pk=%s.",
                    urgency_value, ticket.pk,
                )

        elif action == "close":
            ticket.status      = BreakdownTicket.STATUS_CLOSED
            ticket.resolved_by = company_user
            ticket.resolved_at = now()
            ticket.save(update_fields=["status", "resolved_by", "resolved_at"])
            logger.info(
                "# [BREAKDOWN] Ticket pk=%s cerrado por usuario pk=%s.",
                ticket.pk, company_user.pk,
            )

        return redirect("panel:breakdown_ticket_detail", pk=ticket.pk)


class BreakdownTicketCreateView(CompanyUserRequiredMixin, View):
    """
    Allows ADMIN, SUPERVISOR and WORKSHOPBOSS to manually create a
    BreakdownTicket from the panel without requiring a WhatsApp interaction.
    The ticket is created with status=OPEN and linked directly to the company.

    GET  — renders the creation form.
    POST — validates and persists the ticket, redirects to its detail.

    URL: GET/POST /panel/chat/breakdowns/tickets/create/
    ---
    Permite a ADMIN, SUPERVISOR y WORKSHOPBOSS crear manualmente un
    BreakdownTicket desde el panel sin requerir interacción WhatsApp.
    El ticket se crea con status=OPEN vinculado directamente a la empresa.

    GET  — renderiza el formulario de creación.
    POST — valida y persiste el ticket, redirige a su detalle.

    URL: GET/POST /panel/chat/breakdowns/tickets/create/
    """

    template_name = "panel/chat/breakdown_ticket_form.html"

    def _get_context(self, request):
        """
        Builds the shared context for GET and validation-failed POST renders.
        ---
        Construye el contexto compartido para renders GET y POST con error.
        """
        from django.db.models import Q
        from ivr_config.models import PresenceStatus, Contact, Section
        from fleet.models import MachineAsset

        company_user = request.user.company_user
        company      = company_user.company

        own_presence = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        ).order_by("-starts_at").first()

        contacts = (
            Contact.objects
            .filter(company=company)
            .exclude(phone_number="")
            .order_by("name")
        )
        machines = (
            MachineAsset.objects
            .filter(company=company, is_active=True)
            .order_by("code")
        )
        sections = (
            Section.objects
            .filter(company=company, is_active=True)
            .order_by("name")
        )

        return {
            "contacts":     contacts,
            "machines":     machines,
            "sections":     sections,
            "company_user": company_user,
            "own_presence": own_presence,
            "active_nav":   "breakdown_ticket_list",
        }

    def get(self, request, *args, **kwargs):
        """
        Renders the BreakdownTicket creation form.
        ---
        Renderiza el formulario de creación de BreakdownTicket.
        """
        company_user = request.user.company_user
        if company_user.role not in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
        ):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()
        ctx = self._get_context(request)
        return render(request, self.template_name, ctx)

    def post(self, request, *args, **kwargs):
        """
        Validates form fields and creates a new BreakdownTicket.
        Required: contact_pk, fault_summary.
        Optional: machine_pk, section_pk, urgency.
        ---
        Valida los campos y crea un nuevo BreakdownTicket.
        Obligatorios: contact_pk, fault_summary.
        Opcionales: machine_pk, section_pk, urgency.
        """
        from django.http import HttpResponseForbidden
        from django.shortcuts import redirect
        from ivr_config.models import Contact, Section
        from fleet.models import MachineAsset
        from chat.models import BreakdownTicket

        company_user = request.user.company_user
        company      = company_user.company

        if company_user.role not in (
            company_user.ROLE_ADMIN,
            company_user.ROLE_SUPERVISOR,
            company_user.ROLE_WORKSHOPBOSS,
        ):
            return HttpResponseForbidden()

        contact_pk    = request.POST.get("contact_pk", "").strip()
        fault_summary = request.POST.get("fault_summary", "").strip()
        errors        = {}
        contact       = None

        if not contact_pk:
            errors["contact_pk"] = "Debes seleccionar un contacto."
        else:
            try:
                contact = Contact.objects.get(pk=contact_pk, company=company)
            except Contact.DoesNotExist:
                errors["contact_pk"] = "Contacto no válido."

        if not fault_summary:
            errors["fault_summary"] = "La descripción de la avería es obligatoria."

        if errors:
            ctx = self._get_context(request)
            ctx["errors"]    = errors
            ctx["post_data"] = request.POST
            return render(request, self.template_name, ctx)

        machine    = None
        machine_pk = request.POST.get("machine_pk", "").strip()
        if machine_pk:
            machine = MachineAsset.objects.filter(
                pk=machine_pk, company=company, is_active=True,
            ).first()

        section    = None
        section_pk = request.POST.get("section_pk", "").strip()
        if section_pk:
            section = Section.objects.filter(
                pk=section_pk, company=company, is_active=True,
            ).first()

        urgency_value   = request.POST.get("urgency", "").strip()
        valid_urgencies = {u[0] for u in BreakdownTicket.URGENCY_CHOICES}
        if urgency_value not in valid_urgencies:
            urgency_value = ""

        ticket = BreakdownTicket.objects.create(
            company       = company,
            contact       = contact,
            machine       = machine,
            machine_raw   = machine.code if machine else "",
            section       = section,
            fault_summary = fault_summary,
            urgency       = urgency_value,
            status        = BreakdownTicket.STATUS_OPEN,
        )
        logger.info(
            "# [BREAKDOWN] Ticket pk=%s creado manualmente por usuario pk=%s.",
            ticket.pk, company_user.pk,
        )
        return redirect("panel:breakdown_ticket_detail", pk=ticket.pk)
