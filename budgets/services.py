# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/services.py
"""
Budget calculation engine for the ASISTENCIA section.
Applies insurer tariff lines to operator input data and produces
a total amount plus a full BudgetLine breakdown for ADMIN audit.
---
Motor de calculo de presupuestos para la seccion ASISTENCIA.
Aplica las lineas de tarifa de la aseguradora a los datos de entrada
del operario y produce un importe total mas un desglose BudgetLine
completo para auditoria ADMIN.
"""

import datetime
import json

from decimal import Decimal, ROUND_HALF_UP

from budgets.models import (
    Budget,
    BudgetLine,
    InsurerTariff,
    SpecialRateTariff,
    TariffConcept,
    TariffLine,
    VehicleType,
)

# ---------------------------------------------------------------------------
# TAX CONSTANT — modify directly in this file when the VAT rate changes.
# CONSTANTE FISCAL — modificar directamente en este archivo cuando cambie el IVA.
# ---------------------------------------------------------------------------
IVA_PERCENT = Decimal("21.00")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _round2(value: Decimal) -> Decimal:
    """
    Round a Decimal to 2 decimal places using ROUND_HALF_UP.
    ---
    Redondea un Decimal a 2 decimales usando ROUND_HALF_UP.
    """
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_active_tariff(insurer_id: int) -> InsurerTariff:
    """
    Return the currently active tariff for the given insurer (valid_to=None).
    Raises ValueError if no active tariff exists.
    ---
    Devuelve la tarifa actualmente activa para la aseguradora dada (valid_to=None).
    Lanza ValueError si no existe ninguna tarifa activa.
    """
    try:
        return InsurerTariff.objects.get(insurer_id=insurer_id, valid_to__isnull=True)
    except InsurerTariff.DoesNotExist:
        raise ValueError(
            f"No existe tarifa activa para la aseguradora con id={insurer_id}. "
            "Configura una tarifa antes de generar presupuestos."
        )
    except InsurerTariff.MultipleObjectsReturned:
        # Safety net: return the most recently created active tariff.
        # Red de seguridad: devolver la tarifa activa mas reciente.
        return (
            InsurerTariff.objects
            .filter(insurer_id=insurer_id, valid_to__isnull=True)
            .order_by("-valid_from")
            .first()
        )


def _get_tariff_lines(tariff: InsurerTariff, vehicle_type: VehicleType) -> dict:
    """
    Build a concept-keyed dict of TariffLine objects for the given tariff
    and vehicle type. Generic lines (vehicle_type=None) are included for
    all vehicle types and are overridden by vehicle-specific lines if both exist.
    ---
    Construye un diccionario clave-concepto de objetos TariffLine para la tarifa
    y tipo de vehiculo dados. Las lineas genericas (vehicle_type=None) se incluyen
    para todos los tipos de vehiculo y son sobreescritas por lineas especificas
    si existen ambas.
    """
    lines = {}

    # Load generic lines first (surcharges, unlock if universal price).
    # Cargar primero las lineas genericas (recargos, desbloqueo si precio universal).
    for line in tariff.lines.filter(vehicle_type__isnull=True).select_related("concept"):
        lines[line.concept.code] = line

    # Override or add vehicle-specific lines.
    # Sobreescribir o anadir lineas especificas del tipo de vehiculo.
    for line in tariff.lines.filter(vehicle_type=vehicle_type).select_related("concept"):
        lines[line.concept.code] = line

    return lines


def _get_special_rate_lines(
    tariff: InsurerTariff,
    vehicle_type: VehicleType,
) -> dict | None:
    """
    Return a concept-keyed dict of SpecialRateLine objects for the given
    tariff and vehicle type, or None if no SpecialRateTariff exists.
    Generic lines (vehicle_type=None) are included and overridden by
    vehicle-specific lines if both exist.
    ---
    Devuelve un dict clave-concepto de objetos SpecialRateLine para la
    tarifa y tipo de vehiculo dados, o None si no existe SpecialRateTariff.
    Las lineas genericas (vehicle_type=None) se incluyen y son sobreescritas
    por lineas especificas si existen ambas.
    """
    try:
        srt = tariff.special_rate
    except SpecialRateTariff.DoesNotExist:
        return None

    lines = {}
    for line in srt.lines.filter(vehicle_type__isnull=True).select_related("concept"):
        lines[line.concept.code] = line
    for line in srt.lines.filter(vehicle_type=vehicle_type).select_related("concept"):
        lines[line.concept.code] = line
    return lines


# ---------------------------------------------------------------------------
# Holiday / night helper
# ---------------------------------------------------------------------------

def _is_holiday(date: datetime.date, base) -> bool:
    """
    Return True if the given date is a Saturday, Sunday, or a public holiday
    listed in base.labor_calendar. The calendar is stored as a JSON list of
    ISO date strings ('YYYY-MM-DD') populated by sync_base_calendars.

    Detection strategy (two-pass):
      1. Exact match 'YYYY-MM-DD' -- covers all holidays when the stored year
         matches the requested date year (standard case).
      2. Month-day match 'MM-DD' -- covers fixed-date holidays (e.g. Dec 25,
         May 1, local patron saint days) even when the calendar year differs.
         Mobile holidays (Easter Thursday/Friday) are year-dependent and
         will only be detected correctly when the calendar year matches.

    If the stored calendar year differs from the requested date year, a WARNING
    is logged so the operator knows the calendar may be stale. The budget
    calculation proceeds regardless -- the two-pass logic provides best-effort
    coverage for fixed-date holidays across years.

    If base is None or labor_calendar is empty, only weekend detection applies.
    ---
    Devuelve True si la fecha dada es sabado, domingo o festivo listado en
    base.labor_calendar. El calendario se almacena como lista JSON de fechas
    ISO ('YYYY-MM-DD') poblada por sync_base_calendars.

    Estrategia de deteccion (dos pasadas):
      1. Coincidencia exacta 'YYYY-MM-DD' -- cubre todos los festivos cuando
         el anio almacenado coincide con el de la fecha solicitada (caso normal).
      2. Coincidencia de mes-dia 'MM-DD' -- cubre festivos de fecha fija
         (25-dic, 1-may, patron local) aunque el anio del calendario difiera.
         Los festivos moviles (Jueves/Viernes Santo) solo se detectan
         correctamente cuando el anio coincide.

    Si el anio almacenado difiere del solicitado se emite un WARNING en logs
    para que el operario sepa que el calendario puede estar caducado. El calculo
    del presupuesto continua en cualquier caso.

    Si base es None o labor_calendar esta vacio, solo se aplica la deteccion
    de fin de semana.
    """
    import logging
    _log = logging.getLogger(__name__)

    # Weekend check.
    # Comprobacion de fin de semana.
    if date.weekday() in (5, 6):
        return True

    if base is None:
        return False

    calendar_json = (base.labor_calendar or "").strip()
    if not calendar_json:
        return False

    try:
        holidays: list[str] = json.loads(calendar_json)
    except (json.JSONDecodeError, TypeError):
        # Malformed calendar -- degrade gracefully to weekend-only detection.
        # Calendario malformado -- degradar a deteccion solo de fin de semana.
        return False

    if not holidays:
        return False

    # Detect the year stored in the calendar (year of the first entry).
    # Detectar el anio almacenado en el calendario (anio del primer registro).
    try:
        stored_year = int(holidays[0][:4])
    except (ValueError, IndexError):
        stored_year = None

    # Emit WARNING when the calendar year does not match the requested year.
    # Mobile holidays (Easter) may be incorrect in this case.
    # Emitir WARNING cuando el anio del calendario no coincide con el solicitado.
    # Los festivos moviles (Semana Santa) pueden ser incorrectos en este caso.
    if stored_year is not None and stored_year != date.year:
        _log.warning(
            "Calendario laboral caducado para la base '%s' (pk=%s): "
            "almacenado para %s, fecha solicitada %s. "
            "Festivos de fecha fija detectados por MM-DD; "
            "festivos moviles (Jueves/Viernes Santo) pueden ser inexactos. "
            "Ejecuta: sync_base_calendars --year %s --force --base-id %s",
            getattr(base, "name", base),
            getattr(base, "pk", "?"),
            stored_year,
            date.year,
            date.year,
            getattr(base, "pk", "?"),
        )

    # Pass 1 -- exact match for the full ISO date (standard case, same year).
    # Pasada 1 -- coincidencia exacta con la fecha ISO completa (caso normal).
    if date.isoformat() in holidays:
        return True

    # Pass 2 -- month-day match for fixed-date holidays across calendar years.
    # Build a set of 'MM-DD' fragments from the stored list for fast lookup.
    # Pasada 2 -- coincidencia MM-DD para festivos de fecha fija entre anios.
    # Construir conjunto de fragmentos 'MM-DD' del calendario para busqueda rapida.
    month_day = date.strftime("%m-%d")
    stored_month_days = {h[5:] for h in holidays if len(h) == 10}
    return month_day in stored_month_days

