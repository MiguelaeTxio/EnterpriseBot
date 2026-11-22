# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/clock_core.py
"""
Clock-in shifts of one worker and their corrections, new interface.

---

Jornadas de fichaje de un trabajador y sus correcciones para la nueva
interfaz (S163). Copia de panel/views_clock_events.py (worker_detail_data,
apply_correction y lo que usan) y de panel/views_clock_worker.py (una
fila por jornada y una por día), sin depender de ellas. Se quita la
comida que se propone al añadir una pausa sale de
new_ui/schedule_core.py.
"""
import datetime
import json
import logging
from decimal import Decimal

from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from document_explorer.models import PersonIdentity
from hr_calendar.clock_report import REST_NOTE
from hr_calendar.clock_report import format_duration, reports_by_user
from hr_calendar.models import ClockCorrection
from hr_calendar.models import ClockEvent

logger = logging.getLogger(__name__)

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
    month_excess = {}
    excess_seconds = 0
    excess_label = "0:00"
    last_event = None
    total_seconds = 0
    total_label = "0:00"



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
        # S149: hora real de salida que indica el trabajador.
        "claimed_at": (timezone.localtime(event.claimed_at)
                       if event.claimed_at else None),
        "claimed_value": (timezone.localtime(event.claimed_at).strftime(
            "%Y-%m-%dT%H:%M") if event.claimed_at else ""),
        "claim_note": event.claim_note,
        # S149 (Plataformas): comentario del trabajador al fichar.
        "worker_note": event.worker_note,
        # S149: corrección hecha por la IA al cotejar los albaranes.
        # S153: o con el parte de trabajo (tampoco visa el día).
        "by_ai": bool(correction and correction.source
                      in (ClockCorrection.Source.AI,
                          ClockCorrection.Source.PARTE)),
        "by_parte": bool(correction and correction.source
                         == ClockCorrection.Source.PARTE),
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
        # S157: el historial lee la pulsación corregida y la nueva de
        # cada corrección (lugar, "Ubicación rectificada"); sin esto,
        # dos consultas por corrección (logs/slow_requests.log del
        # 18-19/11: 58 y 97 consultas de ClockEvent en una página).
        "event", "replacement",
    ).order_by("-corrected_at"))


def _meal_edits(shift, by_replacement):
    """
    The meal-break stretches of a shift with types, ready to correct.
    ---
    S149: las pausas "Pausa para comer" de una jornada por tipos que se
    pueden corregir (las que acaban con un cambio de tipo, no con la
    salida): la pulsación que empieza la pausa y la que la acaba.
    """
    ends = list(shift.changes) + (
        [shift.clock_out] if shift.clock_out is not None else [])
    edits = []
    for mark, end in shift.meal_segments:
        back = next((e for e in ends if e.pressed_at == end
                     and e.kind == ClockEvent.Kind.CHANGE), None)
        if back is not None:
            edits.append({"out": _press_view(mark, by_replacement),
                          "back": _press_view(back, by_replacement)})
    return edits



def _lunch_defaults(company, person):
    """
    day -> ("YYYY-MM-DDTHH:MM" start, end) of the schedule's lunch, or None.

    ---

    S149: la pausa de comida que se propone al añadirla: entre la salida
    de la mañana y la entrada de la tarde de su horario ese día (jornada
    partida); None si ese día no la tiene. S163: con el horario de
    new_ui/schedule_core.py y las horas de ese día (WorkdaySchedule.for_day).
    """
    from hr_calendar.clock_report import public_holiday
    from new_ui.schedule_core import resolve_person_schedule

    base, _origin = resolve_person_schedule(person, company)
    cu = person.company_user
    cache = {}

    def lunch(day):
        if base is None:
            return None
        if day not in cache:
            schedule = base.for_day(
                day, holiday=public_holiday(day, getattr(cu, "base", None)))
            cache[day] = None
            if (schedule is not None and not schedule.is_open
                    and not schedule.is_intensive
                    and schedule.end_time_morning
                    and schedule.start_time_afternoon):
                cache[day] = tuple(
                    "%sT%s" % (day.isoformat(), t.strftime("%H:%M"))
                    for t in (schedule.end_time_morning,
                              schedule.start_time_afternoon))
        return cache[day]
    return lunch


