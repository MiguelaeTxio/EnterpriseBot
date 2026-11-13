# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_clock_worker.py
"""
Clock-in page of one worker (H24, S144).

---

Página de fichajes de un trabajador (H24, S144). Miguel Ángel: "vamos
a imaginarnos que han pasado 2 años [...] tenemos que enriquecer la
vista con filtros [...] en lugar de un modal, instaurar un nuevo tipo
de vista con el mismo formato que tenemos las vistas [...] y que se
pueda acceder a esa vista también desde la ficha de personal [...]
filtrar por fechas, poder ver incidencias, poder ordenar, poder
listar, poder editar los fichajes, crear fichajes nuevos, anular".

Formato de listado de la directriz 4.24: panel fijo (buscar y filtrar,
acciones por categoría), lista con scroll propio y cabecera fija, orden
múltiple, casillas con selección que sobrevive a filtros y orden,
visor "Selección actual", menú de tres puntos por fila, pantalla
completa (4.26), navegación persistida (4.15) y "Volver" (4.25).

Una fila por jornada (y por día con todo anulado). Las correcciones son
las mismas que en el detalle (views_clock_events.apply_correction): la
pulsación nunca se toca, queda quién, cuándo y por qué.
"""
import datetime
import json

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from hr_calendar.models import ClockEvent
from hr_calendar.models import ClockType
from panel.mixins import SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_vacation_balance import _param, _parse_date, _person_label

SCREEN_KEY = "clock_worker"
FILTER_KEYS = (
    "date_from", "date_to", "status", "corrected", "clock_type", "sort",
    "view",
)
# S144 (Miguel Ángel): "separar las vistas de las jornadas con el tema
# de las correcciones" y "una vista de tipo calendario".
VIEW_SHIFTS = "jornadas"
VIEW_CALENDAR = "calendario"
VIEW_CORRECTIONS = "correcciones"
VIEW_CHOICES = (
    (VIEW_SHIFTS, "Jornadas", "bi-list-ul"),
    (VIEW_CALENDAR, "Calendario", "bi-calendar3"),
    (VIEW_CORRECTIONS, "Correcciones", "bi-clock-history"),
)
STATUS_OK = "ok"
STATUS_ISSUES = "issues"
STATUS_CANCELLED = "cancelled"
# S143: incidencias visadas (amarillo) y jornada en curso de hoy (verde).
STATUS_REVIEWED = "reviewed"
STATUS_OPEN = "open"
STATUS_CHOICES = (
    (STATUS_OPEN, "En curso"),
    (STATUS_OK, "Correctas"),
    (STATUS_REVIEWED, "Incidencias visadas"),
    (STATUS_ISSUES, "Incidencias sin visar"),
    (STATUS_CANCELLED, "Anuladas"),
)
_STATUS_LABELS = dict(STATUS_CHOICES)
_STATUS_BADGES = {
    STATUS_OK: "success", STATUS_ISSUES: "danger",
    STATUS_CANCELLED: "secondary", STATUS_REVIEWED: "warning",
    STATUS_OPEN: "success",
}
_COLUMNS = (
    ("day", "Día"),
    ("entry", "Entrada"),
    ("exit", "Salida"),
    ("hours", "Horas"),
    ("types", "Tipos"),
    ("incidents", "Incidencias"),
    ("status", "Estado"),
)
_SORT_VALUES = {
    "day": lambda r: r["day"],
    "entry": lambda r: r["entry_time"],
    "exit": lambda r: r["exit_time"],
    "hours": lambda r: r["seconds"],
    "types": lambda r: r["types_label"] or None,
    "incidents": lambda r: len(r["incidents"]),
    "status": lambda r: r["status_label"],
}
_MAX_SORT_KEYS = 4
# Los registros se conservan cuatro años (art. 34.9 ET).
_MAX_RANGE_DAYS = 4 * 366


def _date_range(request):
    """
    (date_from, date_to); default this month so far, at most 4 years.
    ---
    (desde, hasta); por defecto lo que va de mes. Hasta cuatro años de
    una vez: lo que se conservan los registros (art. 34.9 ET).
    """
    today = timezone.localdate()
    date_from = _parse_date(_param(request, "date_from")) or today.replace(
        day=1)
    date_to = _parse_date(_param(request, "date_to")) or today
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days >= _MAX_RANGE_DAYS:
        date_from = date_to - datetime.timedelta(days=_MAX_RANGE_DAYS - 1)
    return date_from, date_to


