# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_clock_events.py
"""
"Fichajes" tab of the Documentation hub (H24, S129, roadmap point 3):
the supervisors' view of the clock-in records. Same layout as the
Personal and Vacaciones tabs (directive 4.24): one row per worker with
the presses, hours and incidents of a date range; the name opens the
day-by-day detail (presses, send delay, GPS position); the marked
workers -- or all the filtered ones -- export to Excel. Records are
read-only here: art. 34.9 ET requires keeping them four years.

The tab carries GPS positions, so it is limited to ADMIN, SUPERVISOR
and WORKSHOPBOSS (SupervisorAccessMixin), unlike the read-only tabs.

---

Pestaña "Fichajes" del hub de Documentación (H24, S129, punto 3 de la
hoja de ruta): la vista de los supervisores sobre el registro de
jornada. Misma disposición que Personal y Vacaciones (directriz 4.24):
una fila por trabajador con las pulsaciones, horas e incidencias de un
intervalo de fechas; el nombre abre el detalle día a día (pulsaciones,
retraso del envío, posición GPS); los marcados -- o todos los
filtrados -- se exportan a Excel. Aquí los registros solo se consultan:
el art. 34.9 ET obliga a conservarlos cuatro años.

La pestaña lleva posiciones GPS, así que queda para ADMIN, SUPERVISOR
y WORKSHOPBOSS (SupervisorAccessMixin), a diferencia de las pestañas de
solo lectura.
"""
import datetime
import io
import os

from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.clock_report import format_duration, reports_by_user
from hr_calendar.models import ClockCorrection
from hr_calendar.models import ClockEvent
from panel.mixins import SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_vacation_balance import (
    _csv_param,
    _filtered_people,
    _param,
    _parse_date,
    _person_label,
)

SCREEN_KEY = "clock_events"
FILTER_KEYS = (
    "search", "active", "company", "date_from", "date_to", "sort",
    "issues_only", "events", "section",
)
NO_SECTION = "none"
_MAX_SORT_KEYS = 4
_MAX_RANGE_DAYS = 366


def _last_day_time(row, field):
    """
    Local time of day of the last day's IN or OUT, or None.
    ---
    Hora (local) de la entrada o la salida del último día, o None.
    S136: para ordenar también por Entrada y Salida.
    """
    last = row.report.last_day
    if not last or last[field] is None:
        return None
    return timezone.localtime(last[field].pressed_at).time()


def _last_day_place(row):
    last = row.report.last_day
    if not last:
        return None
    return (last["last"].municipality or "").upper() or None


_SORT_VALUES = {
    "person": lambda r: r.sort_name,
    "events": lambda r: len(r.report.events),
    "last": lambda r: (r.report.last_event.pressed_at
                       if r.report.last_event else None),
    "issues": lambda r: r.report.incident_count,
    # S136 (Miguel Ángel: "ordenar por columnas"): todas ordenables.
    "entry": lambda r: _last_day_time(r, "clock_in"),
    "exit": lambda r: _last_day_time(r, "clock_out"),
    "place": _last_day_place,
    # S141: sección, si ficha y si recibe recordatorios.
    "section": lambda r: r.state.section_name.upper() or None,
    "clocks": lambda r: r.state.must_clock,
    "reminders": lambda r: r.state.reminders,
}
_COLUMNS = (
    ("person", "Apellidos, Nombre"),
    ("section", "Sección"),
    ("clocks", "Ficha"),
    ("reminders", "Recordatorios"),
    ("events", "Fichajes"),
    ("issues", "Incidencias"),
    ("last", "Último día"),
    ("entry", "Entrada"),
    ("exit", "Salida"),
    ("place", "Municipio"),
)
_EVENTS_CHOICES = ("with", "without")


class _EmptyReport:
    shifts = ()
    events = ()
    issues = ()
    incident_count = 0
    late_events = ()
    timed_arrivals = ()
    late_arrivals = ()
    punctuality_label = ""
    habitually_late = False
    timed_departures = ()
    early_departures = ()
    early_label = ""
    habitually_early = False
    last_day = None
    last_event = None
    total_seconds = 0
    total_label = "0:00"


