# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/history/views.py
"""
Views for the machine history module (Hito 22).
Provides read-only access to intervention history per machine asset
and to work-order history per operator for WORKSHOP role users.
---
Vistas para el modulo de historial de maquinas (Hito 22).
Proporciona acceso de solo lectura al historial de intervenciones
por maquina y al historial de partes por operario para rol WORKSHOP.
"""
from datetime import date, timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.views.generic import View
from django.shortcuts import get_object_or_404, render

from fleet.models import MachineAsset
from panel.mixins import WorkshopRequiredMixin
from work_order_processor.models import (
    WorkOrder,
    WorkOrderEntry,
    WorkOrderEntryLine,
)

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fault category display maps — reused from analytics app
# Mapas de visualizacion de categoria de averia — reutilizados de analytics
# ---------------------------------------------------------------------------

_FAULT_CAT_MAP = {
    "MECHANICAL": "Mecánica",
    "ELECTRICAL": "Eléctrica",
    "HYDRAULIC": "Hidráulica",
    "BODYWORK": "Carrocería",
    "TIRES": "Neumáticos",
    "MAINTENANCE": "Mantenimiento",
    "OTHER": "Otra",
    None: "—",
    "": "—",
}

_FAULT_SUBCAT_LABELS = {
    "ENGINE": "Motor",
    "TRANSMISSION": "Transmisión",
    "BRAKES": "Frenos",
    "SUSPENSION": "Suspensión",
    "STEERING": "Dirección",
    "ALTERNATOR": "Alternador",
    "BATTERY": "Batería",
    "WIRING": "Cableado",
    "LIGHTS": "Alumbrado",
    "PUMP": "Bomba",
    "CYLINDER": "Cilindro",
    "HOSES": "Mangueras",
    "VALVES": "Válvulas",
    "CABIN": "Cabina",
    "CHASSIS": "Chasis",
    "FRONT_TIRE": "Neumático delantero",
    "REAR_TIRE": "Neumático trasero",
    "OIL_CHANGE": "Cambio de aceite",
    "FILTER": "Filtros",
    "GENERAL": "Revisión general",
    "OTHER": "Otro",
    None: "—",
    "": "—",
}

# ---------------------------------------------------------------------------
# Default date range: last 365 days
# Rango de fechas por defecto: últimos 365 días
# ---------------------------------------------------------------------------

_DEFAULT_DAYS = 365

# ---------------------------------------------------------------------------
# Page size for paginated views
# Tamaño de pagina para vistas paginadas
# ---------------------------------------------------------------------------

_PAGE_SIZE = 25

# ---------------------------------------------------------------------------
# Roles that can see all operators' work orders (elevated access)
# Roles que pueden ver partes de todos los operarios (acceso elevado)
# ---------------------------------------------------------------------------

_ELEVATED_ROLES = {"WORKSHOPBOSS", "ADMIN"}


