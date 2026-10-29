# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_worker_schedules.py
"""
"Horarios" tab of the Documentation hub (H24, S141).

Miguel Ángel (S141): a view to set each worker's workday schedule, by
sections, with exactly the same layout and the same filters as the
other Documentation tabs (directive 4.24). One row per worker with the
schedule that applies to them and where it comes from; the marked
workers get a schedule of their own, or lose it and go back to their
section's or the company's default one.

---

Pestaña "Horarios" del hub de Documentación (H24, S141).

Miguel Ángel (S141): una vista para establecer el horario de cada
trabajador, por secciones, con el mismo formato y los mismos filtros
que el resto de pestañas de Documentación (directriz 4.24). Una fila
por trabajador con el horario que le toca y de dónde le viene; a los
marcados se les pone un horario propio o se les quita, y vuelven al de
su sección o al de por defecto de la empresa.

Mismos permisos que Fichajes y que Horarios de jornada
(SupervisorAccessMixin).
"""
from urllib.parse import quote

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views import View

from document_explorer.models import PersonIdentity
from panel.mixins import SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_vacation_balance import (
    _filtered_people,
    _param,
    _person_label,
)

SCREEN_KEY = "worker_schedules"
FILTER_KEYS = ("search", "active", "company", "sort", "section", "schedule")
NO_SECTION = "none"
NO_SCHEDULE = "none"
_MAX_SORT_KEYS = 4

ORIGIN_LABELS = {
    "intensive": "Jornada intensiva (verano)",
    "own": "Propio",
    "section": "De la sección",
    "default": "Por defecto de la empresa",
    "none": "Sin horario",
}

_SORT_VALUES = {
    "person": lambda r: r.sort_name,
    "section": lambda r: r.state.section_name.upper() or None,
    "schedule": lambda r: r.schedule.label.upper() if r.schedule else None,
    "origin": lambda r: r.origin_label,
    "morning": lambda r: r.morning_label or None,
    "afternoon": lambda r: r.afternoon_label or None,
}
_COLUMNS = (
    ("person", "Apellidos, Nombre"),
    ("section", "Sección"),
    ("schedule", "Horario"),
    ("origin", "De dónde le viene"),
    ("morning", "Mañana"),
    ("afternoon", "Tarde"),
)


def _hm(value):
    return value.strftime("%H:%M") if value else ""


class _Row:
    """
    One worker with the schedule that applies to them.
    ---
    Un trabajador con el horario que le toca y de dónde le viene.
    """

    def __init__(self, person, state, schedule, origin, origin_section):
        self.person = person
        self.state = state
        self.schedule = schedule
        self.origin = origin
        self.label = _person_label(person)
        self.sort_name = self.label.upper()
        self.has_account = person.company_user_id is not None
        label = ORIGIN_LABELS.get(origin, "")
        if origin == "section" and origin_section is not None:
            label = "De la sección %s" % origin_section.name
        self.origin_label = label
        self.varies = bool(schedule and schedule.varies_by_day)
        self.days_title = ""
        if schedule is None:
            self.morning_label = self.afternoon_label = ""
        elif self.varies:
            self.morning_label = self.afternoon_label = "Según el día"
            self.days_title = _days_title(schedule)
        else:
            self.morning_label = "%s–%s" % (
                _hm(schedule.start_time_morning),
                _hm(schedule.end_time_morning),
            )
            split = (not schedule.is_intensive
                     and schedule.start_time_afternoon is not None)
            self.afternoon_label = (
                "%s–%s" % (_hm(schedule.start_time_afternoon),
                           _hm(schedule.end_time_afternoon))
                if split else ""
            )


