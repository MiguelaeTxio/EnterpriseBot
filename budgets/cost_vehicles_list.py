# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/cost_vehicles_list.py
"""
List of the service vehicles with their real fuel averages.

---

H37 (S143). Listado de la pestaña "Costes de vehículos de servicio" de
Medias de coste: cada vehículo de la familia asistencia con sus medias
reales de los repostajes de GasoGes (`fleet_fuel_averages`), con el
formato único de listado de la directriz 4.24: búsqueda, filtro por
clase, orden múltiple con prioridad (resuelto aquí, plantillas tontas)
y "mostrar solo la selección actual".
"""
from budgets.assistance_resources import ASSISTANCE_MACHINE_FAMILY
from budgets.fleet_fuel_averages import (
    MIN_VEHICLE_LEGS,
    class_fuel_maximums,
    fleet_averages,
)
from budgets.service_evaluation import _norm, _vehicle_class_map

FILTER_KEYS = ("search", "class_name", "sort")
MAX_SORT_KEYS = 4
# Sort key -> value of a row (None goes always at the end).
# Clave de orden -> valor de una fila (None siempre al final).
SORTABLE = {
    "code": lambda row: row["code"] or None,
    "type": lambda row: _norm(row["type_name"]) or None,
    "class": lambda row: _norm(row["class_name"]) or None,
    "measure": lambda row: (
        row["hours"] if row["unit"] == "h" else row["km"]
    ) or None,
    "litres": lambda row: row["litres"],
    "rate": lambda row: (
        row["l_hour"] if row["unit"] == "h" else row["l_100km"]
    ),
    "spend": lambda row: (
        row["eur_hour"] if row["unit"] == "h" else row["eur_km"]
    ),
    "legs": lambda row: row["legs"],
    "discarded": lambda row: row["discarded"],
}
# Columns that start from the highest on the first click.
# Columnas que empiezan por el mayor en el primer clic.
DESC_FIRST = (
    "measure", "litres", "rate", "spend", "legs", "discarded",
)


def parse_sort(raw):
    """
    [(key, descending), ...] of a sort value, at most MAX_SORT_KEYS.

    ---

    [(clave, descendente), ...] de un valor de orden, como mucho
    MAX_SORT_KEYS (directriz 4.24).
    """
    keys = []
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in SORTABLE and key not in [k for k, _d in keys]:
            keys.append((key, token.startswith("-")))
    return keys[:MAX_SORT_KEYS]


def sort_controls(raw):
    """
    Sort value of each header click, arrows and priorities.

    ---

    Para cada columna ordenable, el valor de "sort" de un clic en su
    cabecera, su flecha y su prioridad (mismo criterio que la pestaña
    Servicios, `service_evaluation.sort_controls`).
    """
    keys = parse_sort(raw)
    active = [key for key, _desc in keys]
    cols = {}
    for key in SORTABLE:
        if key in active:
            idx = active.index(key)
            desc = keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(keys) > 1 else ""
            new = [(key, (not desc) if idx == 0 else desc)] + [
                (k, d) for k, d in keys if k != key
            ]
        else:
            arrow, priority = "", ""
            new = [(key, key in DESC_FIRST)] + keys
        cols[key] = {
            "next": ",".join(
                ("-" if d else "") + k for k, d in new[:MAX_SORT_KEYS]
            ),
            "arrow": arrow,
            "priority": priority,
        }
    return {
        "sort_cols": cols,
        "sort_active": bool(keys),
        "current_sort": ",".join(("-" if d else "") + k for k, d in keys),
    }


def _sort_rows(rows, keys):
    """
    Stable sort by several keys; empty values always at the end.

    ---

    Orden estable por varias claves, la primera la más importante; los
    vacíos siempre al final, sea cual sea el sentido.
    """
    for key, desc in reversed(keys):
        getter = SORTABLE[key]
        filled = [row for row in rows if getter(row) is not None]
        empty = [row for row in rows if getter(row) is None]
        filled.sort(key=getter, reverse=desc)
        rows = filled + empty
    return rows


def build_list(company, params, only_keys=None):
    """
    Rows of the list, the classes for the filter and the overall data.

    ---

    Filas del listado ya filtradas y ordenadas (sin orden elegido, por
    clase y código, como las devuelve `fleet_averages`), las clases que
    aparecen (para el desplegable) y el periodo y el precio medio del
    gasoil. `only_keys`: solo esos códigos ("mostrar solo la selección
    actual").
    """
    from fleet.models import MachineAsset

    real = fleet_averages(company)
    maximums = class_fuel_maximums(company, real)
    class_by_name = {
        vehicle_class.name: vehicle_class
        for vehicle_class in _vehicle_class_map(company).values()
    }
    vehicles = list(real["vehicles"])
    # S143: the assistance vehicles without refuels also count (with
    # the consumption of their class).
    # Los vehículos de asistencia sin repostajes también cuentan (con el
    # consumo de su clase).
    measured = {vehicle["machine_pk"] for vehicle in vehicles}
    by_type = _vehicle_class_map(company)
    for machine in MachineAsset.objects.filter(
        company=company, family__iexact=ASSISTANCE_MACHINE_FAMILY,
    ).exclude(pk__in=measured).only("pk", "code", "type_name"):
        vehicle_class = by_type.get(_norm(machine.type_name))
        vehicles.append({
            "machine_pk": machine.pk, "code": machine.code,
            "type_name": machine.type_name, "unit": "",
            "class_name": vehicle_class.name if vehicle_class else "",
            "km": 0, "hours": 0, "litres": None, "legs": 0,
            "discarded": 0, "l_100km": None, "eur_km": None,
            "l_hour": None, "eur_hour": None,
        })
    rows = []
    for vehicle in vehicles:
        row = dict(vehicle)
        row["few_legs"] = vehicle["legs"] < MIN_VEHICLE_LEGS
        vehicle_class = class_by_name.get(vehicle["class_name"])
        used = maximums.get(vehicle_class.pk) if vehicle_class else None
        row["is_max"] = bool(used) and vehicle["code"] in (
            used["l_100km"][1],
            used["l_hour"][1] if used["l_hour"] else "",
        )
        row["key"] = vehicle["code"]
        row["label"] = "%s · %s" % (
            vehicle["code"], (vehicle["type_name"] or "").capitalize(),
        )
        row["phrase"] = _norm(" ".join((
            vehicle["code"] or "", vehicle["type_name"] or "",
            vehicle["class_name"] or "",
        )))
        rows.append(row)
    class_names = sorted({
        row["class_name"] for row in rows if row["class_name"]
    })
    search = _norm(params.get("search", "")).strip()
    if search:
        words = search.split()
        rows = [
            row for row in rows
            if all(word in row["phrase"] for word in words)
        ]
    class_name = params.get("class_name", "")
    if class_name:
        rows = [row for row in rows if row["class_name"] == class_name]
    if only_keys is not None:
        rows = [row for row in rows if row["key"] in only_keys]
    keys = parse_sort(params.get("sort", ""))
    if keys:
        rows = _sort_rows(rows, keys)
    else:
        rows.sort(key=lambda row: (row["class_name"] or "~", row["code"]))
    return {
        "min_legs": MIN_VEHICLE_LEGS,
        "rows": rows,
        "class_names": class_names,
        "fuel_price": real["fuel_price"],
        "period": real["period"],
        "has_real": bool(real["vehicles"] or real["fuel_price"]),
    }
