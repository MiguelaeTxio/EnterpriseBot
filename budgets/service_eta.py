# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_eta.py
"""
Time estimates of the assistance services.

For every albarán of a driver (the one he is doing and the queued
ones, in order) it estimates the arrival at the pickup and the end of
the service, from Google Routes travel times plus the working times
of the company (`AssistanceTimes`). For a new service it estimates
when each crew would reach its pickup, so the office (or Alia) can
give it to the one who arrives first, even if he is still busy.

---

Estimados de tiempo de los servicios de asistencia. H37 (S134),
Miguel Ángel: *"ver las horas y los kilómetros hasta el punto de
recogida [...] tener estos tiempos de finalización ya calculados una
vez que se lanzan los servicios, de tal forma que podamos asignar un
conductor [...] que se prevé que va a terminar"*.

- Trayectos con la Routes API de Google (matriz de rutas, con
  tráfico), con las direcciones tal cual las trae la orden.
- Tiempos de trabajo de la empresa: carga y descarga 30 min,
  reparación in situ 30 min, levantar un vehículo 60 min.
- Cola con vuelta a base: el siguiente sale de la base del conductor
  después de volver; desde donde esté: sale directo desde donde
  termina el anterior.
"""
import datetime
import json
import logging
import os
import urllib.error
import urllib.request
from decimal import Decimal

from django.utils import timezone

from budgets.dispatch_vehicle import ON_SITE_KINDS, job_for
from budgets.models import (
    AssistanceTimes,
    DriverPosition,
    WorkOrderAssistanceUnit,
)

logger = logging.getLogger(__name__)

Unit = WorkOrderAssistanceUnit
MATRIX_URL = (
    "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
)
MATRIX_TIMEOUT = 20
POSITION_MAX_AGE = datetime.timedelta(hours=12)
# Fields of the order that say what the job is (dispatch_vehicle).
# Campos de la orden que dicen qué trabajo es (dispatch_vehicle).
JOB_FIELDS = (
    "breakdown_description", "breakdown_code", "insurer_comments",
    "company_observations", "extra_notes", "vehicle_brand",
    "vehicle_model", "vehicle_type_label", "vehicle_subtype_label",
    "vehicle_weight", "vehicle_pma", "vehicle_tare", "repair_on_site",
)
JOB_ON_SITE = "on_site"
JOB_LIFT = "lift"
JOB_TOW = "tow"
# Albaranes already finished by the driver (returning or closed).
# Albaranes que el conductor ya ha terminado (regresando o cerrados).
DONE_STATUSES = (
    Unit.STATUS_COMPLETED, Unit.STATUS_CLOSED_UNSIGNED,
    Unit.STATUS_SIGNED_RECEIVED, Unit.STATUS_CLOSED_BASE,
    Unit.STATUS_CANCELLED,
)


class EtaError(Exception):
    """
    The estimate could not be computed.

    ---

    No se ha podido calcular el estimado (sin clave de Google, sin
    ruta o sin dirección).
    """


# ---------------------------------------------------------------------------
# Points and travel times.
# Puntos y tiempos de trayecto.
# ---------------------------------------------------------------------------

def _join(*parts):
    """
    Non-empty parts joined with commas.

    ---

    Las partes no vacías unidas con comas.
    """
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def pickup_address(work_order):
    """
    Full pickup address of an order, or "".

    ---

    Dirección completa de recogida de la orden, o "".
    """
    if not work_order.pickup_location:
        return ""
    return _join(
        work_order.pickup_location, work_order.vehicle_locality,
        work_order.pickup_province,
    )


def delivery_address(work_order):
    """
    Full delivery address of an order, or "" (repaired on the spot).

    ---

    Dirección completa de entrega de la orden, o "" (se queda in situ).
    """
    place = work_order.delivery_address or work_order.destination
    if not place:
        return ""
    return _join(
        place, work_order.delivery_locality, work_order.delivery_province,
    )