class MachineHistoryView(WorkshopRequiredMixin, View):
    """
    Read-only view for WORKSHOP operators to consult the intervention
    history of any active machine asset in their company.

    GET parameters:
      machine_code — code of the MachineAsset to inspect (optional).
      date_from    — YYYY-MM-DD start of range (default: today - 365 days).
      date_to      — YYYY-MM-DD end of range (default: today).

    Returns a chronological (descending) list of WorkOrderEntryLine records
    filtered by machine and date range, plus a summary header with totals.
    No cost data is ever exposed.
    ---
    Vista de solo lectura para operarios WORKSHOP para consultar el
    historial de intervenciones de cualquier maquina activa de su empresa.

    Parametros GET:
      machine_code — codigo del MachineAsset a inspeccionar (opcional).
      date_from    — YYYY-MM-DD inicio del rango (por defecto: hoy - 365 dias).
      date_to      — YYYY-MM-DD fin del rango (por defecto: hoy).

    Devuelve una lista cronologica (descendente) de registros
    WorkOrderEntryLine filtrados por maquina y rango de fechas,
    mas un resumen de cabecera con totales.
    Sin exposicion de datos de coste.
    """

    template_name = "panel/machine_history.html"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_company(self, request):
        """
        Returns the company scoped to the authenticated user.
        ---
        Retorna la empresa del usuario autenticado.
        """
        return request.user.company_user.company

    def _parse_date(self, raw, fallback):
        """
        Parses a YYYY-MM-DD string; returns fallback on any error.
        ---
        Parsea una cadena YYYY-MM-DD; retorna fallback ante cualquier error.
        """
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return fallback

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(self, request, *args, **kwargs):
        """
        Renders the machine history page.
        Fetches WorkOrderEntryLine records for the selected machine and
        date range. Computes summary totals (count, hours, last date).
        ---
        Renderiza la pagina de historial de maquina.
        Obtiene registros WorkOrderEntryLine para la maquina y rango
        de fechas seleccionados. Calcula totales del resumen (contador,
        horas, ultima fecha).
        """
        company = self._get_company(request)
        company_user = request.user.company_user

        today = date.today()
        default_from = today - timedelta(days=_DEFAULT_DAYS)

        # -- Parse GET params -----------------------------------------------
        machine_code_raw = (
            request.GET.get("machine_code", "").strip().upper()
        )
        date_from = self._parse_date(
            request.GET.get("date_from", "").strip(), default_from
        )
        date_to = self._parse_date(
            request.GET.get("date_to", "").strip(), today
        )

        # Swap if inverted
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        # -- Machine queryset scoped to company -----------------------------
        machines = MachineAsset.objects.filter(
            company=company,
            is_active=True,
        )

        # -- Resolve selected machine by code -------------------------------
        selected_machine = None
        if machine_code_raw:
            selected_machine = machines.filter(
                code=machine_code_raw
            ).first()

        # -- History query --------------------------------------------------
        lines = []
        total_intervenciones = 0
        total_horas = None
        ultima_intervencion = None

        if selected_machine is not None:
            qs = (
                WorkOrderEntryLine.objects.filter(
                    machine_asset=selected_machine,
                    entry__work_date__range=(date_from, date_to),
                )
                .select_related(
                    "entry",
                    "entry__work_order",
                )
                .order_by(
                    "-entry__work_date",
                    "-entry__work_order__id",
                )
            )

            # Enrich with translated labels before passing to template
            # Enriquecer con etiquetas traducidas antes de pasar al template
            enriched = []
            for line in qs:
                enriched.append(
                    {
                        "work_date": line.entry.work_date,
                        "worker_name": line.entry.worker_name,
                        "fault_category_display": _FAULT_CAT_MAP.get(
                            line.fault_category,
                            line.fault_category or "—",
                        ),
                        "fault_subcategory_display": (
                            _FAULT_SUBCAT_LABELS.get(
                                line.fault_subcategory,
                                line.fault_subcategory or "—",
                            )
                        ),
                        "fault_description": (
                            line.fault_description or "—"
                        ),
                        "repair_notes": line.repair_notes or "—",
                        "delta_hours": line.delta_hours,
                        "or_val": line.or_val,
                    }
                )

            lines = enriched
            total_intervenciones = len(enriched)

            # Summary aggregates
            agg = qs.aggregate(
                suma_horas=Sum("delta_hours"),
                ultima=django_max("entry__work_date"),
            )
            total_horas = agg["suma_horas"]
            ultima_intervencion = agg["ultima"]

        context = {
            "company": company,
            "company_user": company_user,
            "own_presence": self._get_own_presence(request),
            "active_nav": "machine_history",
            # Selector data
            "selected_machine": selected_machine,
            "machine_code": machine_code_raw,
            # Date range
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            # Results
            "lines": lines,
            "has_results": selected_machine is not None,
            # Summary
            "total_intervenciones": total_intervenciones,
            "total_horas": total_horas,
            "ultima_intervencion": ultima_intervencion,
        }
        return render(request, self.template_name, context)

    # ------------------------------------------------------------------
    # Presence helper (same pattern as panel views)
    # Helper de presencia (mismo patron que las vistas del panel)
    # ------------------------------------------------------------------

    def _get_own_presence(self, request):
        """
        Returns the current active PresenceStatus for the authenticated user,
        or None if no active status exists.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado,
        o None si no existe estado activo.
        """
        from django.db.models import Q
        from django.utils.timezone import now as tz_now
        from ivr_config.models import PresenceStatus

        cu = request.user.company_user
        return (
            PresenceStatus.objects.filter(
                company_user=cu,
                starts_at__lte=tz_now(),
            )
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=tz_now()))
            .order_by("-starts_at")
            .first()
        )