def _date_range(request):
    """
    (date_from, date_to) of the request; default: this month so far.
    ---
    (desde, hasta) de la petición; por defecto, lo que va de mes. Un
    intervalo al revés se da la vuelta y uno de más de un año se corta.
    """
    today = timezone.localdate()
    date_from = _parse_date(_param(request, "date_from")) or today.replace(
        day=1,
    )
    date_to = _parse_date(_param(request, "date_to")) or today
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days >= _MAX_RANGE_DAYS:
        date_from = date_to - datetime.timedelta(days=_MAX_RANGE_DAYS - 1)
    return date_from, date_to


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
    Header links, arrows and priorities (same rules as Vacaciones).
    ---
    Enlaces, flechas y prioridad de cada cabecera (mismas reglas que
    Vacaciones y Centros de gasto).
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


class _Row:
    """
    One worker of the list with the report of the range.
    ---
    Un trabajador del listado con el informe del intervalo.
    """

    def __init__(self, person, report, state=None):
        from hr_calendar.clock_settings import WorkerClockState

        self.person = person
        self.report = report
        self.state = state or WorkerClockState()
        self.label = _person_label(person)
        self.sort_name = self.label.upper()
        self.has_account = person.company_user_id is not None


def _sort_rows(rows, sort_keys):
    rows = sorted(rows, key=lambda r: r.sort_name)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _rows(request, people, date_from, date_to):
    from hr_calendar.clock_settings import worker_states

    company = request.user.company_user.company
    reports = reports_by_user(
        company,
        [p.company_user_id for p in people if p.company_user_id],
        date_from, date_to,
    )
    states = worker_states(people)
    return [
        _Row(p, reports.get(p.company_user_id) or _EmptyReport(),
             states.get(p.pk))
        for p in people
    ]


def _with_section_filter(request, rows):
    """
    "Sección" filter (S141): the section in force today, or none.
    ---
    Filtro "Sección" (S141, Miguel Ángel: "poder discriminar por
    secciones"): la sección vigente hoy, o "Sin sección".
    """
    section = _param(request, "section")
    if section == NO_SECTION:
        return [r for r in rows if r.state.section is None]
    if section.isdigit():
        return [
            r for r in rows
            if r.state.section is not None
            and r.state.section.pk == int(section)
        ]
    return rows


def _sections(company):
    from ivr_config.models import Section

    return list(Section.objects.filter(company=company).order_by("name"))


def _settings_context(company):
    """
    The clock-in settings block: company switch and sections.
    ---
    El bloque de ajustes de fichaje: el permiso general de envío y las
    secciones con si fichan con la plataforma.
    """
    from hr_calendar.clock_settings import reminders_enabled
    from hr_calendar.clock_settings import section_clocks_map

    sections = _sections(company)
    clocks = section_clocks_map([s.pk for s in sections])
    return {
        "reminders_on": reminders_enabled(company),
        "section_settings": [
            {"section": s, "clocks": clocks[s.pk]} for s in sections
        ],
    }


def _with_issues_filter(request, rows):
    """
    "Solo con incidencias" (Miguel Ángel, S129: "un filtro para
    seleccionar los trabajadores con incidencias y poder exportarlos a
    Excel"): only the workers with an incident in the dates.
    ---
    "Solo con incidencias": solo los trabajadores con alguna
    incidencia en las fechas elegidas.
    """
    if _param(request, "issues_only") != "1":
        return rows
    return [r for r in rows if r.report.issues]


def _with_events_filter(request, rows):
    """
    "Con fichajes" / "Sin fichajes" (S136, Miguel Ángel: "filtro de
    trabajadores con/sin fichajes"), checkboxes with literal meaning:
    both = everyone, none = nobody (directive 4.24).
    ---
    Casillas "Con fichajes" y "Sin fichajes" en las fechas elegidas,
    con semántica literal: las dos = todos, ninguna = nadie.
    """
    wanted = _csv_param(request, "events", _EVENTS_CHOICES)
    return [
        r for r in rows
        if ("with" if r.report.events else "without") in wanted
    ]


