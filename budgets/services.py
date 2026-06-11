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
    for line in tariff.lines.filter(vehicle_type__isnull=True):
        lines[line.concept] = line

    # Override or add vehicle-specific lines.
    # Sobreescribir o anadir lineas especificas del tipo de vehiculo.
    for line in tariff.lines.filter(vehicle_type=vehicle_type):
        lines[line.concept] = line

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
    for line in srt.lines.filter(vehicle_type__isnull=True):
        lines[line.concept] = line
    for line in srt.lines.filter(vehicle_type=vehicle_type):
        lines[line.concept] = line
    return lines


# ---------------------------------------------------------------------------
# Holiday / night helper
# ---------------------------------------------------------------------------

def _is_holiday(date: datetime.date, base) -> bool:
    """
    Return True if the given date is a Saturday, Sunday, or a public holiday
    listed in base.labor_calendar. The calendar is stored as a JSON list of
    ISO date strings populated by the sync_base_calendars management command.
    If base is None or labor_calendar is empty, only weekend detection applies.
    ---
    Devuelve True si la fecha dada es sabado, domingo o festivo listado en
    base.labor_calendar. El calendario se almacena como lista JSON de fechas
    ISO poblada por el comando de gestion sync_base_calendars.
    Si base es None o labor_calendar esta vacio, solo se aplica la deteccion
    de fin de semana.
    """
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
        # Malformed calendar — degrade gracefully to weekend-only detection.
        # Calendario malformado — degradar a deteccion solo de fin de semana.
        return False

    # ISO date string for the given date: 'YYYY-MM-DD'.
    # Cadena de fecha ISO para la fecha dada: 'YYYY-MM-DD'.
    date_iso = date.isoformat()
    return date_iso in holidays


# ---------------------------------------------------------------------------
# Night schedule resolver
# Resolutor de horario nocturno
# ---------------------------------------------------------------------------


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


