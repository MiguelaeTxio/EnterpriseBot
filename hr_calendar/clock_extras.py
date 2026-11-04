# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_extras.py
"""
Overtime bag, own-vehicle kilometres and meal breaks of the clock-in
(H24, S144).

---

Bolsa de horas extras, kilómetros con vehículo propio y pausas para
comer del fichaje (H24, S144). Decisiones de Miguel Ángel:

- Bolsa de horas: cada día suma lo trabajado POR ENCIMA de su horario;
  los días de menos no restan. En sábados, domingos y festivos que no
  trabaja, todo lo trabajado es extra. Sin horario, o con horario
  abierto, no hay horas previstas y no se calcula. Solo días cerrados
  (todas sus jornadas con salida). Empieza el BAG_START; el supervisor
  apunta movimientos a mano (horas pagadas o compensadas,
  OvertimeAdjustment).
- Vehículo propio: el operario elige "Desplazamiento con mi vehículo";
  al cerrar ese tramo se calculan los kilómetros por carretera (Google
  Routes, como los presupuestos) entre el GPS de la pulsación que lo
  abre y el de la que lo cierra (OwnVehicleTrip). El supervisor los
  puede corregir.
- Pausa para comer: un único tipo; según la hora a la que empieza es
  comida (MEAL_LUNCH) o cena (MEAL_DINNER); fuera de esas horas (un
  desayuno) no cuenta. Cuenta para dietas si en ese momento el
  trabajador está desplazado: su GPS a más de BASE_RADIUS_M de todas
  las bases de la empresa (budgets.Base con coordenadas). "De momento
  lo ponemos como si fuese a contar [...] por lo menos que cuente para
  dietas."
"""
import datetime
import logging
import math
import os
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

BAG_START = datetime.date(2026, 1, 1)
# Hora de inicio de la pausa: [desde, hasta).
MEAL_LUNCH = (datetime.time(12, 0), datetime.time(17, 0))
MEAL_DINNER = (datetime.time(19, 0), datetime.time(23, 59, 59))
LUNCH = "Comida"
DINNER = "Cena"
BASE_RADIUS_M = 1000
MAX_TRIPS_PER_RENDER = 20


# ---------------------------------------------------------------------------
# Bolsa de horas extras
# ---------------------------------------------------------------------------

def _scheduled_seconds(starts, ends):
    """
    Planned seconds of a day from its start and end times.
    ---
    Segundos previstos de un día: cada entrada con su salida (mañana y,
    en jornada partida, tarde); una salida antes de su entrada es del
    día siguiente (turno de noche).
    """
    total = 0
    for start, end in zip(sorted(starts), sorted(ends)):
        minutes = (end.hour * 60 + end.minute) - (
            start.hour * 60 + start.minute)
        if minutes <= 0:
            minutes += 24 * 60
        total += minutes * 60
    return total


def day_excess(shifts, times_of, is_day_compared, has_hours):
    """
    {day: seconds worked above the schedule} of one worker's shifts.
    ---
    {día: segundos trabajados por encima del horario}. Solo días con
    todas las jornadas cerradas y con algo de más; {} sin horario o con
    horario abierto.
    """
    if not has_hours:
        return {}
    by_day = {}
    for shift in shifts:
        by_day.setdefault(shift.day, []).append(shift)
    result = {}
    for day, same in by_day.items():
        if any(s.clock_in is None or s.clock_out is None for s in same):
            continue
        worked = sum(s.seconds for s in same)
        planned = 0
        if is_day_compared(day):
            starts, ends = times_of(day)
            planned = _scheduled_seconds(starts, ends)
        if worked > planned:
            result[day] = worked - planned
    return result


def overtime_bag(company, company_user, until=None):
    """
    The worker's overtime bag: daily excess since BAG_START plus manual
    movements.
    ---
    La bolsa de un trabajador: lo de más de cada día desde BAG_START
    hasta `until` (hoy) y los movimientos a mano. Devuelve un dict con
    los segundos de los días, los minutos de los movimientos, el total
    en segundos y la lista de movimientos.
    """
    from hr_calendar.clock_report import reports_by_user
    from hr_calendar.models import OvertimeAdjustment

    until = until or timezone.localdate()
    report = reports_by_user(
        company, [company_user.pk], BAG_START, until,
    ).get(company_user.pk)
    worked = report.excess_seconds if report is not None else 0
    adjustments = list(OvertimeAdjustment.objects.filter(
        company_user=company_user, date__gte=BAG_START,
    ).select_related("created_by__user"))
    moved = sum(a.minutes for a in adjustments)
    total = worked + moved * 60
    return {
        "worked_seconds": worked,
        "adjust_minutes": moved,
        "total_seconds": total,
        "adjustments": adjustments,
        "since": BAG_START,
    }


