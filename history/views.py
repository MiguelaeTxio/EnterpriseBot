# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/history/views.py
"""
Views for the machine history module (Hito 22).
Provides read-only access to intervention history per machine asset
for WORKSHOP role users.
---
Vistas para el modulo de historial de maquinas (Hito 22).
Proporciona acceso de solo lectura al historial de intervenciones
por maquina para rol WORKSHOP.
"""
from datetime import date, timedelta

from django.db.models import Sum
from django.views.generic import View
from django.shortcuts import render

from fleet.models import MachineAsset
from panel.mixins import WorkshopRequiredMixin
from work_order_processor.models import (
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


