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

Lo que viene del albarán no se marca dos veces (Miguel Ángel: "lo que
salga en los repuestos es lo que tienen que marcar, y si hay algo
además, se añade"): la casilla muestra los repuestos del albarán
pre-asignados a la máquina, y marcarlos ahí es marcarlos como
consumidos en la tarea (las mismas casillas `consume_part`). Los
filtros que no venían en el albarán se añaden aparte.
"""
from decimal import Decimal
from decimal import InvalidOperation

SERVICE_TYPE = "REVISION"
ALBARAN_PREFIX = "Del albarán: "

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


def parse_service_post(post, prefix, company):
    """
    Service data of one block from the POST, or None if not ticked.

    ---

    Datos de revisión de una tarea (prefijo `entrada_{i}_`), o None si
    la casilla "Revisión" no está marcada.
    """
    if post.get("%sis_service" % prefix, "") != "1":
        return None
    from spare_parts.models import SparePartEntry

    consume = "%sconsume_part_" % prefix
    part_pks = [int(key[len(consume):]) for key in post.keys()
                if key.startswith(consume) and post.get(key) == "1"
                and key[len(consume):].isdigit()]
    albaran_parts = list(SparePartEntry.objects.filter(
        company=company, pk__in=part_pks).order_by("pk").values_list(
        "description", flat=True)) if part_pks else []
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
        "albaran_parts": albaran_parts,
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
        "albaran_note": (record.notes if record.notes.startswith(
            ALBARAN_PREFIX) else ""),
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
    albaran = data.get("albaran_parts") or []
    filters = ", ".join(
        albaran + [FILTER_LABELS[code] for code in data["filters"]])
    _set_type(
        line, WorkOrderEntryLine,
        tipo_tarea=SERVICE_TYPE,
        task_category_free=(
            ("cambio de aceite y filtros (%s)" % filters)[:200]
            if filters else "cambio de aceite"),
        fault_category="",
        fault_subcategory="",
    )
    values = {
        "notes": ((ALBARAN_PREFIX + "; ".join(albaran))[:255] if albaran
                  else (record.notes if record is not None
                        and record.notes.startswith(ALBARAN_PREFIX)
                        else "Anotada desde el parte")),
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
            work_order_line=line, created_by=company_user, **values)
        return "created"
    for field, value in values.items():
        setattr(record, field, value)
    record.save(update_fields=list(values))
    return "updated"