# ---------------------------------------------------------------------------
# Local alias for django.db.models.Max — avoids top-level import collision
# Alias local para django.db.models.Max — evita colision con import global
# ---------------------------------------------------------------------------

def django_max(field):
    """
    Returns a Max() aggregate expression for the given field.
    Used to avoid name collision with Python built-in max().
    ---
    Retorna una expresion agregada Max() para el campo dado.
    Se usa para evitar colision con el built-in max() de Python.
    """
    from django.db.models import Max
    return Max(field)


class WorkOrderHistoryListView(WorkshopRequiredMixin, View):
    """
    Read-only paginated list of WorkOrder records accessible to
    WORKSHOP operators and their superiors.

    Access rules:
      WORKSHOP     — sees only their own work orders (uploaded_by=self).
      WORKSHOPBOSS — sees all work orders of their company.
      ADMIN        — sees all work orders of their company.

    GET parameters:
      date_from    — YYYY-MM-DD start of range (default: today - 365 days).
      date_to      — YYYY-MM-DD end of range (default: today).
      machine_code — filter by MachineAsset code (optional).
      search       — free-text search in WorkOrderEntryLine.fault_description
                     (optional).
      status       — filter by WorkOrder.status code (optional, default: all).
      page         — page number for pagination (default: 1).

    No cost data is ever exposed.
    ---
    Lista paginada de solo lectura de partes de trabajo (WorkOrder)
    accesible a los operarios WORKSHOP y sus superiores.

    Reglas de acceso:
      WORKSHOP     — ve solo sus propios partes (uploaded_by=self).
      WORKSHOPBOSS — ve todos los partes de su empresa.
      ADMIN        — ve todos los partes de su empresa.

    Parametros GET:
      date_from    — YYYY-MM-DD inicio (por defecto: hoy - 365 dias).
      date_to      — YYYY-MM-DD fin (por defecto: hoy).
      machine_code — filtrar por codigo de MachineAsset (opcional).
      search       — busqueda libre en fault_description de las lineas.
      status       — filtrar por WorkOrder.status (opcional, por defecto todos).
      page         — numero de pagina (por defecto: 1).

    Sin exposicion de datos de coste.
    """

    template_name = "panel/workorder_history_list.html"

    def _parse_date(self, raw, fallback):
        """
        Parses a YYYY-MM-DD string; returns fallback on any error.
        ---
        Parsea una cadena YYYY-MM-DD; retorna fallback ante cualquier error.
        """
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return fallback

    def get(self, request, *args, **kwargs):
        """
        Renders the paginated work-order history list for the operator.
        Scopes to own records when role is WORKSHOP; shows all company
        records for WORKSHOPBOSS and ADMIN.
        ---
        Renderiza la lista paginada de historial de partes del operario.
        Limita a los propios cuando el rol es WORKSHOP; muestra todos
        los de la empresa para WORKSHOPBOSS y ADMIN.
        """
        company_user = request.user.company_user
        company = company_user.company
        is_elevated = company_user.role in _ELEVATED_ROLES

        today = date.today()
        default_from = today - timedelta(days=_DEFAULT_DAYS)

        # -- Parse filters --------------------------------------------------
        date_from = self._parse_date(
            request.GET.get("date_from", "").strip(), default_from
        )
        date_to = self._parse_date(
            request.GET.get("date_to", "").strip(), today
        )
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        machine_code = (
            request.GET.get("machine_code", "").strip().upper()
        )
        search = request.GET.get("search", "").strip()
        status_filter = request.GET.get("status", "").strip()

        # -- Base queryset --------------------------------------------------
        # WorkOrder date is represented by its entries' work_date.
        # We filter by the earliest entry work_date within the WO.
        # A WO appears if ANY of its entries falls in the date range.
        # ---
        # La fecha de un WorkOrder se representa por work_date de sus entries.
        # Un WO aparece si ALGUNA de sus entradas cae en el rango de fechas.
        qs = (
            WorkOrder.objects.filter(
                company=company,
                entries__work_date__range=(date_from, date_to),
            )
            .distinct()
        )

        # -- Scope to own records for WORKSHOP role -------------------------
        if not is_elevated:
            qs = qs.filter(uploaded_by=company_user)

        # -- Optional filters -----------------------------------------------
        if status_filter:
            qs = qs.filter(status=status_filter)

        if machine_code:
            qs = qs.filter(
                entries__lines__machine_asset__code=machine_code
            ).distinct()

        if search:
            qs = qs.filter(
                entries__lines__fault_description__icontains=search
            ).distinct()

        # -- Ordering: most recent first ------------------------------------
        # Use the max work_date of entries as sort key.
        # Ordenar por la fecha de entrada mas reciente.
        from django.db.models import Max as _Max
        qs = qs.annotate(
            latest_work_date=_Max("entries__work_date")
        ).order_by("-latest_work_date", "-id")

        # -- Pagination -----------------------------------------------------
        paginator = Paginator(qs, _PAGE_SIZE)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)

        # -- Status choices for filter dropdown ----------------------------
        status_choices = WorkOrder.Status.choices

        # -- Presence (sidebar badge) --------------------------------------
        own_presence = self._get_own_presence(request)

        context = {
            "company": company,
            "company_user": company_user,
            "own_presence": own_presence,
            "active_nav": "workorder_history",
            "is_elevated": is_elevated,
            # Filters (echoed back for form re-population)
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "machine_code": machine_code,
            "search": search,
            "status_filter": status_filter,
            "status_choices": status_choices,
            # Results
            "page_obj": page_obj,
            "total_count": paginator.count,
        }
        return render(request, self.template_name, context)

    def _get_own_presence(self, request):
        """
        Returns the current active PresenceStatus for the authenticated user,
        or None if no active status exists.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado,
        o None si no existe estado activo.
        """
        from django.db.models import Q
        from django.utils.timezone import now as tz_now
        from ivr_config.models import PresenceStatus

        cu = request.user.company_user
        return (
            PresenceStatus.objects.filter(
                company_user=cu,
                starts_at__lte=tz_now(),
            )
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=tz_now()))
            .order_by("-starts_at")
            .first()
        )


