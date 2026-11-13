# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_doc_requests.py
"""
"Pedir documentos" tab of the Documentation hub (S148).

---

Pestaña "Pedir documentos" del hub de Documentación (S148). Miguel
Ángel: el pipeline para pedir documentación al trabajador por WhatsApp
solo estaba en Avisos > Pendientes, colgado de los avisos de cada
requisito; quiere "adecuar la vista al formato que tenemos actualmente
[...] que podamos elegir incluso sin necesidad de tener un determinado
requisito documental hecho, que podamos solicitarle un documento
cualquiera [...] y los filtros, etcétera, tal y como están todas las
vistas".

Mismo formato que Horarios y Fichajes (directriz 4.24): filtros de
siempre (búsqueda, Estado, Empresa, Selección) más Móvil y Pedidos,
grupos de selección, y a la derecha los documentos a pedir (cualquier
tipo de Personal) y las acciones sobre los marcados. Una fila por
trabajador con su móvil y lo que tiene pedido (el activo y la cola).
Pedir usa la misma cola por trabajador de siempre
(worker_request_service.create_requests): uno activo a la vez y, al
aceptarse, el siguiente. Mismos roles que pedir desde Avisos
(DOC_REQUEST_ROLES).
"""
from urllib.parse import quote

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views import View

from document_explorer.models import (
    DocumentTypeCatalog,
    PersonIdentity,
    WorkerDocumentRequest,
)
from document_explorer.person_phone_service import mobile_of
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_vacation_balance import (
    _filtered_people,
    _param,
    _person_label,
)

SCREEN_KEY = "doc_requests"
FILTER_KEYS = ("search", "active", "company", "sort", "mobile", "pending",
               "group", "section")
_MAX_SORT_KEYS = 4
_COLUMNS = (
    ("person", "Apellidos, Nombre"),
    ("dni", "DNI"),
    ("mobile", "Móvil de empresa"),
    ("active_request", "Pedido ahora"),
    ("queued", "En cola"),
)
_SORT_VALUES = {
    "person": lambda r: r.sort_name,
    "dni": lambda r: r.person.dni or None,
    "mobile": lambda r: r.mobile or None,
    "active_request": lambda r: (r.active.document_type.label.upper()
                                 if r.active else None),
    "queued": lambda r: len(r.queued) or None,
}


def _check_role(request):
    from panel.views_document_alerts import DOC_REQUEST_ROLES

    if request.user.company_user.role not in DOC_REQUEST_ROLES:
        raise PermissionDenied


class _Row:
    """
    One worker with their mobile and open requests.
    ---
    Un trabajador con su móvil de empresa y lo que tiene pedido: el
    pedido activo (enviado por WhatsApp) y la cola.
    """

    def __init__(self, person, requests):
        self.person = person
        self.label = _person_label(person)
        self.sort_name = self.label.upper()
        self.mobile = mobile_of(person) or ""
        self.active = next(
            (r for r in requests
             if r.status == WorkerDocumentRequest.STATUS_SENT), None)
        self.queued = [r for r in requests
                       if r.status == WorkerDocumentRequest.STATUS_QUEUED]
        self.queued_labels = ", ".join(
            r.document_type.label for r in self.queued)


def _parse_sort(raw):
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Header links, arrows and priorities (same rules as Horarios).
    ---
    Enlaces, flechas y prioridad de cada cabecera (mismas reglas que
    Horarios y Fichajes).
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in _COLUMNS:
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
                             for k, d in new_keys[:_MAX_SORT_KEYS]),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(("-" if d else "") + k
                                 for k, d in sort_keys),
    }


def _sort_rows(rows, sort_keys):
    rows = sorted(rows, key=lambda r: r.sort_name)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _rows(people):
    open_by_person = {}
    for item in WorkerDocumentRequest.objects.filter(
            person__in=people,
            status__in=WorkerDocumentRequest.OPEN_STATUSES,
    ).select_related("document_type").order_by("created_at", "pk"):
        open_by_person.setdefault(item.person_id, []).append(item)
    return [_Row(p, open_by_person.get(p.pk, [])) for p in people]


def _with_filters(request, rows):
    """
    "Móvil" and "Pedidos" filters.
    ---
    Filtros "Móvil" (con o sin móvil de empresa válido) y "Pedidos"
    (con algo pedido o en cola, o sin nada).
    """
    mobile = _param(request, "mobile")
    if mobile == "yes":
        rows = [r for r in rows if r.mobile]
    elif mobile == "no":
        rows = [r for r in rows if not r.mobile]
    pending = _param(request, "pending")
    if pending == "yes":
        rows = [r for r in rows if r.active or r.queued]
    elif pending == "no":
        rows = [r for r in rows if not (r.active or r.queued)]
    return rows


def _document_types():
    """
    Every active Personal document type, by family.
    ---
    Todos los tipos de documento de Personal activos (también los de
    ambos dominios), sin los subtipos, ordenados por familia y nombre;
    los marcados "lo aporta el trabajador" llevan la marca.
    """
    types = DocumentTypeCatalog.objects.filter(
        is_active=True, parent_type__isnull=True,
        domain__in=(DocumentTypeCatalog.DOMAIN_PERSONAL,
                    DocumentTypeCatalog.DOMAIN_BOTH),
    ).order_by("family", "label")
    families = dict(DocumentTypeCatalog.FAMILY_CHOICES)
    groups = []
    for doc_type in types:
        family = families.get(doc_type.family, doc_type.family or "Otros")
        if not groups or groups[-1]["family"] != family:
            groups.append({"family": family, "types": []})
        groups[-1]["types"].append(doc_type)
    return groups


