# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_epi_deliveries.py
"""
"EPIs" tab of the Documentation hub with the single list format of
the panel (directive 4.24, H31 S148): fixed top panel (search and
filters, saved batches and their content) and a bottom panel with the
deliveries list -- the only part that scrolls, multi-column sort with
priority, full screen and a row menu -- next to the EPI catalogue.
Filters and sort are kept per user (screen_key "epi_deliveries").
The deliveries themselves are read-only here (Miguel Ángel, S113:
"Son los EPIs entregados, ahí no hay que hacer más nada").

---

Pestaña "EPIs" del hub de Documentación con el formato único de
listado del panel (directriz 4.24, H31 S148): panel fijo arriba
(buscar y filtrar, lotes guardados y su contenido) y panel inferior
con el listado de entregas -- lo único que hace scroll, orden por
varias columnas con prioridad, pantalla completa y menú de fila --
junto al catálogo de EPIs. Filtros y orden se recuerdan por usuario
(screen_key "epi_deliveries"). Las entregas aquí solo se consultan
(Miguel Ángel, S113: "Son los EPIs entregados, ahí no hay que hacer
más nada").
"""
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views import View

from document_explorer.models import (
    EpiDelivery,
    EpiDeliveryBatchTemplate,
    EpiItemCatalog,
)
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import apply_list_navigation

SCREEN_KEY = "epi_deliveries"
FILTER_KEYS = ["q", "sort", "family", "date_from", "date_to",
               "active", "company", "group", "section"]
MAX_SORT_KEYS = 4
PAGE_SIZE = 200
NO_FAMILY = "none"

# key, column header, ORM fields (person name sorts by its three parts).
COLUMNS = [
    ("date", "Fecha de entrega", ["delivery_date"]),
    ("person", "Trabajador", [
        "person__first_surname", "person__second_surname",
        "person__given_name",
    ]),
    ("family", "Familia", ["epi__family"]),
    ("epi", "EPI", ["epi__label"]),
]
DEFAULT_ORDER = ["-delivery_date", "person__first_surname"]


def _families():
    """
    Distinct families of the EPI catalogue, alphabetical.

    ---

    Familias distintas del catálogo de EPIs, por orden alfabético.
    """
    return list(
        EpiItemCatalog.objects.order_by("family")
        .values_list("family", flat=True).distinct()
    )


def _family_filter(raw, families):
    """
    Checked families: "" means all of them, "none" none of them.

    ---

    Familias marcadas: "" son todas, "none" ninguna (semántica literal
    de las casillas, directriz 4.24).
    """
    if not raw:
        return list(families)
    if raw == NO_FAMILY:
        return []
    wanted = {value for value in raw.split(",") if value}
    return [family for family in families if family in wanted]


def _parse_sort(raw):
    """
    Valid sort keys ("key" or "-key"), at most four, unknown dropped.

    ---

    Claves de orden válidas ("clave" o "-clave"), como mucho cuatro;
    las desconocidas se descartan.
    """
    valid = {key for key, _label, _fields in COLUMNS}
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in valid and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:MAX_SORT_KEYS]


def _sort_controls(sort_keys):
    """
    Header links, arrows and priorities (same rules as Fichajes and
    Repostajes: a click promotes the column, a click on the main one
    reverses it).

    ---

    Enlaces, flechas y prioridad de cada cabecera (mismas reglas que
    Fichajes y Repostajes: un clic sube la columna a criterio
    principal; un clic en la principal invierte su sentido).
    """
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label, _fields in COLUMNS:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(("-" if d else "") + k
                             for k, d in new_keys[:MAX_SORT_KEYS]),
        })
    return columns


def _order_by(sort_keys):
    """
    ORM ordering for the sort keys (default: newest delivery first).

    ---

    Orden del ORM para las claves (por defecto, la entrega más
    reciente primero).
    """
    fields_by_key = {key: fields for key, _label, fields in COLUMNS}
    order = []
    for key, desc in sort_keys:
        for field in fields_by_key[key]:
            order.append(("-" if desc else "") + field)
    return (order or DEFAULT_ORDER) + ["pk"]


def _list_context(request):
    """
    Filtered, sorted and paginated deliveries plus the filter state.

    ---

    Entregas filtradas, ordenadas y paginadas, más el estado de los
    filtros.
    """
    families = _families()
    family_raw = request.GET.get("family", "")
    checked_families = _family_filter(family_raw, families)
    search = request.GET.get("q", "").strip()
    date_from = parse_date(request.GET.get("date_from", "") or "")
    date_to = parse_date(request.GET.get("date_to", "") or "")
    sort_keys = _parse_sort(request.GET.get("sort", ""))

    qs = EpiDelivery.objects.select_related("person", "epi")
    # S153 (directriz 4.27): bloque común de las pestañas de personas
    # (Estado, Empresa, Grupo, Sección), sobre quien recibió el EPI.
    from panel.common_filters import common_people

    people, active, companies = common_people(request)
    qs = qs.filter(person__in=[person.pk for person in people])
    if search:
        qs = qs.filter(
            Q(person__first_surname__icontains=search)
            | Q(person__second_surname__icontains=search)
            | Q(person__given_name__icontains=search)
            | Q(epi__label__icontains=search),
        )
    if family_raw:
        qs = qs.filter(epi__family__in=checked_families)
    if date_from:
        qs = qs.filter(delivery_date__gte=date_from)
    if date_to:
        qs = qs.filter(delivery_date__lte=date_to)
    qs = qs.order_by(*_order_by(sort_keys))

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    return {
        "page": page,
        "search": search,
        "filter_active": active,
        "filter_company": companies,
        "families": families,
        "family_filter": family_raw,
        "checked_families": checked_families,
        "date_from": date_from,
        "date_to": date_to,
        "sort_columns": _sort_controls(sort_keys),
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(("-" if d else "") + k
                                 for k, d in sort_keys),
    }


class EpiTabFragmentView(CompanyUserRequiredMixin, View):
    """
    First load of the EPIs tab: fixed panel, deliveries list, batches
    and catalogue, with the filters the user left.

    ---

    Carga inicial de la pestaña EPIs: panel fijo, listado de entregas,
    lotes y catálogo, con los filtros que dejó el usuario.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        from panel.common_filters import person_filter_context

        ctx = person_filter_context(request)
        ctx.update(_list_context(request))
        ctx["catalog"] = EpiItemCatalog.objects.filter(
            is_active=True,
        ).order_by("family", "label")
        # H31 (S113): CRUD de lotes centralizado en esta pestaña.
        ctx["batch_templates"] = (
            EpiDeliveryBatchTemplate.objects.prefetch_related("items")
            .order_by("name")
        )
        return render(
            request, "panel/documentation_h30/_epi_pane.html", ctx,
        )


class EpiResultsFragmentView(CompanyUserRequiredMixin, View):
    """
    Search, filters, sort and pagination: only the list is repainted.

    ---

    Búsqueda, filtros, orden y paginación: solo se repinta el listado.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "panel/documentation_h30/_epi_results.html",
            _list_context(request),
        )
