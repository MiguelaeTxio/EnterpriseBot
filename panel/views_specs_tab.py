# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_specs_tab.py
"""
H23 (S154, invasora). "Especificaciones" tab of the Documentation hub:
filter the cost centres by their technical specifications. S163: the
common list format (directives 4.24 and 4.27).

---

H23 (S154, invasora). Pestaña "Especificaciones" del hub de
Documentación. Carlos: "quiero saber cuáles son los camiones y grúas de
50T". Filtra los centros de gasto por capacidad de elevación, momento
de carga y masa máxima autorizada (en toneladas); columnas con las
especificaciones de la ficha (fleet.specs_service las rellena de la
ITV, el permiso de circulación, la ficha técnica y la tabla de carga).

S163 (invasora UX). Miguel Ángel: "esta vista de especificaciones no
tiene nada que ver ya con el resto. Esto parece otra aplicación
diferente". Pasa al formato común, como Revisiones y Centros de gasto:
- Buscar y filtrar: Buscar · Estado · Familia · Grupo (los mismos de
  Centros de gasto, `fleet.views._build_queryset`) y, debajo, lo propio
  (capacidad, momento, MMA y "Solo con datos"); pestaña "Columnas" con
  el catálogo `specs_tab` (panel/screen_export_catalog.py).
- Grupos de selección, Acciones (N seleccionados, Limpiar, Exportar),
  listado con casillas, orden múltiple por cabecera, menú de tres
  puntos y "Selección actual".
- Navegación persistida por usuario (4.15).
- El código abre la tarjeta técnica (panel/views_machine_menu.py), no
  la ficha.
Todo se decide aquí; las plantillas solo pintan.
"""
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from fleet.models import MachineAsset
from fleet.views import _build_queryset, _get_families
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation, get_saved_state_key,
)
from panel.views_machine_menu import machine_menu_items

SCREEN_KEY = "specs_tab"
FILTER_KEYS = (
    "search", "family", "is_active", "group", "sort", "cap_min", "cap_max",
    "tm_min", "tm_max", "mma_min", "mma_max", "with_specs",
)
RANGE_KEYS = ("cap_min", "cap_max", "tm_min", "tm_max", "mma_min",
              "mma_max")
# Clave de orden -> valor de la máquina (sin dato: siempre al final).
SORT_VALUES = {
    "code": lambda m: (m.code or "").upper(),
    "family": lambda m: (m.family or "").upper(),
    "brand_model": lambda m: (m.brand_model or "").upper(),
    "type_name": lambda m: (m.type_name or "").upper(),
    "plate": lambda m: (m.plate or "").upper(),
    "is_active": lambda m: m.is_active,
    "capacity": lambda m: m.capacity_tonnes,
    "moment": lambda m: m.capacity_tm,
    "mma": lambda m: m.max_authorized_mass_kg,
    "mass": lambda m: m.mass_kg,
    "axles": lambda m: m.axle_count,
    "length": lambda m: m.length_mm,
    "width": lambda m: m.width_mm,
    "height": lambda m: m.height_mm,
    "year": lambda m: m.manufacture_year,
}
SORT_KEYS = tuple(SORT_VALUES)
# Primer clic en una cifra: la mayor arriba (lo que se busca es "las de
# 50 t o más").
SORT_DESC_FIRST = ("capacity", "moment", "mma", "mass", "axles", "length",
                   "width", "height", "year")
MAX_SORT_KEYS = 4


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


def _parse_sort(raw):
    """
    "key,-key" -> [(key, descending)] (valid keys only, max 4).

    ---

    "clave,-clave" -> [(clave, descendente)], solo claves válidas y sin
    repetir, como mucho 4 (mismas reglas que Revisiones).
    """
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in SORT_KEYS and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Next "sort" value, arrow and priority of each sortable column.

    ---

    Para cada columna ordenable: el "sort" que envía un clic en su
    cabecera (la promueve a principal; si ya lo es, invierte el
    sentido), su flecha y su prioridad.
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    sort_next, sort_arrows, sort_priority = {}, {}, {}
    for key in SORT_KEYS:
        if key in active:
            index = active.index(key)
            desc = sort_keys[index][1]
            sort_arrows[key] = "down" if desc else "up"
            sort_priority[key] = index + 1 if len(sort_keys) > 1 else ""
            first = (key, (not desc) if index == 0 else desc)
        else:
            sort_arrows[key] = ""
            sort_priority[key] = ""
            first = (key, key in SORT_DESC_FIRST)
        new_keys = [first] + [(k, d) for k, d in sort_keys if k != key]
        sort_next[key] = ",".join(
            ("-" if d else "") + k for k, d in new_keys[:MAX_SORT_KEYS]
        )
    return {
        "sort_next": sort_next,
        "sort_arrows": sort_arrows,
        "sort_priority": sort_priority,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(
            ("-" if d else "") + k for k, d in sort_keys
        ),
    }


def _sort_machines(machines, raw):
    """
    Sort by the requested keys; without any, by capacity (largest first).

    ---

    Ordena por las claves pedidas, con el código como último desempate;
    sin dato, siempre al final en los dos sentidos. Sin orden elegido,
    el de siempre de la pestaña: capacidad de mayor a menor.
    """
    sort_keys = _parse_sort(raw) or [("capacity", True)]
    machines = sorted(machines, key=SORT_VALUES["code"])
    for key, desc in reversed(sort_keys):
        getter = SORT_VALUES[key]
        present = [m for m in machines if getter(m) not in (None, "")]
        empty = [m for m in machines if getter(m) in (None, "")]
        present.sort(key=getter, reverse=desc)
        machines = present + empty
    return machines


