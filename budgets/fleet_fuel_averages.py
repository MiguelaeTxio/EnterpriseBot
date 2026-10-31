# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/fleet_fuel_averages.py
"""
Real fuel averages of the assistance fleet, from the GasoGes refuels.

---

Medias reales de gasoil de la flota de asistencia, sacadas de los
repostajes de GasoGes (H37, S142). Miguel Ángel: "ya que tenemos las
lecturas de km y repostajes, podemos sacar la media de gasto por km de
los vehículos de la familia asistencia".

Método, por vehículo (solo los que apuntan km en el surtidor; las grúas
y rescates apuntan horas y no dan consumo por km):
- Repostajes con lectura creada (los que pasaron la comprobación de
  GasoGes), por fecha.
- Cada tramo entre dos repostajes seguidos: km de diferencia y litros
  del segundo (lo gastado en ese tramo).
- Un KM igual o por debajo del anterior es una lectura mala: se salta y
  sus litros pasan al tramo siguiente. Se descartan los tramos de más
  de MAX_LEG_KM (KM mal tecleado) y los de un consumo fuera de
  MIN/MAX_L_100KM.
- Consumo = litros / km × 100; gasto = litros × precio / km.
Por clase de vehículo (`AssistanceVehicleCost`), media ponderada por km
de sus vehículos. El precio del gasoil es la media ponderada por litros.
"""
from decimal import ROUND_HALF_UP, Decimal

from budgets.assistance_resources import ASSISTANCE_MACHINE_FAMILY

MAX_LEG_KM = 3000
MIN_L_100KM = Decimal("2")
MAX_L_100KM = Decimal("80")


def _round(value, places):
    """
    Decimal rounded to a number of places.

    ---

    Decimal redondeado a `places` decimales.
    """
    return Decimal(value).quantize(
        Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP,
    )


def _empty():
    """
    Empty accumulator.

    ---

    Acumulador vacío.
    """
    return {
        "km": Decimal("0"), "litres": Decimal("0"), "cost": Decimal("0"),
        "legs": 0, "discarded": 0,
    }


def _finish(acc):
    """
    Averages of an accumulator (None when there are no km).

    ---

    Medias de un acumulador: l/100 km, €/km y €/l (None sin km).
    """
    if not acc["km"]:
        return {**acc, "l_100km": None, "eur_km": None, "eur_l": None}
    return {
        **acc,
        "km": int(acc["km"]),
        "litres": _round(acc["litres"], 1),
        "l_100km": _round(acc["litres"] / acc["km"] * 100, 1),
        "eur_km": _round(acc["cost"] / acc["km"], 3),
        "eur_l": (
            _round(acc["cost"] / acc["litres"], 3) if acc["litres"] else None
        ),
    }


def fleet_averages(company):
    """
    Real fuel averages per vehicle, per cost class and overall.

    ---

    Medias reales por vehículo, por clase de coste y del conjunto, y el
    precio medio del gasoil (ponderado por litros, todos los repostajes
    con precio de la flota de asistencia). Devuelve un diccionario con
    `vehicles` (lista), `classes` (nombre de clase -> medias),
    `fuel_price`, `period` (desde, hasta) y `hours_vehicles` (los que
    apuntan horas).
    """
    from budgets.service_evaluation import _norm, _vehicle_classes
    from fleet.models import GasoGesSupply, GasoGesVehicle

    classes = _vehicle_classes(company)
    supplies = GasoGesSupply.objects.filter(
        vehicle__machine__company=company,
        vehicle__machine__family__iexact=ASSISTANCE_MACHINE_FAMILY,
    ).select_related("vehicle__machine").order_by(
        "vehicle_id", "supplied_at", "id",
    )
    price_litres = Decimal("0")
    price_cost = Decimal("0")
    first = last = None
    per_vehicle = {}
    hours_vehicles = set()
    previous = {}
    pending = {}
    for supply in supplies:
        vehicle = supply.vehicle
        machine = vehicle.machine
        if supply.litres and supply.price:
            price_litres += supply.litres
            price_cost += supply.litres * supply.price
        if vehicle.unit != GasoGesVehicle.UNIT_KM:
            hours_vehicles.add(machine.code)
            continue
        if supply.status != GasoGesSupply.STATUS_READING:
            continue
        if supply.meter_value is None or not supply.litres:
            continue
        first = first or supply.supplied_at
        last = supply.supplied_at
        acc = per_vehicle.setdefault(machine.pk, {
            "code": machine.code,
            "type_name": machine.type_name,
            **_empty(),
        })
        before = previous.get(machine.pk)
        if before is None:
            previous[machine.pk] = supply
            continue
        leg_km = Decimal(supply.meter_value - before.meter_value)
        if leg_km <= 0:
            # KM at or below the previous one: this reading is the wrong
            # one; its litres go into the next good leg.
            # KM igual o por debajo del anterior: la lectura mala es
            # esta; sus litros pasan al siguiente tramo bueno.
            acc["discarded"] += 1
            pending[machine.pk] = pending.get(machine.pk, []) + [supply]
            continue
        previous[machine.pk] = supply
        legs_supplies = pending.pop(machine.pk, []) + [supply]
        litres = sum(item.litres for item in legs_supplies)
        cost = sum(item.litres * (item.price or 0) for item in legs_supplies)
        rate = litres / leg_km * 100
        if leg_km > MAX_LEG_KM or rate < MIN_L_100KM or rate > MAX_L_100KM:
            acc["discarded"] += 1
            continue
        acc["km"] += leg_km
        acc["litres"] += litres
        acc["cost"] += cost
        acc["legs"] += 1
    vehicles = []
    by_class = {}
    for acc in per_vehicle.values():
        vehicle_class = classes.get(_norm(acc["type_name"]))
        class_name = vehicle_class.name if vehicle_class else ""
        vehicles.append({**_finish(acc), "class_name": class_name})
        if vehicle_class and acc["km"]:
            total = by_class.setdefault(class_name, _empty())
            for key in ("km", "litres", "cost", "legs", "discarded"):
                total[key] += acc[key]
            total.setdefault("codes", []).append(acc["code"])
    vehicles.sort(key=lambda v: (v["class_name"] or "~", v["code"]))
    return {
        "vehicles": vehicles,
        "classes": {
            name: {**_finish(total), "codes": sorted(total["codes"])}
            for name, total in by_class.items()
        },
        "fuel_price": (
            _round(price_cost / price_litres, 3) if price_litres else None
        ),
        "period": (first, last),
        "hours_vehicles": sorted(hours_vehicles),
    }
