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

from django import forms as django_forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views import View

from budgets.models import (
    Budget,
    BudgetLine,
    Insurer,
    InsurerTariff,
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


# ---------------------------------------------------------------------------
# Insurer management views — ADMIN only
# Vistas de gestion de aseguradoras — solo ADMIN
# ---------------------------------------------------------------------------


class InsurerForm(django_forms.ModelForm):
    """
    ModelForm for the Insurer model. Used by InsurerCreateView and
    InsurerUpdateView. Scopes the queryset to the company of the
    authenticated CompanyUser — unique_together validation is handled
    by the model itself.
    ---
    ModelForm para el modelo Insurer. Usado por InsurerCreateView e
    InsurerUpdateView. No expone el campo company en el formulario —
    se asigna automaticamente en la vista desde el CompanyUser autenticado.
    La validacion unique_together la gestiona el propio modelo.
    """

    class Meta:
        model = Insurer
        fields = [
            "name",
            "code",
            "management_fee_percent",
            "surcharges_are_cumulative",
            "is_active",
            "is_insurance_company",
            "notes",
        ]

    def clean_code(self):
        """
        Normalise the code field to uppercase and strip whitespace.
        ---
        Normaliza el campo code a mayusculas y elimina espacios.
        """
        return self.cleaned_data.get("code", "").strip().upper()


def _insurer_list_qs(company):
    """
    Return the annotated Insurer queryset for the given company,
    including vehicle_type_count and tariff_count annotations.
    ---
    Devuelve el queryset de Insurer anotado para la empresa dada,
    incluyendo las anotaciones vehicle_type_count y tariff_count.
    """
    return (
        Insurer.objects.filter(company=company)
        .annotate(
            vehicle_type_count=Count("vehicle_types", distinct=True),
            tariff_count=Count("tariffs", distinct=True),
        )
        .order_by("name")
    )


class InsurerListView(AdminRoleRequiredMixin, View):
    """
    Lists all insurers for the company. Supports live HTMX search by
    name/code and filter by active/inactive status.
    On HTMX request: returns only the table fragment partial.
    On full request: returns the full page.
    ---
    Lista todas las aseguradoras de la empresa. Soporta busqueda live
    HTMX por nombre/codigo y filtro por estado activa/inactiva.
    En peticion HTMX: devuelve solo el parcial de tabla.
    En peticion completa: devuelve la pagina completa.
    """

    template_name = "budgets/insurer_list.html"
    partial_template = "budgets/_insurer_table_fragment.html"

    def get(self, request):
        """
        Render the insurer list with optional search and status filters.
        ---
        Renderiza el listado de aseguradoras con filtros opcionales de
        busqueda y estado.
        """
        company_user = _get_company_user(request)
        qs = _insurer_list_qs(company_user.company)

        # Apply search filter.
        # Aplicar filtro de busqueda.
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(code__icontains=q)
            )

        # Apply status filter.
        # Aplicar filtro de estado.
        status = request.GET.get("status", "")
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)

        ctx = _build_base_context(request, {
            "insurers": qs,
            "active_nav": "budgets_insurers",
        })

        # HTMX partial swap — return only the table fragment.
        # Swap parcial HTMX — devolver solo el fragmento de tabla.
        if request.headers.get("HX-Request"):
            return render(request, self.partial_template, ctx)

        return render(request, self.template_name, ctx)


class InsurerCreateView(AdminRoleRequiredMixin, View):
    """
    Renders and processes the insurer creation form.
    On GET: renders an empty InsurerForm.
    On POST: validates, assigns company from the authenticated user
    and saves. Redirects to insurer list on success.
    ---
    Renderiza y procesa el formulario de creacion de aseguradora.
    En GET: renderiza un InsurerForm vacio.
    En POST: valida, asigna la company del usuario autenticado
    y guarda. Redirige al listado en caso de exito.
    """

    template_name = "budgets/insurer_form.html"

    def get(self, request):
        """
        Render the empty creation form.
        ---
        Renderiza el formulario de creacion vacio.
        """
        form = InsurerForm()
        ctx = _build_base_context(request, {
            "form": form,
            "mode": "create",
            "active_nav": "budgets_insurers",
        })
        return render(request, self.template_name, ctx)

    def post(self, request):
        """
        Validate and save the new insurer bound to the company.
        ---
        Valida y guarda la nueva aseguradora vinculada a la empresa.
        """
        company_user = _get_company_user(request)
        form = InsurerForm(request.POST)
        if form.is_valid():
            insurer = form.save(commit=False)
            insurer.company = company_user.company
            try:
                insurer.save()
                messages.success(
                    request,
                    f"Aseguradora '{insurer.name}' creada correctamente.",
                )
                return redirect("budgets:insurer_list")
            except Exception:
                messages.error(
                    request,
                    "El codigo introducido ya existe para esta empresa. "
                    "Usa un codigo diferente.",
                )
        ctx = _build_base_context(request, {
            "form": form,
            "mode": "create",
            "active_nav": "budgets_insurers",
        })
        return render(request, self.template_name, ctx)


