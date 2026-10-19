# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_geocode.py
"""
Municipality of a clock-in press (H24, S129): Miguel Ángel, "deberíamos
de indicar en los fichajes el municipio más cercano, si es posible, a
las coordenadas". Reverse geocoding with the same Google Maps key the
budgets already use (GOOGLE_MAPS_API_KEY).

Stored once in ClockEvent.municipality: "" when Google has no
municipality for the point, None while not asked yet (or after a
network error, so it is asked again later). Presses made at the same
spot reuse the answer of an earlier one (coordinates rounded to ~100 m),
so the workshop is asked to Google only once. Never blocks a clock-in:
any failure just leaves the field empty.

---

Municipio de una pulsación de fichaje (H24, S129), con la misma clave
de Google Maps que ya usan los presupuestos. Se guarda una vez en
ClockEvent.municipality ("" sin resultado; None sin consultar o tras un
error de red, para volver a intentarlo). Las pulsaciones hechas en el
mismo sitio (coordenadas a ~100 m) reutilizan la respuesta de otra, así
que el taller se pregunta a Google una sola vez. Nunca bloquea un
fichaje.
"""
import json
import logging
import os
import urllib.parse
import urllib.request

from hr_calendar.models import ClockEvent

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
TIMEOUT_SECONDS = 4
SAME_SPOT_DECIMALS = 3


def _component(result, kind):
    for component in result.get("address_components", []):
        if kind in component.get("types", []):
            return component.get("long_name", "")
    return ""


def municipality_for(latitude, longitude):
    """
    "Municipio (Provincia)" of a point, "" when Google has none, None on
    a network/API error.
    ---
    "Municipio (Provincia)" de un punto, "" si Google no tiene ninguno,
    None si falla la red o la API.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return None
    query = urllib.parse.urlencode({
        "latlng": "%s,%s" % (latitude, longitude),
        "language": "es",
        "key": api_key,
    })
    try:
        with urllib.request.urlopen(
            "%s?%s" % (GEOCODE_URL, query), timeout=TIMEOUT_SECONDS,
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("# [FICHAJE-MUNICIPIO] Error de red: %s", exc)
        return None
    status = data.get("status")
    if status == "ZERO_RESULTS":
        return ""
    if status != "OK":
        logger.warning(
            "# [FICHAJE-MUNICIPIO] Geocoding respondió %s: %s",
            status, data.get("error_message", ""),
        )
        return None
    for result in data.get("results", []):
        town = _component(result, "locality") or _component(
            result, "administrative_area_level_4",
        )
        if town:
            province = _component(result, "administrative_area_level_2")
            if province and province != town:
                return ("%s (%s)" % (town, province))[:150]
            return town[:150]
    return ""


def _same_spot(event):
    lat = round(float(event.latitude), SAME_SPOT_DECIMALS)
    lon = round(float(event.longitude), SAME_SPOT_DECIMALS)
    step = 0.5 / (10 ** SAME_SPOT_DECIMALS)
    return ClockEvent.objects.filter(
        latitude__gte=lat - step, latitude__lt=lat + step,
        longitude__gte=lon - step, longitude__lt=lon + step,
        municipality__isnull=False,
    ).exclude(municipality="").exclude(pk=event.pk).values_list(
        "municipality", flat=True,
    ).first()


def fill_municipality(event):
    """
    Sets and saves event.municipality if it has coordinates and was not
    asked yet. Returns the value (or None).
    ---
    Rellena y guarda event.municipality si tiene coordenadas y no se ha
    consultado todavía. Devuelve el valor (o None).
    """
    if event.municipality is not None or event.latitude is None:
        return event.municipality
    value = _same_spot(event)
    if value is None:
        value = municipality_for(event.latitude, event.longitude)
    if value is not None:
        event.municipality = value
        ClockEvent.objects.filter(pk=event.pk).update(municipality=value)
    return value


def fill_missing(events, limit=40):
    """
    fill_municipality for the presses still not asked, at most `limit`
    Google calls per request (the rest are filled on the next view).
    ---
    fill_municipality para las pulsaciones aún sin consultar, como
    mucho `limit` por petición (el resto, en la siguiente vista).
    """
    pending = [
        e for e in events
        if e is not None and e.latitude is not None and e.municipality is None
    ]
    for event in pending[:limit]:
        fill_municipality(event)
