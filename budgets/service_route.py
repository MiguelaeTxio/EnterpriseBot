# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_route.py
"""
Route of an albarán, with the stops of the vehicle (H37, S138).

Miguel Ángel: "ir guardándola para cuando termine el servicio poder
visualizar la ruta en el mapa con las detenciones que haya tenido el
vehículo". The driver app sends its position every minute while the
albarán is in progress (also the ones it kept without coverage); each
position is tied to its albarán (DriverPosition.unit).

A stop is a run of positions that stays within STOP_RADIUS_M of where
it began for at least STOP_MIN_MINUTES. The app only sends a new
position after moving ~50 m, so a stopped vehicle sends nothing: the
stop lasts until the first position away from it (if that one is
near; after a gap in coverage it ends at its last position).
Positions with a bad accuracy (> MAX_ACCURACY_M) are left out of the
route.

---

Ruta de un albarán con las detenciones del vehículo. Una detención es
un tramo de posiciones que no se aleja más de STOP_RADIUS_M de donde
empezó durante al menos STOP_MIN_MINUTES; dura hasta la primera
posición fuera de ese radio (parado, el móvil no manda nada).
"""
import datetime
import logging
import math

from django.utils import timezone

logger = logging.getLogger(__name__)

STOP_RADIUS_M = 150
# A stopped vehicle sends again after moving ~50 m: a first position
# farther than this after a gap is a gap in coverage, not a stop.
# Parado, el móvil vuelve a mandar al moverse ~50 m: una posición más
# lejos tras un hueco es falta de cobertura, no una detención.
LEAVE_MAX_M = 500
STOP_MIN_MINUTES = 3
MAX_ACCURACY_M = 150
NEAR_PLACE_M = 300
EARTH_RADIUS_M = 6371000


def distance_m(a, b):
    """
    Great-circle distance in metres between two (lat, lng).

    ---

    Distancia en metros entre dos (lat, lng).
    """
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _places(unit):
    """
    Known places to name the stops: pickup, destination and bases.

    ---

    Sitios conocidos para nombrar las detenciones: recogida, destino
    (coordenadas guardadas del servicio) y bases con coordenadas.
    """
    from budgets.models import Base
    from budgets.service_geocode import coordinates

    work_order = unit.work_order
    places = []
    for label, prefix in (("Recogida", "pickup"), ("Destino", "destination")):
        point = coordinates(work_order, prefix)
        if point is not None:
            places.append((label, point))
    for base in Base.objects.filter(
        company=work_order.company,
        latitude__isnull=False, longitude__isnull=False,
    ):
        places.append((
            "Base %s" % base.name,
            (float(base.latitude), float(base.longitude)),
        ))
    return places


def _place_name(point, places):
    """
    Name of the nearest known place within NEAR_PLACE_M, or "".

    ---

    Nombre del sitio conocido más cercano (a menos de NEAR_PLACE_M), o "".
    """
    best = None
    for label, place in places:
        meters = distance_m(point, place)
        if meters <= NEAR_PLACE_M and (best is None or meters < best[0]):
            best = (meters, label)
    return best[1] if best else ""


def find_stops(points):
    """
    Stops of a list of (lat, lng, recorded_at) in time order.

    ---

    Detenciones de una lista de (lat, lng, recorded_at) en orden: cada
    una con su centro, inicio, fin, minutos y los índices de sus puntos.
    """
    stops = []
    minimum = datetime.timedelta(minutes=STOP_MIN_MINUTES)
    i = 0
    n = len(points)
    while i < n:
        anchor = points[i][:2]
        j = i
        while j + 1 < n and distance_m(anchor, points[j + 1][:2]) <= (
            STOP_RADIUS_M
        ):
            j += 1
        leaving = points[j + 1] if j + 1 < n else None
        if leaving is not None and distance_m(anchor, leaving[:2]) <= (
            LEAVE_MAX_M
        ):
            end = leaving[2]
        else:
            end = points[j][2]
        if end - points[i][2] >= minimum:
            run = points[i:j + 1]
            stops.append({
                "lat": sum(p[0] for p in run) / len(run),
                "lng": sum(p[1] for p in run) / len(run),
                "start": points[i][2],
                "end": end,
                "minutes": round((end - points[i][2]).total_seconds() / 60),
            })
            i = j + 1
        else:
            i += 1
    return stops