class InsurerUpdateView(AdminRoleRequiredMixin, View):
    """
    Renders and processes the insurer edit form for an existing insurer.
    On GET: renders InsurerForm pre-filled with the insurer data.
    On POST: validates and saves. Redirects to insurer list on success.
    ---
    Renderiza y procesa el formulario de edicion de una aseguradora existente.
    En GET: renderiza el InsurerForm con los datos de la aseguradora.
    En POST: valida y guarda. Redirige al listado en caso de exito.
    """

    template_name = "budgets/insurer_form.html"

    def _build_edit_context(self, request, insurer, form):
        """
        Build the full accordion context for the edit view:
        active tariff, tariff history with line counts, tariff line groups
        and choice lists for the inline editing selects.
        ---
        Construye el contexto completo del acordeon para la vista de edicion:
        tarifa activa, historial de tarifas con conteo de lineas, grupos de
        lineas de tarifa y listas de choices para los selects de edicion inline.
        """
        from budgets.models import InsurerTariff
        from django.db.models import Count as _Count

        # Resolve active tariff (valid_to=None).
        # Resolver tarifa activa (valid_to=None).
        active_tariff = (
            InsurerTariff.objects
            .filter(insurer=insurer, valid_to__isnull=True)
            .first()
        )

        # Tariff version history (all non-active versions).
        # Historial de versiones de tarifa (todas las versiones no activas).
        tariff_history = (
            InsurerTariff.objects
            .filter(insurer=insurer, valid_to__isnull=False)
            .annotate(line_count=_Count('lines'))
            .order_by('-valid_from')
        )

        # Tariff lines grouped by vehicle type for accordion Panel 3.
        # Lineas de tarifa agrupadas por tipo de vehiculo para Panel 3.
        tariff_line_groups = []
        vehicle_types = []
        if active_tariff:
            lines = (
                active_tariff.lines
                .select_related('vehicle_type')
                .order_by('vehicle_type__sort_order', 'vehicle_type__name', 'concept')
            )
            vehicle_types = (
                insurer.vehicle_types
                .filter(is_active=True)
                .order_by('sort_order', 'name')
            )
            # Group lines by vehicle_type (None = general concepts).
            # Agrupar lineas por vehicle_type (None = conceptos generales).
            groups_dict = {}
            for line in lines:
                key = line.vehicle_type
                if key not in groups_dict:
                    groups_dict[key] = []
                groups_dict[key].append(line)
            # None (general) first, then sorted by vehicle type name.
            # None (general) primero, luego ordenado por nombre de tipo.
            if None in groups_dict:
                tariff_line_groups.append({
                    'vehicle_type': None,
                    'lines': groups_dict.pop(None),
                })
            for vt, vt_lines in groups_dict.items():
                tariff_line_groups.append({
                    'vehicle_type': vt,
                    'lines': vt_lines,
                })

        return _build_base_context(request, {
            'form': form,
            'insurer': insurer,
            'mode': 'edit',
            'active_nav': 'budgets_insurers',
            'active_tariff': active_tariff,
            'tariff_history': tariff_history,
            'tariff_line_groups': tariff_line_groups,
            'vehicle_types': vehicle_types,
            'concept_choices': TariffLine.CONCEPT_CHOICES,
            'unit_choices': TariffLine.UNIT_CHOICES,
        })

    def get(self, request, pk):
        """
        Render the edit form pre-filled with the insurer instance data.
        ---
        Renderiza el formulario de edicion con los datos de la instancia.
        """
        company_user = _get_company_user(request)
        insurer = get_object_or_404(
            Insurer,
            pk=pk,
            company=company_user.company,
        )
        form = InsurerForm(instance=insurer)
        ctx = self._build_edit_context(request, insurer, form)
        return render(request, self.template_name, ctx)

    def post(self, request, pk):
        """
        Validate and save the updated insurer data.
        On success redirects back to the edit view (not to the list)
        so the user can continue editing tariff and lines.
        ---
        Valida y guarda los datos actualizados de la aseguradora.
        En caso de exito redirige de vuelta a la vista de edicion (no al listado)
        para que el usuario pueda continuar editando tarifa y lineas.
        """
        company_user = _get_company_user(request)
        insurer = get_object_or_404(
            Insurer,
            pk=pk,
            company=company_user.company,
        )
        form = InsurerForm(request.POST, instance=insurer)
        if form.is_valid():
            try:
                form.save()
                messages.success(
                    request,
                    f"Aseguradora '{insurer.name}' actualizada correctamente.",
                )
                return redirect('budgets:insurer_update', pk=insurer.pk)
            except Exception:
                messages.error(
                    request,
                    "El codigo introducido ya existe para esta empresa. "
                    "Usa un codigo diferente.",
                )
        ctx = self._build_edit_context(request, insurer, form)
        return render(request, self.template_name, ctx)