def _statuses(request):
    raw = _param(request, "status")
    if raw == "none":
        return []
    chosen = [c for c in raw.split(",") if c in _STATUS_LABELS]
    # S143: un filtro guardado de antes no conoce los estados nuevos:
    # "Con incidencias" trae las visadas y "Correctas" la de hoy en curso.
    if STATUS_REVIEWED not in chosen and STATUS_OPEN not in chosen:
        if STATUS_ISSUES in chosen:
            chosen.append(STATUS_REVIEWED)
        if STATUS_OK in chosen:
            chosen.append(STATUS_OPEN)
    return chosen if raw else list(_STATUS_LABELS)


def _parse_sort(raw):
    keys, seen = [], set()
    for token in (raw or "").split(","):
        key = token.strip().lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.strip().startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Header links with arrow and priority (same rules as Fichajes).
    ---
    Cabeceras con flecha y prioridad: clic promueve la columna a
    principal, clic en la principal invierte su sentido, hasta 4.
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in _COLUMNS:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            new_keys = [(key, (not desc) if idx == 0 else desc)] + [
                (k, d) for k, d in sort_keys if k != key]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
        else:
            new_keys = [(key, False)] + sort_keys
            arrow, priority = "", ""
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
    # Sin orden elegido, el día más reciente arriba. S143: una jornada
    # sin entrada (solo la salida) va con la hora 00:00; antes era un 0
    # y comparar una hora con un número daba error 500 en cuanto el
    # mismo día tenía otra jornada con entrada.
    rows = sorted(
        rows,
        key=lambda r: (r["day"], r["entry_time"] or datetime.time.min),
        reverse=not sort_keys,
    )
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _row(shift):
    """
    One row of the page from a shift of worker_detail_data.
    ---
    Una fila de la página: una jornada, o un día con todo anulado.
    """
    entry, exit_ = (shift.get("presses") or [None, None])
    changes = shift.get("changes") or []
    if shift.get("only_cancelled"):
        status = STATUS_CANCELLED
    elif shift.get("incidents"):
        status = (STATUS_REVIEWED if shift.get("reviewed")
                  else STATUS_ISSUES)
    elif shift.get("in_progress"):
        status = STATUS_OPEN
    else:
        status = STATUS_OK
    presses = [p for p in [entry] + changes + [exit_] if p]
    type_names = {p["event"].clock_type.name for p in presses
                  if p["event"].clock_type_id}
    corrected = bool(shift.get("cancelled")) or any(
        p["correction"] for p in presses)
    first = (entry or exit_ or {}).get("event")
    key = ("s%d" % first.pk if first is not None
           else "c%s" % shift["day"].isoformat())
    return {
        **shift,
        "key": key,
        # S149: las pulsaciones vigentes para «Editar la jornada».
        "edit_presses": [{
            "id": p["event"].pk, "kind": p["event"].kind,
            "at": p["input_value"],
            "type": p["event"].clock_type_id,
        } for p in presses if not shift.get("only_cancelled")],
        "entry": entry,
        "exit": exit_,
        "changes": changes,
        "entry_time": entry["time"].time() if entry else None,
        "exit_time": exit_["time"] if exit_ else None,
        "seconds": shift.get("seconds") or 0,
        "types_label": " · ".join(
            "%s %s" % (t["name"], t["label"])
            for t in shift.get("type_hours") or []),
        "type_names": type_names,
        "incidents": shift.get("incidents") or [],
        "status": status,
        "status_label": _STATUS_LABELS[status],
        "status_badge": _STATUS_BADGES[status],
        "corrected": corrected,
        "label": "%s%s" % (
            shift["day"].strftime("%d/%m/%Y"),
            " %s" % entry["time"].strftime("%H:%M") if entry else ""),
    }


_STATUS_WEIGHT = {STATUS_ISSUES: 4, STATUS_REVIEWED: 3, STATUS_OPEN: 2,
                  STATUS_OK: 1, STATUS_CANCELLED: 0}
GAP_COLOR = ("repeating-linear-gradient(45deg,#f8d7da,#f8d7da 3px,"
             "#fff 3px,#fff 6px)")
