# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/work_order_service.py
"""
H30 (S137). Service (oil and filter change) entered from a work order
block: the "Revisión" checkbox of each task.

---

H30 (S137). Revisión anotada desde el parte. Miguel Ángel: cada tarea
lleva una casilla "Revisión"; marcada, pide qué filtros se cambiaron,
cuánto aceite y cuál, y la próxima revisión en horas (o en km si la
máquina va por km). Al guardar, la tarea pasa a tipo REVISION y se crea
(o se actualiza) su `MachineServiceRecord`, con la fecha del parte y
las horas y km que el mecánico puso en la tarea. Si se desmarca, se
borra esa revisión y la tarea se vuelve a clasificar.

Los filtros que vienen del albarán se marcan como siempre en los
repuestos de la tarea; quedan enlazados a la tarea y se ven con ella.
"""
from decimal import Decimal
from decimal import InvalidOperation

SERVICE_TYPE = "REVISION"

# Filtros que se cambian normalmente (código, etiqueta).
FILTERS = (
    ("aceite", "Aceite"),
    ("aire", "Aire"),
    ("gasoil", "Gasoil"),
    ("hidraulico", "Hidráulico"),
    ("habitaculo", "Habitáculo"),
    ("secador", "Secador de aire"),
)
FILTER_LABELS = dict(FILTERS)


def _int_or_none(raw):
    """
    Positive integer from a form value, or None.

    ---

    Entero positivo de un campo del formulario, o None.
    """
    try:
        value = int(Decimal((raw or "").strip().replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None
    return value if value > 0 else None


def parse_service_post(post, prefix):
    """
    Service data of one block from the POST, or None if not ticked.

    ---

    Datos de revisión de una tarea (prefijo `entrada_{i}_`), o None si
    la casilla "Revisión" no está marcada.
    """
    if post.get("%sis_service" % prefix, "") != "1":
        return None
    filters = [code for code, _label in FILTERS
               if post.get("%sservice_filter_%s" % (prefix, code)) == "1"]
    oil_type = post.get("%sservice_oil_type" % prefix, "").strip()
    try:
        litres = Decimal(
            post.get("%sservice_oil_litres" % prefix, "").strip()
            .replace(",", "."))
        litres = litres if litres > 0 else None
    except InvalidOperation:
        litres = None
    from fleet.models import MachineServiceRecord

    return {
        "filters": filters,
        "oil_type": (oil_type if oil_type in dict(
            MachineServiceRecord.OIL_CHOICES) else ""),
        "oil_litres": litres,
        "next_hours": _int_or_none(
            post.get("%sservice_next_hours" % prefix)),
        "next_km": _int_or_none(post.get("%sservice_next_km" % prefix)),
    }


def form_data(line):
    """
    Service data of a saved block, for the form, or None.

    ---

    Datos de revisión de una tarea ya guardada, para volver a pintar el
    formulario, o None si no tiene revisión anotada.
    """
    record = getattr(line, "service_record", None) if line.pk else None
    if record is None:
        return None
    return {
        "filters": [code for code in record.filters_changed.split(",")
                    if code],
        "oil_type": record.oil_type,
        "oil_litres": record.oil_litres,
        "next_hours": record.next_service_hours,
        "next_km": record.next_service_km,
    }


def _whole(value):
    """
    Integer part of a meter reading, or None.

    ---

    Parte entera de una lectura de contador, o None.
    """
    return int(value) if value is not None and value > 0 else None


def _set_type(line, model, **fields):
    """
    Store the task type in the database and on the loaded object.

    ---

    Guarda el tipo de tarea en BD y también en el objeto ya cargado,
    para que un `save()` posterior de la vista no lo pise.
    """
    model.objects.filter(pk=line.pk).update(**fields)
    for field, value in fields.items():
        setattr(line, field, value)


def sync_line_service(line, data, company_user):
    """
    Create, update or delete the service record of a block.

    Returns "created", "updated", "deleted" or "".

    ---

    Crea, actualiza o borra la revisión de una tarea según la casilla.
    Marcada: la tarea pasa a REVISION y su `MachineServiceRecord` lleva
    la fecha del parte, las lecturas de la tarea, los filtros, el aceite
    y la próxima revisión. Desmarcada con una revisión ya guardada: se
    borra y la tarea queda sin clasificar, para que Gemini la clasifique
    de nuevo. Sin máquina, no se anota nada.
    """
    from fleet.models import MachineServiceRecord
    from work_order_processor.models import WorkOrderEntryLine

    record = MachineServiceRecord.objects.filter(
        work_order_line=line).first()
    if data is None or line.machine_asset_id is None:
        if record is None:
            return ""
        record.delete()
        if line.tipo_tarea == SERVICE_TYPE:
            _set_type(line, WorkOrderEntryLine, tipo_tarea="",
                      task_category_free="")
        return "deleted"
    filters = ", ".join(FILTER_LABELS[code] for code in data["filters"])
    _set_type(
        line, WorkOrderEntryLine,
        tipo_tarea=SERVICE_TYPE,
        task_category_free=(
            "cambio de aceite y filtros (%s)" % filters if filters
            else "cambio de aceite"),
        fault_category="",
        fault_subcategory="",
    )
    values = {
        "machine": line.machine_asset,
        "service_date": line.entry.work_date,
        "hours": _whole(line.engine_hours_reading),
        "km": _whole(line.odometer_reading),
        "crane_hours": _whole(line.crane_hours_reading),
        "filters_changed": ",".join(data["filters"]),
        "oil_type": data["oil_type"],
        "oil_litres": data["oil_litres"],
        "next_service_hours": data["next_hours"],
        "next_service_km": data["next_km"],
    }
    if record is None:
        MachineServiceRecord.objects.create(
            work_order_line=line, created_by=company_user,
            notes="Anotada desde el parte", **values)
        return "created"
    for field, value in values.items():
        setattr(record, field, value)
    record.save(update_fields=list(values))
    return "updated"
