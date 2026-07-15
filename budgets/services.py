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
    include_traffic: bool = True,
) -> dict:
    """
    Execute a single Google Routes API call and return a normalised result dict.
    The FieldMask requests distanceMeters, duration, polyline.encodedPolyline
    and travelAdvisory.tollInfo.
    If avoid_tolls=True, the routeModifiers.avoidTolls flag is set in the
    request payload.

    include_traffic=False omits departureTime and falls back to
    TRAFFIC_UNAWARE — required for past/present service dates, since
    Google's Routes API rejects a past departureTime for DRIVE mode.

    Returns: {"distance_km": Decimal, "has_tolls": bool, "encoded_polyline": str}
    Raises RouteCalculationError on any HTTP or network failure.
    ---
    Ejecuta una llamada individual a la Google Routes API y devuelve un dict
    normalizado. El FieldMask solicita distanceMeters, duration,
    polyline.encodedPolyline y travelAdvisory.tollInfo.
    Si avoid_tolls=True, se activa el flag routeModifiers.avoidTolls en el
    payload de la peticion.

    include_traffic=False omite departureTime y cae a TRAFFIC_UNAWARE —
    necesario para fechas de servicio pasadas/presentes, ya que la
    Routes API de Google rechaza un departureTime pasado en modo DRIVE.

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
        "extraComputations": ["TOLLS"],
    }

    if include_traffic:
        payload["routingPreference"] = "TRAFFIC_AWARE"
        payload["departureTime"] = departure_time_str
    else:
        payload["routingPreference"] = "TRAFFIC_UNAWARE"

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
        import logging as _log_routes
        _log_routes.getLogger(__name__).error(
            "# [budgets] Routes API HTTP %s: %s", exc.code, body[:300],
        )
        raise RouteCalculationError(
            "No se pudo calcular la ruta (error del servicio de rutas)."
        ) from exc
    except Exception as exc:
        import logging as _log_routes2
        _log_routes2.getLogger(__name__).error(
            "# [budgets] Routes API: error de red: %s", exc, exc_info=True,
        )
        raise RouteCalculationError(
            "No se pudo calcular la ruta. Comprueba la conexión o "
            "inténtalo de nuevo."
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
            import logging as _log_geo
            _log_geo.getLogger(__name__).error(
                "# [budgets] Error de red geocodificando la base "
                "pk=%r (%r): %s",
                base.pk, base.name, exc, exc_info=True,
            )
            raise RouteCalculationError(
                f"No se pudo geocodificar la base '{base.name}'. "
                "Comprueba la conexión o inténtalo de nuevo."
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
        import logging as _log_geo_dest
        _log_geo_dest.getLogger(__name__).error(
            "# [budgets] Error de red geocodificando el punto de "
            "destino %r: %s",
            dest_query_str, exc, exc_info=True,
        )
        raise RouteCalculationError(
            f"No se pudo geocodificar el punto de destino "
            f"'{dest_query_str}'. Comprueba la conexión o inténtalo "
            "de nuevo."
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

    # Google's Routes API rejects a past departureTime for DRIVE mode —
    # only include it (with TRAFFIC_AWARE) when the service date is in
    # the future. Verified against current Routes API docs (2026-06).
    # Google rechaza un departureTime pasado para modo DRIVE — solo se
    # incluye (con TRAFFIC_AWARE) cuando la fecha de servicio es futura.
    include_traffic = service_datetime > datetime.datetime.utcnow()

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
        include_traffic=include_traffic,
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
                include_traffic=include_traffic,
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
    include_traffic: bool = True,
) -> dict:
    """
    Execute a single Google Routes API call with intermediate waypoints
    and return a normalised result dict.

    The route is always a closed circuit: origin and destination share
    the same coordinates (the service base). Intermediate waypoints
    define the stops along the route (pickup, drop-off points).

    If avoid_tolls=True, the routeModifiers.avoidTolls flag is set and
    TOLLS extra computation is omitted (toll-free route).

    include_traffic controls whether departureTime/TRAFFIC_AWARE are
    sent. Google's Routes API rejects any departureTime in the past for
    RouteTravelMode=DRIVE (confirmed against current API docs — only
    TRANSIT mode supports past departure times). For budgets with a
    past or present service date, the caller sets include_traffic=False
    so departureTime is omitted entirely (defaults to request time) and
    routingPreference becomes TRAFFIC_UNAWARE — route geometry, distance
    and toll segments are date-independent, so this has no effect on
    accuracy for historical budgets; only live-traffic ETA prediction is
    skipped, which is irrelevant for a service already rendered.

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

    include_traffic controla si se envían departureTime/TRAFFIC_AWARE.
    La Routes API de Google rechaza cualquier departureTime en el pasado
    para RouteTravelMode=DRIVE (confirmado contra la documentación
    actual de la API — solo el modo TRANSIT admite departure times
    pasados). Para presupuestos con fecha de servicio pasada o presente,
    el llamador pasa include_traffic=False para omitir departureTime por
    completo (usa la hora de la petición por defecto) y routingPreference
    pasa a ser TRAFFIC_UNAWARE — la geometría de la ruta, la distancia y
    los tramos de peaje no dependen de la fecha, así que esto no afecta
    a la precisión para presupuestos históricos; solo se omite la
    predicción de tráfico en vivo para el ETA, irrelevante para un
    servicio ya prestado.

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
        "routeModifiers": {
            "avoidTolls": avoid_tolls,
            "avoidHighways": False,
            "avoidFerries": False,
        },
    }

    if include_traffic:
        payload["routingPreference"] = "TRAFFIC_AWARE"
        payload["departureTime"] = departure_time_str
    else:
        # Past/present service date: departureTime omitted (Google
        # rejects past values for DRIVE), routingPreference falls back
        # to time-independent computation.
        # Fecha de servicio pasada/presente: departureTime omitido
        # (Google rechaza valores pasados para DRIVE), routingPreference
        # cae a cómputo independiente del tiempo.
        payload["routingPreference"] = "TRAFFIC_UNAWARE"

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
        import logging as _log_routes_ml
        _log_routes_ml.getLogger(__name__).error(
            "# [budgets] Routes API (multileg) HTTP %s: %s",
            exc.code, body[:300],
        )
        raise RouteCalculationError(
            "No se pudo calcular la ruta multitramo (error del "
            "servicio de rutas)."
        ) from exc
    except Exception as exc:
        import logging as _log_routes_ml2
        _log_routes_ml2.getLogger(__name__).error(
            "# [budgets] Routes API (multileg): error de red: %s",
            exc, exc_info=True,
        )
        raise RouteCalculationError(
            "No se pudo calcular la ruta multitramo. Comprueba la "
            "conexión o inténtalo de nuevo."
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


def _is_holy_week(d: datetime.date) -> bool:
    """
    Return True if the given date falls within Holy Week (Semana Santa),
    defined as Viernes de Dolores (Domingo de Ramos - 8 days) through
    Domingo in Albis (Domingo de Pascua + 7 days), inclusive.

    Easter Sunday is computed with the Butcher/Meeus algorithm — no
    external dependencies required.
    ---
    Devuelve True si la fecha cae en Semana Santa, definida como desde el
    Viernes de Dolores (Domingo de Ramos - 8 días) hasta el Domingo in Albis
    (Domingo de Pascua + 7 días), ambos inclusive.

    El Domingo de Pascua se calcula con el algoritmo de Butcher/Meeus,
    sin dependencias externas.
    """
    y = d.year
    a = y % 19
    b = y // 100
    c = y % 100
    d_ = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d_ - g + 15) % 30
    i = c // 4
    k = c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = ((h + ll - 7 * m + 114) % 31) + 1
    easter = datetime.date(y, month, day)

    # Viernes de Dolores = Domingo de Ramos - 8 días = Pascua - 15 días
    # Domingo in Albis   = Pascua + 7 días
    holy_start = easter - datetime.timedelta(days=15)
    holy_end   = easter + datetime.timedelta(days=7)
    return holy_start <= d <= holy_end