def _bases(unit):
    """
    The company's bases with coordinates, as (name, (lat, lng)).

    ---

    Bases de la empresa con coordenadas, como (nombre, (lat, lng)).
    """
    from budgets.models import Base

    return [
        (base.name, (float(base.latitude), float(base.longitude)))
        for base in Base.objects.filter(
            company=unit.work_order.company,
            latitude__isnull=False, longitude__isnull=False,
        )
    ]


def _near_base(point, bases):
    """
    Name of the base the point is at (within NEAR_PLACE_M), or "".

    ---

    Nombre de la base en la que está el punto (a menos de
    NEAR_PLACE_M), o "".
    """
    for name, place in bases:
        if distance_m(point, place) <= NEAR_PLACE_M:
            return name
    return ""


def night_window(unit, points, bases=None):
    """
    The overnight stay in base of an albarán, or None.

    ---

    La pernocta en base (S138, Miguel Ángel): con pernocta, entre la
    llegada a la recogida y la firma, va de la primera posición en una
    base a la última en esa misma base antes de salir al destino. Lo de
    en medio no es trabajo (si el móvil va en el bolsillo, es el chófer
    yendo a casa). Devuelve (inicio, fin, nombre de la base) o None.
    """
    from budgets.assistance_traffic import _work_end

    if not unit.is_overnight or unit.arrived_at is None:
        return None
    bases = _bases(unit) if bases is None else bases
    if not bases:
        return None
    end_work = _work_end(unit)
    inside = [
        p for p in points
        if p[2] >= unit.arrived_at and (end_work is None or p[2] <= end_work)
    ]
    first = next(
        ((p, _near_base(p[:2], bases)) for p in inside
         if _near_base(p[:2], bases)),
        None,
    )
    if first is None:
        return None
    base_name = first[1]
    base_point = dict(bases)[base_name]
    last = max(
        (p for p in inside
         if p[2] >= first[0][2]
         and distance_m(p[:2], base_point) <= NEAR_PLACE_M),
        key=lambda p: p[2],
    )
    if last[2] <= first[0][2]:
        return None
    return first[0][2], last[2], base_name


def purge_night(unit_pk):
    """
    Delete the positions of the night of an overnight albarán.

    ---

    Borra las posiciones de la noche de un albarán con pernocta, al
    firmarlo (Miguel Ángel, S138: son del chófer fuera de servicio).
    Se quedan la llegada a la base y la salida de la mañana. Nunca
    lanza excepciones.
    """
    from budgets.models import DriverPosition, WorkOrderAssistanceUnit

    try:
        unit = WorkOrderAssistanceUnit.objects.select_related(
            "work_order",
        ).filter(pk=unit_pk).first()
        if unit is None:
            return 0
        points = _points(unit, all_accuracies=True)
        window = night_window(unit, points)
        if window is None:
            return 0
        deleted, _detail = DriverPosition.objects.filter(
            unit=unit, recorded_at__gt=window[0], recorded_at__lt=window[1],
        ).delete()
        return deleted
    except Exception:  # noqa: BLE001 -- nunca rompe la firma
        logger.exception(
            "# [RUTA] No se pudo limpiar la noche de %s.", unit_pk,
        )
        return 0


def _points(unit, all_accuracies=False):
    """
    (lat, lng, recorded_at) of an albarán's positions, in time order.

    ---

    Posiciones del albarán en orden; sin las de mala precisión, salvo
    que se pidan todas.
    """
    rows = unit.positions.order_by("recorded_at").values_list(
        "latitude", "longitude", "recorded_at", "accuracy_m",
    )
    return [
        (float(lat), float(lng), at)
        for lat, lng, at, accuracy in rows
        if all_accuracies or accuracy is None or accuracy <= MAX_ACCURACY_M
    ]


def _nearest(points, when):
    """
    The point nearest in time to `when`, or None.

    ---

    El punto más cercano en el tiempo a esa hora, o None.
    """
    if when is None or not points:
        return None
    return min(points, key=lambda p: abs((p[2] - when).total_seconds()))


def _hhmm(when):
    return timezone.localtime(when).strftime("%H:%M") if when else ""


