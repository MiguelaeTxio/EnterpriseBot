# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/work_order_readings.py
"""
H30 (S137). Meter readings from the digital work orders.

---

H30 (S137). Lecturas de km, horas y horas de grúa sacadas de los partes
digitales. Miguel Ángel, al ver que todos los camiones y grúas apuntan
km en el surtidor y que las revisiones por horas no tendrían nunca
lecturas: que las horas que el mecánico ya apunta en el parte (motor y
grúa, validadas por R6/R7/R8) se guarden también como lecturas del
centro de gasto, sin trabajo de nadie.

Una lectura por bloque de parte (`MachineMeterReading.work_order_line`),
con la fecha del parte. Se rehace al guardar el bloque o el parte
(señales de `fleet/signals.py`) y se borra con el bloque. Un bloque sin
máquina, sin fecha o sin ninguna lectura mayor que 0 no da lectura (los
ceros son la línea base de la primera reparación).
"""
from fleet.models import MachineMeterReading

_FIELDS = (
    ("odometer_reading", "km"),
    ("engine_hours_reading", "hours"),
    ("crane_hours_reading", "crane_hours"),
)


def line_values(line):
    """
    {reading field: int} of the readings of a work order block.

    ---

    Lecturas del bloque mayores que 0, como enteros (redondeadas), con
    el nombre del campo de `MachineMeterReading`.
    """
    values = {}
    for line_field, reading_field in _FIELDS:
        raw = getattr(line, line_field)
        if raw is not None and raw > 0:
            values[reading_field] = int(round(raw))
    return values


def sync_line_reading(line):
    """
    Create, update or delete the reading of one work order block.

    Returns "created", "updated", "deleted" or "".

    ---

    Crea, actualiza o borra la lectura de un bloque de parte. Devuelve
    lo que hizo ("" si no había nada que cambiar).
    """
    existing = MachineMeterReading.objects.filter(
        work_order_line=line).first()
    values = line_values(line)
    day = line.entry.work_date
    if line.machine_asset_id is None or day is None or not values:
        if existing is None:
            return ""
        existing.delete()
        return "deleted"
    wanted = {
        "machine_id": line.machine_asset_id,
        "reading_date": day,
        "km": values.get("km"),
        "hours": values.get("hours"),
        "crane_hours": values.get("crane_hours"),
    }
    if existing is None:
        MachineMeterReading.objects.create(
            work_order_line=line,
            source=MachineMeterReading.SOURCE_WORK_ORDER,
            **wanted,
        )
        return "created"
    if all(getattr(existing, name) == value
           for name, value in wanted.items()):
        return ""
    for name, value in wanted.items():
        setattr(existing, name, value)
    existing.save()
    return "updated"