# Una salida y vuelta a entrar en menos de esto es casi seguro un error.
QUICK_GAP_SECONDS = 5 * 60


def _group_by_day(rows):
    """
    One row per day: its shifts ("parts") together.
    ---
    S143 (Miguel Ángel): "habría que agruparlos por jornada [...] que no
    aparezcan las dos fechas y que esté englobado en el mismo". Una fila
    por día con sus jornadas dentro (parts, por hora de entrada), las
    horas sumadas, las incidencias de todas, el estado más grave, la
    barra de todo el día con los ratos fuera (salida y vuelta a entrar)
    rayados y avisados, sobre todo si es en pocos minutos (casi siempre
    una salida pulsada por error).
    """
    from hr_calendar.clock_report import format_duration

    order, by_day = [], {}
    for row in rows:
        if row["day"] not in by_day:
            order.append(row["day"])
            by_day[row["day"]] = []
        by_day[row["day"]].append(row)
    groups = []
    for day in order:
        parts = sorted(by_day[day], key=lambda r: (
            r["entry_time"] or datetime.time.min))
        if len(parts) == 1:
            row = dict(parts[0])
            row["parts"] = parts
            row["gaps"] = []
            row["edit_json"] = json.dumps(row.get("edit_presses") or [])
            groups.append(row)
            continue
        live = [p for p in parts if not p.get("only_cancelled")] or parts
        row = dict(live[0])
        row["parts"] = live
        row["key"] = ",".join(p["key"] for p in live)
        row["event_ids"] = ",".join(
            p["event_ids"] for p in live if p.get("event_ids"))
        row["seconds"] = sum(p["seconds"] for p in live)
        row["duration"] = format_duration(row["seconds"])
        row["only_cancelled"] = all(p.get("only_cancelled") for p in parts)
        status = max((p["status"] for p in live),
                     key=lambda s: _STATUS_WEIGHT[s])
        row["status"] = status
        row["status_label"] = _STATUS_LABELS[status]
        row["status_badge"] = _STATUS_BADGES[status]
        # Horas por tipo del día, sumadas.
        types = {}
        for part in live:
            for item in part.get("type_hours") or []:
                slot = types.setdefault(item["name"], {
                    "name": item["name"], "seconds": 0,
                    "counts": item["counts"]})
                slot["seconds"] += item.get("seconds", 0)
        row["type_hours"] = [{**t, "label": format_duration(t["seconds"])}
                             for t in types.values()]
        for key in ("incidents", "changes", "trips", "meals",
                    "auto_meals", "cancelled"):
            seen = []
            for part in parts:
                for item in part.get(key) or []:
                    if item not in seen:
                        seen.append(item)
            row[key] = seen
        row["corrected"] = any(p.get("corrected") for p in live)
        row["corrected_any"] = any(p.get("corrected_any") for p in live)
        row["reviewed"] = any(p.get("reviewed") for p in live)
        row["no_meal_break"] = any(p.get("no_meal_break") for p in live)
        row["travel"] = next((p["travel"] for p in live
                              if p.get("travel")), None)
        row["exit"] = live[-1].get("exit")
        # Los ratos fuera entre jornadas.
        gaps = []
        for before, after in zip(live, live[1:]):
            out, back = before.get("exit"), after.get("entry")
            if out and back:
                seconds = int((back["time"] - out["time"]).total_seconds())
                gaps.append({"out": out["time"], "back": back["time"],
                             # S149: para corregir la pausa de comida.
                             "out_press": out, "back_press": back,
                             "seconds": seconds,
                             "quick": seconds < QUICK_GAP_SECONDS})
        row["gaps"] = gaps
        row["edit_json"] = json.dumps(
            [item for p in live for item in p.get("edit_presses") or []])
        # La barra de todo el día.
        segments = [seg for p in live for seg in (p.get("bar") or [])]
        if segments:
            start, end = segments[0]["from"], segments[-1]["to"]
            span = max((end - start).total_seconds(), 1)
            bar, cursor = [], start
            for seg in segments:
                if seg["from"] > cursor:
                    bar.append({
                        "name": "Fuera", "from": cursor, "to": seg["from"],
                        "pct": round((seg["from"] - cursor).total_seconds()
                                     * 100 / span, 2),
                        "color": GAP_COLOR, "gap": True,
                        "duration": format_duration(int(
                            (seg["from"] - cursor).total_seconds())),
                    })
                bar.append({**seg, "pct": round(
                    (seg["to"] - seg["from"]).total_seconds() * 100 / span,
                    2)})
                cursor = max(cursor, seg["to"])
            row["bar"] = bar
        groups.append(row)
    return groups


