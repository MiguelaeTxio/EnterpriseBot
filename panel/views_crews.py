# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_crews.py
"""
S153. "Equipos" tab of the Documentation hub: which person is in which
vehicle (cost centre), in the panel's single list format (directives
4.24 and 4.27).

---

S153. Pestaña "Equipos" del hub de Documentación, junto a Personal y
Centros de gasto. Miguel Ángel: "un equipo es un vehículo y una
persona. Para que sepamos en todo momento quién está ocupando un
determinado vehículo". A mano de momento; una persona puede estar en
varios equipos a la vez. Listado: centro de gasto, código, matrícula,
persona y su teléfono ("importante para poder llamarlo"). Formato
único: fila fija (Buscar y filtrar, Grupos de selección por la persona,
Acciones), lista con "Selección actual" y exportación con plantilla.
"""
import datetime
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from fleet.models import Crew, MachineAsset
from panel.mixins import CompanyUserRequiredMixin, DocsUploadAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

logger = logging.getLogger(__name__)

SCREEN_KEY = "crews"
FILTER_KEYS = ("search", "state", "group", "sort")
_MAX_SORT_KEYS = 4
COLUMNS = (
    ("code", "Código"),
    ("machine", "Centro de gasto"),
    ("plate", "Matrícula"),
    ("person", "Persona"),
    ("phone", "Teléfono"),
    ("start", "Desde"),
    ("end", "Hasta"),
)
DEFAULT_SORT = "code,person"
STATE_CHOICES = (
    ("current", "Actuales"),
    ("ended", "Terminados"),
)


def _csv(request, key, default):
    if key in request.GET:
        return [v for v in request.GET.get(key, "").split(",") if v]
    return list(default)


def _parse_sort(raw):
    valid = {key for key, _label in COLUMNS}
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in valid and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in COLUMNS:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
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
    for key, desc in reversed(sort_keys):
        present = [r for r in rows if r["sort"].get(key) is not None]
        missing = [r for r in rows if r["sort"].get(key) is None]
        rows = sorted(present, key=lambda r: r["sort"][key],
                      reverse=desc) + missing
    return rows


def person_label(person):
    """
    "Surnames, Name".
    ---
    "Apellidos, Nombre" de la persona.
    """
    surnames = " ".join(p for p in (person.first_surname,
                                    person.second_surname) if p)
    return ("%s, %s" % (surnames, person.given_name)).strip(", ")


def _is_current(crew, today):
    """
    Current while it has no end date or it ends after today.
    ---
    Actual mientras no tenga fecha de fin o termine después de hoy:
    "Terminar" con fecha de hoy lo pasa ya a Terminados.
    """
    return crew.date_end is None or crew.date_end > today


def _rows(company):
    today = timezone.localdate()
    rows = []
    for crew in Crew.objects.filter(company=company).select_related(
            "machine", "person"):
        person = person_label(crew.person)
        phone = crew.person.phone or crew.person.phone_secondary
        machine = crew.machine.brand_model or crew.machine.type_name
        rows.append({
            "key": str(crew.pk), "crew": crew, "person": person,
            "person_id": crew.person_id, "phone": phone,
            "machine": machine,
            "current": _is_current(crew, today),
            "label": "%s · %s" % (crew.machine.code, person),
            "text": " ".join([crew.machine.code, crew.machine.plate,
                              machine, person, phone,
                              crew.notes]).lower(),
            "sort": {
                "code": crew.machine.code, "machine": machine.lower(),
                "plate": crew.machine.plate or None,
                "person": person.lower(), "phone": phone or None,
                "start": crew.date_start, "end": crew.date_end,
            },
        })
    return rows


def _list_context(request):
    from panel.person_groups import (
        PERSON_KIND, filter_by_group, group_filter_select_context,
    )

    company = request.user.company_user.company
    rows = _rows(company)
    states = _csv(request, "state", ["current"])
    rows = [r for r in rows if ("current" if r["current"] else "ended")
            in states]
    group = request.GET.get("group", "")
    if group:
        wanted = set(filter_by_group(
            PersonIdentity.objects.all(), group,
            PERSON_KIND).values_list("pk", flat=True))
        rows = [r for r in rows if r["person_id"] in wanted]
    for word in request.GET.get("search", "").strip().lower().split():
        rows = [r for r in rows if word in r["text"]]
    if request.GET.get("only_selected") == "1":
        wanted = set(request.GET.get("selected_ids", "").split(","))
        rows = [r for r in rows if r["key"] in wanted]
    raw_sort = request.GET.get("sort", DEFAULT_SORT)
    rows = _sort_rows(rows, _parse_sort(raw_sort))
    return {
        "rows": rows,
        "filter_search": request.GET.get("search", ""),
        "filter_state": states,
        "state_choices": STATE_CHOICES,
        **group_filter_select_context(request, PERSON_KIND),
        **_sort_controls(raw_sort),
    }