def build_route(unit):
    """
    Route data of an albarán for the panel map.

    ---

    Datos de la ruta de un albarán para el mapa del panel (S138): cortada
    por los hitos del chófer, no por la geografía. Salida (hora de salida),
    llegada a la recogida (botón de llegada), entrega (la firma: el sitio
    donde se firmó, sea el destino previsto o no) y fin (la llegada a base
    que anota al cerrar, o la salida del siguiente si se encadenó en
    ruta). Con pernocta, la noche en base no cuenta. Tramos: ida a la
    recogida, con el vehículo (hasta la firma) y vuelta.
    """
    from budgets.assistance_traffic import _work_end
    from budgets.service_geocode import coordinates

    points = _points(unit)
    end_at = unit.chain_at if unit.chained_to_id else unit.base_arrived_at
    if end_at is not None:
        points = [p for p in points if p[2] <= end_at]
    bases = _bases(unit)
    night = night_window(unit, points, bases)
    if night is not None:
        points = [p for p in points if not night[0] < p[2] < night[1]]
    work_end = _work_end(unit)

    def leg(point):
        if unit.arrived_at is not None and point[2] < unit.arrived_at:
            return "ida"
        if work_end is not None and point[2] > work_end:
            return "vuelta"
        return "servicio" if unit.arrived_at is not None else "ida"

    segments = []
    for point in points:
        name = leg(point)
        after_night = (
            night is not None and segments
            and segments[-1]["points"][-1]["t"] <= night[0] < point[2]
        )
        if not segments or segments[-1]["leg"] != name or after_night:
            segments.append({"leg": name, "points": []})
        segments[-1]["points"].append({
            "lat": point[0], "lng": point[1], "t": point[2],
        })
    meters = sum(
        distance_m(
            (seg["points"][k]["lat"], seg["points"][k]["lng"]),
            (seg["points"][k + 1]["lat"], seg["points"][k + 1]["lng"]),
        )
        for seg in segments for k in range(len(seg["points"]) - 1)
    )
    for seg in segments:
        for point in seg["points"]:
            del point["t"]

    places = _places(unit)
    stops = []
    # The night is not a stop: the stops of each side, apart.
    # La noche no es una detención: las de cada lado, por separado.
    blocks = (
        [[p for p in points if p[2] <= night[0]],
         [p for p in points if p[2] >= night[1]]]
        if night else [points]
    )
    found = [stop for block in blocks for stop in find_stops(block)]
    for number, stop in enumerate(found, start=1):
        stops.append({
            "number": number,
            "lat": stop["lat"],
            "lng": stop["lng"],
            "start": _hhmm(stop["start"]),
            "end": _hhmm(stop["end"]),
            "minutes": stop["minutes"],
            "place": _place_name((stop["lat"], stop["lng"]), places),
        })

    milestones = []

    def milestone(kind, label, when, point):
        if point is not None:
            milestones.append({
                "kind": kind, "label": label, "time": _hhmm(when),
                "lat": point[0], "lng": point[1],
            })

    if points:
        milestone("start", "Salida", unit.started_at or points[0][2],
                  points[0])
    milestone("pickup", "Llegada a la recogida", unit.arrived_at,
              _nearest(points, unit.arrived_at))
    if work_end is not None:
        milestone(
            "delivery",
            "Entrega (firma)" if unit.completed_at else "Entrega (sin firma)",
            work_end, _nearest(points, work_end),
        )
    if points:
        if unit.chained_to_id:
            label = "Encadenado en ruta con %s" % (
                unit.chained_to.albaran_number
            )
        elif unit.base_arrived_at:
            label = "Llegada a base%s" % (
                " %s" % unit.arrival_base.name if unit.arrival_base_id else ""
            )
        else:
            label = "Última posición"
        milestone("end", label, end_at or points[-1][2], points[-1])

    work_order = unit.work_order
    marks = []
    for label, prefix in (
        ("Recogida prevista", "pickup"), ("Destino previsto", "destination"),
    ):
        point = coordinates(work_order, prefix)
        if point is not None:
            marks.append({"label": label, "lat": point[0], "lng": point[1]})
    first = timezone.localtime(points[0][2]) if points else None
    return {
        "path": [{"lat": p[0], "lng": p[1]} for p in points],
        "segments": segments,
        "milestones": milestones,
        "stops": stops,
        "marks": marks,
        "night": (
            {"base": night[2], "start": timezone.localtime(night[0]).strftime(
                "%d/%m %H:%M"), "end": timezone.localtime(night[1]).strftime(
                "%d/%m %H:%M")}
            if night else None
        ),
        "km": round(meters / 1000, 1),
        "start": first.strftime("%d/%m/%Y %H:%M") if first else "",
        "end": _hhmm(points[-1][2]) if points else "",
        "count": len(points),
        "stopped_minutes": sum(stop["minutes"] for stop in stops),
    }
