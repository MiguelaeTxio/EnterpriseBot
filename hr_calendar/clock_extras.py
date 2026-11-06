# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_extras.py
"""
Overtime bag, own-vehicle kilometres and meal breaks of the clock-in
(H24, S144).

---

Bolsa de horas extras, kilómetros con vehículo propio y pausas para
comer del fichaje (H24, S144). Decisiones de Miguel Ángel:

- Bolsa de horas: cada día suma lo trabajado POR ENCIMA de su horario;
  S143: cada mes, hasta el tope de la empresa (7 h) son horas extra y
  lo que pasa va a horas acumuladas;
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

# S143 (convenio, art. 23): "horas extraordinarias las horas de trabajo
# efectivo que excedan de la jornada en su cómputo mensual, es decir,
# días laborales del mes por ocho horas diarias".
DAILY_SECONDS = 8 * 3600


def month_overtime(shifts, required_day, date_from, date_to, today=None):
    """
    {first day of month: {"worked", "required", "excess"}} (seconds).
    ---
    Cómputo mensual del convenio (art. 23, S143): por cada mes del
    intervalo, el trabajo efectivo de las jornadas cerradas (lo que
    cuenta como jornada: ni presencia, ni desplazamiento, ni pausas) y
    la jornada del mes, días laborables (`required_day`) por 8 horas;
    lo que pasa son horas extra. Solo hasta hoy: el día de hoy cuenta
    cuando sus jornadas están cerradas, y uno con alguna abierta no
    cuenta ni lo trabajado ni la jornada.
    """
    today = today or timezone.localdate()
    by_day = {}
    for shift in shifts:
        if date_from <= shift.day <= date_to:
            by_day.setdefault(shift.day, []).append(shift)
    open_days = {day for day, same in by_day.items()
                 if any(s.clock_in is None or s.clock_out is None
                        for s in same)}
    result = {}

    def month(day):
        return result.setdefault(day.replace(day=1), {
            "worked": 0, "required": 0, "excess": 0})

    for day, same in by_day.items():
        if day not in open_days and day <= today:
            month(day)["worked"] += sum(s.seconds for s in same)
    day = date_from
    last = min(date_to, today)
    while day <= last:
        if day not in open_days and required_day(day) and (
                day < today or day in by_day):
            month(day)["required"] += DAILY_SECONDS
        day += datetime.timedelta(days=1)
    for values in result.values():
        values["excess"] = max(values["worked"] - values["required"], 0)
    return result


# S143 (convenio, art. 22): compensación del tiempo de desplazamiento
# por el radio entre el centro de trabajo (su base) y el puesto: más de
# 30 y hasta 60 km, 1 hora; más de 60 y hasta 130, 2 horas; más de 130,
# dieta. Se compensan con descanso (1 por 1); si pasa un trimestre sin
# compensar, se pagan a 6 €/hora. Con vehículo propio, 0,19 €/km.
TRAVEL_BANDS = ((30, 60, 1), (60, 130, 2))
TRAVEL_ALLOWANCE_KM = 130
TRAVEL_EUR_HOUR = Decimal("6")
OWN_VEHICLE_EUR_KM = Decimal("0.19")
# Art. 19: los excesos de jornada se compensan "cada seis meses como
# máximo"; art. 22: las de desplazamiento, en un trimestre.
OVERTIME_DEADLINE_MONTHS = 6
TRAVEL_DEADLINE_MONTHS = 3


def travel_by_day(shifts, base, today=None):
    """
    {day: {"km", "hours", "allowance"}} of the closed days away from base.
    ---
    S143 (convenio, art. 22): por cada día con sus jornadas cerradas, el
    radio (en línea recta) entre su base y el punto más lejano en que
    fichó ese día (pulsaciones con GPS), y lo que le corresponde: 1 o 2
    horas de desplazamiento, o dieta a partir de 130 km. Sin base con
    coordenadas o sin GPS, nada.
    """
    if base is None:
        return {}
    today = today or timezone.localdate()
    by_day = {}
    for shift in shifts:
        by_day.setdefault(shift.day, []).append(shift)
    result = {}
    for day, same in by_day.items():
        if day > today or any(s.clock_in is None or s.clock_out is None
                              for s in same):
            continue
        points = [
            (float(e.latitude), float(e.longitude))
            for s in same
            for e in [s.clock_in] + list(s.changes) + [s.clock_out]
            if e is not None and getattr(e, "latitude", None) is not None
            and getattr(e, "longitude", None) is not None
        ]
        if not points:
            continue
        km = max(_meters(lat, lon, base[0], base[1])
                 for lat, lon in points) / 1000
        hours = next((h for low, high, h in TRAVEL_BANDS
                      if low < km <= high), 0)
        allowance = km > TRAVEL_ALLOWANCE_KM
        if hours or allowance:
            result[day] = {"km": km, "hours": hours,
                           "allowance": allowance}
    return result


def _add_months(day, months):
    year, month = divmod(day.month - 1 + months, 12)
    return datetime.date(day.year + year, month + 1, 1)


def bag_deadlines(months, travel_months, adjustments, today=None):
    """
    The accumulated hours still to compensate, oldest first, with their
    deadline.
    ---
    S143 (convenio): lo que queda por compensar de la bolsa, por mes y
    tipo, gastando las horas compensadas (movimientos que restan, días
    libres) de lo más antiguo a lo más nuevo. Cada fila: mes, tipo
    ("Horas extra" o "Desplazamiento"), horas que quedan, fecha límite
    (6 meses las extra, art. 19; un trimestre las de desplazamiento,
    art. 22) y estado: "vencida", "vence pronto" (este mes) o "".
    """
    today = today or timezone.localdate()
    ledger = []
    for m in months:
        if m["accumulated"]:
            ledger.append([m["month"], 0, "Horas extra", m["accumulated"],
                           OVERTIME_DEADLINE_MONTHS])
    for month, seconds in sorted(travel_months.items()):
        if seconds:
            ledger.append([month, 1, "Desplazamiento", seconds,
                           TRAVEL_DEADLINE_MONTHS])
    for a in adjustments:
        if a.minutes > 0:
            ledger.append([a.date.replace(day=1), 2, "Añadidas a mano",
                           a.minutes * 60, OVERTIME_DEADLINE_MONTHS])
    ledger.sort(key=lambda row: (row[0], row[1]))
    spend = -sum(a.minutes for a in adjustments if a.minutes < 0) * 60
    rows = []
    for month, _order, kind, seconds, limit in ledger:
        used = min(seconds, spend)
        spend -= used
        left = seconds - used
        if not left:
            continue
        deadline = _add_months(month, limit + 1) - datetime.timedelta(days=1)
        if deadline < today:
            state = "vencida"
        elif deadline < _add_months(today, 1):
            state = "vence pronto"
        else:
            state = ""
        rows.append({"month": month, "kind": kind, "seconds": left,
                     "deadline": deadline, "state": state,
                     "travel": kind == "Desplazamiento"})
    return rows


def monthly_cap_seconds(company):
    """
    The company's monthly overtime cap, in seconds.
    ---
    El tope de horas extra al mes de la empresa (S143, Miguel Ángel: 7
    horas por defecto), en segundos.
    """
    from hr_calendar.models import ClockSettings

    minutes = ClockSettings.objects.filter(company=company).values_list(
        "overtime_monthly_cap_minutes", flat=True).first()
    if minutes is None:
        minutes = ClockSettings.DEFAULT_OVERTIME_CAP_MINUTES
    return minutes * 60


def split_by_month(month_excess, cap_seconds, months=None):
    """
    The monthly overtime split at the monthly cap.
    ---
    Las horas extra de cada mes (S143, cómputo mensual del convenio)
    partidas por el tope: hasta el tope, cupo; lo que pasa, bolsa. Lista
    ordenada de {"month", "excess", "extra", "accumulated", "worked",
    "required"} (segundos; trabajado y jornada si se pasan `months`).
    """
    months = months or {}
    by_month = {}
    for day, seconds in month_excess.items():
        month = day.replace(day=1)
        by_month[month] = by_month.get(month, 0) + seconds
    return [
        {
            "month": month,
            "excess": total,
            "extra": min(total, cap_seconds),
            "accumulated": max(total - cap_seconds, 0),
            "worked": months.get(month, {}).get("worked", 0),
            "required": months.get(month, {}).get("required", 0),
        }
        for month, total in sorted(by_month.items())
    ]


def overtime_bag(company, company_user, until=None):
    """
    The worker's overtime: monthly extra hours up to the cap and the
    accumulated hours above it, plus manual movements.
    ---
    Las horas de más de un trabajador desde BAG_START hasta `until`
    (hoy). S143 (Miguel Ángel): cada mes, hasta el tope son horas extra
    y lo que pasa del tope va a horas acumuladas; los movimientos a mano
    (horas compensadas o días libres, añadidas) mueven las acumuladas.
    Devuelve un dict con los segundos de los días, los meses, el tope,
    los minutos de los movimientos, el total acumulado en segundos y la
    lista de movimientos.
    """
    from hr_calendar.clock_report import reports_by_user
    from hr_calendar.models import OvertimeAdjustment

    until = until or timezone.localdate()
    report = reports_by_user(
        company, [company_user.pk], BAG_START, until,
    ).get(company_user.pk)
    cap = monthly_cap_seconds(company)
    months = split_by_month(
        report.month_excess if report is not None else {}, cap,
        report.months if report is not None else None,
    )
    worked = sum(m["excess"] for m in months)
    accumulated = sum(m["accumulated"] for m in months)
    adjustments = list(OvertimeAdjustment.objects.filter(
        company_user=company_user, date__gte=BAG_START,
    ).select_related("created_by__user"))
    moved = sum(a.minutes for a in adjustments)
    # S143 (convenio, art. 22): horas de desplazamiento por mes.
    travel_months = {}
    for day, item in (report.travel if report is not None else {}).items():
        month = day.replace(day=1)
        travel_months[month] = (travel_months.get(month, 0)
                                + item["hours"] * 3600)
    travel = sum(travel_months.values())
    deadlines = bag_deadlines(months, travel_months, adjustments)
    return {
        "travel_seconds": travel,
        "travel_months": travel_months,
        "deadlines": deadlines,
        "worked_seconds": worked,
        "extra_seconds": sum(m["extra"] for m in months),
        "accumulated_seconds": accumulated,
        "months": months,
        "cap_seconds": cap,
        "adjust_minutes": moved,
        "total_seconds": accumulated + travel + moved * 60,
        "adjustments": adjustments,
        "since": BAG_START,
    }


def overtime_bags(company, company_user_ids, until=None):
    """
    {company_user_id: accumulated hours in seconds} of several workers.
    ---
    Las horas acumuladas de varios trabajadores de una vez (S145,
    columna del listado de Fichajes): mismo cálculo que overtime_bag (lo
    que pasa del tope cada mes desde BAG_START hasta `until` y los
    movimientos a mano), con una sola lectura de fichajes y de
    movimientos.
    """
    from django.db.models import Sum

    from hr_calendar.clock_report import reports_by_user
    from hr_calendar.models import OvertimeAdjustment

    ids = [pk for pk in company_user_ids if pk]
    if not ids:
        return {}
    until = until or timezone.localdate()
    reports = reports_by_user(company, ids, BAG_START, until)
    cap = monthly_cap_seconds(company)
    moved = dict(
        OvertimeAdjustment.objects.filter(
            company_user_id__in=ids, date__gte=BAG_START,
        ).values("company_user_id").annotate(
            total=Sum("minutes"),
        ).values_list("company_user_id", "total")
    )
    result = {}
    for pk in ids:
        months = split_by_month(
            reports[pk].month_excess if pk in reports else {}, cap,
        )
        result[pk] = (sum(m["accumulated"] for m in months)
                      + (moved.get(pk) or 0) * 60)
    return result


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