class WorkOrderHistoryDetailView(WorkshopRequiredMixin, View):
    """
    Read-only detail view for a single WorkOrder record.

    Access rules:
      WORKSHOP     — can only view their own work orders (uploaded_by=self).
                     Returns 404 if the requested pk belongs to another user.
      WORKSHOPBOSS — can view any work order in their company.
      ADMIN        — can view any work order in their company.

    The view is strictly read-only in all cases: the operator cannot
    modify any field, even if the work order is still open (IN_PROGRESS).

    GET /panel/history/workorders/<pk>/
    ---
    Vista de detalle de solo lectura para un WorkOrder individual.

    Reglas de acceso:
      WORKSHOP     — solo puede ver sus propios partes (uploaded_by=self).
                     Devuelve 404 si el pk pertenece a otro usuario.
      WORKSHOPBOSS — puede ver cualquier parte de su empresa.
      ADMIN        — puede ver cualquier parte de su empresa.

    La vista es estrictamente de solo lectura en todos los casos: el
    operario no puede modificar ningun campo, aunque el parte este
    abierto (IN_PROGRESS).

    GET /panel/history/workorders/<pk>/
    """

    template_name = "panel/workorder_history_detail.html"

    def get(self, request, pk, *args, **kwargs):
        """
        Renders the read-only detail page for a WorkOrder.
        Enforces ownership restriction for WORKSHOP role.
        Prefetches all entries and their lines for efficient rendering.
        ---
        Renderiza la pagina de detalle de solo lectura de un WorkOrder.
        Aplica la restriccion de propiedad para el rol WORKSHOP.
        Prefetch de entries y lineas para renderizado eficiente.
        """
        company_user = request.user.company_user
        company = company_user.company
        is_elevated = company_user.role in _ELEVATED_ROLES

        # -- Fetch the work order scoped to company -------------------------
        qs = WorkOrder.objects.filter(company=company)

        # WORKSHOP role: restrict to own records only
        # Rol WORKSHOP: restringir a los propios
        if not is_elevated:
            qs = qs.filter(uploaded_by=company_user)

        work_order = get_object_or_404(qs, pk=pk)

        # -- Fetch entries and enrich lines with translated labels ----------
        # Obtenemos entries + lines y enriquecemos en Python para evitar
        # filtros personalizados (get_item) en el template.
        from django.db.models import Prefetch
        entries_qs = (
            WorkOrderEntry.objects.filter(work_order=work_order)
            .prefetch_related(
                Prefetch(
                    "lines",
                    queryset=WorkOrderEntryLine.objects.select_related(
                        "machine_asset"
                    ).order_by("line_number"),
                )
            )
            .order_by("page_number")
        )

        # Build enriched structure: list of dicts per entry, each with
        # a list of enriched line dicts. Keeps templates dumb.
        # ---
        # Estructura enriquecida: lista de dicts por entry, cada uno con
        # lista de dicts de lineas enriquecidas. Mantiene templates tontos.
        enriched_entries = []
        for entry in entries_qs:
            enriched_lines = []
            for line in entry.lines.all():
                enriched_lines.append({
                    "hc": line.hc,
                    "hf": line.hf,
                    "machine_asset": line.machine_asset,
                    "machine_norm": line.machine_norm,
                    "machine_raw": line.machine_raw,
                    "fault_description": line.fault_description or "—",
                    "repair_notes": line.repair_notes or "—",
                    "fault_category_display": _FAULT_CAT_MAP.get(
                        line.fault_category,
                        line.fault_category or "",
                    ),
                    "fault_subcategory_display": _FAULT_SUBCAT_LABELS.get(
                        line.fault_subcategory,
                        line.fault_subcategory or "",
                    ),
                    "delta_hours": line.delta_hours,
                    "or_val": line.or_val,
                })
            enriched_entries.append({
                "work_date": entry.work_date,
                "worker_name": entry.worker_name,
                "uncertain_date": entry.uncertain_date,
                "has_diet": entry.has_diet,
                "lines": enriched_lines,
            })

        # -- Presence (sidebar badge) --------------------------------------
        own_presence = self._get_own_presence(request)

        context = {
            "company": company,
            "company_user": company_user,
            "own_presence": own_presence,
            "active_nav": "workorder_history",
            "is_elevated": is_elevated,
            "work_order": work_order,
            "entries": enriched_entries,
        }
        return render(request, self.template_name, context)

    def _get_own_presence(self, request):
        """
        Returns the current active PresenceStatus for the authenticated user,
        or None if no active status exists.
        ---
        Retorna el PresenceStatus activo actual del usuario autenticado,
        o None si no existe estado activo.
        """
        from django.db.models import Q
        from django.utils.timezone import now as tz_now
        from ivr_config.models import PresenceStatus

        cu = request.user.company_user
        return (
            PresenceStatus.objects.filter(
                company_user=cu,
                starts_at__lte=tz_now(),
            )
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=tz_now()))
            .order_by("-starts_at")
            .first()
        )