def _context(request, person):
    """
    Context of the list: filtered and sorted rows plus the totals.
    ---
    Contexto del listado: filas filtradas y ordenadas, y los totales.
    """
    from panel.views_clock_events import worker_detail_data

    company = request.user.company_user.company
    date_from, date_to = _date_range(request)
    view = _param(request, "view")
    if view not in {code for code, _l, _i in VIEW_CHOICES}:
        view = VIEW_SHIFTS
    # S144: el calendario muestra siempre los cuatro años completos (el
    # actual y los tres anteriores), sea cual sea el intervalo de arriba;
    # el resto de filtros sí se aplica.
    data_from, data_to = date_from, date_to
    if view == VIEW_CALENDAR:
        from panel.clock_calendar import calendar_range

        data_from, data_to = calendar_range()
    data = worker_detail_data(company, person, data_from, data_to)
    rows = [_row(shift) for shift in data["shifts"]]
    statuses = _statuses(request)
    rows = [r for r in rows if r["status"] in statuses]
    if _param(request, "corrected") == "1":
        rows = [r for r in rows if r["corrected"]]
    clock_type = _param(request, "clock_type")
    if clock_type.isdigit():
        name = ClockType.objects.filter(
            pk=int(clock_type), company=company,
        ).values_list("name", flat=True).first()
        rows = [r for r in rows if name in r["type_names"]]
    if request.GET.get("only_selected") == "1":
        wanted = set(request.GET.get("selected_ids", "").split(","))
        rows = [r for r in rows if r["key"] in wanted]
    raw_sort = _param(request, "sort")
    rows = _sort_rows(rows, _parse_sort(raw_sort))
    # S143: una fila por día con sus jornadas dentro.
    rows = _group_by_day(rows)
    report = data["report"]
    calendar = {}
    if view == VIEW_CALENDAR:
        from panel.clock_calendar import calendar_years

        calendar = calendar_years(
            [part for row in rows for part in row["parts"]])
    return {
        "view": view,
        "view_choices": VIEW_CHOICES,
        "view_label": dict(
            (code, label) for code, label, _i in VIEW_CHOICES)[view],
        "view_count": (len(data["history"]) if view == VIEW_CORRECTIONS
                       else len(rows)),
        "calendar": calendar,
        "person": person,
        "person_label": _person_label(person),
        "has_account": person.company_user_id is not None,
        "rows": rows,
        "history": data["history"],
        "date_from": date_from,
        "date_to": date_to,
        "filter_status": statuses,
        "filter_corrected": _param(request, "corrected") == "1",
        "filter_clock_type": clock_type,
        "status_choices": STATUS_CHOICES,
        "clock_types": list(ClockType.objects.filter(company=company)),
        "kind_choices": ClockEvent.Kind.choices,
        "total_label": report.total_label,
        # S143: solo las incidencias sin visar ni corregir.
        "issues_count": sum(
            len(s.get("incidents") or []) for s in data["shifts"]
            if not s.get("reviewed")),
        "punctuality_label": report.punctuality_label,
        "early_label": report.early_label,
        # S144: horas extras, kilómetros y dietas del intervalo.
        "extras": data["extras"],
        **_sort_controls(raw_sort),
    }


def _person(pk):
    from panel.views_clock_events import _person_or_404

    return _person_or_404(pk)


DAY_LETTERS = ("L", "M", "X", "J", "V", "S", "D")


def _tracts(schedule):
    return " · ".join(
        "%s–%s" % (start.strftime("%H:%M"), end.strftime("%H:%M"))
        for start, end in (
            (schedule.start_time_morning, schedule.end_time_morning),
            (schedule.start_time_afternoon, schedule.end_time_afternoon),
        ) if start is not None and end is not None)