def _resolve_toll_pricing(company):
    """
    Resolve (price_field, vehicle_label, high_field) for a given company's
    configured toll vehicle category. Shared by _compute_toll_cost() (Modo
    B — route polyline matching) and _compute_manual_toll_cost() (Modo
    Manual — itemized troncal/salida selection), so both price segments
    identically per DRY principle (see ai_services precedent in H10).
    ---
    Resuelve (price_field, vehicle_label, high_field) para la categoría de
    vehículo de peaje configurada en la empresa. Compartido por
    _compute_toll_cost() (Modo B — cruce de polyline) y
    _compute_manual_toll_cost() (Modo Manual — selección de troncal/salida
    por tramo), para que ambas tarifiquen los tramos de forma idéntica
    (principio DRY, mismo precedente que ai_services en H10).
    """
    from ivr_config.models import Company as _Company

    vehicle_type = _Company.TOLL_VEHICLE_HEAVY_1
    if company is not None:
        vehicle_type = getattr(
            company, "toll_vehicle_type", _Company.TOLL_VEHICLE_HEAVY_1
        )

    PRICE_FIELD_MAP = {
        _Company.TOLL_VEHICLE_LIGHT:   "price_light",
        _Company.TOLL_VEHICLE_HEAVY_1: "price_heavy_1",
        _Company.TOLL_VEHICLE_HEAVY_2: "price_heavy_2",
    }
    VEHICLE_LABEL_MAP = {
        _Company.TOLL_VEHICLE_LIGHT:   "Ligero",
        _Company.TOLL_VEHICLE_HEAVY_1: "Pesado 1",
        _Company.TOLL_VEHICLE_HEAVY_2: "Pesado 2",
    }
    price_field = PRICE_FIELD_MAP.get(vehicle_type, "price_heavy_1")
    vehicle_label = VEHICLE_LABEL_MAP.get(vehicle_type, "Pesado 1")

    HIGH_FIELD_MAP = {
        "price_light":   "price_light_high",
        "price_heavy_1": "price_heavy_1_high",
        "price_heavy_2": "price_heavy_2_high",
    }
    high_field = HIGH_FIELD_MAP.get(price_field)

    return price_field, vehicle_label, high_field


def _price_for_toll_segment(seg, service_date, price_field, high_field):
    """
    Determines the effective price, high-season flag and season type for
    a TollSegment on service_date. Extracted from the former closure inside
    _compute_toll_cost() so _compute_manual_toll_cost() can reuse the exact
    same seasonal logic (verano / Semana Santa) without duplicating it.
    ---
    Determina el precio efectivo, el flag de temporada alta y el tipo de
    temporada de un TollSegment en service_date. Extraída del antiguo
    closure de _compute_toll_cost() para que _compute_manual_toll_cost()
    reutilice exactamente la misma lógica estacional (verano / Semana
    Santa) sin duplicarla.
    """
    effective_field = price_field
    is_high_season  = False
    season_type     = None

    if service_date is not None and high_field is not None:
        if (
            seg.season_high_start is not None
            and seg.season_high_end is not None
            and getattr(seg, high_field) is not None
        ):
            svc_md  = (service_date.month, service_date.day)
            hi_s_md = (
                seg.season_high_start.month,
                seg.season_high_start.day,
            )
            hi_e_md = (
                seg.season_high_end.month,
                seg.season_high_end.day,
            )
            if hi_s_md <= hi_e_md:
                in_range = hi_s_md <= svc_md <= hi_e_md
            else:
                in_range = svc_md >= hi_s_md or svc_md <= hi_e_md

            if in_range:
                effective_field = high_field
                is_high_season  = True
                season_type     = "VERANO"

        if (
            not is_high_season
            and getattr(seg, high_field) is not None
            and _is_holy_week(service_date)
        ):
            effective_field = high_field
            is_high_season  = True
            season_type     = "SEMANA_SANTA"

    price = _round2(Decimal(str(getattr(seg, effective_field) or 0)))
    return price, is_high_season, season_type


def _compute_manual_toll_cost(
    manual_toll_segments: dict,
    company=None,
    service_date=None,
) -> list:
    """
    Build toll cost details from an itemized manual selection of TollSegment
    rows and pass counts (Modo Manual del wizard de presupuestos) — same
    output format as _compute_toll_cost() so both feed
    _build_toll_budget_lines() identically:
      {'segment_name': str, 'vehicle_type_label': str, 'price': Decimal,
       'is_high_season': bool, 'season_type': str|None}

    manual_toll_segments: dict {str(segment_id): passes_int}, as stored in
    Budget.manual_toll_segments. Segments not found or inactive, and
    entries with passes <= 0, are silently skipped.
    ---
    Construye el detalle de peajes desde una selección manual por tramo de
    TollSegment y su número de pases (Modo Manual del wizard) — mismo
    formato de salida que _compute_toll_cost() para que ambas alimenten
    _build_toll_budget_lines() de forma idéntica.

    manual_toll_segments: dict {str(segment_id): pases_int}, tal como se
    almacena en Budget.manual_toll_segments. Los tramos no encontrados o
    inactivos, y las entradas con pases <= 0, se omiten silenciosamente.
    """
    from budgets.models import TollSegment

    if not manual_toll_segments:
        return []

    price_field, vehicle_label, high_field = _resolve_toll_pricing(company)

    try:
        segment_ids = [
            int(sid) for sid in manual_toll_segments.keys()
            if str(sid).lstrip("-").isdigit()
        ]
    except AttributeError:
        return []

    segments_by_id = {
        seg.pk: seg
        for seg in TollSegment.objects.filter(pk__in=segment_ids, is_active=True)
    }

    result = []
    for sid_str, passes in manual_toll_segments.items():
        try:
            sid = int(sid_str)
            count = int(passes)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        seg = segments_by_id.get(sid)
        if seg is None:
            continue
        price, is_high_season, season_type = _price_for_toll_segment(
            seg, service_date, price_field, high_field
        )
        segment_name = (
            f"{seg.road_code} | {seg.origin_name} \u2192 {seg.dest_name}"
        )
        for _ in range(count):
            result.append({
                "segment_name":       segment_name,
                "vehicle_type_label": vehicle_label,
                "price":              price,
                "is_high_season":     is_high_season,
                "season_type":        season_type,
            })
    return result


