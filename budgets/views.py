# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/views.py
"""
View definitions for the budgets application.
Implements the sequential budget wizard, HTMX partial endpoints,
result display, status update and ADMIN-only history and detail views.
---
Definiciones de vistas para la aplicacion budgets.
Implementa el asistente de presupuesto secuencial, endpoints parciales HTMX,
visualizacion de resultado, actualizacion de estado y vistas de historial
y detalle exclusivas para ADMIN.
"""

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views import View

from budgets.models import (
    Budget,
    Insurer,
    TariffLine,
    VehicleType,
)
from budgets.services import calculate_budget
from ivr_config.models import CompanyUser, PresenceStatus
from panel.mixins import AdminRoleRequiredMixin, AssistanceRequiredMixin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_company_user(request):
    """
    Return the CompanyUser linked to the authenticated request user.
    ---
    Devuelve el CompanyUser vinculado al usuario autenticado en la peticion.
    """
    return getattr(request.user, "company_user", None)


def _tariff_has_concept(insurer_id, vehicle_type_id, concept_code):
    """
    Return True if the active tariff for the given insurer contains a
    TariffLine for the given concept and vehicle type (or as a generic line).
    ---
    Devuelve True si la tarifa activa de la aseguradora contiene una TariffLine
    para el concepto y tipo de vehiculo dados (o como linea generica).
    """
    from budgets.models import InsurerTariff
    try:
        tariff = InsurerTariff.objects.get(
            insurer_id=insurer_id,
            valid_to__isnull=True,
        )
    except InsurerTariff.DoesNotExist:
        return False
    return tariff.lines.filter(
        concept=concept_code,
    ).filter(
        models_q_vehicle(vehicle_type_id)
    ).exists()


def models_q_vehicle(vehicle_type_id):
    """
    Return a Q object matching tariff lines that are either generic
    (vehicle_type=None) or specific to the given vehicle_type_id.
    ---
    Devuelve un objeto Q que coincide con lineas de tarifa que son genericas
    (vehicle_type=None) o especificas para el vehicle_type_id dado.
    """
    from django.db.models import Q
    return Q(vehicle_type__isnull=True) | Q(vehicle_type_id=vehicle_type_id)


def _get_optional_concepts(insurer_id, vehicle_type_id):
    """
    Return a list of concept codes that are available as optional inputs
    for the given insurer and vehicle type combination.
    Only includes concepts that the operator must actively fill in
    (rescue, wait, worker, assistant, custody). Surcharges and departures
    are handled separately and are never shown as optional inputs.
    ---
    Devuelve una lista de codigos de concepto disponibles como entradas
    opcionales para la combinacion de aseguradora y tipo de vehiculo dada.
    Solo incluye conceptos que el operario debe rellenar activamente
    (rescate, espera, mano de obra, ayudante, custodia). Los recargos y
    las salidas se gestionan por separado y nunca se muestran como opcionales.
    """
    from budgets.models import InsurerTariff
    optional_codes = [
        TariffLine.CONCEPT_RESCUE_HOUR,
        TariffLine.CONCEPT_WAIT_HOUR,
        TariffLine.CONCEPT_WORKER_HOUR,
        TariffLine.CONCEPT_ASSISTANT_HOUR,
        TariffLine.CONCEPT_CUSTODY_DAY,
    ]
    try:
        tariff = InsurerTariff.objects.get(
            insurer_id=insurer_id,
            valid_to__isnull=True,
        )
    except InsurerTariff.DoesNotExist:
        return []
    available = []
    for code in optional_codes:
        exists = tariff.lines.filter(
            concept=code,
        ).filter(
            models_q_vehicle(vehicle_type_id)
        ).exists()
        if exists:
            available.append(code)
    return available


