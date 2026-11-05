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
from hr_calendar.clock_extras import (
    monthly_cap_seconds,
    signed_duration,
    split_by_month,
)
from hr_calendar.clock_report import REST_NOTE
from hr_calendar.clock_report import format_duration, reports_by_user
from hr_calendar.models import ClockCorrection
from hr_calendar.models import ClockEvent
from hr_calendar.models import ClockType
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
    "issues_only", "events", "section", "onboarding",
)
NO_SECTION = "none"
_MAX_SORT_KEYS = 4
# S145: cuatro años, como Fichajes del trabajador (atajo "Cuatro años").
_MAX_RANGE_DAYS = 4 * 366


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
    # S143: horas de más del intervalo, su cupo y la bolsa (sin cuenta,
    # al final).
    "overtime": lambda r: r.overtime_seconds,
    "quota": lambda r: r.quota_seconds,
    "bag": lambda r: r.bag_seconds,
    # S136 (Miguel Ángel: "ordenar por columnas"): todas ordenables.
    "entry": lambda r: _last_day_time(r, "clock_in"),
    "exit": lambda r: _last_day_time(r, "clock_out"),
    "place": _last_day_place,
    # S141: sección, si ficha y si recibe recordatorios.
    "section": lambda r: r.state.section_name.upper() or None,
    "clocks": lambda r: r.state.must_clock,
    "reminders": lambda r: r.state.reminders,
    # S144: alta en el fichaje (de lo que más falta a "Ya ficha").
    "onboarding": lambda r: (r.onboarding.rank,
                             r.onboarding.when.timestamp()
                             if r.onboarding.when else 0),
}
_COLUMNS = (
    ("person", "Apellidos, Nombre"),
    ("section", "Sección"),
    ("clocks", "Ficha"),
    ("reminders", "Recordatorios"),
    ("onboarding", "Alta en el fichaje"),
    ("events", "Fichajes"),
    ("issues", "Incidencias"),
    ("overtime", "Total de horas"),
    ("quota", "Cupo de horas"),
    ("bag", "Bolsa de horas"),
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
    day_excess = {}
    excess_seconds = 0
    excess_label = "0:00"
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

    def __init__(self, person, report, state=None, onboarding=None):
        from hr_calendar.clock_settings import WorkerClockState

        self.person = person
        self.report = report
        self.state = state or WorkerClockState()
        self.onboarding = onboarding
        self.label = _person_label(person)
        self.sort_name = self.label.upper()
        self.has_account = person.company_user_id is not None
        # S143: horas de más del intervalo, cupo (hasta el tope de cada
        # mes) y bolsa (el resto); None sin cuenta.
        self.overtime_seconds = self.quota_seconds = None
        self.bag_seconds = None
        self.overtime_label = self.quota_label = self.bag_label = ""


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
    from panel.personal_access import onboarding_states

    company = request.user.company_user.company
    reports = reports_by_user(
        company,
        [p.company_user_id for p in people if p.company_user_id],
        date_from, date_to,
    )
    states = worker_states(people)
    onboarding = onboarding_states(people)
    rows = [
        _Row(p, reports.get(p.company_user_id) or _EmptyReport(),
             states.get(p.pk), onboarding[p.pk])
        for p in people
    ]
    # S143 (Miguel Ángel): "tres columnas. Total de horas. [...] cupo de
    # horas con un máximo de 7 y bolsa de horas con el total de horas
    # menos 7". Del intervalo filtrado: lo trabajado de más; de eso, cada
    # mes hasta el tope es cupo y lo demás va a la bolsa.
    cap = monthly_cap_seconds(company)
    for row in rows:
        if row.has_account:
            months = split_by_month(
                getattr(row.report, "day_excess", None) or {}, cap)
            row.overtime_seconds = sum(m["excess"] for m in months)
            row.quota_seconds = sum(m["extra"] for m in months)
            row.bag_seconds = row.overtime_seconds - row.quota_seconds
            row.overtime_label = signed_duration(row.overtime_seconds)
            row.quota_label = signed_duration(row.quota_seconds)
            row.bag_label = signed_duration(row.bag_seconds)
    return rows


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


# S141: iconos que se pueden elegir para un tipo de fichaje (Bootstrap
# Icons, los del panel).
TYPE_ICONS = [
    ("bi-box-arrow-in-right", "Entrada"),
    ("bi-truck", "Camión"),
    ("bi-people", "Personas"),
    ("bi-star", "Estrella"),
    ("bi-arrow-bar-right", "Flecha"),
    ("bi-tools", "Herramientas"),
    ("bi-hourglass-split", "Espera"),
    ("bi-clock", "Reloj"),
    ("bi-cup-hot", "Pausa"),
    ("bi-briefcase", "Maletín"),
    ("bi-geo-alt", "Ubicación"),
    ("bi-telephone", "Teléfono"),
]


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
    from hr_calendar.clock_settings import section_types_map

    sections = _sections(company)
    clocks = section_clocks_map([s.pk for s in sections])
    by_types = section_types_map([s.pk for s in sections])
    from hr_calendar.clock_extras import monthly_cap_seconds

    cap = monthly_cap_seconds(company) // 60
    return {
        "reminders_on": reminders_enabled(company),
        "overtime_cap": "%d:%02d" % (cap // 60, cap % 60),
        "section_settings": [
            {"section": s, "clocks": clocks[s.pk],
             "uses_types": by_types[s.pk]} for s in sections
        ],
        # S141: tipos de fichaje (como en Sesame), gestionables.
        "clock_types": list(ClockType.objects.filter(company=company)),
        "type_icons": TYPE_ICONS,
    }


def _with_onboarding_filter(request, rows):
    """
    "Alta en el fichaje" filter (S144), literal checkboxes.
    ---
    Filtro "Alta en el fichaje" (S144): solo los estados marcados
    (panel/personal_access.py, onboarding_filter).
    """
    from panel.personal_access import onboarding_filter

    codes = onboarding_filter(_param(request, "onboarding"))
    if codes is None:
        return rows
    return [r for r in rows if r.onboarding.code in codes]


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
    from panel.personal_access import ONBOARDING_CHOICES, onboarding_filter

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
        _with_onboarding_filter(request, _with_section_filter(
            request, _with_events_filter(request, _with_issues_filter(
                request, _rows(request, people, date_from, date_to),
            )),
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
        "filter_onboarding": _param(request, "onboarding"),
        "onboarding_checked": onboarding_filter(
            _param(request, "onboarding")),
        "onboarding_choices": ONBOARDING_CHOICES,
        "total_label": format_duration(
            sum(r.report.total_seconds for r in rows),
        ),
        "overtime_cap": signed_duration(
            monthly_cap_seconds(request.user.company_user.company)),
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


class ClockOvertimeCapView(SupervisorAccessMixin, View):
    """
    POST: the company's monthly overtime cap.
    ---
    POST: el tope de horas extra al mes de la empresa (S143, Miguel
    Ángel: 7 horas); lo que pasa del tope va a horas acumuladas. Acepta
    "7", "7,5" o "7:30".
    """

    def post(self, request):
        from hr_calendar.models import ClockSettings
        from panel.views_clock_extras import _parse_minutes

        raw = (request.POST.get("hours") or "").strip()
        minutes = 0 if raw in ("0", "0:00") else _parse_minutes(raw)
        if minutes is None or minutes > 200 * 60:
            return _settings_response(
                request, "Escribe el tope en horas, por ejemplo 7 o 7:30.",
                error=True,
            )
        settings, _created = ClockSettings.objects.get_or_create(
            company=request.user.company_user.company,
        )
        settings.overtime_monthly_cap_minutes = minutes
        settings.updated_by = request.user.company_user
        settings.save()
        return _settings_response(
            request, "Tope de horas extra: %d:%02d h al mes." % (
                minutes // 60, minutes % 60),
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
        from hr_calendar.clock_settings import set_section_types
        from ivr_config.models import Section

        section = Section.objects.filter(
            pk=request.POST.get("section_id") or 0,
            company=request.user.company_user.company,
        ).first()
        if section is None:
            return _settings_response(request, "No existe esa sección.",
                                      error=True)
        # S141: el mismo ajuste sirve para "ficha por tipos".
        if "uses_types" in request.POST:
            value = request.POST.get("uses_types") == "1"
            set_section_types(section, value, request.user.company_user)
            return _settings_response(
                request, "%s %s." % (
                    section.name,
                    "ficha por tipos" if value
                    else "ficha con el botón único"),
            )
        clocks = request.POST.get("clocks") == "1"
        set_section_clocks(section, clocks, request.user.company_user)
        return _settings_response(
            request, "%s %s con la plataforma." % (
                section.name, "ficha" if clocks else "ya no ficha"),
        )


class ClockTypeSaveView(SupervisorAccessMixin, View):
    """
    POST: create or change one clock type (name, icon, counts, active,
    order).
    ---
    POST: crea o cambia un tipo de fichaje (H24, S141; Miguel Ángel:
    "poder gestionarla, para renombrarla, desactivarla, etcétera. Como
    en Sesame"). Los tipos no se borran: se desactivan, porque los
    fichajes ya hechos los conservan.
    """

    def post(self, request):
        company = request.user.company_user.company
        type_id = request.POST.get("type_id") or ""
        clock_type = None
        if type_id:
            clock_type = ClockType.objects.filter(
                pk=type_id if type_id.isdigit() else 0, company=company,
            ).first()
            if clock_type is None:
                return _settings_response(
                    request, "No existe ese tipo de fichaje.", error=True)
        name = " ".join((request.POST.get("name") or "").split())[:60]
        if not name:
            return _settings_response(
                request, "El tipo de fichaje necesita un nombre.",
                error=True)
        same_name = ClockType.objects.filter(
            company=company, name__iexact=name,
        )
        if clock_type is not None:
            same_name = same_name.exclude(pk=clock_type.pk)
        if same_name.exists():
            return _settings_response(
                request, "Ya hay un tipo de fichaje llamado %s." % name,
                error=True)
        active = request.POST.get("is_active") == "1"
        if clock_type is not None and clock_type.is_default and not active:
            return _settings_response(
                request, "%s es el tipo por defecto y no se puede "
                         "desactivar." % clock_type.name, error=True)
        icon = request.POST.get("icon") or ""
        if icon not in dict(TYPE_ICONS):
            icon = TYPE_ICONS[0][0]
        try:
            order = max(0, min(int(request.POST.get("order") or 0), 999))
        except ValueError:
            order = 0
        if clock_type is None:
            clock_type = ClockType(company=company)
        clock_type.name = name
        clock_type.icon = icon
        clock_type.counts_as_work = request.POST.get("counts_as_work") == "1"
        clock_type.is_active = active
        clock_type.order = order
        clock_type.updated_by = request.user.company_user
        created = clock_type.pk is None
        clock_type.save()
        return _settings_response(
            request, "Tipo de fichaje %s %s." % (
                clock_type.name, "creado" if created else "guardado"),
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
                     if correction and correction.old_pressed_at else None),
        # S144: pulsación añadida por el supervisor (no corrige otra).
        "is_added": bool(correction and correction.action
                         == ClockCorrection.Action.ADD),
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
    # S144: un fichaje añadido no tiene pulsación corregida; es del
    # trabajador por la nueva.
    return list(ClockCorrection.objects.filter(
        Q(event__company_user_id=company_user_id)
        | Q(event__isnull=True,
            replacement__company_user_id=company_user_id),
    ).filter(
        Q(old_pressed_at__gte=start, old_pressed_at__lt=end)
        | Q(new_pressed_at__gte=start, new_pressed_at__lt=end),
    ).select_related(
        "corrected_by__user", "old_clock_type", "new_clock_type",
    ).order_by("-corrected_at"))


def worker_detail_data(company, person, date_from, date_to):
    """
    Shifts, corrections history and report of one worker in a range.
    ---
    Las jornadas (con sus pulsaciones listas para la plantilla y las
    anuladas en su día), el historial de correcciones y el informe de un
    trabajador en un intervalo. Lo usan el detalle (modal de la ficha) y
    la página de fichajes del trabajador (S144).
    """
    report = _EmptyReport()
    corrections = []
    if person.company_user_id:
        report = reports_by_user(
            company, [person.company_user_id], date_from, date_to,
        ).get(person.company_user_id) or report
        corrections = _corrections_in_range(
            person.company_user_id, date_from, date_to,
        )
    from hr_calendar.clock_geocode import fill_missing

    fill_missing([
        e for s in report.shifts
        for e in [s.clock_in, s.clock_out] + list(s.changes)
    ])
    by_replacement = {
        c.replacement_id: c for c in corrections if c.replacement_id
    }
    from hr_calendar import clock_extras

    bases = clock_extras.company_bases(company)
    budget = clock_extras.new_budget()
    shifts = [{
        "day": s.day,
        "presses": [_press_view(s.clock_in, by_replacement),
                    _press_view(s.clock_out, by_replacement)],
        "duration": s.duration_label,
        "seconds": s.seconds,
        "issue": s.issue,
        "incidents": s.incidents,
        "expected_start": s.expected_start,
        "late_minutes": s.late_minutes,
        "expected_end": s.expected_end,
        "suggested_end": s.suggested_end,
        "early_minutes": s.early_minutes,
        "start_off": s.start_off_schedule,
        "end_off": s.end_off_schedule,
        # S141: cambios de tipo y horas por tipo (fichaje por tipos).
        "changes": [_press_view(c, by_replacement) for c in s.changes],
        "type_hours": _type_hours(s),
        # S144: día flexible tras una jornada con poco descanso.
        "rest_note": REST_NOTE if s.after_short_rest else "",
        # S144: las pulsaciones de la jornada, para anularla entera.
        "event_ids": ",".join(
            str(e.pk) for e in [s.clock_in] + list(s.changes)
            + [s.clock_out] if e is not None),
        "cancelled": [],
        # S144: pausas para comer (dietas) y tramos con vehículo propio.
        "meals": clock_extras.shift_meals(s, bases),
        "trips": clock_extras.shift_trips(s, budget),
    } for s in report.shifts]
    # S144: lo trabajado de más ese día, en la última jornada del día.
    excess = getattr(report, "day_excess", {}) or {}
    last_of_day = {}
    for shift in shifts:
        last_of_day[shift["day"]] = shift
    for day, seconds in excess.items():
        if day in last_of_day:
            last_of_day[day]["excess"] = format_duration(seconds)
    extras = {
        "excess_label": format_duration(sum(excess.values())),
        "km": clock_extras.km_total(
            [t for shift in shifts for t in shift["trips"]]),
        "meals": {
            kind: sum(1 for shift in shifts for m in shift["meals"]
                      if m["allowance"] and m["kind"] == kind)
            for kind in (clock_extras.LUNCH, clock_extras.DINNER)
        },
    }
    _attach_cancelled(shifts, corrections, date_from, date_to)
    history = [{
        "correction": c,
        "corrected_by": _user_label(c.corrected_by),
        "corrected_at": timezone.localtime(c.corrected_at),
        "old_time": (timezone.localtime(c.old_pressed_at)
                     if c.old_pressed_at else None),
        "new_time": (timezone.localtime(c.new_pressed_at)
                     if c.new_pressed_at else None),
        "is_cancel": c.action == ClockCorrection.Action.CANCEL,
    } for c in corrections]
    return {"report": report, "shifts": shifts, "history": history,
            "extras": extras}


def _render_detail(request, person, date_from, date_to, error="",
                   message="", form=None):
    """
    The day-by-day detail of one worker (also after a correction).
    ---
    El detalle día a día de un trabajador (también tras una
    corrección, con su mensaje o su error).
    """
    data = worker_detail_data(
        request.user.company_user.company, person, date_from, date_to,
    )
    report = data["report"]
    from panel.clock_calendar import calendar_range
    from panel.clock_calendar import calendar_years

    # S144: pestaña Calendario del detalle, siempre los cuatro años.
    cal_from, cal_to = calendar_range()
    cal_shifts = worker_detail_data(
        request.user.company_user.company, person, cal_from, cal_to,
    )["shifts"]
    return render(request, "panel/clock_events/_detail.html", {
        "calendar": calendar_years(cal_shifts),
        "person": person,
        "person_label": _person_label(person),
        "has_account": person.company_user_id is not None,
        "date_from": date_from,
        "date_to": date_to,
        "shifts": data["shifts"],
        "history": data["history"],
        "error": error,
        "message": message,
        "form": form or {},
        "kind_choices": ClockEvent.Kind.choices,
        "clock_types": list(ClockType.objects.filter(
            company=request.user.company_user.company,
        )),
        "total_label": report.total_label,
        "issues_count": report.incident_count,
        "punctuality_label": report.punctuality_label,
        "habitually_late": report.habitually_late,
        "early_label": report.early_label,
        "habitually_early": report.habitually_early,
    })


def _attach_cancelled(shifts, corrections, date_from, date_to):
    """
    Put the cancelled presses of each day with that day's shifts.
    ---
    S144 (Miguel Ángel, con captura: "no queda muy claro en la interfaz
    los días que están anulados"): las pulsaciones anuladas se ven en su
    día, tachadas, con quién, cuándo y por qué, debajo de la última
    jornada de ese día; un día con todo anulado sale como "Día
    anulado". No cuentan horas ni incidencias.
    """
    by_day = {}
    for correction in corrections:
        if (correction.action != ClockCorrection.Action.CANCEL
                or correction.old_pressed_at is None):
            continue
        when = timezone.localtime(correction.old_pressed_at)
        if not date_from <= when.date() <= date_to:
            continue
        by_day.setdefault(when.date(), []).append({
            "time": when,
            "kind": correction.get_old_kind_display(),
            "clock_type": correction.old_clock_type,
            "by": _user_label(correction.corrected_by),
            "at": timezone.localtime(correction.corrected_at),
            "reason": correction.reason,
        })
    last_of_day = {}
    for shift in shifts:
        last_of_day[shift["day"]] = shift
    for day, items in by_day.items():
        items.sort(key=lambda item: item["time"])
        if day in last_of_day:
            last_of_day[day]["cancelled"] = items
        else:
            shifts.append({"day": day, "only_cancelled": True,
                           "cancelled": items})
    shifts.sort(key=lambda shift: shift["day"])


def _type_hours(shift):
    """
    [{"name", "label", "counts"}] hours per clock type of one shift.
    ---
    Horas por tipo de fichaje de una jornada (S141), con si cuentan como
    jornada; [] si nadie eligió tipo.
    """
    counts = {
        clock_type.name: clock_type.counts_as_work
        for clock_type, _start, _end in shift.segments
        if clock_type is not None
    }
    return [{
        "name": name,
        "label": format_duration(seconds),
        "counts": counts.get(name, True),
    } for name, seconds in shift.type_seconds.items()]


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


def apply_correction(request, person):
    """
    Apply the posted correction to a worker's presses.
    ---
    Aplica la corrección enviada (S141/S144) y devuelve (mensaje, error,
    form): cambiar u anular una pulsación (event_id), anular varias de
    una vez (event_ids: una jornada entera o las jornadas marcadas) o
    añadir una (ADD). Lo usan el detalle (modal) y la página de
    fichajes del trabajador. La pulsación nunca se toca:
    hr_calendar.clock_corrections guarda quién, cuándo, antes, después
    y el motivo.
    """
    from django.db import transaction

    from hr_calendar.clock_corrections import ClockCorrectionError
    from hr_calendar.clock_corrections import add_event
    from hr_calendar.clock_corrections import correct_event

    form = {
        "event_id": request.POST.get("event_id", ""),
        "action": request.POST.get("action", ""),
        "new_kind": request.POST.get("new_kind", ""),
        "new_pressed_at": request.POST.get("new_pressed_at", ""),
        "new_clock_type": request.POST.get("new_clock_type", ""),
        "reason": request.POST.get("reason", ""),
        "label": request.POST.get("label", ""),
    }
    agent = request.META.get("HTTP_USER_AGENT", "")
    by = request.user.company_user
    new_pressed_at = parse_datetime(form["new_pressed_at"])
    if new_pressed_at is not None and timezone.is_naive(new_pressed_at):
        new_pressed_at = timezone.make_aware(new_pressed_at)
    # S144: anular varias pulsaciones (una jornada entera, o las
    # jornadas marcadas en la página del trabajador).
    event_ids = [
        int(pk) for pk in request.POST.get("event_ids", "").split(",")
        if pk.isdigit()
    ]
    if form["action"] == ClockCorrection.Action.CANCEL and event_ids:
        own = list(ClockEvent.objects.current().filter(
            pk__in=event_ids, company_user_id=person.company_user_id,
        ).values_list("pk", flat=True))
        if not own:
            return "", "Esas jornadas no son de este trabajador.", form
        try:
            with transaction.atomic():
                for pk in own:
                    correct_event(pk, by, ClockCorrection.Action.CANCEL,
                                  form["reason"], user_agent=agent)
        except ClockCorrectionError as exc:
            return "", str(exc), form
        return ("Anulados %d fichajes. Se ven tachados en su día y quedan "
                "en el historial." % len(own)), "", {}
    # S144: añadir una pulsación (partir un tramo, o la que falta).
    if form["action"] == ClockCorrection.Action.ADD:
        try:
            add_event(person.company_user, person, by, form["new_kind"],
                      new_pressed_at, form["reason"], user_agent=agent,
                      new_clock_type_id=form["new_clock_type"] or None)
        except ClockCorrectionError as exc:
            return "", str(exc), form
        return ("Fichaje añadido. Queda en el historial con quién lo "
                "añadió, cuándo y por qué."), "", {}
    event_id = form["event_id"]
    if (not event_id.isdigit() or person.company_user_id is None
            or not ClockEvent.objects.filter(
                pk=int(event_id),
                company_user_id=person.company_user_id,
            ).exists()):
        return "", "Ese fichaje no es de este trabajador.", form
    try:
        correction = correct_event(
            int(event_id), by, form["action"], form["reason"],
            new_kind=form["new_kind"], new_pressed_at=new_pressed_at,
            user_agent=agent,
            new_clock_type_id=form["new_clock_type"] or None,
        )
    except ClockCorrectionError as exc:
        return "", str(exc), form
    return ("%s guardada. El fichaje original se conserva en el "
            "historial." % correction.get_action_display()), "", {}


class ClockEventCorrectView(SupervisorAccessMixin, View):
    """
    POST: correct (change, cancel or add) presses of the worker.
    ---
    POST: corrige pulsaciones del trabajador (apply_correction) y
    devuelve el detalle actualizado.
    """

    def post(self, request, pk):
        person = _person_or_404(pk)
        date_from = _parse_date(request.POST.get("date_from"))
        date_to = _parse_date(request.POST.get("date_to"))
        if date_from is None or date_to is None:
            date_from, date_to = _date_range(request)
        message, error, form = apply_correction(request, person)
        return _render_detail(request, person, date_from, date_to,
                              error=error, message=message, form=form)


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


def _coordinates(event):
    """
    "lat, lon" of a press for the Excel, or "" without position.
    ---
    "lat, lon" de una pulsación para el Excel, o "" sin posición.
    """
    if event is None or event.latitude is None or event.longitude is None:
        return ""
    return "%s, %s" % (float(event.latitude), float(event.longitude))


def _letterhead(row, date_from, date_to, sheets):
    """
    One-worker Excel: name, DNI, company and period on top of each sheet.
    ---
    Excel de un solo trabajador (S141): en cada hoja se quitan las
    columnas DNI y nombre y se ponen arriba, como membrete, con la
    empresa y el periodo.
    """
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    person = row.person
    lines = [
        ("Registro de jornada", ""),
        ("Trabajador", row.label),
        ("DNI/NIE", person.dni),
        ("Empresa", person.employer_legal_name or ""),
        ("Periodo", "%s – %s" % (date_from.strftime("%d/%m/%Y"),
                                 date_to.strftime("%d/%m/%Y"))),
    ]
    for sheet, headers in sheets:
        sheet.delete_cols(1, 2)
        sheet.insert_rows(1, amount=len(lines) + 1)
        for index, (label, value) in enumerate(lines, start=1):
            sheet.cell(row=index, column=1, value=label).font = Font(
                bold=True, size=13 if index == 1 else 11,
            )
            if value:
                sheet.cell(row=index, column=2, value=value)
        sheet.freeze_panes = "A%d" % (len(lines) + 3)
        for index, (_header, width) in enumerate(headers[2:], start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        # La primera columna lleva también las etiquetas del membrete.
        sheet.column_dimensions["A"].width = max(
            sheet.column_dimensions["A"].width or 0, 20,
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
        from openpyxl.utils import get_column_letter

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
            # S144: los mismos filtros que el listado (la sección no se
            # aplicaba al exportar).
            rows = _with_onboarding_filter(request, _with_section_filter(
                request, _with_events_filter(request, _with_issues_filter(
                    request, _rows(request, people, date_from, date_to),
                )),
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
            ("Municipio salida", 26),
            # S141 (Miguel Ángel): el municipio, si hay, y además las
            # coordenadas.
            ("Coordenadas entrada", 22), ("Coordenadas salida", 22),
            ("Entrada según horario", 10),
            ("Minutos tarde", 9), ("Salida según horario", 10),
            ("Minutos antes", 9), ("Horas", 8), ("Incidencias", 60),
        ]
        # S141: horas de cada tipo de fichaje, al final (los que no
        # cuentan como jornada se marcan en la cabecera).
        type_names = [
            (t.name, t.counts_as_work) for t in ClockType.objects.filter(
                company=request.user.company_user.company,
            )
        ]
        day_headers += [
            ("%s%s" % (name, "" if counts else " (no cuenta)"), 14)
            for name, counts in type_names
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
            ("Tipo de fichaje", 20),
        ]
        presses.append([h for h, _w in press_headers])
        from hr_calendar.clock_geocode import fill_missing

        fill_missing(
            [e for row in rows for e in row.report.events], limit=80,
        )
        for row in rows:
            # S141 (Miguel Ángel): varias filas del mismo día llevan la
            # fecha solo en la primera.
            last_day = None
            for shift in row.report.shifts:
                early = shift.early_minutes
                shown_day = shift.day if shift.day != last_day else None
                last_day = shift.day
                days.append([
                    row.person.dni, row.label, shown_day,
                    _hour(shift.clock_in, "pressed_at", shift.day),
                    _hour(shift.clock_out, "pressed_at", shift.day),
                    _hour(shift.clock_in, "rounded_at", shift.day),
                    _hour(shift.clock_out, "rounded_at", shift.day),
                    (shift.clock_in.municipality or "")
                    if shift.clock_in else "",
                    (shift.clock_out.municipality or "")
                    if shift.clock_out else "",
                    _coordinates(shift.clock_in),
                    _coordinates(shift.clock_out),
                    shift.expected_start
                    if shift.late_minutes is not None else None,
                    max(shift.late_minutes, 0)
                    if shift.late_minutes is not None else None,
                    shift.expected_end if early is not None else None,
                    max(early, 0) if early is not None else None,
                    shift.duration_label, "; ".join(shift.incidents),
                ] + [
                    format_duration(shift.type_seconds[name])
                    if name in shift.type_seconds else ""
                    for name, _counts in type_names
                ])
            last_day = None
            for event in row.report.events:
                pressed = timezone.localtime(event.pressed_at)
                shown_day = (pressed.date() if pressed.date() != last_day
                             else None)
                last_day = pressed.date()
                presses.append([
                    row.person.dni, row.label, event.get_kind_display(),
                    shown_day,
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
                    event.clock_type.name if event.clock_type_id else "",
                ])
        # S141: historial de correcciones (quién, cuándo, antes, después
        # y motivo); el fichaje original no se borra nunca.
        fixes = book.create_sheet("Correcciones")
        fix_headers = [
            ("DNI", 12), ("Apellidos y nombre", 34), ("Corrección", 24),
            ("Tipo anterior", 10), ("Hora anterior", 17),
            ("Tipo nuevo", 10), ("Hora nueva", 17), ("Motivo", 60),
            ("Corregido por", 28), ("Fecha de la corrección", 17),
            ("Tipo de fichaje anterior", 20), ("Tipo de fichaje nuevo", 20),
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
                    timezone.localtime(fix.old_pressed_at).strftime(stamp)
                    if fix.old_pressed_at else "",
                    fix.get_new_kind_display(),
                    timezone.localtime(fix.new_pressed_at).strftime(stamp)
                    if fix.new_pressed_at else "",
                    fix.reason, _user_label(fix.corrected_by),
                    timezone.localtime(fix.corrected_at).strftime(stamp),
                    fix.old_clock_type.name if fix.old_clock_type else "",
                    fix.new_clock_type.name if fix.new_clock_type else "",
                ])
        for sheet, headers in ((days, day_headers), (presses, press_headers),
                               (fixes, fix_headers)):
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            sheet.freeze_panes = "A2"
            for index, (_header, width) in enumerate(headers):
                letter = get_column_letter(index + 1)
                sheet.column_dimensions[letter].width = width
        for cell in days["C"][1:]:
            cell.number_format = "DD/MM/YYYY"
        for column in ("D", "E", "F", "G", "L", "N"):
            for cell in days[column][1:]:
                cell.number_format = "HH:MM"
        for cell in presses["D"][1:]:
            cell.number_format = "DD/MM/YYYY"
        for cell in presses["E"][1:]:
            cell.number_format = "HH:MM:SS"
        for column in ("F", "G"):
            for cell in presses[column][1:]:
                cell.number_format = "HH:MM:SS" if column == "G" else "HH:MM"
        # S141 (Miguel Ángel): con un solo trabajador, sus datos van una
        # vez arriba, como membrete, y no en cada fila.
        people_in_book = {row.person.pk for row in rows}
        if len(people_in_book) == 1:
            _letterhead(
                rows[0], date_from, date_to,
                ((days, day_headers), (presses, press_headers),
                 (fixes, fix_headers)),
            )
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
