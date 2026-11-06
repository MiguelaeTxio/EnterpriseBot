# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_clock_extras.py
"""
Overtime bag and own-vehicle kilometres on a worker's clock-in page
(H24, S144).

---

Bolsa de horas extras y kilómetros con vehículo propio en la página de
fichajes de un trabajador (H24, S144). Los cálculos están en
hr_calendar/clock_extras.py.

- ClockWorkerOvertimeView: GET el contenido del modal de la bolsa (lo de
  más de cada día desde el inicio de la bolsa, los movimientos a mano y
  el total); POST apunta o borra un movimiento (horas pagadas o
  compensadas, que restan, o añadidas) y devuelve el modal y el total
  del panel (fuera de banda).
- ClockWorkerTripView: POST corrige los kilómetros de un tramo con
  vehículo propio y repinta el listado con los filtros que se veían.
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from hr_calendar import clock_extras
from hr_calendar.models import OvertimeAdjustment, OwnVehicleTrip
from panel.mixins import SupervisorAccessMixin


def bag_context(person):
    """
    The bag of the worker, ready for the templates (None without account).
    ---
    La bolsa del trabajador para las plantillas; None si no tiene cuenta.
    """
    if person.company_user_id is None:
        return None
    bag = clock_extras.overtime_bag(
        person.company_user.company, person.company_user,
    )
    label = clock_extras.signed_duration
    return {
        **bag,
        # S143: cada mes, horas extra hasta el tope y acumuladas el resto.
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
        # S143 (convenio): desplazamiento (art. 22) y plazos.
        "travel_label": label(bag["travel_seconds"]),
        "deadline_rows": [{
            **d,
            "label": label(d["seconds"]),
            "euros": (clock_extras.TRAVEL_EUR_HOUR * d["seconds"] / 3600
                      if d["travel"] and d["state"] == "vencida" else None),
        } for d in bag["deadlines"]],
        "overdue": [d for d in bag["deadlines"] if d["state"]],
        "total_label": clock_extras.signed_duration(bag["total_seconds"]),
        "worked_label": clock_extras.signed_duration(bag["worked_seconds"]),
        "adjust_label": clock_extras.signed_duration(
            bag["adjust_minutes"] * 60),
        "rows": [{
            "item": a,
            "label": clock_extras.signed_duration(a.minutes * 60),
        } for a in bag["adjustments"]],
    }


def _parse_minutes(raw):
    """
    "3:30", "3,5" or "3.5" hours -> minutes; None if not valid.
    ---
    Horas escritas como h:mm o con decimales, en minutos.
    """
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


def _person(pk):
    from panel.views_clock_events import _person_or_404

    return _person_or_404(pk)


class ClockWorkerOvertimeView(SupervisorAccessMixin, View):
    """
    GET/POST the overtime bag of one worker.
    ---
    GET/POST la bolsa de horas extras de un trabajador.
    """

    def get(self, request, pk):
        return self._render(request, _person(pk))

    def post(self, request, pk):
        person = _person(pk)
        error = message = ""
        if person.company_user_id is None:
            error = "Sin cuenta en el panel: no tiene bolsa de horas."
        elif request.POST.get("action") == "delete":
            row = OvertimeAdjustment.objects.filter(
                pk=request.POST.get("adjustment") or 0,
                company_user_id=person.company_user_id,
            ).select_related("vacation_adjustment").first()
            deleted = 0
            if row is not None:
                # S143: unos días libres se borran con sus horas (y al
                # revés): el ajuste de vacaciones arrastra el movimiento.
                target = row.vacation_adjustment or row
                deleted, _rest = target.delete()
            message = "Movimiento borrado." if deleted else ""
            error = "" if deleted else "Ese movimiento ya no existe."
        else:
            minutes = _parse_minutes(request.POST.get("hours"))
            reason = (request.POST.get("reason") or "").strip()[:200]
            try:
                day = datetime.date.fromisoformat(
                    request.POST.get("date") or "")
            except ValueError:
                day = None
            if minutes is None:
                error = "Escribe las horas, por ejemplo 3:30 o 3,5."
            elif not reason:
                error = "Escribe el motivo."
            elif day is None:
                error = "Elige la fecha."
            else:
                if request.POST.get("sign") != "add":
                    minutes = -minutes
                OvertimeAdjustment.objects.create(
                    company_user_id=person.company_user_id, date=day,
                    minutes=minutes, reason=reason,
                    created_by=request.user.company_user,
                )
                message = "Movimiento apuntado."
        return self._render(request, person, error, message, oob=True)

    def _render(self, request, person, error="", message="", oob=False):
        return render(request, "panel/clock_worker/_overtime.html", {
            "person": person,
            "bag": bag_context(person),
            "today": timezone.localdate(),
            "error": error,
            "message": message,
            "oob": oob,
        })


def _table_response(request, person, message, error=False):
    """
    The worker's list repainted with the filters that were shown (_f_).
    ---
    La lista del trabajador repintada con los filtros que se veían.
    """
    from urllib.parse import quote

    from django.http import QueryDict

    from panel.views_clock_worker import FILTER_KEYS, _context

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
    response["X-Clock-Message"] = quote(message)
    if error:
        response["X-Clock-Error"] = "1"
    return response


class ClockWorkerReviewView(SupervisorAccessMixin, View):
    """
    POST: mark or unmark a worker's day as seen ("Visado").
    ---
    POST: marca o quita el visado de un día de fichajes del trabajador
    (S143): con incidencias y visado, en amarillo.
    """

    def post(self, request, pk):
        from hr_calendar.models import ClockDayReview

        person = _person(pk)
        try:
            day = datetime.date.fromisoformat(request.POST.get("day") or "")
        except ValueError:
            day = None
        if person.company_user_id is None or day is None:
            return _table_response(request, person, "No se ha podido "
                                   "visar ese día.", error=True)
        if request.POST.get("reviewed") == "1":
            ClockDayReview.objects.get_or_create(
                company_user_id=person.company_user_id, day=day,
                defaults={"reviewed_by": request.user.company_user},
            )
            message = "Día %s visado." % day.strftime("%d/%m/%Y")
        else:
            ClockDayReview.objects.filter(
                company_user_id=person.company_user_id, day=day,
            ).delete()
            message = "Quitado el visado del %s." % day.strftime("%d/%m/%Y")
        return _table_response(request, person, message)


class ClockWorkerTripView(SupervisorAccessMixin, View):
    """
    POST: correct the kilometres of an own-vehicle stretch.
    ---
    POST: corrige los kilómetros de un tramo con vehículo propio y
    repinta el listado (mismos filtros _f_ que las correcciones).
    """

    def post(self, request, pk):
        from urllib.parse import quote

        from django.http import QueryDict

        from panel.views_clock_worker import FILTER_KEYS, _context

        person = _person(pk)
        trip = OwnVehicleTrip.objects.filter(
            pk=request.POST.get("trip") or 0,
            start_event__company_user_id=person.company_user_id,
        ).first() if person.company_user_id else None
        raw = (request.POST.get("km") or "").strip().replace(",", ".")
        error = ""
        try:
            km = Decimal(raw).quantize(Decimal("0.1"))
        except InvalidOperation:
            km = None
        if trip is None:
            error = "Ese desplazamiento ya no existe."
        elif km is None or km < 0 or km > Decimal("5000"):
            error = "Escribe los kilómetros, por ejemplo 23,5."
        else:
            trip.km = km
            trip.error = ""
            trip.source = OwnVehicleTrip.SOURCE_MANUAL
            trip.corrected_by = request.user.company_user
            trip.save()
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
        response["X-Clock-Message"] = quote(
            error or "Kilómetros corregidos.")
        if error:
            response["X-Clock-Error"] = "1"
        return response