def _has_loaded_surcharge(insurer_id):
    """
    Return True if the active tariff for the insurer includes a
    LOADED_PERCENT surcharge line.
    ---
    Devuelve True si la tarifa activa de la aseguradora incluye una linea
    de recargo LOADED_PERCENT.
    """
    from budgets.models import InsurerTariff
    try:
        tariff = InsurerTariff.objects.get(
            insurer_id=insurer_id,
            valid_to__isnull=True,
        )
    except InsurerTariff.DoesNotExist:
        return False
    return tariff.lines.filter(
        concept=TariffLine.CONCEPT_LOADED_PERCENT
    ).exists()


# ---------------------------------------------------------------------------
# Base context helpers — inject company, company_user, own_presence
# Helpers de contexto base — inyectan company, company_user, own_presence
# ---------------------------------------------------------------------------

def _get_own_presence(company_user):
    """
    Return the current active PresenceStatus for the given CompanyUser.
    ---
    Devuelve el PresenceStatus activo actual para el CompanyUser dado.
    """
    return (
        PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__lte=now(),
        )
        .filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now())
        )
        .order_by("-starts_at")
        .first()
    )


def _build_base_context(request, extra=None):
    """
    Build the base template context required by panel/base.html.
    Injects company, company_user and own_presence so the sidebar
    renders correctly for all roles.
    ---
    Construye el contexto base requerido por panel/base.html.
    Inyecta company, company_user y own_presence para que el sidebar
    se renderice correctamente para todos los roles.
    """
    cu = request.user.company_user
    ctx = {
        "company": cu.company,
        "company_user": cu,
        "own_presence": _get_own_presence(cu),
    }
    if extra:
        ctx.update(extra)
    return ctx


# ---------------------------------------------------------------------------
# Optional concept metadata for form rendering
# ---------------------------------------------------------------------------

OPTIONAL_CONCEPT_META = {
    TariffLine.CONCEPT_RESCUE_HOUR: {
        "label": "Horas de rescate",
        "field": "rescue_hours",
        "input_type": "number",
        "step": "0.5",
    },
    TariffLine.CONCEPT_WAIT_HOUR: {
        "label": "Horas de espera",
        "field": "wait_hours",
        "input_type": "number",
        "step": "0.5",
    },
    TariffLine.CONCEPT_WORKER_HOUR: {
        "label": "Horas de mano de obra",
        "field": "worker_hours",
        "input_type": "number",
        "step": "0.5",
    },
    TariffLine.CONCEPT_ASSISTANT_HOUR: {
        "label": "Horas de ayudante",
        "field": "assistant_hours",
        "input_type": "number",
        "step": "0.5",
    },
    TariffLine.CONCEPT_CUSTODY_DAY: {
        "label": "Dias de custodia",
        "field": "custody_days",
        "input_type": "number",
        "step": "1",
    },
}


# ---------------------------------------------------------------------------
# Budget wizard — sequential form (ASSISTANCE + ADMIN)
# ---------------------------------------------------------------------------

