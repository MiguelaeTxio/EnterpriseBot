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
import math

from django.utils import timezone

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


def build_route(unit):
    """
    Route data of an albarán for the panel map.

    ---

    Datos de la ruta de un albarán para el mapa del panel: la línea,
    las detenciones (con el sitio conocido si están en la recogida, el
    destino o una base), los km recorridos según el móvil, y la
    recogida y el destino del servicio.
    """
    from budgets.service_geocode import coordinates

    rows = unit.positions.order_by("recorded_at").values_list(
        "latitude", "longitude", "recorded_at", "accuracy_m",
    )
    points = [
        (float(lat), float(lng), at)
        for lat, lng, at, accuracy in rows
        if accuracy is None or accuracy <= MAX_ACCURACY_M
    ]
    meters = sum(
        distance_m(points[k][:2], points[k + 1][:2])
        for k in range(len(points) - 1)
    )
    places = _places(unit)
    stops = []
    for number, stop in enumerate(find_stops(points), start=1):
        stops.append({
            "number": number,
            "lat": stop["lat"],
            "lng": stop["lng"],
            "start": timezone.localtime(stop["start"]).strftime("%H:%M"),
            "end": timezone.localtime(stop["end"]).strftime("%H:%M"),
            "minutes": stop["minutes"],
            "place": _place_name((stop["lat"], stop["lng"]), places),
        })
    work_order = unit.work_order
    marks = []
    for label, prefix in (("Recogida", "pickup"), ("Destino", "destination")):
        point = coordinates(work_order, prefix)
        if point is not None:
            marks.append({"label": label, "lat": point[0], "lng": point[1]})
    first = timezone.localtime(points[0][2]) if points else None
    last = timezone.localtime(points[-1][2]) if points else None
    return {
        "path": [{"lat": p[0], "lng": p[1]} for p in points],
        "stops": stops,
        "marks": marks,
        "km": round(meters / 1000, 1),
        "start": first.strftime("%d/%m/%Y %H:%M") if first else "",
        "end": last.strftime("%H:%M") if last else "",
        "count": len(points),
        "stopped_minutes": sum(stop["minutes"] for stop in stops),
    }
