# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_specs_tab.py
"""
H23 (S154, invasora). "Especificaciones" tab of the Documentation hub:
filter the cost centres by their technical specifications.

---

H23 (S154, invasora). Pestaña "Especificaciones" del hub de
Documentación. Carlos: "quiero saber cuáles son los camiones y grúas de
50T". Filtra los centros de gasto por capacidad de elevación y masa
máxima autorizada (en toneladas), familia, solo activos y búsqueda
libre; columnas con las especificaciones de la ficha
(fleet.specs_service las rellena de la ITV, el permiso de circulación,
la ficha técnica y la tabla de carga). Todo se decide aquí; la
plantilla solo pinta.
"""
from decimal import Decimal, InvalidOperation

from django.db.models import F, Q
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from fleet.models import MachineAsset
from fleet.views import _get_families
from panel.mixins import CompanyUserRequiredMixin

TEMPLATE = "panel/specs/tab.html"
SORT_CHOICES = (
    ("-capacity", "Capacidad (mayor primero)"),
    ("capacity", "Capacidad (menor primero)"),
    ("-mma", "MMA (mayor primero)"),
    ("mma", "MMA (menor primero)"),
    ("code", "Código"),
)
SORT_FIELDS = {
    "capacity": "capacity_tonnes",
    "mma": "max_authorized_mass_kg",
    "code": "code",
}


def _tonnes(raw):
    """
    Decimal tonnes from a filter box ("50", "4,5"); None if empty.

    ---

    Toneladas de una casilla de filtro ("50", "4,5"); None si vacía o
    no es un número.
    """
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def _metres(value_mm):
    if value_mm is None:
        return ""
    return ("%.2f" % (value_mm / 1000)).replace(".", ",")


class SpecsTabView(CompanyUserRequiredMixin, View):
    """
    GET: the filtered list of cost centres with their specifications.

    ---

    GET: la lista filtrada de centros de gasto con sus especificaciones.
    """

    def get(self, request):
        company = request.user.company_user.company
        params = request.GET
        filters = {
            "search": params.get("search", "").strip(),
            "family": params.get("family", ""),
            "cap_min": params.get("cap_min", "").strip(),
            "cap_max": params.get("cap_max", "").strip(),
            "mma_min": params.get("mma_min", "").strip(),
            "mma_max": params.get("mma_max", "").strip(),
            "active": params.get("active", "1"),
            "with_specs": params.get("with_specs", "1"),
            "sort": params.get("sort", "-capacity"),
        }
        machines = MachineAsset.objects.filter(company=company)
        if filters["active"] == "1":
            machines = machines.filter(is_active=True)
        if filters["family"]:
            machines = machines.filter(family=filters["family"])
        if filters["search"]:
            term = filters["search"]
            machines = machines.filter(
                Q(code__icontains=term) | Q(brand_model__icontains=term)
                | Q(plate__icontains=term)
            )
        cap_min, cap_max = _tonnes(filters["cap_min"]), _tonnes(
            filters["cap_max"])
        if cap_min is not None:
            machines = machines.filter(capacity_tonnes__gte=cap_min)
        if cap_max is not None:
            machines = machines.filter(capacity_tonnes__lte=cap_max)
        mma_min, mma_max = _tonnes(filters["mma_min"]), _tonnes(
            filters["mma_max"])
        if mma_min is not None:
            machines = machines.filter(
                max_authorized_mass_kg__gte=mma_min * 1000)
        if mma_max is not None:
            machines = machines.filter(
                max_authorized_mass_kg__lte=mma_max * 1000)
        if filters["with_specs"] == "1":
            machines = machines.filter(
                Q(capacity_tonnes__isnull=False)
                | Q(max_authorized_mass_kg__isnull=False)
                | Q(mass_kg__isnull=False)
            )
        sort = filters["sort"]
        field = SORT_FIELDS.get(sort.lstrip("-"), "capacity_tonnes")
        expression = F(field)
        expression = (
            expression.desc(nulls_last=True) if sort.startswith("-")
            else expression.asc(nulls_last=True)
        )
        machines = machines.order_by(expression, "code")
        rows = [{
            "machine": machine,
            "detail_url": reverse(
                "panel:documentation_machine_detail", args=[machine.pk]),
            "capacity": machine.capacity_tonnes,
            "capacity_text": machine.max_capacity,
            "mma_t": (
                ("%.1f" % (machine.max_authorized_mass_kg / 1000)).replace(
                    ".", ",")
                if machine.max_authorized_mass_kg else ""
            ),
            "dimensions": " × ".join(
                part for part in (
                    _metres(machine.length_mm), _metres(machine.width_mm),
                    _metres(machine.height_mm),
                ) if part
            ),
        } for machine in machines[:1000]]
        return render(request, TEMPLATE, {
            "rows": rows,
            "count": len(rows),
            "filters": filters,
            "families": _get_families(company),
            "sort_choices": SORT_CHOICES,
            "tab_url": reverse("panel:specs_tab"),
        })
