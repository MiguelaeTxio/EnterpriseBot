# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/gasoges_hours.py
"""
H30 (S141). Supplies of hours vehicles where no hours were typed.

---

H30 (S141). Repostajes de vehículos que van por horas en los que no se
anotaron las horas. Miguel Ángel: "no hay forma de saber qué vehículos
deberían estar anotándose horas y se están anotando kilómetros. Y qué
repostadores están haciendo caso omiso de la orden de anotar horas".

En un vehículo que va por horas (unidad HORAS y contador no averiado),
cada repostaje que no se convirtió en lectura queda en uno de estos
grupos (GasoGesSupply.hours_issue):
- Sin anotar: KM vacío, 0 o un número demasiado pequeño para ser una
  lectura.
- Km en vez de horas: sube más de 24 al día desde el repostaje anterior
  con un dato válido, cosa que un horómetro no puede hacer (S135:
  MAX_HOURS_PER_DAY). En la práctica son los km del cuentakilómetros
  (B32: 305.000-314.000, unos 100 al día).
Los que se convirtieron en lectura, los de vehículos de km o sin unidad
y los de contador averiado no llevan marca.

Se recalcula entero cada vez que se rehacen las lecturas
(gasoges_sync.build_readings), así que un cambio de unidad o una
respuesta del chófer lo corrige solo.
"""
from fleet.gasoges_rules import MAX_HOURS_PER_DAY, MIN_CREDIBLE_VALUE
from fleet.models import GasoGesSupply, GasoGesVehicle

SECONDS_PER_DAY = 86400


def classify_points(points):
    """
    hours_issue for each (supplied_at, value, status) of one vehicle.

    ---

    La marca de cada repostaje de un vehículo de horas, en el orden de
    `points` (ordenados por fecha): (supplied_at, valor, estado).
    """
    issues = []
    previous = None
    for when, value, status in points:
        issue = GasoGesSupply.HOURS_ISSUE_NONE
        credible = value is not None and value >= MIN_CREDIBLE_VALUE
        if status == GasoGesSupply.STATUS_BROKEN_METER:
            pass
        elif not credible:
            if status != GasoGesSupply.STATUS_READING:
                issue = GasoGesSupply.HOURS_ISSUE_EMPTY
        elif (status != GasoGesSupply.STATUS_READING
              and previous is not None and value > previous[1]):
            days = max((when - previous[0]).total_seconds()
                       / SECONDS_PER_DAY, 1)
            if (value - previous[1]) / days > MAX_HOURS_PER_DAY:
                issue = GasoGesSupply.HOURS_ISSUE_KM
        if credible and status != GasoGesSupply.STATUS_BROKEN_METER:
            previous = (when, value)
        issues.append(issue)
    return issues


def classify_hours_issues():
    """
    Recompute hours_issue of every supply; returns how many changed.

    ---

    Recalcula la marca de todos los repostajes y guarda solo las que
    cambian. Devuelve cuántas cambiaron.
    """
    hours_vehicles = set(GasoGesVehicle.objects.filter(
        unit=GasoGesVehicle.UNIT_HOURS).values_list("pk", flat=True))
    changed = []
    by_vehicle = {}
    for row in GasoGesSupply.objects.order_by(
            "vehicle_id", "supplied_at", "id").values_list(
            "pk", "vehicle_id", "supplied_at", "meter_value", "status",
            "hours_issue"):
        by_vehicle.setdefault(row[1], []).append(row)
    for vehicle_id, rows in by_vehicle.items():
        if vehicle_id in hours_vehicles:
            issues = classify_points([(r[2], r[3], r[4]) for r in rows])
        else:
            issues = [GasoGesSupply.HOURS_ISSUE_NONE] * len(rows)
        for row, issue in zip(rows, issues):
            if row[5] != issue:
                changed.append(GasoGesSupply(pk=row[0], hours_issue=issue))
    GasoGesSupply.objects.bulk_update(changed, ["hours_issue"],
                                      batch_size=500)
    return len(changed)
