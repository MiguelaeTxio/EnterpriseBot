# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_invoice.py
"""
Invoice simulation of a finished work order (H37, S140).

It prices each closed albarán with the active tariff of the insurer,
using the same engine as the budgets, without saving anything.

---

Simulación de factura de una orden terminada (H37, S140, Miguel Ángel:
"podíamos incluir algún botón como de simulación de factura, para ver
cómo quedaría la factura con los precios de cada tarifa").

Valora cada albarán cerrado con la tarifa activa de la aseguradora,
con el mismo motor que los presupuestos, sin guardar nada.
"""

from decimal import Decimal

from django.utils.timezone import localtime

from budgets.assistance_albaranes import DONE_STATUSES
from budgets.models import Budget
from budgets.services import calculate_budget


def _budget_for(unit):
    """
    Unsaved budget with the data the driver recorded in the albarán.

    ---

    Presupuesto sin guardar con los datos que anotó el chófer en el
    albarán.
    """
    work_order = unit.work_order
    started = localtime(unit.started_at) if unit.started_at else None
    return Budget(
        company=work_order.company,
        insurer=work_order.insurer,
        vehicle_type=work_order.vehicle_type,
        base=unit.departure_base or work_order.base,
        service_date=started.date() if started else work_order.service_date,
        service_time=started.time() if started else None,
        is_overnight=unit.is_overnight,
        km_phase1=unit.phase1_km or Decimal("0"),
        km_phase2=(unit.phase2_km or Decimal("0")) if unit.is_overnight else Decimal("0"),
        is_night=bool(unit.is_night),
        wait_hours=unit.wait_hours,
        rescue_hours=unit.rescue_hours,
        worker_hours=unit.work_hours,
        route_calculation_mode=Budget.ROUTE_MODE_MANUAL,
        # S140: an invoice carries IVA (Miguel Ángel: "con el IVA").
        # Una factura lleva IVA.
        apply_iva=True,
    )


def simulate_unit(unit):
    """
    Lines and totals of one albarán, or the reason it cannot be priced.

    ---

    Líneas y totales de un albarán, o el motivo por el que no se puede
    valorar.
    """
    work_order = unit.work_order
    result = {"unit": unit, "lines": [], "notes": [], "error": None,
              "total": None, "total_with_iva": None, "budget": None}
    if work_order.insurer_id is None:
        result["error"] = "La orden no tiene aseguradora."
        return result
    if work_order.vehicle_type_id is None:
        result["error"] = "La orden no tiene tipo de vehículo de tarifa."
        return result
    if unit.phase1_km is None:
        result["notes"].append("El albarán no tiene km: no se cobran km.")
    budget = _budget_for(unit)
    try:
        lines = calculate_budget(budget)
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    result.update(
        lines=lines,
        budget=budget,
        total=budget.total_amount,
        total_with_iva=budget.total_amount_with_iva,
    )
    return result


def simulate_order(work_order):
    """
    Simulation of every closed albarán of the order and the order total.

    ---

    Simulación de cada albarán cerrado de la orden y el total de la
    orden.
    """
    units = (
        work_order.units.filter(status__in=DONE_STATUSES)
        .select_related("work_order__insurer", "work_order__vehicle_type",
                        "departure_base", "operator__user")
        .order_by("unit_number")
    )
    results = [simulate_unit(unit) for unit in units]
    priced = [row for row in results if row["error"] is None]
    total = sum((row["total"] for row in priced), Decimal("0.00"))
    with_iva = None
    if priced and all(row["total_with_iva"] is not None for row in priced):
        with_iva = sum((row["total_with_iva"] for row in priced), Decimal("0.00"))
    return {"results": results, "total": total, "total_with_iva": with_iva,
            "complete": len(priced) == len(results)}