class InsurerToggleView(AdminRoleRequiredMixin, View):
    """
    HTMX endpoint. Toggles the is_active flag of an insurer and returns
    the updated badge fragment for inline swap in the list table.
    ---
    Endpoint HTMX. Alterna el flag is_active de una aseguradora y devuelve
    el fragmento de badge actualizado para swap inline en la tabla del listado.
    """

    def post(self, request, pk):
        """
        Toggle is_active and return the badge partial.
        ---
        Alterna is_active y devuelve el parcial del badge.
        """
        company_user = _get_company_user(request)
        insurer = get_object_or_404(
            Insurer,
            pk=pk,
            company=company_user.company,
        )
        insurer.is_active = not insurer.is_active
        insurer.save(update_fields=["is_active", "updated_at"])
        return render(
            request,
            "budgets/_insurer_badge_fragment.html",
            {"insurer": insurer},
        )


class InsurerDeleteView(AdminRoleRequiredMixin, View):
    """
    Deletes an insurer and all its related data (vehicle types, tariffs,
    tariff lines) via CASCADE. Redirects to insurer list with a success
    or error message.
    ---
    Elimina una aseguradora y todos sus datos relacionados (tipos de vehiculo,
    tarifas, lineas de tarifa) via CASCADE. Redirige al listado con un mensaje
    de exito o error.
    """

    def post(self, request, pk):
        """
        Delete the insurer instance. Redirect to insurer list.
        ---
        Elimina la instancia de aseguradora. Redirige al listado.
        """
        company_user = _get_company_user(request)
        insurer = get_object_or_404(
            Insurer,
            pk=pk,
            company=company_user.company,
        )
        name = insurer.name
        try:
            insurer.delete()
            messages.success(
                request,
                f"Aseguradora '{name}' eliminada correctamente.",
            )
        except Exception as exc:
            messages.error(
                request,
                f"No se pudo eliminar la aseguradora '{name}': {exc}",
            )
        return redirect("budgets:insurer_list")


# ---------------------------------------------------------------------------
# Tariff line inline save — HTMX POST, saves a single field change and
# returns the updated row fragment.
# Guardado inline de linea de tarifa — HTMX POST, guarda un cambio de campo
# y devuelve el fragmento de fila actualizado.
# ---------------------------------------------------------------------------


class TariffLineSaveView(AdminRoleRequiredMixin, View):
    """
    HTMX endpoint. Receives a POST with the full row field values for a
    TariffLine, saves them and returns the updated row fragment for swap.
    ---
    Endpoint HTMX. Recibe un POST con todos los valores de campo de la fila
    de una TariffLine, los guarda y devuelve el fragmento de fila actualizado.
    """

    def post(self, request, pk):
        """
        Save TariffLine fields from POST and return updated row fragment.
        ---
        Guarda los campos de TariffLine desde POST y devuelve el fragmento
        de fila actualizado.
        """
        from budgets.models import InsurerTariff
        company_user = _get_company_user(request)
        line = get_object_or_404(
            TariffLine,
            pk=pk,
            tariff__insurer__company=company_user.company,
        )
        data = request.POST

        # Update all editable fields atomically.
        # Actualizar todos los campos editables de forma atomica.
        line.concept = data.get("concept", line.concept)
        line.unit = data.get("unit", line.unit)
        line.price = data.get("price", line.price) or 0
        km_threshold = data.get("km_threshold", "").strip()
        line.km_threshold = int(km_threshold) if km_threshold else None
        min_units = data.get("min_units", "").strip()
        line.min_units = float(min_units) if min_units else None
        # Checkbox: present in POST = checked, absent = unchecked.
        # Checkbox: presente en POST = marcado, ausente = desmarcado.
        line.requires_authorization = "requires_authorization" in data
        line.save()

        ctx = {
            "line": line,
            "concept_choices": TariffLine.CONCEPT_CHOICES,
            "unit_choices": TariffLine.UNIT_CHOICES,
            "csrf_token": request.META.get("CSRF_COOKIE", ""),
        }
        return render(
            request,
            "budgets/_tariff_line_row_fragment.html",
            ctx,
        )