def _filtered(request):
    """
    The cost centres of the filters, unsorted.

    ---

    Los centros de gasto de los filtros, sin ordenar. Los comunes
    (búsqueda, estado, familia, grupo y "solo la selección actual") son
    los de Centros de gasto; con "solo la selección actual" se saltan
    también los propios, como allí.
    """
    company = request.user.company_user.company
    unsorted = request.GET.copy()
    unsorted.pop("sort", None)
    original_get, request.GET = request.GET, unsorted
    try:
        machines = _build_queryset(company, request)
    finally:
        request.GET = original_get
    params = request.GET
    only_selected = (
        params.get("only_selected") == "1"
        and any(pk.isdigit() for pk in params.get(
            "selected_ids", "").split(","))
    )
    if only_selected:
        return list(machines)
    ranges = (
        ("cap_min", "cap_max", "capacity_tonnes", 1),
        ("tm_min", "tm_max", "capacity_tm", 1),
        ("mma_min", "mma_max", "max_authorized_mass_kg", 1000),
    )
    for low_key, high_key, field_name, factor in ranges:
        low, high = _tonnes(params.get(low_key)), _tonnes(
            params.get(high_key))
        if low is not None:
            machines = machines.filter(**{field_name + "__gte": low * factor})
        if high is not None:
            machines = machines.filter(
                **{field_name + "__lte": high * factor})
    if params.get("with_specs", "1") != "0":
        machines = machines.filter(
            Q(capacity_tonnes__isnull=False)
            | Q(capacity_tm__isnull=False)
            | Q(max_authorized_mass_kg__isnull=False)
            | Q(mass_kg__isnull=False)
        )
    return list(machines)


def _list_context(request):
    """
    Filtered and sorted rows, their cells and the filter state.

    ---

    Filas filtradas y ordenadas, sus celdas (columnas elegidas por el
    usuario), el menú de cada fila y el estado de los filtros.
    """
    from panel.list_columns import view_context
    from panel.screen_exports import get_screen

    company_user = request.user.company_user
    sort_raw = request.GET.get("sort", "")
    machines = _sort_machines(_filtered(request), sort_raw)
    controls = _sort_controls(sort_raw)
    for machine in machines:
        items = machine_menu_items(company_user, machine)
        machine.card_url = items[0]["url"]
        machine.menu_items = items[1:]
    params = request.GET
    return {
        "machines": machines,
        "count": len(machines),
        "families": _get_families(company_user.company),
        "filter_search": params.get("search", ""),
        "filter_family": params.get("family", ""),
        "filter_is_active": params.get("is_active", ""),
        "filter_with_specs": params.get("with_specs", "1") != "0",
        "ranges": {key: params.get(key, "") for key in RANGE_KEYS},
        **controls,
        **view_context(company_user, get_screen(SCREEN_KEY), machines,
                       controls),
    }


class SpecsTabView(CompanyUserRequiredMixin, View):
    """
    GET: the "Especificaciones" tab (or only the table with ?fragment=1).

    ---

    GET: pestaña "Especificaciones" (panel completo, o solo la tabla con
    ?fragment=1 al cambiar filtros, columnas u orden). Guarda y recupera
    la navegación del usuario (filtros, orden y selección).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        context = _list_context(request)
        if request.GET.get("fragment") == "1":
            return render(request, "panel/specs/_table.html", context)
        from panel.person_groups import (
            GROUP_FILTER_NONE, MACHINE_KIND, collapsed_state,
            group_filter_options, group_tree, parent_choices,
        )

        company_user = request.user.company_user
        selection = get_saved_state_key(
            company_user, SCREEN_KEY, "selection", [])
        selection = [
            pk for pk in (selection if isinstance(selection, list) else [])
            if str(pk).isdigit()
        ]
        codes = dict(MachineAsset.objects.filter(
            company=company_user.company, pk__in=selection,
        ).values_list("pk", "code"))
        context.update({
            "saved_selection": [
                {"pk": str(pk), "label": codes.get(int(pk), "")}
                for pk in selection
            ],
            "screen_key": SCREEN_KEY,
            "group_filter": request.GET.get("group", ""),
            "group_filter_none": GROUP_FILTER_NONE,
            "group_filter_options": group_filter_options(
                company_user, MACHINE_KIND),
            "machine_group_nodes": group_tree(company_user, MACHINE_KIND),
            "machine_groups_collapsed": collapsed_state(
                company_user, MACHINE_KIND),
            "machine_group_parents": parent_choices(
                editor=company_user, kind=MACHINE_KIND),
        })
        return render(request, "panel/specs/tab.html", context)


class SpecsExportView(CompanyUserRequiredMixin, View):
    """
    GET: the Especificaciones list to Excel, PDF, HTML or print.

    ---

    GET: exporta lo que muestra el listado, con sus filtros y orden (o
    solo los marcados, `selected`), con la plantilla elegida en el modal
    común.
    """

    def get(self, request):
        from openpyxl import Workbook

        from panel.export_formats import workbook_response
        from panel.screen_exports import columns_for, get_screen, write_sheet

        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        machines = _sort_machines(
            _filtered(request), request.GET.get("sort", ""))
        selected = {v for v in request.GET.getlist("selected") if v.isdigit()}
        if selected:
            machines = [m for m in machines if str(m.pk) in selected]
        if not machines:
            return HttpResponse(
                "No hay ningún centro de gasto que exportar.", status=400)
        columns = columns_for(request, get_screen(SCREEN_KEY))
        if columns is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ESPECIFICACIONES"
        write_sheet(sheet, columns, machines)
        return workbook_response(request, workbook, "especificaciones")