def _list_context(request):
    """
    Context of the table: filtered workers with their report, sorted.
    ---
    Contexto de la tabla: trabajadores filtrados con su informe,
    ordenados.
    """
    date_from, date_to = _date_range(request)
    people, active, companies, search = _filtered_people(request)
    if request.GET.get("only_selected") == "1":
        wanted = {
            int(pk) for pk in request.GET.get("selected_ids", "").split(",")
            if pk.isdigit()
        }
        people = list(PersonIdentity.objects.select_related(
            "company_user",
        ).filter(pk__in=wanted))
    rows = _sort_rows(
        _with_section_filter(request, _with_events_filter(
            request, _with_issues_filter(
                request, _rows(request, people, date_from, date_to),
            ),
        )),
        _parse_sort(_param(request, "sort")),
    )
    # H24 (S129): municipio del último fichaje de cada fila.
    from hr_calendar.clock_geocode import fill_missing

    fill_missing([
        r.report.last_day["last"] for r in rows if r.report.last_day
    ])
    return {
        "rows": rows,
        "filter_search": search,
        "filter_active": active,
        "filter_company": companies,
        "date_from": date_from,
        "date_to": date_to,
        "filter_issues_only": _param(request, "issues_only") == "1",
        "filter_events": _csv_param(request, "events", _EVENTS_CHOICES),
        "filter_section": _param(request, "section"),
        "total_label": format_duration(
            sum(r.report.total_seconds for r in rows),
        ),
        **_sort_controls(_param(request, "sort")),
    }


class ClockEventsTabView(SupervisorAccessMixin, View):
    """
    GET: "Fichajes" tab (fixed panel, list, selection column).
    ---
    GET: pestaña "Fichajes" (panel fijo, listado y columna de
    selección), filtros/orden/selección persistidos por usuario
    (screen_key "clock_events").
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
        return render(request, "panel/clock_events/_pane.html", {
            **_list_context(request),
            **_settings_context(company),
            "sections": _sections(company),
            "no_section": NO_SECTION,
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            # H24 (S129): mapa del fichaje con la API de Google Maps
            # (misma clave que los presupuestos).
            "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
            "google_maps_map_id": os.environ.get("GOOGLE_MAPS_MAP_ID", ""),
            "company_filter_choices": COMPANY_FILTER_CHOICES,
        })


class ClockEventsResultsView(SupervisorAccessMixin, View):
    """
    GET: table only.
    ---
    GET: solo la tabla (filtros, fechas, orden).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "panel/clock_events/_table.html",
            _list_context(request),
        )


def _settings_response(request, message, error=False):
    """
    Table plus the settings block (out of band), with a message.
    ---
    La tabla y, fuera de banda, el bloque de ajustes de fichaje, con un
    mensaje en cabecera que pinta el aviso flotante de la pestaña.
    """
    from urllib.parse import quote

    from django.template.loader import render_to_string

    company = request.user.company_user.company
    html = render_to_string(
        "panel/clock_events/_table.html", _list_context(request),
        request=request,
    ) + render_to_string(
        "panel/clock_events/_settings.html",
        {**_settings_context(company), "oob": True}, request=request,
    )
    response = HttpResponse(html)
    response["X-Clock-Message"] = quote(message)
    if error:
        response["X-Clock-Error"] = "1"
    return response


class ClockWorkerSettingsView(SupervisorAccessMixin, View):
    """
    POST: set "ficha" / "recordatorios" for the marked workers.
    ---
    POST: a los trabajadores marcados, "ficha" / "no ficha" o "con
    recordatorios" / "sin recordatorios" (H24, S141). Devuelve la tabla
    con los filtros que se veían.
    """

    ACTIONS = {
        "clocks_on": ("clocks", True, "obligados a fichar"),
        "clocks_off": ("clocks", False, "sin obligación de fichar"),
        "reminders_on": ("reminders", True, "con recordatorios"),
        "reminders_off": ("reminders", False, "sin recordatorios"),
    }

    def post(self, request):
        from hr_calendar.clock_settings import set_worker_flag

        action = self.ACTIONS.get(request.POST.get("action", ""))
        company = request.user.company_user.company
        wanted = [
            int(pk) for pk in request.POST.getlist("selected")
            if pk.isdigit()
        ]
        ids = list(PersonIdentity.objects.filter(
            Q(company=company) | Q(company__isnull=True), pk__in=wanted,
        ).values_list("pk", flat=True))
        if action is None or not ids:
            return _settings_response(
                request, "Marca algún trabajador y elige la acción.",
                error=True,
            )
        field, value, label = action
        count = set_worker_flag(ids, field, value,
                                request.user.company_user)
        return _settings_response(
            request, "%d trabajador(es) %s." % (count, label),
        )