def _can_manage(company_user):
    """
    Same roles as DocsUploadAccessMixin (who can add or end crews).
    ---
    Mismos roles que DocsUploadAccessMixin: dan de alta y terminan.
    """
    from ivr_config.models import CompanyUser

    return company_user.role in (
        CompanyUser.ROLE_DOCS_SUPERVISOR, CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_ADMIN_SUPERVISOR,
    )


class CrewTabView(CompanyUserRequiredMixin, View):
    """
    GET: the whole "Equipos" tab.
    ---
    GET: la pestaña "Equipos" completa (fila fija, lista y selección).
    """

    def get(self, request):
        from panel.person_groups import group_filter_context

        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        cu = request.user.company_user
        saved = get_saved_state_key(cu, SCREEN_KEY, "selection", [])
        machines = MachineAsset.objects.filter(
            company=cu.company, is_active=True).order_by("code").only(
            "pk", "code", "plate", "brand_model", "type_name")
        people = PersonIdentity.objects.filter(
            company=cu.company, is_active_employee=True).order_by(
            "first_surname", "second_surname", "given_name").only(
            "pk", "first_surname", "second_surname", "given_name")
        return render(request, "panel/crews/_pane.html", {
            **_list_context(request),
            **group_filter_context(request),
            "saved_selection": saved if isinstance(saved, list) else [],
            "machines": machines,
            "people": people,
            "can_manage": _can_manage(cu),
            "today": timezone.localdate(),
        })


class CrewResultsView(CompanyUserRequiredMixin, View):
    """
    GET: the table only (filters and order).
    ---
    GET: solo la tabla (filtros y orden).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(request, "panel/crews/_table.html",
                      _list_context(request))


def _parse_date(raw):
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


class CrewCreateView(DocsUploadAccessMixin, View):
    """
    POST: new crews (one vehicle with one or more people).
    ---
    POST: alta de equipos: un centro de gasto (`machine`) con una o
    varias personas (`person`, repetido) desde `date_start`.
    """

    def post(self, request):
        cu = request.user.company_user
        machine = MachineAsset.objects.filter(
            company=cu.company, pk=request.POST.get("machine") or 0).first()
        people = list(PersonIdentity.objects.filter(
            company=cu.company,
            pk__in=[pk for pk in request.POST.getlist("person")
                    if pk.isdigit()]))
        date_start = _parse_date(request.POST.get("date_start"))
        if machine is None or not people or date_start is None:
            return JsonResponse(
                {"error": "Elige el centro de gasto, la persona y la "
                          "fecha."}, status=400)
        notes = (request.POST.get("notes") or "").strip()[:255]
        created = 0
        for person in people:
            already = Crew.objects.filter(
                machine=machine, person=person, date_end__isnull=True,
            ).exists()
            if already:
                continue
            Crew.objects.create(
                company=cu.company, machine=machine, person=person,
                date_start=date_start, notes=notes, created_by=cu)
            created += 1
        return JsonResponse({"created": created,
                             "skipped": len(people) - created})


class CrewMassView(DocsUploadAccessMixin, View):
    """
    POST: end (action=end, with date) or delete the marked crews.
    ---
    POST: termina (action=end, con `date_end`, por defecto hoy) o borra
    (action=delete) los equipos marcados. JSON {done}.
    """

    def post(self, request):
        cu = request.user.company_user
        ids = [pk for pk in request.POST.get("ids", "").split(",")
               if pk.isdigit()]
        crews = Crew.objects.filter(company=cu.company, pk__in=ids)
        action = request.POST.get("action", "")
        if action == "end":
            date_end = (_parse_date(request.POST.get("date_end"))
                        or timezone.localdate())
            done = crews.update(date_end=date_end)
        elif action == "delete":
            done = crews.count()
            logger.info("# [EQUIPOS] %s borra %d equipo(s)",
                        request.user.username, done)
            crews.delete()
        else:
            return JsonResponse({"error": "Acción desconocida."},
                                status=400)
        return JsonResponse({"done": done})


class CrewExportView(CompanyUserRequiredMixin, View):
    """
    POST: the marked crews to Excel, PDF or print (common template modal).
    ---
    POST: los equipos marcados (`selected`) a Excel, PDF o imprimir, con
    la plantilla elegida en el modal común.
    """

    def post(self, request):
        from openpyxl import Workbook

        from panel.export_formats import workbook_response
        from panel.screen_exports import columns_for, get_screen, write_sheet

        cu = request.user.company_user
        ids = {v for v in request.POST.getlist("selected") if v.isdigit()}
        rows = [r for r in _sort_rows(_rows(cu.company),
                                      _parse_sort(DEFAULT_SORT))
                if r["key"] in ids]
        if not rows:
            return HttpResponse("No hay ningún equipo seleccionado.",
                                status=400)
        columns = columns_for(request, get_screen("crews"))
        if columns is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "EQUIPOS"
        write_sheet(sheet, columns, rows)
        return workbook_response(request, workbook, "equipos")