class BudgetWizardView(AssistanceRequiredMixin, View):
    """
    Sequential budget wizard. Renders the step-by-step form for the operator.
    On GET: renders the wizard with the list of active insurers.
    On POST: validates all inputs, calculates the budget via the engine,
    persists Budget + BudgetLine records in a single transaction and
    redirects to the result view.
    ---
    Asistente de presupuesto secuencial. Renderiza el formulario paso a paso
    para el operario. En GET: renderiza el asistente con la lista de
    aseguradoras activas. En POST: valida todas las entradas, calcula el
    presupuesto via el motor, persiste Budget + BudgetLine en una sola
    transaccion y redirige a la vista de resultado.
    """

    template_name = "budgets/wizard.html"

    def get(self, request):
        """
        Render the wizard with active insurers for the operator's company.
        ---
        Renderiza el asistente con las aseguradoras activas de la empresa
        del operario.
        """
        company_user = _get_company_user(request)
        insurers = Insurer.objects.filter(
            company=company_user.company,
            is_active=True,
        ).order_by("name")
        ctx = _build_base_context(request, {
            "insurers": insurers,
            "active_nav": "budgets_wizard",
        })
        return render(request, self.template_name, ctx)

    def post(self, request):
        """
        Process the wizard form submission, run the calculation engine and
        persist the budget. Redirects to BudgetResultView on success.
        ---
        Procesa el envio del formulario del asistente, ejecuta el motor de
        calculo y persiste el presupuesto. Redirige a BudgetResultView
        en caso de exito.
        """
        company_user = _get_company_user(request)
        data = request.POST

        # --- Validate required fields ---
        # --- Validar campos obligatorios ---
        try:
            insurer_id = int(data["insurer_id"])
            vehicle_type_id = int(data["vehicle_type_id"])
            km_phase1 = float(data["km_phase1"])
            service_date = data["service_date"]
            is_overnight = data.get("is_overnight") == "1"
            has_unlock = data.get("has_unlock") == "1"
            is_night_or_holiday = data.get("is_night_or_holiday") == "1"
            is_loaded = data.get("is_loaded") == "1"
        except (KeyError, ValueError):
            messages.error(
                request,
                "Faltan datos obligatorios. Revisa el formulario.",
            )
            return redirect("budgets:wizard")

        km_phase2 = None
        if is_overnight:
            try:
                km_phase2 = float(data["km_phase2"])
            except (KeyError, ValueError):
                messages.error(
                    request,
                    "Introduce los kilometros de la fase 2 para servicios de pernocta.",
                )
                return redirect("budgets:wizard")

        # --- Resolve FK objects ---
        # --- Resolver objetos FK ---
        insurer = get_object_or_404(
            Insurer,
            pk=insurer_id,
            company=company_user.company,
            is_active=True,
        )
        vehicle_type = get_object_or_404(
            VehicleType,
            pk=vehicle_type_id,
            insurer=insurer,
            is_active=True,
        )

        # --- Build Budget instance (unsaved) ---
        # --- Construir instancia Budget (sin guardar) ---
        budget = Budget(
            company=company_user.company,
            insurer=insurer,
            operator=company_user,
            service_date=service_date,
            vehicle_type=vehicle_type,
            is_overnight=is_overnight,
            km_phase1=km_phase1,
            km_phase2=km_phase2,
            has_unlock=has_unlock,
            is_night_or_holiday=is_night_or_holiday,
            is_loaded=is_loaded,
            wait_hours=_parse_optional(data.get("wait_hours")),
            rescue_hours=_parse_optional(data.get("rescue_hours")),
            assistant_hours=_parse_optional(data.get("assistant_hours")),
            worker_hours=_parse_optional(data.get("worker_hours")),
            custody_days=_parse_optional(data.get("custody_days")),
            extra_notes=data.get("extra_notes", "").strip(),
            # Placeholders — set by the engine before save.
            # Valores provisionales — el motor los establece antes de guardar.
            total_amount=0,
            tariff_id=None,
        )

        # --- Run calculation engine and persist atomically ---
        # --- Ejecutar motor de calculo y persistir atomicamente ---
        try:
            with transaction.atomic():
                budget_lines = calculate_budget(budget)
                budget.save()
                for line in budget_lines:
                    line.budget = budget
                BudgetLine = budget.lines.model
                BudgetLine.objects.bulk_create(budget_lines)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("budgets:wizard")

        return redirect("budgets:result", pk=budget.pk)


def _parse_optional(raw):
    """
    Parse an optional numeric form field. Returns None if empty or invalid.
    ---
    Parsea un campo de formulario numerico opcional.
    Devuelve None si esta vacio o es invalido.
    """
    if not raw:
        return None
    try:
        value = float(raw)
        return value if value > 0 else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTMX partial — vehicle types for selected insurer
# ---------------------------------------------------------------------------

