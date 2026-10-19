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

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar.clock_report import format_duration, reports_by_user
from hr_calendar.models import ClockEvent
from panel.mixins import SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_vacation_balance import (
    _filtered_people,
    _param,
    _parse_date,
    _person_label,
)

SCREEN_KEY = "clock_events"
FILTER_KEYS = (
    "search", "active", "company", "date_from", "date_to", "sort",
    "issues_only",
)
_MAX_SORT_KEYS = 4
_MAX_RANGE_DAYS = 366

_SORT_VALUES = {
    "person": lambda r: r.sort_name,
    "events": lambda r: len(r.report.events),
    "last": lambda r: (r.report.last_event.pressed_at
                       if r.report.last_event else None),
    "issues": lambda r: r.report.incident_count,
}
_COLUMNS = (
    ("person", "Apellidos, Nombre"),
    ("events", "Fichajes"),
    ("issues", "Incidencias"),
    ("last", "Último día"),
)


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

    def __init__(self, person, report):
        self.person = person
        self.report = report
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
    company = request.user.company_user.company
    reports = reports_by_user(
        company,
        [p.company_user_id for p in people if p.company_user_id],
        date_from, date_to,
    )
    return [
        _Row(p, reports.get(p.company_user_id) or _EmptyReport())
        for p in people
    ]


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
        _with_issues_filter(
            request, _rows(request, people, date_from, date_to),
        ),
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
        return render(request, "panel/clock_events/_pane.html", {
            **_list_context(request),
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


def _maps_url(event):
    if event is None or event.latitude is None:
        return ""
    return "https://www.google.com/maps?q=%s,%s" % (
        event.latitude, event.longitude,
    )


def _press_view(event):
    """
    One press ready for the template (local time, delay, map link).
    ---
    Una pulsación lista para el template (hora local, retraso, enlace
    al mapa).
    """
    if event is None:
        return None
    delay = event.delay_seconds
    is_manual = event.sent_by == ClockEvent.SentBy.MANUAL
    return {
        "event": event,
        # S130: fichaje manual por olvido; su "retraso" es cuándo se
        # apuntó, no un envío tardío.
        "is_manual": is_manual,
        "time": timezone.localtime(event.pressed_at),
        "rounded": (timezone.localtime(event.rounded_at)
                    if event.rounded_at else None),
        "received": timezone.localtime(event.received_at),
        "is_late": delay > 300 and not is_manual,
        "delay_label": format_duration(delay) if delay > 300 else "",
        "maps_url": _maps_url(event),
        "accuracy": event.accuracy_m,
        "municipality": event.municipality or "",
        "lat": float(event.latitude) if event.latitude is not None else None,
        "lon": float(event.longitude) if event.longitude is not None else None,
    }


class ClockEventsDetailView(SupervisorAccessMixin, View):
    """
    GET: day-by-day shifts of one worker in the range.
    ---
    GET: jornadas día a día de un trabajador en el intervalo.
    """

    def get(self, request, pk):
        person = PersonIdentity.objects.select_related(
            "company_user",
        ).filter(pk=pk).first()
        if person is None:
            raise Http404
        date_from, date_to = _date_range(request)
        report = _EmptyReport()
        if person.company_user_id:
            report = reports_by_user(
                request.user.company_user.company,
                [person.company_user_id], date_from, date_to,
            ).get(person.company_user_id) or report
        from hr_calendar.clock_geocode import fill_missing

        fill_missing([
            e for s in report.shifts for e in (s.clock_in, s.clock_out)
        ])
        shifts = [{
            "day": s.day,
            "presses": [_press_view(s.clock_in), _press_view(s.clock_out)],
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
        return render(request, "panel/clock_events/_detail.html", {
            "person": person,
            "person_label": _person_label(person),
            "has_account": person.company_user_id is not None,
            "date_from": date_from,
            "date_to": date_to,
            "shifts": shifts,
            "total_label": report.total_label,
            "issues_count": report.incident_count,
            "punctuality_label": report.punctuality_label,
            "habitually_late": report.habitually_late,
            "early_label": report.early_label,
            "habitually_early": report.habitually_early,
        })


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
    parte y la del horario) y hoja "Pulsaciones" (cada
    pulsación tal como llegó, con su posición).
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
            rows = _with_issues_filter(
                request, _rows(request, people, date_from, date_to),
            )
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
        for sheet, headers in ((days, day_headers), (presses, press_headers)):
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