def _compute_toll_cost(
    encoded_polyline: str,
    company=None,
    service_date=None,
) -> list:
    """
    Cross-reference the route polyline with the TollSegment table to
    compute toll cost details for the configured vehicle type.

    Returns a list of dicts, one per matched segment:
      {
        'segment_name':     str,   # "road_code | origin → dest"
        'vehicle_type_label': str, # "Ligero" / "Pesado 1" / "Pesado 2"
        'price':            Decimal,  # base price (before markup)
        'is_high_season':   bool,
        'season_type':      str | None,  # 'VERANO' | 'SEMANA_SANTA' | None
      }

    The caller is responsible for applying markup and building BudgetLines.
    Returns an empty list when no toll segments are matched.
    ---
    Cruza la polyline de la ruta con la tabla TollSegment para calcular
    el detalle de peajes según el tipo de vehículo configurado.

    Devuelve una lista de dicts, uno por tramo detectado:
      {
        'segment_name':       str,    # "road_code | origin → dest"
        'vehicle_type_label': str,    # "Ligero" / "Pesado 1" / "Pesado 2"
        'price':              Decimal, # precio base (sin recargo)
        'is_high_season':     bool,
        'season_type':        str | None, # 'VERANO' | 'SEMANA_SANTA' | None
      }

    El llamador aplica el recargo y construye las BudgetLine.
    Devuelve lista vacía si no se detectan tramos.
    """
    from budgets.models import TollSegment

    if not encoded_polyline:
        return []

    try:
        points = _decode_polyline(encoded_polyline)
    except Exception:
        return []

    if not points:
        return []

    # Determine vehicle type, label and high-season field from company
    # config — shared helper, see _resolve_toll_pricing().
    # Determinar tipo de vehículo, etiqueta y campo de temporada alta desde
    # la config de empresa — helper compartido, ver _resolve_toll_pricing().
    price_field, vehicle_label, high_field = _resolve_toll_pricing(company)

    # Maximum distance (km) between a polyline point and a toll gantry
    # coordinate to consider it a match. Reduced from 1.5 to 1.0 km after
    # confirming empirically that troncal/salida gantry pairs on the AP-7
    # (Calahonda, San Pedro, Manilva) sit ~2.6-2.9 km apart — 1.0 km keeps
    # a safe margin against cross-matching a troncal barrier with its
    # nearby salida barrier (or vice versa) while still tolerating GPS/
    # polyline noise. Adjust empirically per Miguel Ángel's testing.
    # ---
    # Distancia máxima (km) entre un punto de la polyline y la
    # coordenada de una cabina de peaje para considerarlo coincidencia.
    # Reducido de 1.5 a 1.0 km tras confirmar empíricamente que los
    # pares troncal/salida de la AP-7 (Calahonda, San Pedro, Manilva)
    # están separados ~2,6-2,9 km — 1.0 km deja margen de seguridad
    # frente a confundir una barrera troncal con su salida cercana (o
    # viceversa) sin dejar de tolerar el ruido de GPS/polyline. Ajustar
    # empíricamente según las pruebas de Miguel Ángel.
    SNAP_KM = 1.0

    # Load all geocoded active segments.
    # Cargar todos los segmentos geocodificados activos.
    segments = TollSegment.objects.filter(
        origin_lat__isnull=False,
        origin_lng__isnull=False,
        dest_lat__isnull=False,
        dest_lng__isnull=False,
        is_active=True,
    ).only(
        "road_code", "origin_name", "dest_name",
        "origin_lat", "origin_lng",
        "dest_lat", "dest_lng",
        "price_light", "price_heavy_1", "price_heavy_2",
        "price_light_high", "price_heavy_1_high", "price_heavy_2_high",
        "season_high_start", "season_high_end",
    )

    result = []

    def _find_occurrences(target_lat, target_lng, snap_km):
        """
        Scans the polyline sequentially and returns the index of the
        closest point for EACH separate pass near (target_lat,
        target_lng) — i.e. every time the route comes within snap_km
        and then moves away again counts as one occurrence. This is
        the key fix versus a single global-nearest search: a round
        trip passes the same physical point twice (outbound + return),
        and each pass must be detected independently.
        ---
        Recorre la polyline secuencialmente y devuelve el índice del
        punto más cercano para CADA pase por separado cerca de
        (target_lat, target_lng) — es decir, cada vez que la ruta entra
        en snap_km y luego se aleja cuenta como una ocurrencia. Esta es
        la corrección clave frente a una búsqueda de mínimo global
        único: un viaje de ida y vuelta pasa por el mismo punto físico
        dos veces (ida + vuelta), y cada paso debe detectarse de forma
        independiente.
        """
        occurrences = []
        i = 0
        n = len(points)
        while i < n:
            p_lat, p_lng = points[i]
            dist = _haversine_km(p_lat, p_lng, target_lat, target_lng)
            if dist <= snap_km:
                # Start of a contiguous close cluster (one physical
                # pass) — find its closest point, then skip past it.
                # Inicio de un cluster contiguo cercano (un pase
                # físico) — buscar su punto más cercano y saltarlo.
                best_idx = i
                best_dist = dist
                j = i
                while j < n:
                    pj_lat, pj_lng = points[j]
                    dj = _haversine_km(pj_lat, pj_lng, target_lat, target_lng)
                    if dj <= snap_km:
                        if dj < best_dist:
                            best_dist = dj
                            best_idx = j
                        j += 1
                    else:
                        break
                occurrences.append(best_idx)
                i = j
            else:
                i += 1
        return occurrences

    def _append_segment_result(seg, count):
        """
        Appends `count` result entries for a fully-resolved segment.
        Price/season resolution delegated to the shared helper
        _price_for_toll_segment() (ver _resolve_toll_pricing() más arriba).
        ---
        Añade `count` entradas de resultado para un tramo ya resuelto.
        Resolución de precio/temporada delegada al helper compartido
        _price_for_toll_segment() (ver _resolve_toll_pricing() más arriba).
        """
        price, is_high_season, season_type = _price_for_toll_segment(
            seg, service_date, price_field, high_field
        )
        segment_name = (
            f"{seg.road_code} | {seg.origin_name} \u2192 {seg.dest_name}"
        )
        for _ in range(count):
            result.append({
                "segment_name":       segment_name,
                "vehicle_type_label": vehicle_label,
                "price":              price,
                "is_high_season":     is_high_season,
                "season_type":        season_type,
            })

    # -------------------------------------------------------------------
    # AP-7 TRONCAL / SALIDA gate resolution — the physical toll booths at
    # Calahonda, San Pedro and Manilva each have TWO separate gantries: a
    # 'Troncal' one on the main carriageway (crossed when the route drives
    # straight through) and a 'Salida' one on the exit ramp (crossed only
    # when the route actually exits/enters at that junction). Matching
    # each booth's coordinate independently (as the generic point-matching
    # below does) cannot tell these apart when both booths sit within
    # SNAP_KM of each other's vicinity along the corridor — it would
    # wrongly charge BOTH.
    #
    # Instead, for each of these three locations, two checkpoint
    # coordinates further along the corridor (provided by Miguel Ángel,
    # verified empirically against the real road) determine which gantry
    # applies: if the route passes checkpoint_a AND checkpoint_b, it
    # continued past the junction → TRONCAL; if it passes checkpoint_a but
    # NOT checkpoint_b, it exited/entered at the junction → SALIDA. Each
    # occurrence of checkpoint_a is resolved independently, so a round
    # trip that continues through on the outbound leg but exits on the
    # return leg (or vice versa) is billed correctly per direction.
    #
    # AP-46 (Casabermeja) has no such ambiguity — it is a single physical
    # barrier with no separate troncal/salida gantries — so it is left to
    # the generic point-matching loop below, unaffected by this block.
    # ---
    # Resolución de puertas TRONCAL / SALIDA de la AP-7 — las cabinas
    # físicas de Calahonda, San Pedro y Manilva tienen cada una DOS
    # pórticos separados: uno 'Troncal' en el carril principal (se cruza
    # si la ruta sigue recto) y uno 'Salida' en el ramal de salida (se
    # cruza solo si la ruta realmente sale/entra por ese enlace). Emparejar
    # la coordenada de cada cabina de forma independiente (como hace el
    # emparejamiento genérico de más abajo) no puede distinguirlas cuando
    # ambas caen dentro de SNAP_KM la una de la otra a lo largo del
    # corredor — cobraría las DOS por error.
    #
    # En su lugar, para cada una de estas tres ubicaciones, dos
    # coordenadas de control más adelante en el corredor (proporcionadas
    # por Miguel Ángel, verificadas empíricamente contra la carretera
    # real) determinan qué pórtico aplica: si la ruta pasa por checkpoint_a
    # Y checkpoint_b, siguió recto pasado el enlace → TRONCAL; si pasa por
    # checkpoint_a pero NO por checkpoint_b, salió/entró por el enlace →
    # SALIDA. Cada ocurrencia de checkpoint_a se resuelve de forma
    # independiente, así que un viaje de ida y vuelta que sigue recto a la
    # ida pero sale a la vuelta (o al revés) se factura correctamente por
    # sentido.
    #
    # La AP-46 (Casabermeja) no tiene esta ambigüedad — es una barrera
    # física única sin pórticos troncal/salida separados — así que queda
    # para el bucle genérico de más abajo, sin verse afectada por este
    # bloque.
    AP7_GATE_PAIRS = [
        {
            "checkpoint_a": (36.53893578993178, -4.676974059446321),
            "checkpoint_b": (36.50508152174629, -4.740510226751807),
            "troncal_name": "Calahonda Troncal",
            "salida_name":  "Salida Calahonda",
        },
        {
            "checkpoint_a": (36.52631071669154, -4.964125499305323),
            "checkpoint_b": (36.490054579403406, -5.043082933396812),
            "troncal_name": "San Pedro Troncal",
            "salida_name":  "Salida San Pedro",
        },
        {
            "checkpoint_a": (36.394235158954636, -5.252037189233206),
            "checkpoint_b": (36.37092252215686, -5.268302104630619),
            "troncal_name": "Manilva Troncal",
            "salida_name":  "Salida Manilva",
        },
    ]

    def _resolve_gate_pair(checkpoint_a, checkpoint_b):
        """
        Returns a list with one 'TRONCAL' or 'SALIDA' string per detected
        pass through checkpoint_a, decided by whether that same pass also
        reaches checkpoint_b.
        ---
        Devuelve una lista con un 'TRONCAL' o 'SALIDA' por cada pase
        detectado por checkpoint_a, decidido según si ese mismo pase
        alcanza también checkpoint_b.
        """
        a_lat, a_lng = checkpoint_a
        b_lat, b_lng = checkpoint_b
        a_occurrences = sorted(_find_occurrences(a_lat, a_lng, SNAP_KM))
        b_occurrences = sorted(_find_occurrences(b_lat, b_lng, SNAP_KM))

        used_b = set()
        decisions = []
        for a_idx in a_occurrences:
            best_b_idx = None
            best_gap = None
            for b_idx in b_occurrences:
                if b_idx in used_b:
                    continue
                gap = abs(b_idx - a_idx)
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    best_b_idx = b_idx
            if best_b_idx is not None:
                used_b.add(best_b_idx)
                decisions.append("TRONCAL")
            else:
                decisions.append("SALIDA")
        return decisions

    segments_by_name = {s.origin_name: s for s in segments}
    gated_names = set()
    for gate in AP7_GATE_PAIRS:
        gated_names.add(gate["troncal_name"])
        gated_names.add(gate["salida_name"])

        decisions = _resolve_gate_pair(
            gate["checkpoint_a"], gate["checkpoint_b"]
        )
        troncal_count = decisions.count("TRONCAL")
        salida_count  = decisions.count("SALIDA")

        if troncal_count:
            seg = segments_by_name.get(gate["troncal_name"])
            if seg is not None:
                _append_segment_result(seg, troncal_count)
        if salida_count:
            seg = segments_by_name.get(gate["salida_name"])
            if seg is not None:
                _append_segment_result(seg, salida_count)

    # -------------------------------------------------------------------
    # Generic point/segment matching — for everything NOT covered by the
    # AP-7 gate logic above (e.g. AP-46 Casabermeja, a single physical
    # barrier with no troncal/salida ambiguity, and any future toll with
    # the same simple structure).
    # ---
    # Emparejamiento genérico de punto/tramo — para todo lo NO cubierto
    # por la lógica de puertas AP-7 de arriba (p.ej. AP-46 Casabermeja,
    # una barrera física única sin ambigüedad troncal/salida, y cualquier
    # peaje futuro con la misma estructura simple).
    for seg in segments:
        if seg.origin_name in gated_names:
            continue

        o_lat = float(seg.origin_lat)
        o_lng = float(seg.origin_lng)
        d_lat = float(seg.dest_lat)
        d_lng = float(seg.dest_lng)

        same_point = (
            abs(o_lat - d_lat) < 0.0001
            and abs(o_lng - d_lng) < 0.0001
        )

        matched_pairs = []

        if same_point:
            for idx in _find_occurrences(o_lat, o_lng, SNAP_KM):
                matched_pairs.append((idx, idx))
        else:
            o_occurrences = sorted(_find_occurrences(o_lat, o_lng, SNAP_KM))
            d_occurrences = sorted(_find_occurrences(d_lat, d_lng, SNAP_KM))

            used_d = set()
            for o_idx in o_occurrences:
                best_d_idx = None
                best_gap = None
                for d_idx in d_occurrences:
                    if d_idx in used_d:
                        continue
                    gap = abs(d_idx - o_idx)
                    if best_gap is None or gap < best_gap:
                        best_gap = gap
                        best_d_idx = d_idx
                if best_d_idx is not None:
                    used_d.add(best_d_idx)
                    matched_pairs.append((o_idx, best_d_idx))

        if not matched_pairs:
            continue

        _append_segment_result(seg, len(matched_pairs))

    return result


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

    # Google's Routes API rejects a past departureTime for DRIVE mode —
    # only include it (with TRAFFIC_AWARE) when the service date is in
    # the future. Verified against current Routes API docs (2026-06).
    # Google rechaza un departureTime pasado para modo DRIVE — solo se
    # incluye (con TRAFFIC_AWARE) cuando la fecha de servicio es futura.
    include_traffic = service_datetime > datetime.datetime.utcnow()

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
                include_traffic=include_traffic,
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
                include_traffic=include_traffic,
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
                    _round2(sum(
                        d["price"]
                        for d in _compute_toll_cost(
                            result["encoded_polyline"],
                            company,
                            service_datetime.date()
                            if service_datetime else None,
                        )
                    ))
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
                include_traffic=include_traffic,
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
                include_traffic=include_traffic,
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
                include_traffic=include_traffic,
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
                include_traffic=include_traffic,
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
                toll_cost = _round2(
                    sum(
                        d["price"]
                        for d in _compute_toll_cost(
                            result1["encoded_polyline"], company, svc_date
                        )
                    )
                    + sum(
                        d["price"]
                        for d in _compute_toll_cost(
                            result2["encoded_polyline"], company, svc_date
                        )
                    )
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


def _build_toll_budget_lines(
    toll_details: list,
    markup_percent: Decimal,
    sort_order_start: int = 300,
) -> tuple:
    """
    Build BudgetLine instances (unsaved) from the toll detail list returned
    by _compute_toll_cost, applying company markup_percent.

    Returns (lines, total_with_markup) where:
      - lines: list of BudgetLine (not yet saved to DB)
      - total_with_markup: Decimal total added to base_total

    One BudgetLine per matched TollSegment (CODE_TOLL_SEGMENT), each showing:
      segment name, vehicle type applied, price, and season label if any.
    If markup_percent > 0, one additional BudgetLine (CODE_TOLL_MARKUP) is
    appended showing the markup amount.
    ---
    Construye instancias BudgetLine (sin guardar) a partir de la lista de
    detalles de peajes devuelta por _compute_toll_cost, aplicando el recargo
    de empresa markup_percent.

    Devuelve (lines, total_with_markup) donde:
      - lines: lista de BudgetLine (sin guardar en BD)
      - total_with_markup: Decimal total sumado a base_total

    Una BudgetLine por tramo detectado (CODE_TOLL_SEGMENT), mostrando:
      nombre del tramo, tipo de vehiculo, precio y etiqueta de temporada si
      aplica. Si markup_percent > 0, se anade una linea adicional
      (CODE_TOLL_MARKUP) con el importe del recargo.
    """
    from budgets.models import TariffConcept

    lines = []
    subtotal = Decimal("0.00")
    sort_order = sort_order_start

    for detail in toll_details:
        seg_name    = detail["segment_name"]
        veh_label   = detail["vehicle_type_label"]
        price       = detail["price"]
        is_high     = detail["is_high_season"]
        season_type = detail["season_type"]

        # Build a descriptive label for the operator/ADMIN.
        # Construir etiqueta descriptiva para operario/ADMIN.
        label_parts = [seg_name, f"({veh_label})"]
        if is_high and season_type == "SEMANA_SANTA":
            label_parts.append("— Temp. alta (Semana Santa)")
        elif is_high:
            label_parts.append("— Temp. alta (verano)")
        else:
            label_parts.append("— Temp. baja")
        label = " ".join(label_parts)

        lines.append(BudgetLine(
            concept_code=TariffConcept.CODE_TOLL_SEGMENT,
            concept_label=label,
            units=Decimal("1"),
            unit_price=price,
            subtotal=price,
            is_surcharge=False,
            is_informational=False,
            sort_order=sort_order,
        ))
        subtotal += price
        sort_order += 1

    if not lines:
        return [], Decimal("0.00")

    # Apply company markup if configured.
    # Aplicar recargo de empresa si esta configurado.
    if markup_percent and markup_percent > 0:
        markup_amount = _round2(
            subtotal * markup_percent / Decimal("100")
        )
        if markup_amount > 0:
            lines.append(BudgetLine(
                concept_code=TariffConcept.CODE_TOLL_MARKUP,
                concept_label=(
                    f"Recargo peajes ({markup_percent}%)"
                ),
                units=Decimal("1"),
                unit_price=markup_amount,
                subtotal=markup_amount,
                is_surcharge=True,
                is_informational=False,
                sort_order=sort_order,
            ))
            total_with_markup = _round2(subtotal + markup_amount)
        else:
            total_with_markup = _round2(subtotal)
    else:
        total_with_markup = _round2(subtotal)

    return lines, total_with_markup


# ---------------------------------------------------------------------------
# Tariff PDF extraction service (Gemini Vision)
# Servicio de extracción de PDF de tarifa (Gemini Vision)
# ---------------------------------------------------------------------------

import logging as _log_svc
import pathlib as _pathlib_svc
from decimal import Decimal as _Decimal, InvalidOperation as _InvalidOperation
from typing import Optional as _Optional

from google.genai import types as _genai_types
from pydantic import BaseModel as _BaseModel, Field as _Field

from ai_services.gemini_client import (
    DEFAULT_MODEL as _DEFAULT_MODEL,
    get_gemini_client as _get_gemini_client,
    get_request_config as _get_request_config,
)

_logger_tariff = _log_svc.getLogger(__name__)


class ExtractedTariffLine(_BaseModel):
    """
    Single price line extracted from the tariff PDF, for one rate period
    (LABORABLE or FESTIVO/NOCTURNO). May match an existing concept from the
    catalog passed in the prompt, or propose a new one when no existing
    concept is semantically equivalent.
    ---
    Línea de precio individual extraída del PDF de tarifa, para un periodo
    de tarifa (LABORABLE o FESTIVO/NOCTURNO). Puede emparejar con un
    concepto existente del catálogo pasado en el prompt, o proponer uno
    nuevo cuando ningún concepto existente es semánticamente equivalente.
    """

    concept_code_match: _Optional[str] = _Field(
        default=None,
        description=(
            "Código EXACTO (tal cual aparece en el catálogo proporcionado) "
            "del concepto existente que corresponde semánticamente a esta "
            "línea del PDF. Null si esta línea representa un concepto de "
            "facturación distinto a todos los del catálogo."
        ),
    )
    concept_new_label: _Optional[str] = _Field(
        default=None,
        description=(
            "Obligatorio solo si concept_code_match es null. Nombre "
            "descriptivo y distintivo propuesto para el concepto nuevo, en "
            "castellano, tal como debería aparecer en el desplegable de "
            "líneas de tarifa (ej. 'Forfait Salida (Reparación in situ)', "
            "'Hora de trabajo mecánico (in situ)'). Debe distinguirse "
            "claramente de cualquier concepto ya existente en el catálogo "
            "aunque el nombre en el PDF se parezca."
        ),
    )
    concept_new_unit: _Optional[str] = _Field(
        default=None,
        description=(
            "Solo si concept_code_match es null. Unidad del concepto "
            "nuevo: uno de 'FIXED' (importe fijo), 'PER_KM' (por "
            "kilómetro), 'PER_HOUR' (por hora), 'PER_DAY' (por día), "
            "'PERCENT' (porcentaje)."
        ),
    )
    vehicle_type_name: _Optional[str] = _Field(
        default=None,
        description=(
            "Nombre exacto del tramo de peso o tipo de vehículo al que "
            "aplica esta línea, tal como aparece en el PDF. Null si el "
            "concepto es genérico y no varía por tipo de vehículo (aplica "
            "un único precio para toda la tarifa)."
        ),
    )
    price: _Optional[str] = _Field(
        default=None,
        description=(
            "Precio de esta línea, como texto numérico con punto decimal, "
            "sin símbolo de moneda. Para conceptos PERCENT, el número del "
            "porcentaje (ej. '45' para un recargo del 45%). Null si no es "
            "legible."
        ),
    )


class TariffPdfExtraction(_BaseModel):
    """
    Full structured extraction from a single insurer column of a tariff
    PDF, driven entirely by the concept catalog and night/holiday mode
    supplied in the prompt at call time — no concept names are hardcoded
    in this schema or in the service.
    ---
    Extracción estructurada completa de la columna de una aseguradora en
    un PDF de tarifa, guiada por completo por el catálogo de conceptos y
    el modo nocturno/festivo suministrados en el prompt en cada llamada —
    ningún nombre de concepto está hardcodeado en este esquema ni en el
    servicio.
    """

    detected_insurer_name: _Optional[str] = _Field(
        default=None,
        description=(
            "Nombre de la aseguradora tal como figura en la cabecera de la "
            "columna seleccionada. Null si no es legible."
        ),
    )
    laborable_lines: list[ExtractedTariffLine] = _Field(
        default_factory=list,
        description=(
            "TODAS las líneas de precio LABORABLE encontradas en la "
            "columna seleccionada del PDF, de TODAS las secciones/tablas "
            "presentes (remolcaje, reparación in situ, u otras), no solo "
            "las que coincidan con conceptos ya conocidos."
        ),
    )
    festivo_lines: list[ExtractedTariffLine] = _Field(
        default_factory=list,
        description=(
            "TODAS las líneas de precio FESTIVO/NOCTURNO encontradas, "
            "misma estructura que laborable_lines. Se rellena SOLO si el "
            "prompt indica modo de tabla festiva completa; en modo "
            "recargo porcentual, dejar vacío."
        ),
    )
    night_holiday_surcharge_percent: _Optional[str] = _Field(
        default=None,
        description=(
            "Solo relevante en modo de recargo porcentual: el porcentaje "
            "de recargo nocturno/festivo indicado en el PDF (ej. '45' si "
            "el texto dice 'recargo del 45%'), como texto numérico. Null "
            "si no se indica o si el modo es de tabla festiva completa."
        ),
    )


def _build_concept_catalog_text(concepts) -> str:
    """
    Renders the TariffConcept queryset as a plain-text catalog listing for
    injection into the Gemini prompt. Dynamic — reflects whatever concepts
    currently exist (system + company-custom) at call time.
    ---
    Renderiza el queryset de TariffConcept como listado de texto plano para
    inyectar en el prompt de Gemini. Dinámico — refleja los conceptos que
    existan en ese momento (sistema + personalizados de la empresa).
    """
    lines = []
    for c in concepts:
        lines.append(f"- código: {c.code} | nombre: {c.label} | unidad: {c.default_unit}")
    return "\n".join(lines) if lines else "(catálogo vacío)"


def _build_tariff_extraction_prompt(
    insurer_company_name: str,
    concept_catalog_text: str,
    full_night_holiday_table: bool,
) -> str:
    """
    Builds the Gemini prompt for tariff PDF extraction. Fully generic:
    no company or concept names are hardcoded anywhere in this function.
    Two dynamic inputs shape the instructions:
      - concept_catalog_text: the current TariffConcept catalog (system +
        company-custom), so Gemini can match or propose concepts against
        real data rather than a fixed schema.
      - full_night_holiday_table: derived from
        insurer.special_night_holiday_tariff, tells Gemini whether to
        extract a full separate FESTIVO/NOCTURNO price table or just a
        single surcharge percentage.
    ---
    Construye el prompt de Gemini para extracción de PDF de tarifa.
    Totalmente genérico: ningún nombre de empresa o concepto está
    hardcodeado en esta función. Dos entradas dinámicas dan forma a las
    instrucciones:
      - concept_catalog_text: el catálogo TariffConcept actual (sistema +
        personalizados de la empresa), para que Gemini empareje o
        proponga conceptos contra datos reales en vez de un esquema fijo.
      - full_night_holiday_table: derivado de
        insurer.special_night_holiday_tariff, indica a Gemini si debe
        extraer una tabla FESTIVO/NOCTURNO completa separada o solo un
        porcentaje de recargo único.
    """
    if full_night_holiday_table:
        night_holiday_instructions = (
            "MODO NOCTURNO/FESTIVO: esta aseguradora usa una TABLA DE "
            "PRECIOS COMPLETA Y SEPARADA para servicios nocturnos/"
            "festivos (no un simple recargo porcentual). Busca en el PDF "
            "las secciones o columnas tituladas 'Festivo', 'Nocturno', "
            "'Festivo/Nocturno' o similar, y extrae TODAS sus líneas de "
            "precio en festivo_lines, con la misma estructura y el mismo "
            "criterio de emparejamiento de conceptos que laborable_lines. "
            "Dejar night_holiday_surcharge_percent en null."
        )
    else:
        night_holiday_instructions = (
            "MODO RECARGO PORCENTUAL: esta aseguradora NO tiene tabla de "
            "precios festiva separada. Busca en el texto del PDF una "
            "mención a un recargo nocturno y/o festivo expresado en "
            "porcentaje (ej. 'recargo del 45%', 'incremento nocturno "
            "20%') y extrae ese número en night_holiday_surcharge_percent. "
            "Deja festivo_lines vacío."
        )

    return (
        f"Eres un asistente experto en tarifas de asistencia en carretera "
        f"para vehículos industriales pesados (camiones, grúas, autocares, "
        f"cabezas tractoras).\n\n"
        f"El documento adjunto es un PDF de tarifa de asistencia que puede "
        f"contener columnas de precios para varias compañías aseguradoras.\n\n"
        f"AVISO SOBRE EL NOMBRE DE LA ASEGURADORA: el nombre proporcionado "
        f"es '{insurer_company_name}'. Si este nombre tiene el formato "
        f"'CompañíaA - CompañíaB' (dos nombres de compañía separados por "
        f"un guion), significa que se trata de un PAR de aseguradoras que "
        f"colaboran entre sí. En ese caso, si el PDF muestra una columna "
        f"de precios para CompañíaA y otra columna distinta para "
        f"CompañíaB, debes extraer ÚNICAMENTE la columna de la PRIMERA "
        f"compañía nombrada (CompañíaA, la que aparece antes del guion), "
        f"e ignorar por completo la columna de la segunda (CompañíaB) y "
        f"cualquier otra columna presente en el documento. El orden "
        f"importa: 'CompañíaA - CompañíaB' y 'CompañíaB - CompañíaA' "
        f"identifican columnas distintas dentro del mismo PDF.\n\n"
        f"Si el nombre proporcionado NO tiene formato de par (es una única "
        f"compañía), localiza directamente la columna cuya cabecera "
        f"coincida con ese nombre.\n\n"
        f"CATÁLOGO DE CONCEPTOS EXISTENTES (código | nombre | unidad):\n"
        f"{concept_catalog_text}\n\n"
        f"TAREA: Extrae TODAS las líneas de precio de la columna "
        f"seleccionada, de TODAS las secciones/tablas del PDF que "
        f"contengan precios negociados con esta aseguradora (remolcaje "
        f"por tramo de peso, reparación en el sitio sin remolcaje, "
        f"conceptos generales sueltos como desbloqueo/espera/mano de "
        f"obra, o cualquier otra sección de precios que exista). No te "
        f"limites a categorías predefinidas: si el PDF tiene una sección "
        f"de precios que no aparece en el catálogo, extráela igualmente "
        f"como concepto nuevo.\n\n"
        f"EMPAREJAMIENTO DE CONCEPTOS: para cada línea, decide si "
        f"corresponde a un concepto YA EXISTENTE en el catálogo de "
        f"arriba:\n"
        f"- Empareja (concept_code_match) SOLO si es real y "
        f"genuinamente el MISMO concepto de facturación: mismo tipo de "
        f"servicio, mismo ámbito de aplicación (por ejemplo, un forfait "
        f"de salida de REMOLCAJE que varía por tramo de peso NO es lo "
        f"mismo que un forfait de salida de REPARACIÓN IN SITU con un "
        f"único importe fijo, aunque ambos se llamen 'Forfait Salida' en "
        f"el PDF — son conceptos distintos).\n"
        f"- Si tienes dudas razonables de que sea el mismo concepto, o el "
        f"concepto pertenece a una sección/servicio distinto aunque el "
        f"nombre se parezca, NO empareges: deja concept_code_match en "
        f"null y propón un concepto nuevo (concept_new_label, "
        f"concept_new_unit) con un nombre que lo distinga claramente del "
        f"existente.\n\n"
        f"{night_holiday_instructions}\n\n"
        f"REGLAS GENERALES:\n"
        f"- Devuelve los precios como texto numérico simple, usando punto "
        f"como separador decimal, sin símbolo de moneda.\n"
        f"- Si un precio usa coma como decimal en el PDF (p. ej. "
        f"'138,88'), conviértelo a punto ('138.88').\n"
        f"- Si un concepto no figura en la columna seleccionada, omítelo "
        f"(no generes líneas con precio null salvo que el dato "
        f"simplemente no sea legible).\n"
        f"- No inventes precios ni conceptos que no puedas leer con "
        f"certeza en el documento."
    )


class TariffPdfExtractionService:
    """
    Extracts structured tariff data from a single insurer column of a
    tariff PDF using Gemini Vision via the shared ai_services.gemini_client
    helper. Uses gemini-3.5-flash (Directriz 4.1, mandatory for new code).
    Fully data-driven: the concept catalog and night/holiday mode are
    read from the database at call time and injected into the prompt —
    no insurer or concept names are hardcoded in this service, so it
    works identically for any insurer pair or single insurer, and for
    any concept negotiated with any company.

    ---

    Extrae datos estructurados de tarifa de la columna de una aseguradora
    en un PDF de tarifa usando Gemini Vision a través del helper
    compartido ai_services.gemini_client. Usa gemini-3.5-flash (Directriz
    4.1, obligatorio para código nuevo).
    Totalmente guiado por datos: el catálogo de conceptos y el modo
    nocturno/festivo se leen de la base de datos en el momento de la
    llamada y se inyectan en el prompt — ningún nombre de aseguradora o
    concepto está hardcodeado en este servicio, así que funciona igual
    para cualquier par de aseguradoras o aseguradora individual, y para
    cualquier concepto negociado con cualquier empresa.
    """

    _MIME_TYPES = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    def __init__(self, model: str = _DEFAULT_MODEL):
        self._model = model

    def extract(self, file_path: str, insurer) -> TariffPdfExtraction:
        """
        Sends the tariff PDF at file_path to Gemini Vision and returns
        the structured extraction for the column matching
        insurer.insurer_company_name, using insurer.company's concept
        catalog and insurer.special_night_holiday_tariff to shape the
        prompt.

        Args:
            file_path: Absolute path to the PDF file on disk.
            insurer: Insurer instance (the ORIGINAL/source insurer, not
                the copy) whose insurer_company_name, company and
                special_night_holiday_tariff drive the extraction.

        Raises:
            ValueError: if the file extension is not a supported MIME
                type.

        ---

        Envía el PDF de tarifa en file_path a Gemini Vision y devuelve
        la extracción estructurada de la columna que corresponde a
        insurer.insurer_company_name, usando el catálogo de conceptos de
        insurer.company e insurer.special_night_holiday_tariff para dar
        forma al prompt.

        Args:
            file_path: Ruta absoluta al archivo PDF en disco.
            insurer: Instancia de Insurer (la ORIGEN, no la copia) cuyo
                insurer_company_name, company y
                special_night_holiday_tariff guían la extracción.

        Raises:
            ValueError: si la extensión del archivo no es un tipo MIME
                soportado.
        """
        from budgets.models import TariffConcept
        from django.db.models import Q as _Q

        path = _pathlib_svc.Path(file_path)
        mime_type = self._MIME_TYPES.get(path.suffix.lower())
        if mime_type is None:
            raise ValueError(
                f"Extensión no soportada para extracción de tarifa: "
                f"{path.suffix!r}. Tipos válidos: {sorted(self._MIME_TYPES)}."
            )

        insurer_company_name = insurer.insurer_company_name or insurer.name

        concepts = TariffConcept.objects.filter(
            _Q(is_system=True) | _Q(company=insurer.company)
        ).order_by("sort_order", "label")
        concept_catalog_text = _build_concept_catalog_text(concepts)

        client = _get_gemini_client()
        request_config = _get_request_config()

        file_part = _genai_types.Part.from_bytes(
            data=path.read_bytes(),
            mime_type=mime_type,
        )

        prompt = _build_tariff_extraction_prompt(
            insurer_company_name=insurer_company_name,
            concept_catalog_text=concept_catalog_text,
            full_night_holiday_table=bool(insurer.special_night_holiday_tariff),
        )

        generation_config = _genai_types.GenerateContentConfig(
            http_options=request_config.http_options,
            response_mime_type="application/json",
            response_schema=TariffPdfExtraction,
        )

        _logger_tariff.info(
            "# Enviando PDF de tarifa a Gemini Vision (modelo=%s, "
            "archivo=%s, aseguradora=%r, modo_festivo_completo=%s).",
            self._model, path.name, insurer_company_name,
            insurer.special_night_holiday_tariff,
        )

        response = client.models.generate_content(
            model=self._model,
            contents=[file_part, prompt],
            config=generation_config,
        )

        extraction = TariffPdfExtraction.model_validate_json(response.text)

        _logger_tariff.info(
            "# Extracción de tarifa completada: aseguradora_detectada=%r, "
            "lineas_lab=%d, lineas_fest=%d, recargo_pct=%r.",
            extraction.detected_insurer_name,
            len(extraction.laborable_lines),
            len(extraction.festivo_lines),
            extraction.night_holiday_surcharge_percent,
        )

        return extraction


def _parse_tariff_decimal(value: _Optional[str]) -> _Optional[_Decimal]:
    """
    Safely parses a numeric string from Gemini tariff extraction into a
    Decimal. Returns None if value is missing or not parseable.
    ---
    Parsea de forma segura un texto numérico de la extracción de tarifa
    de Gemini a Decimal. Devuelve None si el valor falta o no es parseable.
    """
    if not value:
        return None
    try:
        return _Decimal(str(value).replace(",", "."))
    except (_InvalidOperation, ValueError):
        _logger_tariff.warning(
            "# Valor numérico no parseable en extracción de tarifa: %r.",
            value,
        )
        return None


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

    # Calculate is_night_or_holiday from is_night (operator/NightSchedule)
    # and is_holiday (automatic from labor_calendar + weekends) — the
    # calendar lookup ALWAYS runs, in both API and Manual mode. The wizard's
    # Manual mode checkbox (is_night_or_holiday_manual_override) only FORCES
    # the result to True when explicitly selected — it never suppresses a
    # True calendar/night result, and leaving it unselected (False or None)
    # simply falls back to the automatic calendar-based result. This lets
    # an operator mark a service as nocturno/festivo by agreement with the
    # insurer even when the date/schedule wouldn't otherwise qualify.
    # ---
    # Calcular is_night_or_holiday desde is_night (operario/NightSchedule) e
    # is_holiday (automatico desde labor_calendar + fines de semana) — la
    # consulta al calendario SIEMPRE se ejecuta, tanto en modo API como en
    # modo Manual. El checkbox del modo Manual del wizard
    # (is_night_or_holiday_manual_override) solo FUERZA el resultado a True
    # cuando se selecciona explícitamente — nunca suprime un resultado True
    # del calendario/horario, y dejarlo sin marcar (False o None) recurre
    # simplemente al resultado automático basado en calendario. Esto permite
    # marcar un servicio como nocturno/festivo por acuerdo con la
    # aseguradora aunque la fecha/horario no lo justifique por sí solos.
    is_holiday = (
        _is_holiday(budget.service_date, budget.base)
        if budget.service_date
        else False
    )
    auto_night_or_holiday = budget.is_night or is_holiday
    if budget.is_night_or_holiday_manual_override is True:
        budget.is_night_or_holiday = True
    else:
        budget.is_night_or_holiday = auto_night_or_holiday

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
    # 3. TOLL COST
    #
    # Modo Manual (route_calculation_mode=MANUAL): dos fuentes de peaje,
    # ambas opcionales y aditivas (no excluyentes entre sí):
    #   (a) Budget.manual_toll_segments — selección itemizada de tramos
    #       TollSegment (troncal/salida, tipicamente AP-7/AP-46) con nº de
    #       pases, elegida en la tabla del wizard. Genera una BudgetLine
    #       por tramo, igual formato que el desglose de Modo B.
    #   (b) Budget.route_toll_budget_cost — importe manual "Otros peajes"
    #       (campo libre del wizard) para peajes fuera de la tabla. Genera
    #       una única línea catch-all TOLL_COST adicional si es > 0.
    #
    # Modo B (route_calculation_mode=API): cruza la polyline confirmada de
    # la ruta con TollSegment para generar una BudgetLine por tramo
    # detectado (nombre, tipo de vehículo, precio, temporada). Fallback a
    # línea única TOLL_COST cuando no hay polyline almacenada (presupuestos
    # legacy). Sin cambios respecto al comportamiento previo.
    #
    # En ambos modos: recargo de markup si company.toll_markup_percent > 0,
    # y el total (con recargo) se suma a base_total para que los recargos
    # NYF/cargado se apliquen encima.
    # ------------------------------------------------------------------
    company = getattr(insurer, "company", None)
    markup_pct = Decimal(
        str(getattr(company, "toll_markup_percent", 0) or 0)
    ) if company else Decimal("0.00")

    if budget.route_calculation_mode == Budget.ROUTE_MODE_MANUAL:
        # (a) Desglose itemizado por tramo elegido en la tabla del wizard.
        if budget.manual_toll_segments:
            toll_details = _compute_manual_toll_cost(
                budget.manual_toll_segments,
                company=company,
                service_date=budget.service_date,
            )
            if toll_details:
                toll_lines, toll_total = _build_toll_budget_lines(
                    toll_details,
                    markup_pct,
                    sort_order_start=300,
                )
                for tl in toll_lines:
                    tl.budget = budget
                    result_lines.append(tl)
                base_total += toll_total

        # (b) Importe manual catch-all "Otros peajes" — aditivo, no
        # sustituye al desglose itemizado de (a).
        if budget.route_toll_budget_cost and budget.route_toll_budget_cost > 0:
            toll_amount = _round2(
                Decimal(str(budget.route_toll_budget_cost))
            )
            base_total += _add_line(
                "TOLL_COST",
                "Otros peajes",
                Decimal("1"),
                toll_amount,
            )
    elif budget.route_toll_budget_cost and budget.route_toll_budget_cost > 0:
        encoded_poly = (budget.encoded_polyline or "").strip()
        toll_details = []

        if encoded_poly:
            # Overnight services store two polylines joined by \x01.
            # Servicios de pernocta: dos polylines unidas por \x01.
            segments_poly = encoded_poly.split("\x01")
            for poly in segments_poly:
                poly = poly.strip()
                if poly:
                    toll_details.extend(
                        _compute_toll_cost(
                            poly,
                            company=company,
                            service_date=budget.service_date,
                        )
                    )

        if toll_details:
            toll_lines, toll_total = _build_toll_budget_lines(
                toll_details,
                markup_pct,
                sort_order_start=300,
            )
            for tl in toll_lines:
                tl.budget = budget
                result_lines.append(tl)
            base_total += toll_total
        else:
            # Fallback: no polyline stored — use pre-computed total.
            # Fallback: sin polyline — usar total precalculado.
            toll_amount = _round2(
                Decimal(str(budget.route_toll_budget_cost))
            )
            base_total += _add_line(
                "TOLL_COST",
                "Peajes de ruta",
                Decimal("1"),
                toll_amount,
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