def _list_context(request):
    """
    Context of the table: filtered workers with their requests, sorted.
    ---
    Contexto de la tabla: trabajadores filtrados con lo que tienen
    pedido, ordenados.
    """
    people, active, companies, search = _filtered_people(request)
    # S153 (4.27): Sección, del bloque común de filtros de personas.
    from panel.common_filters import filter_people_by_section

    people = filter_people_by_section(
        people, request.user.company_user.company,
        _param(request, "section"))
    if (request.GET.get("only_selected")
            or request.POST.get("_f_only_selected")) == "1":
        wanted = {
            int(pk) for pk in (
                request.GET.get("selected_ids")
                or request.POST.get("_f_selected_ids", "")
            ).split(",") if pk.isdigit()
        }
        people = list(PersonIdentity.objects.filter(pk__in=wanted))
    rows = _sort_rows(
        _with_filters(request, _rows(people)),
        _parse_sort(_param(request, "sort")),
    )
    return {
        "rows": rows,
        "filter_search": search,
        "filter_active": active,
        "filter_company": companies,
        "filter_mobile": _param(request, "mobile"),
        "filter_pending": _param(request, "pending"),
        **_sort_controls(_param(request, "sort")),
    }


class DocRequestsTabView(CompanyUserRequiredMixin, View):
    """
    GET: "Pedir documentos" tab.
    ---
    GET: pestaña "Pedir documentos" (panel fijo, listado y columna de
    selección); filtros, orden y selección persistidos por usuario
    (screen_key "doc_requests").
    """

    def get(self, request):
        from panel.person_groups import group_filter_context
        from panel.views_documentation_h30 import COMPANY_FILTER_CHOICES

        _check_role(request)
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        if not isinstance(saved_selection, list):
            saved_selection = []
        from panel.common_filters import person_filter_context

        return render(request, "panel/doc_requests/_pane.html", {
            # S153 (4.27): bloque común de filtros de personas.
            **person_filter_context(request),
            **_list_context(request),
            **group_filter_context(request),
            "type_groups": _document_types(),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "company_filter_choices": COMPANY_FILTER_CHOICES,
        })


class DocRequestsResultsView(CompanyUserRequiredMixin, View):
    """
    GET: table only.
    ---
    GET: solo la tabla (filtros y orden).
    """

    def get(self, request):
        _check_role(request)
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(request, "panel/doc_requests/_table.html",
                      _list_context(request))


def _table_response(request, message, error=False):
    response = HttpResponse(render_to_string(
        "panel/doc_requests/_table.html", _list_context(request),
        request=request,
    ))
    response["X-DocRequest-Message"] = quote(message)
    if error:
        response["X-DocRequest-Error"] = "1"
    return response


def _marked(request):
    company = request.user.company_user.company
    wanted = [int(pk) for pk in request.POST.getlist("selected")
              if pk.isdigit()]
    people = list(PersonIdentity.objects.filter(
        Q(company=company) | Q(company__isnull=True), pk__in=wanted,
    ))
    type_ids = [int(pk) for pk in request.POST.getlist("type_ids")
                if pk.isdigit()]
    types = list(DocumentTypeCatalog.objects.filter(
        pk__in=type_ids, is_active=True))
    return people, types


class DocRequestsSendView(CompanyUserRequiredMixin, View):
    """
    POST: ask the marked workers for the chosen documents over WhatsApp.
    ---
    POST: pide por WhatsApp a los marcados los documentos elegidos
    (cualquier tipo, any_type=True); se encolan y se envía el primero
    de cada trabajador que no tenga ya uno activo. El resumen (enviados,
    en cola, descartados y por qué) sale en el aviso de la pestaña.
    """

    def post(self, request):
        from document_explorer.worker_request_service import (
            create_requests,
        )

        _check_role(request)
        people, types = _marked(request)
        if not people or not types:
            return _table_response(
                request, "Marca algún trabajador y elige algún documento.",
                error=True)
        summary = create_requests(
            [(p.pk, t.pk) for p in people for t in types],
            request.user.company_user, any_type=True,
        )
        lines = ["Solicitudes nuevas: %d. Enviadas ahora por WhatsApp: %d."
                 % (summary["queued"], summary["sent"])]
        if summary["queued"] > summary["sent"]:
            lines.append("El resto queda en cola: se pide cuando el "
                         "trabajador entregue el anterior.")
        lines.extend("No enviado: %s" % e for e in summary["send_errors"])
        lines.extend("Descartado: %s" % e for e in summary["skipped"])
        return _table_response(
            request, "\n".join(lines),
            error=bool(summary["send_errors"]) or not summary["queued"])


class DocRequestsCancelView(CompanyUserRequiredMixin, View):
    """
    POST: cancel the open requests of the marked workers.
    ---
    POST: cancela lo pedido a los marcados: los documentos elegidos o,
    sin ninguno elegido, todo lo que tengan pedido o en cola. Si se
    cancela el activo, se envía el siguiente de su cola.
    """

    def post(self, request):
        from document_explorer.worker_request_service import (
            cancel_request,
        )

        _check_role(request)
        people, types = _marked(request)
        if not people:
            return _table_response(request, "Marca algún trabajador.",
                                   error=True)
        open_requests = WorkerDocumentRequest.objects.filter(
            person__in=people,
            status__in=WorkerDocumentRequest.OPEN_STATUSES,
        ).select_related("person")
        if types:
            open_requests = open_requests.filter(document_type__in=types)
        # Primero la cola, luego los activos: así no se envía un
        # siguiente que también se va a cancelar.
        items = sorted(open_requests, key=lambda r: (
            r.status == WorkerDocumentRequest.STATUS_SENT, r.pk))
        for item in items:
            cancel_request(item)
        return _table_response(
            request, "Cancelados %d pedidos." % len(items),
            error=not items)