class ClockRemindersSwitchView(SupervisorAccessMixin, View):
    """
    POST: switch the company's reminders on or off.
    ---
    POST: activa o desactiva el envío de recordatorios de fichaje de la
    empresa (H24, S141).
    """

    def post(self, request):
        from hr_calendar.clock_settings import set_reminders_enabled

        enabled = request.POST.get("enabled") == "1"
        set_reminders_enabled(request.user.company_user.company, enabled,
                              request.user.company_user)
        return _settings_response(
            request,
            "Envío de recordatorios %s." % (
                "activado" if enabled else "desactivado"),
        )


class ClockSectionSettingView(SupervisorAccessMixin, View):
    """
    POST: put a section in or out of clocking with the platform.
    ---
    POST: pone o quita una sección del fichaje con la plataforma (H24,
    S141; Plataformas ficha con Prologic).
    """

    def post(self, request):
        from hr_calendar.clock_settings import set_section_clocks
        from ivr_config.models import Section

        section = Section.objects.filter(
            pk=request.POST.get("section_id") or 0,
            company=request.user.company_user.company,
        ).first()
        if section is None:
            return _settings_response(request, "No existe esa sección.",
                                      error=True)
        clocks = request.POST.get("clocks") == "1"
        set_section_clocks(section, clocks, request.user.company_user)
        return _settings_response(
            request, "%s %s con la plataforma." % (
                section.name, "ficha" if clocks else "ya no ficha"),
        )


def _maps_url(event):
    if event is None or event.latitude is None:
        return ""
    return "https://www.google.com/maps?q=%s,%s" % (
        event.latitude, event.longitude,
    )


def _user_label(company_user):
    """
    Name of a panel user for the history.
    ---
    Nombre de un usuario del panel para el historial.
    """
    user = company_user.user
    return user.get_full_name() or user.username


def _press_view(event, corrections_by_replacement=None):
    """
    One press ready for the template (local time, delay, map link).
    ---
    Una pulsación lista para el template (hora local, retraso, enlace
    al mapa). S141: si es la pulsación nueva de una corrección, la
    corrección (quién, cuándo, valor anterior y motivo).
    """
    if event is None:
        return None
    delay = event.delay_seconds
    is_manual = event.sent_by == ClockEvent.SentBy.MANUAL
    is_correction = event.sent_by == ClockEvent.SentBy.CORRECTION
    correction = (corrections_by_replacement or {}).get(event.pk)
    local = timezone.localtime(event.pressed_at)
    return {
        "event": event,
        # S130: fichaje manual por olvido; su "retraso" es cuándo se
        # apuntó, no un envío tardío.
        "is_manual": is_manual,
        "correction": correction,
        "corrected_by": (_user_label(correction.corrected_by)
                         if correction else ""),
        "old_time": (timezone.localtime(correction.old_pressed_at)
                     if correction else None),
        "input_value": local.strftime("%Y-%m-%dT%H:%M"),
        "time": local,
        "rounded": (timezone.localtime(event.rounded_at)
                    if event.rounded_at else None),
        "received": timezone.localtime(event.received_at),
        "is_late": delay > 300 and not (is_manual or is_correction),
        "delay_label": format_duration(delay) if delay > 300 else "",
        "maps_url": _maps_url(event),
        "accuracy": event.accuracy_m,
        "municipality": event.municipality or "",
        "lat": float(event.latitude) if event.latitude is not None else None,
        "lon": float(event.longitude) if event.longitude is not None else None,
    }


def _corrections_in_range(company_user_id, date_from, date_to):
    """
    Corrections of a user's presses whose old or new time falls in the
    range, newest first.
    ---
    Correcciones de las pulsaciones de un usuario cuya hora anterior o
    nueva cae en el intervalo, de la más reciente a la más antigua.
    """
    from hr_calendar.clock_report import _range_bounds

    start, end = _range_bounds(date_from, date_to)
    return list(ClockCorrection.objects.filter(
        event__company_user_id=company_user_id,
    ).filter(
        Q(old_pressed_at__gte=start, old_pressed_at__lt=end)
        | Q(new_pressed_at__gte=start, new_pressed_at__lt=end),
    ).select_related("corrected_by__user").order_by("-corrected_at"))