def address_point(address):
    """
    A point given by its address.

    ---

    Un punto dado por su dirección (la Routes API la sitúa).
    """
    return {"address": address, "label": address}


def base_point(base):
    """
    The point of a base, or None.

    ---

    El punto de una base: sus coordenadas o, si no tiene, su municipio.
    """
    if base is None:
        return None
    label = "base %s" % base.name
    if base.latitude is not None and base.longitude is not None:
        return {
            "lat": float(base.latitude), "lng": float(base.longitude),
            "label": label,
        }
    if base.municipality:
        return {"address": base.municipality, "label": label}
    return None


def driver_point(driver, now=None):
    """
    Where the driver is now: last GPS position or his base.

    ---

    Dónde está ahora el conductor: su última posición del móvil (de
    menos de 12 h) o, si no hay, su base.
    """
    now = now or timezone.now()
    position = DriverPosition.objects.filter(
        company_user=driver, recorded_at__gte=now - POSITION_MAX_AGE,
    ).order_by("-recorded_at").first()
    if position is not None:
        return {
            "lat": float(position.latitude),
            "lng": float(position.longitude),
            "label": "posición del móvil de las %s" % timezone.localtime(
                position.recorded_at,
            ).strftime("%H:%M"),
        }
    return base_point(getattr(driver, "base", None))


def _waypoint(point):
    """
    Routes API waypoint of a point.

    ---

    Waypoint de la Routes API para un punto (coordenadas o dirección).
    """
    if "lat" in point:
        return {"waypoint": {"location": {"latLng": {
            "latitude": point["lat"], "longitude": point["lng"],
        }}}}
    return {"waypoint": {"address": point["address"]}}


def _point_key(point):
    """
    Key of a point for the cache.

    ---

    Clave de un punto para la caché de trayectos.
    """
    if "lat" in point:
        return ("ll", round(point["lat"], 5), round(point["lng"], 5))
    return ("ad", point["address"].strip().lower())


class Router:
    """
    Travel times between points, with a cache for one calculation.

    ---

    Tiempos de trayecto entre puntos, con caché durante un cálculo
    (cada par de puntos se pide a Google una sola vez).
    """

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY", "")
        self.cache = {}

    def matrix(self, origins, destinations):
        """
        Travel (seconds, metres) for every origin and destination.

        ---

        Trayecto (segundos, metros) de cada origen a cada destino, en
        una sola llamada a la matriz de rutas. Los que no tienen ruta
        no salen.
        """
        wanted = [
            (o, d) for o in origins for d in destinations
            if (_point_key(o), _point_key(d)) not in self.cache
        ]
        if wanted:
            self._fetch(
                _unique(o for o, _d in wanted),
                _unique(d for _o, d in wanted),
            )
        return {
            (i, j): self.cache[(_point_key(o), _point_key(d))]
            for i, o in enumerate(origins)
            for j, d in enumerate(destinations)
            if self.cache.get((_point_key(o), _point_key(d)))
        }

    def leg(self, origin, destination):
        """
        Travel (seconds, metres) from one point to another.

        ---

        Trayecto (segundos, metros) de un punto a otro; EtaError si no
        hay ruta.
        """
        if _point_key(origin) == _point_key(destination):
            return 0, 0
        result = self.matrix([origin], [destination]).get((0, 0))
        if result is None:
            raise EtaError("No hay ruta de %s a %s." % (
                origin["label"], destination["label"],
            ))
        return result

    def _fetch(self, origins, destinations):
        """
        Ask Google for a route matrix and fill the cache.

        ---

        Pide la matriz de rutas a Google y llena la caché.
        """
        if not self.api_key:
            raise EtaError("Falta la clave de Google Maps del servidor.")
        body = json.dumps({
            "origins": [_waypoint(o) for o in origins],
            "destinations": [_waypoint(d) for d in destinations],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
        }).encode("utf-8")
        request = urllib.request.Request(
            MATRIX_URL, data=body, method="POST", headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "originIndex,destinationIndex,duration,"
                    "distanceMeters,condition,status"
                ),
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=MATRIX_TIMEOUT,
            ) as response:
                elements = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise EtaError("Google Routes respondió %s: %s" % (
                exc.code, detail,
            )) from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise EtaError("No se pudo consultar Google Routes: %s" % (
                exc,
            )) from exc
        for element in elements:
            origin = origins[element.get("originIndex", 0)]
            destination = destinations[element.get("destinationIndex", 0)]
            key = (_point_key(origin), _point_key(destination))
            if element.get("condition") != "ROUTE_EXISTS":
                self.cache[key] = None
                continue
            seconds = int(str(element.get("duration", "0s")).rstrip("s"))
            self.cache[key] = (seconds, int(element.get(
                "distanceMeters", 0,
            )))