def _days_title(schedule):
    """
    "Lun 08:00–13:00 / 15:00–18:00 · ..." of a schedule by day.
    ---
    Resumen de un horario distinto según el día, para el título de la
    celda.
    """
    from panel.views_workorders import _schedule_day_rows

    parts = []
    for row in _schedule_day_rows(schedule):
        if not row["works"]:
            parts.append("%s: no se trabaja" % row["name"][:3])
            continue
        text = "%s %s–%s" % (row["name"][:3], row["sm"], row["em"])
        if row["sa"]:
            text += " / %s–%s" % (row["sa"], row["ea"])
        parts.append(text)
    return " · ".join(parts)


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
    Header links, arrows and priorities (same rules as Fichajes).
    ---
    Enlaces, flechas y prioridad de cada cabecera (mismas reglas que
    Fichajes y Vacaciones).
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
                (k, d) for k, d in sort_keys if k != key
            ]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(
                ("-" if d else "") + k
                for k, d in new_keys[:_MAX_SORT_KEYS]
            ),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(
            ("-" if d else "") + k for k, d in sort_keys
        ),
    }


def _sort_rows(rows, sort_keys):
    rows = sorted(rows, key=lambda r: r.sort_name)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _rows(company, people):
    from hr_calendar.clock_settings import worker_states
    from panel.views_operator import resolve_person_schedule

    states = worker_states(people)
    rows = []
    for person in people:
        # S141: el horario va en el trabajador; no hace falta usuario
        # del panel.
        schedule, (origin, section) = resolve_person_schedule(
            person, company,
        )
        rows.append(_Row(person, states[person.pk], schedule, origin,
                         section))
    return rows


def _with_filters(request, rows):
    """
    "Sección" (in force today) and "Horario" filters.
    ---
    Filtros "Sección" (la vigente hoy, o "Sin sección") y "Horario" (el
    que le toca, o "Sin horario").
    """
    section = _param(request, "section")
    if section == NO_SECTION:
        rows = [r for r in rows if r.state.section is None]
    elif section.isdigit():
        rows = [
            r for r in rows
            if r.state.section is not None
            and r.state.section.pk == int(section)
        ]
    schedule = _param(request, "schedule")
    if schedule == NO_SCHEDULE:
        rows = [r for r in rows if r.schedule is None]
    elif schedule.isdigit():
        rows = [
            r for r in rows
            if r.schedule is not None and r.schedule.pk == int(schedule)
        ]
    return rows


def _schedules(company):
    from ivr_config.models import WorkdaySchedule

    return list(WorkdaySchedule.objects.filter(
        company=company,
    ).order_by("label"))


def _sections(company):
    from ivr_config.models import Section

    return list(Section.objects.filter(company=company).order_by("name"))


def _list_context(request):
    """
    Context of the table: filtered workers with their schedule, sorted.
    ---
    Contexto de la tabla: trabajadores filtrados con su horario,
    ordenados.
    """
    company = request.user.company_user.company
    people, active, companies, search = _filtered_people(request)
    if (request.GET.get("only_selected")
            or request.POST.get("_f_only_selected")) == "1":
        wanted = {
            int(pk) for pk in (
                request.GET.get("selected_ids")
                or request.POST.get("_f_selected_ids", "")
            ).split(",") if pk.isdigit()
        }
        people = list(PersonIdentity.objects.select_related(
            "company_user__workday_schedule",
        ).filter(pk__in=wanted))
    rows = _sort_rows(
        _with_filters(request, _rows(company, people)),
        _parse_sort(_param(request, "sort")),
    )
    return {
        "rows": rows,
        "filter_search": search,
        "filter_active": active,
        "filter_company": companies,
        "filter_section": _param(request, "section"),
        "filter_schedule": _param(request, "schedule"),
        **_sort_controls(_param(request, "sort")),
    }


class WorkerSchedulesTabView(SupervisorAccessMixin, View):
    """
    GET: "Horarios" tab (fixed panel, list, selection column).
    ---
    GET: pestaña "Horarios" (panel fijo, listado y columna de
    selección), filtros/orden/selección persistidos por usuario
    (screen_key "worker_schedules").
    """

    def get(self, request):
        from panel.views_documentation_h30 import COMPANY_FILTER_CHOICES

        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        if not isinstance(saved_selection, list):
            saved_selection = []
        company = request.user.company_user.company
        return render(request, "panel/worker_schedules/_pane.html", {
            **_list_context(request),
            "sections": _sections(company),
            "schedules": _schedules(company),
            "no_section": NO_SECTION,
            "no_schedule": NO_SCHEDULE,
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "company_filter_choices": COMPANY_FILTER_CHOICES,
        })


