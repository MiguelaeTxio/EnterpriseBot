# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_geocode.py
"""
Coordinates of the pickup and the destination of a service (H37, S138).

Miguel Ángel chose the complete option: "guardar las coordenadas de la
recogida y del destino al dar de alta el servicio". The full address
(the same text the ETA uses) is geocoded once with Google Geocoding
(GOOGLE_MAPS_API_KEY, as hr_calendar.clock_geocode) and kept in the
order with the text it came from; when the address changes, it is
geocoded again. The coordinates feed:
- the "Cómo llegar" buttons of the drivers' app (Google Maps URLs),
- the Maps links of the service message in the Asistencia room,
- the board map and the estimated times (Routes API by coordinates).
Never blocks anything: without key, network or result, the address
text is used as before.

---

Coordenadas de la recogida y del destino de un servicio (H37, S138).
Se geocodifica una vez la dirección completa (la misma que usan los
estimados) y se guarda con el texto del que salió; si la dirección
cambia, se vuelve a geocodificar. Alimentan los botones "Cómo llegar"
de la app, los enlaces de Maps de la sala, el mapa del tablero y los
estimados. Nunca bloquea: sin clave, red o resultado, se usa el texto.
"""
import json
import logging
import os
import urllib.parse
import urllib.request
from decimal import Decimal

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
MAPS_DIR_URL = "https://www.google.com/maps/dir/?api=1&destination=%s"
TIMEOUT_SECONDS = 4
COORD_PLACES = Decimal("0.000001")


def geocode(address):
    """
    (lat, lng) of an address in Spain, or None.

    ---

    (lat, lng) de una dirección en España, o None si no hay clave,
    falla la red o Google no la encuentra.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not address or not api_key:
        return None
    query = urllib.parse.urlencode({
        "address": address,
        "region": "es",
        "language": "es",
        "key": api_key,
    })
    try:
        with urllib.request.urlopen(
            "%s?%s" % (GEOCODE_URL, query), timeout=TIMEOUT_SECONDS,
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 -- nunca bloquea
        logger.warning("# [SERVICIO-COORDENADAS] Error de red: %s", exc)
        return None
    status = data.get("status")
    if status != "OK":
        if status != "ZERO_RESULTS":
            logger.warning(
                "# [SERVICIO-COORDENADAS] Geocoding respondió %s: %s",
                status, data.get("error_message", ""),
            )
        return None
    location = data["results"][0]["geometry"]["location"]
    return (
        Decimal(str(location["lat"])).quantize(COORD_PLACES),
        Decimal(str(location["lng"])).quantize(COORD_PLACES),
    )


def _fields(work_order):
    """
    (prefix, current full address) of the two points of an order.

    ---

    (prefijo, dirección completa actual) de los dos puntos de la orden.
    """
    from budgets.service_eta import delivery_address, pickup_address

    return (
        ("pickup", pickup_address(work_order)),
        ("destination", delivery_address(work_order)),
    )


def ensure_points(work_order):
    """
    Geocode the points whose address changed since the last time.

    ---

    Geocodifica los puntos cuya dirección cambió desde la última vez
    (o que nunca se geocodificaron). Guarda con update() para no
    disparar otra vez las señales. Devuelve True si cambió algo.
    """
    from budgets.models import WorkOrderAssistance

    changes = {}
    for prefix, address in _fields(work_order):
        if address == getattr(work_order, prefix + "_geocoded"):
            continue
        point = geocode(address)
        if address and point is None:
            # Sin resultado o sin red: se intentará en el próximo cambio
            # y, mientras, se usa el texto.
            # No result or no network: retried on the next change.
            changes[prefix + "_latitude"] = None
            changes[prefix + "_longitude"] = None
            changes[prefix + "_geocoded"] = ""
            continue
        changes[prefix + "_latitude"] = point[0] if point else None
        changes[prefix + "_longitude"] = point[1] if point else None
        changes[prefix + "_geocoded"] = address
    if not changes:
        return False
    WorkOrderAssistance.objects.filter(pk=work_order.pk).update(**changes)
    for name, value in changes.items():
        setattr(work_order, name, value)
    return True


def ensure_points_by_pk(work_order_pk):
    """
    ensure_points for a primary key; never raises.

    ---

    ensure_points por clave primaria; nunca lanza excepciones.
    """
    from budgets.models import WorkOrderAssistance

    work_order = WorkOrderAssistance.objects.filter(pk=work_order_pk).first()
    if work_order is None:
        return
    try:
        ensure_points(work_order)
    except Exception:  # noqa: BLE001 -- nunca rompe el guardado
        logger.exception(
            "# [SERVICIO-COORDENADAS] No se pudo geocodificar la orden %s.",
            work_order_pk,
        )


def coordinates(work_order, prefix):
    """
    (lat, lng) floats of a point, only if they belong to its address.

    ---

    (lat, lng) de un punto, solo si son de la dirección actual (si la
    dirección cambió y aún no se ha vuelto a geocodificar, None).
    """
    address = dict(_fields(work_order))[prefix]
    latitude = getattr(work_order, prefix + "_latitude")
    longitude = getattr(work_order, prefix + "_longitude")
    if (
        not address or latitude is None or longitude is None
        or getattr(work_order, prefix + "_geocoded") != address
    ):
        return None
    return float(latitude), float(longitude)


def eta_point(work_order, prefix):
    """
    Routes API point of the pickup or the destination.

    ---

    Punto para la Routes API: por coordenadas si las hay; si no, por la
    dirección, como antes.
    """
    address = dict(_fields(work_order))[prefix]
    coords = coordinates(work_order, prefix)
    if coords is None:
        return {"address": address, "label": address}
    return {"lat": coords[0], "lng": coords[1], "label": address}


def maps_url(work_order, prefix):
    """
    Google Maps navigation URL to a point, or "".

    ---

    Enlace de Google Maps para ir al punto: por coordenadas si las hay;
    si no, por la dirección. Una recogida en base va a la base.
    """
    if prefix == "pickup" and work_order.base_pickup:
        base = work_order.base if work_order.base_id else None
        if base is not None and base.latitude is not None:
            return MAPS_DIR_URL % ("%s,%s" % (base.latitude, base.longitude))
    coords = coordinates(work_order, prefix)
    if coords is not None:
        return MAPS_DIR_URL % ("%.6f,%.6f" % coords)
    address = dict(_fields(work_order))[prefix]
    if not address:
        return ""
    return MAPS_DIR_URL % urllib.parse.quote(address)