# ---------------------------------------------------------------------------
# Tariff line delete — HTMX POST, deletes the line and returns empty string
# so the row is removed from the DOM.
# Eliminacion de linea de tarifa — HTMX POST, elimina la linea y devuelve
# cadena vacia para que la fila desaparezca del DOM.
# ---------------------------------------------------------------------------


class TariffLineDeleteView(AdminRoleRequiredMixin, View):
    """
    HTMX endpoint. Deletes a TariffLine and returns an empty response
    so HTMX replaces the row with nothing (outerHTML swap).
    ---
    Endpoint HTMX. Elimina una TariffLine y devuelve una respuesta vacia
    para que HTMX sustituya la fila por nada (swap outerHTML).
    """

    def post(self, request, pk):
        """
        Delete the TariffLine and return empty 200 response.
        ---
        Elimina la TariffLine y devuelve respuesta 200 vacia.
        """
        company_user = _get_company_user(request)
        line = get_object_or_404(
            TariffLine,
            pk=pk,
            tariff__insurer__company=company_user.company,
        )
        line.delete()
        from django.http import HttpResponse
        return HttpResponse("")


# ---------------------------------------------------------------------------
# Tariff line add form — HTMX GET, returns the add-line inline form fragment.
# Formulario de adicion de linea — HTMX GET, devuelve el fragmento del
# formulario inline de nueva linea.
# ---------------------------------------------------------------------------


class TariffLineAddFormView(AdminRoleRequiredMixin, View):
    """
    HTMX GET endpoint. Returns the inline add-line form fragment for the
    given active tariff. The form is injected into #new-line-row.
    ---
    Endpoint HTMX GET. Devuelve el fragmento de formulario inline de nueva
    linea para la tarifa activa dada. El formulario se inyecta en #new-line-row.
    """

    def get(self, request, pk):
        """
        Return the add-line form fragment for the given tariff pk.
        ---
        Devuelve el fragmento de formulario de nueva linea para el pk de tarifa.
        """
        from budgets.models import InsurerTariff
        company_user = _get_company_user(request)
        tariff = get_object_or_404(
            InsurerTariff,
            pk=pk,
            insurer__company=company_user.company,
        )
        vehicle_types = (
            tariff.insurer.vehicle_types
            .filter(is_active=True)
            .order_by("sort_order", "name")
        )
        ctx = {
            "tariff": tariff,
            "vehicle_types": vehicle_types,
            "concept_choices": TariffLine.CONCEPT_CHOICES,
            "unit_choices": TariffLine.UNIT_CHOICES,
        }
        return render(
            request,
            "budgets/_tariff_line_add_form_fragment.html",
            ctx,
        )


# ---------------------------------------------------------------------------
# Tariff line add — HTMX POST, creates a new TariffLine and returns the
# new row fragment inserted at the top of the table.
# Adicion de linea — HTMX POST, crea una nueva TariffLine y devuelve el
# fragmento de fila nuevo insertado en la tabla.
# ---------------------------------------------------------------------------


class TariffLineAddView(AdminRoleRequiredMixin, View):
    """
    HTMX POST endpoint. Creates a new TariffLine for the given active tariff
    and returns the new row fragment. Also clears the add form by returning
    an empty string swapped into #new-line-row.
    ---
    Endpoint HTMX POST. Crea una nueva TariffLine para la tarifa activa dada
    y devuelve el fragmento de fila nuevo. Tambien limpia el formulario de
    adicion devolviendo cadena vacia en #new-line-row.
    """

    def post(self, request, pk):
        """
        Create a new TariffLine from POST data and return updated row.
        ---
        Crea una nueva TariffLine desde los datos POST y devuelve la fila.
        """
        from budgets.models import InsurerTariff
        from django.http import HttpResponse
        company_user = _get_company_user(request)
        tariff = get_object_or_404(
            InsurerTariff,
            pk=pk,
            insurer__company=company_user.company,
        )
        data = request.POST
        vehicle_type_id = data.get("vehicle_type_id", "").strip()
        vehicle_type = None
        if vehicle_type_id:
            vehicle_type = get_object_or_404(
                VehicleType,
                pk=int(vehicle_type_id),
                insurer=tariff.insurer,
            )
        km_threshold = data.get("km_threshold", "").strip()
        min_units = data.get("min_units", "").strip()
        line = TariffLine.objects.create(
            tariff=tariff,
            vehicle_type=vehicle_type,
            concept=data.get("concept", TariffLine.CONCEPT_DEPARTURE),
            unit=data.get("unit", TariffLine.UNIT_FIXED),
            price=data.get("price", 0) or 0,
            km_threshold=int(km_threshold) if km_threshold else None,
            min_units=float(min_units) if min_units else None,
            requires_authorization="requires_authorization" in data,
        )
        ctx = {
            "line": line,
            "concept_choices": TariffLine.CONCEPT_CHOICES,
            "unit_choices": TariffLine.UNIT_CHOICES,
            "csrf_token": request.META.get("CSRF_COOKIE", ""),
        }
        return render(
            request,
            "budgets/_tariff_line_row_fragment.html",
            ctx,
        )