class WorkerSchedulesResultsView(SupervisorAccessMixin, View):
    """
    GET: table only.
    ---
    GET: solo la tabla (filtros y orden).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "panel/worker_schedules/_table.html",
            _list_context(request),
        )


def _table_response(request, message, error=False):
    """
    The table with the filters that were on screen, and a message.
    ---
    La tabla con los filtros que se veían y un mensaje en cabecera para
    el aviso flotante de la pestaña.
    """
    response = HttpResponse(render_to_string(
        "panel/worker_schedules/_table.html", _list_context(request),
        request=request,
    ))
    response["X-Schedule-Message"] = quote(message)
    if error:
        response["X-Schedule-Error"] = "1"
    return response


class WorkerSchedulesAssignView(SupervisorAccessMixin, View):
    """
    POST: give the marked workers a schedule of their own, or remove it.
    ---
    POST: pone a los trabajadores marcados un horario propio
    (schedule_id) o se lo quita (schedule_id vacío): entonces les toca
    el de su sección o el de por defecto de la empresa. S141 (Miguel
    Ángel): el horario va en el trabajador, así que no hace falta que
    tenga usuario del panel (chóferes, gruistas y administrativos solo
    fichan).
    """

    def post(self, request):
        from hr_calendar.clock_settings import set_worker_schedule
        from ivr_config.models import WorkdaySchedule

        company = request.user.company_user.company
        people = _marked_people(request, company)
        if not people:
            return _table_response(request, "Marca algún trabajador.",
                                   error=True)
        raw = request.POST.get("schedule_id", "")
        schedule = None
        if raw:
            schedule = WorkdaySchedule.objects.filter(
                pk=raw if raw.isdigit() else 0, company=company,
            ).first()
            if schedule is None:
                return _table_response(request, "No existe ese horario.",
                                       error=True)
        count = set_worker_schedule(people, schedule,
                                    request.user.company_user)
        if schedule is not None:
            message = "Horario %s puesto a %d trabajador(es)." % (
                schedule.label, count)
        else:
            message = ("Horario propio quitado a %d trabajador(es): les "
                       "toca el de su sección o el de por defecto."
                       % count)
        return _table_response(request, message)


class WorkerSchedulesSectionView(SupervisorAccessMixin, View):
    """
    POST: assign a section from a date to the marked workers.
    ---
    POST: asigna a los marcados una sección desde una fecha (hoy por
    defecto), la misma asignación que en Vacaciones
    (hr_calendar.balance.assign_section). Miguel Ángel (S141): sin
    sección no se puede trabajar por secciones.
    """

    def post(self, request):
        from django.utils import timezone

        from hr_calendar.balance import assign_section
        from ivr_config.models import Section
        from panel.views_vacation_balance import _parse_date

        company = request.user.company_user.company
        people = _marked_people(request, company)
        raw = request.POST.get("section_id", "")
        section = Section.objects.filter(
            pk=raw if raw.isdigit() else 0, company=company,
        ).first()
        valid_from = (_parse_date(request.POST.get("valid_from"))
                      or timezone.localdate())
        if section is None or not people:
            return _table_response(
                request, "Elige la sección y marca algún trabajador.",
                error=True,
            )
        assign_section(people, section, valid_from,
                       request.user.company_user)
        return _table_response(
            request, "Sección %s desde el %s para %d trabajador(es)." % (
                section.name, valid_from.strftime("%d/%m/%Y"),
                len(people)),
        )


def _marked_people(request, company):
    wanted = [
        int(pk) for pk in request.POST.getlist("selected")
        if pk.isdigit()
    ]
    return list(PersonIdentity.objects.filter(
        Q(company=company) | Q(company__isnull=True), pk__in=wanted,
    ).select_related("company_user"))
