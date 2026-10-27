# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/shift.py
"""
H30 (S139). Shift type (intensive or split) of a new digital parte.

---

H30 (S139). Tipo de jornada (intensiva o partida) de un parte digital
nuevo, para guardarlo en WorkOrderEntry.is_intensive_shift (Miguel
Ángel: trazabilidad "por si surgen problemas con los horarios").

Se resuelve con la misma cadena que usa el formulario del operario
para decidir si pinta la jornada intensiva o la partida
(`_resolve_operator_schedule` de panel/views_operator.py: interruptor
de intensiva del operario, su horario, el de su sección o el de la
empresa), para que lo guardado sea lo que el operario vio. No se
duplica esa cadena aquí: se reutiliza.
"""
import logging

logger = logging.getLogger(__name__)


def entry_shift_is_intensive(entry):
    """
    True/False for a digital parte with an operator, None otherwise.

    ---

    True si el horario del operario del parte es de jornada intensiva,
    False si es partida, y None si el parte no es digital, no tiene
    operario o el operario no tiene ningún horario (no hay dato real que
    guardar: nunca se inventa).
    """
    from work_order_processor.models import WorkOrder

    work_order = entry.work_order
    if work_order.source != WorkOrder.Source.DIGITAL:
        return None
    operator = work_order.uploaded_by
    if operator is None:
        return None
    try:
        from panel.views_operator import _resolve_operator_schedule

        schedule = _resolve_operator_schedule(operator, work_order.company)
    except Exception:
        logger.exception(
            "# [S139 jornada] No se pudo resolver el horario del operario "
            "%s para el parte %s; se deja la jornada sin registrar.",
            operator.pk, work_order.pk,
        )
        return None
    if schedule is None:
        return None
    return bool(schedule.is_intensive)