def _unique(points):
    """
    Points without repetitions, in order.

    ---

    Puntos sin repetir, en orden.
    """
    seen, result = set(), []
    for point in points:
        key = _point_key(point)
        if key not in seen:
            seen.add(key)
            result.append(point)
    return result


# ---------------------------------------------------------------------------
# Plan of one service.
# Plan de un servicio.
# ---------------------------------------------------------------------------

def order_job(work_order):
    """
    Kind of job of an order: on site, lift or tow.

    ---

    Tipo de trabajo de la orden para el estimado: in situ (sin
    trayecto al destino), levantar o remolcar (dispatch_vehicle).
    """
    data = {
        field: getattr(work_order, field, None) for field in JOB_FIELDS
    }
    if work_order.vehicle_type_id:
        data["vehicle_type_name"] = work_order.vehicle_type.name
    job = job_for(data) or {"trabajos": []}
    kinds = job["trabajos"]
    if kinds and all(kind in ON_SITE_KINDS for kind in kinds):
        return JOB_ON_SITE
    if "lift" in kinds:
        return JOB_LIFT
    return JOB_TOW


def plan(unit, start_at, start_point, router, times):
    """
    Arrival at the pickup and end of one service.

    ---

    Llegada a la recogida y fin de un servicio que empieza en
    `start_at` desde `start_point`. Si el conductor ya ha llegado a la
    recogida (`arrived_at`), cuenta desde ahí. Devuelve un dict con
    pickup_at, finish_at, km, end_point y detail.
    """
    work_order = unit.work_order
    pickup = pickup_address(work_order)
    if not pickup:
        raise EtaError("La orden %s no tiene dirección de recogida." % (
            work_order.work_order_number,
        ))
    # S138: by its coordinates when the order has them.
    # Por sus coordenadas si la orden las tiene.
    from budgets.service_geocode import eta_point

    pickup_point = eta_point(work_order, "pickup")
    delivery = delivery_address(work_order)
    job = order_job(work_order)
    meters = 0
    if unit.arrived_at is not None:
        pickup_at = unit.arrived_at
        detail = ["en la recogida desde las %s" % timezone.localtime(
            unit.arrived_at,
        ).strftime("%H:%M")]
    else:
        seconds, meters = router.leg(start_point, pickup_point)
        pickup_at = start_at + datetime.timedelta(seconds=seconds)
        detail = ["desde %s" % start_point["label"]]
    if job == JOB_ON_SITE or not delivery:
        work = times.on_site_minutes if job == JOB_ON_SITE else (
            times.load_minutes
        )
        finish_at = pickup_at + datetime.timedelta(minutes=work)
        detail.append("%d min %s" % (work, (
            "de reparación in situ" if job == JOB_ON_SITE else "de carga"
        )))
        end_point = pickup_point
    else:
        first = times.lift_minutes if job == JOB_LIFT else times.load_minutes
        delivery_point = eta_point(work_order, "destination")
        seconds, transport = router.leg(pickup_point, delivery_point)
        meters += transport
        finish_at = pickup_at + datetime.timedelta(
            minutes=first + times.unload_minutes, seconds=seconds,
        )
        detail.append("%d min %s + %d min de descarga" % (
            first, "de levantar" if job == JOB_LIFT else "de carga",
            times.unload_minutes,
        ))
        end_point = delivery_point
    return {
        "pickup_at": pickup_at,
        "finish_at": finish_at,
        "km": Decimal(meters) / 1000,
        "end_point": end_point,
        "detail": "; ".join(detail),
    }