def worker_detail_data(company, person, date_from, date_to):
    """
    Shifts, corrections history and report of one worker in a range.
    ---
    Las jornadas (con sus pulsaciones listas para la plantilla y las
    anuladas en su día), el historial de correcciones y el informe de un
    trabajador en un intervalo. Lo usan el detalle (modal de la ficha) y
    la página de fichajes del trabajador (S144).
    """
    # S163: el horario de cada día (comida que se propone) sale de la
    # caché en bloque de new_ui/schedule_core.py; el informe
    # (reports_by_user) precarga además el suyo.
    from new_ui.schedule_core import bulk_schedule_cache

    with bulk_schedule_cache([person], company):
        return _worker_detail_data(company, person, date_from, date_to)


def _worker_detail_data(company, person, date_from, date_to):
    """
    worker_detail_data without the schedule cache.
    ---
    worker_detail_data, ya dentro de la caché de horarios.
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
    lunch = _lunch_defaults(company, person)
    shifts = [{
        "day": s.day,
        "presses": [_press_view(s.clock_in, by_replacement),
                    _press_view(s.clock_out, by_replacement)],
        "duration": s.duration_label,
        "seconds": s.seconds,
        "issue": s.issue,
        "incidents": s.incidents,
        "expected_start": s.expected_start,
        # S143: jornada de hoy con entrada y sin salida (en verde).
        "in_progress": s.in_progress,
        "late_minutes": s.late_minutes,
        "expected_end": s.expected_end,
        "suggested_end": s.suggested_end,
        "early_minutes": s.early_minutes,
        "start_off": s.start_off_schedule,
        "end_off": s.end_off_schedule,
        # S141: cambios de tipo y horas por tipo (fichaje por tipos).
        "changes": [_press_view(c, by_replacement) for c in s.changes],
        "type_hours": _type_hours(s),
        # S143: barra de tramos de la jornada, con su color por tipo.
        "bar": (bar := _shift_bar(s)),
        # S149: la barra para el modal de «Intercalar un tipo».
        "bar_json": _bar_json(bar),
        # S144: día flexible tras una jornada con poco descanso.
        "rest_note": REST_NOTE if s.after_short_rest else "",
        # S144: las pulsaciones de la jornada, para anularla entera.
        "event_ids": ",".join(
            str(e.pk) for e in [s.clock_in] + list(s.changes)
            + [s.clock_out] if e is not None),
        "cancelled": [],
        # S144: pausas para comer (dietas) y tramos con vehículo propio.
        "meals": clock_extras.shift_meals(s, bases),
        # S149: pausas por tipos para corregir y la comida del horario
        # que se propone al añadirla.
        "meal_edits": _meal_edits(s, by_replacement),
        "lunch": lunch(s.day),
        # S143: comida o cena sin fichar que se descuenta (1 h cada una).
        # S149: con de dónde sale la hora si no es de la jornada (p. ej.
        # "de presencia 1:00").
        "auto_meals": [
            "%s descontada: −1:00 h" % kind + (", de %s" % ", ".join(
                "%s %s" % (_ROLE_LABELS.get(role, "otros tipos"),
                           format_duration(seconds))
                for role, seconds in taken.items()) if taken else "")
            for kind, taken in zip(s.auto_meals, s.auto_meal_from)],
        "no_meal_break": any(
            getattr(e, "no_meal_break", False)
            for e in [s.clock_in] + list(s.changes) + [s.clock_out]
            if e is not None),
        "trips": clock_extras.shift_trips(s, budget),
    } for s in report.shifts]
    # S143 (convenio, art. 23): las horas extra son por mes, no por día.
    excess = getattr(report, "month_excess", {}) or {}
    # S143 (convenio, art. 22): desplazamiento del día, en su última
    # jornada.
    travel = getattr(report, "travel", {}) or {}
    last_of_day = {}
    for shift in shifts:
        last_of_day[shift["day"]] = shift
    for day, item in travel.items():
        if day in last_of_day:
            last_of_day[day]["travel"] = item
    km = clock_extras.km_total(
        [t for shift in shifts for t in shift["trips"]])
    extras = {
        "travel_hours": sum(i["hours"] for i in travel.values()),
        "allowances": sum(1 for i in travel.values() if i["allowance"]),
        "km_euros": (clock_extras.OWN_VEHICLE_EUR_KM
                     * Decimal(str(km)) if km else None),
        "excess_label": format_duration(sum(excess.values())),
        "km": km,
        "meals": {
            kind: sum(1 for shift in shifts for m in shift["meals"]
                      if m["allowance"] and m["kind"] == kind)
            for kind in (clock_extras.LUNCH, clock_extras.DINNER)
        },
    }
    _attach_cancelled(shifts, corrections, date_from, date_to)
    _attach_reviewed(person, shifts)
    history = [{
        "correction": c,
        "corrected_by": _user_label(c.corrected_by),
        "corrected_at": timezone.localtime(c.corrected_at),
        "old_time": (timezone.localtime(c.old_pressed_at)
                     if c.old_pressed_at else None),
        "new_time": (timezone.localtime(c.new_pressed_at)
                     if c.new_pressed_at else None),
        "is_cancel": c.action == ClockCorrection.Action.CANCEL,
        # S147: ubicación rectificada en el mapa (antes / después).
        "old_place": _place_of(c.event),
        "new_place": _place_of(c.replacement),
        "relocated": bool(c.replacement_id and c.replacement.gps_error
                          .startswith("Ubicación rectificada")),
    } for c in corrections]
    return {"report": report, "shifts": shifts, "history": history,
            "extras": extras}


BAR_COLORS = {
    "travel": "#0d6efd", "meal": "#adb5bd", "presence": "#fd7e14",
    "force": "#dc3545",
}
BAR_WORK = "#198754"
BAR_OTHER_WORK = "#20c997"


def _shift_bar(shift):
    """
    The shift's segments as a coloured bar: [{name, from, to, pct,
    color}].
    ---
    S143 (Miguel Ángel): "por los tramos que ha fichado, y que se vea con
    color los tramos, como una barra de progreso". Un tramo por tipo
    fichado (el de la entrada y uno por cada cambio de tipo), hasta la
    salida o, si la jornada de hoy sigue abierta, hasta ahora. Sin tipos,
    un solo tramo de trabajo.
    """
    if shift.clock_in is None:
        return []
    marks = [shift.clock_in] + list(shift.changes)
    end = shift.clock_out.pressed_at if shift.clock_out is not None else (
        timezone.now() if shift.in_progress else None)
    if end is None:
        return []
    ends = [m.pressed_at for m in marks[1:]] + [end]
    total = max((end - shift.clock_in.pressed_at).total_seconds(), 1)
    bar = []
    for mark, stop in zip(marks, ends):
        clock_type = mark.clock_type
        seconds = max((stop - mark.pressed_at).total_seconds(), 0)
        if clock_type is None:
            name, color = "Trabajo", BAR_WORK
        else:
            name = clock_type.name
            color = BAR_COLORS.get(clock_type.role) or (
                (BAR_WORK if clock_type.is_default else BAR_OTHER_WORK)
                if clock_type.counts_as_work else "#6c757d")
        bar.append({
            "name": name,
            "from": timezone.localtime(mark.pressed_at),
            "to": timezone.localtime(stop),
            "pct": round(seconds * 100 / total, 2),
            "color": color,
            "duration": format_duration(int(seconds)),
        })
    return bar


def _bar_json(bar):
    """
    The shift's bar as JSON, for the "insert a type" timeline.
    ---
    S149 (Miguel Ángel): "facilitar el poder intercalar el tramo viendo
    visualmente los tramos actuales; cuando sale el modal ya no se ven".
    Cada tramo con su nombre, color y horas en el formato de los campos
    de fecha y hora del modal.
    """
    import json

    return json.dumps([{
        "name": seg["name"], "color": seg["color"],
        "from": seg["from"].strftime("%Y-%m-%dT%H:%M"),
        "to": seg["to"].strftime("%Y-%m-%dT%H:%M"),
    } for seg in bar])


# S149: de dónde sale la comida sin fichar cuando no es de la jornada.
_ROLE_LABELS = {"presence": "presencia", "force": "fuerza mayor"}


def _attach_reviewed(person, shifts):
    """
    Mark each shift as seen by a supervisor ("reviewed") or not.
    ---
    S143 (Miguel Ángel): una jornada está visada si su día tiene la
    casilla de visado (ClockDayReview) o si se ha corregido algo de ella
    ("al corregir automáticamente se marca como visada"). También marca
    la jornada en curso de hoy ("in_progress").
    """
    from hr_calendar.models import (
        ClockDayAiCheck, ClockDayHold, ClockDayReview,
    )

    reviews, checks, holds = {}, {}, {}
    if person.company_user_id is not None and shifts:
        wanted = {s["day"] for s in shifts}
        reviews = {r.day: r for r in ClockDayReview.objects.filter(
            company_user_id=person.company_user_id, day__in=wanted,
        ).select_related("reviewed_by__user")}
        # S149: días comparados con sus albaranes por la IA.
        checks = {c.day: c for c in ClockDayAiCheck.objects.filter(
            company_user_id=person.company_user_id, day__in=wanted,
        ).select_related("checked_by__user")}
        # S149 (18/11): días marcados para revisar después.
        holds = {h.day: h for h in ClockDayHold.objects.filter(
            company_user_id=person.company_user_id, day__in=wanted,
        ).select_related("held_by__user")}
    for shift in shifts:
        presses = [p for p in (shift.get("presses") or [])
                   + (shift.get("changes") or []) if p]
        shift["corrected_any"] = bool(shift.get("cancelled")) or any(
            p.get("correction") for p in presses)
        # S149 (Miguel Ángel): lo que corrige la IA no visa el día; el
        # visado es solo del supervisor. Una corrección manual sí.
        manual = any(not c.get("by_ai") for c in shift.get("cancelled")
                     or []) or any(p.get("correction") and not
                                   p.get("by_ai") for p in presses)
        review = reviews.get(shift["day"])
        shift["reviewed"] = review is not None or manual
        shift["review_manual"] = review is not None
        shift["reviewed_by"] = (_user_label(review.reviewed_by)
                                if review and review.reviewed_by_id
                                else "")
        hold = holds.get(shift["day"])
        shift["hold"] = hold
        shift["held_by"] = (_user_label(hold.held_by)
                            if hold and hold.held_by_id else "")
        check = checks.get(shift["day"])
        shift["ai_check"] = check
        shift["ai_checked_by"] = (_user_label(check.checked_by)
                                  if check and check.checked_by_id else "")



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
            # S149: para recuperar el día en «Editar la jornada».
            "kind_code": correction.old_kind,
            "clock_type": correction.old_clock_type,
            "by": _user_label(correction.corrected_by),
            "at": timezone.localtime(correction.corrected_at),
            "reason": correction.reason,
            "by_ai": correction.source in (ClockCorrection.Source.AI,
                                           ClockCorrection.Source.PARTE),
            "by_parte": correction.source == ClockCorrection.Source.PARTE,
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
        "seconds": seconds,
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



def _place_of(event):
    """
    Short place text of a press for the corrections history.
    ---
    Dónde se fichó, para el historial de correcciones (S147): municipio
    o coordenadas; vacío si no tiene posición.
    """
    if event is None or event.latitude is None:
        return ""
    return event.municipality or "%.5f, %.5f" % (
        event.latitude, event.longitude)


def _resync_partes(person, before):
    """
    After a correction, carry each touched day's parte with it
    (hr_calendar.clock_parts.resync_parte_after_correction, S146).
    Returns a text for the supervisor ("" = nothing changed).
    ---
    Tras una corrección, lleva el parte de cada día tocado con ella
    (S146). Devuelve un texto para el supervisor ("" = nada cambió).
    """
    from hr_calendar.clock_parts import resync_parte_after_correction

    texts = []
    for day, bounds in sorted(before.items()):
        try:
            outcome = resync_parte_after_correction(
                person.company_user, day, bounds)
        except Exception:
            logger.exception(
                "# [FICHAJE-PARTE] Fallo al ajustar el parte del %s del "
                "usuario #%s tras la corrección.", day,
                person.company_user_id,
            )
            continue
        if outcome.text:
            texts.append("Parte del %s: %s." % (
                day.strftime("%d/%m"), outcome.text))
    return " ".join(texts)


def _bounds_before(person, moments):
    """
    {day: day_bounds} of the local days of `moments`, before correcting.
    ---
    {día: day_bounds} de los días locales de `moments`, antes de
    corregir.
    """
    from hr_calendar.clock_parts import day_bounds

    days = {timezone.localtime(m).date() for m in moments if m}
    return {day: day_bounds(person.company_user, day) for day in days}


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
    from hr_calendar.clock_corrections import meal_break
    from hr_calendar.clock_corrections import insert_type
    from hr_calendar.clock_corrections import edit_presses

    form = {
        "event_id": request.POST.get("event_id", ""),
        "action": request.POST.get("action", ""),
        "new_kind": request.POST.get("new_kind", ""),
        "new_pressed_at": request.POST.get("new_pressed_at", ""),
        "new_clock_type": request.POST.get("new_clock_type", ""),
        "reason": request.POST.get("reason", ""),
        "label": request.POST.get("label", ""),
        "new_lat": request.POST.get("new_lat", ""),
        "new_lon": request.POST.get("new_lon", ""),
    }
    agent = request.META.get("HTTP_USER_AGENT", "")
    # S147: ubicación rectificada en el mapa (vacío = sin rectificar).
    new_location = None
    if form["new_lat"] or form["new_lon"]:
        try:
            lat, lon = float(form["new_lat"]), float(form["new_lon"])
        except ValueError:
            return "", "La ubicación marcada en el mapa no es válida.", form
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return "", "La ubicación marcada en el mapa no es válida.", form
        new_location = (lat, lon)
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
        before = _bounds_before(person, ClockEvent.objects.filter(
            pk__in=own).values_list("pressed_at", flat=True))
        try:
            with transaction.atomic():
                for pk in own:
                    correct_event(pk, by, ClockCorrection.Action.CANCEL,
                                  form["reason"], user_agent=agent)
        except ClockCorrectionError as exc:
            return "", str(exc), form
        return " ".join(filter(None, (
            "Anulados %d fichajes. Se ven tachados en su día y quedan "
            "en el historial." % len(own),
            _resync_partes(person, before)))), "", {}
    # S149 (Miguel Ángel): añadir o corregir la pausa de comida.
    if form["action"] == "MEAL":
        def moment(name):
            value = parse_datetime(request.POST.get(name, ""))
            if value is not None and timezone.is_naive(value):
                value = timezone.make_aware(value)
            return value

        start, end = moment("meal_start"), moment("meal_end")
        before = _bounds_before(person, [start, end])
        try:
            meal_break(
                person.company_user, person, by, form["reason"], start,
                end,
                out_event_id=request.POST.get("meal_out") or None,
                back_event_id=request.POST.get("meal_back") or None,
                entry_event_id=request.POST.get("meal_entry") or None,
                user_agent=agent,
            )
        except ClockCorrectionError as exc:
            return "", str(exc), form
        return " ".join(filter(None, (
            "Pausa de comida guardada. Queda en el historial con quién, "
            "cuándo y por qué.",
            _resync_partes(person, before)))), "", {}
    # S149 (Miguel Ángel): intercalar un tramo de otro tipo (p. ej. el
    # desplazamiento que no fichó entre el trabajo efectivo y la
    # presencia). Sin hora de fin, llega hasta el siguiente fichaje.
    # S149 (Miguel Ángel): «Editar la jornada», todas las pulsaciones
    # de una vez (corregir, anular, añadir) con un solo motivo.
    if form["action"] == "EDIT":
        import json

        try:
            raw = json.loads(request.POST.get("edit_rows") or "[]")
        except ValueError:
            return "", "No se ha podido leer la jornada editada.", form
        rows = []
        for item in raw if isinstance(raw, list) else []:
            at = parse_datetime(item.get("at") or "")
            if at is not None and timezone.is_naive(at):
                at = timezone.make_aware(at)
            rows.append({"id": item.get("id"), "delete": bool(item.get("delete")),
                         "kind": item.get("kind"), "at": at,
                         "type": item.get("type")})
        before = _bounds_before(person, [r["at"] for r in rows])
        try:
            cancelled, changed, added = edit_presses(
                person.company_user, person, by, form["reason"], rows,
                user_agent=agent,
            )
        except ClockCorrectionError as exc:
            return "", str(exc), form
        done = ", ".join(filter(None, (
            "%d anulado%s" % (cancelled, "s" if cancelled != 1 else "") if cancelled else "",
            "%d corregido%s" % (changed, "s" if changed != 1 else "") if changed else "",
            "%d añadido%s" % (added, "s" if added != 1 else "") if added else "")))
        return " ".join(filter(None, (
            "Jornada guardada (%s). Queda en el historial con quién, "
            "cuándo y por qué." % done,
            _resync_partes(person, before)))), "", {}
    if form["action"] == "INSERT":
        start = parse_datetime(request.POST.get("insert_start", ""))
        end = parse_datetime(request.POST.get("insert_end", ""))
        start, end = [
            timezone.make_aware(v) if v is not None and timezone.is_naive(v)
            else v for v in (start, end)
        ]
        before = _bounds_before(person, [start, end])
        try:
            insert_type(
                person.company_user, person, by, form["reason"],
                request.POST.get("insert_entry") or None,
                request.POST.get("insert_type") or None, start, end,
                user_agent=agent,
            )
        except ClockCorrectionError as exc:
            return "", str(exc), form
        return " ".join(filter(None, (
            "Tramo intercalado. Queda en el historial con quién, cuándo "
            "y por qué.",
            _resync_partes(person, before)))), "", {}
    # S144: añadir una pulsación (partir un tramo, o la que falta).
    if form["action"] == ClockCorrection.Action.ADD:
        before = _bounds_before(person, [new_pressed_at])
        try:
            add_event(person.company_user, person, by, form["new_kind"],
                      new_pressed_at, form["reason"], user_agent=agent,
                      new_clock_type_id=form["new_clock_type"] or None,
                      new_location=new_location)
        except ClockCorrectionError as exc:
            return "", str(exc), form
        return " ".join(filter(None, (
            "Fichaje añadido. Queda en el historial con quién lo "
            "añadió, cuándo y por qué.",
            _resync_partes(person, before)))), "", {}
    event_id = form["event_id"]
    if (not event_id.isdigit() or person.company_user_id is None
            or not ClockEvent.objects.filter(
                pk=int(event_id),
                company_user_id=person.company_user_id,
            ).exists()):
        return "", "Ese fichaje no es de este trabajador.", form
    before = _bounds_before(person, [
        ClockEvent.objects.get(pk=int(event_id)).pressed_at,
        new_pressed_at,
    ])
    try:
        correction = correct_event(
            int(event_id), by, form["action"], form["reason"],
            new_kind=form["new_kind"], new_pressed_at=new_pressed_at,
            user_agent=agent,
            new_clock_type_id=form["new_clock_type"] or None,
            new_location=new_location,
        )
    except ClockCorrectionError as exc:
        return "", str(exc), form
    return " ".join(filter(None, (
        "%s guardada. El fichaje original se conserva en el "
        "historial." % correction.get_action_display(),
        _resync_partes(person, before)))), "", {}




# ---------------------------------------------- filas (views_clock_worker)
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
# S149 (Miguel Ángel, 16/11: "importante la marca de que han sido
# procesados de forma automática y no queden visados para que los vise
# el supervisor"): día cotejado con sus albaranes por la IA y aún sin
# visar.
STATUS_AI = "ai"
# S149 (Miguel Ángel, 18/11: "marcarla para una revisión posterior y
# darle un color diferente"): sin el albarán a mano, por ejemplo.
STATUS_HOLD = "hold"
STATUS_CHOICES = (
    (STATUS_HOLD, "Pendientes de revisar"),
    (STATUS_OPEN, "En curso"),
    (STATUS_OK, "Correctas"),
    # S153 (Miguel Ángel, con captura de Juan corrigiendo jornadas): se
    # visa cualquier jornada, tenga incidencias o no; visada = casilla
    # "Visado" o corregida.
    (STATUS_AI, "Procesadas por IA, sin visar"),
    (STATUS_REVIEWED, "Visadas"),
    (STATUS_ISSUES, "Incidencias sin visar"),
    (STATUS_CANCELLED, "Anuladas"),
)
_STATUS_LABELS = dict(STATUS_CHOICES)
_STATUS_BADGES = {
    STATUS_OK: "success", STATUS_ISSUES: "danger",
    STATUS_CANCELLED: "secondary", STATUS_REVIEWED: "warning",
    STATUS_OPEN: "success", STATUS_AI: "info", STATUS_HOLD: "hold",
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

def _row(shift):
    """
    One row of the page from a shift of worker_detail_data.
    ---
    Una fila de la página: una jornada, o un día con todo anulado.
    """
    entry, exit_ = (shift.get("presses") or [None, None])
    changes = shift.get("changes") or []
    # S149: salida fichada tarde con la hora real que indica el
    # trabajador: incidencia hasta que el supervisor la aplica (la
    # pulsación corregida ya no la lleva) o visa el día.
    if exit_ and (exit_.get("claimed_at") or exit_.get("claim_note")):
        claim = "Salida fichada a las %s; indica %s%s" % (
            timezone.localtime(exit_["event"].pressed_at).strftime("%H:%M"),
            ("que salió a las %s" % exit_["claimed_at"].strftime("%H:%M")
             if exit_.get("claimed_at") else "otra hora"),
            (": «%s»" % exit_["claim_note"]) if exit_.get("claim_note")
            else ".")
        shift = {**shift, "incidents": list(shift.get("incidents") or [])
                 + [claim]}
    if shift.get("only_cancelled"):
        status = STATUS_CANCELLED
    # Marcada para después: hasta que se quite o se vise con la casilla
    # (una corrección a mano no la quita).
    elif shift.get("hold") and not shift.get("review_manual"):
        status = STATUS_HOLD
    elif shift.get("ai_check") and not shift.get("reviewed"):
        status = STATUS_AI
    elif shift.get("incidents") and not shift.get("reviewed"):
        status = STATUS_ISSUES
    elif shift.get("reviewed"):
        status = STATUS_REVIEWED
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
    if shift.get("only_cancelled"):
        # S149 (Miguel Ángel, 18/11): un día que quedó anulado entero (la
        # salida olvidada que enganchaba con el día siguiente) se puede
        # recuperar: «Editar la jornada» trae lo anulado como fichajes
        # nuevos, para dejar, cambiar de hora o de tipo, o quitar.
        edit_presses, seen = [], set()
        for item in shift.get("cancelled") or []:
            at = item["time"].strftime("%Y-%m-%dT%H:%M")
            mark = (item.get("kind_code"), at)
            if not item.get("kind_code") or mark in seen:
                continue
            seen.add(mark)
            edit_presses.append({
                "id": None, "kind": item["kind_code"], "at": at,
                "type": getattr(item.get("clock_type"), "pk", None)
                if item["kind_code"] != "OUT" else None,
            })
    else:
        # S149: las pulsaciones vigentes para «Editar la jornada».
        edit_presses = [{
            "id": p["event"].pk, "kind": p["event"].kind,
            "at": p["input_value"],
            "type": p["event"].clock_type_id,
        } for p in presses]
    return {
        **shift,
        "key": key,
        "edit_presses": edit_presses,
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


_STATUS_WEIGHT = {STATUS_HOLD: 6, STATUS_AI: 5, STATUS_ISSUES: 4,
                  STATUS_REVIEWED: 3, STATUS_OPEN: 2, STATUS_OK: 1,
                  STATUS_CANCELLED: 0}
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
        row["hold"] = next((p["hold"] for p in live if p.get("hold")), None)
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


