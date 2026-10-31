# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/fleet_fuel_averages.py
"""
Real fuel averages of the assistance fleet, from the GasoGes refuels.

---

Medias reales de gasoil de la flota de asistencia, sacadas de los
repostajes de GasoGes (H37, S142). Miguel Ángel: "ya que tenemos las
lecturas de km y repostajes, podemos sacar la media de gasto por km de
los vehículos de la familia asistencia".

Método, por vehículo: los que apuntan km en el surtidor dan l/100 km y
€/km; los que apuntan horas (grúas móviles y rescates, S142) dan l/h y
€/h, con el mismo método en horas (tramos de hasta MAX_LEG_HOURS, de
MIN_L_HOUR a MAX_L_HOUR):
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
# S142: the cranes meter hours: same method, in hours.
# Las grúas apuntan horas: el mismo método, en horas.
MAX_LEG_HOURS = 300
MIN_L_HOUR = Decimal("1")
MAX_L_HOUR = Decimal("60")


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
        "km": Decimal("0"), "hours": Decimal("0"), "litres": Decimal("0"),
        "cost": Decimal("0"), "legs": 0, "discarded": 0,
    }


def _finish(acc):
    """
    Averages of an accumulator (None when there is nothing measured).

    ---

    Medias de un acumulador: por km (l/100 km y €/km) si se midió en
    km, por hora (l/h y €/h) si se midió en horas, y €/l.
    """
    result = {
        **acc,
        "km": int(acc["km"]),
        "hours": int(acc["hours"]),
        "litres": _round(acc["litres"], 1),
        "l_100km": None, "eur_km": None, "l_hour": None, "eur_hour": None,
        "eur_l": (
            _round(acc["cost"] / acc["litres"], 3) if acc["litres"] else None
        ),
    }
    if acc["km"]:
        result["l_100km"] = _round(acc["litres"] / acc["km"] * 100, 1)
        result["eur_km"] = _round(acc["cost"] / acc["km"], 3)
    if acc["hours"]:
        result["l_hour"] = _round(acc["litres"] / acc["hours"], 1)
        result["eur_hour"] = _round(acc["cost"] / acc["hours"], 2)
    return result


def fleet_averages(company):
    """
    Real fuel averages per vehicle, per cost class and overall.

    ---

    Medias reales por vehículo, por clase de coste y del conjunto, y el
    precio medio del gasoil (ponderado por litros, todos los repostajes
    con precio de la flota de asistencia). Devuelve un diccionario con
    `vehicles` (lista), `classes` (nombre de clase -> medias),
    `fuel_price` y `period` (desde, hasta). Los que apuntan km dan
    l/100 km; los que apuntan horas (grúas), l/h.
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
    previous = {}
    pending = {}
    for supply in supplies:
        vehicle = supply.vehicle
        machine = vehicle.machine
        if supply.litres and supply.price:
            price_litres += supply.litres
            price_cost += supply.litres * supply.price
        if vehicle.unit not in (
            GasoGesVehicle.UNIT_KM, GasoGesVehicle.UNIT_HOURS,
        ):
            continue
        in_hours = vehicle.unit == GasoGesVehicle.UNIT_HOURS
        if supply.status != GasoGesSupply.STATUS_READING:
            continue
        if supply.meter_value is None or not supply.litres:
            continue
        first = first or supply.supplied_at
        last = supply.supplied_at
        acc = per_vehicle.setdefault(machine.pk, {
            "code": machine.code,
            "type_name": machine.type_name,
            "unit": "h" if in_hours else "km",
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
        if in_hours:
            rate = litres / leg_km
            wrong = (
                leg_km > MAX_LEG_HOURS or rate < MIN_L_HOUR
                or rate > MAX_L_HOUR
            )
        else:
            rate = litres / leg_km * 100
            wrong = (
                leg_km > MAX_LEG_KM or rate < MIN_L_100KM
                or rate > MAX_L_100KM
            )
        if wrong:
            acc["discarded"] += 1
            continue
        acc["hours" if in_hours else "km"] += leg_km
        acc["litres"] += litres
        acc["cost"] += cost
        acc["legs"] += 1
    vehicles = []
    by_class = {}
    for acc in per_vehicle.values():
        vehicle_class = classes.get(_norm(acc["type_name"]))
        class_name = vehicle_class.name if vehicle_class else ""
        vehicles.append({**_finish(acc), "class_name": class_name})
        if vehicle_class and (acc["km"] or acc["hours"]):
            # Per km and per hour apart: a class may mix both.
            # Por km y por hora aparte: una clase puede mezclar los dos.
            total = by_class.setdefault(class_name, {
                "km": _empty(), "h": _empty(), "codes": [],
            })
            part = total[acc["unit"]]
            for key in ("km", "hours", "litres", "cost", "legs",
                        "discarded"):
                part[key] += acc[key]
            total["codes"].append(acc["code"])
    vehicles.sort(key=lambda v: (v["class_name"] or "~", v["code"]))
    return {
        "vehicles": vehicles,
        "classes": {
            name: {
                "km": _finish(total["km"]) if total["km"]["km"] else None,
                "h": _finish(total["h"]) if total["h"]["hours"] else None,
                "codes": sorted(total["codes"]),
            }
            for name, total in by_class.items()
        },
        "fuel_price": (
            _round(price_cost / price_litres, 3) if price_litres else None
        ),
        "period": (first, last),
    }


def apply_real_averages(company):
    """
    Copy the real averages into the cost settings of a company.

    ---

    Copia las medias reales de los repostajes en las medias de coste:
    consumo por km de cada clase con vehículos que apuntan km, consumo
    por hora de cada clase con vehículos que apuntan horas, y precio
    medio del gasoil. Las clases sin datos se quedan como estaban. No
    recalcula los servicios (lo hace quien llama). Devuelve (real,
    lista de lo aplicado en texto).
    """
    from budgets.models import AssistanceCostSettings

    real = fleet_averages(company)
    settings = AssistanceCostSettings.for_company(company)
    applied = []
    if real["fuel_price"] is not None:
        settings.fuel_price_per_liter = real["fuel_price"]
        settings.save(update_fields=["fuel_price_per_liter", "updated_at"])
        applied.append("gasoil %s €/l" % real["fuel_price"])
    for vehicle in company.assistance_vehicle_costs.all():
        averages = real["classes"].get(vehicle.name) or {}
        fields = []
        if averages.get("km"):
            vehicle.fuel_liters_per_100km = averages["km"]["l_100km"]
            fields.append("fuel_liters_per_100km")
            applied.append("%s %s l/100 km" % (
                vehicle.name, averages["km"]["l_100km"],
            ))
        if averages.get("h"):
            # Hour-metered: from now on its fuel goes by hours.
            # Por horas: desde ahora su gasoil va por horas.
            vehicle.fuel_liters_per_hour = averages["h"]["l_hour"]
            fields.append("fuel_liters_per_hour")
            applied.append("%s %s l/h" % (
                vehicle.name, averages["h"]["l_hour"],
            ))
        if fields:
            vehicle.save(update_fields=fields)
    return real, applied