def driver_units(company, driver_id):
    """
    Albaranes of a driver still to finish, in the order he does them.

    ---

    Albaranes del conductor aún por terminar, en el orden en que los
    hará: primero el que tiene en curso, después los de la cola por
    orden de llegada.
    """
    from budgets.assistance_traffic import board_units

    units = list(board_units(company).filter(
        operator_id=driver_id,
    ).exclude(status__in=DONE_STATUSES).select_related(
        "work_order", "work_order__vehicle_type", "operator__base",
    ))
    active = [u for u in units if u.queued_at is None]
    queued = sorted(
        (u for u in units if u.queued_at is not None),
        key=lambda u: u.queued_at,
    )
    return active + queued


def refresh_driver(company, driver, router=None, now=None):
    """
    Recompute and save the estimates of a driver's albaranes.

    ---

    Recalcula y guarda los estimados de los albaranes pendientes del
    conductor, en cadena: cada uno empieza donde y cuando termina el
    anterior (con la vuelta a base si su cola es con vuelta a base).
    No falla nunca: si Google no responde, deja el motivo en el
    detalle del albarán.
    """
    now = now or timezone.now()
    router = router or Router()
    times = AssistanceTimes.for_company(company)
    start_at, start_point = now, None
    for unit in driver_units(company, driver.pk):
        try:
            if start_point is None:
                start_point = driver_point(driver, now)
                if start_point is None:
                    raise EtaError("%s no tiene posición ni base." % (
                        driver,
                    ))
            if unit.queued_at is not None and (
                unit.queue_mode == Unit.QUEUE_FROM_BASE
            ):
                base = base_point(getattr(driver, "base", None))
                if base is None:
                    raise EtaError("El conductor no tiene base.")
                seconds, _meters = router.leg(start_point, base)
                start_at += datetime.timedelta(seconds=seconds)
                start_point = base
            result = plan(unit, start_at, start_point, router, times)
        except EtaError as exc:
            logger.warning(
                "# [ETA] %s: %s", unit.albaran_number, exc,
            )
            unit.eta_pickup_at = unit.eta_finish_at = unit.eta_km = None
            unit.eta_end_place = ""
            unit.eta_detail = ("Sin estimado: %s" % exc)[:255]
            unit.eta_computed_at = now
            unit.save(update_fields=_ETA_FIELDS)
            # The next ones cannot be chained any more.
            # Los siguientes ya no se pueden encadenar.
            start_point = None
            start_at = now
            continue
        unit.eta_pickup_at = result["pickup_at"]
        unit.eta_finish_at = result["finish_at"]
        unit.eta_km = result["km"].quantize(Decimal("0.1"))
        unit.eta_end_place = result["end_point"]["label"][:255]
        unit.eta_detail = result["detail"][:255]
        unit.eta_computed_at = now
        unit.save(update_fields=_ETA_FIELDS)
        start_at, start_point = result["finish_at"], result["end_point"]


_ETA_FIELDS = [
    "eta_pickup_at", "eta_finish_at", "eta_km", "eta_end_place",
    "eta_detail", "eta_computed_at", "updated_at",
]