def _resolve_night_schedule(insurer):
    """
    Return the NightSchedule that applies to the given insurer.
    Resolution order:
      1. If the insurer has a NightSchedule assigned (insurer.night_schedule),
         return it regardless of is_default.
      2. Otherwise return the company-level default NightSchedule
         (is_default=True, is_active=True) for the insurer's company.
      3. If no default exists, return None.
    ---
    Devuelve el NightSchedule que aplica a la aseguradora dada.
    Orden de resolución:
      1. Si la aseguradora tiene NightSchedule asignado (insurer.night_schedule),
         devolverlo independientemente de is_default.
      2. Si no, devolver el NightSchedule por defecto de la empresa
         (is_default=True, is_active=True) para la empresa de la aseguradora.
      3. Si no existe ninguno por defecto, devolver None.
    """
    from budgets.models import NightSchedule

    # 1. Insurer-specific schedule takes priority.
    # 1. El horario específico de la aseguradora tiene prioridad.
    if insurer.night_schedule_id is not None:
        try:
            return insurer.night_schedule
        except NightSchedule.DoesNotExist:
            pass

    # 2. Fall back to company-level default.
    # 2. Recurrir al horario por defecto de la empresa.
    return (
        NightSchedule.objects
        .filter(
            company=insurer.company,
            is_default=True,
            is_active=True,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Route calculation — Google Routes API integration
# Calculo de ruta — integracion con Google Routes API
# ---------------------------------------------------------------------------


class RouteCalculationError(Exception):
    """
    Raised when the Routes API call fails or returns an unexpected response.
    ---
    Se lanza cuando la llamada a la Routes API falla o devuelve una respuesta
    inesperada.
    """
    pass


def _call_routes_api(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    departure_time_str: str,
    api_key: str,
    avoid_tolls: bool = False,
) -> dict:
    """
    Execute a single Google Routes API call and return a normalised result dict.
    The FieldMask requests distanceMeters, duration, polyline.encodedPolyline
    and travelAdvisory.tollInfo.
    If avoid_tolls=True, the routeModifiers.avoidTolls flag is set in the
    request payload.
    Returns: {"distance_km": Decimal, "has_tolls": bool, "encoded_polyline": str}
    Raises RouteCalculationError on any HTTP or network failure.
    ---
    Ejecuta una llamada individual a la Google Routes API y devuelve un dict
    normalizado. El FieldMask solicita distanceMeters, duration,
    polyline.encodedPolyline y travelAdvisory.tollInfo.
    Si avoid_tolls=True, se activa el flag routeModifiers.avoidTolls en el
    payload de la peticion.
    Devuelve: {"distance_km": Decimal, "has_tolls": bool, "encoded_polyline": str}
    Lanza RouteCalculationError ante cualquier fallo HTTP o de red.
    """
    import json
    import urllib.request
    import urllib.error

    routes_url = (
        "https://routes.googleapis.com/directions/v2:computeRoutes"
    )

    payload: dict = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": origin_lat,
                    "longitude": origin_lng,
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": dest_lat,
                    "longitude": dest_lng,
                }
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "departureTime": departure_time_str,
        "extraComputations": ["TOLLS"],
    }

    if avoid_tolls:
        # Request a toll-free alternative route.
        # Solicitar una ruta alternativa sin peajes.
        payload["routeModifiers"] = {"avoidTolls": True}

    routes_headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "routes.distanceMeters,"
            "routes.duration,"
            "routes.polyline.encodedPolyline,"
            "routes.travelAdvisory.tollInfo"
        ),
    }
    routes_request = urllib.request.Request(
        routes_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=routes_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(routes_request, timeout=15) as resp:
            routes_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RouteCalculationError(
            f"Routes API: HTTP {exc.code} — {body[:300]}"
        ) from exc
    except Exception as exc:
        raise RouteCalculationError(
            f"Routes API: error de red — {exc}"
        ) from exc

    routes = routes_data.get("routes", [])
    if not routes:
        raise RouteCalculationError(
            "Routes API: la respuesta no contiene ninguna ruta. "
            f"Respuesta completa: {str(routes_data)[:300]}"
        )
    route = routes[0]

    # Extract distance.
    # Extraer distancia.
    distance_meters = route.get("distanceMeters", 0)
    distance_km = _round2(Decimal(str(distance_meters)) / Decimal("1000"))

    # Extract encoded polyline for map rendering.
    # Extraer polyline codificada para renderizado en mapa.
    encoded_polyline: str = (
        route.get("polyline", {}).get("encodedPolyline", "")
    )

    # Detect toll presence: tollInfo in travelAdvisory signals a toll route.
    # Google Routes API does not return toll prices for Spain — has_tolls
    # is used as a boolean flag only.
    # Detectar presencia de peajes: tollInfo en travelAdvisory indica ruta
    # de peaje. La API no devuelve precios de peajes en Espana — has_tolls
    # se usa exclusivamente como indicador booleano.
    has_tolls = False
    try:
        _toll_info = route["travelAdvisory"]["tollInfo"]
        has_tolls = True
    except (KeyError, TypeError):
        pass

    return {
        "distance_km": _round2(distance_km * 2),
        "has_tolls": has_tolls,
        "encoded_polyline": encoded_polyline,
    }


def calculate_route(
    base,
    road_name: str,
    pk_km: Decimal,
    service_datetime: datetime.datetime,
    dest_location: str = "",
) -> dict:
    """
    Orchestrate up to two Google Routes API calls to obtain a dual route result:
    one with tolls (primary) and, if the primary has tolls, one without tolls
    (secondary). Returns a contract dict:
    {
        "route_with_tolls": {
            "distance_km": Decimal,
            "has_tolls": bool,
            "encoded_polyline": str,
        },
        "route_without_tolls": {
            "distance_km": Decimal,
            "has_tolls": False,
            "encoded_polyline": str,
        } | None,
        "error": None,
    }
    If the primary route has no tolls, route_without_tolls is None.
    Raises RouteCalculationError on any failure in the primary call.
    Errors in the secondary (avoid_tolls) call are silenced — route_without_tolls
    is set to None so the wizard can still proceed with the primary route.

    If base.latitude / base.longitude are null, geocodes the base municipality
    via the Geocoding API and persists the result before calling Routes API.
    ---
    Orquesta hasta dos llamadas a la Google Routes API para obtener un resultado
    de ruta dual: una con peajes (primaria) y, si la primaria tiene peajes, una
    sin peajes (secundaria). Devuelve el dict de contrato descrito arriba.
    Si la ruta primaria no tiene peajes, route_without_tolls es None.
    Lanza RouteCalculationError ante cualquier fallo en la llamada primaria.
    Los errores en la llamada secundaria (avoid_tolls) se silencian — se
    establece route_without_tolls a None para que el wizard pueda continuar
    con la ruta primaria.

    Si base.latitude / base.longitude son nulos, geocodifica el municipio
    de la base via la Geocoding API y persiste el resultado antes de llamar
    a la Routes API.
    """
    import os
    import json
    import urllib.request
    import urllib.parse
    import urllib.error
    import re as _re

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise RouteCalculationError(
            "GOOGLE_MAPS_API_KEY no configurada en el entorno."
        )

    # Step 1: ensure base has coordinates.
    # Paso 1: asegurar que la base tiene coordenadas.
    if not base.latitude or not base.longitude:
        # Geocode the base municipality and persist.
        # Geocodificar el municipio de la base y persistir.
        geocode_query = urllib.parse.urlencode({
            "address": f"{base.municipality}, España",
            "key": api_key,
            "language": "es",
            "region": "es",
        })
        geocode_url = (
            "https://maps.googleapis.com/maps/api/geocode/json"
            f"?{geocode_query}"
        )
        try:
            with urllib.request.urlopen(geocode_url, timeout=10) as resp:
                geo_data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RouteCalculationError(
                "Geocoding API: error de red geocodificando la base "
                f"'{base.name}': {exc}"
            ) from exc
        if (
            geo_data.get("status") != "OK"
            or not geo_data.get("results")
        ):
            raise RouteCalculationError(
                "Geocoding API: no se encontraron coordenadas para "
                f"'{base.municipality}' "
                f"(status: {geo_data.get('status')})."
            )
        geo_loc = geo_data["results"][0]["geometry"]["location"]
        base.latitude = Decimal(
            str(geo_loc["lat"])
        ).quantize(Decimal("0.000001"))
        base.longitude = Decimal(
            str(geo_loc["lng"])
        ).quantize(Decimal("0.000001"))
        base.save(update_fields=["latitude", "longitude", "updated_at"])

    origin_lat = float(base.latitude)
    origin_lng = float(base.longitude)

    # Step 2: geocode the kilometre marker on the road.
    # Paso 2: geocodificar el punto kilometrico en la carretera.
    _road = road_name.strip().upper()
    _road = _re.sub(r'\s+', ' ', _road)
    _road = _re.sub(r'^([A-Z]+)-?([0-9])', r'\1-\2', _road)
    pk_int = int(pk_km)
    if dest_location:
        dest_query_str = (
            f"{_road}, PK {pk_int}, {dest_location}, España"
        )
    else:
        dest_query_str = f"{_road}, {pk_int}, España"
    geocode_dest_query = urllib.parse.urlencode({
        "address": dest_query_str,
        "key": api_key,
        "language": "es",
        "region": "es",
    })
    geocode_dest_url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?{geocode_dest_query}"
    )
    try:
        with urllib.request.urlopen(geocode_dest_url, timeout=10) as resp:
            dest_data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RouteCalculationError(
            "Geocoding API: error de red geocodificando el punto "
            f"'{dest_query_str}': {exc}"
        ) from exc
    if (
        dest_data.get("status") != "OK"
        or not dest_data.get("results")
    ):
        raise RouteCalculationError(
            "Geocoding API: no se encontraron coordenadas para "
            f"'{dest_query_str}' "
            f"(status: {dest_data.get('status')})."
        )
    dest_loc = dest_data["results"][0]["geometry"]["location"]
    dest_lat = dest_loc["lat"]
    dest_lng = dest_loc["lng"]

    # Step 3: build departureTime in RFC 3339 UTC.
    # Paso 3: construir departureTime en RFC 3339 UTC.
    # PythonAnywhere operates in UTC — no conversion needed.
    # PythonAnywhere opera en UTC — no se necesita conversion.
    departure_time_str = service_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 4: primary call (with tolls).
    # Paso 4: llamada primaria (con peajes).
    route_with_tolls = _call_routes_api(
        origin_lat,
        origin_lng,
        dest_lat,
        dest_lng,
        departure_time_str,
        api_key,
        avoid_tolls=False,
    )

    # Step 5: secondary call (without tolls) — only when needed.
    # Paso 5: llamada secundaria (sin peajes) — solo si la primaria
    # tiene peajes.
    route_without_tolls = None
    if route_with_tolls["has_tolls"]:
        try:
            route_without_tolls = _call_routes_api(
                origin_lat,
                origin_lng,
                dest_lat,
                dest_lng,
                departure_time_str,
                api_key,
                avoid_tolls=True,
            )
            # Force has_tolls=False on the toll-free route regardless of
            # what the API returns (should be False, but we guarantee it).
            # Forzar has_tolls=False en la ruta sin peajes aunque la API
            # devolviera True (no deberia, pero lo garantizamos).
            route_without_tolls["has_tolls"] = False
        except RouteCalculationError:
            # Secondary call failure is non-fatal.
            # El fallo de la llamada secundaria no es fatal.
            route_without_tolls = None

    return {
        "route_with_tolls": route_with_tolls,
        "route_without_tolls": route_without_tolls,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Multi-leg route calculation — planificador multi-parada
# Calculo de ruta multi-tramo — planificador de ruta multi-parada
# ---------------------------------------------------------------------------


def _call_routes_multileg(
    origin_lat: float,
    origin_lng: float,
    intermediates: list[dict],
    dest_lat: float,
    dest_lng: float,
    departure_time_str: str,
    api_key: str,
    avoid_tolls: bool = False,
) -> dict:
    """
    Execute a single Google Routes API call with intermediate waypoints
    and return a normalised result dict.

    The route is always a closed circuit: origin and destination share
    the same coordinates (the service base). Intermediate waypoints
    define the stops along the route (pickup, drop-off points).

    If avoid_tolls=True, the routeModifiers.avoidTolls flag is set and
    TOLLS extra computation is omitted (toll-free route).

    Returns:
    {
        "distance_km":      Decimal,   # total distance of the full circuit
        "legs_distance_km": list[Decimal],  # distance per leg
        "has_tolls":        bool,
        "encoded_polyline": str,       # full circuit encoded polyline
    }
    Raises RouteCalculationError on any HTTP or network failure.
    ---
    Ejecuta una llamada a la Google Routes API con waypoints intermedios
    y devuelve un dict normalizado.

    La ruta es siempre un circuito cerrado: origen y destino comparten
    las mismas coordenadas (la base de servicio). Los waypoints intermedios
    definen las paradas del recorrido (recogida, puntos de entrega).

    Si avoid_tolls=True, se activa routeModifiers.avoidTolls y se omite
    TOLLS de extraComputations (ruta sin peajes).

    Devuelve el dict descrito arriba.
    Lanza RouteCalculationError ante cualquier fallo HTTP o de red.
    """
    import json as _json
    import urllib.request
    import urllib.error

    routes_url = (
        "https://routes.googleapis.com/directions/v2:computeRoutes"
    )

    # Build intermediates payload — each waypoint as latLng location.
    # Construir payload de intermediates — cada waypoint como latLng.
    intermediates_payload = [
        {
            "location": {
                "latLng": {
                    "latitude": wp["lat"],
                    "longitude": wp["lng"],
                }
            }
        }
        for wp in intermediates
    ]

    payload: dict = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": origin_lat,
                    "longitude": origin_lng,
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": dest_lat,
                    "longitude": dest_lng,
                }
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "departureTime": departure_time_str,
        "routeModifiers": {
            "avoidTolls": avoid_tolls,
            "avoidHighways": False,
            "avoidFerries": False,
        },
    }

    # Only request toll computation when not avoiding tolls — the
    # toll-free call does not need extraComputations=TOLLS.
    # Solo solicitar cómputo de peajes cuando no se evitan — la llamada
    # sin peajes no necesita extraComputations=TOLLS.
    if not avoid_tolls:
        payload["extraComputations"] = ["TOLLS"]

    if intermediates_payload:
        payload["intermediates"] = intermediates_payload

    routes_headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        # Request route-level distance + polyline + toll advisory,
        # plus per-leg distance for phase splitting.
        # Solicitar distancia de ruta + polyline + peajes,
        # mas distancia por tramo para separacion de fases.
        "X-Goog-FieldMask": (
            "routes.distanceMeters,"
            "routes.duration,"
            "routes.polyline.encodedPolyline,"
            "routes.travelAdvisory.tollInfo,"
            "routes.legs.distanceMeters"
        ),
    }

    routes_request = urllib.request.Request(
        routes_url,
        data=_json.dumps(payload).encode("utf-8"),
        headers=routes_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(routes_request, timeout=20) as resp:
            routes_data = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RouteCalculationError(
            f"Routes API (multileg): HTTP {exc.code} — {body[:300]}"
        ) from exc
    except Exception as exc:
        raise RouteCalculationError(
            f"Routes API (multileg): error de red — {exc}"
        ) from exc

    routes = routes_data.get("routes", [])
    if not routes:
        raise RouteCalculationError(
            "Routes API (multileg): la respuesta no contiene ninguna ruta. "
            f"Respuesta completa: {str(routes_data)[:300]}"
        )
    route = routes[0]

    # Total circuit distance — does NOT multiply by 2 because the route
    # is already a closed circuit (origin == destination == base).
    # Distancia total del circuito — NO se multiplica por 2 porque la
    # ruta ya es un circuito cerrado (origen == destino == base).
    distance_meters = route.get("distanceMeters", 0)
    distance_km = _round2(
        Decimal(str(distance_meters)) / Decimal("1000")
    )

    # Per-leg distances for phase splitting (overnight detection).
    # Distancias por tramo para separacion de fases (deteccion de pernocta).
    legs_distance_km: list[Decimal] = []
    for leg in route.get("legs", []):
        leg_meters = leg.get("distanceMeters", 0)
        legs_distance_km.append(
            _round2(Decimal(str(leg_meters)) / Decimal("1000"))
        )

    # Full circuit encoded polyline.
    # Polyline codificada del circuito completo.
    encoded_polyline: str = (
        route.get("polyline", {}).get("encodedPolyline", "")
    )

    # Toll detection — tollInfo presence in travelAdvisory signals tolls.
    # Deteccion de peajes — presencia de tollInfo en travelAdvisory.
    has_tolls = False
    try:
        _toll_info = route["travelAdvisory"]["tollInfo"]
        has_tolls = True
    except (KeyError, TypeError):
        pass

    return {
        "distance_km": distance_km,
        "legs_distance_km": legs_distance_km,
        "has_tolls": has_tolls,
        "encoded_polyline": encoded_polyline,
    }


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """
    Decode a Google Maps Encoded Polyline string into a list of (lat, lng)
    tuples. Pure Python implementation — no external dependencies.
    ---
    Decodifica una cadena de polyline codificada de Google Maps en una
    lista de tuplas (lat, lng). Implementación Python pura.
    """
    points: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        # Decode latitude
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else result >> 1
        lat += dlat
        # Decode longitude
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else result >> 1
        lng += dlng
        points.append((lat / 1e5, lng / 1e5))
    return points


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Return the great-circle distance in km between two points.
    ---
    Devuelve la distancia ortodrómica en km entre dos puntos.
    """
    import math
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_toll_cost(encoded_polyline: str, company=None, service_date=None) -> Decimal:
    """
    Cross-reference the route polyline with the TollSegment table to
    compute the total toll cost for the configured vehicle type.

    The vehicle type (LIGHT/HEAVY_1/HEAVY_2) is read from company.toll_vehicle_type.
    If company is None or the field is missing, defaults to HEAVY_1.

    A markup percentage (company.toll_markup_percent) is applied over the
    computed toll cost before returning.

    Algorithm:
    1. Decode the polyline into lat/lng points.
    2. For each geocoded TollSegment (origin_lat/lng + dest_lat/lng not null):
       - Find the polyline point closest to the segment origin.
       - Find the polyline point closest to the segment destination.
       - If both are within SNAP_KM and origin point comes before destination
         point in the polyline order → the route traverses this segment → add
         the appropriate price field to the total.
    3. Apply toll_markup_percent over the subtotal.
    4. Return the sum as Decimal, rounded to 2 dp.

    SNAP_KM: maximum distance (km) from a polyline point to a toll point to
    consider it a match. 1.5 km gives a good balance between precision and
    tolerance for motorway access ramps.
    ---
    Cruza la polyline de la ruta con la tabla TollSegment para calcular
    el coste total de peajes según el tipo de vehículo configurado.

    El tipo de vehículo (LIGHT/HEAVY_1/HEAVY_2) se lee de company.toll_vehicle_type.
    Si company es None o el campo no existe, usa HEAVY_1 por defecto.

    Se aplica un recargo porcentual (company.toll_markup_percent) sobre el
    coste calculado antes de devolver el resultado.
    """
    from budgets.models import TollSegment
    from ivr_config.models import Company as _Company

    if not encoded_polyline:
        return Decimal("0.00")

    try:
        points = _decode_polyline(encoded_polyline)
    except Exception:
        return Decimal("0.00")

    if not points:
        return Decimal("0.00")

    # Determine which price field to use based on company configuration.
    # Determinar qué campo de precio usar según la configuración de empresa.
    vehicle_type = _Company.TOLL_VEHICLE_HEAVY_1
    markup_percent = Decimal("0.00")
    if company is not None:
        vehicle_type = getattr(
            company, "toll_vehicle_type", _Company.TOLL_VEHICLE_HEAVY_1
        )
        markup_percent = Decimal(
            str(getattr(company, "toll_markup_percent", 0) or 0)
        )

    PRICE_FIELD_MAP = {
        _Company.TOLL_VEHICLE_LIGHT:   "price_light",
        _Company.TOLL_VEHICLE_HEAVY_1: "price_heavy_1",
        _Company.TOLL_VEHICLE_HEAVY_2: "price_heavy_2",
    }
    price_field = PRICE_FIELD_MAP.get(vehicle_type, "price_heavy_1")

    SNAP_KM = 1.5

    # Load all geocoded active segments — also fetch season fields.
    # Cargar todos los segmentos geocodificados activos — incluir campos de temporada.
    segments = TollSegment.objects.filter(
        origin_lat__isnull=False,
        origin_lng__isnull=False,
        dest_lat__isnull=False,
        dest_lng__isnull=False,
        is_active=True,
    ).only(
        "origin_lat", "origin_lng",
        "dest_lat", "dest_lng",
        "price_light", "price_heavy_1", "price_heavy_2",
        "price_light_high", "price_heavy_1_high", "price_heavy_2_high",
        "season_high_start", "season_high_end",
    )

    total = Decimal("0.00")

    for seg in segments:
        o_lat = float(seg.origin_lat)
        o_lng = float(seg.origin_lng)
        d_lat = float(seg.dest_lat)
        d_lng = float(seg.dest_lng)

        best_o_idx = None
        best_o_dist = float("inf")
        best_d_idx = None
        best_d_dist = float("inf")

        for i, (p_lat, p_lng) in enumerate(points):
            dist_o = _haversine_km(p_lat, p_lng, o_lat, o_lng)
            if dist_o < best_o_dist:
                best_o_dist = dist_o
                best_o_idx = i
            dist_d = _haversine_km(p_lat, p_lng, d_lat, d_lng)
            if dist_d < best_d_dist:
                best_d_dist = dist_d
                best_d_idx = i

        same_point = (
            abs(o_lat - d_lat) < 0.0001
            and abs(o_lng - d_lng) < 0.0001
        )

        # Determine effective price field for this segment.
        # Base field comes from company vehicle type config.
        # If the segment has a high-season range AND high-season price fields,
        # and the service date falls within the range, use the _high field.
        # The season range is year-independent: only month+day are compared.
        # ---
        # Determinar el campo de precio efectivo para este tramo.
        # El campo base viene del tipo de vehículo configurado en la empresa.
        # Si el tramo tiene rango de temporada alta Y precios de temporada alta,
        # y la fecha del servicio cae en ese rango, se usa el campo _high.
        # El rango de temporada es independiente del año: solo mes y día.
        HIGH_FIELD_MAP = {
            "price_light":   "price_light_high",
            "price_heavy_1": "price_heavy_1_high",
            "price_heavy_2": "price_heavy_2_high",
        }
        effective_price_field = price_field
        high_field = HIGH_FIELD_MAP.get(price_field)

        if (
            service_date is not None
            and high_field is not None
            and seg.season_high_start is not None
            and seg.season_high_end is not None
            and getattr(seg, high_field) is not None
        ):
            svc_md  = (service_date.month, service_date.day)
            hi_s_md = (seg.season_high_start.month, seg.season_high_start.day)
            hi_e_md = (seg.season_high_end.month, seg.season_high_end.day)

            if hi_s_md <= hi_e_md:
                in_high_season = hi_s_md <= svc_md <= hi_e_md
            else:
                # Cross-year range e.g. Dec 15 → Jan 15
                # Rango que cruza el año ej. 15 dic → 15 ene
                in_high_season = svc_md >= hi_s_md or svc_md <= hi_e_md

            if in_high_season:
                effective_price_field = high_field

        price = Decimal(str(getattr(seg, effective_price_field) or 0))

        if same_point:
            if best_o_dist <= SNAP_KM:
                total += _round2(price)
        elif (
            best_o_dist <= SNAP_KM
            and best_d_dist <= SNAP_KM
            and best_o_idx is not None
            and best_d_idx is not None
            and best_o_idx < best_d_idx
        ):
            total += _round2(price)

    # Apply markup percentage over the toll subtotal.
    # Aplicar recargo porcentual sobre el subtotal de peajes.
    if markup_percent > 0:
        total = _round2(total * (Decimal("1") + markup_percent / Decimal("100")))

    return _round2(total)


def calculate_route_multileg(
    base,
    waypoints: list[dict],
    service_datetime: datetime.datetime,
    api_key: str,
    company=None,
) -> dict:
    """
    Orchestrate one or two Routes API calls to compute the full closed-circuit
    route for an ASISTENCIA service.

    The circuit is always: Base → [stops] → Base.
    Waypoints must be provided in service order (pickup first, drop-off last).
    Each waypoint is a dict: {lat, lng, label, address, is_base_return}.

    Overnight detection: if any waypoint has is_base_return=True, the list
    is split at that point into two independent legs:
      - Leg 1: Base → stops-before-split → Base  (km_phase1)
      - Leg 2: Base → stops-after-split  → Base  (km_phase2)
    Two separate Routes API calls are made, one per leg.
    If no waypoint has is_base_return=True, a single call computes the full
    circuit and km_phase2 is None.

    Returns:
    {
        "distance_km":   Decimal,        # km_phase1 total (== full distance
                                         # when no overnight split)
        "km_phase1":     Decimal,
        "km_phase2":     Decimal | None,
        "is_overnight":  bool,
        "has_tolls":     bool,
        "encoded_polyline": str,
        "error":         None | str,
    }
    ---
    Orquesta una o dos llamadas a la Routes API para calcular el circuito
    cerrado completo de un servicio de ASISTENCIA.

    El circuito es siempre: Base → [paradas] → Base.
    Los waypoints deben entregarse en orden de servicio (recogida primero,
    entrega al final). Cada waypoint es un dict:
    {lat, lng, label, address, is_base_return}.

    Deteccion de pernocta: si algun waypoint tiene is_base_return=True, la
    lista se divide en ese punto en dos tramos independientes:
      - Tramo 1: Base → paradas-antes-del-corte → Base  (km_phase1)
      - Tramo 2: Base → paradas-despues-del-corte → Base (km_phase2)
    Se realizan dos llamadas separadas a la Routes API, una por tramo.
    Si ningun waypoint tiene is_base_return=True, una sola llamada calcula
    el circuito completo y km_phase2 es None.
    """
    import os

    if not api_key:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {
            "distance_km": Decimal("0"),
            "km_phase1": Decimal("0"),
            "km_phase2": None,
            "is_overnight": False,
            "has_tolls": False,
            "encoded_polyline": "",
            "error": (
                "GOOGLE_MAPS_API_KEY no configurada en el entorno."
            ),
        }

    # Ensure base coordinates are available.
    # Asegurar que la base tiene coordenadas.
    if not base.latitude or not base.longitude:
        return {
            "distance_km": Decimal("0"),
            "km_phase1": Decimal("0"),
            "km_phase2": None,
            "is_overnight": False,
            "has_tolls": False,
            "encoded_polyline": "",
            "error": (
                f"La base '{base.name}' no tiene coordenadas. "
                "Geocodifica la base desde el panel antes de calcular."
            ),
        }

    origin_lat = float(base.latitude)
    origin_lng = float(base.longitude)
    departure_time_str = service_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Detect overnight split: find first waypoint with is_base_return=True
    # that has at least one real stop after it (not via, not base-return).
    # A single "Return to base" closing a normal circuit is NOT overnight.
    # ---
    # Detectar corte de pernocta: primer waypoint con is_base_return=True
    # que tenga al menos una parada real despues (no via, no base-return).
    # Un unico "Volver a base" que cierra el circuito normal NO es pernocta.
    split_index: int | None = None
    for idx, wp in enumerate(waypoints):
        if wp.get("is_base_return"):
            has_stops_after = any(
                not w.get("is_base_return") and not w.get("is_via")
                for w in waypoints[idx + 1:]
            )
            if has_stops_after:
                split_index = idx
            break

    try:
        if split_index is None:
            # ── Single-leg service ─────────────────────────────────────
            # Servicio de tramo unico.
            # All waypoints are intermediates; circuit closes at Base.
            # Todos los waypoints son intermedios; el circuito cierra en
            # Base.
            result = _call_routes_multileg(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                intermediates=waypoints,
                dest_lat=origin_lat,
                dest_lng=origin_lng,
                departure_time_str=departure_time_str,
                api_key=api_key,
            )

            # Alternative route: same circuit avoiding tolls.
            # Errors are silenced — alt is optional, primary is mandatory.
            # Ruta alternativa: mismo circuito evitando peajes.
            # Los errores se silencian — la alt es opcional, la principal
            # es obligatoria.
            try:
                result_alt = _call_routes_multileg(
                    origin_lat=origin_lat,
                    origin_lng=origin_lng,
                    intermediates=waypoints,
                    dest_lat=origin_lat,
                    dest_lng=origin_lng,
                    departure_time_str=departure_time_str,
                    api_key=api_key,
                    avoid_tolls=True,
                )
                encoded_polyline_alt = result_alt["encoded_polyline"]
                distance_km_alt = result_alt["distance_km"]
            except Exception:
                encoded_polyline_alt = ""
                distance_km_alt = None

            return {
                "distance_km": result["distance_km"],
                "km_phase1": result["distance_km"],
                "km_phase2": None,
                "is_overnight": False,
                "has_tolls": result["has_tolls"],
                "route_toll_budget_cost": (
                    _compute_toll_cost(
                        result["encoded_polyline"],
                        company,
                        service_datetime.date() if service_datetime else None,
                    )
                    if result["has_tolls"] else Decimal("0.00")
                ),
                "encoded_polyline":     result["encoded_polyline"],
                "encoded_polyline_alt": encoded_polyline_alt,
                "distance_km_alt":      distance_km_alt,
                "error": None,
            }

        else:
            # ── Overnight service — two independent legs ────────────────
            # Servicio de pernocta — dos tramos independientes.
            leg1_waypoints = waypoints[:split_index]
            leg2_waypoints = waypoints[split_index + 1:]

            # Phase 1: Base → pickups/stops → Base.
            # Fase 1: Base → recogida/paradas → Base.
            result1 = _call_routes_multileg(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                intermediates=leg1_waypoints,
                dest_lat=origin_lat,
                dest_lng=origin_lng,
                departure_time_str=departure_time_str,
                api_key=api_key,
            )

            # Phase 2: Base → delivery stops → Base.
            # Use same departure_time for API consistency; actual day
            # does not affect distance calculation (only toll timing).
            # Fase 2: Base → puntos de entrega → Base.
            # Se usa el mismo departureTime por consistencia con la API;
            # el dia real no afecta al calculo de distancia (solo peajes).
            result2 = _call_routes_multileg(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                intermediates=leg2_waypoints,
                dest_lat=origin_lat,
                dest_lng=origin_lng,
                departure_time_str=departure_time_str,
                api_key=api_key,
            )

            # Alternative routes (avoid tolls) — silenced on error.
            # Rutas alternativas (sin peajes) — silenciadas en error.
            try:
                result1_alt = _call_routes_multileg(
                    origin_lat=origin_lat,
                    origin_lng=origin_lng,
                    intermediates=leg1_waypoints,
                    dest_lat=origin_lat,
                    dest_lng=origin_lng,
                    departure_time_str=departure_time_str,
                    api_key=api_key,
                    avoid_tolls=True,
                )
                result2_alt = _call_routes_multileg(
                    origin_lat=origin_lat,
                    origin_lng=origin_lng,
                    intermediates=leg2_waypoints,
                    dest_lat=origin_lat,
                    dest_lng=origin_lng,
                    departure_time_str=departure_time_str,
                    api_key=api_key,
                    avoid_tolls=True,
                )
                encoded_polyline_alt = (
                    result1_alt["encoded_polyline"]
                    + ""
                    + result2_alt["encoded_polyline"]
                )
                distance_km_alt = result1_alt["distance_km"] + result2_alt["distance_km"]
            except Exception:
                encoded_polyline_alt = ""
                distance_km_alt = None

            # Combine polylines: phase 1 then phase 2.
            # Combinar polylines: fase 1 seguida de fase 2.
            combined_polyline = (
                result1["encoded_polyline"]
                + ""
                + result2["encoded_polyline"]
            )

            has_tolls = result1["has_tolls"] or result2["has_tolls"]
            toll_cost = Decimal("0.00")
            if has_tolls:
                svc_date = service_datetime.date() if service_datetime else None
                toll_cost = (
                    _compute_toll_cost(result1["encoded_polyline"], company, svc_date)
                    + _compute_toll_cost(result2["encoded_polyline"], company, svc_date)
                )

            return {
                "distance_km": result1["distance_km"],
                "km_phase1": result1["distance_km"],
                "km_phase2": result2["distance_km"],
                "is_overnight": True,
                "has_tolls": has_tolls,
                "route_toll_budget_cost": _round2(toll_cost),
                "encoded_polyline":     combined_polyline,
                "encoded_polyline_alt": encoded_polyline_alt,
                "distance_km_alt":      distance_km_alt,
                "error": None,
            }

    except RouteCalculationError as exc:
        return {
            "distance_km": Decimal("0"),
            "km_phase1": Decimal("0"),
            "km_phase2": None,
            "is_overnight": False,
            "has_tolls": False,
            "route_toll_budget_cost": Decimal("0.00"),
            "encoded_polyline": "",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_budget(budget: Budget) -> list[BudgetLine]:
    """
    Core calculation engine. Receives a Budget instance with all input fields
    populated (vehicle_type, km_phase1/2, is_overnight, has_unlock,
    is_night_or_holiday, is_loaded, wait_hours, rescue_hours,
    assistant_hours, worker_hours, custody_days) and computes:

      1. Departure(s) — 1 or 2 depending on is_overnight.
      2. Kilometres — KM_NORMAL or KM_LONG based on km_total vs threshold.
      3. Unlock — if has_unlock.
      4. Optional concepts — wait, rescue, assistant, worker, custody.
      5. Subtotal base.
      6. Surcharges — NYF and/or loaded vehicle, applied per insurer rules.
      7. Management fee — if insurer.management_fee_percent > 0.

    Returns the list of BudgetLine instances (not yet saved to DB).
    Sets budget.total_amount and budget.tariff before returning.
    The caller is responsible for saving budget + lines in a single transaction.
    ---
    Motor de calculo principal. Recibe una instancia Budget con todos los campos
    de entrada rellenos y calcula los importes aplicando la tarifa activa de la
    aseguradora. Devuelve la lista de instancias BudgetLine (sin guardar en BD).
    Establece budget.total_amount y budget.tariff antes de devolver.
    El llamador es responsable de guardar budget + lineas en una sola transaccion.
    """
    insurer = budget.insurer
    vehicle_type = budget.vehicle_type

    # Resolve active tariff and attach to budget snapshot.
    # Resolver tarifa activa y adjuntar al snapshot del presupuesto.
    tariff = _get_active_tariff(insurer.pk)
    budget.tariff = tariff

    # Ensure km_total is calculated before the engine uses it.
    # km_total depends on save() but the budget is not yet saved here.
    # Asegurar que km_total esta calculado antes de que el motor lo use.
    # km_total depende del save() pero el budget aun no ha sido guardado.
    budget.km_total = (
        Decimal(str(budget.km_phase1 or 0))
        + Decimal(str(budget.km_phase2 or 0))
    )

    # Calculate is_night_or_holiday from is_night (operator) and
    # is_holiday (automatic from labor_calendar + weekends).
    # Calcular is_night_or_holiday desde is_night (operario) e
    # is_holiday (automatico desde labor_calendar + fines de semana).
    is_holiday = (
        _is_holiday(budget.service_date, budget.base)
        if budget.service_date
        else False
    )
    budget.is_night_or_holiday = budget.is_night or is_holiday

    # Force apply_iva if the insurer always requires IVA.
    # Forzar apply_iva si la aseguradora siempre requiere IVA.
    if insurer.always_apply_iva:
        budget.apply_iva = True

    lines_map = _get_tariff_lines(tariff, vehicle_type)

    # Resolve special night/holiday rate lines if applicable.
    # When is_night_or_holiday=True and the insurer has a SpecialRateTariff,
    # use those lines for base concepts instead of the standard lines_map.
    # Resolver lineas de tarifa especial nocturno/festivo si aplica.
    # Cuando is_night_or_holiday=True y la aseguradora tiene SpecialRateTariff,
    # usar esas lineas para conceptos base en lugar del lines_map estandar.
    active_lines_map = lines_map
    using_special_rate = False
    if budget.is_night_or_holiday and insurer.special_night_holiday_tariff:
        special_map = _get_special_rate_lines(tariff, vehicle_type)
        if special_map:
            active_lines_map = special_map
            using_special_rate = True

    result_lines: list[BudgetLine] = []
    sort_order = 0

    def _add_line(concept_code: str, label: str, units: Decimal,
                  unit_price: Decimal, is_surcharge: bool = False) -> Decimal:
        """
        Create a BudgetLine, append it to result_lines and return its subtotal.
        ---
        Crea una BudgetLine, la anade a result_lines y devuelve su subtotal.
        """
        nonlocal sort_order
        subtotal = _round2(units * unit_price)
        result_lines.append(BudgetLine(
            budget=budget,
            concept_code=concept_code,
            concept_label=label,
            units=units,
            unit_price=unit_price,
            subtotal=subtotal,
            is_surcharge=is_surcharge,
            sort_order=sort_order,
        ))
        sort_order += 1
        return subtotal

    base_total = Decimal("0.00")

    # ------------------------------------------------------------------
    # 1. DEPARTURE(S) or SERVICE_LOCAL forfait
    # If km_total <= insurer.local_service_km_threshold AND the tariff
    # includes a SERVICE_LOCAL line: apply the forfait (no departure, no km).
    # Otherwise: apply DEPARTURE normally and proceed to km calculation.
    #
    # Si km_total <= insurer.local_service_km_threshold Y la tarifa incluye
    # una linea SERVICE_LOCAL: aplicar el forfait (sin salida, sin km).
    # En caso contrario: aplicar DEPARTURE normalmente y calcular km.
    # ------------------------------------------------------------------
    departure_line = active_lines_map.get(TariffConcept.CODE_DEPARTURE)
    service_local_line = active_lines_map.get(TariffConcept.CODE_SERVICE_LOCAL)
    km_total = Decimal(str(budget.km_total))

    # Determine whether this service qualifies as local (forfait).
    # A service is local when: the insurer has a configured threshold,
    # the tariff includes a SERVICE_LOCAL line, and km_total is within
    # that threshold (0 km included — operators enter 0 for urban jobs).
    #
    # Determinar si el servicio califica como local (forfait).
    # Es local cuando: la aseguradora tiene umbral configurado, la tarifa
    # incluye linea SERVICE_LOCAL, y km_total esta dentro del umbral
    # (0 km incluido — los operarios introducen 0 en trabajos urbanos).
    _local_threshold = insurer.local_service_km_threshold
    _is_local_service = (
        _local_threshold is not None
        and service_local_line is not None
        and km_total <= Decimal(str(_local_threshold))
    )

    if _is_local_service:
        # Forfait: SERVICE_LOCAL replaces both DEPARTURE and km.
        # Forfait: SERVICE_LOCAL sustituye tanto a DEPARTURE como a los km.
        num_units = Decimal("2") if budget.is_overnight else Decimal("1")
        base_total += _add_line(
            TariffConcept.CODE_SERVICE_LOCAL,
            "Servicio local / Urbano",
            num_units,
            Decimal(str(service_local_line.price)),
        )
    else:
        # Standard service: apply DEPARTURE and km normally.
        # Servicio estandar: aplicar DEPARTURE y km normalmente.
        if departure_line:
            num_departures = Decimal("2") if budget.is_overnight else Decimal("1")
            base_total += _add_line(
                TariffConcept.CODE_DEPARTURE,
                "Salida / Enganche",
                num_departures,
                Decimal(str(departure_line.price)),
            )

        # ------------------------------------------------------------------
        # 2. KILOMETRES
        # Select KM_NORMAL or KM_LONG based on km_total vs km_threshold.
        # Seleccionar KM_NORMAL o KM_LONG en funcion de km_total vs km_threshold.
        # ------------------------------------------------------------------
        km_long_line = active_lines_map.get(TariffConcept.CODE_KM_LONG)
        km_normal_line = active_lines_map.get(TariffConcept.CODE_KM_NORMAL)

        km_line_to_use = None
        if km_long_line and km_long_line.km_threshold is not None:
            threshold = Decimal(str(km_long_line.km_threshold))
            if km_total > threshold:
                km_line_to_use = km_long_line
                km_label = "Kilometros largo recorrido"
            else:
                km_line_to_use = km_normal_line
                km_label = "Kilometros"
        elif km_normal_line:
            km_line_to_use = km_normal_line
            km_label = "Kilometros"

        if km_line_to_use and km_total > 0:
            base_total += _add_line(
                km_line_to_use.concept,
                km_label,
                km_total,
                Decimal(str(km_line_to_use.price)),
            )

    # ------------------------------------------------------------------
    # 3. TOLL COST (Modo B — route_calculation_mode=API)
    # If the budget has a route_toll_budget_cost, add it as a direct
    # BudgetLine. The amount comes from BudgetWaypointView (Routes API
    # v2 server-side via TollSegment table) — not from TariffLine.
    # It is added to base_total so surcharges and fees apply on top.
    # ---
    # Si el budget tiene route_toll_budget_cost, añadirlo como BudgetLine
    # directa. El importe viene de BudgetWaypointView (Routes API v2
    # server-side via tabla TollSegment) — no de TariffLine.
    # Se suma a base_total para que los recargos y comisiones se apliquen
    # encima.
    # ------------------------------------------------------------------
    if budget.route_toll_budget_cost and budget.route_toll_budget_cost > 0:
        toll_amount = _round2(Decimal(str(budget.route_toll_budget_cost)))
        base_total += _add_line(
            "TOLL_COST",
            "Peajes de ruta",
            Decimal("1"),
            toll_amount,
        )
        budget.total_amount = _round2(
            budget.total_amount if budget.total_amount else Decimal("0")
        )

    # ------------------------------------------------------------------
    # 5. UNLOCK
    # Only if has_unlock and the tariff includes an UNLOCK line.
    # Solo si has_unlock y la tarifa incluye una linea UNLOCK.
    # ------------------------------------------------------------------
    if budget.has_unlock:
        unlock_line = active_lines_map.get(TariffConcept.CODE_UNLOCK)
        if unlock_line:
            base_total += _add_line(
                TariffConcept.CODE_UNLOCK,
                "Desbloqueo / Enganche eslingas",
                Decimal("1"),
                Decimal(str(unlock_line.price)),
            )

    # ------------------------------------------------------------------
    # 6. OPTIONAL CONCEPTS
    # Each is included only if the operator provided a value > 0
    # and the tariff has a matching line.
    # Cada uno se incluye solo si el operario proporciono un valor > 0
    # y la tarifa tiene una linea correspondiente.
    # ------------------------------------------------------------------
    optional_map = [
        (budget.rescue_hours,   TariffConcept.CODE_RESCUE_HOUR,    "Hora de rescate"),
        (budget.wait_hours,     TariffConcept.CODE_WAIT_HOUR,      "Hora de espera"),
        (budget.worker_hours,   TariffConcept.CODE_WORKER_HOUR,    "Hora de mano de obra"),
        (budget.assistant_hours, TariffConcept.CODE_ASSISTANT_HOUR, "Hora de ayudante"),
        (budget.custody_days,   TariffConcept.CODE_CUSTODY_DAY,    "Custodia por dia"),
    ]

    for raw_value, concept_code, label in optional_map:
        if not raw_value:
            continue
        opt_line = active_lines_map.get(concept_code)
        if not opt_line:
            continue
        units = Decimal(str(raw_value))
        # Apply minimum billable units if defined in the tariff.
        # Aplicar unidades minimas facturables si estan definidas en la tarifa.
        if opt_line.min_units and units < Decimal(str(opt_line.min_units)):
            units = Decimal(str(opt_line.min_units))
        base_total += _add_line(
            concept_code,
            label,
            units,
            Decimal(str(opt_line.price)),
        )

    # ------------------------------------------------------------------
    # 7. SURCHARGES — NYF and/or loaded vehicle
    # Applied as a percentage over base_total.
    # Rules:
    #   - If insurer.surcharges_are_cumulative: both surcharges are summed.
    #   - Otherwise: only the higher surcharge is applied (standard rule).
    # Aplicados como porcentaje sobre base_total.
    # Reglas:
    #   - Si insurer.surcharges_are_cumulative: ambos recargos se suman.
    #   - En caso contrario: solo se aplica el mayor (regla estandar).
    # ------------------------------------------------------------------
    nyf_percent = Decimal("0.00")
    loaded_percent = Decimal("0.00")

    nyf_line = lines_map.get(TariffConcept.CODE_NYF_PERCENT)
    loaded_line = lines_map.get(TariffConcept.CODE_LOADED_PERCENT)

    # When using special night/holiday rates, skip the percentage surcharge.
    # The special tariff already prices night/holiday conditions directly.
    # Cuando se usa la tarifa especial nocturno/festivo, omitir el recargo
    # porcentual. La tarifa especial ya incorpora los precios diferenciados.
    if budget.is_night_or_holiday and nyf_line and not using_special_rate:
        nyf_percent = Decimal(str(nyf_line.price))

    if budget.is_loaded and loaded_line:
        loaded_percent = Decimal(str(loaded_line.price))

    surcharge_total = Decimal("0.00")

    if insurer.surcharges_are_cumulative:
        # Both surcharges apply independently and are summed.
        # Ambos recargos aplican de forma independiente y se suman.
        if nyf_percent > 0:
            surcharge_amount = _round2(base_total * nyf_percent / Decimal("100"))
            surcharge_total += surcharge_amount
            _add_line(
                TariffConcept.CODE_NYF_PERCENT,
                f"Recargo nocturno/festivo ({nyf_percent}%)",
                base_total,
                nyf_percent / Decimal("100"),
                is_surcharge=True,
            )
        if loaded_percent > 0:
            surcharge_amount = _round2(base_total * loaded_percent / Decimal("100"))
            surcharge_total += surcharge_amount
            _add_line(
                TariffConcept.CODE_LOADED_PERCENT,
                f"Recargo vehiculo cargado ({loaded_percent}%)",
                base_total,
                loaded_percent / Decimal("100"),
                is_surcharge=True,
            )
    else:
        # Apply only the higher surcharge (standard for most insurers).
        # Aplicar solo el mayor recargo (estandar para la mayoria de aseguradoras).
        effective_percent = max(nyf_percent, loaded_percent)
        if effective_percent > 0:
            if effective_percent == nyf_percent:
                code = TariffConcept.CODE_NYF_PERCENT
                label = f"Recargo nocturno/festivo ({effective_percent}%)"
            else:
                code = TariffConcept.CODE_LOADED_PERCENT
                label = f"Recargo vehiculo cargado ({effective_percent}%)"
            surcharge_amount = _round2(base_total * effective_percent / Decimal("100"))
            surcharge_total += surcharge_amount
            _add_line(
                code,
                label,
                base_total,
                effective_percent / Decimal("100"),
                is_surcharge=True,
            )

    subtotal_after_surcharges = base_total + surcharge_total

    # ------------------------------------------------------------------
    # 8. MANAGEMENT FEE
    # Only if insurer.management_fee_percent > 0 (e.g. COVEI 5%).
    # Solo si insurer.management_fee_percent > 0 (ej: COVEI 5%).
    # ------------------------------------------------------------------
    management_fee_total = Decimal("0.00")
    if insurer.management_fee_percent and insurer.management_fee_percent > 0:
        fee_percent = Decimal(str(insurer.management_fee_percent))
        management_fee_total = _round2(
            subtotal_after_surcharges * fee_percent / Decimal("100")
        )
        _add_line(
            "MANAGEMENT_FEE",
            f"Gastos de gestion ({fee_percent}%)",
            subtotal_after_surcharges,
            fee_percent / Decimal("100"),
            is_surcharge=True,
        )

    # ------------------------------------------------------------------
    # 9. TOTAL (base, before IVA)
    # ------------------------------------------------------------------
    budget.total_amount = _round2(subtotal_after_surcharges + management_fee_total)

    # ------------------------------------------------------------------
    # 10. IVA (optional — controlled by budget.apply_iva)
    # Applied over total_amount. Result stored as instance attribute
    # total_amount_with_iva (not persisted in DB).
    # Aplicado sobre total_amount. Resultado almacenado como atributo de
    # instancia total_amount_with_iva (no persistido en BD).
    # ------------------------------------------------------------------
    if budget.apply_iva:
        iva_amount = _round2(budget.total_amount * IVA_PERCENT / Decimal("100"))
        _add_line(
            "IVA",
            f"IVA ({IVA_PERCENT}%)",
            budget.total_amount,
            IVA_PERCENT / Decimal("100"),
            is_surcharge=True,
        )
        budget.total_amount_with_iva = _round2(budget.total_amount + iva_amount)
    else:
        budget.total_amount_with_iva = None

    return result_lines