def schedule_info(person):
    """
    The worker's schedule and how they clock, for the page header.
    ---
    S143 (Miguel Ángel): en la página de fichajes "no sabemos el horario
    que tiene cada uno [...] el tipo de fichaje que hace, si es con tipo
    o si no es con tipo [...] los horarios abiertos, el horario que se
    han fijado ellos". Horario de hoy (nombre, temporada, tramos o los
    de cada día), cómo ficha (por tipos o con un botón), desde cuándo,
    sus avisos y, con horario abierto, el horario propio de sus avisos.
    """
    from hr_calendar.clock_settings import worker_states
    from hr_calendar.models import WorkerClockSetting
    from panel.views_operator import _resolve_operator_schedule

    cu = person.company_user
    info = {"has_account": cu is not None}
    state = worker_states([person]).get(person.pk)
    info["state"] = state
    if cu is None:
        return info
    schedule = _resolve_operator_schedule(cu, cu.company)
    info["schedule"] = schedule
    if schedule is not None:
        info["season"] = schedule.get_season_display()
        if schedule.varies_by_day:
            rows = {d.weekday: d for d in schedule.days.all()}
            info["days"] = []
            for weekday, letter in enumerate(DAY_LETTERS):
                row = rows.get(weekday)
                info["days"].append((letter, _tracts(row) if row is not None
                                     and row.works else ""))
        elif not schedule.is_open:
            info["tracts"] = _tracts(schedule)
    setting = WorkerClockSetting.objects.filter(person=person).first()
    labels_in = dict(WorkerClockSetting.IN_REMINDER_CHOICES)
    labels_out = dict(WorkerClockSetting.OUT_REMINDER_CHOICES)
    probe = setting or WorkerClockSetting()
    info["in_reminders"] = ", ".join(
        labels_in.get(k, k) for k in probe.in_reminder_keys()) or "ninguno"
    info["out_reminders"] = ", ".join(
        labels_out.get(k, k) for k in probe.out_reminder_keys()) or "ninguno"
    if setting is not None and setting.own_shifts():
        info["own"] = {
            "tracts": " · ".join(
                "%s–%s" % (a.strftime("%H:%M"), b.strftime("%H:%M"))
                for a, b in setting.own_shifts()),
            "days": " ".join(DAY_LETTERS[d] for d in setting.own_days()),
            "until": setting.own_schedule_until,
        }
    return info


class ClockWorkerPageView(SupervisorAccessMixin, View):
    """
    GET: the clock-in page of one worker.
    ---
    GET: la página de fichajes del trabajador (panel fijo, listado,
    selección), con sus filtros recordados por usuario.
    """

    def get(self, request, pk):
        person = _person(pk)
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY,
            "selection_%d" % person.pk, [],
        )
        from panel.views_clock_extras import bag_context

        return render(request, "panel/clock_worker/page.html", {
            **_context(request, person),
            # S144: bolsa de horas extras (total en el panel fijo).
            "bag": bag_context(person),
            # S143: su horario y cómo ficha.
            "sched": schedule_info(person),
            "screen_key": SCREEN_KEY,
            "saved_selection": selection if isinstance(
                selection, list) else [],
        })


class ClockWorkerResultsView(SupervisorAccessMixin, View):
    """
    GET: the list only (filters, dates, order).
    ---
    GET: solo el listado.
    """

    def get(self, request, pk):
        person = _person(pk)
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(request, "panel/clock_worker/_table.html",
                      _context(request, person))


class ClockWorkerActionView(SupervisorAccessMixin, View):
    """
    POST: a correction (change, cancel, add, cancel the marked).
    ---
    POST: una corrección (cambiar, anular, añadir, anular las jornadas
    marcadas) y el listado repintado con los filtros que se veían
    (copia _f_ de cada filtro); el mensaje va en X-Clock-Message y, si
    es un error, X-Clock-Error.
    """

    def post(self, request, pk):
        from urllib.parse import quote

        from django.http import QueryDict

        from panel.views_clock_events import apply_correction

        person = _person(pk)
        message, error, _form = apply_correction(request, person)
        filters = QueryDict(mutable=True)
        for key in FILTER_KEYS + ("only_selected", "selected_ids"):
            value = request.POST.get("_f_" + key)
            if value:
                filters[key] = value
        request.GET = filters
        response = HttpResponse(render(
            request, "panel/clock_worker/_table.html",
            _context(request, person),
        ).content)
        response["X-Clock-Message"] = quote(error or message)
        if error:
            response["X-Clock-Error"] = "1"
        return response