class BudgetVehicleTypesView(AssistanceRequiredMixin, View):
    """
    HTMX partial view. Returns the vehicle type dropdown fragment for the
    insurer selected in step 1 of the wizard.
    ---
    Vista parcial HTMX. Devuelve el fragmento de desplegable de tipos de
    vehiculo para la aseguradora seleccionada en el paso 1 del asistente.
    """

    template_name = "budgets/_vehicle_types_fragment.html"

    def get(self, request):
        """
        Return vehicle types for the given insurer_id query parameter.
        ---
        Devuelve los tipos de vehiculo para el parametro insurer_id.
        """
        company_user = _get_company_user(request)
        insurer_id = request.GET.get("insurer_id")
        if not insurer_id:
            return HttpResponseBadRequest("insurer_id requerido.")
        vehicle_types = VehicleType.objects.filter(
            insurer_id=insurer_id,
            insurer__company=company_user.company,
            is_active=True,
        ).order_by("sort_order", "name")
        return render(request, self.template_name, {
            "vehicle_types": vehicle_types,
        })


# ---------------------------------------------------------------------------
# HTMX partial — optional concepts for selected insurer + vehicle type
# ---------------------------------------------------------------------------

class BudgetOptionalConceptsView(AssistanceRequiredMixin, View):
    """
    HTMX partial view. Returns the optional concepts form fragment for
    the selected insurer + vehicle type combination.
    ---
    Vista parcial HTMX. Devuelve el fragmento de formulario de conceptos
    opcionales para la combinacion de aseguradora y tipo de vehiculo seleccionados.
    """

    template_name = "budgets/_optional_concepts_fragment.html"

    def get(self, request):
        """
        Return optional concept inputs for the given insurer_id and
        vehicle_type_id query parameters.
        ---
        Devuelve los campos opcionales para los parametros insurer_id
        y vehicle_type_id dados.
        """
        insurer_id = request.GET.get("insurer_id")
        vehicle_type_id = request.GET.get("vehicle_type_id")
        if not insurer_id or not vehicle_type_id:
            return HttpResponseBadRequest(
                "insurer_id y vehicle_type_id requeridos."
            )
        available_codes = _get_optional_concepts(
            int(insurer_id),
            int(vehicle_type_id),
        )
        has_loaded = _has_loaded_surcharge(int(insurer_id))
        concepts = [
            OPTIONAL_CONCEPT_META[code]
            for code in available_codes
            if code in OPTIONAL_CONCEPT_META
        ]
        return render(request, self.template_name, {
            "concepts": concepts,
            "has_loaded_surcharge": has_loaded,
        })


# ---------------------------------------------------------------------------
# Budget result — operator view (total only)
# ---------------------------------------------------------------------------

class BudgetResultView(AssistanceRequiredMixin, View):
    """
    Displays the budget result to the operator. Only the total amount is
    shown — no tariff lines, no unit prices, no breakdown.
    Provides ACCEPTED / REJECTED action buttons.
    ---
    Muestra el resultado del presupuesto al operario. Solo se muestra el
    importe total — sin lineas de tarifa, sin precios unitarios, sin desglose.
    Proporciona los botones de accion ACEPTADO / RECHAZADO.
    """

    template_name = "budgets/result.html"

    def get(self, request, pk):
        """
        Render the result page for the given budget pk.
        ---
        Renderiza la pagina de resultado para el pk de presupuesto dado.
        """
        company_user = _get_company_user(request)
        budget = get_object_or_404(
            Budget,
            pk=pk,
            company=company_user.company,
        )
        ctx = _build_base_context(request, {
            "budget": budget,
            "active_nav": "budgets_wizard",
        })
        return render(request, self.template_name, ctx)


# ---------------------------------------------------------------------------
# Budget status update — ACCEPTED / REJECTED
# ---------------------------------------------------------------------------