# ---------------------------------------------------------------------------
# Insurer tariff create — creates a new tariff version, closes the active one.
# Creacion de nueva version de tarifa — crea una nueva version y cierra la activa.
# ---------------------------------------------------------------------------


class InsurerTariffCreateView(AdminRoleRequiredMixin, View):
    """
    Creates a new InsurerTariff version for the given insurer.
    Closes the currently active tariff (valid_to = valid_from - 1 day).
    Redirects back to the insurer edit view.
    ---
    Crea una nueva version de InsurerTariff para la aseguradora dada.
    Cierra la tarifa actualmente activa (valid_to = valid_from - 1 dia).
    Redirige de vuelta a la vista de edicion de la aseguradora.
    """

    def post(self, request, pk):
        """
        Create the new tariff version and close the previous active one.
        ---
        Crea la nueva version de tarifa y cierra la anterior activa.
        """
        from budgets.models import InsurerTariff
        from datetime import date, timedelta
        company_user = _get_company_user(request)
        insurer = get_object_or_404(
            Insurer,
            pk=pk,
            company=company_user.company,
        )
        year_raw = request.POST.get("year", "").strip()
        valid_from_raw = request.POST.get("valid_from", "").strip()
        if not year_raw or not valid_from_raw:
            messages.error(request, "El ano y la fecha de inicio son obligatorios.")
            return redirect("budgets:insurer_update", pk=pk)
        try:
            year = int(year_raw)
            valid_from = date.fromisoformat(valid_from_raw)
        except ValueError:
            messages.error(request, "Formato de ano o fecha invalido.")
            return redirect("budgets:insurer_update", pk=pk)

        with transaction.atomic():
            # Close the current active tariff.
            # Cerrar la tarifa activa actual.
            active = InsurerTariff.objects.filter(
                insurer=insurer,
                valid_to__isnull=True,
            ).first()
            if active:
                active.valid_to = valid_from - timedelta(days=1)
                active.save(update_fields=["valid_to"])
            # Create the new tariff version.
            # Crear la nueva version de tarifa.
            InsurerTariff.objects.create(
                insurer=insurer,
                year=year,
                valid_from=valid_from,
                valid_to=None,
                notes="",
            )
        messages.success(
            request,
            f"Nueva version de tarifa {year} creada correctamente.",
        )
        return redirect("budgets:insurer_update", pk=pk)


# ---------------------------------------------------------------------------
# Tariff notes save — saves the notes field of the active tariff.
# Guardado de notas de tarifa — guarda el campo notes de la tarifa activa.
# ---------------------------------------------------------------------------


class TariffSaveNotesView(AdminRoleRequiredMixin, View):
    """
    Saves the notes field of an InsurerTariff. Redirects back to the
    insurer edit view.
    ---
    Guarda el campo notes de un InsurerTariff. Redirige de vuelta a la
    vista de edicion de la aseguradora.
    """

    def post(self, request, pk):
        """
        Save tariff notes and redirect to insurer edit view.
        ---
        Guarda las notas de la tarifa y redirige a la vista de edicion.
        """
        from budgets.models import InsurerTariff
        company_user = _get_company_user(request)
        tariff = get_object_or_404(
            InsurerTariff,
            pk=pk,
            insurer__company=company_user.company,
        )
        tariff.notes = request.POST.get("notes", "").strip()
        tariff.save(update_fields=["notes"])
        messages.success(request, "Notas de la tarifa guardadas.")
        return redirect("budgets:insurer_update", pk=tariff.insurer.pk)