def refresh_driver_by_pk(company, driver_pk):
    """
    `refresh_driver` for a driver given by his pk (on_commit hooks).

    ---

    `refresh_driver` para un conductor dado por su pk (lo llaman los
    avisos tras el commit). Nunca lanza: un estimado que falla no
    puede romper una asignación ni un cambio de estado.
    """
    from ivr_config.models import CompanyUser

    try:
        driver = CompanyUser.objects.select_related("base").get(
            pk=driver_pk,
        )
        refresh_driver(company, driver)
    except Exception:  # noqa: BLE001 -- never break the caller
        logger.exception("# [ETA] No se pudo recalcular el conductor %s.",
                         driver_pk)


def schedule_refresh(company, driver_pk):
    """
    Recompute a driver's estimates after the current transaction.

    ---

    Recalcula los estimados del conductor cuando se confirme la
    transacción en curso.
    """
    from django.db import transaction

    if driver_pk:
        transaction.on_commit(
            lambda: refresh_driver_by_pk(company, driver_pk),
        )


# ---------------------------------------------------------------------------
# Who arrives first at a new pickup.
# Quién llega antes a una recogida nueva.
# ---------------------------------------------------------------------------

def _free_at(company, driver, now):
    """
    When and where a driver is free: now where he is, or at the end
    of his last pending albarán.

    ---

    Cuándo y dónde queda libre el conductor: ahora donde esté, o al
    terminar su último albarán pendiente (según su estimado).
    """
    pending = driver_units(company, driver.pk)
    if not pending:
        return now, driver_point(driver, now), True
    last = pending[-1]
    if last.eta_finish_at is None or not last.eta_end_place:
        return None, None, False
    # S138: the stored coordinates of the place where it ends.
    # Las coordenadas guardadas del sitio donde termina.
    from budgets.service_geocode import eta_point

    end_point = address_point(last.eta_end_place)
    for prefix in ("destination", "pickup"):
        point = eta_point(last.work_order, prefix)
        if point["label"][:255] == last.eta_end_place:
            end_point = point
            break
    return max(last.eta_finish_at, now), end_point, False


def arrivals(company, crews, pickup, router=None, now=None):
    """
    When each crew would reach a new pickup.

    ---

    Cuándo llegaría cada equipo a la recogida nueva: los libres desde
    donde están ahora; los ocupados al terminar lo que llevan, desde
    donde terminan (cola desde donde esté) y pasando por su base (cola
    con vuelta a base). De menos a más tiempo.
    """
    now = now or timezone.now()
    router = router or Router()
    pickup_point = address_point(pickup)
    rows = []
    for crew in crews:
        driver = crew.driver_card
        free_at, free_point, is_free = _free_at(company, driver, now)
        name = "%s con %s" % (driver.display_name, crew.machine_card.code)
        if free_point is None:
            rows.append({"equipo": name, "aviso": (
                "sin estimado de cuándo termina"
            )})
            continue
        try:
            seconds, meters = router.leg(free_point, pickup_point)
        except EtaError as exc:
            rows.append({"equipo": name, "aviso": str(exc)})
            continue
        arrive = free_at + datetime.timedelta(seconds=seconds)
        row = {
            "equipo": name,
            "libre": "ya" if is_free else timezone.localtime(
                free_at,
            ).strftime("%H:%M"),
            "desde": free_point["label"],
            "llegaria": timezone.localtime(arrive).strftime("%H:%M"),
            "km": round(meters / 1000),
            "_arrive": arrive,
        }
        if not is_free:
            row["cola"] = "desde donde esté"
            base = base_point(getattr(driver, "base", None))
            if base is not None:
                try:
                    to_base, _m1 = router.leg(free_point, base)
                    from_base, km_base = router.leg(base, pickup_point)
                    row["con_vuelta_a_base"] = timezone.localtime(
                        free_at + datetime.timedelta(
                            seconds=to_base + from_base,
                        ),
                    ).strftime("%H:%M")
                except EtaError:
                    pass
        rows.append(row)
    rows.sort(key=lambda r: r.get("_arrive") or datetime.datetime.max
              .replace(tzinfo=datetime.timezone.utc))
    for row in rows:
        row.pop("_arrive", None)
    return rows