class BudgetStatusUpdateView(AssistanceRequiredMixin, View):
    """
    Updates the status of a budget to ACCEPTED or REJECTED.
    Called from the result view action buttons.
    ---
    Actualiza el estado de un presupuesto a ACCEPTED o REJECTED.
    Se llama desde los botones de accion de la vista de resultado.
    """

    def post(self, request, pk):
        """
        Set budget.status to the value provided in the POST body.
        Redirects back to the result view.
        ---
        Establece budget.status al valor proporcionado en el cuerpo POST.
        Redirige de vuelta a la vista de resultado.
        """
        company_user = _get_company_user(request)
        budget = get_object_or_404(
            Budget,
            pk=pk,
            company=company_user.company,
        )
        new_status = request.POST.get("status")
        if new_status not in (
            Budget.STATUS_ACCEPTED,
            Budget.STATUS_REJECTED,
        ):
            messages.error(request, "Estado no valido.")
            return redirect("budgets:result", pk=pk)
        budget.status = new_status
        budget.save(update_fields=["status"])
        return redirect("budgets:result", pk=pk)


# ---------------------------------------------------------------------------
# Budget history — ADMIN only
# ---------------------------------------------------------------------------

class BudgetHistoryView(AdminRoleRequiredMixin, View):
    """
    Lists all budgets for the company with filters by insurer, date and status.
    Visible to ADMIN only.
    ---
    Lista todos los presupuestos de la empresa con filtros por aseguradora,
    fecha y estado. Visible solo para ADMIN.
    """

    template_name = "budgets/history.html"

    def get(self, request):
        """
        Render the budget history list with optional filters.
        ---
        Renderiza la lista de historial de presupuestos con filtros opcionales.
        """
        company_user = _get_company_user(request)
        qs = Budget.objects.filter(
            company=company_user.company,
        ).select_related(
            "insurer",
            "vehicle_type",
            "operator__user",
            "tariff",
        ).order_by("-created_at")

        # Optional filters from GET params.
        # Filtros opcionales desde parametros GET.
        insurer_id = request.GET.get("insurer")
        status = request.GET.get("status")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        if insurer_id:
            qs = qs.filter(insurer_id=insurer_id)
        if status:
            qs = qs.filter(status=status)
        if date_from:
            qs = qs.filter(service_date__gte=date_from)
        if date_to:
            qs = qs.filter(service_date__lte=date_to)

        insurers = Insurer.objects.filter(
            company=company_user.company,
        ).order_by("name")

        ctx = _build_base_context(request, {
            "budgets": qs,
            "insurers": insurers,
            "status_choices": Budget.STATUS_CHOICES,
            "active_nav": "budgets_history",
            "filters": {
                "insurer": insurer_id,
                "status": status,
                "date_from": date_from,
                "date_to": date_to,
            },
        })
        return render(request, self.template_name, ctx)


# ---------------------------------------------------------------------------
# Budget detail — ADMIN audit view (full breakdown)
# ---------------------------------------------------------------------------

class BudgetDetailView(AdminRoleRequiredMixin, View):
    """
    Displays the full calculation breakdown of a budget for ADMIN audit.
    Shows all BudgetLine records with concept, units, unit price and subtotal.
    ---
    Muestra el desglose completo del calculo de un presupuesto para auditoria
    ADMIN. Muestra todos los registros BudgetLine con concepto, unidades,
    precio unitario y subtotal.
    """

    template_name = "budgets/detail.html"

    def get(self, request, pk):
        """
        Render the full breakdown for the given budget pk.
        ---
        Renderiza el desglose completo para el pk de presupuesto dado.
        """
        company_user = _get_company_user(request)
        budget = get_object_or_404(
            Budget,
            pk=pk,
            company=company_user.company,
        )
        lines = budget.lines.order_by("sort_order")
        ctx = _build_base_context(request, {
            "budget": budget,
            "lines": lines,
            "active_nav": "budgets_history",
        })
        return render(request, self.template_name, ctx)