def _render_detail(request, person, date_from, date_to, error="",
                   message="", form=None):
    """
    The day-by-day detail of one worker (also after a correction).
    ---
    El detalle día a día de un trabajador (también tras una
    corrección, con su mensaje o su error).
    """
    report = _EmptyReport()
    corrections = []
    if person.company_user_id:
        report = reports_by_user(
            request.user.company_user.company,
            [person.company_user_id], date_from, date_to,
        ).get(person.company_user_id) or report
        corrections = _corrections_in_range(
            person.company_user_id, date_from, date_to,
        )
    from hr_calendar.clock_geocode import fill_missing

    fill_missing([
        e for s in report.shifts for e in (s.clock_in, s.clock_out)
    ])
    by_replacement = {
        c.replacement_id: c for c in corrections if c.replacement_id
    }
    shifts = [{
        "day": s.day,
        "presses": [_press_view(s.clock_in, by_replacement),
                    _press_view(s.clock_out, by_replacement)],
        "duration": s.duration_label,
        "issue": s.issue,
        "incidents": s.incidents,
        "expected_start": s.expected_start,
        "late_minutes": s.late_minutes,
        "expected_end": s.expected_end,
        "early_minutes": s.early_minutes,
        "start_off": s.start_off_schedule,
        "end_off": s.end_off_schedule,
    } for s in report.shifts]
    history = [{
        "correction": c,
        "corrected_by": _user_label(c.corrected_by),
        "corrected_at": timezone.localtime(c.corrected_at),
        "old_time": timezone.localtime(c.old_pressed_at),
        "new_time": (timezone.localtime(c.new_pressed_at)
                     if c.new_pressed_at else None),
        "is_cancel": c.action == ClockCorrection.Action.CANCEL,
    } for c in corrections]
    return render(request, "panel/clock_events/_detail.html", {
        "person": person,
        "person_label": _person_label(person),
        "has_account": person.company_user_id is not None,
        "date_from": date_from,
        "date_to": date_to,
        "shifts": shifts,
        "history": history,
        "error": error,
        "message": message,
        "form": form or {},
        "kind_choices": ClockEvent.Kind.choices,
        "total_label": report.total_label,
        "issues_count": report.incident_count,
        "punctuality_label": report.punctuality_label,
        "habitually_late": report.habitually_late,
        "early_label": report.early_label,
        "habitually_early": report.habitually_early,
    })


def _person_or_404(pk):
    person = PersonIdentity.objects.select_related(
        "company_user",
    ).filter(pk=pk).first()
    if person is None:
        raise Http404
    return person


class ClockEventsDetailView(SupervisorAccessMixin, View):
    """
    GET: day-by-day shifts of one worker in the range.
    ---
    GET: jornadas día a día de un trabajador en el intervalo.
    """

    def get(self, request, pk):
        date_from, date_to = _date_range(request)
        return _render_detail(request, _person_or_404(pk), date_from,
                              date_to)


