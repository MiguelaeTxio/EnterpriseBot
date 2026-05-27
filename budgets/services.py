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

from decimal import Decimal, ROUND_HALF_UP

from budgets.models import (
    Budget,
    BudgetLine,
    InsurerTariff,
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

    lines_map = _get_tariff_lines(tariff, vehicle_type)
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
    # 1. DEPARTURE(S)
    # If overnight: 2 departures (one per phase). Otherwise: 1.
    # Si pernocta: 2 salidas (una por fase). Si no: 1.
    # ------------------------------------------------------------------
    departure_line = lines_map.get(TariffLine.CONCEPT_DEPARTURE)
    service_local_line = lines_map.get(TariffLine.CONCEPT_SERVICE_LOCAL)

    if departure_line:
        num_departures = Decimal("2") if budget.is_overnight else Decimal("1")
        base_total += _add_line(
            TariffLine.CONCEPT_DEPARTURE,
            "Salida / Enganche",
            num_departures,
            Decimal(str(departure_line.price)),
        )
    elif service_local_line:
        # Some tariffs use SERVICE_LOCAL (forfait, no km) instead of DEPARTURE.
        # Algunas tarifas usan SERVICE_LOCAL (forfait sin km) en lugar de DEPARTURE.
        num_departures = Decimal("2") if budget.is_overnight else Decimal("1")
        base_total += _add_line(
            TariffLine.CONCEPT_SERVICE_LOCAL,
            "Servicio local / Urbano",
            num_departures,
            Decimal(str(service_local_line.price)),
        )

    # ------------------------------------------------------------------
    # 2. KILOMETRES
    # Select KM_NORMAL or KM_LONG based on km_total vs km_threshold.
    # Seleccionar KM_NORMAL o KM_LONG en funcion de km_total vs km_threshold.
    # ------------------------------------------------------------------
    km_total = Decimal(str(budget.km_total))

    km_long_line = lines_map.get(TariffLine.CONCEPT_KM_LONG)
    km_normal_line = lines_map.get(TariffLine.CONCEPT_KM_NORMAL)

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
        unlock_line = lines_map.get(TariffLine.CONCEPT_UNLOCK)
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
        opt_line = lines_map.get(concept_code)
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

    if budget.is_night_or_holiday and nyf_line:
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