def signed_duration(seconds):
    """
    "-3:15" / "12:40" (h:mm with sign).
    ---
    Duración h:mm con signo.
    """
    sign = "-" if seconds < 0 else ""
    seconds = abs(int(seconds))
    return "%s%d:%02d" % (sign, seconds // 3600, seconds % 3600 // 60)


# ---------------------------------------------------------------------------
# Pausas para comer y dietas
# ---------------------------------------------------------------------------

def meal_kind(moment):
    """
    LUNCH, DINNER or None by the local start time of the break.
    ---
    Comida o cena según la hora local a la que empieza la pausa; None
    fuera de esas horas (un desayuno no cuenta).
    """
    local = timezone.localtime(moment).time()
    if MEAL_LUNCH[0] <= local < MEAL_LUNCH[1]:
        return LUNCH
    if MEAL_DINNER[0] <= local <= MEAL_DINNER[1]:
        return DINNER
    return None


def company_bases(company):
    """
    [(name, lat, lon)] of the company's bases with coordinates.
    ---
    Las bases de la empresa que tienen coordenadas.
    """
    from budgets.models import Base

    return [
        (name, float(lat), float(lon))
        for name, lat, lon in Base.objects.filter(
            company=company, latitude__isnull=False,
            longitude__isnull=False,
        ).values_list("name", "latitude", "longitude")
    ]


def _meters(lat1, lon1, lat2, lon2):
    radius = 6371000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_base(lat, lon, bases):
    """
    (name, meters) of the closest base, or (None, None).
    ---
    La base más cercana y a cuántos metros.
    """
    best = (None, None)
    for name, base_lat, base_lon in bases:
        meters = _meters(lat, lon, base_lat, base_lon)
        if best[1] is None or meters < best[1]:
            best = (name, meters)
    return best


def shift_meals(shift, bases):
    """
    The meal breaks of a shift, each with its kind and whether it
    counts for allowances.
    ---
    Las pausas para comer de una jornada: hora, minutos, comida o cena
    (o None), si cuenta para dietas y por qué.
    """
    meals = []
    for mark, end in shift.meal_segments:
        kind = meal_kind(mark.pressed_at)
        item = {
            "start": timezone.localtime(mark.pressed_at),
            "minutes": max(int((end - mark.pressed_at).total_seconds())
                           // 60, 0),
            "kind": kind,
            "allowance": False,
            "note": "",
        }
        if kind is None:
            item["note"] = "fuera de las horas de comida y cena"
        elif mark.latitude is None or mark.longitude is None:
            item["note"] = "sin GPS: no se sabe si estaba desplazado"
        elif not bases:
            item["note"] = "no hay bases con coordenadas"
        else:
            name, meters = nearest_base(
                float(mark.latitude), float(mark.longitude), bases,
            )
            if meters > BASE_RADIUS_M:
                item["allowance"] = True
                item["note"] = "desplazado (a %.1f km de %s)" % (
                    meters / 1000, name)
            else:
                item["note"] = "en la base de %s" % name
        meals.append(item)
    return meals


def meal_totals(shifts, bases):
    """
    {"Comida": n, "Cena": n} of the breaks that count for allowances.
    ---
    Comidas y cenas que cuentan para dietas.
    """
    totals = {LUNCH: 0, DINNER: 0}
    for shift in shifts:
        for meal in shift_meals(shift, bases):
            if meal["allowance"]:
                totals[meal["kind"]] += 1
    return totals


# ---------------------------------------------------------------------------
# Vehículo propio
# ---------------------------------------------------------------------------

def _is_own_travel(event):
    from hr_calendar.models import ClockType

    return bool(
        event is not None and event.own_vehicle
        and event.clock_type is not None
        and event.clock_type.role == ClockType.ROLE_TRAVEL
    )


def _route_km(start_event, end_event):
    """
    (km, error) by road between the GPS of two presses.
    ---
    Kilómetros por carretera (Google Routes) entre el GPS de dos
    pulsaciones; (None, motivo) si falta GPS o falla la consulta.
    """
    if start_event.latitude is None or end_event.latitude is None:
        return None, "Falta el GPS al empezar o al terminar el tramo"
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return None, "GOOGLE_MAPS_API_KEY no configurada"
    from budgets.services import _call_routes_api

    try:
        result = _call_routes_api(
            float(start_event.latitude), float(start_event.longitude),
            float(end_event.latitude), float(end_event.longitude),
            "", api_key, include_traffic=False,
        )
    except Exception as error:  # noqa: BLE001 -- nunca tumba el fichaje
        logger.warning("# [FICHAJE-KM] Fallo de Routes: %s", error)
        return None, ("No se pudo calcular la ruta: %s" % error)[:200]
    return Decimal(str(result["distance_km"])).quantize(Decimal("0.1")), ""


def record_trip(start_event, end_event):
    """
    Create or refresh the trip of an own-vehicle stretch (never one
    corrected by hand).
    ---
    Crea o recalcula el desplazamiento de un tramo con vehículo propio;
    nunca pisa uno corregido a mano.
    """
    from hr_calendar.models import OwnVehicleTrip

    trip = OwnVehicleTrip.objects.filter(start_event=start_event).first()
    if trip is not None and trip.source == OwnVehicleTrip.SOURCE_MANUAL:
        return trip
    km, error = _route_km(start_event, end_event)
    if trip is None:
        trip = OwnVehicleTrip(start_event=start_event)
    trip.end_event = end_event
    trip.km = km
    trip.error = error
    trip.source = OwnVehicleTrip.SOURCE_ROUTES
    trip.save()
    return trip


def on_press(event):
    """
    After a press that closes a stretch: kilometres of the stretch if it
    was in the worker's own vehicle.
    ---
    Tras una pulsación que cierra un tramo (cambio de tipo o salida):
    si el tramo que cierra era con vehículo propio, sus kilómetros.
    """
    from hr_calendar.models import ClockEvent

    if event.kind not in (ClockEvent.Kind.CHANGE, ClockEvent.Kind.OUT):
        return None
    opener = ClockEvent.objects.current().filter(
        company_user_id=event.company_user_id,
        pressed_at__lt=event.pressed_at,
        kind__in=(ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE),
    ).select_related("clock_type").order_by("-pressed_at", "-pk").first()
    if not _is_own_travel(opener):
        return None
    return record_trip(opener, event)


def new_budget():
    """Missing trips that one render may calculate (MAX_TRIPS_PER_RENDER)."""
    return {"left": MAX_TRIPS_PER_RENDER}


def shift_trips(shift, budget=None):
    """
    The own-vehicle stretches of a shift with their kilometres.
    ---
    Los tramos con vehículo propio de una jornada; calcula los que
    falten (como el municipio, hasta MAX_TRIPS_PER_RENDER por vez).
    """
    from hr_calendar.models import OwnVehicleTrip

    trips = []
    marks = [(m, e) for m, e in shift.segment_marks if _is_own_travel(m)]
    if not marks:
        return trips
    known = {
        t.start_event_id: t for t in OwnVehicleTrip.objects.filter(
            start_event__in=[m for m, _e in marks],
        ).select_related("corrected_by__user")
    }
    ends = {m.pk: end for m, end in shift.segment_marks}
    closers = [c for c in list(shift.changes) + [shift.clock_out] if c]
    for mark, end in marks:
        trip = known.get(mark.pk)
        if trip is None and budget is not None and budget["left"] > 0:
            closer = next(
                (c for c in closers if c.pressed_at == ends[mark.pk]), None)
            if closer is not None:
                budget["left"] -= 1
                trip = record_trip(mark, closer)
        trips.append({
            "start": timezone.localtime(mark.pressed_at),
            "end": timezone.localtime(end),
            "trip": trip,
            "km": trip.km if trip is not None else None,
            "error": trip.error if trip is not None else "",
        })
    return trips


def km_total(trips):
    return sum((t["km"] for t in trips if t["km"] is not None), Decimal("0"))