class ClockEventCorrectView(SupervisorAccessMixin, View):
    """
    POST: correct (change or cancel) one press of the worker.
    ---
    POST: corrige (cambia o anula) una pulsación del trabajador (H24,
    S141). La pulsación no se toca: hr_calendar.clock_corrections
    guarda la corrección con quién, cuándo, el valor anterior, el nuevo
    y el motivo. Devuelve el detalle del trabajador actualizado.
    """

    def post(self, request, pk):
        from hr_calendar.clock_corrections import ClockCorrectionError
        from hr_calendar.clock_corrections import correct_event

        person = _person_or_404(pk)
        date_from = _parse_date(request.POST.get("date_from"))
        date_to = _parse_date(request.POST.get("date_to"))
        if date_from is None or date_to is None:
            date_from, date_to = _date_range(request)
        form = {
            "event_id": request.POST.get("event_id", ""),
            "action": request.POST.get("action", ""),
            "new_kind": request.POST.get("new_kind", ""),
            "new_pressed_at": request.POST.get("new_pressed_at", ""),
            "reason": request.POST.get("reason", ""),
            "label": request.POST.get("label", ""),
        }
        new_pressed_at = parse_datetime(form["new_pressed_at"])
        if new_pressed_at is not None and timezone.is_naive(new_pressed_at):
            new_pressed_at = timezone.make_aware(new_pressed_at)
        event_id = form["event_id"]
        if (not event_id.isdigit() or person.company_user_id is None
                or not ClockEvent.objects.filter(
                    pk=int(event_id),
                    company_user_id=person.company_user_id,
                ).exists()):
            return _render_detail(
                request, person, date_from, date_to,
                error="Ese fichaje no es de este trabajador.", form=form,
            )
        try:
            correction = correct_event(
                int(event_id), request.user.company_user, form["action"],
                form["reason"], new_kind=form["new_kind"],
                new_pressed_at=new_pressed_at,
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ClockCorrectionError as exc:
            return _render_detail(request, person, date_from, date_to,
                                  error=str(exc), form=form)
        return _render_detail(
            request, person, date_from, date_to,
            message="%s guardada. El fichaje original se conserva en el "
                    "historial." % correction.get_action_display(),
        )


def _hour(event, field_name, day, seconds=False):
    """
    The time of a press field for the Excel: a time when it is on the
    row's day; otherwise text with its date ("06:00 (18/10)"), so the
    date is written once per row without hiding a change of day.
    ---
    La hora de un campo de la pulsación para el Excel: una hora si cae
    en el día de la fila; si no, texto con su fecha.
    """
    if event is None or getattr(event, field_name) is None:
        return None
    value = timezone.localtime(getattr(event, field_name))
    if value.date() == day:
        return value.time().replace(
            microsecond=0, second=value.second if seconds else 0,
        )
    return value.strftime(
        "%H:%M:%S (%d/%m)" if seconds else "%H:%M (%d/%m)",
    )


class ClockEventsExportView(SupervisorAccessMixin, View):
    """
    GET: Excel of the range for the marked workers (or all filtered).
    ---
    GET: Excel del intervalo para los marcados (o todos los filtrados):
    hoja "Jornadas" (una fila por jornada, con la hora real, la del
    parte y la del horario), hoja "Pulsaciones" (cada
    pulsación tal como llegó, con su posición) y, desde S141, hoja
    "Correcciones" (el historial de modificaciones del registro).
    """

    def get(self, request):
        from openpyxl import Workbook
        from openpyxl.styles import Font

        date_from, date_to = _date_range(request)
        wanted = [
            int(pk) for pk in request.GET.get("selected_ids", "").split(",")
            if pk.isdigit()
        ]
        if wanted:
            people = list(PersonIdentity.objects.select_related(
                "company_user",
            ).filter(pk__in=wanted))
            rows = _rows(request, people, date_from, date_to)
        else:
            people, _a, _c, _s = _filtered_people(request)
            rows = _with_events_filter(request, _with_issues_filter(
                request, _rows(request, people, date_from, date_to),
            ))
        rows = sorted(rows, key=lambda r: r.sort_name)
        book = Workbook()
        days = book.active
        days.title = "Jornadas"
        # S129 (Miguel Ángel): la fecha una sola vez; el resto, horas.
        day_headers = [
            ("DNI", 12), ("Apellidos y nombre", 34), ("Fecha", 12),
            ("Entrada", 9), ("Salida", 9), ("Entrada (parte)", 9),
            ("Salida (parte)", 9), ("Municipio entrada", 26),
            ("Municipio salida", 26), ("Entrada según horario", 10),
            ("Minutos tarde", 9), ("Salida según horario", 10),
            ("Minutos antes", 9), ("Horas", 8), ("Incidencias", 60),
        ]
        days.append([h for h, _w in day_headers])
        presses = book.create_sheet("Pulsaciones")
        press_headers = [
            ("DNI", 12), ("Apellidos y nombre", 34), ("Tipo", 9),
            ("Fecha", 12), ("Hora de la pulsación", 10),
            ("Hora redondeada (parte)", 10), ("Hora de llegada", 16),
            ("Retraso (min)", 9), ("Municipio", 28), ("Latitud", 11),
            ("Longitud", 11), ("Precisión (m)", 9), ("Sin GPS porque", 24),
            ("Cómo se envió", 34), ("Navegador", 40),
        ]
        presses.append([h for h, _w in press_headers])
        from hr_calendar.clock_geocode import fill_missing

        fill_missing(
            [e for row in rows for e in row.report.events], limit=80,
        )
        for row in rows:
            for shift in row.report.shifts:
                early = shift.early_minutes
                days.append([
                    row.person.dni, row.label, shift.day,
                    _hour(shift.clock_in, "pressed_at", shift.day),
                    _hour(shift.clock_out, "pressed_at", shift.day),
                    _hour(shift.clock_in, "rounded_at", shift.day),
                    _hour(shift.clock_out, "rounded_at", shift.day),
                    (shift.clock_in.municipality or "")
                    if shift.clock_in else "",
                    (shift.clock_out.municipality or "")
                    if shift.clock_out else "",
                    shift.expected_start
                    if shift.late_minutes is not None else None,
                    max(shift.late_minutes, 0)
                    if shift.late_minutes is not None else None,
                    shift.expected_end if early is not None else None,
                    max(early, 0) if early is not None else None,
                    shift.duration_label, "; ".join(shift.incidents),
                ])
            for event in row.report.events:
                pressed = timezone.localtime(event.pressed_at)
                presses.append([
                    row.person.dni, row.label, event.get_kind_display(),
                    pressed.date(),
                    pressed.time().replace(microsecond=0),
                    _hour(event, "rounded_at", pressed.date()),
                    _hour(event, "received_at", pressed.date(), True),
                    round(event.delay_seconds / 60),
                    event.municipality or "",
                    float(event.latitude) if event.latitude is not None
                    else None,
                    float(event.longitude) if event.longitude is not None
                    else None,
                    event.accuracy_m, event.gps_error,
                    event.get_sent_by_display(), event.user_agent,
                ])
        # S141: historial de correcciones (quién, cuándo, antes, después
        # y motivo); el fichaje original no se borra nunca.
        fixes = book.create_sheet("Correcciones")
        fix_headers = [
            ("DNI", 12), ("Apellidos y nombre", 34), ("Corrección", 24),
            ("Tipo anterior", 10), ("Hora anterior", 17),
            ("Tipo nuevo", 10), ("Hora nueva", 17), ("Motivo", 60),
            ("Corregido por", 28), ("Fecha de la corrección", 17),
        ]
        fixes.append([h for h, _w in fix_headers])
        stamp = "%d/%m/%Y %H:%M"
        for row in rows:
            if not row.person.company_user_id:
                continue
            for fix in reversed(_corrections_in_range(
                    row.person.company_user_id, date_from, date_to)):
                fixes.append([
                    row.person.dni, row.label, fix.get_action_display(),
                    fix.get_old_kind_display(),
                    timezone.localtime(fix.old_pressed_at).strftime(stamp),
                    fix.get_new_kind_display(),
                    timezone.localtime(fix.new_pressed_at).strftime(stamp)
                    if fix.new_pressed_at else "",
                    fix.reason, _user_label(fix.corrected_by),
                    timezone.localtime(fix.corrected_at).strftime(stamp),
                ])
        for sheet, headers in ((days, day_headers), (presses, press_headers),
                               (fixes, fix_headers)):
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            sheet.freeze_panes = "A2"
            for index, (_header, width) in enumerate(headers):
                letter = chr(ord("A") + index)
                sheet.column_dimensions[letter].width = width
        for cell in days["C"][1:]:
            cell.number_format = "DD/MM/YYYY"
        for column in ("D", "E", "F", "G", "J", "L"):
            for cell in days[column][1:]:
                cell.number_format = "HH:MM"
        for cell in presses["D"][1:]:
            cell.number_format = "DD/MM/YYYY"
        for cell in presses["E"][1:]:
            cell.number_format = "HH:MM:SS"
        for column in ("F", "G"):
            for cell in presses[column][1:]:
                cell.number_format = "HH:MM:SS" if column == "G" else "HH:MM"
        buffer = io.BytesIO()
        book.save(buffer)
        filename = "fichajes_%s_%s.xlsx" % (
            date_from.strftime("%Y%m%d"), date_to.strftime("%Y%m%d"),
        )
        response = HttpResponse(
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            'attachment; filename="%s"' % filename
        )
        return response
