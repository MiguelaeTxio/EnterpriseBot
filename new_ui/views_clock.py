# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_clock.py
"""
Shifts of one worker (Personal › Jornadas), new interface.

---

Jornadas de un trabajador en la nueva interfaz (S163): la pestaña
Personal › Jornadas de la persona abierta, con el periodo del filtro
común (sin periodo, el mes actual). Copiado de
panel/views_clock_worker.py y panel/views_clock_extras.py:
- una fila por día con sus jornadas, horas, tipos, incidencias y estado;
- editar la jornada (todas sus pulsaciones de una vez), anularla,
  visar o quitar el visado, dejarla pendiente de revisar;
- corregir los km de un tramo con vehículo propio;
- la bolsa de horas: resumen por meses y movimientos (apuntar, borrar);
- el historial de correcciones del periodo.
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from hr_calendar import clock_extras
from hr_calendar.models import (
    ClockDayHold, ClockDayReview, ClockEvent, ClockType, OvertimeAdjustment,
    OwnVehicleTrip,
)
from new_ui import clock_core
from new_ui.filters import period_range
from new_ui.mixins import SuperuserRequiredMixin


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _days(request):
    days = set()
    for raw in request.POST.getlist("day"):
        try:
            days.add(datetime.date.fromisoformat(raw))
        except ValueError:
            continue
    return days


VIEW_SHIFTS = "jornadas"
VIEW_CALENDAR = "calendario"
VIEW_HISTORY = "correcciones"


def _period(params):
    """
    The period of the common filter; without one, the current month.

    ---

    El periodo del filtro común; sin periodo, el mes en curso.
    """
    start, end = period_range(params)
    today = timezone.localdate()
    if start is None and end is None:
        start = today.replace(day=1)
        end = today
    start = start or (end - datetime.timedelta(days=30))
    end = end or today
    if (end - start).days > clock_core._MAX_RANGE_DAYS:
        start = end - datetime.timedelta(days=clock_core._MAX_RANGE_DAYS)
    return start, end


def bag_context(person):
    """
    The overtime bag of the worker for the template (None without account).

    ---

    La bolsa de horas del trabajador para la plantilla; None si no
    tiene cuenta (copia de panel/views_clock_extras.bag_context).
    """
    if person.company_user_id is None:
        return None
    bag = clock_extras.overtime_bag(
        person.company_user.company, person.company_user)
    label = clock_extras.signed_duration
    return {
        **bag,
        "cap_label": label(bag["cap_seconds"]),
        "extra_label": label(bag["extra_seconds"]),
        "accumulated_label": label(bag["accumulated_seconds"]),
        "month_rows": [{
            **m,
            "excess_label": label(m["excess"]),
            "extra_label": label(m["extra"]),
            "accumulated_label": label(m["accumulated"]),
            "worked_label": label(m["worked"]),
            "required_label": label(m["required"]),
        } for m in reversed(bag["months"])],
        "travel_label": label(bag["travel_seconds"]),
        "overdue": [d for d in bag["deadlines"] if d["state"]],
        "total_label": label(bag["total_seconds"]),
        "worked_label": label(bag["worked_seconds"]),
        "adjust_label": label(bag["adjust_minutes"] * 60),
        "rows": [{"item": a, "label": label(a.minutes * 60)}
                 for a in bag["adjustments"]],
    }


def render_jornadas(request, person):
    """
    The «Jornadas» tab of the open worker.

    ---

    La pestaña «Jornadas» de la persona abierta: los días del periodo
    (el más reciente arriba), sus totales, la bolsa y el historial.
    """
    company = request.user.company_user.company
    view = request.GET.get("vista", "")
    if view not in (VIEW_SHIFTS, VIEW_CALENDAR, VIEW_HISTORY):
        view = VIEW_SHIFTS
    only_day = None
    try:
        only_day = datetime.date.fromisoformat(request.GET.get("dia") or "")
    except ValueError:
        pass
    if view == VIEW_CALENDAR:
        from new_ui.clock_calendar import calendar_range, calendar_years

        cal_from, cal_to = calendar_range()
        cal = clock_core.worker_detail_data(company, person, cal_from,
                                            cal_to)
        parts = [clock_core._row(shift) for shift in cal["shifts"]]
        return render(request, "new_ui/_jornadas.html", {
            "person": person, "view": view,
            "has_account": person.company_user_id is not None,
            "calendar": calendar_years(parts),
        })
    if only_day is not None and view == VIEW_SHIFTS:
        date_from = date_to = only_day
    else:
        date_from, date_to = _period(request.GET)
    data = clock_core.worker_detail_data(company, person, date_from,
                                         date_to)
    rows = [clock_core._row(shift) for shift in data["shifts"]]
    rows = clock_core._group_by_day(rows)
    rows.reverse()
    clock_types = list(ClockType.objects.filter(company=company))
    for row in rows:
        row["edit_rows"] = [
            {**item, "n": index} for index, item in enumerate(
                _edit_items(row))]
        row["edit_blank"] = list(range(len(row["edit_rows"]),
                                       len(row["edit_rows"]) + 2))
    report = data["report"]
    return render(request, "new_ui/_jornadas.html", {
        "person": person,
        "view": view,
        "only_day": only_day,
        "has_account": person.company_user_id is not None,
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "history": data["history"],
        "extras": data["extras"],
        "total_label": report.total_label,
        "issues_count": sum(
            len(s.get("incidents") or []) for s in data["shifts"]
            if not s.get("reviewed")),
        "punctuality_label": report.punctuality_label,
        "kinds": [(ClockEvent.Kind.IN, "Entrada"),
                  (ClockEvent.Kind.CHANGE, "Cambio de tipo"),
                  (ClockEvent.Kind.OUT, "Salida")],
        "clock_types": clock_types,
        "bag": bag_context(person),
        "today": timezone.localdate(),
    })


def _edit_items(row):
    """
    Presses of a day for «Editar la jornada» (all its shifts).

    ---

    Las pulsaciones del día para «Editar la jornada» (las de todas sus
    jornadas, o las anuladas si el día quedó anulado entero).
    """
    items = []
    for part in row.get("parts") or [row]:
        items.extend(part.get("edit_presses") or [])
    seen, out = set(), []
    for item in items:
        mark = (item.get("id"), item.get("at"), item.get("kind"))
        if mark not in seen:
            seen.add(mark)
            out.append(item)
    return out


def _person(pk):
    return clock_core._person_or_404(pk)


class ShiftEditView(SuperuserRequiredMixin, View):
    """
    POST: «Editar la jornada» of one day (all its presses at once).

    ---

    POST: guarda las pulsaciones de un día de una vez (corregir,
    anular, añadir) con un solo motivo; queda quién, cuándo y por qué.
    """

    def post(self, request, pk):
        import json

        person = _person(pk)
        rows = []
        count = int(request.POST.get("edit_count") or 0)
        for n in range(min(count, 60)):
            at = (request.POST.get("at_%d" % n) or "").strip()
            press_id = request.POST.get("id_%d" % n) or None
            if not at and not press_id:
                continue
            rows.append({
                "id": press_id,
                "delete": request.POST.get("delete_%d" % n) == "1",
                "kind": request.POST.get("kind_%d" % n) or "",
                "at": at,
                "type": request.POST.get("type_%d" % n) or None,
            })
        if not rows:
            return _error("No hay ninguna pulsación que guardar.")
        post = request.POST.copy()
        post["action"] = "EDIT"
        post["edit_rows"] = json.dumps(rows)
        request.POST = post
        message, error, _form = clock_core.apply_correction(request, person)
        return _error(error) if error else _ok(message)


class ShiftFixView(SuperuserRequiredMixin, View):
    """
    POST `action` (MEAL | INSERT): meal break or an inserted stretch.

    ---

    POST: añadir o corregir la pausa de comida (meal_start, meal_end y,
    si se corrige una, meal_out/meal_back; si se añade, meal_entry) o
    intercalar un tramo de otro tipo que no fichó (insert_entry,
    insert_type, insert_start y, si no llega al siguiente fichaje,
    insert_end). Queda quién, cuándo y por qué.
    """

    def post(self, request, pk):
        person = _person(pk)
        if request.POST.get("action") not in ("MEAL", "INSERT"):
            return _error("Acción no válida.")
        message, error, _form = clock_core.apply_correction(request, person)
        return _error(error) if error else _ok(message)


class ShiftCancelView(SuperuserRequiredMixin, View):
    """
    POST `event_ids`, `reason`: cancel a whole day.

    ---

    POST: anula todas las pulsaciones del día (se ven tachadas y quedan
    en el historial).
    """

    def post(self, request, pk):
        person = _person(pk)
        post = request.POST.copy()
        post["action"] = "CANCEL"
        request.POST = post
        message, error, _form = clock_core.apply_correction(request, person)
        return _error(error) if error else _ok(message)


class ShiftReviewView(SuperuserRequiredMixin, View):
    """
    POST `day`, `action` (review | unreview | hold | unhold), `note`.

    ---

    POST: visar o quitar el visado de un día (visar quita la marca de
    pendiente) o dejarlo pendiente de revisar (con un motivo) o quitar
    esa marca.
    """

    def post(self, request, pk):
        person = _person(pk)
        days = _days(request)
        action = request.POST.get("action", "")
        if person.company_user_id is None or not days:
            return _error("No se ha podido marcar ese día.")
        cu_id = person.company_user_id
        first = min(days).strftime("%d/%m/%Y")
        if action == "review":
            ClockDayHold.objects.filter(company_user_id=cu_id,
                                        day__in=days).delete()
            for day in days:
                ClockDayReview.objects.get_or_create(
                    company_user_id=cu_id, day=day,
                    defaults={"reviewed_by": request.user.company_user})
            return _ok("Día %s visado." % first)
        if action == "unreview":
            ClockDayReview.objects.filter(company_user_id=cu_id,
                                          day__in=days).delete()
            return _ok("Quitado el visado del %s." % first)
        if action == "hold":
            note = (request.POST.get("note") or "").strip()[:255]
            for day in days:
                ClockDayHold.objects.update_or_create(
                    company_user_id=cu_id, day=day,
                    defaults={"note": note,
                              "held_by": request.user.company_user})
            return _ok("Día %s pendiente de revisar." % first)
        if action == "unhold":
            ClockDayHold.objects.filter(company_user_id=cu_id,
                                        day__in=days).delete()
            return _ok("Quitada la marca de pendiente del %s." % first)
        return _error("Acción no válida.")


class TripKmView(SuperuserRequiredMixin, View):
    """
    POST `trip`, `km`: correct the km of an own-vehicle stretch.

    ---

    POST: corrige los kilómetros de un tramo con vehículo propio.
    """

    def post(self, request, pk):
        person = _person(pk)
        trip = OwnVehicleTrip.objects.filter(
            pk=request.POST.get("trip") or 0,
            start_event__company_user_id=person.company_user_id,
        ).first() if person.company_user_id else None
        raw = (request.POST.get("km") or "").strip().replace(",", ".")
        try:
            km = Decimal(raw).quantize(Decimal("0.1"))
        except InvalidOperation:
            km = None
        if trip is None:
            return _error("Ese desplazamiento ya no existe.")
        if km is None or km < 0 or km > Decimal("5000"):
            return _error("Escribe los kilómetros, por ejemplo 23,5.")
        trip.km = km
        trip.error = ""
        trip.source = OwnVehicleTrip.SOURCE_MANUAL
        trip.corrected_by = request.user.company_user
        trip.save()
        return _ok("Kilómetros corregidos.")


def _parse_minutes(raw):
    """"3:30", "3,5" or "3.5" hours -> minutes; None if not valid."""
    raw = (raw or "").strip().replace(",", ".")
    try:
        if ":" in raw:
            hours, minutes = raw.split(":", 1)
            total = int(hours or 0) * 60 + int(minutes or 0)
        else:
            total = int(round(float(raw) * 60))
    except ValueError:
        return None
    return total if total > 0 else None


class BagMovementView(SuperuserRequiredMixin, View):
    """
    POST: record (`sign` pay | add) or delete (`adjustment`) a movement.

    ---

    POST: apunta un movimiento de la bolsa de horas (pagadas o
    compensadas, que restan, o añadidas) o borra uno. Unos días libres
    se borran con sus horas (el ajuste de vacaciones arrastra el
    movimiento).
    """

    def post(self, request, pk):
        person = _person(pk)
        if person.company_user_id is None:
            return _error("Sin cuenta en el panel: no tiene bolsa de "
                          "horas.")
        if request.POST.get("action") == "delete":
            row = OvertimeAdjustment.objects.filter(
                pk=request.POST.get("adjustment") or 0,
                company_user_id=person.company_user_id,
            ).select_related("vacation_adjustment").first()
            if row is None:
                return _error("Ese movimiento ya no existe.")
            (row.vacation_adjustment or row).delete()
            return _ok("Movimiento borrado.")
        minutes = _parse_minutes(request.POST.get("hours"))
        reason = (request.POST.get("reason") or "").strip()[:200]
        try:
            day = datetime.date.fromisoformat(request.POST.get("date") or "")
        except ValueError:
            day = None
        if minutes is None:
            return _error("Escribe las horas, por ejemplo 3:30 o 3,5.")
        if not reason:
            return _error("Escribe el motivo.")
        if day is None:
            return _error("Elige la fecha.")
        if request.POST.get("sign") != "add":
            minutes = -minutes
        OvertimeAdjustment.objects.create(
            company_user_id=person.company_user_id, date=day,
            minutes=minutes, reason=reason,
            created_by=request.user.company_user)
        return _ok("Movimiento apuntado.")