def calculate_route(
    base,
    road_name: str,
    pk_km: Decimal,
    service_datetime: datetime.datetime,
    dest_location: str = "",
) -> dict:
    """
    Calculate the route from a service base to a kilometre marker on a road
    using the Google Routes API. Returns a dict with distance_km, toll_cost
    and mode='API'. Raises RouteCalculationError on any failure.

    If base.latitude / base.longitude are null, geocodes the base municipality
    via the Geocoding API and persists the result before calling Routes API.

    The departureTime is built from service_datetime (UTC — PythonAnywhere
    runs in UTC) to ensure toll costs are time-dependent.
    ---
    Calcula la ruta desde una base de servicio hasta un punto kilometrico en
    una carretera usando la Google Routes API. Devuelve un dict con
    distance_km, toll_cost y mode='API'. Lanza RouteCalculationError ante
    cualquier fallo.

    Si base.latitude / base.longitude son nulos, geocodifica el municipio
    de la base via la Geocoding API y persiste el resultado antes de llamar
    a la Routes API.

    El departureTime se construye desde service_datetime (UTC — PythonAnywhere
    opera en UTC) para que los peajes sean dependientes de la hora.
    """
    import os
    import json
    import urllib.request
    import urllib.parse
    import urllib.error

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise RouteCalculationError(
            "GOOGLE_MAPS_API_KEY no configurada en el entorno."
        )

    # ── Step 1: ensure base has coordinates ─────────────────────────────
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
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?{geocode_query}"
        try:
            with urllib.request.urlopen(geocode_url, timeout=10) as resp:
                geo_data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RouteCalculationError(
                f"Geocoding API: error de red geocodificando la base '{base.name}': {exc}"
            ) from exc
        if geo_data.get("status") != "OK" or not geo_data.get("results"):
            raise RouteCalculationError(
                f"Geocoding API: no se encontraron coordenadas para "
                f"'{base.municipality}' (status: {geo_data.get('status')})."
            )
        geo_loc = geo_data["results"][0]["geometry"]["location"]
        base.latitude  = Decimal(str(geo_loc["lat"])).quantize(Decimal("0.000001"))
        base.longitude = Decimal(str(geo_loc["lng"])).quantize(Decimal("0.000001"))
        base.save(update_fields=["latitude", "longitude", "updated_at"])

    origin_lat = float(base.latitude)
    origin_lng = float(base.longitude)

    # ── Step 2: geocode the kilometre marker on the road ─────────────────
    # Paso 2: geocodificar el punto kilometrico en la carretera.
    import re as _re
    _road = road_name.strip().upper()
    _road = _re.sub(r'\s+', ' ', _road)
    _road = _re.sub(r'^([A-Z]+)-?([0-9])', r'\1-\2', _road)
    pk_int = int(pk_km)
    if dest_location:
        dest_query_str = f"{_road}, PK {pk_int}, {dest_location}, España"
    else:
        dest_query_str = f"{_road}, {pk_int}, España"
    geocode_dest_query = urllib.parse.urlencode({
        "address": dest_query_str,
        "key": api_key,
        "language": "es",
        "region": "es",
    })
    geocode_dest_url = (
        f"https://maps.googleapis.com/maps/api/geocode/json?{geocode_dest_query}"
    )
    try:
        with urllib.request.urlopen(geocode_dest_url, timeout=10) as resp:
            dest_data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RouteCalculationError(
            f"Geocoding API: error de red geocodificando el punto "
            f"'{dest_query_str}': {exc}"
        ) from exc
    if dest_data.get("status") != "OK" or not dest_data.get("results"):
        raise RouteCalculationError(
            f"Geocoding API: no se encontraron coordenadas para "
            f"'{dest_query_str}' (status: {dest_data.get('status')})."
        )
    dest_loc = dest_data["results"][0]["geometry"]["location"]
    dest_lat = dest_loc["lat"]
    dest_lng = dest_loc["lng"]

    # ── Step 3: build departureTime in RFC 3339 UTC ───────────────────────
    # Paso 3: construir departureTime en RFC 3339 UTC.
    # PythonAnywhere operates in UTC — no conversion needed.
    # PythonAnywhere opera en UTC — no se necesita conversion.
    departure_time_str = service_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Step 4: call Routes API ───────────────────────────────────────────
    # Paso 4: llamar a la Routes API.
    routes_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    routes_payload = json.dumps({
        "origin": {
            "location": {
                "latLng": {"latitude": origin_lat, "longitude": origin_lng}
            }
        },
        "destination": {
            "location": {
                "latLng": {"latitude": dest_lat, "longitude": dest_lng}
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "departureTime": departure_time_str,
        "extraComputations": ["TOLLS"],
    }).encode("utf-8")
    routes_headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "routes.distanceMeters,"
            "routes.duration,"
            "routes.travelAdvisory.tollInfo"
        ),
    }
    routes_request = urllib.request.Request(
        routes_url,
        data=routes_payload,
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

    # ── Step 5: extract distance and tolls ───────────────────────────────
    # Paso 5: extraer distancia y peajes.
    routes = routes_data.get("routes", [])
    if not routes:
        raise RouteCalculationError(
            "Routes API: la respuesta no contiene ninguna ruta. "
            f"Respuesta completa: {str(routes_data)[:300]}"
        )
    route = routes[0]

    distance_meters = route.get("distanceMeters", 0)
    distance_km = _round2(Decimal(str(distance_meters)) / Decimal("1000"))

    # Extract toll cost and toll presence indicator.
    # has_tolls=True when tollInfo exists in response, even if estimatedPrice
    # is empty (Google Routes API does not cover Spanish toll pricing).
    # Extraer coste de peajes e indicador de presencia de peajes.
    # has_tolls=True cuando tollInfo existe en la respuesta, aunque estimatedPrice
    # este vacio (la Routes API no cubre tarifas de peajes en Espana).
    toll_cost = Decimal("0")
    has_tolls = False
    try:
        toll_info = route["travelAdvisory"]["tollInfo"]
        # tollInfo present in response means the route has tolls.
        # tollInfo presente en la respuesta indica que la ruta tiene peajes.
        has_tolls = True
        estimated_prices = toll_info.get("estimatedPrice", [])
        if estimated_prices:
            units = estimated_prices[0].get("units", "0")
            nanos = estimated_prices[0].get("nanos", 0)
            toll_cost = Decimal(str(units)) + _round2(
                Decimal(str(nanos)) / Decimal("1000000000")
            )
    except (KeyError, TypeError, IndexError):
        # No toll info in response — route has no tolls.
        # Sin informacion de peajes en la respuesta — la ruta no tiene peajes.
        pass

    return {
        "distance_km": _round2(distance_km * 2),
        "toll_cost":   _round2(toll_cost),
        "has_tolls":   has_tolls,
        "mode":        "API",
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
    departure_line = active_lines_map.get(TariffLine.CONCEPT_DEPARTURE)
    service_local_line = active_lines_map.get(TariffLine.CONCEPT_SERVICE_LOCAL)
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
            TariffLine.CONCEPT_SERVICE_LOCAL,
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
                TariffLine.CONCEPT_DEPARTURE,
                "Salida / Enganche",
                num_departures,
                Decimal(str(departure_line.price)),
            )

        # ------------------------------------------------------------------
        # 2. KILOMETRES
        # Select KM_NORMAL or KM_LONG based on km_total vs km_threshold.
        # Seleccionar KM_NORMAL o KM_LONG en funcion de km_total vs km_threshold.
        # ------------------------------------------------------------------
        km_long_line = active_lines_map.get(TariffLine.CONCEPT_KM_LONG)
        km_normal_line = active_lines_map.get(TariffLine.CONCEPT_KM_NORMAL)

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
    # 3. UNLOCK
    # Only if has_unlock and the tariff includes an UNLOCK line.
    # Solo si has_unlock y la tarifa incluye una linea UNLOCK.
    # ------------------------------------------------------------------
    if budget.has_unlock:
        unlock_line = active_lines_map.get(TariffLine.CONCEPT_UNLOCK)
        if unlock_line:
            base_total += _add_line(
                TariffLine.CONCEPT_UNLOCK,
                "Desbloqueo / Enganche eslingas",
                Decimal("1"),
                Decimal(str(unlock_line.price)),
            )

    # ------------------------------------------------------------------
    # 4. OPTIONAL CONCEPTS
    # Each is included only if the operator provided a value > 0
    # and the tariff has a matching line.
    # Cada uno se incluye solo si el operario proporciono un valor > 0
    # y la tarifa tiene una linea correspondiente.
    # ------------------------------------------------------------------
    optional_map = [
        (budget.rescue_hours,   TariffLine.CONCEPT_RESCUE_HOUR,    "Hora de rescate"),
        (budget.wait_hours,     TariffLine.CONCEPT_WAIT_HOUR,      "Hora de espera"),
        (budget.worker_hours,   TariffLine.CONCEPT_WORKER_HOUR,    "Hora de mano de obra"),
        (budget.assistant_hours, TariffLine.CONCEPT_ASSISTANT_HOUR, "Hora de ayudante"),
        (budget.custody_days,   TariffLine.CONCEPT_CUSTODY_DAY,    "Custodia por dia"),
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
    # 5. SURCHARGES — NYF and/or loaded vehicle
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

    nyf_line = lines_map.get(TariffLine.CONCEPT_NYF_PERCENT)
    loaded_line = lines_map.get(TariffLine.CONCEPT_LOADED_PERCENT)

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
                TariffLine.CONCEPT_NYF_PERCENT,
                f"Recargo nocturno/festivo ({nyf_percent}%)",
                base_total,
                nyf_percent / Decimal("100"),
                is_surcharge=True,
            )
        if loaded_percent > 0:
            surcharge_amount = _round2(base_total * loaded_percent / Decimal("100"))
            surcharge_total += surcharge_amount
            _add_line(
                TariffLine.CONCEPT_LOADED_PERCENT,
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
                code = TariffLine.CONCEPT_NYF_PERCENT
                label = f"Recargo nocturno/festivo ({effective_percent}%)"
            else:
                code = TariffLine.CONCEPT_LOADED_PERCENT
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
    # 6. MANAGEMENT FEE
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
    # 7. TOTAL (base, before IVA)
    # ------------------------------------------------------------------
    budget.total_amount = _round2(subtotal_after_surcharges + management_fee_total)

    # ------------------------------------------------------------------
    # 8. IVA (optional — controlled by budget.apply_iva)
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
